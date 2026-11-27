from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def benjamini_hochberg(values: list[float] | np.ndarray) -> np.ndarray:
    probabilities = np.asarray(values, dtype=float)
    if probabilities.ndim != 1:
        raise ValueError("p-values phải là vector một chiều")
    finite = np.isfinite(probabilities)
    observed = probabilities[finite]
    if ((observed < 0) | (observed > 1)).any():
        raise ValueError("p-values hữu hạn phải thuộc [0, 1]")
    result = np.full(probabilities.shape, np.nan)
    if not len(observed):
        return result
    order = np.argsort(observed, kind="stable")
    ranked = observed[order] * len(observed) / np.arange(1, len(observed) + 1)
    adjusted = np.minimum.accumulate(ranked[::-1])[::-1]
    restored = np.empty_like(adjusted)
    restored[order] = np.clip(adjusted, 0, 1)
    result[finite] = restored
    return result


def holm(p_values: Sequence[float]) -> list[float]:
    values = [float(p) for p in p_values]
    order = sorted(range(len(values)), key=values.__getitem__)
    adjusted = [1.0] * len(values)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(values) - rank) * values[index]))
        adjusted[index] = running
    return adjusted
