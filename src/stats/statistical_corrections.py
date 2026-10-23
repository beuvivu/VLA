"""Hiệu chỉnh nhiều kiểm định, giữ nguyên các vị trí thiếu dữ liệu."""
from __future__ import annotations

import numpy as np


def benjamini_hochberg(values: list[float] | np.ndarray) -> np.ndarray:
    """Tính q-value BH trên các p-value hữu hạn, trả về đúng thứ tự đầu vào.

    Args:
        values: Vector p-value. NaN/Inf biểu thị kiểm định không có kết quả.

    Returns:
        Vector q-value; vị trí không hữu hạn giữ NaN và không tăng số kiểm định.

    Raises:
        ValueError: Khi đầu vào không phải vector hoặc p-value hữu hạn ngoài [0, 1].
    """
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
