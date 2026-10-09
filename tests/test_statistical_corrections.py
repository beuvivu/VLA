"""Phép hiệu chỉnh chung không để giá trị thiếu làm mất các kiểm định hợp lệ."""
from __future__ import annotations

import numpy as np
import pytest

from research_diagnostics import bh_fdr
from significance_stats import _bh_fdr


@pytest.mark.parametrize("correct", [bh_fdr, _bh_fdr])
def test_missing_p_value_does_not_poison_other_hypotheses(correct) -> None:
    corrected = correct(np.array([0.01, np.nan, 0.2, np.inf]))
    np.testing.assert_allclose(corrected[[0, 2]], [0.02, 0.2])
    assert np.isnan(corrected[[1, 3]]).all()


@pytest.mark.parametrize("correct", [bh_fdr, _bh_fdr])
@pytest.mark.parametrize("values", [[-0.01, 0.5], [0.2, 1.1], [[0.1, 0.2]]])
def test_invalid_finite_p_values_or_matrix_are_rejected(correct, values) -> None:
    with pytest.raises(ValueError):
        correct(np.asarray(values))


@pytest.mark.parametrize("correct", [bh_fdr, _bh_fdr])
def test_fdr_finite_values_keep_order_and_known_result(correct) -> None:
    np.testing.assert_allclose(correct(np.array([0.04, 0.01, 0.03, 0.002])), [0.04, 0.02, 0.04, 0.008])
    assert correct(np.array([])).shape == (0,)
