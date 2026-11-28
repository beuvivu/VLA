from __future__ import annotations


import json
from collections.abc import Iterable, Sequence
from functools import lru_cache

import numpy as np
import pandas as pd

from core.paths import REPO_ROOT


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
    if lag_days <= 0:
        raise ValueError("lag_days must be >= 1")
    idx = normalize_dates(dates)
    if len(idx) == 0:
        empty = np.array([], dtype=np.int32)
        return empty, empty.copy()

    wanted = idx + pd.Timedelta(days=int(lag_days))
    position = idx.searchsorted(wanted)
    in_range = position < len(idx)
    probe = np.where(in_range, position, 0)
    matches = in_range & (idx.to_numpy()[probe] == wanted.to_numpy())
    return (
        np.flatnonzero(matches).astype(np.int32),
        position[matches].astype(np.int32),
    )


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


@lru_cache(maxsize=1)
def known_non_draw_days() -> frozenset[str]:
    path = REPO_ROOT / "data" / "non_draw_days.json"
    if not path.exists():
        return frozenset()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return frozenset(payload.get("ngay_khong_quay", ()))


def unexpected_gap_dates(
    dates: Sequence[object] | pd.Series | pd.Index,
    *,
    allow_missing: Iterable[str] | None = None,
) -> list[str]:
    allowed = (
        known_non_draw_days() if allow_missing is None else frozenset(allow_missing)
    )
    return [d for d in missing_calendar_dates(dates) if d not in allowed]


def require_daily_contiguous(
    dates: Sequence[object] | pd.Series | pd.Index,
    *,
    context: str = "time series",
    allow_missing: Iterable[str] | None = None,
) -> pd.DatetimeIndex:
    idx = normalize_dates(dates)
    missing = unexpected_gap_dates(idx, allow_missing=allow_missing)
    if missing:
        raise ValueError(
            f"{context} requires contiguous calendar days; missing {len(missing)} date(s): "
            + ", ".join(missing[:10])
        )
    return idx
