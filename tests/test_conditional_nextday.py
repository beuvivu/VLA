from __future__ import annotations

import numpy as np
import pandas as pd

from conditional_nextday import compute_loto_nextday_given_special


def _two(dates: list[str]) -> pd.DataFrame:
    cols = ["special"] + [f"p{i}" for i in range(1, 27)]
    rows = []
    for t, d in enumerate(dates):
        vals = [(10 * t + i) % 100 for i in range(27)]
        vals[0] = t % 2  # two repeating special states 00/01
        rows.append({"date": d, **dict(zip(cols, vals))})
    return pd.DataFrame(rows)


def test_conditional_matrix_has_probabilities_and_fdr():
    dates = pd.date_range("2026-01-01", periods=50, freq="D").strftime("%Y-%m-%d").tolist()
    out = compute_loto_nextday_given_special(_two(dates), prior_strength=20.0)
    assert not out.empty
    assert set(out["special"].unique()) == {0, 1}
    assert out["p_raw"].between(0, 1).all()
    assert out["p_eb"].between(0, 1).all()
    assert out["baseline"].between(0, 1).all()
    assert out["p_value"].between(0, 1).all()
    assert out["q_value_fdr"].between(0, 1).all()
    assert np.allclose(out["p"], out["p_raw"])


def test_missing_calendar_day_is_not_treated_as_next_day_pair():
    full_dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    gap_dates = ["2026-01-01", "2026-01-02", "2026-01-04"]
    full = compute_loto_nextday_given_special(_two(full_dates), prior_strength=0.0)
    gap = compute_loto_nextday_given_special(_two(gap_dates), prior_strength=0.0)

    # State 01 occurs at source row 1. In the gapped history its following row is
    # Jan-04, which must NOT be counted as a t+1 trial for Jan-02.
    full_trials = int(full.loc[full["special"] == 1, "trials"].iloc[0])
    gap_state = gap[gap["special"] == 1]
    assert full_trials == 1
    assert gap_state.empty


def test_empirical_bayes_probability_shrinks_toward_baseline():
    dates = pd.date_range("2026-01-01", periods=40, freq="D").strftime("%Y-%m-%d").tolist()
    raw = compute_loto_nextday_given_special(_two(dates), prior_strength=0.0)
    shrunk = compute_loto_nextday_given_special(_two(dates), prior_strength=100.0)
    key = ["special", "number"]
    merged = raw.merge(shrunk, on=key, suffixes=("_raw0", "_shrunk"))
    distance_raw = (merged["p_eb_raw0"] - merged["baseline_raw0"]).abs()
    distance_shrunk = (merged["p_eb_shrunk"] - merged["baseline_shrunk"]).abs()
    assert (distance_shrunk <= distance_raw + 1e-12).all()
