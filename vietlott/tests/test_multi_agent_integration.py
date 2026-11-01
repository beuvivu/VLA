"""Bộ đa thuật toán phải tham gia luật thật và giữ nguyên thứ tự chấm trước học."""
from copy import deepcopy
from itertools import combinations

import numpy as np
import pytest

from vietlott_engine.forecast.data import DigitSpec, SetSpec
from vlm.forecast.pipeline import MLComponent, MLConfig, MLForecaster
from tests.test_vlm_forecast_pipeline import mega_series


def test_multi_agent_is_available_and_changes_the_actual_set_law():
    config = MLConfig(backends=(), multi_agent=True, warmup=2, bootstrap=20, search_nodes=1)
    component = MLComponent(SetSpec(n=5, k=2), config)
    assert component.multi_agent is not None
    assert 'multi_agent' in component.names
    for t in range(12):
        component.observe(np.array([1, 1, 0, 0, 0]), t + 1, '2026-01-02')
    law = component.law()
    assert len(law.mixture) == len(component.names) + 3
    assert sum(law.probability(list(s)) for s in combinations(range(1, 6), 2)) == pytest.approx(1)
    assert law.marginals().sum() == pytest.approx(2)
    diagnostics = component.metrics()['multi_agent']
    assert diagnostics['observations'] == 12
    assert sum(diagnostics['weights'].values()) == pytest.approx(1)
    assert diagnostics['evaluation'] == 'retrospective_prequential_exploratory'


def test_nested_mixture_likelihood_matches_its_parent_group_score():
    from vlm.forecast.multi_agent import MultiAgentExpert
    expert = MultiAgentExpert(5, 2, seed=7)
    for _ in range(4):
        expert.learn(np.array([1, 1, 0, 0, 0]))
    values, weights = expert.distribution()
    from vlm.forecast.distribution import Law
    law = Law(SetSpec(n=5, k=2), values, weights)
    row = np.array([1, 0, 1, 0, 0])
    assert expert.group_log_likelihood(law.expert_log_likelihood(row)) == pytest.approx(law.log_likelihood(row))


def test_multi_agent_checkpoint_replay_and_gate_remain_honest(tmp_path):
    cfg = MLConfig(backends=(), multi_agent=True, bootstrap=16, warmup=2, search_nodes=1)
    series = mega_series(16)
    whole, split = MLForecaster('mega645', cfg), MLForecaster('mega645', cfg)
    whole.update(series)
    split.update(series.head(8))
    path = tmp_path / 'ml.json.gz'
    split.save(path)
    split = MLForecaster.load(path)
    split.update(series)
    assert whole.components['main'].multi_agent.to_dict() == split.components['main'].multi_agent.to_dict()
    np.testing.assert_array_equal(whole.components['main'].law().marginals(), split.components['main'].law().marginals())
    assert not split.report()['confidence']['validated']
    assert split.report()['components'][0]['metrics']['multi_agent']['observations'] == 16


def test_invalid_observation_does_not_update_nested_memory():
    component = MLComponent(SetSpec(n=5, k=2), MLConfig(backends=(), multi_agent=True))
    before = deepcopy(component.to_dict())
    with pytest.raises(ValueError):
        component.observe(np.array([1, 0, 0, 0, 0]), 1, '2026-01-02')
    assert component.to_dict() == before


def test_digit_models_and_registered_research_config_keep_their_policy():
    assert not MLConfig().multi_agent
    component = MLComponent(DigitSpec(positions=1, alphabet=6, per_draw=1, position_labels=('vị trí',)), MLConfig(multi_agent=True))
    assert component.multi_agent is None
    assert 'multi_agent' not in component.names


def test_failure_after_nested_learning_rolls_back_every_component(monkeypatch):
    from vlm.forecast.multi_agent import MultiAgentExpert
    cfg = MLConfig(backends=(), multi_agent=True, bootstrap=8, search_nodes=1)
    f = MLForecaster('mega645', cfg)
    series = mega_series(2)
    f.update(series.head(1))
    before = deepcopy(f.to_dict())
    original = MultiAgentExpert.learn
    def fail_after_learning(self, outcome):
        original(self, outcome)
        raise RuntimeError('lỗi ghi sau học')
    monkeypatch.setattr(MultiAgentExpert, 'learn', fail_after_learning)
    with pytest.raises(RuntimeError):
        f.update(series)
    assert f.to_dict() == before


def test_production_service_persists_real_multi_agent_summary(tmp_path):
    from vlm.forecast.service import refresh_snapshot
    import json
    cfg = MLConfig(backends=(), multi_agent=True, bootstrap=8, search_nodes=1)
    f, _, _ = refresh_snapshot('mega645', mega_series(8), tmp_path, config=cfg, issue=False)
    report = json.loads((tmp_path / 'multi-agent-summary.json').read_text())
    assert report['products']['mega645']['last_id'] == f.last_id
    assert report['products']['mega645']['components']['main']['observations'] == 8
    assert not report['products']['mega645']['confidence']['validated']


def test_disabling_multi_agent_removes_stale_public_summary(tmp_path):
    from vlm.forecast.service import refresh_snapshot
    import json
    series = mega_series(2)
    cfg = MLConfig(backends=(), multi_agent=True, bootstrap=8, search_nodes=1)
    refresh_snapshot('mega645', series, tmp_path, config=cfg, issue=False)
    refresh_snapshot('mega645', series, tmp_path,
                     config=cfg.model_copy(update={'multi_agent': False}), refit=True, issue=False)
    report = json.loads((tmp_path / 'multi-agent-summary.json').read_text())
    assert 'mega645' not in report['products']


def test_refreshing_with_nothing_new_keeps_the_committed_summary_byte_for_byte(tmp_path):
    """Tệp tóm tắt được commit vào kho. Làm mới không có kỳ mới chỉ đổi `generated_at`, nên không được ghi lại;
    có kỳ mới thì phải ghi, kèm dấu giờ mới."""
    from vlm.forecast.service import refresh_snapshot
    cfg = MLConfig(backends=(), multi_agent=True, bootstrap=8, search_nodes=1)
    path = tmp_path / 'multi-agent-summary.json'
    refresh_snapshot('mega645', mega_series(8), tmp_path, config=cfg, issue=False)
    first = path.read_bytes()
    refresh_snapshot('mega645', mega_series(8), tmp_path, config=cfg, issue=False)
    assert path.read_bytes() == first
    refresh_snapshot('mega645', mega_series(9), tmp_path, config=cfg, issue=False)
    import json
    before, after = json.loads(first)['products']['mega645'], json.loads(path.read_bytes())['products']['mega645']
    assert after['last_id'] == before['last_id'] + 1 and after['generated_at'] > before['generated_at']
