from __future__ import annotations

"""Exact calendar alignment primitives for time-dependent analytics.

Row adjacency is not a time interval.  Every algorithm that claims a one-day or
N-day lag must either use these index pairs or explicitly require a contiguous
daily series.  This prevents a missing canonical date from silently turning a
2-day jump into a "next-day" transition.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd


def normalize_dates(dates: Sequence[object] | pd.Series | pd.Index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(dates)).normalize()
    if idx.hasnans:
        raise ValueError("dates contain null/invalid values")
    if idx.has_duplicates:
        duplicates = idx[idx.duplicated()].strftime("%Y-%m-%d").tolist()
        raise ValueError(f"dates contain duplicates: {duplicates[:5]}")
    if not idx.is_monotonic_increasing:
        raise ValueError("dates must be sorted in strictly increasing order")
    return idx


def calendar_lag_pairs(
    dates: Sequence[object] | pd.Series | pd.Index, lag_days: int
) -> tuple[np.ndarray, np.ndarray]:
    """Return source/target indices separated by exactly ``lag_days`` calendar days."""
    if lag_days <= 0:
        raise ValueError("lag_days must be >= 1")
    idx = normalize_dates(dates)
    if len(idx) == 0:
        empty = np.array([], dtype=np.int32)
        return empty, empty.copy()

    by_date = {d: i for i, d in enumerate(idx)}
    source: list[int] = []
    target: list[int] = []
    delta = pd.Timedelta(days=int(lag_days))
    for i, d in enumerate(idx):
        j = by_date.get(d + delta)
        if j is not None:
            source.append(i)
            target.append(int(j))
    return np.asarray(source, dtype=np.int32), np.asarray(target, dtype=np.int32)


def consecutive_next_pairs(
    dates: Sequence[object] | pd.Series | pd.Index,
) -> tuple[np.ndarray, np.ndarray]:
    return calendar_lag_pairs(dates, 1)


def missing_calendar_dates(
    dates: Sequence[object] | pd.Series | pd.Index,
) -> list[str]:
    idx = normalize_dates(dates)
    if len(idx) < 2:
        return []
    expected = pd.date_range(idx[0], idx[-1], freq="D")
    missing = expected.difference(idx)
    return missing.strftime("%Y-%m-%d").tolist()


def require_daily_contiguous(
    dates: Sequence[object] | pd.Series | pd.Index, *, context: str = "time series"
) -> pd.DatetimeIndex:
    idx = normalize_dates(dates)
    missing = missing_calendar_dates(idx)
    if missing:
        raise ValueError(
            f"{context} requires contiguous calendar days; missing {len(missing)} date(s): "
            + ", ".join(missing[:10])
        )
    return idx
