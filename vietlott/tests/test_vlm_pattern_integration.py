"""Chuyên gia mẫu hình phải nhân quả và không nhận bằng chứng của chính sách cũ."""
from copy import deepcopy
import gzip
import json

import numpy as np
import pytest

from tests.test_vlm_forecast_pipeline import mega_series
from tests.test_multi_agent_migration import _old_issue
from vietlott_engine.core.config import Settings
from vlm.forecast.pipeline import MLConfig, MLForecaster
from vlm.forecast.service import model_config, refresh_snapshot
from vietlott_engine.forecast.data import CONFIGS
from vietlott_engine.core.products import ProductCode
from vlm.forecast.pipeline import MLComponent


def config(**kwargs):
    return MLConfig(bootstrap=32, warmup=1, backends=(), search_nodes=1, patterns=True, **kwargs)


def test_pattern_configuration_is_explicit_and_service_propagates_it():
    assert MLConfig().patterns is False
    assert Settings(_env_file=None).ml_patterns is False
    assert model_config(Settings(_env_file=None, ml_patterns=True)).patterns is True


def test_pattern_experts_are_scored_separately_and_prediction_is_read_only():
    model = MLForecaster('mega645', config())
    series = mega_series(12)
    model.update(series.head(8))
    component = model.components['main']
    assert set(component.patterns.names) <= set(component.names)
    assert component.patterns.seen == 8
    before = deepcopy(model.to_dict())
    law = component.law('2026-02-01')
    assert len(law.mixture) == len(component.names)
    assert law.marginals().sum() == pytest.approx(6)
    assert model.to_dict() == before
    previous = component.expert_nll.copy()
    row = series.obs['main']['X'][8]
    expected = -component.law(str(series.dates[8]), next_id=9).expert_log_likelihood(row)
    model.update(series.head(9))
    np.testing.assert_allclose(model.components['main'].expert_nll-previous, expected)
    assert model.components['main'].patterns.seen == 9


def test_pattern_checkpoint_reload_and_chunking_match(tmp_path):
    series = mega_series(14)
    whole = MLForecaster('mega645', config(multi_agent=True))
    whole.update(series)
    chunk = MLForecaster('mega645', config(multi_agent=True))
    chunk.update(series.head(7))
    path = tmp_path / 'state.json.gz'
    chunk.save(path)
    restored = MLForecaster.load(path)
    restored.update(series)
    assert restored.to_dict() == whole.to_dict()
    broken = restored.to_dict()
    broken['components']['main']['patterns']['seen'] -= 1
    path.write_bytes(gzip.compress(json.dumps(broken).encode()))
    with pytest.raises(ValueError):
        MLForecaster.load(path)


def test_pre_pattern_checkpoint_remains_loadable(tmp_path):
    old = MLForecaster('mega645', MLConfig(backends=()))
    old.update(mega_series(3))
    state = old.to_dict()
    state['version'] = 4
    state['config'].pop('patterns', None)
    state['components']['main'].pop('patterns', None)
    path = tmp_path / 'old.json.gz'
    path.write_bytes(gzip.compress(json.dumps(state).encode()))
    restored = MLForecaster.load(path)
    assert restored.config.patterns is False
    assert restored.last_id == 3


def test_pattern_digit_counts_are_normalized_by_draw_without_invalid_laws():
    component = MLComponent(CONFIGS[ProductCode.MAX3D].components['digits'], config())
    row = np.tile([4., 3., 3., 2., 2., 2., 1., 1., 1., 1.], 3)
    for draw_id in range(1, 6):
        component.observe(row, draw_id, '2026-01-02')
    prediction = component.law().marginals().reshape(3, 10)
    np.testing.assert_allclose(prediction.sum(axis=1), 1.)
    assert component.patterns.seen == 5
    assert component.patterns.predict()[0, 0] > component.features.base


def test_pattern_learning_failure_rolls_back_every_component(monkeypatch):
    from vlm.forecast.patterns import PatternExperts

    model = MLForecaster('mega645', config())
    series = mega_series(3)
    model.update(series.head(2))
    previous = deepcopy(model.to_dict())

    def fail(*args, **kwargs):
        raise ValueError('Lỗi học tổng hợp')

    monkeypatch.setattr(PatternExperts, 'observe', fail)
    with pytest.raises(ValueError, match='Lỗi học tổng hợp'):
        model.update(series)
    assert model.to_dict() == previous


def test_pattern_upgrade_preserves_issued_law_and_scores_it_without_new_policy_credit(tmp_path):
    series, _, event = _old_issue(tmp_path)
    original = (tmp_path / 'ml-ledger.jsonl').read_bytes()
    upgraded, _, _ = refresh_snapshot('mega645', series.head(1), tmp_path, config=config(), issue=False)
    assert upgraded.config.patterns is True
    assert upgraded.pending == event['pending']
    assert upgraded.pending_valid()
    assert upgraded.live_scored == 0
    updated, _, _ = refresh_snapshot('mega645', series, tmp_path, config=config(), issue=False)
    events = [json.loads(line) for line in (tmp_path / 'ml-ledger.jsonl').read_text().splitlines()]
    assert (tmp_path / 'ml-ledger.jsonl').read_bytes().startswith(original)
    assert events[-1]['event'] == 'score' and events[-1]['target_id'] == 2
    assert events[-1]['counts_toward_live'] is False
    assert updated.live_scored == 0
    assert updated.components['main'].patterns.seen == 2


def test_pattern_upgrade_scores_old_result_then_starts_new_evidence(tmp_path):
    series, _, _ = _old_issue(tmp_path)
    upgraded, _, _ = refresh_snapshot('mega645', series, tmp_path, config=config(), issue=False)
    assert upgraded.config.patterns is True
    assert upgraded.live_scored == 0
    assert upgraded.components['main'].patterns.seen == 2
    assert upgraded.issue('2026-01-07T18:00:00+07:00', '2026-01-04T19:00:00+07:00')
    future = mega_series(3)
    future.dates[:2] = series.dates
    future.dates[2] = '2026-01-07'
    upgraded.update(future)
    assert upgraded.live_scored == 1
    assert upgraded.last_live_scores[0]['counts_toward_live'] is True


def test_multi_agent_upgrade_with_patterns_does_not_credit_the_old_law(tmp_path):
    series = mega_series(2)
    series.dates[-1] = '2026-01-04'
    previous = MLForecaster('mega645', config())
    previous.update(series.head(1))
    assert previous.issue('2026-01-04T18:00:00+07:00', '2026-01-04T17:00:00+07:00')
    previous.save(tmp_path / 'ml' / 'mega645.json.gz')
    from vlm.forecast.service import _event
    _event(tmp_path, {'event':'issue', 'product':'mega645', 'target_id':2,
                     'history_sha256':previous.prefix_hash, 'pending':deepcopy(previous.pending)})
    upgraded, _, _ = refresh_snapshot('mega645', series.head(1), tmp_path,
                                     config=config(multi_agent=True), issue=False)
    assert upgraded.pending == previous.pending
    upgraded, _, _ = refresh_snapshot('mega645', series, tmp_path,
                                     config=config(multi_agent=True), issue=False)
    assert upgraded.last_live_scores[0]['counts_toward_live'] is False
    assert upgraded.live_scored == 0


@pytest.mark.parametrize('result_available', [False, True])
def test_explicit_pattern_refit_keeps_or_scores_existing_issue(tmp_path, result_available):
    series, _, event = _old_issue(tmp_path)
    original = (tmp_path / 'ml-ledger.jsonl').read_bytes()
    current = series if result_available else series.head(1)
    upgraded, _, _ = refresh_snapshot('mega645', current, tmp_path, config=config(),
                                     refit=True, require_config_match=True, issue=False)
    assert upgraded.config.patterns is True
    assert upgraded.live_scored == 0
    events = [json.loads(line) for line in (tmp_path / 'ml-ledger.jsonl').read_text().splitlines()]
    assert (tmp_path / 'ml-ledger.jsonl').read_bytes().startswith(original)
    if result_available:
        assert events[-1]['event'] == 'score' and events[-1]['target_id'] == 2
        assert upgraded.pending is None
    else:
        assert upgraded.pending == event['pending']
        assert upgraded.pending_valid()
        assert len(events) == 1


def _strip_pattern_keys(data: dict) -> dict:
    """Checkpoint v5 do production ghi TRƯỚC khi có challenger mẫu hình: cấu hình và component không có khoá
    ``patterns``."""
    data = deepcopy(data)
    data['version'] = 5  # bản production ghi từ 31-10-2026; bật challenger không được buộc tăng phiên bản
    data['config'].pop('patterns', None)
    for component in data['components'].values():
        component.pop('patterns', None)
    return data


@pytest.mark.parametrize('product', ['max3d', 'mega645'])
def test_a_production_v5_checkpoint_without_pattern_keys_loads_and_publishes_the_same_law(tmp_path, product):
    """Gộp với chuyên gia hỗn hợp Bayes (checkpoint v5, 31-10-2026): bật tắt mẫu hình là khoá TUỲ CHỌN trong
    cùng phiên bản. Tắt thì checkpoint production đã có phải nạp nguyên vẹn và cho đúng từng bit luật cũ —
    không học lại, không mất bằng chứng live."""
    from tests.test_vlm_bayes_expert import NOW, max3d_series
    if product == 'max3d':
        series = max3d_series(60, six=0.13)
    else:
        series = mega_series(40)
    production = MLConfig(bootstrap=40, warmup=8, tree_every=64, tree_buffer=16, search_nodes=20, multi_agent=True)
    model = MLForecaster(product, production)
    model.update(series, now=NOW)
    path = tmp_path / f'{product}.json.gz'
    path.write_bytes(gzip.compress(json.dumps(_strip_pattern_keys(model.to_dict())).encode()))
    restored = MLForecaster.load(path)
    assert restored.config == production and not restored.config.patterns
    for name, component in model.components.items():
        assert restored.components[name].names == component.names
        assert restored.components[name].law().to_dict() == component.law().to_dict()
    assert restored.to_dict()['components'] == model.to_dict()['components']


def test_digit_components_carry_the_bayes_expert_and_the_pattern_experts_in_the_same_order_they_predict():
    """Tên chuyên gia và hàng xác suất phải cùng thứ tự (cơ sở → bayes → mẫu hình): lệch thì trọng số của
    chuyên gia này chấm điểm cho chuyên gia khác mà không lỗi nào báo."""
    from tests.test_vlm_bayes_expert import NOW, max3d_series
    from vlm.forecast.bayes_expert import NAME as BAYES_NAME
    model = MLForecaster('max3d', MLConfig(bootstrap=40, warmup=8, tree_every=64, tree_buffer=16, search_nodes=20,
                                           patterns=True))
    model.update(max3d_series(40, six=0.13), now=NOW)
    component = model.components['digits']
    base = component.base_expert_count
    assert component.names[base] == BAYES_NAME
    assert component.names[base + 1:base + 1 + len(component.patterns.names)] == list(component.patterns.names)
    assert len(component.law().mixture) == len(component.names)
    assert component.expert_nll.shape == (len(component.names),) and np.isfinite(component.expert_nll).all()
