from __future__ import annotations

import numpy as np
import pandas as pd

from frequency_stats import compute_frequency_stats, compute_group_frequency_stats
from gap_cycle_stats import compute_gap_stats, compute_recurrence_intervals


def _sparse(days: int = 10) -> pd.DataFrame:
    frame = pd.DataFrame(0, index=np.arange(days), columns=["date", *range(100)])
    frame["date"] = pd.date_range("2026-01-01", periods=days, freq="D")
    return frame


def test_frequency_separates_occurrences_from_draws_and_two_nhay() -> None:
    history = _sparse(4)
    history.loc[0, 5] = 2
    history.loc[2, 5] = 1
    history.loc[3, 5] = 9  # target-day result must be excluded

    row = compute_frequency_stats(history, "2026-01-04").set_index("number").loc[5]

    assert int(row["eligible_draws"]) == 3
    assert int(row["occurrence_count"]) == 3
    assert int(row["draw_count"]) == 2
    assert float(row["hit_rate_by_draw"]) == 2 / 3
    assert int(row["exactly_two_draws"]) == 1
    assert int(row["at_least_two_draws"]) == 1


def test_frequency_supports_calendar_and_draw_lookbacks() -> None:
    history = _sparse(6)
    history.loc[:, 12] = 1
    calendar = compute_frequency_stats(history, "2026-01-07", lookback_days=3).set_index("number")
    draws = compute_frequency_stats(history, "2026-01-07", lookback_draws=2).set_index("number")

    assert int(calendar.loc[12, "eligible_draws"]) == 3
    assert int(calendar.loc[12, "draw_count"]) == 3
    assert int(draws.loc[12, "eligible_draws"]) == 2
    assert int(draws.loc[12, "draw_count"]) == 2


def test_three_draw_cycle_has_known_ground_truth() -> None:
    history = _sparse(10)
    history.loc[[0, 3, 6, 9], 12] = 1

    row = compute_gap_stats(history, "2026-01-11").set_index("number").loc[12]
    intervals = compute_recurrence_intervals(history, 12, "2026-01-11")

    assert intervals["interval_draws"].tolist() == [3, 3, 3]
    assert intervals["absent_draws"].tolist() == [2, 2, 2]
    assert float(row["mean_interval_draws"]) == 3.0
    assert float(row["median_interval_draws"]) == 3.0
    assert float(row["historical_max_gap_draws"]) == 2.0
    assert int(row["current_gap_draws"]) == 0
    assert int(row["current_gap_calendar_days"]) == 0


def test_head_tail_total_and_cham_use_canonical_memberships() -> None:
    history = _sparse(1)
    history.loc[0, 12] = 1
    history.loc[0, 19] = 2
    as_of = "2026-01-02"

    head = compute_group_frequency_stats(history, as_of, group="head").set_index("value")
    tail = compute_group_frequency_stats(history, as_of, group="tail").set_index("value")
    total = compute_group_frequency_stats(history, as_of, group="total_mod10").set_index("value")
    cham = compute_group_frequency_stats(history, as_of, group="cham").set_index("value")

    assert int(head.loc[1, "occurrence_count"]) == 3
    assert int(head.loc[1, "draw_count"]) == 1
    assert int(tail.loc[2, "occurrence_count"]) == 1
    assert int(total.loc[3, "occurrence_count"]) == 1
    assert int(total.loc[0, "occurrence_count"]) == 2
    assert int(cham.loc[1, "occurrence_count"]) == 3


def test_future_mutation_cannot_change_earlier_statistics() -> None:
    history = _sparse(12)
    history.loc[[0, 3, 6, 9], 12] = 1
    cutoff = "2026-01-08"
    frequency_before = compute_frequency_stats(history, cutoff)
    gap_before = compute_gap_stats(history, cutoff)

    mutated = history.copy()
    future = mutated["date"] >= pd.Timestamp(cutoff)
    mutated.loc[future, list(range(100))] = 7
    frequency_after = compute_frequency_stats(mutated, cutoff)
    gap_after = compute_gap_stats(mutated, cutoff)

    pd.testing.assert_frame_equal(frequency_before, frequency_after)
    pd.testing.assert_frame_equal(gap_before, gap_after)
