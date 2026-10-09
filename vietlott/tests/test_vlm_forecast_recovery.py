"""Lỗi số học hoặc fit thất bại không được phá model tốt hay chấm kỳ hai lần."""
from __future__ import annotations

import copy
import gzip
import json

import numpy as np
import pytest
from sklearn.ensemble import RandomForestRegressor

from vlm.forecast.models import GRU, OnlineLogistic, TreeExpert
from vlm.forecast.pipeline import MLConfig, MLForecaster
from tests.test_vlm_forecast_pipeline import mega_series


@pytest.mark.parametrize("bad", ["nan_x", "inf_y", "empty", "bad_label"])
def test_logistic_rejects_bad_training_batch_without_mutation(bad: str) -> None:
    model = OnlineLogistic(2, .5)
    x = np.array([[0., 1.], [1., 0.]])
    y = np.array([0., 1.])
    if bad == "nan_x":
        x[0, 0] = np.nan
    elif bad == "inf_y":
        y[0] = np.inf
    elif bad == "empty":
        x, y = x[:0], y[:0]
    else:
        y[0] = 1.5
    before = model.to_dict()
    with pytest.raises(ValueError):
        model.learn(x, y)
    assert model.to_dict() == before


def test_gru_rejects_empty_nodes_without_optimizer_step() -> None:
    model = GRU(2, hidden=2)
    before = model.to_dict()
    with pytest.raises(ValueError):
        model.learn(np.zeros((2, 0, 2)), np.zeros(0))
    assert model.to_dict() == before


def test_gru_nonfinite_loss_does_not_commit_optimizer() -> None:
    model = GRU(2, hidden=2)
    model.params['Wo'][:] = 1e200
    before = model.to_dict()
    with pytest.raises(FloatingPointError):
        model.learn(np.ones((2, 3, 2)), np.array([0., 1., 0.]))
    assert model.to_dict() == before


def test_gru_large_finite_gradient_is_clipped_without_disappearing(monkeypatch) -> None:
    model = GRU(2, hidden=2)
    gradients = {key: np.full_like(value, 1e200) for key, value in model.params.items()}
    monkeypatch.setattr(model, 'loss_and_gradients', lambda x, y: (1., gradients))
    model.learn(np.ones((2, 3, 2)), np.zeros(3))
    assert model.params['bo'][0] < 0
    assert model.steps == 1
    assert all(np.isfinite(value).all() for value in model.first.values())


def test_failed_tree_refit_retains_last_working_predictions(monkeypatch) -> None:
    model = TreeExpert('rf', .5)
    x = np.arange(80, dtype=float).reshape(40, 2)
    y = np.tile([0., 1.], 20)
    model.fit(x, y)
    expected = model.predict(x)
    before = copy.deepcopy(model.to_dict())
    def fail(*args, **kwargs):
        raise MemoryError('injected backend OOM')
    monkeypatch.setattr(RandomForestRegressor, 'fit', fail)
    with pytest.raises(MemoryError):
        model.fit(x, y)
    assert model.to_dict() == before
    np.testing.assert_array_equal(model.predict(x), expected)


def test_infinite_backend_predictions_are_rejected_before_clipping() -> None:
    class BadBooster:
        def predict(self, x):
            return np.full(len(x), np.inf)
    model = TreeExpert('rf', .5)
    model.booster = BadBooster()
    with pytest.raises(FloatingPointError):
        model.predict(np.zeros((3, 2)))


@pytest.mark.parametrize("scale", [0, -1, 2, np.nan])
def test_optimizer_rate_scale_checkpoint_is_validated(scale: float) -> None:
    data = OnlineLogistic(2, .5).to_dict()
    data['rate_scale'] = scale
    with pytest.raises(ValueError):
        OnlineLogistic.from_dict(data)


def test_impossible_live_evidence_is_rejected_on_restore(tmp_path) -> None:
    model = MLForecaster('mega645', MLConfig(bootstrap=8, search_nodes=1))
    model.update(mega_series(2))
    data = model.to_dict()
    data.update(live_scored=100, live_log_e=20., max_live_log_e=20., live_recent=[.2] * 100)
    path = tmp_path / 'bad.json.gz'
    path.write_bytes(gzip.compress(json.dumps(data).encode()))
    with pytest.raises(ValueError):
        MLForecaster.load(path)


def test_retry_reduces_work_and_stops_at_its_limit() -> None:
    from vlm.forecast.recovery import auto_patch_and_retry
    workload = [16]
    attempted = []
    def reduce_work(error, attempt):
        workload[0] //= 2
        return True
    @auto_patch_and_retry(on_error=reduce_work, max_retries=1)
    def fit():
        attempted.append(workload[0])
        if workload[0] > 8:
            raise MemoryError('insufficient memory')
        return workload[0]
    assert fit() == 8
    assert attempted == [16, 8]
    workload[0], attempted[:] = 64, []
    with pytest.raises(MemoryError):
        fit()
    assert attempted == [64, 32]


def test_retry_does_not_hide_invalid_input() -> None:
    from vlm.forecast.recovery import auto_patch_and_retry
    failures = []
    @auto_patch_and_retry(on_error=lambda error, attempt: failures.append(error) or True)
    def invalid():
        raise ValueError('wrong target shape')
    with pytest.raises(ValueError, match='target'):
        invalid()
    assert not failures


def test_running_statistics_match_numpy_and_are_causal() -> None:
    from vlm.forecast.adaptation import RunningFeatureStats
    first = np.array([[1., 2.], [3., 4.]])
    future = np.array([[5., 6.], [7., 8.]])
    stats = RunningFeatureStats(2)
    before = stats.normalize(first)
    np.testing.assert_array_equal(before, first)
    stats.update(first)
    checkpoint = stats.to_dict()
    restored = RunningFeatureStats.from_dict(checkpoint, features=2)
    np.testing.assert_array_equal(stats.normalize(future), restored.normalize(future))
    stats.update(future)
    np.testing.assert_allclose(stats.mean, np.vstack([first, future]).mean(axis=0))
    np.testing.assert_allclose(stats.std, np.vstack([first, future]).std(axis=0))
    assert restored.to_dict() == checkpoint


def test_drift_monitor_detects_a_regime_change_without_retaining_batches() -> None:
    from vlm.forecast.adaptation import RunningFeatureStats
    stats = RunningFeatureStats(2)
    for _ in range(32):
        stats.update(np.zeros((4, 2)))
    assert not stats.report()['drift_alert']
    for _ in range(8):
        stats.update(np.full((4, 2), 5.))
    assert stats.report()['drift_alert']
    assert stats.samples == 160 and stats.updates == 40
    assert not any(isinstance(value, list) for value in vars(stats).values())


def test_statistics_failed_update_is_atomic() -> None:
    from vlm.forecast.adaptation import RunningFeatureStats
    stats = RunningFeatureStats(2)
    stats.update(np.ones((3, 2)))
    before = stats.to_dict()
    with pytest.raises(ValueError):
        stats.update(np.full((3, 2), np.nan))
    assert stats.to_dict() == before


def test_failed_prediction_falls_back_to_fair_before_scoring(monkeypatch) -> None:
    model = MLForecaster('mega645', MLConfig(bootstrap=8, search_nodes=1))
    component = model.components['main']
    monkeypatch.setattr(component.logistics[0], 'predict', lambda x: np.where(np.arange(len(x)) == 0, np.inf, .2))
    law = component.law()
    np.testing.assert_allclose(law.values[1], np.ones(45), rtol=0, atol=1e-14)
    assert component.metrics()['recovery']['counts']['prediction_fallback'] == 1
    assert np.isfinite(law.marginals()).all()


def test_nonfinite_learning_skips_only_failed_expert_and_backs_off(monkeypatch) -> None:
    model = MLForecaster('mega645', MLConfig(bootstrap=8, search_nodes=1))
    component = model.components['main']
    before = copy.deepcopy(component.gru.to_dict()['params'])
    gradients = {key: np.zeros_like(value) for key, value in component.gru.params.items()}
    monkeypatch.setattr(component.gru, 'loss_and_gradients', lambda x, y: (np.nan, gradients))
    model.update(mega_series(1))
    component = model.components['main']
    assert component.gru.to_dict()['params'] == before
    assert component.gru.steps == 0 and component.gru.rate_scale == .5
    assert component.features.seen == 1 and component.logistics[0].acc.any()
    assert component.metrics()['recovery']['counts']['training_skip'] == 1


def test_tree_oom_retry_reduces_replay_and_retains_last_model(monkeypatch) -> None:
    model = MLForecaster('mega645', MLConfig(bootstrap=8, warmup=1, tree_every=1, tree_buffer=8, search_nodes=1))
    model.update(mega_series(4))
    before = copy.deepcopy(model.components['main'].trees[0].to_dict())
    sizes = []
    def oom(self, x, y):
        sizes.append(len(x))
        raise MemoryError('injected OOM')
    monkeypatch.setattr(TreeExpert, 'fit', oom)
    assert model.update(mega_series(5)) == 1
    component = model.components['main']
    assert len(sizes) == 2 and sizes[1] < sizes[0]
    assert component.trees[0].to_dict() == before
    assert component.metrics()['recovery']['counts']['tree_retry'] == 1
    assert component.metrics()['recovery']['counts']['training_skip'] == 1


def test_draw_failure_rolls_back_pending_live_score_and_every_component(monkeypatch) -> None:
    from vietlott_engine.core.products import ProductCode
    from vietlott_engine.forecast.data import DigitSpec, Series
    from vlm.forecast.features import FeatureState
    x, special = np.zeros((2, 35), bool), np.zeros((2, 1, 12), int)
    x[:, :5], special[:, :, 0] = True, 1
    series = Series(ProductCode.LOTTO_535, np.arange(1, 3), np.full(2, '2026-01-02'),
                    {'main':{'X':x, 'bonus':np.zeros(2, int)}, 'special':{'C':special}})
    model = MLForecaster('lotto535', MLConfig(bootstrap=8, search_nodes=1))
    model.update(series.head(1))
    assert model.issue('2026-01-02T21:00:00+07:00', '2026-01-02T14:00:00+07:00')
    before = copy.deepcopy(model.to_dict())
    original = FeatureState.observe
    def fail_special(self, *args, **kwargs):
        if isinstance(self.spec, DigitSpec):
            raise RuntimeError('injected unexpected downstream failure')
        return original(self, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(FeatureState, 'observe', fail_special)
        with pytest.raises(RuntimeError):
            model.update(series)
    assert model.to_dict() == before
    assert model.update(series) == 1
    assert model.live_scored == 1 and model.learned == 2


def test_partial_update_can_resume_without_retraining_the_committed_prefix(monkeypatch) -> None:
    from vlm.forecast.features import FeatureState
    model = MLForecaster('mega645', MLConfig(bootstrap=8, search_nodes=1))
    original = FeatureState.observe
    def fail_third(self, row, draw_id, draw_date):
        if draw_id == 3:
            raise RuntimeError('injected unexpected third draw failure')
        return original(self, row, draw_id, draw_date)
    with monkeypatch.context() as patch:
        patch.setattr(FeatureState, 'observe', fail_third)
        with pytest.raises(RuntimeError):
            model.update(mega_series(3))
    assert model.learned == 2 and model.last_id == 2
    assert model.update(mega_series(3)) == 1
    assert model.learned == 3 and 'history_revised' not in model.warnings


def test_adaptive_challenger_is_optional_causal_and_reloadable(tmp_path) -> None:
    default = MLForecaster('mega645')
    assert 'adaptive_logistic' not in default.components['main'].names
    config = MLConfig(bootstrap=16, warmup=4, tree_every=8, tree_buffer=8, search_nodes=1, adaptive=True)
    whole, split = MLForecaster('mega645', config), MLForecaster('mega645', config)
    series = mega_series(12)
    whole.update(series)
    split.update(series.head(6))
    path = tmp_path / 'adaptive.json.gz'
    split.save(path)
    split = MLForecaster.load(path)
    assert split.update(series) == 6
    np.testing.assert_array_equal(whole.components['main'].law().marginals(), split.components['main'].law().marginals())
    component = split.components['main']
    assert component.metrics()['feature_statistics']['updates'] == 12
    assert component.metrics()['feature_statistics']['samples'] == 12 * 45
    assert not split.confidence()['validated']


def test_restored_live_success_without_issued_ledger_is_not_certified(tmp_path) -> None:
    from vlm.forecast.service import refresh_snapshot
    series = mega_series(102)
    model = MLForecaster('mega645', MLConfig(bootstrap=128, tree_every=128, backends=(), search_nodes=1))
    model.update(series)
    model.live_scored = 100
    model.live_log_e = model.max_live_log_e = 20.
    model.live_recent = [.2] * 100
    model.save(tmp_path / 'ml' / 'mega645.json.gz')
    restored, learned, summary = refresh_snapshot('mega645', series, tmp_path, issue=False)
    assert learned == 0 and not summary['validated']
    assert restored.live_scored == 0
    assert 'live_evidence_unverified' in restored.warnings


def test_real_issued_ledger_evidence_survives_restart(tmp_path) -> None:
    from vlm.forecast.service import _event, refresh_snapshot
    series = mega_series(2)
    series.dates[-1] = '2026-01-04'
    model = MLForecaster('mega645', MLConfig(bootstrap=8, backends=(), search_nodes=1))
    model.update(series.head(1))
    assert model.issue('2026-01-04T18:00:00+07:00', '2026-01-04T17:00:00+07:00')
    _event(tmp_path, {'event':'issue', 'product':'mega645', 'target_id':2,
                     'history_sha256':model.prefix_hash, 'pending':model.pending})
    model.save(tmp_path / 'ml' / 'mega645.json.gz')
    model, _, _ = refresh_snapshot('mega645', series, tmp_path, issue=False)
    assert model.live_scored == 1
    gain = model.live_log_e
    model, learned, _ = refresh_snapshot('mega645', series, tmp_path, issue=False)
    assert learned == 0 and model.live_scored == 1 and model.live_log_e == gain
    assert 'live_evidence_unverified' not in model.warnings


def test_checkpoint_spec_is_checked_before_feature_allocation(tmp_path, monkeypatch) -> None:
    from vlm.forecast.features import FeatureState
    model = MLForecaster('mega645', MLConfig(bootstrap=8, backends=(), search_nodes=1))
    model.update(mega_series(1))
    data = model.to_dict()
    data['components']['main']['features']['spec']['n'] = 80
    path = tmp_path / 'wrong-spec.json.gz'
    path.write_bytes(gzip.compress(json.dumps(data).encode()))
    original = FeatureState.__init__
    def protected(self, spec):
        if spec.n != 45:
            raise RuntimeError('allocation with unexpected checkpoint dimensions')
        original(self, spec)
    monkeypatch.setattr(FeatureState, '__init__', protected)
    with pytest.raises(ValueError):
        MLForecaster.load(path)


def test_old_version_two_checkpoint_starts_new_monitor_without_changing_model(tmp_path) -> None:
    model = MLForecaster('mega645', MLConfig(bootstrap=8, backends=(), search_nodes=1))
    model.update(mega_series(3))
    data = model.to_dict()
    data['config'].pop('adaptive')
    for component in data['components'].values():
        component.pop('statistics')
        component.pop('recovery')
        for expert in [*component['logistics'], component['gru']]:
            expert.pop('rate_scale')
    path = tmp_path / 'old.json.gz'
    path.write_bytes(gzip.compress(json.dumps(data).encode()))
    restored = MLForecaster.load(path)
    np.testing.assert_array_equal(model.components['main'].law().marginals(), restored.components['main'].law().marginals())
    assert restored.components['main'].statistics.updates == 0
    assert restored.update(mega_series(4)) == 1


def test_cli_can_benchmark_adaptive_challenger_without_saving_state(tmp_path, capsys) -> None:
    from vlm.forecast.cli import main
    path = tmp_path / 'history.jsonl'
    path.write_text(json.dumps({'id':1, 'date':'2026-01-02', 'result':[1, 2, 3, 4, 5, 6]}) + '\n')
    output = tmp_path / 'state'
    assert main(['benchmark', '--product','mega645', '--input',str(path), '--dir',str(output),
                 '--top-n','1', '--adaptive']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['config']['adaptive'] is True
    assert 'adaptive_logistic' in report['components'][0]['expert_weights']
    assert not output.exists() and not report['confidence']['validated']


def test_recovery_events_are_bounded_and_checkpointed(monkeypatch) -> None:
    from vietlott_engine.forecast.data import SetSpec
    from vlm.forecast.pipeline import MLComponent
    config = MLConfig(backends=(), search_nodes=1)
    component = MLComponent(SetSpec(45, 6), config)
    monkeypatch.setattr(component.logistics[0], 'predict', lambda x: np.full((len(x), 1), .5))
    for _ in range(40):
        component.law()
    data = component.to_dict()
    restored = MLComponent.from_dict(SetSpec(45, 6), config, data)
    recovery = restored.metrics()['recovery']
    assert recovery['counts']['prediction_fallback'] == 40
    assert len(recovery['events']) == 32


@pytest.mark.parametrize('field,value', [('m2', [-1., 0.]), ('samples', True), ('drift_score', np.nan)])
def test_corrupt_statistics_are_rejected(field, value) -> None:
    from vlm.forecast.adaptation import RunningFeatureStats
    data = RunningFeatureStats(2).to_dict()
    data[field] = value
    with pytest.raises(ValueError):
        RunningFeatureStats.from_dict(data, features=2)


def test_backend_memory_error_subclass_can_be_checkpointed() -> None:
    from vlm.forecast.recovery import RecoveryLog
    class BackendAllocationFailure(MemoryError):
        pass
    log = RecoveryLog()
    log.record('training_skip', 'gru', 1, BackendAllocationFailure())
    restored = RecoveryLog.from_dict(log.to_dict(), names=['gru'])
    assert restored.counts['training_skip'] == 1
    assert restored.events[0]['reason'] == 'MemoryError'


@pytest.mark.parametrize('bad', ['nan_value', 'cycle'])
def test_invalid_returned_rf_retains_working_checkpoint(monkeypatch, bad: str) -> None:
    from types import SimpleNamespace
    model = TreeExpert('rf', .5)
    x = np.arange(80, dtype=float).reshape(40, 2)
    y = np.tile([0., 1.], 20)
    model.fit(x, y)
    before, predictions = copy.deepcopy(model.to_dict()), model.predict(x)
    tree = SimpleNamespace(children_left=np.array([-1]), children_right=np.array([-1]),
        feature=np.array([-2]), threshold=np.array([-2.]), value=np.array([[[.5]]]))
    if bad == 'nan_value':
        tree.value[:] = np.nan
    else:
        tree.children_left[:], tree.children_right[:], tree.feature[:] = 0, 0, 0
    forest = SimpleNamespace(estimators_=[SimpleNamespace(tree_=tree)])
    monkeypatch.setattr(RandomForestRegressor, 'fit', lambda *args, **kwargs: forest)
    with pytest.raises(FloatingPointError):
        model.fit(x, y)
    assert model.to_dict() == before
    restored = TreeExpert.from_dict(json.loads(json.dumps(before, allow_nan=False)), features=2)
    np.testing.assert_array_equal(restored.predict(x), predictions)


@pytest.mark.parametrize('bad', ['nan', 'shape', 'range'])
def test_invalid_returned_booster_retains_working_model(monkeypatch, bad: str) -> None:
    import sys
    from importlib.machinery import ModuleSpec
    from types import ModuleType
    xgb = ModuleType('xgboost')
    xgb.__spec__ = ModuleSpec('xgboost', loader=None)
    class Matrix:
        def __init__(self, array, label=None):
            self.array = array
        def num_row(self):
            return len(self.array)
    xgb.DMatrix = Matrix
    monkeypatch.setitem(sys.modules, 'xgboost', xgb)
    model = TreeExpert('xgb', .5)
    x, y = np.ones((8, 2)), np.tile([0., 1.], 4)
    model.fit(x, np.zeros(8))
    before = model.to_dict()
    class InvalidBooster:
        def predict(self, matrix):
            count = matrix.num_row()
            return np.zeros((count, 1)) if bad == 'shape' else np.full(count, np.nan if bad == 'nan' else 2.)
    monkeypatch.setattr(xgb, 'train', lambda *args, **kwargs: InvalidBooster(), raising=False)
    with pytest.raises(FloatingPointError):
        model.fit(x, y)
    assert model.to_dict() == before
    np.testing.assert_array_equal(model.predict(x), np.full(8, .001))


@pytest.mark.parametrize('problem', ['gap', 'old_date_reversal'])
def test_partial_failure_preserves_audit_metadata_on_reload(tmp_path, monkeypatch, problem: str) -> None:
    from vlm.forecast.features import FeatureState
    series = mega_series(4)
    bootstrap = 8
    if problem == 'gap':
        series.draw_ids = np.array([1, 3, 4, 5])
    else:
        series.dates[:] = ['2026-01-02', '2026-01-01', '2026-01-02', '2026-01-02']
        bootstrap = 2  # Đảo ngày nằm ngoài cửa sổ huấn luyện, vẫn phải được báo cáo.
    model = MLForecaster('mega645', MLConfig(bootstrap=bootstrap, backends=(), search_nodes=1))
    original = FeatureState.observe
    def fail_last(self, row, draw_id, draw_date):
        if draw_id == int(series.draw_ids[-1]):
            raise RuntimeError('injected late update failure')
        return original(self, row, draw_id, draw_date)
    with monkeypatch.context() as patch:
        patch.setattr(FeatureState, 'observe', fail_last)
        with pytest.raises(RuntimeError):
            model.update(series)
    path = tmp_path / 'partial.json.gz'
    model.save(path)
    restored = MLForecaster.load(path)
    report = restored.report(1)
    assert report['historical_draws_available'] == 4
    if problem == 'gap':
        assert report['missing_ids_inside_range'] == 1
    else:
        assert report['date_anomalies'] == 1
        assert 'history_date_anomalies' in report['warnings']
    before_learned = restored.learned
    assert restored.update(series) == 1 and restored.learned == before_learned + 1
    assert 'history_revised' not in restored.warnings
