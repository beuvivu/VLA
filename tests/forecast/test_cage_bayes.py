from __future__ import annotations

import itertools
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.xsmb_domain import FIELD_WIDTHS
from forecast import cage_bayes as cb
from stats.xsmb_venue_effects import CAGE_OF_DIGIT, from_frame

ROOT = Path(__file__).resolve().parents[2]
UNITS = np.flatnonzero(CAGE_OF_DIGIT == 0)
SMALL = {"kappas": (300.0, 3000.0), "hazards": (1 / 250,), "share": 5e-4, "prior_uniform": 0.5, "max_run": 400}


def _digits(n: int, seed: int, *, biased: slice | None = None, share: float = 0.35) -> np.ndarray:
    rng = np.random.default_rng(seed)
    digits = rng.integers(0, 10, size=(n, 107))
    if biased is not None:
        rows = np.arange(n)[biased]
        mask = rng.random((rows.size, UNITS.size)) < share
        block = digits[np.ix_(rows, UNITS)]
        block[mask] = 7
        digits[np.ix_(rows, UNITS)] = block
    return digits


def _draws(digits: np.ndarray, start: date = date(2020, 1, 1)):
    rows, offset = {"date": [(start + timedelta(days=i)).isoformat() for i in range(digits.shape[0])]}, 0
    for name, width in FIELD_WIDTHS:
        rows[name] = ["".join(str(d) for d in row) for row in digits[:, offset:offset + width]]
        offset += width
    return from_frame(pd.DataFrame(rows))


def _scores(digits: np.ndarray, config: dict = SMALL, warmup: int = 50):
    draws = _draws(digits)
    scores, model = cb.walk_forward(cb.cage_counts(draws), cb.loto_outcome(draws), draws.special,
                                    config=config, warmup=warmup)
    return draws, scores, model


def test_cage_counts_follow_the_last_two_digits_of_every_prize() -> None:
    draws = _draws(_digits(5, seed=1))
    counts = cb.cage_counts(draws)
    assert counts.shape == (5, 2, 10) and (counts.sum(axis=-1) == 27).all()
    units, tens = draws.loto % 10, draws.loto // 10
    assert np.array_equal(counts[0, 0], np.bincount(units[0], minlength=10))
    assert np.array_equal(counts[0, 1], np.bincount(tens[0], minlength=10))
    outcome = cb.loto_outcome(draws)
    assert set(np.flatnonzero(outcome[0])) == set(draws.loto[0].tolist())


@pytest.mark.parametrize("total", [1, 2, 3])
def test_the_dirichlet_multinomial_likelihood_is_a_distribution(total: int) -> None:
    alpha = np.random.default_rng(total).uniform(0.2, 5.0, size=10)
    mass = 0.0
    for cells in itertools.combinations_with_replacement(range(10), total):
        counts = np.bincount(cells, minlength=10).astype(float)
        coef = math.factorial(total) / math.prod(math.factorial(int(c)) for c in counts)
        mass += coef * math.exp(float(cb.dirichlet_multinomial_log(alpha, counts)))
    assert mass == pytest.approx(1.0, abs=1e-12)


def test_the_mixture_never_loses_more_than_the_fixed_share_bound() -> None:
    for digits in (_digits(400, seed=2), _digits(400, seed=3, biased=slice(100, 250))):
        _, scores, _ = _scores(digits, warmup=0)
        regret = -float(np.cumsum(scores["log_lr"]).min())
        for t in range(1, digits.shape[0] + 1):
            assert -scores["log_lr"][:t].sum() <= cb.fixed_share_bound(t, SMALL) + 1e-9
        assert regret <= cb.fixed_share_bound(400, SMALL)
    assert cb.fixed_share_bound(4000) == pytest.approx(math.log(2) - 4000 * math.log1p(-5e-4))


def test_the_model_adapts_to_a_planted_change_and_keeps_still_on_fair_draws() -> None:
    digits = _digits(700, seed=4, biased=slice(400, 700))
    _, scores, model = _scores(digits)
    before, after = scores["gain_loto"][50:400], scores["gain_loto"][400:]
    assert abs(before.sum()) < 2.0
    assert after.sum() > 10.0 and after.mean() / (after.std(ddof=1) / math.sqrt(after.size)) > 2.0
    assert scores["gain_de"][400:].sum() > 0
    assert np.nanmean(scores["uniform_weight"][50:400]) > 0.8 > 0.2 > np.nanmean(scores["uniform_weight"][600:])
    forecast = model.forecast()
    assert int(np.argmax(forecast.digits[0])) == 7 and forecast.digits[0, 7] > 0.25
    assert forecast.loto[7] > cb.LOTO_BASELINE_RATE > forecast.loto[8]
    assert forecast.special.sum() == pytest.approx(1.0) and forecast.digits.sum(axis=1) == pytest.approx([1.0, 1.0])


def test_fixed_share_lets_the_fair_forecast_regain_weight_after_a_biased_spell() -> None:
    digits = _digits(500, seed=5, biased=slice(100, 300))
    sharing = cb.CageBayes(dict(SMALL))
    frozen = cb.CageBayes({**SMALL, "share": 1e-15})
    for t, row in enumerate(cb.cage_counts(_draws(digits))):
        sharing.update(row)
        frozen.update(row)
        if t == 299:
            assert sharing.forecast().uniform_weight < 0.01 and frozen.forecast().uniform_weight < 0.01
    assert sharing.forecast().uniform_weight > 0.9 > 0.01 > frozen.forecast().uniform_weight


def test_walk_forward_never_reads_the_draw_it_scores() -> None:
    digits = _digits(200, seed=6)
    _, base, _ = _scores(digits)
    altered = digits.copy()
    altered[-1] = (altered[-1] + 3) % 10
    _, other, _ = _scores(altered)
    for name in ("gain_loto", "gain_de", "uniform_weight", "log_lr"):
        assert np.array_equal(base[name][:-1], other[name][:-1], equal_nan=True), name
    assert base["log_lr"][-1] != other["log_lr"][-1] and base["gain_loto"][-1] != other["gain_loto"][-1]
    draws = _draws(digits)
    counts, outcome = cb.cage_counts(draws), cb.loto_outcome(draws)
    model = cb.CageBayes(dict(SMALL))
    for row in counts[:120]:
        model.update(row)
    forecast = model.forecast()
    expected = cb._bernoulli_total(cb._CONSTANT_LOTO, outcome[120]) - cb._bernoulli_total(forecast.loto, outcome[120])
    assert base["gain_loto"][120] == pytest.approx(expected, abs=1e-12)
    assert base["gain_de"][120] == pytest.approx(math.log(forecast.special[draws.special[120]] / 0.01), abs=1e-12)


def test_the_digit_evidence_crosses_the_threshold_only_when_the_machine_drifts() -> None:
    _, fair, _ = _scores(_digits(600, seed=7), warmup=0)
    _, drift, _ = _scores(_digits(600, seed=7, biased=slice(300, 600)), warmup=0)
    threshold = math.log(1 / cb.ALPHA)
    assert np.cumsum(fair["log_lr"]).max() < threshold
    assert np.cumsum(drift["log_lr"][300:]).max() > threshold


def test_prospective_scores_only_later_draws_and_never_rewrites_a_row(tmp_path: Path) -> None:
    registry, ledger = tmp_path / "reg.json", tmp_path / "led.csv"
    dates = tuple(date(2026, 11, 20) + timedelta(days=i) for i in range(6))
    values = np.array([0.5, -0.1, 0.2, 0.3, -0.4, 1.0])
    first = cb.prospective(dates[:3], values[:3], registry, ledger)
    assert first["registered_on"] == "2026-11-22" and first["draws"] == 0 and first["ledger_consistent"]
    second = cb.prospective(dates, values, registry, ledger)
    assert second["draws"] == 3 and second["log10_e"] == pytest.approx(values[3:].sum() / math.log(10))
    rows = ledger.read_text(encoding="utf-8").splitlines()
    assert rows[0] == "date,version,log_e,log_e_total" and [r.split(",")[0] for r in rows[1:]] == [
        "2026-11-23", "2026-11-24", "2026-11-25"]
    changed = values.copy()
    changed[3] = 9.0
    third = cb.prospective(dates, changed, registry, ledger)
    assert not third["ledger_consistent"] and ledger.read_text(encoding="utf-8").splitlines() == rows
    assert third["log10_e"] == pytest.approx(second["log10_e"])
    renewed = cb.prospective(dates, values, registry, ledger, version=cb.VERSION + 1)
    saved = json.loads(registry.read_text(encoding="utf-8"))
    assert renewed["registered_on"] == "2026-11-25" and renewed["draws"] == 0
    assert [item["version"] for item in saved["retired"]] == [cb.VERSION]
    assert ledger.read_text(encoding="utf-8").splitlines()[:4] == rows


def test_the_summary_reads_from_its_own_numbers_and_is_deterministic(tmp_path: Path) -> None:
    draws = _draws(_digits(500, seed=8, biased=slice(300, 500)))
    first = cb.summarize(draws, config=SMALL, warmup=50, registry_path=tmp_path / "r.json", ledger_path=tmp_path / "l.csv")
    again = cb.summarize(draws, config=SMALL, warmup=50, registry_path=tmp_path / "r.json", ledger_path=tmp_path / "l.csv")
    assert json.dumps(first, sort_keys=True) == json.dumps(again, sort_keys=True)
    whole = first["windows"]["all"]
    assert whole["loto"]["draws"] == 450 and [row["label"] for row in first["by_year"]] == ["2020", "2021"]
    assert f"{whole['loto']['total']:+.2f}".replace(".", ",") in first["reading"]
    assert first["promotion"]["deployment"] == "shadow"
    assert first["promotion"]["eligible"] == (whole["loto"]["z"] >= cb.PROMOTE_Z and first["prospective"]["evidence"])
    assert len(first["state"]["next_loto"]) == 100 and 0 < first["state"]["uniform_weight"] < 1


def test_the_committed_outputs_carry_the_frozen_rule() -> None:
    summary = json.loads((ROOT / "data" / cb.OUT_DIR / cb.SUMMARY).read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "data" / cb.REGISTRY).read_text(encoding="utf-8"))
    assert summary["version"] == cb.VERSION and summary["config"] == cb._config_json(cb.CONFIG)
    registration = registry["registration"]
    assert registration["version"] == cb.VERSION and registration["config"] == cb._config_json(cb.CONFIG)
    assert registration["registered_on"] <= summary["data_through"]
    assert summary["prospective"]["registered_on"] == registration["registered_on"]
