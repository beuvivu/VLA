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
from numbers import Integral
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.ensemble import HistGradientBoostingClassifier

from calibration import CalibParams, apply_calibration
from ensemble_components import (
    COMPONENT_KEYS,
    availability_from_history_day,
    probability_component,
    renormalize_available_weights,
)
from ensemble_utils import (
    DEFAULT_ENSEMBLE_WEIGHTS,
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
    clip01,
    finalize_blend,
    normalize_distribution,
)
from ml_models import PlattCalibratedClassifier

META_SCHEMA_VERSION = 3
COMPONENT_COLS = ["p_ml", "p_cau", "p_stat", "p_active", "p_stable"]

# Richer tiers are preferred, but only when every selected component has genuine
# labeled walk-forward history. Smaller tiers have lower production trust caps.
COMPONENT_TIERS = [
    ("five_component", ["p_ml", "p_cau", "p_stat", "p_active", "p_stable"], 0.40),
    ("four_with_cau", ["p_ml", "p_cau", "p_active", "p_stable"], 0.25),
    ("four_with_stat", ["p_ml", "p_stat", "p_active", "p_stable"], 0.25),
    ("core_three", ["p_ml", "p_active", "p_stable"], 0.15),
]


class InsufficientMetaHistory(RuntimeError):
    """Không tầng nào đủ kỳ hợp lệ; khác với lỗi đọc dữ liệu hoặc khớp model."""

    def __init__(self, maturity: dict[str, int], minimum_days: int) -> None:
        self.maturity = dict(maturity)
        self.minimum_days = minimum_days
        super().__init__(
            "Stacked ML history is not mature for any supported tier: "
            + ", ".join(f"{name}={count}" for name, count in maturity.items())
        )


@dataclass(frozen=True)
class MetaMetrics:
    logloss: float
    brier: float
    # AUC-ROC là chỉ số PHỤ, và phải đọc đúng vai trò ấy.
    #
    # Nó đo khả năng XẾP HẠNG và bất biến với MỌI phép biến đổi đơn điệu —
    # nghĩa là một mô hình hiệu chuẩn sai bét vẫn có thể đạt AUC hoàn hảo. Với
    # bài toán mà giá trị nằm ở độ ĐÚNG của xác suất, `brier` và `logloss` mới
    # là chỉ số quyết định; AUC chỉ trả lời câu hỏi khác: "thứ tự có đúng
    # không". Giữ riêng và ghi rõ để không ai dùng nó thay hai chỉ số kia.
    #
    # NaN khi không tính được (một lớp vắng mặt hoàn toàn trong đoạn đánh giá).
    auc_roc: float = float("nan")


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
    if mode not in {"loto", "de"}:
        raise ValueError("mode must be 'loto' or 'de'")
    if arr.size == 0 or not np.isfinite(arr).all():
        raise ValueError("probability values must be non-empty and finite")
    if mode == "de":
        if bool((arr < 0.0).any()):
            raise ValueError("Đặc Biệt probability weights must be non-negative")
        return normalize_distribution(arr)
    if bool(((arr < 0.0) | (arr > 1.0)).any()):
        raise ValueError("loto probabilities must be inside [0, 1]")
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
    df: pd.DataFrame, component_cols: list[str], window_days: int, *, mode: str | None = None
) -> list[str]:
    required = ["target_date", "number", "y", *component_cols]
    if any(c not in df.columns for c in required):
        return []
    days: list[str] = []
    for day, sub in df.groupby("target_date", sort=True):
        labels = pd.to_numeric(sub["y"], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(labels).all() or not np.isin(labels, [0.0, 1.0]).all():
            continue
        if mode == "de" and labels.sum() != 1.0:
            continue
        # Cùng hợp đồng với production: cờ thiếu, vector rỗng và số trùng
        # không được biến thành lịch sử đủ trưởng thành cho tầng xếp chồng.
        available = availability_from_history_day(sub, mode=mode)
        if all(available.get(column.removeprefix("p_"), False) for column in component_cols):
            days.append(str(day))
    return days if window_days <= 0 else days[-window_days:]


def _select_component_tier(
    df: pd.DataFrame, window_days: int, min_days: int, *, mode: str | None = None
) -> tuple[str, list[str], float, list[str], dict[str, int]]:
    maturity: dict[str, int] = {}
    for name, cols, trust_cap in COMPONENT_TIERS:
        days = _complete_days_for_components(df, cols, window_days, mode=mode)
        maturity[name] = len(days)
        if len(days) >= min_days:
            return name, list(cols), float(trust_cap), days, maturity
    raise InsufficientMetaHistory(maturity, min_days)


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
    """Trọng số giảm dần theo NGÀY LỊCH thật, không phải theo số kỳ.

    Khác với ``learn_ensemble_weights._day_weights`` vốn nhận tham số cùng tên
    nhưng đếm theo chỉ số hàng, tức số kỳ. Hai đơn vị lệch nhau trung vị 12 và
    tối đa 50 trên lịch sử hiện có. Đừng sao chép công thức giữa hai nơi.
    """
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


def _day_number_grid(df: pd.DataFrame, column: str, days: list[str]) -> pd.DataFrame:
    """Pivot ``(target_date, number) -> column`` once and reindex onto ``days``.

    The previous implementation scanned and sorted the entire frame once per
    day (``df[day_key == day].sort_values(...)``), i.e. O(days x rows).  With a
    240-day window that is 240 full passes over 24,000 rows for *each* of the
    ~12 matrices ``train_meta`` builds.  One pivot is ~19x faster and returns
    the identical matrix.
    """
    work = pd.DataFrame(
        {
            "day": _date_strings(df["target_date"]),
            "number": pd.to_numeric(df["number"], errors="raise").astype(int),
            "value": pd.to_numeric(df[column], errors="raise").astype(float),
        }
    )
    if work["number"].lt(0).any() or work["number"].gt(99).any():
        raise RuntimeError("history contains numbers outside 00..99")
    if work.duplicated(subset=["day", "number"]).any():
        dupes = work.loc[work.duplicated(subset=["day", "number"]), "day"].unique()
        raise RuntimeError(f"history has duplicate (day, number) rows: {list(dupes)[:5]}")
    grid = work.pivot(index="day", columns="number", values="value")
    missing_days = [day for day in days if day not in grid.index]
    if missing_days:
        raise RuntimeError(f"Missing history day(s): {missing_days[:5]}")
    return grid.reindex(index=days, columns=range(100))


def _matrix_by_day(df: pd.DataFrame, column: str, days: list[str]) -> np.ndarray:
    grid = _day_number_grid(df, column, days)
    if grid.isna().to_numpy().any():
        incomplete = grid.index[grid.isna().any(axis=1)].tolist()
        raise RuntimeError(f"Incomplete history day {incomplete[0]}: missing numbers")
    return grid.to_numpy(dtype=float)


def _roc_auc(probs: np.ndarray, labels: np.ndarray) -> float:
    """AUC-ROC bằng thứ hạng Mann-Whitney, xử lý hoà bằng thứ hạng trung bình.

    Tự tính thay vì gọi sklearn: hàm này chạy trên mảng đã phẳng sẵn ở đây, và
    một phụ thuộc thêm cho mười dòng số học là không đáng. Công thức thứ hạng
    cho đúng kết quả của `sklearn.metrics.roc_auc_score`, kể cả khi có hoà.
    """
    p = np.asarray(probs, dtype=float).reshape(-1)
    y = np.asarray(labels, dtype=float).reshape(-1) > 0.5
    positives = int(y.sum())
    negatives = int(y.size - positives)
    if positives == 0 or negatives == 0:
        # Chỉ một lớp: AUC không xác định. Trả NaN thay vì 0.5 — 0.5 đọc thành
        # "đoán mò", còn sự thật là "không đo được".
        return float("nan")
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(p.size, dtype=float)
    ranks[order] = np.arange(1, p.size + 1, dtype=float)
    # Hoà nhận thứ hạng trung bình, nếu không AUC phụ thuộc thứ tự sắp xếp.
    sorted_p = p[order]
    start = 0
    while start < sorted_p.size:
        stop = start + 1
        while stop < sorted_p.size and sorted_p[stop] == sorted_p[start]:
            stop += 1
        if stop - start > 1:
            ranks[order[start:stop]] = ranks[order[start:stop]].mean()
        start = stop
    rank_sum = float(ranks[y].sum())
    return (rank_sum - positives * (positives + 1) / 2.0) / (positives * negatives)


def _evaluate(mode: str, probs: np.ndarray, y: np.ndarray) -> MetaMetrics:
    if mode == "de":
        ll: list[float] = []
        br: list[float] = []
        for i in range(len(probs)):
            p = clip01(normalize_distribution(probs[i]), eps=1e-12)
            idx = int(np.argmax(y[i]))
            ll.append(categorical_logloss(p, idx))
            br.append(categorical_brier(p, idx))
        return MetaMetrics(
            logloss=float(np.mean(ll)),
            brier=float(np.mean(br)),
            auc_roc=_roc_auc(probs, y),
        )

    p = clip01(probs, eps=1e-6)
    ll = [bernoulli_logloss(p[i], y[i]) for i in range(len(p))]
    br = [bernoulli_brier(p[i], y[i]) for i in range(len(p))]
    return MetaMetrics(
        logloss=float(np.mean(ll)),
        brier=float(np.mean(br)),
        auc_roc=_roc_auc(p, y),
    )


def _row_probs_to_day_matrix(
    row_probs: np.ndarray,
    frame: pd.DataFrame,
    days: list[str],
    mode: str,
) -> np.ndarray:
    temp = frame[["target_date", "number"]].copy()
    temp["prob"] = np.asarray(row_probs, dtype=float)
    grid = _day_number_grid(temp, "prob", days)
    if grid.isna().to_numpy().any():
        incomplete = grid.index[grid.isna().any(axis=1)].tolist()
        raise RuntimeError(f"Incomplete meta probability day {incomplete[0]}")
    matrix = grid.to_numpy(dtype=float)
    return np.vstack([_safe_prob(row, mode) for row in matrix])


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
    # Stack once: SLSQP evaluates the objective ~(k+1) x maxiter times, and the
    # old per-day Python loop re-paid that cost on every single evaluation
    # (~3.2s of pure interpreter overhead for a 240-day window).  The vectorised
    # form is ~9x faster and numerically identical.
    stack = np.stack([np.asarray(arrays[col], dtype=np.float64) for col in component_cols])
    y_arr = np.asarray(y, dtype=np.float64)
    y_idx = np.argmax(y_arr, axis=1) if mode == "de" else None

    def objective(x: np.ndarray) -> float:
        w = np.clip(x, 0.0, 1.0)
        w = w / max(float(w.sum()), 1e-12)
        p = np.tensordot(w, stack, axes=(0, 0))
        if mode == "de":
            p = np.clip(p, 0.0, None)
            totals = p.sum(axis=1, keepdims=True)
            p = np.divide(p, totals, out=np.full_like(p, 1.0 / p.shape[1]), where=totals > 0)
            picked = np.clip(p[np.arange(p.shape[0]), y_idx], 1e-12, 1.0)
            losses = -np.log(picked)
        else:
            pc = np.clip(p, 1e-6, 1.0 - 1e-6)
            losses = -(y_arr * np.log(pc) + (1.0 - y_arr) * np.log1p(-pc)).mean(axis=1)
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
    """Dựng lại policy tuyến tính từ dữ liệu trước lát kiểm.

    Dùng chung bộ học production, mặc định và phép đặt sàn. Trọng số và
    hiệu chuẩn được đóng băng trước lát kiểm; availability vẫn xét riêng
    từng ngày, gồm cả thành phần ngoài tầng của mô hình xếp chồng.
    """
    from learn_ensemble_weights import learn_chronological_stack

    work = history.copy()
    work["target_date"] = _date_strings(work["target_date"])
    pre = work[work["target_date"].isin(pre_val_days)].copy()
    complete = _complete_days_for_components(pre, COMPONENT_COLS, 180, mode=mode)
    weights = DEFAULT_ENSEMBLE_WEIGHTS
    calib = CalibParams(mode=mode)
    if len(complete) >= 20:
        pre = _normalize_components_by_day(
            pre[pre["target_date"].isin(complete)], mode, COMPONENT_COLS
        )
        arrays = {column: _matrix_by_day(pre, column, complete) for column in COMPONENT_COLS}
        weights, _, calib, _, _ = learn_chronological_stack(
            mode, arrays, _matrix_by_day(pre, "y", complete), complete,
            half_life_days, DEFAULT_ENSEMBLE_WEIGHTS,
        )

    by_day = {day: sub for day, sub in work.groupby("target_date", sort=False)}
    predictions: list[np.ndarray] = []
    for day in val_days:
        sub = by_day[day]
        available = availability_from_history_day(sub, mode=mode)
        effective = renormalize_available_weights(weights, available).as_dict()
        raw = np.zeros(100)
        for key in COMPONENT_KEYS:
            if available[key]:
                component = probability_component(
                    sub[["number", f"p_{key}"]].rename(columns={f"p_{key}": "prob"}),
                    mode=mode,
                )
                raw += effective[f"w_{key}"] * component.prob
        raw = finalize_blend(raw, mode)
        predictions.append(apply_calibration(mode, raw, calib) if all(available.values()) else raw)
    configured = weights.as_dict()
    weight_dict = {f"p_{key}": configured[f"w_{key}"] for key in COMPONENT_KEYS}
    return np.vstack(predictions), weight_dict, calib.as_dict()


def _constant_validation(
    history: pd.DataFrame,
    pre_val_days: list[str],
    val_days: list[str],
    mode: str,
) -> np.ndarray:
    """Dự báo KHÔNG THÔNG TIN trên lát thẩm định: cùng một xác suất cho mọi con.

    Đặc Biệt: 1/100. LOTO: tần suất về của một con trên các ngày TRƯỚC lát
    thẩm định — không nhìn vào lát ấy, nên đây là đối thủ ngoài mẫu thật.

    Vì sao phải có mốc này bên cạnh tổ hợp tuyến tính: ngày 25-09-2026, tổ
    hợp tuyến tính hiệu chỉnh của LOTO chọn a=4,89 trên chính các ngày nó được
    khớp — tức LÀM NHỌN xác suất gần năm lần — và trên lát thẩm định cho logloss
    1,0157, tệ gần gấp đôi dự báo hằng số (≈0,545). Mô hình xếp chồng đạt
    0,5456, KHÔNG hơn hằng số, nhưng vẫn "thắng 46%" và được trộn vào
    production. Thắng một đối thủ hỏng không chứng minh được gì.
    """
    if mode == "de":
        return np.full((len(val_days), 100), 0.01)
    pre = history[_date_strings(history["target_date"]).isin(pre_val_days)]
    rate = float(np.clip(_matrix_by_day(pre, "y", pre_val_days).mean(), 1e-6, 1.0 - 1e-6))
    return np.full((len(val_days), 100), rate)


def quality_gate(
    mode: str,
    meta: MetaMetrics,
    linear: MetaMetrics,
    constant: MetaMetrics,
) -> dict[str, float | bool]:
    """Mô hình xếp chồng chỉ được bật khi thắng CẢ HAI đối thủ ngoài mẫu.

    - tổ hợp tuyến tính hiệu chỉnh — thứ production sẽ dùng nếu không có nó;
    - dự báo hằng số — mốc không thông tin, không thể hỏng theo kiểu khớp quá.

    Kỹ năng NHỎ HƠN được ghi lại để một đối thủ hỏng không thổi phồng báo
    cáo. Cổng ngoài mẫu bổ sung xét độ bất định và mức trộn cố định theo tầng.
    """

    def skill(model: float, baseline: float) -> float:
        return 1.0 - model / baseline if baseline > 0 else 0.0

    brier_floor = -0.02 if mode == "de" else 0.0
    result: dict[str, float | bool] = {
        "logloss_skill": skill(meta.logloss, linear.logloss),
        "brier_skill": skill(meta.brier, linear.brier),
        "constant_logloss_skill": skill(meta.logloss, constant.logloss),
        "constant_brier_skill": skill(meta.brier, constant.brier),
    }
    beats_linear = result["logloss_skill"] > 0.003 and result["brier_skill"] > brier_floor
    beats_constant = (
        result["constant_logloss_skill"] > 0.003
        and result["constant_brier_skill"] > brier_floor
    )
    result["quality_pass"] = bool(beats_linear and beats_constant)
    result["gate_skill"] = min(result["logloss_skill"], result["constant_logloss_skill"])
    return result


def holdout_quality_gate(
    mode: str,
    meta_prob: np.ndarray,
    linear_prob: np.ndarray,
    constant_prob: np.ndarray,
    labels: np.ndarray,
    trust: float,
) -> dict[str, float | bool | int]:
    """Chấm chính xác suất sẽ công bố, với mức trộn chốt trước lát kiểm.

    Lấy mẫu theo khối ngày giữ nguyên phụ thuộc trong một kỳ và một phần
    phụ thuộc giữa các kỳ liên tiếp. Khoảng tin cậy là bằng chứng của lát
    kiểm hiện tại, không phải bảo đảm cho chuỗi tái kiểm định vô hạn.
    """
    y = np.asarray(labels, dtype=float)
    if y.ndim != 2 or y.shape[1] != 100 or y.shape[0] == 0:
        raise ValueError("Nhãn thẩm định phải có dạng (số ngày, 100)")
    if not np.isfinite(y).all() or not np.isin(y, [0.0, 1.0]).all():
        raise ValueError("Nhãn thẩm định phải hữu hạn và nhị phân")
    if mode == "de" and not np.all(y.sum(axis=1) == 1.0):
        raise ValueError("Mỗi ngày Đặc Biệt phải có đúng một số trúng")
    matrices = [np.asarray(value, dtype=float) for value in (meta_prob, linear_prob, constant_prob)]
    if any(value.shape != y.shape for value in matrices):
        raise ValueError("Xác suất và nhãn thẩm định phải cùng hình dạng")
    p_meta, p_linear, p_constant = [
        np.vstack([_safe_prob(row, mode) for row in value]) for value in matrices
    ]
    blended = np.vstack([
        blend_predictions(mode, linear, challenger, trust)
        for linear, challenger in zip(p_linear, p_meta, strict=True)
    ])
    linear_metrics = _evaluate(mode, p_linear, y)
    constant_metrics = _evaluate(mode, p_constant, y)
    point_gate = quality_gate(mode, _evaluate(mode, p_meta, y), linear_metrics, constant_metrics)
    blend_metrics = _evaluate(mode, blended, y)
    blend_gate = quality_gate(mode, blend_metrics, linear_metrics, constant_metrics)
    result: dict[str, float | bool | int] = dict(point_gate)
    result.update({f"blend_{key}": value for key, value in blend_gate.items()})
    result["blend_logloss"] = blend_metrics.logloss
    result["blend_brier"] = blend_metrics.brier
    result["holdout_days"] = len(y)

    def daily_loss(prob: np.ndarray) -> np.ndarray:
        if mode == "de":
            hit = prob[np.arange(len(y)), np.argmax(y, axis=1)]
            return -np.log(np.clip(hit, 1e-12, 1.0))
        p = np.clip(prob, 1e-6, 1.0 - 1e-6)
        return -(y * np.log(p) + (1.0 - y) * np.log1p(-p)).mean(axis=1)

    n_days = len(y)
    block_size = max(1, int(np.ceil(n_days ** (1.0 / 3.0))))
    rng = np.random.default_rng(20260927)
    starts = rng.integers(0, n_days, size=(2000, int(np.ceil(n_days / block_size))))
    indices = ((starts[..., None] + np.arange(block_size)) % n_days).reshape(2000, -1)[:, :n_days]
    loss = daily_loss(blended)
    uncertainty_pass = n_days >= 20
    for name, baseline in (("linear", p_linear), ("constant", p_constant)):
        difference = loss - daily_loss(baseline)
        low, high = np.quantile(difference[indices].mean(axis=1), [0.025, 0.975])
        result[f"{name}_delta_ci95_low"] = float(low)
        result[f"{name}_delta_ci95_high"] = float(high)
        uncertainty_pass = uncertainty_pass and float(high) < 0.0
    result["bootstrap_block_days"] = block_size
    result["uncertainty_pass"] = bool(uncertainty_pass)
    result["quality_pass"] = bool(
        point_gate["quality_pass"] and blend_gate["quality_pass"] and uncertainty_pass
    )
    return result


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
    if mode not in {"loto", "de"}:
        raise ValueError("Mode phải là loto hoặc de")
    if not history_path.exists():
        raise RuntimeError(f"History not found: {history_path}")
    history = pd.read_csv(history_path)
    required = {"target_date", "number", "y", "p_ml", "p_active", "p_stable"}
    if missing := required.difference(history.columns):
        raise ValueError(f"Lịch sử stacking thiếu cột: {sorted(missing)}")
    _date_strings(history["target_date"])
    # Bốn lát train/calibrate/select/validate cần ít nhất 100 kỳ ngay cả
    # khi tham số CLI thấp hơn; không nới sàn để làm kiểm phát hành xanh.
    minimum_days = max(100, min_days)
    try:
        tier, component_cols, trust_cap, days, maturity = _select_component_tier(
            history, window_days, minimum_days, mode=mode
        )
    except InsufficientMetaHistory as exc:
        pack = {
            "schema_version": META_SCHEMA_VERSION,
            "mode": mode,
            "status": "insufficient_history",
            "model": None,
            "features": [],
            "component_tier": None,
            "component_cols": [],
            "quality_pass": False,
            "meta_trust": 0.0,
            "history_days": max(exc.maturity.values(), default=0),
            "minimum_history_days": exc.minimum_days,
            "tier_maturity_days": exc.maturity,
            "trained_through_target_date": None,
            "evaluated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "reason": str(exc),
        }
        # Ghi đè pack cũ bằng trạng thái vô hiệu hóa: không giữ một model
        # đang bật khi bằng chứng hiện tại không còn đủ điều kiện.
        models_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(pack, models_dir / f"meta_{mode}.joblib")
        report = {key: value for key, value in pack.items() if key != "model"}
        (report_dir / f"meta_report_{mode}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        pd.DataFrame([{
            key: pack[key]
            for key in ("mode", "status", "history_days", "minimum_history_days", "quality_pass", "meta_trust")
        }]).to_csv(report_dir / f"meta_report_{mode}.csv", index=False)
        print(f"[INFO] stacked ML {mode}: insufficient_history; {pack['history_days']}/{minimum_days} kỳ; giữ linear")
        return pack
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
    p_constant = _constant_validation(history, pre_val_days, val_days, mode)
    constant_metrics = _evaluate(mode, p_constant, y_matrix)

    # Mức trộn cố định theo tầng được khai trước khi nhìn nhãn thẩm định.
    # Không tăng trust theo chính biên thắng trên lát quyết định đề bạt.
    gate = holdout_quality_gate(mode, p_meta, p_baseline, p_constant, y_matrix, trust_cap)
    logloss_skill = float(gate["logloss_skill"])
    brier_skill = float(gate["brier_skill"])
    quality_pass = bool(gate["quality_pass"])

    meta_trust = trust_cap if quality_pass else 0.0

    pack = {
        "schema_version": META_SCHEMA_VERSION,
        "mode": mode,
        "status": "trained",
        "minimum_history_days": minimum_days,
        "model": best_model,
        "features": feature_cols,
        "component_tier": tier,
        "component_cols": component_cols,
        "tier_maturity_days": maturity,
        "tier_trust_cap": trust_cap,
        "selected_candidate": dict(best_cfg),
        "quality_pass": quality_pass,
        "meta_trust": meta_trust,
        "holdout_gate": gate,
        "validation_logloss": meta_metrics.logloss,
        "validation_brier": meta_metrics.brier,
        "baseline_validation_logloss": baseline_metrics.logloss,
        "baseline_validation_brier": baseline_metrics.brier,
        "logloss_skill": logloss_skill,
        "brier_skill": brier_skill,
        "constant_validation_logloss": constant_metrics.logloss,
        "constant_validation_brier": constant_metrics.brier,
        "constant_logloss_skill": float(gate["constant_logloss_skill"]),
        "constant_brier_skill": float(gate["constant_brier_skill"]),
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
        f"vs constant={constant_metrics.logloss:.6f} "
        f"skill={logloss_skill:.4%} constant_skill={float(gate['constant_logloss_skill']):.4%} "
        f"trust={meta_trust:.3f}/{trust_cap:.2f}"
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
    if not isinstance(pack, dict):
        raise ValueError("Invalid stacked-ML model pack")
    schema_version = pack.get("schema_version")
    if isinstance(schema_version, bool) or not isinstance(schema_version, Integral):
        raise ValueError("Invalid stacked-ML schema metadata")
    if schema_version != META_SCHEMA_VERSION:
        raise ValueError("Incompatible stacked-ML schema")
    if str(pack.get("mode")) != mode:
        raise ValueError("Stacked-ML mode mismatch")
    component_cols = list(pack.get("component_cols") or [])
    allowed_component_tiers = {tuple(columns) for _, columns, _ in COMPONENT_TIERS}
    if tuple(component_cols) not in allowed_component_tiers:
        raise ValueError("Stacked-ML component tier is not allowlisted")
    expected_features = meta_feature_columns(component_cols)
    if list(pack.get("features") or []) != expected_features:
        raise ValueError("Stacked-ML feature allowlist mismatch")
    # Mốc này bao gồm mọi nhãn dùng cho fit, chọn và duyệt mô hình. Ngày
    # đích phải đứng sau cả lát thẩm định, kể cả khi chạy lại một ngày cũ.
    try:
        if not isinstance(pack.get("trained_through_target_date"), str) or not isinstance(target_date, str):
            raise ValueError("mốc ngày phải là chuỗi ngày có nguồn gốc")
        last_day = pd.Timestamp(pack.get("trained_through_target_date"))
        target_day = pd.Timestamp(target_date)
        if pd.isna(last_day) or pd.isna(target_day) or last_day.date() >= target_day.date():
            raise ValueError("ngày huấn luyện phải đứng trước ngày dự đoán")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Mốc ngày huấn luyện hoặc ngày đích không hợp lệ") from exc
    model = pack.get("model")
    if not callable(getattr(model, "predict_proba", None)):
        raise ValueError("Stacked-ML model is missing predict_proba")
    frame = current_component_frame(
        target_date, p_ml, p_cau, p_stat, p_active, p_stable
    )
    for column in component_cols:
        component = probability_component(
            frame[["number", column]].rename(columns={column: "prob"}), mode=mode
        )
        if not component.available:
            raise ValueError(f"Thành phần {column} không hợp lệ: {component.reason}")
    features = build_meta_features(frame, mode, component_cols)
    X = features[expected_features].astype(np.float32).to_numpy()
    prediction = np.asarray(model.predict_proba(X), dtype=np.float64)
    if prediction.shape != (len(features), 2):
        raise ValueError("Stacked-ML predict_proba must return shape (rows, 2)")
    p = prediction[:, 1]
    return _safe_prob(p, mode)


def blend_predictions(
    mode: str,
    linear_prob: np.ndarray,
    meta_prob: np.ndarray,
    meta_trust: float,
) -> np.ndarray:
    if not np.isfinite(meta_trust):
        raise ValueError("meta_trust must be finite")
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
