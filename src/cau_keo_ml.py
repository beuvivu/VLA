from __future__ import annotations

"""Explainable AI/ML layer for Vietnamese lottery statistical "cầu kèo".

This module builds a leakage-aware training table where each row is:
(anchor day t, number 00..99) -> whether the number appears on t+1.

It combines modern ML with lottery-domain statistical signals:
- rolling frequency windows
- current gap/rhythm pressure
- same-weekday seasonality
- previous-special relations: same/reverse/chạm/tổng/bóng
- conditional transitions: ĐB hôm nay -> tomorrow target, loto hôm nay -> tomorrow target
- raw-result digit pair/path support
- lô rơi style support from numbers appearing in today's result

All row-based rolling, lag and next-day features are evaluated only after the raw
and two-digit histories are proven daily-contiguous and date-aligned. The output
is an explainable ranking signal, not a guarantee of future lottery outcomes.
"""

import argparse
import csv
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from numbers import Integral
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss

from calendar_alignment import require_daily_contiguous
from lottery import Lottery, RepoPaths
from ml_features import _pairs_indices, _path_support_matrix, _raw_digits_from_row
from ml_models import PlattCalibratedClassifier

Mode = Literal["loto", "de"]
NUMBER_COLS = list(range(100))

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CauKeoConfig:
    min_history_days: int = 60
    lag_max_for_path_support: int = 30
    window_days: int = 2000
    top: int = 20

    def __post_init__(self) -> None:
        for name in (
            "min_history_days",
            "lag_max_for_path_support",
            "window_days",
            "top",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or value < 1
            ):
                raise ValueError(f"{name} must be a positive integer")
        if self.top > 100:
            raise ValueError("top must be <= 100")


FEATURE_COLS = [
    "number_value",
    "tens",
    "ones",
    "digit_total",
    "weekday_next",
    "month_next",
    "freq_3d",
    "freq_7d",
    "freq_14d",
    "freq_30d",
    "freq_90d",
    "freq_365d",
    "gap",
    "gap_log",
    "hit_today",
    "hit_yesterday",
    "hit_2d_ago",
    "loto_occ_today",
    "loto_occ_7d",
    "same_weekday_freq_364",
    "month_to_date_freq",
    "year_to_date_freq",
    "path_support",
    "path_support_log",
    "reverse_hit_today",
    "reverse_freq_7d",
    "is_prev_special",
    "is_reverse_prev_special",
    "is_bong_prev_special",
    "share_head_prev_special",
    "share_tail_prev_special",
    "same_total_prev_special",
    "cham_overlap_prev_special",
    "cond_de_rate",
    "cond_loto_mean_rate",
    "cond_loto_max_rate",
    "head_freq_7d",
    "tail_freq_7d",
    "trend_7_vs_30",
]


def _fmt2(n: int | float | str) -> str:
    return f"{int(float(n)):02d}"


def _ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df.sort_values("date").reset_index(drop=True)


def _build_hit_matrices(
    two_digit_df: pd.DataFrame,
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray]:
    """Return dates, loto bool hits, de bool hits, and loto occurrence counts."""
    two = _ensure_datetime(two_digit_df)
    if two.empty:
        raise RuntimeError("No 2-digit data loaded. Run src/sync.py first.")

    dates = pd.DatetimeIndex(two["date"])
    value_cols = [c for c in two.columns if c != "date"]
    vals = (
        two[value_cols]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
        .astype(int)
        .to_numpy()
        % 100
    )

    loto_counts = np.zeros((len(two), 100), dtype=np.int16)
    for i in range(vals.shape[0]):
        loto_counts[i] = np.bincount(vals[i], minlength=100).astype(np.int16)

    loto_hit = loto_counts > 0

    de = (two["special"].astype(int).to_numpy() % 100).astype(np.int16)
    de_hit = np.zeros((len(two), 100), dtype=bool)
    de_hit[np.arange(len(two)), de] = True
    return dates, loto_hit, de_hit, loto_counts


def _rolling_sum_bool(hit: np.ndarray, window: int) -> np.ndarray:
    x = hit.astype(np.int16)
    c = np.cumsum(x, axis=0)
    out = c.copy()
    if window < len(x):
        out[window:] = c[window:] - c[:-window]
    return out


def _rolling_sum_int(values: np.ndarray, window: int) -> np.ndarray:
    x = values.astype(np.int32)
    c = np.cumsum(x, axis=0)
    out = c.copy()
    if window < len(x):
        out[window:] = c[window:] - c[:-window]
    return out


def _compute_gap(hit: np.ndarray) -> np.ndarray:
    n, m = hit.shape
    last = np.full(m, -10_000, dtype=np.int32)
    gap = np.zeros((n, m), dtype=np.int16)
    for t in range(n):
        gap[t] = (t - last).astype(np.int16)
        gap[t][hit[t]] = 0
        last[hit[t]] = t
    return gap


def _reverse_numbers() -> np.ndarray:
    nums = np.arange(100, dtype=np.int16)
    return ((nums % 10) * 10 + (nums // 10)).astype(np.int16)


def _bong_number(n: int) -> int:
    """Simple bóng +/-5 transform for both digits: ab -> (a+5)(b+5) modulo 10."""
    return (((n // 10 + 5) % 10) * 10) + ((n % 10 + 5) % 10)


def _minmax(values: pd.Series | np.ndarray) -> np.ndarray:
    arr = (
        pd.to_numeric(pd.Series(values), errors="coerce")
        .fillna(0.0)
        .astype(float)
        .to_numpy()
    )
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros_like(arr, dtype=float)
    lo = float(finite.min())
    hi = float(finite.max())
    if np.isclose(lo, hi):
        return np.zeros_like(arr, dtype=float)
    return np.clip((arr - lo) / (hi - lo), 0.0, 1.0)


def _score_band(score: float) -> str:
    if score >= 75:
        return "very_high"
    if score >= 55:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _downsample(
    X: np.ndarray, y: np.ndarray, neg_ratio: int, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    pos = np.where(y == 1)[0]
    neg = np.where(y == 0)[0]
    if len(pos) == 0 or len(neg) == 0:
        return X, y
    n_neg = min(len(neg), len(pos) * neg_ratio)
    sel_neg = rng.choice(neg, size=n_neg, replace=False)
    keep = np.concatenate([pos, sel_neg])
    rng.shuffle(keep)
    return X[keep], y[keep]


def _time_splits(
    unique_anchor_days: pd.DatetimeIndex,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    if len(unique_anchor_days) < 160:
        calib_start = unique_anchor_days[int(len(unique_anchor_days) * 0.70)]
        val_start = unique_anchor_days[int(len(unique_anchor_days) * 0.85)]
    else:
        calib_start = unique_anchor_days[-90]
        val_start = unique_anchor_days[-60]
    return calib_start, val_start


def _target_matrix(
    mode: Mode, loto_hit: np.ndarray, de_hit: np.ndarray
) -> np.ndarray:
    return loto_hit if mode == "loto" else de_hit


def _build_same_weekday_feature(
    hit: np.ndarray,
    dates: pd.DatetimeIndex,
    *,
    anchor_t: int,
    target_weekday: int,
    lookback_days: int = 364,
) -> np.ndarray:
    start = max(0, anchor_t - lookback_days + 1)
    if start > anchor_t:
        return np.zeros(100, dtype=np.int16)
    idx = [
        i
        for i in range(start, anchor_t + 1)
        if int(dates[i].weekday()) == target_weekday
    ]
    if not idx:
        return np.zeros(100, dtype=np.int16)
    return hit[idx].sum(axis=0).astype(np.int16)


def _build_month_year_to_date(
    hit: np.ndarray,
    dates: pd.DatetimeIndex,
    anchor_t: int,
    target_date: pd.Timestamp,
) -> tuple[np.ndarray, np.ndarray]:
    anchor_dates = dates[: anchor_t + 1]
    month_mask = (anchor_dates.year == target_date.year) & (
        anchor_dates.month == target_date.month
    )
    year_mask = anchor_dates.year == target_date.year
    month_freq = (
        hit[: anchor_t + 1][month_mask].sum(axis=0)
        if month_mask.any()
        else np.zeros(100)
    )
    year_freq = (
        hit[: anchor_t + 1][year_mask].sum(axis=0)
        if year_mask.any()
        else np.zeros(100)
    )
    return month_freq.astype(np.int16), year_freq.astype(np.int16)


def _conditional_loto_rates(
    counts: np.ndarray,
    trials: np.ndarray,
    today_hits: np.ndarray,
    *,
    alpha: float = 1.0,
    beta: float = 8.0,
) -> tuple[np.ndarray, np.ndarray]:
    prev_hits = np.where(today_hits > 0)[0]
    if prev_hits.size == 0:
        return np.zeros(100, dtype=float), np.zeros(100, dtype=float)

    denom = trials[prev_hits].astype(float)[:, None] + alpha + beta
    rates = (counts[prev_hits].astype(float) + alpha) / denom
    return rates.mean(axis=0), rates.max(axis=0)


def build_cau_keo_feature_frame(
    mode: Mode,
    *,
    include_target: bool,
    config: CauKeoConfig,
) -> tuple[pd.DataFrame, pd.Series | None]:
    """Build explainable calendar-safe cầu-kèo features."""
    lot = Lottery()
    lot.load()
    raw = _ensure_datetime(lot.get_raw_data())
    two = _ensure_datetime(lot.get_2_digits_data())
    if raw.empty or two.empty:
        raise RuntimeError("No data loaded. Run src/sync.py first.")

    raw_calendar = require_daily_contiguous(
        raw["date"], context="cau-keo raw history"
    )
    two_calendar = require_daily_contiguous(
        two["date"], context="cau-keo two-digit history"
    )
    if not raw_calendar.equals(two_calendar):
        raise ValueError("cau-keo raw and two-digit histories are not date-aligned")

    dates, loto_hit, de_hit, loto_counts = _build_hit_matrices(two)
    if not dates.equals(two_calendar):
        raise ValueError("cau-keo hit-matrix dates changed during normalization")

    hit = _target_matrix(mode, loto_hit, de_hit)
    n_days = len(dates)
    if n_days < config.min_history_days + 2:
        raise RuntimeError(
            f"Need at least {config.min_history_days + 2} days, got {n_days}."
        )

    de_targets = (two["special"].astype(int).to_numpy() % 100).astype(np.int16)
    reverse = _reverse_numbers()
    nums = np.arange(100, dtype=np.int16)
    tens = (nums // 10).astype(np.int16)
    ones = (nums % 10).astype(np.int16)
    digit_total = ((tens + ones) % 10).astype(np.int16)

    freq_3 = _rolling_sum_bool(hit, 3)
    freq_7 = _rolling_sum_bool(hit, 7)
    freq_14 = _rolling_sum_bool(hit, 14)
    freq_30 = _rolling_sum_bool(hit, 30)
    freq_90 = _rolling_sum_bool(hit, min(90, n_days))
    freq_365 = _rolling_sum_bool(hit, min(365, n_days))
    gap = _compute_gap(hit)
    loto_occ_7 = _rolling_sum_int(loto_counts, 7)

    # Pair/path support from raw result digits. The raw/two date-axis equality
    # guard above proves that path_support[t] and hit[t] refer to the same day.
    raw_digits = [_raw_digits_from_row(r) for _, r in raw.iterrows()]
    P = raw_digits[0].shape[0]
    I, J = _pairs_indices(P)
    path_support = _path_support_matrix(
        raw_digits, config.lag_max_for_path_support, I, J
    )

    # Dynamic, leakage-aware conditional counts. Updated with relationships that
    # have known outcomes before creating features for anchor day t.
    cond_de_counts = np.zeros((100, 100), dtype=np.int32)
    cond_de_trials = np.zeros(100, dtype=np.int32)
    cond_loto_counts = np.zeros((100, 100), dtype=np.int32)
    cond_loto_trials = np.zeros(100, dtype=np.int32)

    rows: list[pd.DataFrame] = []
    targets: list[np.ndarray] = []
    end_t = n_days - 2 if include_target else n_days - 1
    start_save_t = max(1, config.min_history_days)
    if include_target and config.window_days and n_days > config.window_days:
        start_save_t = max(start_save_t, n_days - config.window_days - 1)
    elif not include_target:
        # For next-day inference we only need the latest anchor frame. The loop
        # still walks prior days to update conditional transition counts, but it
        # no longer builds hundreds/thousands of throwaway DataFrames.
        start_save_t = end_t

    for t in range(1, end_t + 1):
        # Calendar continuity has already been proven, so k=t-1 -> t is exactly
        # a one-calendar-day transition known by anchor t.
        k = t - 1
        s_prev = int(de_targets[k])
        cond_de_trials[s_prev] += 1
        known_target_hits = np.where(hit[t] > 0)[0]
        cond_de_counts[s_prev, known_target_hits] += 1

        prev_loto_hits = np.where(loto_hit[k] > 0)[0]
        if prev_loto_hits.size and known_target_hits.size:
            cond_loto_trials[prev_loto_hits] += 1
            cond_loto_counts[np.ix_(prev_loto_hits, known_target_hits)] += 1

        if t < start_save_t:
            continue

        target_date = (
            dates[t + 1]
            if include_target
            else dates[t] + pd.Timedelta(days=1)
        )
        target_weekday = int(target_date.weekday())
        month_to_date, year_to_date = _build_month_year_to_date(
            hit, dates, t, target_date
        )
        same_weekday = _build_same_weekday_feature(
            hit, dates, anchor_t=t, target_weekday=target_weekday
        )

        prev_special = int(de_targets[t])
        prev_head = prev_special // 10
        prev_tail = prev_special % 10
        prev_total = (prev_head + prev_tail) % 10
        prev_rev = int(reverse[prev_special])
        prev_bong = _bong_number(prev_special)

        cond_de_rate = (
            cond_de_counts[prev_special].astype(float) + 1.0
        ) / (cond_de_trials[prev_special] + 10.0)
        cond_loto_mean, cond_loto_max = _conditional_loto_rates(
            cond_loto_counts,
            cond_loto_trials,
            loto_hit[t],
        )

        head_freq_7 = np.zeros(100, dtype=np.int16)
        tail_freq_7 = np.zeros(100, dtype=np.int16)
        f7_t = freq_7[t]
        for h in range(10):
            head_freq_7[h * 10 : h * 10 + 10] = int(
                f7_t[h * 10 : h * 10 + 10].sum()
            )
        for tail in range(10):
            tail_freq_7[tail::10] = int(f7_t[tail::10].sum())

        frame = pd.DataFrame(
            {
                "anchor_date": [dates[t].date().isoformat()] * 100,
                "predict_for_date": [target_date.date().isoformat()] * 100,
                "mode": [mode] * 100,
                "number": nums.astype(int),
                "number_str": [_fmt2(i) for i in nums],
                "number_value": nums.astype(float) / 99.0,
                "tens": tens,
                "ones": ones,
                "digit_total": digit_total,
                "weekday_next": [target_weekday] * 100,
                "month_next": [int(target_date.month)] * 100,
                "freq_3d": freq_3[t],
                "freq_7d": freq_7[t],
                "freq_14d": freq_14[t],
                "freq_30d": freq_30[t],
                "freq_90d": freq_90[t],
                "freq_365d": freq_365[t],
                "gap": gap[t],
                "gap_log": np.log1p(gap[t].astype(float)),
                "hit_today": hit[t].astype(np.int16),
                "hit_yesterday": hit[t - 1].astype(np.int16),
                "hit_2d_ago": (
                    hit[t - 2].astype(np.int16)
                    if t >= 2
                    else np.zeros(100, dtype=np.int16)
                ),
                "loto_occ_today": loto_counts[t],
                "loto_occ_7d": loto_occ_7[t],
                "same_weekday_freq_364": same_weekday,
                "month_to_date_freq": month_to_date,
                "year_to_date_freq": year_to_date,
                "path_support": path_support[t],
                "path_support_log": np.log1p(path_support[t].astype(float)),
                "reverse_hit_today": hit[t, reverse].astype(np.int16),
                "reverse_freq_7d": freq_7[t, reverse],
                "is_prev_special": (nums == prev_special).astype(np.int16),
                "is_reverse_prev_special": (nums == prev_rev).astype(np.int16),
                "is_bong_prev_special": (nums == prev_bong).astype(np.int16),
                "share_head_prev_special": (tens == prev_head).astype(np.int16),
                "share_tail_prev_special": (ones == prev_tail).astype(np.int16),
                "same_total_prev_special": (digit_total == prev_total).astype(np.int16),
                "cham_overlap_prev_special": (
                    (tens == prev_head)
                    | (tens == prev_tail)
                    | (ones == prev_head)
                    | (ones == prev_tail)
                ).astype(np.int16),
                "cond_de_rate": cond_de_rate,
                "cond_loto_mean_rate": cond_loto_mean,
                "cond_loto_max_rate": cond_loto_max,
                "head_freq_7d": head_freq_7,
                "tail_freq_7d": tail_freq_7,
                "trend_7_vs_30": freq_7[t].astype(float)
                - (freq_30[t].astype(float) * 7.0 / 30.0),
            }
        )
        rows.append(frame)
        if include_target:
            targets.append(hit[t + 1].astype(np.int16))

    X = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    y = (
        pd.Series(np.concatenate(targets).astype(int), name="target")
        if include_target and targets
        else None
    )
    return X, y


def _train_model(
    mode: Mode, X: pd.DataFrame, y: pd.Series, models_dir: Path
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    X = X.copy()
    X["anchor_date"] = pd.to_datetime(X["anchor_date"])
    unique_days = pd.DatetimeIndex(sorted(X["anchor_date"].unique()))
    calib_start, val_start = _time_splits(unique_days)

    train_mask = X["anchor_date"] < calib_start
    calib_mask = (X["anchor_date"] >= calib_start) & (
        X["anchor_date"] < val_start
    )
    val_mask = X["anchor_date"] >= val_start

    Xf = X[FEATURE_COLS].astype(np.float32).to_numpy()
    y_np = y.to_numpy().astype(int)

    X_train, y_train = Xf[train_mask.to_numpy()], y_np[train_mask.to_numpy()]
    X_cal, y_cal = Xf[calib_mask.to_numpy()], y_np[calib_mask.to_numpy()]
    X_val, y_val = Xf[val_mask.to_numpy()], y_np[val_mask.to_numpy()]

    neg_ratio = 22 if mode == "de" else 8
    # Downsample only the fit block. Calibration must retain the natural class
    # prevalence; downsampling it makes Platt probabilities systematically too high.
    X_train, y_train = _downsample(
        X_train, y_train, neg_ratio=neg_ratio, seed=20260812
    )

    clf = PlattCalibratedClassifier(
        base=HistGradientBoostingClassifier(
            max_depth=4,
            learning_rate=0.045,
            max_iter=180,
            l2_regularization=0.35,
            early_stopping=True,
            random_state=20260812,
        )
    )
    clf.fit(X_train, y_train)
    p_cal = clf.base_.predict_proba(X_cal)[:, 1]
    clf.fit_platt(p_cal, y_cal)

    p_val = clf.predict_proba(X_val)[:, 1]
    brier = brier_score_loss(y_val, p_val)
    ll = log_loss(
        y_val, np.vstack([1 - p_val, p_val]).T, labels=[0, 1]
    )

    val_df = X.loc[val_mask].copy().reset_index(drop=True)
    val_df["target"] = y_val
    val_df["prob"] = p_val

    report = _topk_backtest(val_df, mode=mode)
    report.insert(0, "mode", mode)
    report["val_brier"] = round(float(brier), 10)
    report["val_logloss"] = round(float(ll), 10)
    report["calib_start"] = str(pd.to_datetime(calib_start).date())
    report["val_start"] = str(pd.to_datetime(val_start).date())
    report["neg_ratio"] = int(neg_ratio)
    report["features"] = len(FEATURE_COLS)

    pack = {
        "model_type": "cau_keo_platt_hgb",
        "model": clf,
        "features": FEATURE_COLS,
        "mode": mode,
        "calib_start": str(calib_start),
        "val_start": str(val_start),
        "neg_ratio": int(neg_ratio),
        "trained_at": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "trained_through_date": str(
            pd.to_datetime(X["anchor_date"]).max().date()
        ),
        "calibration_prevalence": "natural",
        "calendar_contract": "daily-contiguous raw and two-digit histories",
    }

    models_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(pack, models_dir / f"cau_keo_{mode}.joblib")
    return pack, report, val_df


def _topk_backtest(
    val_df: pd.DataFrame,
    *,
    mode: Mode,
    ks: tuple[int, ...] = (5, 8, 10, 15, 20),
) -> pd.DataFrame:
    if val_df.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    grouped = val_df.sort_values(
        ["predict_for_date", "prob"], ascending=[True, False]
    ).groupby("predict_for_date", sort=True)
    n_days = grouped.ngroups
    for k in ks:
        hit_any = 0
        hits_total = 0
        for _, g in grouped:
            top = g.head(k)
            hits = int(top["target"].sum())
            hits_total += hits
            hit_any += int(hits > 0)
        rows.append(
            {
                "top_k": k,
                "validation_days": n_days,
                "hit_any_days": hit_any,
                "hit_any_rate": hit_any / max(n_days, 1),
                "avg_hits_per_day": hits_total / max(n_days, 1),
                "interpretation": (
                    "top-k contains actual target"
                    if mode == "de"
                    else "top-k contains at least one actual loto"
                ),
            }
        )
    return pd.DataFrame(rows)


def _load_or_train(
    mode: Mode,
    models_dir: Path,
    config: CauKeoConfig,
    *,
    force_train: bool = False,
) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    model_path = models_dir / f"cau_keo_{mode}.joblib"
    X_train, y_train = build_cau_keo_feature_frame(
        mode, include_target=True, config=config
    )
    latest_anchor = str(pd.to_datetime(X_train["anchor_date"]).max().date())
    needs_train = force_train or not model_path.exists()

    if not needs_train:
        try:
            pack = joblib.load(model_path)
            same_schema = pack.get("features") == FEATURE_COLS
            up_to_date = str(pack.get("trained_through_date", "")) == latest_anchor
            if same_schema and up_to_date:
                # Produce a fresh validation report while avoiding duplicate training
                # inside the same daily pipeline run. A new draw automatically makes
                # ``latest_anchor`` advance and forces retraining.
                X_eval = X_train.copy()
                X_eval["anchor_date"] = pd.to_datetime(X_eval["anchor_date"])
                unique_days = pd.DatetimeIndex(
                    sorted(X_eval["anchor_date"].unique())
                )
                _, val_start = _time_splits(unique_days)
                val_mask = X_eval["anchor_date"] >= val_start
                model = pack["model"]
                p = model.predict_proba(
                    X_eval.loc[val_mask, FEATURE_COLS]
                    .astype(np.float32)
                    .to_numpy()
                )[:, 1]
                val_df = X_eval.loc[val_mask].copy().reset_index(drop=True)
                val_df["target"] = (
                    y_train.loc[val_mask.to_numpy()].to_numpy().astype(int)
                )
                val_df["prob"] = p
                report = _topk_backtest(val_df, mode=mode)
                report.insert(0, "mode", mode)
                return pack, report, val_df
            if same_schema and not up_to_date:
                logger.info(
                    "New draw detected for %s (%s -> %s); retraining cầu-kèo model.",
                    mode,
                    pack.get("trained_through_date"),
                    latest_anchor,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cannot load %s (%s). Retraining.", model_path, exc)

    if y_train is None:
        raise RuntimeError("supervised target is required for cầu-kèo training")
    return _train_model(mode, X_train, y_train, models_dir)


def _reason_candidates(
    row: pd.Series, quantiles: dict[str, float]
) -> list[str]:
    reasons: list[str] = []
    if float(row.get("ml_prob_raw", 0.0)) >= quantiles.get("ml_prob_raw", 1.0):
        reasons.append("ML xác suất cao")
    if float(row.get("path_support", 0.0)) >= quantiles.get("path_support", 1.0):
        reasons.append("cầu rawdata mạnh")
    if float(row.get("cond_de_rate", 0.0)) >= quantiles.get("cond_de_rate", 1.0):
        reasons.append("hợp điều kiện ĐB hôm trước")
    if float(row.get("cond_loto_max_rate", 0.0)) >= quantiles.get(
        "cond_loto_max_rate", 1.0
    ):
        reasons.append("hợp điều kiện loto hôm trước")
    if float(row.get("same_weekday_freq_364", 0.0)) >= quantiles.get(
        "same_weekday_freq_364", 1.0
    ):
        reasons.append("cùng thứ trong tuần nổi bật")
    if int(float(row.get("reverse_hit_today", 0))) == 1:
        reasons.append("cặp lộn vừa chạm")
    if int(float(row.get("is_reverse_prev_special", 0))) == 1:
        reasons.append("đảo của ĐB gần nhất")
    if int(float(row.get("is_bong_prev_special", 0))) == 1:
        reasons.append("bóng của ĐB gần nhất")
    if int(float(row.get("cham_overlap_prev_special", 0))) == 1:
        reasons.append("cùng chạm ĐB gần nhất")
    if float(row.get("gap", 0.0)) >= quantiles.get("gap", 1.0):
        reasons.append("gan/nhịp cao")
    if float(row.get("freq_30d", 0.0)) >= quantiles.get("freq_30d", 1.0):
        reasons.append("tần suất 30 ngày cao")
    return reasons


def _add_ai_judgement(pred: pd.DataFrame, *, mode: Mode) -> pd.DataFrame:
    out = pred.copy()
    prob_norm = _minmax(out["ml_prob_raw"])
    path_norm = _minmax(out["path_support"])
    cond_de_norm = _minmax(out["cond_de_rate"])
    cond_loto_norm = _minmax(out["cond_loto_max_rate"])
    freq30_norm = _minmax(out["freq_30d"])
    gap_norm = _minmax(out["gap"])
    weekday_norm = _minmax(out["same_weekday_freq_364"])
    trend_norm = _minmax(out["trend_7_vs_30"])

    if mode == "loto":
        score = 100 * (
            0.38 * prob_norm
            + 0.18 * path_norm
            + 0.14 * cond_de_norm
            + 0.13 * cond_loto_norm
            + 0.10 * freq30_norm
            + 0.04 * weekday_norm
            + 0.03 * trend_norm
        )
    else:
        score = 100 * (
            0.42 * prob_norm
            + 0.18 * cond_de_norm
            + 0.16 * path_norm
            + 0.10 * gap_norm
            + 0.08 * weekday_norm
            + 0.06 * cond_loto_norm
        )

    out["cau_score"] = np.round(score, 4)
    out["score_band"] = [
        _score_band(float(s)) for s in out["cau_score"]
    ]

    qcols = [
        "ml_prob_raw",
        "path_support",
        "cond_de_rate",
        "cond_loto_max_rate",
        "same_weekday_freq_364",
        "gap",
        "freq_30d",
    ]
    quantiles = {
        c: float(pd.to_numeric(out[c], errors="coerce").quantile(0.80))
        for c in qcols
        if c in out.columns
    }

    reason_1: list[str] = []
    reason_2: list[str] = []
    reason_3: list[str] = []
    primary: list[str] = []
    evidence: list[str] = []
    for _, row in out.iterrows():
        reasons = _reason_candidates(row, quantiles)
        while len(reasons) < 3:
            # deterministic, user-friendly fallbacks
            if "tần suất gần" not in reasons:
                reasons.append("tần suất gần")
            elif "nhịp lịch sử" not in reasons:
                reasons.append("nhịp lịch sử")
            else:
                reasons.append("điểm tổng hợp")
        reason_1.append(reasons[0])
        reason_2.append(reasons[1])
        reason_3.append(reasons[2])
        primary.append(" + ".join(reasons[:2]))
        evidence.append(
            f"ML={float(row['ml_prob_raw']):.4f}; "
            f"cầu={int(float(row['path_support']))}; "
            f"ĐB→x={float(row['cond_de_rate']):.3f}; "
            f"loto→x={float(row['cond_loto_max_rate']):.3f}; "
            f"gap={int(float(row['gap']))}; "
            f"f30={int(float(row['freq_30d']))}"
        )

    out["primary_reason"] = primary
    out["reason_1"] = reason_1
    out["reason_2"] = reason_2
    out["reason_3"] = reason_3
    out["evidence"] = evidence
    out["note"] = (
        "AI/ML ranking signal from historical statistics; not a guaranteed prediction"
    )

    # A probability alias for compatibility with older dashboard/statistics loaders.
    if mode == "de":
        s = float(out["ml_prob_raw"].sum())
        out["prob"] = (
            out["ml_prob_raw"] / s if s > 0 else out["ml_prob_raw"]
        )
    else:
        out["prob"] = out["ml_prob_raw"]
    out["prob_percent"] = (out["prob"] * 100.0).round(4)
    return out.sort_values(
        ["cau_score", "ml_prob_raw"], ascending=False
    ).reset_index(drop=True)


def _predict_next(
    mode: Mode, pack: dict, config: CauKeoConfig
) -> pd.DataFrame:
    X_pred, _ = build_cau_keo_feature_frame(
        mode, include_target=False, config=config
    )
    latest_anchor = sorted(X_pred["anchor_date"].astype(str).unique())[-1]
    X_pred = X_pred[
        X_pred["anchor_date"].astype(str) == latest_anchor
    ].copy().reset_index(drop=True)

    model = pack["model"]
    proba = model.predict_proba(
        X_pred[FEATURE_COLS].astype(np.float32).to_numpy()
    )[:, 1]
    X_pred["ml_prob_raw"] = proba
    return _add_ai_judgement(X_pred, mode=mode)


def _write_outputs(
    *,
    mode: Mode,
    pred: pd.DataFrame,
    report: pd.DataFrame,
    val_df: pd.DataFrame,
    out_dir: Path,
    top: int,
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    base_cols = [
        "predict_for_date",
        "anchor_date",
        "mode",
        "number_str",
        "number",
        "prob",
        "prob_percent",
        "ml_prob_raw",
        "cau_score",
        "score_band",
        "primary_reason",
        "reason_1",
        "reason_2",
        "reason_3",
        "evidence",
        "freq_7d",
        "freq_30d",
        "freq_90d",
        "gap",
        "loto_occ_today",
        "same_weekday_freq_364",
        "path_support",
        "cond_de_rate",
        "cond_loto_mean_rate",
        "cond_loto_max_rate",
        "reverse_hit_today",
        "is_reverse_prev_special",
        "is_bong_prev_special",
        "cham_overlap_prev_special",
        "trend_7_vs_30",
        "note",
    ]
    cols = [c for c in base_cols if c in pred.columns]

    all_path = out_dir / f"cau_keo_{mode}_all.csv"
    top_path = out_dir / f"cau_keo_{mode}_top{top}.csv"
    report_path = out_dir / f"cau_keo_report_{mode}.csv"
    backtest_path = out_dir / f"cau_keo_backtest_{mode}.csv"
    manifest_path = out_dir / f"cau_keo_manifest_{mode}.json"

    pred[cols].to_csv(all_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    pred.head(top)[cols].to_csv(
        top_path, index=False, quoting=csv.QUOTE_NONNUMERIC
    )
    report.to_csv(report_path, index=False, quoting=csv.QUOTE_NONNUMERIC)

    # Store a compact validation sample, enough for debugging UI/reporting.
    backtest_cols = ["predict_for_date", "number_str", "target", "prob"]
    bt = val_df.copy()
    if "number_str" not in bt.columns and "number" in bt.columns:
        bt["number_str"] = bt["number"].map(_fmt2)
    bt = (
        bt.sort_values(["predict_for_date", "prob"], ascending=[True, False])
        .groupby("predict_for_date")
        .head(top)
    )
    bt[[c for c in backtest_cols if c in bt.columns]].to_csv(
        backtest_path, index=False, quoting=csv.QUOTE_NONNUMERIC
    )

    payload = {
        "mode": mode,
        "generated_at": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "predict_for_date": (
            str(pred["predict_for_date"].iloc[0]) if not pred.empty else ""
        ),
        "top": int(top),
        "features": FEATURE_COLS,
        "calendar_contract": "daily-contiguous raw and two-digit histories",
        "outputs": {
            "all": all_path.name,
            "top": top_path.name,
            "report": report_path.name,
            "backtest": backtest_path.name,
        },
        "note": (
            "AI/ML scores are calibrated historical ranking signals, not guaranteed "
            "future lottery outcomes."
        ),
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    created.extend(
        [all_path, top_path, report_path, backtest_path, manifest_path]
    )
    return created


def run(
    *,
    mode: Mode | Literal["both"] = "both",
    models_dir: Path | str = "models",
    out_dir: Path | str = "data/ai_ml",
    config: CauKeoConfig | None = None,
    force_train: bool = False,
) -> list[Path]:
    cfg = config or CauKeoConfig()
    models = Path(models_dir)
    out = Path(out_dir)
    modes: list[Mode] = ["loto", "de"] if mode == "both" else [mode]
    created: list[Path] = []

    for m in modes:
        pack, report, val_df = _load_or_train(
            m, models, cfg, force_train=force_train
        )
        pred = _predict_next(m, pack, cfg)
        created.extend(
            _write_outputs(
                mode=m,
                pred=pred,
                report=report,
                val_df=val_df,
                out_dir=out,
                top=cfg.top,
            )
        )
        logger.info(
            "Generated cầu-kèo AI/ML %s for %s",
            m,
            pred["predict_for_date"].iloc[0],
        )

    return created


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train/predict explainable AI/ML cầu-kèo ranking for loto and ĐB."
    )
    parser.add_argument("--mode", choices=["loto", "de", "both"], default="both")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--out-dir", default="data/ai_ml")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--window-days", type=int, default=2000)
    parser.add_argument("--min-history-days", type=int, default=60)
    parser.add_argument("--lag-max", type=int, default=30)
    parser.add_argument("--force-train", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    cfg = CauKeoConfig(
        min_history_days=args.min_history_days,
        lag_max_for_path_support=args.lag_max,
        window_days=args.window_days,
        top=args.top,
    )
    created = run(
        mode=args.mode,
        models_dir=args.models_dir,
        out_dir=args.out_dir,
        config=cfg,
        force_train=args.force_train,
    )
    for path in created:
        print(f"[OK] {path}")


if __name__ == "__main__":
    main()
