from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


def ensure_full_probs(df: pd.DataFrame) -> np.ndarray:
    """Return length-100 probability vector indexed by number 0..99."""
    p = np.zeros(100, dtype=np.float64)
    if df is None or df.empty:
        return p
    nums = df["number"].astype(int).to_numpy()
    probs = df["prob"].astype(float).to_numpy()
    mask = (nums >= 0) & (nums < 100)
    p[nums[mask]] = probs[mask]
    return p


def normalize_distribution(p: np.ndarray) -> np.ndarray:
    values = np.asarray(p, dtype=np.float64)
    if values.size == 0:
        raise ValueError("probability distribution must not be empty")
    if not np.isfinite(values).all() or bool((values < 0.0).any()):
        raise ValueError("probability distribution must be finite and non-negative")
    s = float(np.sum(values))
    if s <= 0:
        return np.full(values.shape, 1.0 / values.size, dtype=np.float64)
    return values / s


def clip01(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    return np.clip(p, eps, 1.0 - eps)


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


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

    def normalized(self) -> "EnsembleWeights":
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


def weight_grid(step: float = 0.10) -> Iterable[EnsembleWeights]:
    """Simplex grid for five ensemble components (fallback when scipy is absent)."""
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


def categorical_logloss(p: np.ndarray, y_true_idx: int) -> float:
    p = clip01(p, eps=1e-12)
    return float(-np.log(p[int(y_true_idx)]))


def categorical_brier(p: np.ndarray, y_true_idx: int) -> float:
    y = np.zeros_like(p)
    y[int(y_true_idx)] = 1.0
    return float(np.mean((p - y) ** 2))
