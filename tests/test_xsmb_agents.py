"""Hợp đồng tiến cứu, xác suất và điều phối ba tác tử XSMB."""
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import online_learning as online
from time_policy import VIETNAM_TZ
from xsmb_domain import FIELD_WIDTHS, baseline_rate


def history(n=80, seed=17):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        row = {key: int(rng.integers(10**width)) for key, width in FIELD_WIDTHS}
        row['date'] = (date(2025, 1, 1) + timedelta(days=i)).isoformat()
        rows.append(row)
    return pd.DataFrame(rows)


def clock(frame):
    return datetime.combine(date.fromisoformat(frame.iloc[-1]['date']) + timedelta(days=1),
                            datetime.min.time(), VIETNAM_TZ)


def test_registered_agents_reuse_online_settlement_without_rewriting_legacy():
    frame = history(15)
    state = online.new_state('de', profile='agents')
    p = np.full(100, .01)
    experts = {name: p.copy() for name in ('statistical', 'probabilistic', 'pattern')}
    target = clock(frame).date().isoformat()
    state, record = online.advance(state, frame, p, target, now=clock(frame),
                                   expert_predictions=experts)
    assert set(record['experts']) == {'incumbent', 'constant', *experts}
    assert state['learning']['n_settled'] == 0
    same, frozen = online.advance(state, frame, p, target, now=clock(frame),
                                  expert_predictions={k: p[::-1] for k in experts})
    assert same == state and frozen == record
    extended = history(16)
    state, _ = online.advance(state, extended, p, clock(extended).date().isoformat(),
                              now=clock(extended), expert_predictions=experts)
    assert state['learning']['n_settled'] == 1
    assert state['records'][0]['settlement']['scores']['pattern']['logloss'] > 0
    legacy = online.new_state('de')
    assert legacy['recipe'] == online.RECIPE
    assert len(legacy['learning']['slow_loss']) == len(online.EXPERTS)


@pytest.mark.parametrize('mode', ['de', 'loto'])
def test_agents_preserve_probability_domains_and_do_not_read_target(mode):
    from xsmb_agents import AlgorithmEnsemble, KnowledgeBaseManager
    frame = history(85)
    target = frame.iloc[-1]['date']
    kb = KnowledgeBaseManager(frame, target_date=target)
    altered = frame.copy()
    altered.loc[84, 'special'] = 99999
    other = KnowledgeBaseManager(altered, target_date=target)
    incumbent = np.full(100, baseline_rate(mode))
    one = AlgorithmEnsemble(kb).predict(mode, incumbent)
    two = AlgorithmEnsemble(other).predict(mode, incumbent)
    assert set(one.probabilities) == {'statistical', 'probabilistic', 'pattern'}
    for name, p in one.probabilities.items():
        assert np.allclose(p, two.probabilities[name])
        assert p.shape == (100,) and np.isfinite(p).all()
        assert np.all((p >= 0) & (p <= 1))
        assert p.sum() == pytest.approx(1) if mode == 'de' else p.sum() <= 27
    retrieved = kb.retrieve('loto')
    assert all(item['date'] < kb.frame.iloc[-30]['date'] for item in retrieved)


def test_memory_rejects_unexplained_gap_and_conflicting_dates():
    from xsmb_agents import KnowledgeBaseManager
    frame = history()
    with pytest.raises(ValueError, match='Thiếu|gap'):
        KnowledgeBaseManager(frame.drop(index=10))
    bad = pd.concat([frame, frame.iloc[[5]].assign(special=99)])
    with pytest.raises(ValueError, match='xung đột|duplicate'):
        KnowledgeBaseManager(bad)


def test_engine_is_idempotent_preserves_public_vector_and_explains_mixture(tmp_path):
    from xsmb_agents import PredictiveEngine
    frame = history(40)
    frame.to_csv(tmp_path / 'xsmb.csv', index=False)
    pred = tmp_path / 'predict'
    pred.mkdir()
    target = clock(frame).date().isoformat()
    snapshots = {}
    for mode in ('de', 'loto'):
        p = np.full(100, baseline_rate(mode))
        path = pred / f'predict_next_{mode}_all_{target}.csv'
        pd.DataFrame({'number': np.arange(100), 'prob': p}).to_csv(path, index=False)
        snapshots[path] = path.read_bytes()
    engine = PredictiveEngine()
    report = engine.run(tmp_path, now=clock(frame))
    again = engine.run(tmp_path, now=clock(frame))
    assert report == again
    for path, content in snapshots.items():
        assert path.read_bytes() == content
    for mode, item in report['modes'].items():
        assert item['n_settled'] == 0
        assert len(item['items']) == 100
        for row in item['items']:
            assert row['candidate_probability'] == pytest.approx(
                baseline_rate(mode) + sum(x['delta'] for x in row['contributions']))
            assert row['hit_probability_percent'] == pytest.approx(100 * row['published_probability'])
            assert row['calibration_band'] is None
            assert row['reasoning_path'] and row['risk_factors']
    path = tmp_path / 'online' / 'agents_de.json'
    path.write_text('{}')
    with pytest.raises(ValueError, match='Checksum|corrupt|đọc'):
        engine.run(tmp_path, now=clock(frame))


def test_profile_never_claims_shadow_vector_was_published(monkeypatch):
    frame = history(15)
    p = np.full(100, .01)
    candidate = p.copy()
    candidate[7] += .5
    candidate /= candidate.sum()
    monkeypatch.setattr(online, 'promotion_gate', lambda _: {'active': True, 'reason': 'test'})
    state, record = online.advance(online.new_state('de', profile='agents'), frame, p,
                                   clock(frame).date().isoformat(), now=clock(frame),
                                   expert_predictions={name: candidate for name in
                                                       ('statistical', 'probabilistic', 'pattern')})
    assert record['gate']['active'] is False
    assert record['gate']['experimental_pass'] is True
    np.testing.assert_array_equal(record['published'], p)
    assert state['records'][0]['published'] == p.tolist()


def test_mlp_is_fitted_on_chronological_prefix_and_target_mutation_cannot_change_it():
    from xsmb_agents import AlgorithmEnsemble, KnowledgeBaseManager
    frame = history(100)
    target = frame.iloc[-1]['date']
    kb = KnowledgeBaseManager(frame, target_date=target)
    one = AlgorithmEnsemble(kb).pattern('de')
    changed = frame.copy()
    changed.loc[99, 'special'] = 99999
    two = AlgorithmEnsemble(KnowledgeBaseManager(changed, target_date=target)).pattern('de')
    assert one[1]['status'] == 'fitted'
    assert one[1]['hidden_layers'] == [24, 12]
    assert one[1]['validation_draws'] == 30
    assert one[1]['training_until'] < target
    np.testing.assert_array_equal(one[0], two[0])


def test_tuning_uses_settled_forecasts_only_and_rewards_lower_proper_loss():
    p = np.full(100, .01)
    strong = p / 2
    strong[7] += .5
    y = np.zeros(100)
    y[7] = 1
    experts = {name: (strong if name == 'pattern' else p) for name in online.AGENT_EXPERTS}
    record = {'experts': experts,
              'settlement': {'status': 'scored', 'labels': y.tolist(), 'scores': {
                  name: online.proper_losses('de', pred, y) for name, pred in experts.items()}}}
    weights, tuned = online.tune_agent_weights([record] * 35, 'de')
    assert tuned['replay_draws'] == 35
    assert tuned['eta'] in (1, 4, 8) and tuned['discount'] in (.9, .97)
    assert weights[-1] > weights[0]
    after, _ = online.tune_agent_weights([record] * 35 + [{'settlement': None}], 'de')
    np.testing.assert_array_equal(weights, after)


def test_tuning_keeps_long_memory_beyond_the_selection_window():
    p = np.full(100, .01)
    strong = p / 2
    strong[7] += .5
    y = np.zeros(100)
    y[8] = 1

    def record(pattern):
        experts = {name: (pattern if name == 'pattern' else p) for name in online.AGENT_EXPERTS}
        return {'experts': experts, 'settlement': {'status': 'scored', 'labels': y.tolist(),
                'scores': {name: online.proper_losses('de', pred, y) for name, pred in experts.items()}}}

    weights, _ = online.tune_agent_weights([record(strong)] * 5 + [record(p)] * 180, 'de')
    assert weights[-1] < weights[0]


def test_pipeline_runs_agents_after_both_online_forecasts_even_without_docs(monkeypatch):
    import sys
    import pipeline
    calls = []
    monkeypatch.setattr(pipeline, '_run', lambda argv, **options: calls.append((argv, options)))
    monkeypatch.setattr(sys, 'argv', ['pipeline.py', '--skip-sync', '--skip-docs', '--strict'])
    pipeline.main()
    agents = [(i, options) for i, (cmd, options) in enumerate(calls)
              if 'src/run_xsmb_agents.py' in cmd]
    assert len(agents) == 1
    at, options = agents[0]
    assert options['allow_fail'] is False
    assert all(i < at for i, (cmd, _) in enumerate(calls) if 'src/online_learning.py' in cmd)
    for producer in ('src/confidence_matrix.py', 'src/multi_hit_report.py', 'src/knowledge_base.py'):
        produced = [i for i, (cmd, _) in enumerate(calls) if producer in cmd]
        assert len(produced) == 1 and produced[0] < at


def test_public_agents_card_distinguishes_candidates_and_rejects_old_date():
    from build_confidence_page import agents_card
    mode = {'n_settled': 0, 'weights': dict.fromkeys(online.AGENT_EXPERTS, .2),
            'tuning': {'eta': 4, 'discount': .97}, 'confidence_matrix': {},
            'candidate_top5': [{'number': '<07>', 'published_probability': .01,
                                'candidate_probability': .013, 'reasoning_path': ['Chỉ dùng kỳ trước'],
                                'risk_factors': ['Chưa đủ kỳ'], 'calibration_band': None}],
            'diagnostics': {'pattern': {'status': 'insufficient_history'}},
            'knowledge': {'similar_contexts': []}}
    payload = {'target_date': '2026-10-17', 'modes': {'de': mode, 'loto': mode}}
    text = agents_card(payload, target_date='2026-10-17')
    assert 'ứng viên' in text.lower() and 'công bố' in text.lower()
    assert '1,30%' in text and '&lt;07&gt;' in text
    assert '<07>' not in text and 'Chưa đủ kỳ' in text
    from bs4 import BeautifulSoup
    table = BeautifulSoup(text, 'html.parser').find('table')
    assert len(table.find_all('th')) == 3
    assert 'Chỉ dùng kỳ trước' not in table.get_text()
    old = agents_card(payload, target_date='2026-10-18')
    assert '1,30%' not in old and 'chờ' in old.lower()


def test_engine_checks_real_clock_after_lock_and_training_before_freezing(tmp_path, monkeypatch):
    import xsmb_agents.engine as engine_module
    from xsmb_agents import PredictiveEngine
    frame = history(40)
    frame.to_csv(tmp_path / 'xsmb.csv', index=False)
    pred = tmp_path / 'predict'
    pred.mkdir()
    target = clock(frame).date().isoformat()
    for mode in ('de', 'loto'):
        pd.DataFrame({'number': np.arange(100), 'prob': np.full(100, baseline_rate(mode))}).to_csv(
            pred / f'predict_next_{mode}_all_{target}.csv', index=False)
    moments = iter([clock(frame).replace(hour=17, minute=59),
                    clock(frame).replace(hour=18, minute=1)])
    monkeypatch.setattr(engine_module, 'now_vietnam', lambda: next(moments))
    with pytest.raises(ValueError, match='cutoff|18:00|quá giờ'):
        PredictiveEngine().run(tmp_path)
    assert not (tmp_path / 'online' / 'agents_de.json').exists()


def test_backtest_is_prefix_only_diagnostic_and_does_not_fabricate_live_observations():
    from xsmb_agents.benchmark import walk_forward
    frame = history(40)
    original = frame.copy(deep=True)
    result = walk_forward(frame, last=4)
    assert result['evidence_type'] == 'retrospective_diagnostic'
    assert result['prospective_draws'] == 0
    for mode in ('de', 'loto'):
        scores = result['modes'][mode]
        assert scores['draws'] == 4
        assert scores['agents']['constant']['logloss'] > 0
        assert set(scores['agents']) == {*online.AGENT_EXPERTS, 'mixture'}
    pd.testing.assert_frame_equal(frame, original)
