from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.conditional_matrices import build_cooccurrence_matrix, build_transition_matrix


def _sparse(days: int) -> pd.DataFrame:
    frame = pd.DataFrame(0, index=np.arange(days), columns=["date", *range(100)])
    frame["date"] = pd.date_range("2026-02-01", periods=days, freq="D")
    return frame


def test_transition_matrix_keeps_raw_counts_and_beta_smoothing() -> None:
    history = _sparse(4)
    history.loc[[0, 2], 1] = 1
    history.loc[[1, 3], 2] = 1

    result = build_transition_matrix(history, "2026-02-05", alpha=1.0)

    assert result.eligible_observations == 3
    assert int(result.source_counts[1]) == 2
    assert int(result.counts[1, 2]) == 2
    assert float(result.support[1, 2]) == pytest.approx(2 / 3)
    assert float(result.confidence[1, 2]) == pytest.approx(1.0)
    assert float(result.smoothed_probability[1, 2]) == pytest.approx(3 / 4)


def test_cooccurrence_and_transition_are_strictly_before_cutoff() -> None:
    history = _sparse(5)
    history.loc[0, [3, 4]] = 1
    cutoff = "2026-02-05"
    before_cooccur = build_cooccurrence_matrix(history, cutoff)
    before_transition = build_transition_matrix(history, cutoff)

    mutated = history.copy()
    mutated.loc[mutated["date"] >= pd.Timestamp(cutoff), list(range(100))] = 9
    after_cooccur = build_cooccurrence_matrix(mutated, cutoff)
    after_transition = build_transition_matrix(mutated, cutoff)

    np.testing.assert_array_equal(before_cooccur.counts, after_cooccur.counts)
    np.testing.assert_array_equal(before_transition.counts, after_transition.counts)
