from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stats.advanced_stats import compute_cycle_stats  # noqa: E402
from stats.gap_cycle_stats import compute_gap_stats  # noqa: E402


def _sparse(rows: list[tuple[str, list[int]]]) -> pd.DataFrame:
    records = []
    for day, numbers in rows:
        record: dict[str, object] = {"date": day}
        for number in range(100):
            record[number] = numbers.count(number)
        records.append(record)
    return pd.DataFrame(records)


def test_current_gap_counts_draws_across_a_suspension() -> None:
    frame = _sparse(
        [
            ("2020-01-01", [7, 1]),
            ("2020-01-02", [7, 2]),
            ("2020-01-22", [3]),
            ("2020-01-23", [4]),
        ]
    )
    cycle = compute_cycle_stats(frame).set_index("value")
    assert int(cycle.loc[7, "current_gap"]) == 2

    cutoff = pd.Timestamp("2020-01-24")
    canonical = compute_gap_stats(frame, cutoff).set_index("number")
    assert int(canonical.loc[7, "current_gap_draws"]) == 2
    assert int(canonical.loc[7, "current_gap_calendar_days"]) == 21


def test_interval_columns_are_in_draws_too() -> None:
    frame = _sparse(
        [
            ("2020-01-01", [7]),
            ("2020-01-02", [0]),
            ("2020-01-03", [7]),
            ("2020-01-25", [7]),
            ("2020-01-26", [0]),
        ]
    )
    cycle = compute_cycle_stats(frame).set_index("value")
    assert float(cycle.loc[7, "min_gap"]) == 1.0
    assert float(cycle.loc[7, "max_gap"]) == 2.0
    assert float(cycle.loc[7, "mean_gap"]) == 1.5


def test_published_rhythm_table_matches_a_draw_count_recomputation() -> None:
    rhythm = ROOT / "data" / "stats" / "advanced" / "loto_rhythm.csv"
    raw = ROOT / "data" / "xsmb.csv"
    if not (rhythm.exists() and raw.exists()):
        return

    widths = [("special", 5), ("prize1", 5), ("prize2_1", 5), ("prize2_2", 5)]
    widths += [(f"prize3_{i}", 5) for i in range(1, 7)]
    widths += [(f"prize4_{i}", 4) for i in range(1, 5)]
    widths += [(f"prize5_{i}", 4) for i in range(1, 7)]
    widths += [(f"prize6_{i}", 3) for i in range(1, 4)]
    widths += [(f"prize7_{i}", 2) for i in range(1, 5)]

    draws = pd.read_csv(raw, dtype=str).sort_values("date").reset_index(drop=True)
    per_draw = [
        {int(str(row[field]).strip().zfill(width)[-2:]) for field, width in widths}
        for _, row in draws.iterrows()
    ]
    total = len(per_draw)
    expected = {}
    for number in range(100):
        seen = [i for i, s in enumerate(per_draw) if number in s]
        if seen:
            expected[number] = total - seen[-1] - 1

    table = pd.read_csv(rhythm)
    table = table[table["mode"] == "loto"]
    mismatched = [
        (int(r["number"]), int(r["current_gap"]), expected[int(r["number"])])
        for _, r in table.iterrows()
        if int(r["number"]) in expected and int(r["current_gap"]) != expected[int(r["number"])]
    ]
    assert not mismatched, f"gan đã sinh lệch phép đếm theo kỳ: {mismatched[:5]}"


def test_the_two_recency_weightings_use_different_units_on_purpose() -> None:

    from ensemble.learn_ensemble_weights import _day_weights
    from forecast.meta_predictor import _recency_row_weights

    days = ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-23"]

    by_draw = _day_weights(days, 2)
    assert by_draw[-1] / by_draw[-2] == pytest.approx(2 ** (1 / 2), rel=1e-9)

    by_calendar = _recency_row_weights(pd.Series(days), 2.0)
    assert by_calendar[-1] / by_calendar[-2] > 10.0


def test_shipped_rhythm_builder_also_counts_draws() -> None:
    from stats.statistical_matrices import _rhythm_from_sparse

    frame = _sparse(
        [
            ("2020-01-01", [7]),
            ("2020-01-02", [0]),
            ("2020-01-03", [0]),
            ("2020-01-23", [0]),
        ]
    )
    out = _rhythm_from_sparse(frame, mode="loto").set_index("number")

    assert int(out.loc[7, "current_gap"]) == 3

    assert out.loc[0, "last_10_intervals"] == "1|1"
    assert int(out.loc[0, "max_gap"]) == 1

    assert float(out.loc[0, "rhythm_pressure"]) == pytest.approx(0.0)
