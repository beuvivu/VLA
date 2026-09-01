from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from conditional_matrices import build_conditional_tables


def _frames(dates: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "special": [10000 + i for i in range(len(dates))],
        }
    )
    sparse = pd.DataFrame(0, index=np.arange(len(dates)), columns=["date", *range(100)])
    sparse["date"] = pd.to_datetime(dates)
    for i in range(len(dates)):
        sparse.loc[i, (10 + i) % 100] = 1
    return raw, sparse


def test_gap_is_not_counted_as_next_day_transition() -> None:
    raw, sparse = _frames(["2026-08-01", "2026-08-02", "2026-08-04"])
    de_loto, de_de, loto_loto, diag = build_conditional_tables(raw, sparse, top=500)

    assert diag["exact_next_day_pairs"] == 1
    assert diag["skipped_nonconsecutive_boundaries"] == 1

    # Only 00 on Aug-01 may condition Aug-02. 01 on Aug-02 must not condition
    # Aug-04 because that boundary is two calendar days.
    assert set(de_de["prev_special_2d"].tolist()) == {"00"}
    assert set(de_de["next_special_2d"].tolist()) == {"01"}
    assert set(de_loto["prev_special_2d"].tolist()) == {"00"}
    assert set(loto_loto["prev_loto"].tolist()) == {"10"}


def test_contiguous_history_counts_every_boundary() -> None:
    raw, sparse = _frames(["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"])
    _, de_de, _, diag = build_conditional_tables(raw, sparse, top=500)
    assert diag["exact_next_day_pairs"] == 3
    assert diag["skipped_nonconsecutive_boundaries"] == 0
    assert len(de_de) == 3


def test_raw_sparse_date_axes_must_match() -> None:
    raw, sparse = _frames(["2026-08-01", "2026-08-02", "2026-08-03"])
    sparse.loc[2, "date"] = pd.Timestamp("2026-08-04")
    with pytest.raises(ValueError, match="same ordered date axis"):
        build_conditional_tables(raw, sparse)


def test_duplicate_dates_are_rejected() -> None:
    raw, sparse = _frames(["2026-08-01", "2026-08-02", "2026-08-03"])
    raw.loc[2, "date"] = pd.Timestamp("2026-08-02")
    with pytest.raises(ValueError, match="duplicates"):
        build_conditional_tables(raw, sparse)
