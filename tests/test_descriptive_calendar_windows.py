from __future__ import annotations

import pandas as pd

from descriptive_extensions import build_head_table


def test_head_table_uses_calendar_window_not_last_n_rows() -> None:
    # Four observations but only two fall inside the inclusive 3-calendar-day
    # window ending on Aug-10. A row-count implementation would incorrectly use 3.
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2026-08-01", "2026-08-07", "2026-08-09", "2026-08-10"]
            ),
            "special": [1, 2, 3, 4],
            "prize1": [11, 12, 13, 14],
        }
    )
    out = build_head_table(df, lookback_days=3)
    assert out["draw_rows"].nunique() == 1
    assert int(out["draw_rows"].iloc[0]) == 2
    assert out["window_start"].iloc[0] == "2026-08-08"
    assert out["window_end"].iloc[0] == "2026-08-10"
    # Two prize positions across two included draws -> four total observations.
    assert int(out["count"].sum()) == 4
