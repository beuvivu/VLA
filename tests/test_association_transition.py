from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from association_rules import _wilson_lower, mine_association_rules
from conditional_matrices import build_cooccurrence_matrix, build_transition_matrix


def _sparse(days: int) -> pd.DataFrame:
    frame = pd.DataFrame(0, index=np.arange(days), columns=["date", *range(100)])
    frame["date"] = pd.date_range("2026-02-01", periods=days, freq="D")
    return frame


def test_association_support_confidence_and_lift_match_definitions() -> None:
    history = _sparse(20)
    history.loc[:9, 1] = 1
    history.loc[:7, 2] = 1
    history.loc[10:11, 2] = 1

    rules = mine_association_rules(
        history,
        "2026-02-21",
        min_support=0.1,
        minimum_antecedent_observations=1,
    )
    rule = rules[(rules["antecedent"] == 1) & (rules["consequent"] == 2)].iloc[0]

    assert int(rule["joint_count"]) == 8
    assert float(rule["support"]) == pytest.approx(8 / 20)
    assert float(rule["confidence"]) == pytest.approx(8 / 10)
    assert float(rule["lift"]) == pytest.approx(1.6)


def test_minimum_support_filters_sparse_rules() -> None:
    history = _sparse(10)
    history.loc[0, [1, 2]] = 1
    rules = mine_association_rules(
        history,
        "2026-02-11",
        min_support=0.2,
        minimum_antecedent_observations=1,
    )
    assert not bool(((rules["antecedent"] == 1) & (rules["consequent"] == 2)).any())


def test_wilson_ranking_penalizes_one_success_from_one_observation() -> None:
    assert _wilson_lower(70, 100) > _wilson_lower(1, 1)


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
