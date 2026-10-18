"""Giữ số nháy cho tiền thưởng, còn xác suất và Hit-Rate chấm nhị phân."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

import ml_engine.main_pipeline as orchestration
import ml_engine.models as learners
from ml_engine.capabilities import CAPABILITIES
from ml_engine.main_pipeline import ContinuousLearningPipeline, PipelineConfig
from ml_engine.metrics import EconomicModel, PerformanceTracker, score_day
from ml_engine.schema import ObservationMatrix
from ml_engine.validation import WalkForwardValidator


@pytest.fixture
def observations():
    rng = np.random.default_rng(721)
    counts = rng.multinomial(27, np.full(100, 0.01), size=61)
    counts[-1] = 0
    counts[-1, [17, 25]] = [2, 25]
    return ObservationMatrix(pd.date_range("2025-02-01", periods=61), counts)


@pytest.mark.parametrize("enabled", [True, False])
def test_temporal_configuration_uses_the_real_linear_fallback_without_torch(
    observations, monkeypatch, enabled
):
    capabilities = replace(CAPABILITIES, torch=None)
    monkeypatch.setattr(orchestration, "CAPABILITIES", capabilities)
    monkeypatch.setattr(learners, "CAPABILITIES", capabilities)
    pipeline = ContinuousLearningPipeline(
        observations, PipelineConfig(warmup=60, use_temporal=enabled, use_ranking=False)
    )
    assert ("temporal_sequence" in pipeline.arm_builders) is enabled
    if enabled:
        model = pipeline.arm_builders["temporal_sequence"]()
        assert model.backend == "linear"
        model.fit_sequence(observations.hits[:60])
        probabilities = model.predict_sequence(observations.hits[:60])
        assert probabilities.shape == (100,)
        assert np.isfinite(probabilities).all()
        assert np.all((probabilities >= 0) & (probabilities <= 1))


def test_two_occurrences_pay_twice_without_changing_binary_scores(observations):
    counts = observations.counts[-1]
    outcome = counts > 0
    probabilities = np.full(100, 0.1)
    probabilities[17] = 0.9
    tracker = PerformanceTracker(k_values=(1,))
    score = tracker.add(probabilities, outcome, counts=counts)
    binary_score = score_day(probabilities, outcome, k_values=(1,))
    assert score.brier == binary_score.brier
    assert score.logloss == binary_score.logloss
    assert score.hit_rate_at == {1: 1}
    assert score.actual_hits == 2
    assert score.occurrences_at == {1: 2}
    assert tracker.report().profit_ratio[1] == pytest.approx((160 - 23) / 23)


@pytest.mark.parametrize("invalid", [
    np.zeros(99), np.full(100, np.nan), np.full(100, np.inf),
    np.full(100, -1), np.full(100, 0.5), np.zeros(100),
])
def test_payout_counts_must_be_valid_and_align_with_binary_outcome(invalid):
    with pytest.raises(ValueError, match="counts"):
        score_day(np.full(100, 0.2), np.ones(100), counts=invalid)


def test_economics_uses_expected_occurrences_instead_of_hit_probability():
    economics = EconomicModel()
    assert economics.baseline_edge == pytest.approx((0.27 * 80 - 23) / 23)
    assert economics.required_relative_lift() == pytest.approx((23 / 80) / 0.27 - 1)


class _FixedLearner:
    """Bộ học cố định để theo dõi số nháy qua đường cuốn chiếu thật."""

    def fit(self, x, y):
        pass

    def predict_proba(self, x):
        probabilities = np.full(100, 0.1)
        probabilities[17] = 0.9
        probabilities[[1, 2]] = [0.8, 0.7]
        return probabilities


def test_walk_forward_preserves_occurrences_for_payout(observations):
    report = WalkForwardValidator(observations.counts, warmup=60).evaluate(
        _FixedLearner, start=60, stop=61
    )
    assert report.hit_rate_at[3] == 1
    assert report.profit_ratio[3] == pytest.approx((160 - 3 * 23) / (3 * 23))


def test_pipeline_preserves_occurrences_for_payout(observations, monkeypatch):
    pipeline = ContinuousLearningPipeline(
        observations, PipelineConfig(warmup=60, use_temporal=False, use_ranking=False)
    )
    # Giữ đường dự báo/chấm/học thật, chỉ thay bộ học bằng dự báo cố định.
    pipeline.arm_builders = {name: _FixedLearner for name in pipeline.arm_builders}
    booster = learners.TabularBooster
    monkeypatch.setattr(orchestration, "TabularBooster", lambda: booster(n_estimators=2))
    pipeline.safe_mode.apply = lambda counts, probabilities: probabilities
    pipeline.step(60)
    report = pipeline.tracker.report()
    assert report.hit_rate_at[3] == 1
    assert report.profit_ratio[3] == pytest.approx((160 - 3 * 23) / (3 * 23))
