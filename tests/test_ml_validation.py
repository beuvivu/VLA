from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ml_validation import (
    ValidationConfig,
    _paired_date_bootstrap,
    assert_temporal_partitions,
    compare_paired_predictions,
    evaluate_predictions,
    predict_with_feature_allowlist,
    relative_skill,
)


def test_metric_direction_uses_positive_values_for_lower_challenger_loss() -> None:
    assert relative_skill(0.20, 0.15) == pytest.approx(0.25)
    assert relative_skill(0.20, 0.20) == pytest.approx(0.0)
    assert relative_skill(0.20, 0.25) == pytest.approx(-0.25)


def test_clustered_bootstrap_resamples_complete_dates() -> None:
    dates = np.repeat(pd.date_range("2026-01-01", periods=2), 2)
    y = np.tile([0, 1], 2)
    baseline = evaluate_predictions(y, [0.5] * 4, dates)
    challenger = evaluate_predictions(y, [0.1, 0.9, 0.9, 0.1], dates)
    config = ValidationConfig(
        bootstrap_replicates=200,
        bootstrap_seed=17,
        minimum_oos_dates=1,
    )

    brier, _ = _paired_date_bootstrap(baseline, challenger, config=config)

    # Sampling two whole dates can select good/good, good/bad, or bad/bad.
    # Independent row bootstrap would produce additional intermediate values.
    assert set(np.round(brier, 8)).issubset({0.24, -0.16, -0.56})
    assert {0.24, -0.16, -0.56}.issubset(set(np.round(brier, 8)))


def test_promotion_requires_positive_paired_confidence_intervals() -> None:
    dates = np.repeat(pd.date_range("2026-01-01", periods=40), 2)
    y = np.tile([0, 1], 40)
    baseline = evaluate_predictions(y, [0.5] * len(y), dates)
    challenger = evaluate_predictions(y, np.tile([0.2, 0.8], 40), dates)
    decision = compare_paired_predictions(
        baseline,
        challenger,
        config=ValidationConfig(bootstrap_replicates=100, bootstrap_seed=9),
        temporal_checks_pass=True,
    )

    assert decision.promoted is True
    assert decision.brier_skill > 0
    assert decision.logloss_skill > 0
    assert decision.brier_improvement.lower > 0
    assert decision.logloss_improvement.lower > 0
    assert decision.rejection_reasons == ()


def test_promotion_fails_closed_for_noise_and_insufficient_dates() -> None:
    dates = np.repeat(pd.date_range("2026-01-01", periods=5), 2)
    y = np.tile([0, 1], 5)
    baseline = evaluate_predictions(y, [0.5] * len(y), dates)
    same = evaluate_predictions(y, [0.5] * len(y), dates)
    decision = compare_paired_predictions(
        baseline,
        same,
        config=ValidationConfig(bootstrap_replicates=25, minimum_oos_dates=30),
        temporal_checks_pass=True,
    )

    assert decision.promoted is False
    assert "insufficient_oos_dates" in decision.rejection_reasons
    assert "negative_brier_skill" in decision.rejection_reasons
    assert "negative_logloss_skill" in decision.rejection_reasons
    assert "brier_ci_crosses_zero" in decision.rejection_reasons
    assert "logloss_ci_crosses_zero" in decision.rejection_reasons


def test_temporal_partitions_reject_same_date_crossing_boundaries() -> None:
    dates = np.array(["2026-01-01", "2026-01-02", "2026-01-02", "2026-01-03"])
    with pytest.raises(ValueError, match="same draw date"):
        assert_temporal_partitions(
            dates,
            [True, True, False, False],
            [False, False, True, False],
            [False, False, False, True],
        )


def test_rejected_feature_cannot_affect_allowlisted_inference() -> None:
    class FirstColumnModel:
        def predict_proba(self, values: np.ndarray) -> np.ndarray:
            positive = np.clip(values[:, 0], 0.0, 1.0)
            return np.column_stack([1.0 - positive, positive])

    frame = pd.DataFrame({"baseline": [0.2, 0.8], "rejected_experiment": [0.0, 1.0]})
    expected = predict_with_feature_allowlist(FirstColumnModel(), frame, ["baseline"])
    mutated = frame.copy()
    mutated["rejected_experiment"] = [-1e20, 1e20]
    actual = predict_with_feature_allowlist(FirstColumnModel(), mutated, ["baseline"])

    np.testing.assert_array_equal(actual, expected)


def test_production_inference_rejects_nonfinite_features_and_invalid_probabilities() -> None:
    class InvalidProbabilityModel:
        def predict_proba(self, values: np.ndarray) -> np.ndarray:
            return np.column_stack([np.zeros(len(values)), np.full(len(values), 1.2)])

    with pytest.raises(ValueError, match="features must be finite"):
        predict_with_feature_allowlist(
            InvalidProbabilityModel(),
            pd.DataFrame({"baseline": [np.inf]}),
            ["baseline"],
        )

    with pytest.raises(ValueError, match="outside"):
        predict_with_feature_allowlist(
            InvalidProbabilityModel(),
            pd.DataFrame({"baseline": [0.5]}),
            ["baseline"],
        )
