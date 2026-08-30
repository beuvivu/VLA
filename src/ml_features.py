from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from lottery import Lottery

Mode = Literal["loto", "de"]


@dataclass(frozen=True)
class FeatureParams:
    # Rolling windows for frequencies (days)
    w1: int = 7
    w2: int = 30
    w3: int = 90
    w4: int = 365
    lag_max_for_path_support: int = 30


def _ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _build_hit_matrices(df_2d: pd.DataFrame) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """
    Return:
      dates (DatetimeIndex)
      hit_loto: shape (n_days, 100) boolean, True if number appears in day
      hit_de:   shape (n_days, 100) boolean, True if special%100 == number
    """
    df_2d = _ensure_datetime(df_2d)
    dates = pd.DatetimeIndex(df_2d["date"])
    cols = [c for c in df_2d.columns if c != "date"]

    vals = df_2d[cols].to_numpy(dtype=np.int16, copy=False)  # (n, draws)
    hit_loto = np.zeros((len(df_2d), 100), dtype=bool)
    for i in range(vals.shape[0]):
        hit_loto[i, np.unique(vals[i])] = True

    de = (df_2d["special"].to_numpy(dtype=np.int16) % 100).astype(np.int16)
    hit_de = np.zeros((len(df_2d), 100), dtype=bool)
    hit_de[np.arange(len(df_2d)), de] = True

    return dates, hit_loto, hit_de


def _rolling_sum_bool(hit: np.ndarray, window: int) -> np.ndarray:
    """
    hit: (n,100) bool
    returns rolling sum over previous 'window' days ending at current day (inclusive).
    """
    x = hit.astype(np.int16)
    c = np.cumsum(x, axis=0)
    out = c.copy()
    if window < len(x):
        out[window:] = c[window:] - c[:-window]
    return out


def _compute_gap(hit: np.ndarray) -> np.ndarray:
    """
    gap[t, x] = number of days since last hit up to day t (0 if hit today, 1 if hit yesterday, ...)
    """
    n, m = hit.shape
    last = np.full(m, -10_000, dtype=np.int32)
    gap = np.zeros((n, m), dtype=np.int16)
    for t in range(n):
        gap[t] = (t - last).astype(np.int16)
        gap[t][hit[t]] = 0
        last[hit[t]] = t
    return gap

def _ewm_rate(hit: np.ndarray, half_life_days: float) -> np.ndarray:
    """Exponentially weighted historical hit rate through each anchor day."""
    alpha = 1.0 - float(np.exp(np.log(0.5) / max(float(half_life_days), 1.0)))
    out = np.zeros(hit.shape, dtype=np.float32)
    state = np.zeros(hit.shape[1], dtype=np.float64)
    for t in range(len(hit)):
        state = (1.0 - alpha) * state + alpha * hit[t].astype(np.float64)
        out[t] = state
    return out


def _hit_streak(hit: np.ndarray) -> np.ndarray:
    """Consecutive-hit streak through each day for every 00..99 number."""
    out = np.zeros(hit.shape, dtype=np.int16)
    state = np.zeros(hit.shape[1], dtype=np.int16)
    for t in range(len(hit)):
        state = np.where(hit[t], state + 1, 0).astype(np.int16)
        out[t] = state
    return out


def _target_weekday_rate(
    dates: pd.DatetimeIndex, hit: np.ndarray, prior_strength: float = 28.0
) -> np.ndarray:
    """Empirical-Bayes rate for the weekday of t+1, using observations <= t."""
    n, m = hit.shape
    out = np.zeros((n, m), dtype=np.float32)
    successes = np.zeros((7, m), dtype=np.float64)
    trials = np.zeros(7, dtype=np.float64)
    global_success = np.zeros(m, dtype=np.float64)
    global_trials = 0.0
    for t in range(n):
        observed_wd = int(dates[t].weekday())
        successes[observed_wd] += hit[t]
        trials[observed_wd] += 1.0
        global_success += hit[t]
        global_trials += 1.0

        target_wd = int((dates[t] + pd.Timedelta(days=1)).weekday())
        baseline = global_success / max(global_trials, 1.0)
        denom = trials[target_wd] + prior_strength
        out[t] = ((successes[target_wd] + prior_strength * baseline) / denom).astype(np.float32)
    return out


def _reverse_indices() -> np.ndarray:
    return np.array([10 * (x % 10) + (x // 10) for x in range(100)], dtype=np.int16)


def _target_weekday_components(
    dates: pd.DatetimeIndex,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    target = np.array(
        [(d + pd.Timedelta(days=1)).weekday() for d in dates], dtype=np.int16
    )
    angle = 2.0 * np.pi * target.astype(np.float64) / 7.0
    return target, np.sin(angle).astype(np.float32), np.cos(angle).astype(np.float32)



# --- PATH-support feature (rawdata -> numbers) ---
FIELD_WIDTHS = [
    ("special", 5),
    ("prize1", 5),
    ("prize2_1", 5), ("prize2_2", 5),
    ("prize3_1", 5), ("prize3_2", 5), ("prize3_3", 5),
    ("prize3_4", 5), ("prize3_5", 5), ("prize3_6", 5),
    ("prize4_1", 4), ("prize4_2", 4), ("prize4_3", 4), ("prize4_4", 4),
    ("prize5_1", 4), ("prize5_2", 4), ("prize5_3", 4),
    ("prize5_4", 4), ("prize5_5", 4), ("prize5_6", 4),
    ("prize6_1", 3), ("prize6_2", 3), ("prize6_3", 3),
    ("prize7_1", 2), ("prize7_2", 2), ("prize7_3", 2), ("prize7_4", 2),
]


def _raw_digits_from_row(row: pd.Series) -> np.ndarray:
    parts = []
    for f, w in FIELD_WIDTHS:
        parts.append(str(int(row[f])).zfill(w))
    s = "".join(parts)
    return np.fromiter((ord(ch) - 48 for ch in s), dtype=np.uint8)


def _pairs_indices(P: int) -> tuple[np.ndarray, np.ndarray]:
    I, J = np.triu_indices(P, k=1)
    return I.astype(np.int16), J.astype(np.int16)


def _pair_histogram_by_day(raw_digits: list[np.ndarray], I: np.ndarray, J: np.ndarray) -> np.ndarray:
    """Return per-day counts for every two-digit value generated by position pairs.

    The original implementation rebuilt the same pair combinations once for every
    lag and every feature day.  Computing each day's 100-bin histogram once makes
    the ML feature build roughly O(days * pairs) instead of
    O(days * lag_max * pairs), which is important on GitHub-hosted runners.
    """
    hist = np.zeros((len(raw_digits), 100), dtype=np.int32)
    for t, d in enumerate(raw_digits):
        nums = (10 * d[I] + d[J]).astype(np.int16, copy=False)
        hist[t] = np.bincount(nums, minlength=100)
    return hist


def _path_support_matrix(
    raw_digits: list[np.ndarray], lag_max: int, I: np.ndarray, J: np.ndarray
) -> np.ndarray:
    """Path-support features for all days using only *prior* draw days."""
    daily = _pair_histogram_by_day(raw_digits, I, J)
    if len(daily) == 0:
        return daily

    # prefix[k] is the sum of daily[0:k].  Feature row t predicts t+1, so
    # draw t is already known and is valid evidence.  Include the anchor draw
    # and up to lag_max-1 prior draws; only t+1 must remain unseen.
    prefix = np.vstack([np.zeros((1, 100), dtype=np.int64), np.cumsum(daily, axis=0, dtype=np.int64)])
    out = np.zeros_like(daily, dtype=np.int32)
    for t in range(len(daily)):
        start = max(0, t - lag_max + 1)
        out[t] = (prefix[t + 1] - prefix[start]).astype(np.int32, copy=False)
    return out


def _path_support_for_day(raw_digits: list[np.ndarray], t: int, lag_max: int, I: np.ndarray, J: np.ndarray) -> np.ndarray:
    """Compatibility helper for one feature day; uses only preceding days."""
    if t < 0:
        return np.zeros(100, dtype=np.int32)
    start = max(0, t - lag_max + 1)
    hist = _pair_histogram_by_day(raw_digits[start : t + 1], I, J)
    return hist.sum(axis=0, dtype=np.int64).astype(np.int32, copy=False)


def build_ml_table(mode: Mode, params: FeatureParams) -> tuple[pd.DataFrame, pd.Series]:
    """
    Build dataset:
      X rows = (day t, number x) -> predict hit at day t+1
      y = hit(t+1, x)
    """
    lot = Lottery()
    lot.load()
    df_raw = _ensure_datetime(lot.get_raw_data())
    df_2d = _ensure_datetime(lot.get_2_digits_data())
    if df_raw.empty or df_2d.empty:
        raise RuntimeError("No data loaded. Run src/sync.py first.")

    dates, hit_loto, hit_de = _build_hit_matrices(df_2d)
    hit = hit_loto if mode == "loto" else hit_de

    freq7 = _rolling_sum_bool(hit, params.w1)
    freq30 = _rolling_sum_bool(hit, params.w2)
    freq90 = _rolling_sum_bool(hit, params.w3)
    freq365 = _rolling_sum_bool(hit, min(params.w4, len(hit)))
    ewm14 = _ewm_rate(hit, 14.0)
    ewm45 = _ewm_rate(hit, 45.0)
    gap = _compute_gap(hit)
    streak = _hit_streak(hit)
    hit_yday = np.vstack([np.zeros((1, 100), dtype=bool), hit[:-1]])
    hit_today = hit.astype(np.int16)
    weekday_rate = _target_weekday_rate(dates, hit)
    target_weekday, target_weekday_sin, target_weekday_cos = _target_weekday_components(dates)
    reverse_idx = _reverse_indices()

    raw_digits = [_raw_digits_from_row(r) for _, r in df_raw.iterrows()]
    P = raw_digits[0].shape[0]
    I, J = _pairs_indices(P)

    path_sup = _path_support_matrix(raw_digits, params.lag_max_for_path_support, I, J)

    n = len(dates)
    xs = np.tile(np.arange(100, dtype=np.int16), n - 1)
    X = pd.DataFrame(
        {
            "date": np.repeat(dates[: n - 1].to_pydatetime(), 100),
            "number": xs,
            "target_weekday": np.repeat(target_weekday[: n - 1], 100),
            "target_weekday_sin": np.repeat(target_weekday_sin[: n - 1], 100),
            "target_weekday_cos": np.repeat(target_weekday_cos[: n - 1], 100),
            "freq7": freq7[: n - 1].reshape(-1),
            "freq30": freq30[: n - 1].reshape(-1),
            "freq90": freq90[: n - 1].reshape(-1),
            "freq365": freq365[: n - 1].reshape(-1),
            "ewm14": ewm14[: n - 1].reshape(-1),
            "ewm45": ewm45[: n - 1].reshape(-1),
            "trend_7_30": (freq7[: n - 1] / 7.0 - freq30[: n - 1] / 30.0).reshape(-1),
            "trend_30_90": (freq30[: n - 1] / 30.0 - freq90[: n - 1] / 90.0).reshape(-1),
            "gap": gap[: n - 1].reshape(-1),
            "log_gap": np.log1p(gap[: n - 1].astype(np.float32)).reshape(-1),
            "streak": streak[: n - 1].reshape(-1),
            "hit_today": hit_today[: n - 1].reshape(-1),
            "hit_yesterday": hit_yday[: n - 1].reshape(-1).astype(np.int16),
            "weekday_rate": weekday_rate[: n - 1].reshape(-1),
            "reverse_freq30": freq30[: n - 1][:, reverse_idx].reshape(-1),
            "reverse_gap": gap[: n - 1][:, reverse_idx].reshape(-1),
            "reverse_hit_today": hit_today[: n - 1][:, reverse_idx].reshape(-1),
            "is_double": np.tile((np.arange(100) // 10 == np.arange(100) % 10).astype(np.int16), n - 1),
            "digit_sum_mod10": np.tile(((np.arange(100) // 10 + np.arange(100) % 10) % 10).astype(np.int16), n - 1),
            "path_support": path_sup[: n - 1].reshape(-1),
        }
    )

    y = pd.Series(hit[1:].reshape(-1).astype(np.int16), name="y_nextday_hit")

    # The target is explicitly the next calendar draw. Historical gaps must not
    # silently turn a t -> t+k pair into a one-day training example.
    consecutive = np.asarray((dates[1:] - dates[:-1]).days == 1, dtype=bool)
    row_mask = np.repeat(consecutive, 100)
    if not bool(np.all(row_mask)):
        X = X.loc[row_mask].reset_index(drop=True)
        y = y.loc[row_mask].reset_index(drop=True)
    X.attrs["source_through_date"] = str(dates[-1].date())
    return X, y


def build_features_for_prediction(mode: Mode, params: FeatureParams) -> tuple[pd.Timestamp, pd.DataFrame]:
    """
    Build features for the last available day (t = last_date), to predict t+1.
    Returns (last_date, X_pred with 100 rows)
    """
    lot = Lottery()
    lot.load()
    df_raw = _ensure_datetime(lot.get_raw_data())
    df_2d = _ensure_datetime(lot.get_2_digits_data())

    dates, hit_loto, hit_de = _build_hit_matrices(df_2d)
    hit = hit_loto if mode == "loto" else hit_de

    freq7 = _rolling_sum_bool(hit, params.w1)
    freq30 = _rolling_sum_bool(hit, params.w2)
    freq90 = _rolling_sum_bool(hit, params.w3)
    freq365 = _rolling_sum_bool(hit, min(params.w4, len(hit)))
    ewm14 = _ewm_rate(hit, 14.0)
    ewm45 = _ewm_rate(hit, 45.0)
    gap = _compute_gap(hit)
    streak = _hit_streak(hit)
    hit_yday = np.vstack([np.zeros((1, 100), dtype=bool), hit[:-1]])
    hit_today = hit.astype(np.int16)
    weekday_rate = _target_weekday_rate(dates, hit)
    target_weekday, target_weekday_sin, target_weekday_cos = _target_weekday_components(dates)
    reverse_idx = _reverse_indices()

    raw_digits = [_raw_digits_from_row(r) for _, r in df_raw.iterrows()]
    P = raw_digits[0].shape[0]
    I, J = _pairs_indices(P)

    t = len(dates) - 1
    path_sup_t = _path_support_for_day(raw_digits, t, params.lag_max_for_path_support, I, J)

    X_pred = pd.DataFrame(
        {
            "date": [dates[t].to_pydatetime()] * 100,
            "number": np.arange(100, dtype=np.int16),
            "target_weekday": [int(target_weekday[t])] * 100,
            "target_weekday_sin": [float(target_weekday_sin[t])] * 100,
            "target_weekday_cos": [float(target_weekday_cos[t])] * 100,
            "freq7": freq7[t],
            "freq30": freq30[t],
            "freq90": freq90[t],
            "freq365": freq365[t],
            "ewm14": ewm14[t],
            "ewm45": ewm45[t],
            "trend_7_30": freq7[t] / 7.0 - freq30[t] / 30.0,
            "trend_30_90": freq30[t] / 30.0 - freq90[t] / 90.0,
            "gap": gap[t],
            "log_gap": np.log1p(gap[t].astype(np.float32)),
            "streak": streak[t],
            "hit_today": hit_today[t],
            "hit_yesterday": hit_yday[t].astype(np.int16),
            "weekday_rate": weekday_rate[t],
            "reverse_freq30": freq30[t][reverse_idx],
            "reverse_gap": gap[t][reverse_idx],
            "reverse_hit_today": hit_today[t][reverse_idx],
            "is_double": (np.arange(100) // 10 == np.arange(100) % 10).astype(np.int16),
            "digit_sum_mod10": ((np.arange(100) // 10 + np.arange(100) % 10) % 10).astype(np.int16),
            "path_support": path_sup_t,
        }
    )
    return dates[t], X_pred
