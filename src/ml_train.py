from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, log_loss

from ml_features import FeatureParams, build_ml_table
from ml_models import PlattCalibratedClassifier

FEATURE_SCHEMA_VERSION = 2
FEATURE_COLUMNS = [
    "target_weekday",
    "target_weekday_sin",
    "target_weekday_cos",
    "freq7",
    "freq30",
    "freq90",
    "freq365",
    "ewm14",
    "ewm45",
    "trend_7_30",
    "trend_30_90",
    "gap",
    "log_gap",
    "streak",
    "hit_today",
    "hit_yesterday",
    "weekday_rate",
    "reverse_freq30",
    "reverse_gap",
    "reverse_hit_today",
    "is_double",
    "digit_sum_mod10",
    "path_support",
]


def _time_splits(
    unique_days: pd.DatetimeIndex,
) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    """Four chronological blocks: train | calibration | selection | validation."""
    if len(unique_days) < 80:
        raise RuntimeError("At least 80 historical anchor days are required for ML training.")
    if len(unique_days) >= 180:
        return unique_days[-135], unique_days[-90], unique_days[-45]
    return (
        unique_days[int(len(unique_days) * 0.70)],
        unique_days[int(len(unique_days) * 0.80)],
        unique_days[int(len(unique_days) * 0.90)],
    )


def _recency_weights(dates: pd.Series | pd.DatetimeIndex, half_life_days: float) -> np.ndarray:
    d = pd.DatetimeIndex(pd.to_datetime(dates))
    latest = pd.Timestamp(d.max())
    ages = np.asarray((latest - d).days, dtype=np.float64)
    w = np.power(0.5, ages / max(float(half_life_days), 1.0))
    w = np.clip(w, 0.05, 1.0)
    return (w / max(float(np.mean(w)), 1e-12)).astype(np.float64)


def _downsample(
    X: np.ndarray,
    y: np.ndarray,
    sample_weight: np.ndarray,
    neg_ratio: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    pos = np.where(y == 1)[0]
    neg = np.where(y == 0)[0]
    if len(pos) == 0:
        return X, y, sample_weight
    n_neg = min(len(neg), len(pos) * neg_ratio)
    if n_neg == len(neg):
        keep = np.arange(len(y))
    else:
        sel_neg = rng.choice(neg, size=n_neg, replace=False)
        keep = np.concatenate([pos, sel_neg])
        rng.shuffle(keep)
    return X[keep], y[keep], sample_weight[keep]


def _candidate_configs() -> list[dict[str, object]]:
    # Deliberately conservative candidates. Model selection is temporal and the
    # final validation block remains untouched until the winner is selected.
    return [
        {
            "name": "shallow_smooth",
            "max_depth": 2,
            "learning_rate": 0.050,
            "max_iter": 180,
            "l2_regularization": 0.45,
            "min_samples_leaf": 25,
        },
        {
            "name": "balanced",
            "max_depth": 3,
            "learning_rate": 0.040,
            "max_iter": 220,
            "l2_regularization": 0.60,
            "min_samples_leaf": 20,
        },
        {
            "name": "responsive",
            "max_depth": 3,
            "learning_rate": 0.060,
            "max_iter": 160,
            "l2_regularization": 0.35,
            "min_samples_leaf": 25,
        },
    ]


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
    clf = PlattCalibratedClassifier(base=base)
    clf.fit(X_train, y_train, sample_weight=w_train)
    p_cal = clf.base_.predict_proba(X_cal)[:, 1]
    # Calibration uses the untouched natural class prevalence. Recency weighting
    # changes only the time emphasis; it does not rebalance positives/negatives.
    clf.fit_platt(p_cal, y_cal, sample_weight=w_cal)
    return clf


def _metrics(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    p = np.clip(np.asarray(p, dtype=float), 1e-8, 1 - 1e-8)
    return (
        float(brier_score_loss(y, p)),
        float(log_loss(y, np.column_stack([1 - p, p]), labels=[0, 1])),
    )


def train_one(mode: str, out_dir: Path, window_days: int = 2000) -> None:
    params = FeatureParams()
    X, y = build_ml_table(mode=mode, params=params)
    source_through_date = str(X.attrs.get("source_through_date", ""))
    X["date"] = pd.to_datetime(X["date"])

    unique_days = pd.DatetimeIndex(sorted(X["date"].unique()))
    if len(unique_days) > window_days:
        cutoff = unique_days[-window_days]
        mask = X["date"] >= cutoff
        X = X.loc[mask].reset_index(drop=True)
        y = y.loc[mask].reset_index(drop=True)
        unique_days = pd.DatetimeIndex(sorted(X["date"].unique()))

    calib_start, select_start, val_start = _time_splits(unique_days)
    train_mask = X["date"] < calib_start
    calib_mask = (X["date"] >= calib_start) & (X["date"] < select_start)
    select_mask = (X["date"] >= select_start) & (X["date"] < val_start)
    val_mask = X["date"] >= val_start

    Xf = X[FEATURE_COLUMNS].astype(np.float32).to_numpy()
    y_np = y.to_numpy(dtype=int)

    train_idx = train_mask.to_numpy()
    cal_idx = calib_mask.to_numpy()
    select_idx = select_mask.to_numpy()
    val_idx = val_mask.to_numpy()

    X_train_raw, y_train_raw = Xf[train_idx], y_np[train_idx]
    X_cal, y_cal = Xf[cal_idx], y_np[cal_idx]
    X_select, y_select = Xf[select_idx], y_np[select_idx]
    X_val, y_val = Xf[val_idx], y_np[val_idx]

    if min(len(y_train_raw), len(y_cal), len(y_select), len(y_val)) == 0:
        raise RuntimeError("Temporal ML split produced an empty block.")

    w_train_raw = _recency_weights(X.loc[train_mask, "date"], half_life_days=365.0)
    w_cal = _recency_weights(X.loc[calib_mask, "date"], half_life_days=120.0)

    neg_ratio = 20 if mode == "de" else 10
    X_train, y_train, w_train = _downsample(
        X_train_raw,
        y_train_raw,
        w_train_raw,
        neg_ratio=neg_ratio,
        seed=42,
    )

    candidates: list[tuple[float, dict[str, object], PlattCalibratedClassifier, float, float]] = []
    for cfg in _candidate_configs():
        clf = _fit_candidate(cfg, X_train, y_train, w_train, X_cal, y_cal, w_cal)
        p_sel = clf.predict_proba(X_select)[:, 1]
        brier_sel, ll_sel = _metrics(y_select, p_sel)
        # Log-loss is primary because the downstream ensemble consumes calibrated
        # probabilities; Brier is a small tie-breaker for probability sharpness.
        score = ll_sel + 0.25 * brier_sel
        candidates.append((score, cfg, clf, brier_sel, ll_sel))

    candidates.sort(key=lambda item: item[0])
    _, best_cfg, clf, select_brier, select_ll = candidates[0]

    # Untouched final validation metrics.
    p_val = clf.predict_proba(X_val)[:, 1]
    brier, ll = _metrics(y_val, p_val)

    # A leakage-safe constant baseline learned only before the validation block.
    pre_val = X["date"] < val_start
    baseline_prob = float(np.clip(y_np[pre_val.to_numpy()].mean(), 1e-6, 1 - 1e-6))
    baseline_vec = np.full(len(y_val), baseline_prob, dtype=float)
    baseline_brier, baseline_ll = _metrics(y_val, baseline_vec)
    logloss_skill = float(1.0 - ll / baseline_ll) if baseline_ll > 0 else 0.0
    brier_skill = float(1.0 - brier / baseline_brier) if baseline_brier > 0 else 0.0
    quality_pass = bool(logloss_skill > 0.0 and brier_skill > 0.0)

    # Weak/noisy models stay in the ensemble but are shrunk toward the natural
    # prevalence rather than being allowed to emit overconfident probabilities.
    model_trust = float(np.clip(0.35 + 20.0 * max(0.0, min(logloss_skill, brier_skill)), 0.35, 1.0))

    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / f"ml_{mode}.joblib"
    joblib.dump(
        {
            "model_type": "platt_temporal_hgb",
            "model": clf,
            "features": FEATURE_COLUMNS,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "calib_start": str(calib_start),
            "selection_start": str(select_start),
            "val_start": str(val_start),
            "window_days": int(window_days),
            "neg_ratio": int(neg_ratio),
            "calibration_prevalence": "natural_time_weighted",
            "training_recency_half_life_days": 365.0,
            "calibration_recency_half_life_days": 120.0,
            "selected_candidate": dict(best_cfg),
            "selection_brier": float(select_brier),
            "selection_logloss": float(select_ll),
            "val_brier": float(brier),
            "val_logloss": float(ll),
            "baseline_prob": baseline_prob,
            "baseline_brier": baseline_brier,
            "baseline_logloss": baseline_ll,
            "logloss_skill": logloss_skill,
            "brier_skill": brier_skill,
            "quality_pass": quality_pass,
            "model_trust": model_trust,
            "trained_through_date": source_through_date,
        },
        model_path,
    )

    report = pd.DataFrame(
        [
            {
                "mode": mode,
                "selected_candidate": best_cfg["name"],
                "val_brier": brier,
                "val_logloss": ll,
                "baseline_brier": baseline_brier,
                "baseline_logloss": baseline_ll,
                "brier_skill": brier_skill,
                "logloss_skill": logloss_skill,
                "quality_pass": quality_pass,
                "model_trust": model_trust,
                "calib_start": calib_start,
                "selection_start": select_start,
                "val_start": val_start,
                "window_days": int(window_days),
                "neg_ratio": int(neg_ratio),
            }
        ]
    )
    report.to_csv(out_dir / f"train_report_{mode}.csv", index=False)

    print(f"[OK] saved model: {model_path}")
    print(
        f"[OK] candidate={best_cfg['name']} val_brier={brier:.6f} "
        f"val_logloss={ll:.6f} baseline_logloss={baseline_ll:.6f} "
        f"trust={model_trust:.3f}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["loto", "de"], required=True)
    ap.add_argument("--out-dir", default="models")
    ap.add_argument("--window-days", type=int, default=2000)
    args = ap.parse_args()
    train_one(args.mode, Path(args.out_dir), window_days=args.window_days)


if __name__ == "__main__":
    main()
