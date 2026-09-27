"""Hồi quy cho thứ tự dự báo–chấm–học và hợp đồng xác suất."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import ml_engine.main_pipeline as orchestration
import ml_engine.models as learners
from ml_engine.drift import DriftVerdict
from ml_engine.main_pipeline import ContinuousLearningPipeline, PipelineConfig
from ml_engine.metrics import score_day
from ml_engine.models import RankingBooster, TemporalSequenceModel
from ml_engine.schema import BASELINE_RATE, DailyRequest, ObservationMatrix, SchemaError


@pytest.fixture(scope="module")
def observations():
    rng = np.random.default_rng(912)
    counts = np.array([rng.multinomial(27, np.full(100, 0.01)) for _ in range(85)])
    return ObservationMatrix(pd.date_range("2025-02-01", periods=85), counts)


@pytest.fixture
def pipeline(observations, monkeypatch):
    # Giảm chi phí bộ cây, vẫn chạy thật toàn bộ fit/chọn đặc trưng/dự báo.
    booster = learners.TabularBooster
    monkeypatch.setattr(orchestration, "TabularBooster", lambda: booster(n_estimators=2))
    return ContinuousLearningPipeline(
        observations,
        PipelineConfig(warmup=60, window=60, refit_every=40, use_temporal=False, use_ranking=False),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"top_k": 0},
        {"top_k": 101},
        {"top_k": 1.5},
        {"warmup": 1},
        {"window": 0},
        {"refit_every": 0},
        {"discount": np.nan},
        {"feature_epsilon": np.inf},
        {"feature_epsilon": -1},
    ],
)
def test_invalid_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        PipelineConfig(**changes)


def test_repeated_forecast_does_not_change_or_advance_randomness(pipeline):
    first = pipeline.predict_day(70)
    state = json.dumps(pipeline.bandit.to_dict(), sort_keys=True)
    second = pipeline.predict_day(70)
    assert np.array_equal(first[0], second[0])
    assert first[1] == second[1]
    assert json.dumps(pipeline.bandit.to_dict(), sort_keys=True) == state
    first[0][:] = 0.99
    assert np.array_equal(pipeline.predict_day(70)[0], second[0])


def test_step_scores_the_forecast_already_issued(pipeline):
    issued, weights, _ = pipeline.predict_day(70)
    result = pipeline.step(70)
    assert np.array_equal(result.probabilities, issued)
    assert result.arm_weights == weights
    expected = np.mean((issued - (pipeline.observations.counts[70] > 0)) ** 2)
    assert pipeline.tracker.report().brier == pytest.approx(expected)


@pytest.mark.parametrize("action", ["step", "run", "predict"])
def test_past_or_replayed_day_is_rejected_without_learning(pipeline, action):
    pipeline.step(70)
    before = json.dumps(pipeline.bandit.to_dict(), sort_keys=True)
    with pytest.raises(ValueError):
        if action == "step":
            pipeline.step(70)
        elif action == "run":
            pipeline.run(start=69, stop=73)
        else:
            pipeline.predict_day(69)
    assert json.dumps(pipeline.bandit.to_dict(), sort_keys=True) == before
    assert pipeline.tracker.report().days == 1


def test_prediction_refuses_to_reuse_a_model_fitted_in_the_future(pipeline):
    pipeline.predict_day(75)
    with pytest.raises(ValueError):
        pipeline.predict_day(70)
    with pytest.raises(ValueError):
        pipeline.arm_probabilities(70)


def test_rewards_distinguish_identical_rankings_with_wrong_probabilities(pipeline, monkeypatch):
    ordinary = np.linspace(0.22, 0.25, 100)
    overconfident = np.linspace(0.92, 0.95, 100)
    monkeypatch.setattr(
        pipeline,
        "arm_probabilities",
        lambda day: {
            "baseline": np.full(100, BASELINE_RATE),
            "frequency": ordinary,
            "gap_hazard": overconfident,
            "tabular_boosting": ordinary,
        },
    )
    result = pipeline.step(70)
    assert result.arm_rewards["frequency"] > result.arm_rewards["gap_hazard"] + 0.3


def test_drift_refits_next_day_and_records_mode_at_prediction(pipeline, monkeypatch):
    pipeline.predict_day(70)
    monkeypatch.setattr(
        pipeline.drift,
        "update",
        lambda error: DriftVerdict(
            drifted=True,
            method="ks",
            statistic=1.0,
            p_value=0.001,
            window_size=60,
        ),
    )
    result = pipeline.step(70)
    assert result.mode == "normal"
    assert pipeline.safe_mode.mode.value == "safe"
    pipeline.predict_day(71)
    assert pipeline._fitted_at == 71


def test_invalid_arm_probability_does_not_enter_learning_state(pipeline, monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "arm_probabilities",
        lambda day: {name: np.full(100, np.nan) for name in pipeline.arm_builders},
    )
    with pytest.raises(ValueError):
        pipeline.step(70)
    assert pipeline.bandit.total_updates == 0


def test_failed_new_forecast_preserves_the_pending_forecast(pipeline, monkeypatch):
    issued, _, _ = pipeline.predict_day(70)
    fitted_at = pipeline._fitted_at
    pipeline._force_refit = True
    monkeypatch.setattr(
        pipeline,
        "arm_probabilities",
        lambda day: {name: np.full(100, np.nan) for name in pipeline.arm_builders},
    )
    with pytest.raises(ValueError):
        pipeline.predict_day(75)
    assert pipeline._fitted_at == fitted_at
    assert pipeline._force_refit
    assert np.array_equal(pipeline.step(70).probabilities, issued)


@pytest.mark.parametrize("top_k", [2.5, True, "10"])
def test_daily_request_rejects_noninteger_top_k(top_k):
    with pytest.raises(SchemaError):
        DailyRequest.from_json({"anchor_date": "2025-02-01", "top_k": top_k})


def test_daily_request_rejects_a_two_calendar_day_gap_hidden_by_hours():
    with pytest.raises(SchemaError):
        DailyRequest.from_json(
            {
                "anchor_date": "2025-02-01 01:00",
                "target_date": "2025-02-03 00:00",
            }
        )


def test_single_invalid_date_is_rejected():
    counts = np.zeros((1, 100), dtype=int)
    counts[0, 0] = 27
    with pytest.raises(SchemaError):
        ObservationMatrix(pd.DatetimeIndex([pd.NaT]), counts)


def test_overflow_cannot_turn_invalid_counts_into_twenty_seven_draws():
    counts = np.zeros((1, 100), dtype=np.uint64)
    counts[0, :2] = [2**64 - 1, 28]
    with pytest.raises(SchemaError):
        ObservationMatrix(pd.date_range("2025-02-01", periods=1), counts)


@pytest.mark.parametrize("probability,outcome", [(np.nan, 0), (np.inf, 0), (0.2, 2), (0.2, np.nan)])
def test_score_rejects_nonfinite_or_nonbinary_input(probability, outcome):
    with pytest.raises(ValueError):
        score_day(np.full(100, probability), np.full(100, outcome))


def test_counts_reject_fractional_draws(observations):
    counts = observations.counts.astype(float)
    counts[0] = 0
    counts[0, :2] = [26.5, 0.5]
    with pytest.raises(SchemaError):
        ObservationMatrix(observations.dates, counts)


def test_observation_contract_survives_mutating_the_input(observations):
    counts = observations.counts.copy()
    matrix = ObservationMatrix(observations.dates, counts)
    counts[0] = 0
    assert matrix.counts[0].sum() == 27
    with pytest.raises(ValueError):
        matrix.counts[0, 0] = 99


def test_linear_parameter_count_matches_trained_weights(observations):
    model = TemporalSequenceModel(lookback=2)
    model.backend = "linear"
    model.fit_sequence(observations.hits[:12])
    assert model.parameter_count == model._linear_weights.size == 20_100


def test_ranker_calibration_uses_later_days_unseen_by_ranker(monkeypatch):
    class Ranker:
        def __init__(self, **kwargs):
            pass

        def fit(self, x, y, group):
            self.training_days = np.unique(x[:, 0])
            assert sum(group) == len(x)

        def predict(self, x):
            return x[:, 0]

    monkeypatch.setattr(
        learners,
        "CAPABILITIES",
        SimpleNamespace(
            lightgbm=SimpleNamespace(LGBMRanker=Ranker),
        ),
    )
    x = np.repeat(np.arange(10), 100).reshape(-1, 1)
    y = np.tile(np.arange(100) % 2, 10)
    y[-200:] = 0
    model = RankingBooster()
    model.fit(x, y)
    assert model._model.training_days.max() < 8
    assert model.predict_proba(np.array([[9]]))[0] < 0.01


def test_cli_rejects_bandit_only_resume_without_rewriting(tmp_path, caplog):
    state = tmp_path / "bandit.json"
    state.write_text('{"legacy": true}')
    # Không cần dữ liệu đầu vào: resume phải bị từ chối trước khi đọc hay fit.
    result = orchestration.main(["--bandit-state", str(state), "--raw", "missing.csv"])
    assert result == 1
    assert "không đủ để tiếp tục" in caplog.text
    assert state.read_text() == '{"legacy": true}'
