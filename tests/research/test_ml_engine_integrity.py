"""Hồi quy cho thứ tự dự báo–chấm–học và hợp đồng xác suất."""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from research.ml_engine import main_pipeline as orchestration
from research.ml_engine import models as learners
from research.ml_engine.drift import DriftVerdict
from research.ml_engine.main_pipeline import ContinuousLearningPipeline, PipelineConfig
from research.ml_engine.metrics import score_day
from research.ml_engine.models import RankingBooster, TabularBooster, TemporalSequenceModel
from research.ml_engine.schema import BASELINE_RATE, DailyRequest, ObservationMatrix, SchemaError


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
        {"learning_rate": np.nan},
        {"learning_rate": 0.0},
        {"share": 1.0},
        {"trust_window": 10, "trust_min_days": 11},
        {"feature_epsilon": np.inf},
        {"feature_epsilon": -1},
    ],
)
def test_invalid_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        PipelineConfig(**changes)


def _learning_state(pipeline) -> str:
    return json.dumps({"weights": pipeline.aggregator.weights(),
                       "updates": pipeline.aggregator.updates,
                       "trust": pipeline.safe_mode.state()}, sort_keys=True)


def test_repeated_forecast_does_not_change_learning_state(pipeline):
    first = pipeline.predict_day(70)
    state = _learning_state(pipeline)
    second = pipeline.predict_day(70)
    assert np.array_equal(first[0], second[0])
    assert first[1] == second[1]
    assert _learning_state(pipeline) == state
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
    before = _learning_state(pipeline)
    with pytest.raises(ValueError):
        if action == "step":
            pipeline.step(70)
        elif action == "run":
            pipeline.run(start=69, stop=73)
        else:
            pipeline.predict_day(69)
    assert _learning_state(pipeline) == before
    assert pipeline.tracker.report().days == 1


def test_prediction_refuses_to_reuse_a_model_fitted_in_the_future(pipeline):
    pipeline.predict_day(75)
    with pytest.raises(ValueError):
        pipeline.predict_day(70)
    with pytest.raises(ValueError):
        pipeline.arm_probabilities(70)


def test_losses_distinguish_identical_rankings_with_wrong_probabilities(pipeline, monkeypatch):
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
    assert result.arm_losses["gap_hazard"] > result.arm_losses["frequency"] + 0.3
    weights = pipeline.aggregator.weights()
    assert weights["gap_hazard"] < weights["frequency"]


def test_drift_refits_next_day_and_records_mode_at_prediction(pipeline, monkeypatch):
    # Cổng đang mở trước kỳ 70: đủ bằng chứng kỹ năng dương.
    for _ in range(pipeline.config.trust_min_days):
        pipeline.safe_mode.observe(logloss=0.5, brier=0.17,
                                   baseline_logloss=0.55, baseline_brier=0.18)
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
    assert result.mode == "normal" and result.trust == 1.0
    assert pipeline.safe_mode.mode.value == "safe"
    assert "trôi lệch" in pipeline.safe_mode.reason
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
    assert pipeline.aggregator.updates == 0


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


def test_failed_tabular_refit_preserves_the_previous_model(monkeypatch):
    model = TabularBooster()
    incumbent = SimpleNamespace(predict_proba=lambda x: np.full((len(x), 2), 0.5))
    model._model, model.backend = incumbent, "incumbent"

    class Broken:
        def fit(self, x, y):
            raise RuntimeError("fit failed")

    monkeypatch.setattr(model, "_build", lambda: (Broken(), "candidate"))
    with pytest.raises(RuntimeError, match="fit failed"):
        model.fit(np.zeros((2, 1)), np.array([0, 1]))
    assert model._model is incumbent
    assert model.backend == "incumbent"
    np.testing.assert_array_equal(model.predict_proba(np.zeros((2, 1))), [0.5, 0.5])


@pytest.mark.parametrize("field", ["x", "y"])
def test_linear_fit_rejects_nonfinite_input_before_changing_weights(field):
    model = TemporalSequenceModel(lookback=1)
    model.backend = "linear"
    old = np.zeros((101, 100))
    model._linear_weights = old
    x, y = np.zeros((2, 1, 100)), np.zeros((2, 100))
    (x if field == "x" else y).flat[0] = np.nan
    with pytest.raises(ValueError, match="hữu hạn"):
        model._fit_linear(x, y)
    assert model._linear_weights is old


@pytest.mark.parametrize("lookback", [0, -1, 1.5, True])
def test_sequence_constructor_rejects_invalid_lookback_before_creating_samples(lookback):
    with pytest.raises(ValueError, match="lookback"):
        TemporalSequenceModel(lookback=lookback)


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
@pytest.mark.parametrize("kind", ["tabular", "temporal"])
def test_model_prediction_rejects_nonfinite_output_before_clipping(bad, kind):
    if kind == "tabular":
        model = TabularBooster()
        model._model = SimpleNamespace(predict_proba=lambda x: np.array([[0, bad]]))
        with pytest.raises(ValueError, match="hữu hạn"):
            model.predict_proba(np.zeros((1, 1)))
    else:
        model = TemporalSequenceModel(lookback=1)
        model.backend = "linear"
        model._linear_weights = np.full((101, 100), bad)
        with pytest.raises(ValueError, match="hữu hạn"):
            model.predict_sequence(np.ones((1, 100)))


def test_failed_pipeline_refit_keeps_incumbent_arm_and_feature_columns(pipeline, monkeypatch):
    pipeline.predict_day(70)
    incumbent = pipeline._fitted["tabular_boosting"]
    probabilities = pipeline.arm_probabilities(71)["tabular_boosting"]

    class Broken:
        def fit(self, x, y):
            raise RuntimeError("candidate failed")

    pipeline.arm_builders["tabular_boosting"] = Broken
    # Chọn cột khác để chắc chắn model cũ vẫn nhận đúng schema riêng của nó.
    monkeypatch.setattr(orchestration, "select_features", lambda *args, **kwargs:
                        SimpleNamespace(kept=["number"], describe=lambda: "changed"))
    pipeline._refit(71)
    assert pipeline._fitted.get("tabular_boosting") is incumbent
    np.testing.assert_array_equal(pipeline.arm_probabilities(71)["tabular_boosting"], probabilities)


def test_failed_initial_arm_is_not_scored_as_a_baseline_alias_and_signals_safe_mode(pipeline):
    class Broken:
        def fit(self, x, y):
            raise RuntimeError("candidate failed")

    pipeline.arm_builders["tabular_boosting"] = Broken
    result = pipeline.step(70)
    assert "tabular_boosting" not in result.arm_losses
    assert "tabular_boosting" not in result.arm_weights
    assert pipeline.safe_mode.is_safe
    assert "mô hình lỗi" in pipeline.safe_mode.reason


@pytest.mark.parametrize("stage", ["drift", "safe_mode"])
def test_step_failure_after_reward_rolls_back_for_retry(pipeline, monkeypatch, stage):
    issued = pipeline.predict_day(70)[0]
    before = _learning_state(pipeline)
    real_update = pipeline.drift.update
    real_observe = pipeline.safe_mode.observe
    safe_before = pipeline.safe_mode.state()

    def fail_after_mutation(error):
        real_update(error)
        raise RuntimeError("drift failed")

    def fail_safe_after_mutation(*args, **kwargs):
        real_observe(*args, **kwargs)
        raise RuntimeError("safe_mode failed")

    if stage == "drift":
        monkeypatch.setattr(pipeline.drift, "update", fail_after_mutation)
    else:
        monkeypatch.setattr(pipeline.drift, "update", lambda error: replace(real_update(error), drifted=True))
        monkeypatch.setattr(pipeline.safe_mode, "observe", fail_safe_after_mutation)
    with pytest.raises(RuntimeError, match=f"{stage} failed"):
        pipeline.step(70)
    assert _learning_state(pipeline) == before
    with pytest.raises(ValueError, match="chưa có kỳ"):
        pipeline.tracker.report()
    assert len(pipeline.drift._history) == 0
    assert pipeline._last_observed_day == -1
    assert not pipeline._force_refit
    assert pipeline.safe_mode.state() == safe_before
    monkeypatch.setattr(pipeline.drift, "update", real_update)
    monkeypatch.setattr(pipeline.safe_mode, "observe", real_observe)
    result = pipeline.step(70)
    np.testing.assert_array_equal(result.probabilities, issued)
    assert pipeline.tracker.report().days == 1
    assert pipeline.aggregator.updates == 1


def test_unavailable_arm_with_all_weight_falls_back_to_named_baseline(pipeline, monkeypatch):
    class Broken:
        def fit(self, x, y):
            raise RuntimeError("candidate failed")

    pipeline.arm_builders["tabular_boosting"] = Broken
    monkeypatch.setattr(pipeline.aggregator, "weights", lambda: {
        "baseline": 0.0, "frequency": 0.0, "gap_hazard": 0.0, "tabular_boosting": 1.0
    })
    probabilities, weights, per_arm = pipeline.predict_day(70)
    np.testing.assert_array_equal(probabilities, per_arm["baseline"])
    assert weights == {"baseline": 1.0}


def test_mixer_learns_the_summed_log_loss_of_each_arm(pipeline):
    """Trọng số là hậu nghiệm Bayes: loss của kỳ là log-loss CỘNG 100 con."""
    from research.ml_engine.aggregation import ExponentialWeights

    result = pipeline.step(70)
    reference = ExponentialWeights(pipeline.arm_builders, learning_rate=pipeline.config.learning_rate,
                                   share=pipeline.config.share)
    reference.update({name: 100 * loss for name, loss in result.arm_losses.items()})
    assert pipeline.aggregator.weights() == pytest.approx(reference.weights(), rel=1e-12)


def test_trust_and_drift_read_the_mixture_before_the_gate(pipeline, monkeypatch):
    """Đo trên dự báo đã qua cổng thì trust = 0 giữ dự báo bằng nền và cổng không bao giờ mở."""
    _, weights, per_arm = pipeline.predict_day(70)
    mixture = sum(weights[name] * per_arm[name] for name in weights)
    outcome = (pipeline.observations.counts[70] > 0).astype(float)
    expected = score_day(mixture, outcome)
    seen = {}
    real_update, real_observe = pipeline.drift.update, pipeline.safe_mode.observe

    def update(error):
        seen["drift"] = error
        return real_update(error)

    def observe(**kwargs):
        seen["trust"] = kwargs
        return real_observe(**kwargs)

    monkeypatch.setattr(pipeline.drift, "update", update)
    monkeypatch.setattr(pipeline.safe_mode, "observe", observe)
    pipeline.step(70)
    assert seen["drift"] == pytest.approx(expected.brier, rel=1e-12)
    assert seen["trust"]["logloss"] == pytest.approx(expected.logloss, rel=1e-12)
    assert seen["trust"]["baseline_logloss"] == pytest.approx(expected.baseline_logloss)


def test_arm_skill_is_paired_against_the_baseline_arm_on_shared_days():
    rows = [
        orchestration.DayResult(day_index=i, date=pd.Timestamp("2025-01-01"),
                                probabilities=np.full(100, BASELINE_RATE), top_k=[],
                                arm_weights={}, mode="safe", trust=0.0, drifted=False,
                                hits_in_top_k=0, arm_losses=losses)
        for i, losses in enumerate([
            {"baseline": 0.50, "tot": 0.45, "te": 0.60},
            {"baseline": 0.60, "tot": 0.57},
            {"baseline": 0.55, "tot": 0.53, "te": 0.70},
        ])
    ]
    skill = {row["arm"]: row for row in orchestration.arm_skill(rows)}
    assert skill["tot"]["days"] == 3
    assert skill["tot"]["logloss_skill"] == pytest.approx((0.05 + 0.03 + 0.02) / 3 / 0.55)
    gain = np.array([0.05, 0.03, 0.02])
    assert skill["tot"]["paired_t"] == pytest.approx(gain.mean() / (gain.std(ddof=1) / np.sqrt(3)))
    # "te" chỉ so trên hai kỳ nó có mặt, với nền của đúng hai kỳ ấy.
    assert skill["te"]["days"] == 2
    assert skill["te"]["logloss_skill"] == pytest.approx(-(0.10 + 0.15) / 2 / 0.525)
    assert [row["arm"] for row in orchestration.arm_skill(rows)][0] == "tot"


def _aggregation_benchmark():
    import importlib.util
    from pathlib import Path

    path = (Path(__file__).resolve().parents[2] / "scripts" / "research"
            / "benchmark_ml_engine_aggregation.py")
    spec = importlib.util.spec_from_file_location("benchmark_ml_engine_aggregation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_aggregation_benchmark_uses_the_promotion_gate_error_bar():
    """Phép đo thay bandit chấm z bằng đúng sai số của cổng đề bạt production."""
    from forecast import online_learning

    rng = np.random.default_rng(5)
    gain = rng.normal(0.001, 0.01, 200) + np.repeat(rng.normal(0, 0.01, 29), 7)[:200]
    measured = _aggregation_benchmark().paired(gain)
    gate = online_learning._gain_stats(gain)
    assert measured["se"] == pytest.approx(gate["se"], rel=1e-12)
    assert measured["z"] == pytest.approx(gate["mean"] / gate["se"], rel=1e-12)
