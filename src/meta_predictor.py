from __future__ import annotations

"""Leakage-safe nonlinear stacking for production prediction components.

Prediction history evolves as new components are introduced. The stacked learner
therefore trains on the richest component tier with enough fully labeled history
instead of fabricating old values. A mature three-component model can run today
with a small trust cap; richer four/five-component tiers activate automatically
only after enough genuine walk-forward observations accumulate.
"""

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.ensemble import HistGradientBoostingClassifier

from calibration import apply_calibration, learn_calibration
from ensemble_utils import (
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
    clip01,
    normalize_distribution,
)
from ml_models import PlattCalibratedClassifier

META_SCHEMA_VERSION = 2
COMPONENT_COLS = ["p_ml", "p_cau", "p_stat", "p_active", "p_stable"]

# Richer tiers are preferred, but only when every selected component has genuine
# labeled walk-forward history. Smaller tiers have lower production trust caps.
COMPONENT_TIERS = [
    ("five_component", ["p_ml", "p_cau", "p_stat", "p_active", "p_stable"], 0.40),
    ("four_with_cau", ["p_ml", "p_cau", "p_active", "p_stable"], 0.25),
    ("four_with_stat", ["p_ml", "p_stat", "p_active", "p_stable"], 0.25),
    ("core_three", ["p_ml", "p_active", "p_stable"], 0.15),
]


@dataclass(frozen=True)
class MetaMetrics:
    logloss: float
    brier: float


def meta_feature_columns(component_cols: list[str]) -> list[str]:
    shorts = [c.removeprefix("p_") for c in component_cols]
    cols = [*component_cols]
    cols += [f"logp_{s}" for s in shorts]
    cols += [f"rank_{s}" for s in shorts]
    cols += [
        "component_mean",
        "component_std",
        "component_min",
        "component_max",
        "component_range",
        "component_cv",
        "above_median_count",
    ]
    for i in range(len(shorts)):
        for j in range(i + 1, len(shorts)):
            cols.append(f"x_{shorts[i]}_{shorts[j]}")
    cols += [
        "weekday_sin",
        "weekday_cos",
        "is_double",
        "digit_sum_mod10",
        "reverse_distance",
    ]
    return cols


META_FEATURE_COLUMNS = meta_feature_columns(COMPONENT_COLS)


def _date_strings(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values).dt.date.astype(str)


def _safe_prob(x: np.ndarray, mode: str) -> np.ndarray:
    arr = np.asarray(x, dtype=np.float64)
    if mode == "de":
        return normalize_distribution(np.clip(arr, 0.0, None))
    return clip01(arr, eps=1e-6)


def _normalize_components_by_day(
    df: pd.DataFrame, mode: str, component_cols: list[str]
) -> pd.DataFrame:
    out = df.copy()
    for col in component_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    if mode != "de":
        return out

    for col in component_cols:
        sums = out.groupby("target_date")[col].transform("sum")
        valid = sums > 0
        out.loc[valid, col] = out.loc[valid, col] / sums[valid]
        out.loc[~valid, col] = 1.0 / 100.0
    return out


def build_meta_features(
    df: pd.DataFrame,
    mode: str,
    component_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Create features available at prediction time; target ``y`` is never read."""
    selected = list(component_cols or COMPONENT_COLS)
    required = ["target_date", "number", *selected]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing meta-predictor columns: {missing}")

    work = _normalize_components_by_day(df[required], mode, selected)
    work["target_date"] = pd.to_datetime(work["target_date"])
    work["number"] = pd.to_numeric(work["number"], errors="raise").astype(int)
    work.sort_values(["target_date", "number"], inplace=True, ignore_index=True)

    p = work[selected].to_numpy(dtype=np.float64)
    if not np.isfinite(p).all():
        raise ValueError("Selected stacked-ML components contain non-finite values")
    p_clip = np.clip(p, 1e-8, 1.0)
    out = work[["target_date", "number", *selected]].copy()

    shorts = [c.removeprefix("p_") for c in selected]
    for j, col in enumerate(selected):
        short = shorts[j]
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

    medians = work.groupby("target_date")[selected].transform("median")
    out["above_median_count"] = (work[selected] >= medians).sum(axis=1)

    for i in range(len(selected)):
        for j in range(i + 1, len(selected)):
            out[f"x_{shorts[i]}_{shorts[j]}"] = (
                work[selected[i]] * work[selected[j]]
            )

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

    feature_cols = meta_feature_columns(selected)
    return out[["target_date", "number", *feature_cols]]


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


def _complete_days_for_components(
    df: pd.DataFrame, component_cols: list[str], window_days: int
) -> list[str]:
    required = ["y", *component_cols]
    if any(c not in df.columns for c in required):
        return []
    ok = df.groupby("target_date")[required].apply(
        lambda g: len(g) == 100 and bool(g.notna().all().all())
    )
    days = sorted(str(day) for day, valid in ok.items() if bool(valid))
    return days if window_days <= 0 else days[-window_days:]


def _select_component_tier(
    df: pd.DataFrame, window_days: int, min_days: int
) -> tuple[str, list[str], float, list[str], dict[str, int]]:
    maturity: dict[str, int] = {}
    for name, cols, trust_cap in COMPONENT_TIERS:
        days = _complete_days_for_components(df, cols, window_days)
        maturity[name] = len(days)
        if len(days) >= min_days:
            return name, list(cols), float(trust_cap), days, maturity
    raise RuntimeError(
        "Stacked ML history is not mature for any supported tier: "
        + ", ".join(f"{name}={count}" for name, count in maturity.items())
    )


def _four_way_split(
    days: list[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    n = len(days)
    if n < 100:
        raise RuntimeError("At least 100 fully labeled days are required for stacked ML.")
    block = max(20, min(30, n // 5))
    if n - 3 * block < 40:
        block = max(15, (n - 40) // 3)
    train_end = n - 3 * block
    cal_end = n - 2 * block
    select_end = n - block
    return (
        days[:train_end],
        days[train_end:cal_end],
        days[cal_end:select_end],
        days[select_end:],
    )


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


def _day_weights(days: list[str], half_life_days: int) -> np.ndarray:
    if half_life_days <= 0:
        return np.ones(len(days), dtype=float)
    ages = np.arange(len(days) - 1, -1, -1, dtype=float)
    w = np.power(0.5, ages / max(float(half_life_days), 1.0))
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
    day_key = _date_strings(df["target_date"])
    rows: list[np.ndarray] = []
    for day in days:
        sub = df[day_key == day].sort_values("number")
        if len(sub) != 100:
            raise RuntimeError(f"Incomplete history day {day}: {len(sub)} rows")
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
    row_probs: np.ndarray,
    frame: pd.DataFrame,
    days: list[str],
    mode: str,
) -> np.ndarray:
    temp = frame[["target_date", "number"]].copy()
    temp["prob"] = np.asarray(row_probs, dtype=float)
    day_key = _date_strings(temp["target_date"])
    out: list[np.ndarray] = []
    for day in days:
        sub = temp[day_key == day].sort_values("number")
        if len(sub) != 100:
            raise RuntimeError(f"Incomplete meta probability day {day}: {len(sub)} rows")
        out.append(_safe_prob(sub["prob"].to_numpy(dtype=float), mode))
    return np.vstack(out)


def _blend_arrays(
    arrays: dict[str, np.ndarray], component_cols: list[str], weights: np.ndarray
) -> np.ndarray:
    out = np.zeros_like(arrays[component_cols[0]], dtype=np.float64)
    for i, col in enumerate(component_cols):
        out += float(weights[i]) * arrays[col]
    return out


def _optimize_linear_weights(
    mode: str,
    arrays: dict[str, np.ndarray],
    component_cols: list[str],
    y: np.ndarray,
    day_weights: np.ndarray,
) -> np.ndarray:
    k = len(component_cols)
    prior = np.full(k, 1.0 / k, dtype=float)

    def objective(x: np.ndarray) -> float:
        w = np.clip(x, 0.0, 1.0)
        w = w / max(float(w.sum()), 1e-12)
        p = _blend_arrays(arrays, component_cols, w)
        if mode == "de":
            losses = []
            for i in range(len(p)):
                pi = normalize_distribution(np.clip(p[i], 0.0, None))
                losses.append(categorical_logloss(pi, int(np.argmax(y[i]))))
        else:
            losses = [bernoulli_logloss(p[i], y[i]) for i in range(len(p))]
        ll = float(np.average(losses, weights=day_weights))
        return ll + 0.02 * float(np.square(w - prior).sum())

    bounds = [(0.0, 0.80)] * k
    constraints = ({"type": "eq", "fun": lambda x: np.sum(x) - 1.0},)
    result = minimize(
        objective,
        x0=prior,
        bounds=bounds,
        constraints=constraints,
        method="SLSQP",
        options={"maxiter": 200},
    )
    if not result.success:
        return prior
    w = np.clip(result.x, 0.0, 1.0)
    return w / max(float(w.sum()), 1e-12)


def _baseline_validation(
    history: pd.DataFrame,
    pre_val_days: list[str],
    val_days: list[str],
    mode: str,
    component_cols: list[str],
    half_life_days: int,
) -> tuple[np.ndarray, dict[str, float], dict]:
    pre = history[_date_strings(history["target_date"]).isin(pre_val_days)].copy()
    arrays_pre = {
        col: _matrix_by_day(pre, col, pre_val_days) for col in component_cols
    }
    y_pre = _matrix_by_day(pre, "y", pre_val_days)
    day_w = _day_weights(pre_val_days, half_life_days)
    weights = _optimize_linear_weights(
        mode, arrays_pre, component_cols, y_pre, day_w
    )
    p_pre = _blend_arrays(arrays_pre, component_cols, weights)
    if mode == "de":
        p_pre = np.vstack([normalize_distribution(row) for row in p_pre])
    calib = learn_calibration(mode, p_pre, y_pre, sample_weight_by_day=day_w)

    val = history[_date_strings(history["target_date"]).isin(val_days)].copy()
    arrays_val = {
        col: _matrix_by_day(val, col, val_days) for col in component_cols
    }
    p_val_raw = _blend_arrays(arrays_val, component_cols, weights)
    p_val = np.vstack(
        [apply_calibration(mode, row, calib) for row in p_val_raw]
    )
    weight_dict = {
        col: float(weights[i]) for i, col in enumerate(component_cols)
    }
    return p_val, weight_dict, calib.as_dict()


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
    tier, component_cols, trust_cap, days, maturity = _select_component_tier(
        history, window_days, min_days
    )
    history = history[_date_strings(history["target_date"]).isin(days)].copy()
    history = _normalize_components_by_day(history, mode, component_cols)
    train_days, cal_days, select_days, val_days = _four_way_split(days)

    features = build_meta_features(history, mode, component_cols)
    features["day_str"] = _date_strings(features["target_date"])
    labels = history[["target_date", "number", "y"]].copy()
    labels["target_date"] = pd.to_datetime(labels["target_date"])
    merged = features.merge(labels, on=["target_date", "number"], how="left")
    feature_cols = meta_feature_columns(component_cols)

    def block(block_days: list[str]) -> tuple[np.ndarray, np.ndarray, pd.Series]:
        sub = merged[merged["day_str"].isin(block_days)]
        return (
            sub[feature_cols].astype(np.float32).to_numpy(),
            sub["y"].astype(int).to_numpy(),
            sub["target_date"],
        )

    X_train_raw, y_train_raw, d_train = block(train_days)
    X_cal, y_cal, d_cal = block(cal_days)
    X_select, _, _ = block(select_days)
    X_val, _, _ = block(val_days)

    w_train_raw = _recency_row_weights(d_train, half_life_days=180.0)
    w_cal = _recency_row_weights(d_cal, half_life_days=90.0)
    X_train, y_train, w_train = _downsample_training(
        X_train_raw, y_train_raw, w_train_raw, mode, seed=42
    )

    select_frame = merged[merged["day_str"].isin(select_days)].copy()
    select_y = _matrix_by_day(history, "y", select_days)
    candidates: list[
        tuple[float, dict[str, object], PlattCalibratedClassifier]
    ] = []
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
    p_baseline, baseline_weights, baseline_calibration = _baseline_validation(
        history,
        pre_val_days,
        val_days,
        mode,
        component_cols,
        half_life_days,
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
        meta_trust = float(
            np.clip(0.05 + 6.0 * logloss_skill, 0.05, trust_cap)
        )

    pack = {
        "schema_version": META_SCHEMA_VERSION,
        "mode": mode,
        "model": best_model,
        "features": feature_cols,
        "component_tier": tier,
        "component_cols": component_cols,
        "tier_maturity_days": maturity,
        "tier_trust_cap": trust_cap,
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
        "baseline_calibration": baseline_calibration,
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
        if k not in {"model", "train_days", "calibration_days"}
    }
    (report_dir / f"meta_report_{mode}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pd.DataFrame(
        [
            {
                "mode": mode,
                "component_tier": tier,
                "components": "+".join(component_cols),
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
                "tier_trust_cap": trust_cap,
                "meta_trust": meta_trust,
            }
        ]
    ).to_csv(report_dir / f"meta_report_{mode}.csv", index=False)

    print(
        f"[OK] stacked ML {mode}: tier={tier} components={component_cols} "
        f"history={len(days)} candidate={best_cfg['name']} "
        f"logloss={meta_metrics.logloss:.6f} "
        f"vs calibrated-linear={baseline_metrics.logloss:.6f} "
        f"skill={logloss_skill:.4%} trust={meta_trust:.3f}/{trust_cap:.2f}"
    )
    print("[INFO] tier maturity:", maturity)
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
    component_cols = list(pack.get("component_cols") or [])
    if not component_cols:
        raise ValueError("Stacked-ML component tier missing")
    frame = current_component_frame(
        target_date, p_ml, p_cau, p_stat, p_active, p_stable
    )
    features = build_meta_features(frame, mode, component_cols)
    columns = list(pack.get("features") or meta_feature_columns(component_cols))
    X = features[columns].astype(np.float32).to_numpy()
    p = pack["model"].predict_proba(X)[:, 1]
    return _safe_prob(p, mode)


def blend_predictions(
    mode: str,
    linear_prob: np.ndarray,
    meta_prob: np.ndarray,
    meta_trust: float,
) -> np.ndarray:
    trust = float(np.clip(meta_trust, 0.0, 0.40))
    linear = _safe_prob(linear_prob, mode)
    meta = _safe_prob(meta_prob, mode)
    blended = (1.0 - trust) * linear + trust * meta
    return _safe_prob(blended, mode)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Train leakage-safe maturity-tiered nonlinear stacked predictor from "
            "walk-forward history."
        )
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
