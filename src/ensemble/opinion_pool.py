from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

import numpy as np

from ensemble.ensemble_utils import clip01, logit, normalize_distribution, sigmoid

Mode = Literal["loto", "de"]
PoolKind = Literal["linear", "log"]

_EPS: Final[float] = 1e-6
MIN_SELECTION_DAYS: Final[int] = 60
DEFAULT_HOLDOUT: Final[float] = 0.30
SIGNIFICANCE_SIGMAS = 2.0

SHARPNESS_GRID: Final[tuple[float, ...]] = (
    0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.85, 1.0, 1.2, 1.5, 2.0, 3.0,
)


@dataclass(frozen=True)
class PoolParams:

    kind: PoolKind
    weights: tuple[float, ...]
    baseline: float
    sharpness: float = 1.0

    def __post_init__(self) -> None:
        w = np.asarray(self.weights, dtype=float)
        if w.size == 0:
            raise ValueError("phải có ít nhất một thành phần")
        if not np.isfinite(w).all() or np.any(w < 0.0):
            raise ValueError("trọng số phải hữu hạn và không âm")
        if float(w.sum()) <= 0.0:
            raise ValueError("tổng trọng số phải dương")
        if not 0.0 < self.baseline < 1.0:
            raise ValueError("tần suất nền phải nằm trong (0, 1)")
        if not np.isfinite(self.sharpness) or self.sharpness < 0.0:
            raise ValueError("độ sắc phải hữu hạn và không âm")

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "weights": [float(v) for v in self.weights],
            "baseline": float(self.baseline),
            "sharpness": float(self.sharpness),
        }


def apply_pool(mode: Mode, components: np.ndarray, params: PoolParams) -> np.ndarray:
    matrix = np.asarray(components, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("components phải có dạng (số thành phần, số con)")
    if matrix.shape[0] != len(params.weights):
        raise ValueError("số thành phần không khớp số trọng số")
    if not np.isfinite(matrix).all():
        raise ValueError("xác suất thành phần phải hữu hạn")

    w = np.asarray(params.weights, dtype=float)
    w = w / w.sum()

    if params.kind == "linear":
        pooled = np.tensordot(w, clip01(matrix, eps=_EPS), axes=(0, 0))
    else:
        base_logit = logit(np.full(matrix.shape[1], params.baseline))
        deviation = logit(clip01(matrix, eps=_EPS)) - base_logit[None, :]
        pooled = sigmoid(base_logit + params.sharpness * np.tensordot(w, deviation, axes=(0, 0)))

    pooled = clip01(pooled, eps=_EPS)
    return normalize_distribution(pooled) if mode == "de" else pooled


@dataclass(frozen=True)
class PoolAudit:

    chosen: PoolKind
    sharpness: float
    brier_by_candidate: dict[str, float]
    fit_days: int
    holdout_days: int
    selected: bool

    def describe(self) -> str:
        if not self.selected:
            return (
                f"Không chọn được ({self.fit_days + self.holdout_days} kỳ, dưới ngưỡng "
                f"{MIN_SELECTION_DAYS}); giữ trộn số học."
            )
        ranked = sorted(self.brier_by_candidate.items(), key=lambda kv: kv[1])
        detail = ", ".join(f"{name} {score:.6f}" for name, score in ranked[:4])
        return (
            f"Chọn '{self.chosen}' (độ sắc {self.sharpness:g}) theo Brier trên "
            f"{self.holdout_days} kỳ giữ riêng ({detail})."
        )


def fit_pool(
    mode: Mode,
    components_by_day: np.ndarray,
    y_by_day: np.ndarray,
    weights: np.ndarray,
    *,
    holdout_fraction: float = DEFAULT_HOLDOUT,
) -> tuple[PoolParams, PoolAudit]:
    cube = np.asarray(components_by_day, dtype=float)
    labels = np.asarray(y_by_day, dtype=float)
    if cube.ndim != 3:
        raise ValueError("components_by_day phải có dạng (kỳ, thành phần, số con)")
    if labels.shape != (cube.shape[0], cube.shape[2]):
        raise ValueError("y_by_day phải có dạng (kỳ, số con)")
    if not 0.05 <= holdout_fraction <= 0.6:
        raise ValueError("holdout_fraction phải nằm trong [0.05, 0.6]")

    days = cube.shape[0]
    split = int(round(days * (1.0 - holdout_fraction)))
    w = tuple(float(v) for v in np.asarray(weights, dtype=float))

    if days < MIN_SELECTION_DAYS or split <= 0 or days - split <= 0:
        baseline = float(np.clip(labels.mean(), _EPS, 1 - _EPS)) if labels.size else 0.5
        return (
            PoolParams(kind="linear", weights=w, baseline=baseline),
            PoolAudit("linear", 1.0, {}, days, 0, selected=False),
        )

    baseline = float(np.clip(labels[:split].mean(), _EPS, 1 - _EPS))

    candidates: dict[str, PoolParams] = {
        "linear": PoolParams(kind="linear", weights=w, baseline=baseline),
    }
    for sharpness in SHARPNESS_GRID:
        candidates[f"log(s={sharpness:g})"] = PoolParams(
            kind="log", weights=w, baseline=baseline, sharpness=sharpness
        )

    per_day: dict[str, np.ndarray] = {}
    for name, params in candidates.items():
        pooled = np.vstack([apply_pool(mode, day, params) for day in cube[split:]])
        per_day[name] = np.mean((pooled - labels[split:]) ** 2, axis=1)
    scores = {name: float(errors.mean()) for name, errors in per_day.items()}

    names = list(candidates)
    best_name = min(names, key=lambda n: (scores[n], names.index(n)))
    best_errors = per_day[best_name]
    n_days = max(best_errors.size, 1)

    tied = []
    for name in names:
        delta = per_day[name] - best_errors
        standard_error = (
            float(np.std(delta, ddof=1) / np.sqrt(n_days)) if n_days > 1 else 0.0
        )
        if float(delta.mean()) <= SIGNIFICANCE_SIGMAS * standard_error + 1e-12:
            tied.append(name)
    chosen = candidates[tied[0]]
    return chosen, PoolAudit(
        chosen=chosen.kind,
        sharpness=chosen.sharpness,
        brier_by_candidate=scores,
        fit_days=split,
        holdout_days=days - split,
        selected=True,
    )
