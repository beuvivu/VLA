from __future__ import annotations

"""Leakage-safe nonlinear stacking for the five production prediction components.

The base system already produces five independent probability signals. This module
learns how their agreement, ranks and interactions relate to the next draw without
replacing the conservative linear ensemble. The stacked learner is a challenger:
it receives non-zero production trust only when it beats a leakage-safe linear
baseline on an untouched chronological validation block.
"""

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from ensemble_utils import (
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
    clip01,
    normalize_distribution,
)
from learn_ensemble_weights import COMPONENT_COLS, _day_weights, _optimize_weights_continuous
from ml_models import PlattCalibratedClassifier

META_SCHEMA_VERSION = 1

META_FEATURE_COLUMNS = [
    "p_ml",
    "p_cau",
    "p_stat",
    "p_active",
    "p_stable",
    "logp_ml",
    "logp_cau",
    "logp_stat",
    "logp_active",
    "logp_stable",
    "rank_ml",
    "rank_cau",
    "rank_stat",
    "rank_active",
    "rank_stable",
    "component_mean",
    "component_std",
    "component_min",
    "component_max",
    "component_range",
    "component_cv",
    "above_median_count",
    "ml_stat_mean",
    "cau_path_mean",
    "path_mean",
    "ml_x_stat",
    "cau_x_path",
    "weekday_sin",
    "weekday_cos",
    "is_double",
    "digit_sum_mod10",
    "reverse_distance",
]


@dataclass(frozen=True)
class MetaMetrics:
    logloss: float
    brier: float


def _safe_prob(x: np.ndarray, mode: str) -> np.ndarray:
    arr = np.asarray(x, dtype=np.float64)
    if mode == "de":
        return normalize_distribution(np.clip(arr, 0.0, None))
    return clip01(arr, eps=1e-6)


def _normalize_components_by_day(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    out = df.copy()
    for col in COMPONENT_COLS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if mode != "de":
        return out

    for col in COMPONENT_COLS:
        sums = out.groupby("target_date")[col].transform("sum")
        valid = sums > 0
        out.loc[valid, col] = out.loc[valid, col] / sums[valid]
        out.loc[~valid, col] = 0.01
    return out


def build_meta_features(df: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Create features available at prediction time; never reads the target y."""
    required = ["target_date", "number", *COMPONENT_COLS]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing meta-predictor columns: {missing}")

    work = _normalize_components_by_day(df[required], mode)
    work["target_date"] = pd.to_datetime(work["target_date"])
    work["number"] = pd.to_numeric(work["number"], errors="raise").astype(int)
    work.sort_values(["target_date", "number"], inplace=True, ignore_index=True)

    p = work[COMPONENT_COLS].to_numpy(dtype=np.float64)
    p_clip = np.clip(p, 1e-8, 1.0)
    out = work[["target_date", "number", *COMPONENT_COLS]].copy()

    for j, col in enumerate(COMPONENT_COLS):
        short = col.removeprefix("p_")
        out[f"logp_{short}"] = np.log(p_clip[:, j])
        rank = work.groupby("target_date")[col].rank(
            method="average", ascending=False, pct=True
        )
        out[f"rank_{short}"] = 1.0 - rank.astype(float)

    out["component_mean"] = np.mean(p, axis=1)
    out["component_std"] = np.std(p, axis=1)
    out["component_min"] = np.min(p, axis=1)
    out["component_max"] = np.max(p, axis=1)
    out["component_range"] = out["component_max"] - out["component_min"]
    out["component_cv"] = out["component_std"] / np.maximum(
        out["component_mean"], 1e-6
    )

    medians = work.groupby("target_date")[COMPONENT_COLS].transform("median")
    out["above_median_count"] = (work[COMPONENT_COLS] >= medians).sum(axis=1)

    out["ml_stat_mean"] = 0.5 * (work["p_ml"] + work["p_stat"])
    path_mean = 0.5 * (work["p_active"] + work["p_stable"])
    out["path_mean"] = path_mean
    out["cau_path_mean"] = 0.5 * (work["p_cau"] + path_mean)
    out["ml_x_stat"] = work["p_ml"] * work["p_stat"]
    out["cau_x_path"] = work["p_cau"] * path_mean

    weekday = out["target_date"].dt.weekday.to_numpy(dtype=np.float64)
    angle = 2.0 * np.pi * weekday / 7.0
    out["weekday_sin"] = np.sin(angle)
    out["weekday_cos"] = np.cos(angle)

    numbers = out["number"].to_numpy(dtype=int)
    tens = numbers // 10
    ones = numbers % 10
    out["is_double"] = (tens == ones).astype(np.int8)
    out["digit_sum_mod10"] = ((tens + ones) % 10).astype(np.int8)
    reverse = 10 * ones + tens
    out["reverse_distance"] = np.abs(numbers - reverse).astype(np.int16)

    return out[["target_date", "number", *META_FEATURE_COLUMNS]]


def current_component_frame(
    target_date: str,
    p_ml: np.ndarray,
    p_cau: np.ndarray,
    p_stat: np.ndarray,
    p_active: np.ndarray,
    p_stable: np.ndarray,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "target_date": [target_date] * 100,
            "number": np.arange(100, dtype=int),
            "p_ml": p_ml,
            "p_cau": p_cau,
            "p_stat": p_stat,
            "p_active": p_active,
            "p_stable": p_stable,
        }
    )


def _complete_days(df: pd.DataFrame, window_days: int) -> list[str]:
    required = ["y", *COMPONENT_COLS]
    if any(c not in df.columns for c in required):
        return []
    ok = df.groupby("target_date")[required].apply(
        lambda g: len(g) == 100 and bool(g.notna().all().all())
    )
    days = sorted(str(day) for day, valid in ok.items() if bool(valid))
    return days if window_days <= 0 else days[-window_days:]


def _four_way_split(days: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    n = len(days)
    if n < 100:
        raise RuntimeError("At least 100 fully labeled days are required for stacked ML.")
    block = max(20, min(30, n // 5))
    if n - 3 * block < 40:
        block = max(15, (n - 40) // 3)
    train_end = n - 3 * block
    cal_end = n - 2 * block
    select_end = n - block
    return days[:train_end], days[train_end:cal_end], days[cal_end:select_end], days[select_end:]


def _candidate_configs() -> list[dict[str, object]]:
    return [
        {
            "name": "meta_shallow",
            "max_depth": 2,
            "learning_rate": 0.040,
            "max_iter": 180,
            "l2_regularization": 0.90,
            "min_samples_leaf": 35,
        },
        {
            "name": "meta_balanced",
            "max_depth": 3,
            "learning_rate": 0.035,
            "max_iter": 220,
            "l2_regularization": 1.20,
            "min_samples_leaf": 30,
        },
        {
            "name": "meta_interaction",
            "max_depth": 3,
            "learning_rate": 0.050,
            "max_iter": 170,
            "l2_regularization": 1.50,
            "min_samples_leaf": 40,
        },
    ]


def _recency_row_weights(dates: pd.Series, half_life_days: float) -> np.ndarray:
    d = pd.DatetimeIndex(pd.to_datetime(dates))
    latest = pd.Timestamp(d.max())
    ages = np.asarray((latest - d).days, dtype=np.float64)
    w = np.power(0.5, ages / max(float(half_life_days), 1.0))
    w = np.clip(w, 0.05, 1.0)
    return w / max(float(np.mean(w)), 1e-12)


def _downsample_training(
    X: np.ndarray,
    y: np.ndarray,
    weights: np.ndarray,
    mode: str,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pos = np.where(y == 1)[0]
    neg = np.where(y == 0)[0]
    if len(pos) == 0 or len(neg) == 0:
        return X, y, weights
    ratio = 20 if mode == "de" else 8
    n_neg = min(len(neg), len(pos) * ratio)
    if n_neg >= len(neg):
        return X, y, weights
    rng = np.random.default_rng(seed)
    selected_neg = rng.choice(neg, size=n_neg, replace=False)
    keep = np.concatenate([pos, selected_neg])
    rng.shuffle(keep)
    return X[keep], y[keep], weights[keep]


def _fit_candidate(
    cfg: dict[str, object],
    X_train: np.ndarray,
    y_train: np.ndarray,
    w_train: np.ndarray,
    X_cal: np.ndarray,
    y_cal: np.ndarray,
    w_cal: np.ndarray,
) -> PlattCalibratedClassifier:
    base = HistGradientBoostingClassifier(
        max_depth=int(cfg["max_depth"]),
        learning_rate=float(cfg["learning_rate"]),
        max_iter=int(cfg["max_iter"]),
        l2_regularization=float(cfg["l2_regularization"]),
        min_samples_leaf=int(cfg["min_samples_leaf"]),
        early_stopping=True,
        random_state=42,
    )
    model = PlattCalibratedClassifier(base=base)
    model.fit(X_train, y_train, sample_weight=w_train)
    p_cal = model.base_.predict_proba(X_cal)[:, 1]
    model.fit_platt(p_cal, y_cal, sample_weight=w_cal)
    return model


def _matrix_by_day(df: pd.DataFrame, column: str, days: list[str]) -> np.ndarray:
    rows: list[np.ndarray] = []
    for day in days:
        sub = df[df["target_date"].astype(str) == day].sort_values("number")
        rows.append(sub[column].astype(float).to_numpy())
    return np.vstack(rows)


def _evaluate(mode: str, probs: np.ndarray, y: np.ndarray) -> MetaMetrics:
    if mode == "de":
        ll: list[float] = []
        br: list[float] = []
        for i in range(len(probs)):
            p = clip01(normalize_distribution(probs[i]), eps=1e-12)
            idx = int(np.argmax(y[i]))
            ll.append(categorical_logloss(p, idx))
            br.append(categorical_brier(p, idx))
        return MetaMetrics(logloss=float(np.mean(ll)), brier=float(np.mean(br)))

    p = clip01(probs, eps=1e-6)
    ll = [bernoulli_logloss(p[i], y[i]) for i in range(len(p))]
    br = [bernoulli_brier(p[i], y[i]) for i in range(len(p))]
    return MetaMetrics(logloss=float(np.mean(ll)), brier=float(np.mean(br)))


def _row_probs_to_day_matrix(
    row_probs: np.ndarray, frame: pd.DataFrame, days: list[str], mode: str
) -> np.ndarray:
    temp = frame[["target_date", "number"]].copy()
    temp["prob"] = np.asarray(row_probs, dtype=float)
    out: list[np.ndarray] = []
    for day in days:
        sub = temp[temp["target_date"].astype(str) == day].sort_values("number")
        p = sub["prob"].to_numpy(dtype=float)
        out.append(_safe_prob(p, mode))
    return np.vstack(out)


def _baseline_validation(
    history: pd.DataFrame,
    pre_val_days: list[str],
    val_days: list[str],
    mode: str,
    half_life_days: int,
) -> tuple[np.ndarray, dict[str, float]]:
    pre = history[history["target_date"].astype(str).isin(pre_val_days)].copy()
    all_arrays = {
        col: _matrix_by_day(pre, col, pre_val_days) for col in COMPONENT_COLS
    }
    y_pre = _matrix_by_day(pre, "y", pre_val_days)
    day_w = _day_weights(pre_val_days, half_life_days)
    weights, _, _ = _optimize_weights_continuous(
        mode,
        all_arrays["p_ml"],
        all_arrays["p_cau"],
        all_arrays["p_stat"],
        all_arrays["p_active"],
        all_arrays["p_stable"],
        y_pre,
        day_w,
    )

    val = history[history["target_date"].astype(str).isin(val_days)].copy()
    arrays = {col: _matrix_by_day(val, col, val_days) for col in COMPONENT_COLS}
    p = (
        weights.w_ml * arrays["p_ml"]
        + weights.w_cau * arrays["p_cau"]
        + weights.w_stat * arrays["p_stat"]
        + weights.w_active * arrays["p_active"]
        + weights.w_stable * arrays["p_stable"]
    )
    if mode == "de":
        p = np.vstack([normalize_distribution(row) for row in p])
    return p, weights.as_dict()


def train_meta(
    mode: str,
    history_path: Path,
    models_dir: Path,
    report_dir: Path,
    *,
    window_days: int = 240,
    min_days: int = 100,
    half_life_days: int = 90,
) -> dict:
    if not history_path.exists():
        raise RuntimeError(f"History not found: {history_path}")
    history = pd.read_csv(history_path)
    days = _complete_days(history, window_days)
    if len(days) < min_days:
        raise RuntimeError(
            f"Stacked ML history is not mature: {len(days)} < {min_days} complete days"
        )

    history = history[history["target_date"].astype(str).isin(days)].copy()
    history = _normalize_components_by_day(history, mode)
    train_days, cal_days, select_days, val_days = _four_way_split(days)
    features = build_meta_features(history, mode)
    features["day_str"] = features["target_date"].dt.date.astype(str)
    labels = history.sort_values(["target_date", "number"])[
        ["target_date", "number", "y"]
    ].copy()
    labels["target_date"] = pd.to_datetime(labels["target_date"])
    merged = features.merge(labels, on=["target_date", "number"], how="left")

    def block(block_days: list[str]) -> tuple[np.ndarray, np.ndarray, pd.Series]:
        sub = merged[merged["day_str"].isin(block_days)]
        return (
            sub[META_FEATURE_COLUMNS].astype(np.float32).to_numpy(),
            sub["y"].astype(int).to_numpy(),
            sub["target_date"],
        )

    X_train_raw, y_train_raw, d_train = block(train_days)
    X_cal, y_cal, d_cal = block(cal_days)
    X_select, y_select, _ = block(select_days)
    X_val, y_val, _ = block(val_days)

    w_train_raw = _recency_row_weights(d_train, half_life_days=180.0)
    w_cal = _recency_row_weights(d_cal, half_life_days=90.0)
    X_train, y_train, w_train = _downsample_training(
        X_train_raw, y_train_raw, w_train_raw, mode, seed=42
    )

    candidates: list[tuple[float, dict[str, object], PlattCalibratedClassifier]] = []
    select_frame = merged[merged["day_str"].isin(select_days)].copy()
    select_y = _matrix_by_day(history, "y", select_days)
    for cfg in _candidate_configs():
        model = _fit_candidate(
            cfg, X_train, y_train, w_train, X_cal, y_cal, w_cal
        )
        p_select_rows = model.predict_proba(X_select)[:, 1]
        p_select = _row_probs_to_day_matrix(
            p_select_rows, select_frame, select_days, mode
        )
        metrics = _evaluate(mode, p_select, select_y)
        score = metrics.logloss + 0.20 * metrics.brier
        candidates.append((score, cfg, model))

    candidates.sort(key=lambda item: item[0])
    _, best_cfg, best_model = candidates[0]

    val_frame = merged[merged["day_str"].isin(val_days)].copy()
    p_val_rows = best_model.predict_proba(X_val)[:, 1]
    p_meta = _row_probs_to_day_matrix(p_val_rows, val_frame, val_days, mode)
    y_matrix = _matrix_by_day(history, "y", val_days)
    meta_metrics = _evaluate(mode, p_meta, y_matrix)

    pre_val_days = train_days + cal_days + select_days
    p_baseline, baseline_weights = _baseline_validation(
        history, pre_val_days, val_days, mode, half_life_days
    )
    baseline_metrics = _evaluate(mode, p_baseline, y_matrix)

    logloss_skill = (
        1.0 - meta_metrics.logloss / baseline_metrics.logloss
        if baseline_metrics.logloss > 0
        else 0.0
    )
    brier_skill = (
        1.0 - meta_metrics.brier / baseline_metrics.brier
        if baseline_metrics.brier > 0
        else 0.0
    )
    if mode == "de":
        quality_pass = bool(logloss_skill > 0.003 and brier_skill > -0.02)
    else:
        quality_pass = bool(logloss_skill > 0.003 and brier_skill > 0.0)

    meta_trust = 0.0
    if quality_pass:
        meta_trust = float(np.clip(0.10 + 8.0 * logloss_skill, 0.10, 0.40))

    pack = {
        "schema_version": META_SCHEMA_VERSION,
        "mode": mode,
        "model": best_model,
        "features": META_FEATURE_COLUMNS,
        "selected_candidate": dict(best_cfg),
        "quality_pass": quality_pass,
        "meta_trust": meta_trust,
        "validation_logloss": meta_metrics.logloss,
        "validation_brier": meta_metrics.brier,
        "baseline_validation_logloss": baseline_metrics.logloss,
        "baseline_validation_brier": baseline_metrics.brier,
        "logloss_skill": logloss_skill,
        "brier_skill": brier_skill,
        "baseline_weights": baseline_weights,
        "history_days": len(days),
        "train_days": train_days,
        "calibration_days": cal_days,
        "selection_days": select_days,
        "validation_days": val_days,
        "trained_through_target_date": days[-1],
        "trained_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        ),
    }
    models_dir.mkdir(parents=True, exist_ok=True)
    model_path = models_dir / f"meta_{mode}.joblib"
    joblib.dump(pack, model_path)

    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        k: v
        for k, v in pack.items()
        if k not in {"model", "features", "train_days", "calibration_days"}
    }
    report["features"] = META_FEATURE_COLUMNS
    (report_dir / f"meta_report_{mode}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame(
        [
            {
                "mode": mode,
                "candidate": best_cfg["name"],
                "history_days": len(days),
                "validation_days": len(val_days),
                "meta_logloss": meta_metrics.logloss,
                "linear_logloss": baseline_metrics.logloss,
                "logloss_skill": logloss_skill,
                "meta_brier": meta_metrics.brier,
                "linear_brier": baseline_metrics.brier,
                "brier_skill": brier_skill,
                "quality_pass": quality_pass,
                "meta_trust": meta_trust,
            }
        ]
    ).to_csv(report_dir / f"meta_report_{mode}.csv", index=False)

    print(
        f"[OK] stacked ML {mode}: candidate={best_cfg['name']} "
        f"logloss={meta_metrics.logloss:.6f} vs linear={baseline_metrics.logloss:.6f} "
        f"skill={logloss_skill:.4%} trust={meta_trust:.3f}"
    )
    return pack


def predict_meta(
    pack: dict,
    mode: str,
    target_date: str,
    p_ml: np.ndarray,
    p_cau: np.ndarray,
    p_stat: np.ndarray,
    p_active: np.ndarray,
    p_stable: np.ndarray,
) -> np.ndarray:
    if int(pack.get("schema_version", 0)) != META_SCHEMA_VERSION:
        raise ValueError("Incompatible stacked-ML schema")
    if str(pack.get("mode")) != mode:
        raise ValueError("Stacked-ML mode mismatch")
    frame = current_component_frame(
        target_date, p_ml, p_cau, p_stat, p_active, p_stable
    )
    features = build_meta_features(frame, mode)
    columns = list(pack.get("features", META_FEATURE_COLUMNS))
    X = features[columns].astype(np.float32).to_numpy()
    p = pack["model"].predict_proba(X)[:, 1]
    return _safe_prob(p, mode)


def blend_predictions(
    mode: str, linear_prob: np.ndarray, meta_prob: np.ndarray, meta_trust: float
) -> np.ndarray:
    trust = float(np.clip(meta_trust, 0.0, 0.40))
    linear = _safe_prob(linear_prob, mode)
    meta = _safe_prob(meta_prob, mode)
    blended = (1.0 - trust) * linear + trust * meta
    return _safe_prob(blended, mode)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Train leakage-safe nonlinear stacked predictor from walk-forward history."
    )
    ap.add_argument("--mode", choices=["loto", "de"], required=True)
    ap.add_argument("--history-dir", default="data/history")
    ap.add_argument("--models-dir", default="models")
    ap.add_argument("--report-dir", default="data/ensemble")
    ap.add_argument("--window-days", type=int, default=240)
    ap.add_argument("--min-days", type=int, default=100)
    ap.add_argument("--half-life-days", type=int, default=90)
    args = ap.parse_args()

    train_meta(
        args.mode,
        Path(args.history_dir) / f"pred_{args.mode}.csv",
        Path(args.models_dir),
        Path(args.report_dir),
        window_days=args.window_days,
        min_days=args.min_days,
        half_life_days=args.half_life_days,
    )


if __name__ == "__main__":
    main()
