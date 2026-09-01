from __future__ import annotations

from datetime import date

import pandas as pd

from cycle_stats import _gap_series_calendar
from hazard_stats import _calendar_ordinals


def test_cycle_gap_counts_missing_calendar_dates_as_elapsed_time():
    all_dates = [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 5)]
    hit_dates = [date(2026, 1, 1), date(2026, 1, 2)]
    current, maximum, mean_gap, median_gap = _gap_series_calendar(hit_dates, all_dates)
    assert current == 3
    assert maximum == 3
    assert mean_gap == 0.0
    assert median_gap == 0.0


def test_cycle_between_hit_absence_uses_calendar_difference_minus_one():
    all_dates = [date(2026, 1, 1), date(2026, 1, 4), date(2026, 1, 5)]
    hit_dates = [date(2026, 1, 1), date(2026, 1, 4)]
    current, maximum, mean_gap, _ = _gap_series_calendar(hit_dates, all_dates)
    assert current == 1
    assert maximum == 2
    assert mean_gap == 1.0  # mean of leading=0 and completed absence=2


def test_hazard_calendar_ordinals_do_not_collapse_missing_dates():
    df = pd.DataFrame({"date": ["2026-01-01", "2026-01-02", "2026-01-05"]})
    assert _calendar_ordinals(df).tolist() == [0, 1, 4]
