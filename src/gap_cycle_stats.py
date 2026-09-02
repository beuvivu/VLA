from __future__ import annotations

"""Canonical lô-gan and recurrence statistics with explicit units."""

import numpy as np
import pandas as pd

from frequency_stats import (
    FrequencyConfig,
    GroupKind,
    NUMBER_COLUMNS,
    _group_members,
    history_before,
)


def _safe_stat(values: np.ndarray, reducer: str) -> float:
    if values.size == 0:
        return float("nan")
    return float(getattr(np, reducer)(values))


def _trend(values: np.ndarray, recent_intervals: int) -> float:
    recent = values[-max(2, int(recent_intervals)) :]
    if recent.size < 2:
        return float("nan")
    return float(np.polyfit(np.arange(len(recent), dtype=float), recent, 1)[0])


def _gap_row(
    number: int,
    hit: np.ndarray,
    dates: pd.DatetimeIndex,
    cutoff: pd.Timestamp,
    *,
    recent_intervals: int,
) -> dict[str, object]:
    indices = np.flatnonzero(hit)
    eligible = len(hit)
    if indices.size:
        last_index = int(indices[-1])
        last_seen = pd.Timestamp(dates[last_index])
        current_draws = eligible - last_index - 1
        current_calendar = max(0, int((cutoff - last_seen).days) - 1)
    else:
        last_seen = None
        current_draws = eligible
        current_calendar = max(0, int((cutoff - dates[0]).days)) if eligible else 0

    interval_draws = np.diff(indices).astype(float)
    absence_draws = np.maximum(interval_draws - 1.0, 0.0)
    hit_dates = dates[indices] if indices.size else pd.DatetimeIndex([])
    interval_calendar = (
        np.diff(hit_dates.to_numpy(dtype="datetime64[D]")).astype("timedelta64[D]").astype(float)
        if len(hit_dates) >= 2
        else np.array([], dtype=float)
    )
    if absence_draws.size:
        gap_percentile = float(np.mean(absence_draws <= current_draws))
        mean_gap = float(np.mean(absence_draws))
        std_gap = float(np.std(absence_draws, ddof=1)) if absence_draws.size >= 2 else 0.0
        gap_zscore = float((current_draws - mean_gap) / std_gap) if std_gap > 0.0 else float("nan")
    else:
        gap_percentile = mean_gap = gap_zscore = float("nan")

    return {
        "number": int(number),
        "number_str": f"{int(number):02d}",
        "as_of_date": cutoff.date().isoformat(),
        "eligible_draws": eligible,
        "hit_draws": int(indices.size),
        "last_seen_date": last_seen.date().isoformat() if last_seen is not None else None,
        "current_gap_draws": int(current_draws),
        "current_gap_calendar_days": int(current_calendar),
        "historical_max_gap_draws": _safe_stat(absence_draws, "max"),
        "mean_gap_draws": mean_gap,
        "median_gap_draws": _safe_stat(absence_draws, "median"),
        "gap_percentile": gap_percentile,
        "gap_zscore": gap_zscore,
        "mean_interval_draws": _safe_stat(interval_draws, "mean"),
        "median_interval_draws": _safe_stat(interval_draws, "median"),
        "variance_interval_draws": (
            float(np.var(interval_draws, ddof=1)) if interval_draws.size >= 2 else float("nan")
        ),
        "interval_q25_draws": (
            float(np.quantile(interval_draws, 0.25)) if interval_draws.size else float("nan")
        ),
        "interval_q75_draws": (
            float(np.quantile(interval_draws, 0.75)) if interval_draws.size else float("nan")
        ),
        "maximum_interval_draws": _safe_stat(interval_draws, "max"),
        "minimum_interval_calendar_days": _safe_stat(interval_calendar, "min"),
        "maximum_interval_calendar_days": _safe_stat(interval_calendar, "max"),
        "mean_interval_calendar_days": _safe_stat(interval_calendar, "mean"),
        "recent_interval_trend": _trend(interval_draws, recent_intervals),
        "current_censoring_interval_draws": int(current_draws),
    }


def compute_gap_stats(
    history: pd.DataFrame,
    as_of_date: object,
    *,
    lookback_days: int | None = None,
    lookback_draws: int | None = None,
    recent_intervals: int = 5,
) -> pd.DataFrame:
    """Compute current gaps and completed recurrence summaries for 00..99.

    ``current_gap_draws`` counts completed draws after the most recent hit and
    strictly before the target date.  Long gaps are descriptive and are not
    interpreted here as increased future probability.
    """
    if recent_intervals < 2:
        raise ValueError("recent_intervals must be >= 2")
    window = history_before(
        history,
        as_of_date,
        config=FrequencyConfig(
            lookback_days=lookback_days,
            lookback_draws=lookback_draws,
        ),
    )
    dates = pd.DatetimeIndex(window["date"])
    cutoff = pd.Timestamp(as_of_date).normalize()
    matrix = window.loc[:, list(NUMBER_COLUMNS)].to_numpy(dtype=int, copy=False) > 0
    return pd.DataFrame(
        [
            _gap_row(
                number,
                matrix[:, number],
                dates,
                cutoff,
                recent_intervals=recent_intervals,
            )
            for number in NUMBER_COLUMNS
        ]
    )


def compute_recurrence_intervals(
    history: pd.DataFrame,
    number: int,
    as_of_date: object,
    *,
    lookback_days: int | None = None,
    lookback_draws: int | None = None,
) -> pd.DataFrame:
    """Return each completed hit-to-hit interval for one number."""
    if not 0 <= int(number) <= 99:
        raise ValueError("number must be in 00..99")
    window = history_before(
        history,
        as_of_date,
        config=FrequencyConfig(
            lookback_days=lookback_days,
            lookback_draws=lookback_draws,
        ),
    )
    indices = np.flatnonzero(window[int(number)].to_numpy(dtype=int) > 0)
    rows: list[dict[str, object]] = []
    for previous, current in zip(indices[:-1], indices[1:], strict=True):
        previous_date = pd.Timestamp(window.loc[int(previous), "date"])
        current_date = pd.Timestamp(window.loc[int(current), "date"])
        interval_draws = int(current - previous)
        rows.append(
            {
                "number": int(number),
                "previous_date": previous_date.date().isoformat(),
                "current_date": current_date.date().isoformat(),
                "interval_draws": interval_draws,
                "absent_draws": max(0, interval_draws - 1),
                "interval_calendar_days": int((current_date - previous_date).days),
            }
        )
    return pd.DataFrame(rows)


def compute_group_gap_stats(
    history: pd.DataFrame,
    as_of_date: object,
    *,
    group: GroupKind,
    lookback_days: int | None = None,
    lookback_draws: int | None = None,
) -> pd.DataFrame:
    """Compute draw gaps for head, tail, total-mod-10, or chạm groups."""
    window = history_before(
        history,
        as_of_date,
        config=FrequencyConfig(
            lookback_days=lookback_days,
            lookback_draws=lookback_draws,
        ),
    )
    dates = pd.DatetimeIndex(window["date"])
    cutoff = pd.Timestamp(as_of_date).normalize()
    rows: list[dict[str, object]] = []
    for value in range(10):
        members = _group_members(group, value)
        hit = (window.loc[:, list(members)].to_numpy(dtype=int, copy=False) > 0).any(axis=1)
        row = _gap_row(
            value,
            hit,
            dates,
            cutoff,
            recent_intervals=5,
        )
        row["group"] = group
        row["value"] = row.pop("number")
        row.pop("number_str")
        rows.append(row)
    return pd.DataFrame(rows)
