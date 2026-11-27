from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from core.xsmb_domain import FIELD_WIDTHS
from core.xsmb_schedule import ERAS, ScheduleEra
from stats import xsmb_venue_effects as v

UNITS = v._TAIL_INDEX


def _frame(digits: np.ndarray, start: date = date(2020, 1, 1)) -> pd.DataFrame:
    rows, offset = {"date": [(start + timedelta(days=i)).isoformat() for i in range(digits.shape[0])]}, 0
    for field, width in FIELD_WIDTHS:
        rows[field] = ["".join(str(d) for d in row) for row in digits[:, offset:offset + width]]
        offset += width
    return pd.DataFrame(rows)


def _fair(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 10, size=(n, 107))


def _venue_bias(digits: np.ndarray, start: date = date(2020, 1, 1), weekday: int = 1, share: float = 0.4,
                seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = digits.copy()
    days = np.array([(start + timedelta(days=i)).weekday() for i in range(out.shape[0])])
    rows = np.flatnonzero(days == weekday)
    mask = rng.random((rows.size, UNITS.size)) < share
    block = out[np.ix_(rows, UNITS)]
    block[mask] = 7
    out[np.ix_(rows, UNITS)] = block
    return out


@pytest.fixture(scope="module")
def fair_draws() -> v.Draws:
    return v.from_frame(_frame(_fair(840, seed=1)))


@pytest.fixture(scope="module")
def biased_draws() -> v.Draws:
    return v.from_frame(_frame(_venue_bias(_fair(840, seed=1))))


def test_draws_follow_the_schedule_and_rebuild_every_digit(fair_draws: v.Draws) -> None:
    assert fair_draws.n == 840 and fair_draws.digits.shape == (840, 107)
    assert fair_draws.venue[:7] == ("Bắc Ninh", "Hà Nội", "Hải Phòng", "Nam Định", "Thái Bình", "Hà Nội", "Quảng Ninh")
    assert int(fair_draws.loto[0, 0]) == fair_draws.digits[0, 3] * 10 + fair_draws.digits[0, 4]
    assert np.array_equal(fair_draws.special, fair_draws.loto[:, 0])
    assert v.CAGE_OF_DIGIT[:5].tolist() == [4, 3, 2, 1, 0] and v.CAGE_OF_DIGIT[-2:].tolist() == [1, 0]


def test_fair_history_shows_no_venue_effect(fair_draws: v.Draws) -> None:
    rows = v.heterogeneity_tests(fair_draws, permutations=99, seed=3)
    assert len(rows) == 10
    assert not any(row["rejected"] for row in rows)
    assert all(0 < row["p_value"] <= 1 for row in rows)


def test_the_default_permutations_can_reach_significance_after_holm() -> None:
    assert v.HETEROGENEITY_TESTS / (v.PERMUTATIONS + 1) < v.ALPHA
    assert v.HETEROGENEITY_TESTS / (999 + 1) >= v.ALPHA


def test_a_planted_venue_bias_is_found_by_permutation(biased_draws: v.Draws) -> None:
    rows = {(row["grouping"], row["statistic"]): row
            for row in v.heterogeneity_tests(biased_draws, permutations=v.PERMUTATIONS)}
    for key in (("đài", "loto"), ("đài", "cage_digits"), ("thứ", "cage_digits")):
        assert rows[key]["p_value"] == pytest.approx(1 / (v.PERMUTATIONS + 1)) and rows[key]["rejected"], key
    assert all(row["min_attainable_p_holm"] < v.ALPHA for row in rows.values())
    assert all(row["p_holm"] >= row["p_value"] for row in rows.values())


def test_the_permutation_is_reproducible(fair_draws: v.Draws) -> None:
    first = v.heterogeneity_tests(fair_draws, permutations=49, seed=11)
    again = v.heterogeneity_tests(fair_draws, permutations=49, seed=11)
    assert first == again


def test_cage_monitor_flags_only_the_biased_venue(biased_draws: v.Draws, fair_draws: v.Draws) -> None:
    fair = {row["venue"]: row for row in v.cage_monitor(fair_draws)}
    assert not any(row["flagged_on"] or row["detector_alarm_on"] for row in fair.values())
    biased = {row["venue"]: row for row in v.cage_monitor(biased_draws)}
    assert biased["Quảng Ninh"]["flagged_on"] and biased["Quảng Ninh"]["detector_alarm_on"]
    assert biased["Quảng Ninh"]["largest_deviation"]["cage"] == "đơn vị"
    assert biased["Quảng Ninh"]["largest_deviation"]["digit"] == 7
    assert not biased["Hải Phòng"]["flagged_on"] and not biased["Hải Phòng"]["detector_alarm_on"]
    assert biased[v.POOLED]["pooled"] and biased[v.POOLED]["draws"] == biased_draws.n


def test_the_detector_adapts_to_a_change_that_starts_late() -> None:
    rng = np.random.default_rng(8)
    counts = np.zeros((900, v.CAGES, 10))
    for t in range(900):
        for cage in range(v.CAGES):
            p = np.full(10, 0.1)
            if t >= 600 and cage == 0:
                p[3] = 0.0
                p[[d for d in range(10) if d != 3]] = 1 / 9
            counts[t, cage] = rng.multinomial(int((v.CAGE_OF_DIGIT == cage).sum()), p)
    threshold = math.log10(v.DETECTOR_YEARS * 52.18 * 7 / v.ALPHA)
    adaptive = v.change_detector(counts) / math.log(10)
    alarm = np.flatnonzero(adaptive >= threshold)
    assert alarm.size and 600 <= alarm[0] < 700
    frozen = v.change_detector(counts, memory=1e12) / math.log(10)
    assert frozen[:alarm[0] + 1].max() < threshold
    cumulative = np.cumsum(counts, axis=0)
    assert (v._kt_log_e(cumulative[:alarm[0] + 1]) / math.log(10)).max() < threshold


def test_the_detector_threshold_bounds_false_alarms_over_the_horizon(fair_draws: v.Draws) -> None:
    rows = v.cage_monitor(fair_draws)
    sequences = len(rows)
    for row in rows:
        horizon = v.DETECTOR_YEARS * 52.18 * row["draws_per_week"]
        assert row["detector_log10_threshold"] == pytest.approx(math.log10(horizon * sequences / v.ALPHA), abs=1e-4)


def test_monitor_keys_split_by_era(monkeypatch: pytest.MonkeyPatch) -> None:
    start = date(2020, 1, 1)
    renamed = ScheduleEra(start=start + timedelta(days=420), venues=ERAS[0].venues, basis="cùng tên, thời kỳ mới")
    eras = (*ERAS, renamed)
    monkeypatch.setattr(v, "era_for", lambda day: next(e for e in reversed(eras) if e.start <= day))
    draws = v.from_frame(_frame(_fair(840, seed=4), start))
    rows = v.cage_monitor(draws)
    pooled = [row for row in rows if row["pooled"]]
    assert [row["era_start"] for row in pooled] == [ERAS[0].start.isoformat(), renamed.start.isoformat()]
    assert sum(row["draws"] for row in pooled) == draws.n
    assert len(rows) == 2 * 7


def test_the_venue_model_is_promoted_only_when_it_wins(fair_draws: v.Draws, biased_draws: v.Draws) -> None:
    fair = v.walk_forward(fair_draws, test_draws=300)
    assert not fair["modes"]["loto"]["comparisons"]["đài"]["promoted"]
    biased = v.walk_forward(biased_draws, test_draws=300)
    venue = biased["modes"]["loto"]["comparisons"]["đài"]
    assert venue["promoted"]
    assert venue["vs_pooled"]["z"] >= v.PROMOTE_Z and venue["vs_constant"]["z"] >= v.PROMOTE_Z
    assert venue["kappa"] < max(v.KAPPA_GRID)


def test_walk_forward_never_reads_the_draw_it_scores(biased_draws: v.Draws) -> None:
    altered_digits = biased_draws.digits.copy()
    altered_digits[-1] = (altered_digits[-1] + 1) % 10
    altered = v.Draws(dates=biased_draws.dates, digits=altered_digits, venue=biased_draws.venue)
    base = v.walk_forward(biased_draws, test_draws=300, keep_losses=True)
    other = v.walk_forward(altered, test_draws=300, keep_losses=True)
    for mode in ("loto", "de"):
        for name, losses in base["modes"][mode]["losses"].items():
            assert losses[:-1] == other["modes"][mode]["losses"][name][:-1], (mode, name)
    assert base["modes"]["loto"]["losses"]["đài"][-1] != other["modes"]["loto"]["losses"]["đài"][-1]


def test_reading_is_written_from_the_numbers(biased_draws: v.Draws) -> None:
    summary, profile = v.summarize(biased_draws, test_draws=300)
    assert "KHÁC NHAU" in summary["reading"] and "Quảng Ninh" in summary["reading"]
    assert set(profile["mode"]) == {"loto", "de"} and len(profile) == 2 * 6 * 100
    seven = profile[(profile["mode"] == "loto") & (profile["venue"] == "Quảng Ninh") & (profile["number"].str[1] == "7")]
    assert (seven["z"] > 3).all()
    assert profile["q_value"].between(0, 1).all()


def test_the_real_ledger_runs_and_is_deterministic(tmp_path) -> None:
    from core.paths import REPO_ROOT
    import shutil
    (tmp_path / "data").mkdir()
    shutil.copy(REPO_ROOT / "data" / "xsmb.csv", tmp_path / "data" / "xsmb.csv")
    first = [p.read_bytes() for p in v.run(tmp_path, permutations=19)]
    again = [p.read_bytes() for p in v.run(tmp_path, permutations=19)]
    assert first == again
