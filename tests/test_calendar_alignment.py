from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from calendar_alignment import calendar_lag_pairs, consecutive_next_pairs, require_daily_contiguous
from markov_stats import compute_markov_for_loto


def _two_digit_frame(dates: list[str]) -> pd.DataFrame:
    rows = []
    for i, day in enumerate(dates):
        row = {"date": day, "special": i % 100}
        for j in range(1, 27):
            row[f"p{j}"] = (i + j) % 100
        rows.append(row)
    return pd.DataFrame(rows)


def test_calendar_pairs_skip_missing_day() -> None:
    dates = pd.to_datetime(["2026-08-01", "2026-08-02", "2026-08-04", "2026-08-05"])
    src, dst = consecutive_next_pairs(dates)
    assert list(zip(src.tolist(), dst.tolist())) == [(0, 1), (2, 3)]


def test_exact_multi_day_lag_is_date_based_not_row_based() -> None:
    dates = pd.to_datetime(["2026-08-01", "2026-08-03", "2026-08-04"])
    src, dst = calendar_lag_pairs(dates, 2)
    assert list(zip(src.tolist(), dst.tolist())) == [(0, 1)]


def test_contiguity_guard_reports_gap() -> None:
    with pytest.raises(ValueError, match="missing 1 date"):
        require_daily_contiguous(
            pd.to_datetime(["2026-08-01", "2026-08-03"]),
            context="unit-test",
        )


def test_markov_does_not_cross_calendar_gap() -> None:
    # With only two observations separated by two calendar days there is no
    # legitimate next-day transition to estimate.
    df = _two_digit_frame(["2026-08-01", "2026-08-03"])
    assert compute_markov_for_loto(df).empty
