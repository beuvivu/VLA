from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from vietlott_engine.core.products import ProductCode
from vietlott_engine.forecast.data import Series, digit_counts
from vlm.forecast import transfer as tr

ROOT = Path(__file__).resolve().parents[1]
A, B = tr.PRODUCTS


def _series(product: ProductCode, start: date, n: int, seed: int, *, six: float = 0.1, step: int = 2) -> Series:
    rng = np.random.default_rng(seed)
    digits = rng.integers(0, 10, size=(n, 20, 3))
    units = np.where(rng.random((n, 20)) < six, 6, rng.choice([d for d in range(10) if d != 6], size=(n, 20)))
    if six != 0.1:
        digits[:, :, 2] = units
    dates = np.array([np.datetime64(start + timedelta(days=step * i), "D") for i in range(n)])
    return Series(product, np.arange(1, n + 1), dates, {"digits": {"C": digit_counts(digits, 10)}})


def _by_product(steps: list[tr.Step], product: ProductCode) -> list[tr.Step]:
    return [s for s in steps if s.product == product]


def test_the_two_products_share_one_digit_layout_and_the_engine_switch_rate() -> None:
    spec = tr._spec()
    assert (spec.positions, spec.alphabet, spec.per_draw) == (3, 10, 20)
    assert tr.share(A) == pytest.approx(1 / (10 * 156)) and tr.share(B) == pytest.approx(1 / (10 * 156))


def test_the_mixture_never_trails_the_own_law_by_more_than_the_bound() -> None:
    series = {A: _series(A, date(2020, 1, 1), 300, seed=1, six=0.13),
              B: _series(B, date(2020, 1, 2), 300, seed=2, six=0.1)}
    steps, _ = tr.walk_forward(series)
    for product in (A, B):
        mine = _by_product(steps, product)
        regret = np.cumsum([s.sep - s.mix for s in mine])
        for t, value in enumerate(regret, start=1):
            assert value <= tr.fixed_share_bound(t, product) + 1e-9


def test_a_shared_bias_is_learned_faster_together() -> None:
    series = {A: _series(A, date(2020, 1, 1), 500, seed=3, six=0.13),
              B: _series(B, date(2022, 9, 1), 150, seed=4, six=0.13)}
    steps, model = tr.walk_forward(series)
    late = _by_product(steps, B)
    gain = np.array([s.mix - s.sep for s in late])
    assert gain.sum() > 2.0 and gain.mean() / (gain.std(ddof=1) / math.sqrt(gain.size)) > 2.0
    own, pooled, w_pool = model.laws(B)
    assert w_pool > 0.5
    mixed = model.mixed(B)
    assert int(np.argmax(mixed[2])) == 6 and mixed.sum(axis=1) == pytest.approx([1.0, 1.0, 1.0])
    assert np.abs(mixed - pooled).max() < np.abs(mixed - own).max()


def test_diverging_products_fall_back_to_their_own_law() -> None:
    series = {A: _series(A, date(2020, 1, 1), 500, seed=5, six=0.14),
              B: _series(B, date(2020, 1, 2), 500, seed=6, six=0.1)}
    steps, model = tr.walk_forward(series)
    own = _by_product(steps, B)
    pooled_loss = sum(s.sep - s.pool for s in own)
    mixed_loss = sum(s.sep - s.mix for s in own)
    assert pooled_loss > 5.0 and mixed_loss < tr.fixed_share_bound(len(own), B)
    assert model.laws(B)[2] < 0.1


def test_draws_of_the_same_day_do_not_see_each_other() -> None:
    a = _series(A, date(2021, 1, 1), 60, seed=7, six=0.13, step=1)
    b = _series(B, date(2021, 1, 1), 60, seed=8, six=0.13, step=1)
    base, _ = tr.walk_forward({A: a, B: b})
    changed = a.obs["digits"]["C"].copy()
    changed[40] = np.roll(changed[40], 1, axis=-1)
    altered = Series(A, a.draw_ids, a.dates, {"digits": {"C": changed}})
    other, _ = tr.walk_forward({A: altered, B: b})
    b_base, b_other = _by_product(base, B), _by_product(other, B)
    assert [s.mix for s in b_base[:41]] == [s.mix for s in b_other[:41]]
    assert b_base[41].pool != b_other[41].pool


def test_prospective_scores_only_later_draws_and_never_rewrites_a_row(tmp_path: Path) -> None:
    start = tr.REGISTERED_ON - timedelta(days=20)
    series = {A: _series(A, start, 20, seed=9, step=2), B: _series(B, start + timedelta(days=1), 20, seed=10, step=2)}
    ledger = tmp_path / tr.LEDGER
    steps, _ = tr.walk_forward(series)
    through = tr.final_through(series)
    first = tr.prospective(steps, ledger, through, "dau-van-tay")
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert rows and all(tr.REGISTERED_ON < date.fromisoformat(r["date"]) <= through for r in rows)
    assert all(r["engine"] == "dau-van-tay" for r in rows)
    later = [s for s in steps if tr.REGISTERED_ON < s.day <= through]
    assert len(rows) == len(later) and first["ledger_consistent"] and first["engine_consistent"]
    assert first["products"][A.value]["draws"] == len(_by_product(later, A))
    text = ledger.read_text(encoding="utf-8")
    assert tr.prospective(steps, ledger, through, "dau-van-tay") == first and ledger.read_text(encoding="utf-8") == text
    shifted = [tr.Step(s.product, s.draw_id, s.day, s.sep, s.pool, s.mix + 1.0, s.w_pool) for s in steps]
    third = tr.prospective(shifted, ledger, through, "dau-van-tay")
    assert not third["ledger_consistent"] and ledger.read_text(encoding="utf-8") == text


def _drop(series: Series, index: int) -> Series:
    keep = np.arange(len(series)) != index
    return Series(series.product, series.draw_ids[keep], series.dates[keep],
                  {"digits": {"C": series.obs["digits"]["C"][keep]}})


def test_a_row_is_written_only_once_every_product_has_caught_up(tmp_path: Path) -> None:
    start = tr.REGISTERED_ON + timedelta(days=1)
    full = {A: _series(A, start, 6, seed=21, six=0.13, step=2), B: _series(B, start + timedelta(days=1), 6, seed=22, six=0.13, step=2)}
    late = {A: full[A], B: full[B].head(2)}
    gap = {A: full[A], B: _drop(full[B], 2)}
    assert tr.final_through(late) == full[B].dates[1].astype(object)
    assert tr.final_through(gap) == full[B].dates[1].astype(object)
    ledger = tmp_path / tr.LEDGER
    steps, _ = tr.walk_forward(late)
    partial = tr.prospective(steps, ledger, tr.final_through(late), "fp")
    written = {(r["product"], r["draw_id"]) for r in map(json.loads, ledger.read_text(encoding="utf-8").splitlines())}
    assert all(day <= full[B].dates[1].astype(object) for day in
               [s.day for s in steps if (s.product.value, s.draw_id) in written])
    assert partial["products"][A.value]["draws"] == 2
    steps_full, _ = tr.walk_forward(full)
    done = tr.prospective(steps_full, ledger, tr.final_through(full), "fp")
    assert done["ledger_consistent"]
    rows = {(r["product"], r["draw_id"]): r for r in map(json.loads, ledger.read_text(encoding="utf-8").splitlines())}
    for step in steps_full:
        if step.day <= tr.final_through(full):
            assert rows[(step.product.value, step.draw_id)]["gain_vs_separate"] == pytest.approx(step.mix - step.sep, abs=1e-8)


def test_a_changed_engine_stops_the_ledger_and_blocks_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    start = tr.REGISTERED_ON + timedelta(days=1)
    series = {A: _series(A, start, 8, seed=23, six=0.13, step=2), B: _series(B, start + timedelta(days=1), 8, seed=24, six=0.13, step=2)}
    fingerprint = tr.engine_fingerprint()
    assert fingerprint == tr.engine_fingerprint() and len(fingerprint) == 16
    monkeypatch.setattr(tr.Forecaster, "SWITCH_YEARS", 5.0)
    assert tr.engine_fingerprint() != fingerprint
    monkeypatch.undo()
    original = tr.BayesMixtureExpert.predict
    monkeypatch.setattr(tr.BayesMixtureExpert, "predict", lambda self: original(self) * (1 + 1e-6))
    assert tr.engine_fingerprint() != fingerprint
    monkeypatch.undo()
    ledger = tmp_path / tr.LEDGER
    steps, _ = tr.walk_forward(series)
    first_half = [s for s in steps if s.day <= start + timedelta(days=6)]
    tr.prospective(first_half, ledger, tr.final_through(series), fingerprint)
    before = ledger.read_text(encoding="utf-8")
    changed = tr.prospective(steps, ledger, tr.final_through(series), "khac")
    assert not changed["engine_consistent"] and ledger.read_text(encoding="utf-8") == before
    assert not any(v["eligible"] for v in changed["products"].values())


def test_eligibility_needs_a_ledger_that_still_matches_the_rule(tmp_path: Path) -> None:
    start = tr.REGISTERED_ON + timedelta(days=1)
    rows = [{"version": tr.VERSION, "product": A.value, "draw_id": i, "engine": "fp", "date": (start + timedelta(days=2 * i)).isoformat(),
             "gain_vs_separate": 1.0 + 0.01 * i, "gain_vs_uniform": 1.0} for i in range(1, 6)]
    ledger = tmp_path / tr.LEDGER
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    steps = [tr.Step(A, i, date.fromisoformat(r["date"]), 0.0, 0.0, 0.5, 0.5) for i, r in zip(range(1, 6), rows)]
    out = tr.prospective(steps, ledger, start + timedelta(days=20), "fp")
    assert not out["ledger_consistent"] and out["products"][A.value]["z"] > tr.PROMOTE_Z
    assert not out["products"][A.value]["eligible"]
    matching = [tr.Step(A, i, date.fromisoformat(r["date"]), 0.0, 0.0, r["gain_vs_separate"], 0.5) for i, r in zip(range(1, 6), rows)]
    assert tr.prospective(matching, ledger, start + timedelta(days=20), "fp")["products"][A.value]["eligible"]


def test_a_second_run_over_recorded_rows_still_writes_the_summary(tmp_path: Path) -> None:
    start = tr.REGISTERED_ON - timedelta(days=20)
    series = {A: _series(A, start, 20, seed=9, step=2), B: _series(B, start + timedelta(days=1), 20, seed=10, step=2)}
    tr.write(series, tmp_path)
    ledger = tmp_path / tr.LEDGER
    assert ledger.read_text(encoding="utf-8").strip()
    path = tr.write(series, tmp_path)
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert summary["prospective"]["ledger_consistent"] is True
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert summary["prospective"]["products"][A.value]["draws"] == sum(r["product"] == A.value for r in rows)


def test_write_is_deterministic_and_keeps_an_unchanged_summary(tmp_path: Path) -> None:
    series = {A: _series(A, date(2020, 1, 1), 120, seed=11, six=0.13),
              B: _series(B, date(2020, 1, 2), 120, seed=12, six=0.13)}
    path = tr.write(series, tmp_path)
    first = path.read_bytes()
    stamp = path.stat().st_mtime_ns
    tr.write(series, tmp_path)
    assert path.read_bytes() == first and path.stat().st_mtime_ns == stamp
    summary = json.loads(first)
    assert summary["deployment"] == "shadow" and summary["version"] == tr.VERSION
    block = summary["walk_forward"][A.value]
    assert block["draws"] == 120 and len(block["next"]["mixed"]) == 3
    assert block["log10_wealth"]["mixed"] - block["log10_wealth"]["separate"] == pytest.approx(
        block["mixed_vs_separate"]["log10"], abs=1e-8)


def test_the_committed_summary_carries_the_frozen_rule() -> None:
    summary = json.loads((ROOT / "data" / "forecast" / tr.SUMMARY).read_text(encoding="utf-8"))
    assert summary["version"] == tr.VERSION and summary["products"] == [p.value for p in tr.PRODUCTS]
    assert summary["rule"]["registered_on"] == tr.REGISTERED_ON.isoformat()
    assert summary["rule"]["prior_pooled"] == tr.PRIOR_POOLED
    registered = tr.REGISTERED_ON.isoformat()
    through = summary["prospective"]["ledger_through"]
    ledger = [json.loads(line) for line in (ROOT / "data" / "forecast" / tr.LEDGER).read_text(encoding="utf-8").splitlines()
              if line.strip()]
    rows = [r for r in ledger if r["version"] == tr.VERSION]
    assert all(registered < r["date"] <= through for r in rows)
    for k, v in summary["walk_forward"].items():
        assert summary["prospective"]["products"][k]["draws"] == sum(r["product"] == k for r in rows)
        if registered < v["last_date"] <= through:
            assert summary["prospective"]["products"][k]["draws"] > 0
    assert summary["prospective"]["ledger_consistent"] and summary["prospective"]["engine_consistent"]
    assert summary["prospective"]["engine_fingerprint"] == tr.engine_fingerprint()


def test_fixed_share_keeps_a_floor_under_the_losing_law() -> None:
    model = tr.TransferModel()
    counts = np.zeros((3, 10))
    counts[:, 6] = 20
    model.pool.learn(np.tile(np.eye(10)[3] * 20, (3, 1)), 1)
    for _ in range(40):
        model.score(B, counts, 1, date(2020, 1, 1))
    w_pool = model.laws(B)[2]
    floor = tr.share(B) * tr.PRIOR_POOLED
    assert floor * 0.999 <= w_pool < 3 * floor
