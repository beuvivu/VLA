from __future__ import annotations

import numpy as np
import pytest

from ensemble_utils import normalize_distribution


def test_zero_distribution_uses_its_actual_state_space_size() -> None:
    normalized = normalize_distribution(np.zeros(4, dtype=int))
    np.testing.assert_allclose(normalized, np.full(4, 0.25))
    assert normalized.dtype == np.float64


@pytest.mark.parametrize(
    "values",
    [np.array([]), np.array([0.5, np.nan]), np.array([1.0, -0.1])],
)
def test_distribution_normalization_rejects_invalid_values(values: np.ndarray) -> None:
    with pytest.raises(ValueError):
        normalize_distribution(values)
