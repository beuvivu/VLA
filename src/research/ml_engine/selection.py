from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from sklearn.metrics import log_loss

from research.ml_engine.capabilities import CAPABILITIES

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

DEFAULT_EPSILON: Final[float] = 1e-4

MIN_FEATURES: Final[int] = 3


@dataclass(frozen=True)
class SelectionResult:

    kept: list[str]
    dropped: list[str]
    importance: dict[str, float]
    method: str

    def describe(self) -> str:
        top = ", ".join(self.kept[:5])
        return (
            f"chọn {len(self.kept)}/{len(self.importance)} đặc trưng bằng {self.method}; "
            f"dẫn đầu: {top}"
        )


def shap_importance(model: Any, x: np.ndarray, names: tuple[str, ...]) -> dict[str, float]:
    if CAPABILITIES.shap is None:
        raise RuntimeError("thiếu thư viện shap")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*list of ndarray.*", category=UserWarning)
        explainer = CAPABILITIES.shap.TreeExplainer(model)
        values = explainer.shap_values(x)
    if isinstance(values, list):
        values = values[-1]
    values = np.asarray(values)
    if values.ndim == 3:
        values = values[..., -1]
    magnitude = np.abs(values).mean(axis=0)
    return dict(zip(names, magnitude.astype(float), strict=True))


def permutation_importance(
    model: Any, x: np.ndarray, y: np.ndarray, names: tuple[str, ...], *, seed: int = 0
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    baseline = log_loss(y, model.predict_proba(x)[:, 1], labels=[0, 1])
    scores: dict[str, float] = {}
    for position, name in enumerate(names):
        shuffled = x.copy()
        shuffled[:, position] = rng.permutation(shuffled[:, position])
        degraded = log_loss(y, model.predict_proba(shuffled)[:, 1], labels=[0, 1])
        scores[name] = max(float(degraded - baseline), 0.0)
    return scores


def select_features(
    model: Any,
    x: np.ndarray,
    y: np.ndarray,
    names: tuple[str, ...],
    *,
    epsilon: float = DEFAULT_EPSILON,
    max_features: int | None = None,
    seed: int = 0,
) -> SelectionResult:
    if x.shape[1] != len(names):
        raise ValueError(f"x có {x.shape[1]} cột nhưng names có {len(names)} tên")

    try:
        importance = shap_importance(model, x, names)
        method = "shap"
    except Exception as error:
        LOGGER.info("Không dùng được SHAP (%s); chuyển sang tầm quan trọng hoán vị", error)
        importance = permutation_importance(model, x, y, names, seed=seed)
        method = "permutation"

    ordered = sorted(importance, key=lambda name: -importance[name])
    kept = [name for name in ordered if importance[name] > epsilon]
    if len(kept) < MIN_FEATURES:
        LOGGER.warning(
            "Chỉ %d/%d đặc trưng vượt ngưỡng %.1e — giữ tối thiểu %d cột đầu bảng",
            len(kept),
            len(names),
            epsilon,
            MIN_FEATURES,
        )
        kept = ordered[:MIN_FEATURES]
    if max_features is not None:
        kept = kept[:max_features]

    return SelectionResult(
        kept=kept,
        dropped=[name for name in ordered if name not in set(kept)],
        importance=importance,
        method=method,
    )
