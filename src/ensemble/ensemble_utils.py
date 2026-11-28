from __future__ import annotations

import json
from dataclasses import dataclass
from numbers import Integral
from pathlib import Path
from typing import Final
from collections.abc import Iterable

import numpy as np

from core.xsmb_domain import LOTO_BASELINE_RATE

MIN_WEIGHTS_SCHEMA: Final[int] = 5


def normalize_distribution(p: np.ndarray) -> np.ndarray:
    values = np.asarray(p, dtype=np.float64)
    if values.size == 0:
        raise ValueError("probability distribution must not be empty")
    if not np.isfinite(values).all() or bool((values < 0.0).any()):
        raise ValueError("probability distribution must be finite and non-negative")
    maximum = float(np.max(values))
    if maximum <= 0:
        return np.full(values.shape, 1.0 / values.size, dtype=np.float64)
    scaled = values / maximum
    return scaled / float(np.sum(scaled))


PROBABILITY_FLOOR_SHARE: Final[float] = 0.05


def floor_distribution(
    p: np.ndarray, *, share: float = PROBABILITY_FLOOR_SHARE
) -> np.ndarray:
    if not 0.0 <= share < 1.0:
        raise ValueError("share must lie in [0, 1)")
    values = normalize_distribution(p)
    if share == 0.0:
        return values
    return (1.0 - share) * values + share / values.size


def clip01(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return np.clip(p, eps, 1.0 - eps)


_PROB_LO: Final[float] = 1e-6
_PROB_HI: Final[float] = 1.0 - 1e-6


def anchor_loto_level(p: np.ndarray) -> np.ndarray:
    values = np.asarray(p, dtype=np.float64)
    total = values.sum(axis=-1, keepdims=True)
    target = values.shape[-1] * LOTO_BASELINE_RATE
    safe = np.where(total > 0.0, total, 1.0)
    scaled = np.where(total > 0.0, values * (target / safe), LOTO_BASELINE_RATE)
    inside = np.all((scaled >= _PROB_LO) & (scaled <= _PROB_HI), axis=-1)
    if np.all(inside):
        return scaled
    rows = scaled.reshape(-1, values.shape[-1])
    raw = values.reshape(-1, values.shape[-1])
    for index in np.flatnonzero(~np.asarray(inside).reshape(-1)):
        rows[index] = _bounded_level(raw[index], target)
    return rows.reshape(values.shape)


def _bounded_level(row: np.ndarray, target: float) -> np.ndarray:
    positive = row > 0.0
    ceiling = positive.sum() * _PROB_HI + (~positive).sum() * _PROB_LO
    if ceiling < target:
        out = np.where(positive, _PROB_HI, 0.0)
        out[~positive] = (target - out.sum()) / max(int((~positive).sum()), 1)
        return out
    low, high = 0.0, _PROB_HI / float(row[positive].min())
    for _ in range(200):
        middle = 0.5 * (low + high)
        if np.clip(middle * row, _PROB_LO, _PROB_HI).sum() < target:
            low = middle
        else:
            high = middle
    return np.clip(high * row, _PROB_LO, _PROB_HI)


def finalize_blend(p: np.ndarray, mode: str, *, anchor_loto: bool = True) -> np.ndarray:
    if mode == "de":
        return floor_distribution(p)
    if mode == "loto":
        return anchor_loto_level(p) if anchor_loto else clip01(p, eps=1e-6)
    raise ValueError("mode must be 'loto' or 'de'")


def sigmoid(x: np.ndarray) -> np.ndarray:
    values = np.asarray(x, dtype=np.float64)
    out = np.empty_like(values)
    positive = values >= 0
    out[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exp_x = np.exp(values[~positive])
    out[~positive] = exp_x / (1.0 + exp_x)
    return out


def logit(p: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    p = np.clip(p, eps, 1.0 - eps)
    return np.log(p / (1.0 - p))


def softmax_from_logp(logp: np.ndarray) -> np.ndarray:
    m = np.max(logp)
    ex = np.exp(logp - m)
    s = np.sum(ex)
    if s <= 0:
        return np.full_like(ex, 1.0 / len(ex))
    return ex / s


@dataclass(frozen=True)
class EnsembleWeights:
    w_ml: float
    w_cau: float = 0.0
    w_stat: float = 0.0
    w_active: float = 0.0
    w_stable: float = 0.0

    def normalized(self) -> EnsembleWeights:
        arr = np.array(
            [self.w_ml, self.w_cau, self.w_stat, self.w_active, self.w_stable],
            dtype=float,
        )
        if not np.isfinite(arr).all():
            raise ValueError("ensemble weights must be finite")
        arr = np.clip(arr, 0.0, 1.0)
        total = float(arr.sum())
        if total <= 0:
            arr[:] = 0.20
        else:
            arr /= total
        return EnsembleWeights(w_ml=float(arr[0]), w_cau=float(arr[1]), w_stat=float(arr[2]), w_active=float(arr[3]), w_stable=float(arr[4]))

    def as_dict(self) -> dict:
        w = self.normalized()
        return {"w_ml": w.w_ml, "w_cau": w.w_cau, "w_stat": w.w_stat, "w_active": w.w_active, "w_stable": w.w_stable}


DEFAULT_ENSEMBLE_WEIGHTS = EnsembleWeights(
    w_ml=0.25, w_cau=0.30, w_stat=0.20, w_active=0.125, w_stable=0.125
)


def load_ensemble_weights(data_dir: Path, mode: str) -> EnsembleWeights:
    path = Path(data_dir) / "ensemble" / f"weights_{mode}.json"
    if not path.exists():
        return DEFAULT_ENSEMBLE_WEIGHTS

    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
        weights = blob.get("weights", {})
        schema = blob.get("schema_version")
        if (
            isinstance(schema, bool)
            or not isinstance(schema, Integral)
            or schema < MIN_WEIGHTS_SCHEMA
            or "w_stat" not in weights
        ):
            return DEFAULT_ENSEMBLE_WEIGHTS
        return EnsembleWeights(
            w_ml=float(weights.get("w_ml", DEFAULT_ENSEMBLE_WEIGHTS.w_ml)),
            w_cau=float(weights.get("w_cau", DEFAULT_ENSEMBLE_WEIGHTS.w_cau)),
            w_stat=float(weights.get("w_stat", DEFAULT_ENSEMBLE_WEIGHTS.w_stat)),
            w_active=float(weights.get("w_active", DEFAULT_ENSEMBLE_WEIGHTS.w_active)),
            w_stable=float(weights.get("w_stable", DEFAULT_ENSEMBLE_WEIGHTS.w_stable)),
        ).normalized()
    except (AttributeError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return DEFAULT_ENSEMBLE_WEIGHTS


def weights_provenance(data_dir: Path, mode: str) -> dict:
    effective = load_ensemble_weights(data_dir, mode)
    path = Path(data_dir) / "ensemble" / f"weights_{mode}.json"
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}

    out: dict = {"mode": mode, "weights": effective.as_dict()}
    promotion = stored.get("promotion")

    if stored:
        for key in ("learned_at_utc", "window_days", "half_life_days", "metric"):
            if key in stored:
                out[key] = stored[key]
        days_used = stored.get("days_used")
        out["days_used"] = len(days_used) if isinstance(days_used, list) else 0

    if not isinstance(promotion, dict):
        out["xuat_xu"] = "khong_co_ho_so"
        out["ly_do"] = (
            "tep trong so thieu hoac sai luoc do" if stored else "chua co tep trong so"
        )
        return out

    if promotion.get("promoted"):
        out["xuat_xu"] = "da_hoc"
    else:
        out["xuat_xu"] = "bi_tu_choi"
    out["ly_do"] = str(promotion.get("reason", ""))

    out["tham_dinh"] = {
        "so_ky_khop": promotion.get("train_days"),
        "so_ky_tham_dinh": promotion.get("validation_days"),
        "logloss_ngoai_mau": promotion.get("validation_logloss"),
        "loi_tuong_doi": promotion.get("relative_gain"),
    }
    return out


def weight_grid(step: float = 0.10) -> Iterable[EnsembleWeights]:
    k = int(round(1.0 / step))
    for i in range(k + 1):
        for j in range(k + 1 - i):
            for m in range(k + 1 - i - j):
                for n in range(k + 1 - i - j - m):
                    q = k - i - j - m - n
                    yield EnsembleWeights(
                        w_ml=i * step,
                        w_cau=j * step,
                        w_stat=m * step,
                        w_active=n * step,
                        w_stable=q * step,
                    )


def bernoulli_logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = clip01(p, eps=1e-6)
    return float(np.mean(-(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))))


def bernoulli_brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def skill_score(model: float, baseline: float) -> float:
    if not np.isfinite(model) or not np.isfinite(baseline) or baseline <= 0.0:
        return 0.0
    return float((baseline - model) / baseline)


def categorical_logloss(p: np.ndarray, y_true_idx: int) -> float:
    p = clip01(p, eps=1e-12)
    return float(-np.log(p[int(y_true_idx)]))


def categorical_brier(p: np.ndarray, y_true_idx: int) -> float:
    values = np.asarray(p, dtype=np.float64)
    y = np.zeros_like(values)
    y[int(y_true_idx)] = 1.0
    return float(np.sum((values - y) ** 2))
