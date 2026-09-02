from __future__ import annotations

"""Canonical frequency statistics with explicit temporal and count semantics."""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from calendar_alignment import normalize_dates
from number_reference import dan_cham, dan_dau, dan_duoi, dan_tong_mod10

GroupKind = Literal["head", "tail", "total_mod10", "cham"]
NUMBER_COLUMNS = tuple(range(100))


@dataclass(frozen=True)
class FrequencyConfig:
    lookback_days: int | None = None
    lookback_draws: int | None = None

    def __post_init__(self) -> None:
        if self.lookback_days is not None and self.lookback_days < 1:
            raise ValueError("lookback_days must be >= 1")
        if self.lookback_draws is not None and self.lookback_draws < 1:
            raise ValueError("lookback_draws must be >= 1")
        if self.lookback_days is not None and self.lookback_draws is not None:
            raise ValueError("choose lookback_days or lookback_draws, not both")


def prepare_sparse_history(history: pd.DataFrame) -> pd.DataFrame:
    """Normalize a date + 00..99 occurrence-count table.

    Values are non-negative integer occurrence counts.  A value greater than
    zero means that the number appeared in that draw; a value of two or more
    preserves nháy multiplicity.
    """
    if "date" not in history.columns:
        raise ValueError("history must contain a date column")
    work = history.copy()
    work["date"] = pd.to_datetime(work["date"], errors="raise").dt.normalize()
    work = work.sort_values("date").reset_index(drop=True)
    normalize_dates(work["date"])

    rename: dict[object, int] = {}
    seen: set[int] = set()
    for column in work.columns:
        if column == "date":
            continue
        try:
            number = int(column)
        except (TypeError, ValueError):
            continue
        if 0 <= number <= 99:
            if number in seen:
                raise ValueError(f"duplicate number column after normalization: {number:02d}")
            rename[column] = number
            seen.add(number)
    work = work.rename(columns=rename)
    missing = [number for number in NUMBER_COLUMNS if number not in work.columns]
    if missing:
        raise ValueError(f"history missing number columns: {missing[:10]}")
    work = work.loc[:, ["date", *NUMBER_COLUMNS]].copy()
    numeric = work.loc[:, list(NUMBER_COLUMNS)].apply(pd.to_numeric, errors="raise")
    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values).all() or bool((values < 0).any()):
        raise ValueError("occurrence counts must be finite and non-negative")
    if not np.equal(values, np.floor(values)).all():
        raise ValueError("occurrence counts must be integers")
    work.loc[:, list(NUMBER_COLUMNS)] = numeric.astype(np.int16)
    return work


def history_before(
    history: pd.DataFrame,
    as_of_date: object,
    *,
    config: FrequencyConfig | None = None,
) -> pd.DataFrame:
    """Return only information observable strictly before ``as_of_date``."""
    cfg = config or FrequencyConfig()
    data = prepare_sparse_history(history)
    cutoff = pd.Timestamp(as_of_date).normalize()
    if pd.isna(cutoff):
        raise ValueError("as_of_date must be valid")
    data = data[data["date"] < cutoff]
    if cfg.lookback_days is not None:
        data = data[data["date"] >= cutoff - pd.Timedelta(days=cfg.lookback_days)]
    elif cfg.lookback_draws is not None:
        data = data.tail(cfg.lookback_draws)
    return data.reset_index(drop=True)


def compute_frequency_stats(
    history: pd.DataFrame,
    as_of_date: object,
    *,
    lookback_days: int | None = None,
    lookback_draws: int | None = None,
) -> pd.DataFrame:
    """Compute occurrence and draw-level frequency separately for 00..99."""
    window = history_before(
        history,
        as_of_date,
        config=FrequencyConfig(
            lookback_days=lookback_days,
            lookback_draws=lookback_draws,
        ),
    )
    matrix = window.loc[:, list(NUMBER_COLUMNS)].to_numpy(dtype=np.int32, copy=False)
    eligible_draws = len(window)
    if eligible_draws:
        occurrence_count = matrix.sum(axis=0, dtype=np.int64)
        draw_count = (matrix > 0).sum(axis=0, dtype=np.int64)
        max_occurrences = matrix.max(axis=0)
        exact_two = (matrix == 2).sum(axis=0, dtype=np.int64)
        at_least_two = (matrix >= 2).sum(axis=0, dtype=np.int64)
    else:
        occurrence_count = draw_count = max_occurrences = np.zeros(100, dtype=np.int64)
        exact_two = at_least_two = np.zeros(100, dtype=np.int64)

    cutoff = pd.Timestamp(as_of_date).normalize()
    return pd.DataFrame(
        {
            "number": np.arange(100, dtype=np.int16),
            "number_str": [f"{number:02d}" for number in range(100)],
            "as_of_date": cutoff.date().isoformat(),
            "window_start": (window["date"].iloc[0].date().isoformat() if eligible_draws else None),
            "window_end": (window["date"].iloc[-1].date().isoformat() if eligible_draws else None),
            "eligible_draws": eligible_draws,
            "occurrence_count": occurrence_count,
            "draw_count": draw_count,
            "hit_rate_by_draw": draw_count / max(eligible_draws, 1),
            "max_occurrences_per_draw": max_occurrences,
            "exactly_two_draws": exact_two,
            "at_least_two_draws": at_least_two,
        }
    )


def _group_members(kind: GroupKind, value: int) -> tuple[int, ...]:
    if not 0 <= value <= 9:
        raise ValueError("group value must be 0..9")
    if kind == "head":
        members = dan_dau(value)
    elif kind == "tail":
        members = dan_duoi(value)
    elif kind == "total_mod10":
        members = dan_tong_mod10(value)
    elif kind == "cham":
        members = dan_cham(value)
    else:
        raise ValueError(f"unknown group kind: {kind}")
    return tuple(int(member) for member in members)


def compute_group_frequency_stats(
    history: pd.DataFrame,
    as_of_date: object,
    *,
    group: GroupKind,
    lookback_days: int | None = None,
    lookback_draws: int | None = None,
) -> pd.DataFrame:
    """Compute occurrence and any-member draw counts for canonical digit groups."""
    window = history_before(
        history,
        as_of_date,
        config=FrequencyConfig(
            lookback_days=lookback_days,
            lookback_draws=lookback_draws,
        ),
    )
    eligible = len(window)
    rows: list[dict[str, object]] = []
    for value in range(10):
        members = _group_members(group, value)
        matrix = window.loc[:, list(members)].to_numpy(dtype=np.int32, copy=False)
        occurrence_count = int(matrix.sum()) if eligible else 0
        draw_count = int((matrix > 0).any(axis=1).sum()) if eligible else 0
        rows.append(
            {
                "group": group,
                "value": value,
                "members": tuple(f"{member:02d}" for member in members),
                "eligible_draws": eligible,
                "occurrence_count": occurrence_count,
                "draw_count": draw_count,
                "hit_rate_by_draw": draw_count / max(eligible, 1),
            }
        )
    return pd.DataFrame(rows)
