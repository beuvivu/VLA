from __future__ import annotations

import numpy as np
import pandas as pd

from research_legacy_extensions import (
    coverage_coupon_summary,
    de_weekday_profile,
    ks_special_uniformity,
    ljung_box_even_tail_count,
    loto_acf_bartlett,
    number_recency_calendar,
    pair_recency_calendar,
    transition_independence_by_number,
)


def _two_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-04", "2026-01-05"]),
            "special": [1, 3, 1, 4],
            "prize1": [2, 9, 2, 8],
        }
    )


def _sparse(pattern: list[int] | None = None, days: int = 12) -> pd.DataFrame:
    arr = np.zeros((days, 100), dtype=int)
    if pattern is not None:
        arr[: len(pattern), 0] = pattern
    df = pd.DataFrame(arr, columns=[str(i) for i in range(100)])
    df.insert(0, "date", pd.date_range("2026-01-01", periods=days, freq="D"))
    return df


def test_number_and_pair_recency_use_calendar_days_and_boundary_absence() -> None:
    two = _two_frame()
    loto = number_recency_calendar(two, mode="loto")
    row = loto[loto["number"] == 1].iloc[0]
    assert row["current_absence_days"] == 1
    assert row["max_completed_interval_days"] == 3
    assert row["max_observed_absence_days"] == 2

    pairs = pair_recency_calendar(two)
    pair = pairs[(pairs["a"] == 1) & (pairs["b"] == 2)].iloc[0]
    assert pair["cooccurrence_days"] == 2
    assert pair["current_absence_days"] == 1
    assert pair["max_completed_interval_days"] == 3
    assert pair["max_observed_absence_days"] == 2


def test_de_weekday_profile_has_complete_7x100_contract() -> None:
    out = de_weekday_profile(_two_frame())
    assert len(out) == 700
    assert set(out["number"]) == set(range(100))
    assert set(out["weekday"]) == set(range(7))


def test_transition_independence_handles_degenerate_numbers_and_fdr() -> None:
    sparse = _sparse([1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0], days=12)
    out = transition_independence_by_number(sparse)
    assert len(out) == 100
    assert {"p_value", "q_value_fdr", "fdr_05", "test"}.issubset(out.columns)
    zero = out[out["number"] == 0].iloc[0]
    assert 0 <= zero["p_next_given_hit"] <= 1
    never = out[out["number"] == 99].iloc[0]
    assert never["test"] == "degenerate_no_variation"
    assert never["p_value"] == 1.0


def test_loto_acf_bartlett_contract_and_constant_series_safety() -> None:
    sparse = _sparse([1, 0] * 6, days=12)
    out = loto_acf_bartlett(sparse, lags=(1, 2))
    assert len(out) == 200
    assert {"acf", "bartlett_lower", "bartlett_upper", "q_value_fdr"}.issubset(out.columns)
    constant = out[(out["number"] == 99) & (out["lag_days"] == 1)].iloc[0]
    assert constant["acf"] == 0.0
    assert constant["p_value"] == 1.0


def test_coverage_coupon_summary_tracks_cumulative_milestones() -> None:
    arr = np.zeros((5, 100), dtype=int)
    for day in range(5):
        arr[day, day * 20 : (day + 1) * 20] = 1
    sparse = pd.DataFrame(arr, columns=[str(i) for i in range(100)])
    sparse.insert(0, "date", pd.date_range("2026-01-01", periods=5))
    summary = coverage_coupon_summary(sparse)
    assert summary["all_time_distinct_numbers"] == 100
    assert summary["first_full_coverage_day_from_start"] == 5
    assert summary["coverage_milestone_days_from_start"]["50"] == 3
    assert summary["unseen_numbers"] == []
    assert summary["coupon_collector_expected_days_approx"] > 0


def test_randomness_extension_metrics_return_valid_probabilities() -> None:
    raw = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=20),
            "special": np.linspace(1000, 99000, 20, dtype=int),
        }
    )
    ks = ks_special_uniformity(raw)
    assert 0 <= ks["p_value"] <= 1

    rows = []
    for day in range(20):
        row = {"date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=day)}
        for j in range(27):
            row[f"p{j}"] = 10 + ((j + day) % 2)
        rows.append(row)
    two = pd.DataFrame(rows)
    lb = ljung_box_even_tail_count(two, lags=5)
    assert lb["lags"] == 5
    assert 0 <= lb["p_value"] <= 1
