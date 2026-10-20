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
    assert engine.run(tmp_path, now=clock(frame).replace(hour=19)) == report
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


@pytest.mark.parametrize('slow_phase', ['serialization', 'fsync'])
def test_engine_rechecks_cutoff_after_serializing_a_new_journal(tmp_path, monkeypatch, slow_phase):
    import atomic_io
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
    moment = [clock(frame).replace(hour=17, minute=59)]
    monkeypatch.setattr(engine_module, 'now_vietnam', lambda: moment[0])
    real_json = online._json_bytes

    def delayed_json(value):
        result = real_json(value)
        if slow_phase == 'serialization' and isinstance(value, dict) and '_checksum' in value:
            moment[0] = clock(frame).replace(hour=18, minute=1)
        return result

    monkeypatch.setattr(online, '_json_bytes', delayed_json)
    real_fsync = atomic_io.os.fsync

    def delayed_fsync(fd):
        real_fsync(fd)
        if slow_phase == 'fsync':
            moment[0] = clock(frame).replace(hour=18, minute=1)

    monkeypatch.setattr(atomic_io.os, 'fsync', delayed_fsync)
    with pytest.raises(ValueError, match='cutoff|18:00|quá giờ'):
        PredictiveEngine().run(tmp_path)
    assert not (tmp_path / 'online' / 'agents_de.json').exists()
    assert list((tmp_path / 'online').glob('.agents_de.json.*')) == []


@pytest.mark.parametrize('mode', ['de', 'loto'])
def test_explanation_decodes_calibration_history_once_and_preserves_intervals(mode, monkeypatch):
    """100 số dùng chung thống kê nhóm; nén sổ không được nhân việc giải mã 100 lần."""
    import base64
    import copy
    import hashlib
    import zlib
    from xsmb_agents.engine import MetaLearner, PredictiveEngine
    frame = history(40)
    p = np.linspace(1, 2, 100)
    p = p / p.sum() if mode == 'de' else p / 7
    predictions = {name: p for name in ('statistical', 'probabilistic', 'pattern')}
    state, record = online.advance(online.new_state(mode, profile='agents'), frame, p,
                                   clock(frame).date().isoformat(), now=clock(frame),
                                   expert_predictions=predictions)
    record['agent_diagnostics'] = {'pattern': {'status': 'insufficient_history'}}
    record['knowledge_snapshot'] = {}
    settled = []
    for index in range(68):
        item = copy.deepcopy(record)
        if index < 20:
            item['experts']['incumbent'] = np.full(100, baseline_rate(mode)).tolist()
        labels = np.zeros(100)
        labels[index % 100] = 1
        if mode == 'loto':
            labels[(np.arange(23) + index) % 100] = 1
        item['settlement'] = {'status': 'scored', 'labels': labels.tolist(),
                              'scores': online._scores(mode, item, labels)}
        settled.append(item)
    # Bản chưa chốt và ngày nghỉ không được trộn thành mẫu hiệu chuẩn.
    raw = online._json_bytes(settled + [{'settlement': None}, {'settlement': {'status': 'non_draw'}}])
    state['archive'] = [{'count': 70, 'sha256': hashlib.sha256(raw).hexdigest(),
                         'zlib_base64': base64.b64encode(zlib.compress(raw)).decode()}]
    state['records'] = [record]
    learner = MetaLearner.__new__(MetaLearner)
    learner.mode, learner.state = mode, state
    expected = []
    width = .01 if mode == 'de' else .05
    for probability in p:
        residuals = []
        for item in settled:
            historical_p = np.asarray(item['experts']['incumbent'])
            selected = np.floor(historical_p / width) == np.floor(probability / width)
            if selected.any():
                residuals.append(float((np.asarray(item['settlement']['labels'])[selected]
                                        - historical_p[selected]).mean()))
        if len(residuals) < 60:
            expected.append(None)
            continue
        stats = online._gain_stats(residuals)
        center, radius = probability + stats['mean'], 1.96 * stats['se']
        expected.append({'lower': max(0.0, center - radius), 'upper': min(1.0, center + radius),
                         'draws': len(residuals), 'method': 'Xấp xỉ 95% theo nhóm, SE khối 7 kỳ',
                         'per_number_guarantee': False})
    real_decompress = zlib.decompress
    calls = []

    def counted_decompress(*args, **kwargs):
        calls.append(None)
        return real_decompress(*args, **kwargs)

    monkeypatch.setattr(zlib, 'decompress', counted_decompress)
    report = PredictiveEngine.explain(learner, record)
    assert [item['calibration_band'] for item in report['items']] == expected
    assert len(calls) <= 2, 'Chỉ giải mã một lần cho confidence_matrix và một lần cho toàn bộ bands'
    learner.state = {**state, 'archive': [], 'records': settled[:59]}
    assert learner.calibration_band(float(p[0])) is None


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


def _planted_loto_history(n=100):
    """Giải cuối luôn có hai số cuối 07: con 07 về MỌI kỳ, mạng phải học được."""
    frame = history(n)
    frame[FIELD_WIDTHS[-1][0]] = 7
    return frame


@pytest.mark.parametrize('mode', ['de', 'loto'])
def test_pattern_without_validation_skill_publishes_exactly_the_base_rate(mode):
    """Không có kỹ năng thì không tin: lịch sử công bằng cho trust = 0 và vector đúng mức nền.

    Định nghĩa 1 trộn cố định 20% mạng bất kể khối thẩm định; bản ghi đầu của sổ thật có logloss
    thẩm định Đặc Biệt kém nền mà vẫn được trộn.
    """
    from xsmb_agents import AlgorithmEnsemble, KnowledgeBaseManager
    from xsmb_agents.algorithms import AGENT_POLICY, feasible
    p, info = AlgorithmEnsemble(KnowledgeBaseManager(history(100))).pattern(mode)
    assert info['status'] == 'fitted' and info['policy'] == AGENT_POLICY == 2
    assert min(info['validation_skill'].values()) <= 0
    assert info['trust'] == 0.0
    np.testing.assert_array_equal(p, feasible(mode, np.full(100, baseline_rate(mode))))


def test_pattern_trust_is_the_repository_rule_applied_to_validation_skill(monkeypatch):
    """Mạng có kỹ năng thật: trust = model_trust(s), vector = trust·mạng + (1 − trust)·nền."""
    import xsmb_agents.algorithms as algorithms
    from ml_train import model_trust
    from xsmb_agents import AlgorithmEnsemble, KnowledgeBaseManager
    frame = _planted_loto_history()
    p, info = AlgorithmEnsemble(KnowledgeBaseManager(frame)).pattern('loto')
    skill = info['validation_skill']
    for name in ('logloss', 'brier'):
        reference = info[f'baseline_validation_{name}']
        assert skill[name] == pytest.approx((reference - info[f'validation_{name}']) / reference)
    assert min(skill.values()) > 0
    assert 0 < info['trust'] == pytest.approx(model_trust(skill['logloss'], skill['brier']))
    assert p[7] > baseline_rate('loto')
    monkeypatch.setattr(algorithms, 'model_trust', lambda *_: 1.0)
    raw, _ = AlgorithmEnsemble(KnowledgeBaseManager(frame)).pattern('loto')
    base = np.full(100, baseline_rate('loto'))
    expected = algorithms.feasible('loto', info['trust'] * raw + (1 - info['trust']) * base)
    np.testing.assert_allclose(p, expected, rtol=0, atol=1e-12)


def test_ledger_records_the_agent_policy_without_rewriting_older_records(tmp_path):
    """Bản ghi mới mang ``agent_policy``; bản ghi cũ không có trường vẫn đọc được là định nghĩa 1."""
    import json
    from xsmb_agents import PredictiveEngine
    from xsmb_agents.algorithms import AGENT_POLICY
    from xsmb_agents.engine import record_policy
    frame = history(40)
    frame.to_csv(tmp_path / 'xsmb.csv', index=False)
    pred = tmp_path / 'predict'
    pred.mkdir()
    target = clock(frame).date().isoformat()
    for mode in ('de', 'loto'):
        pd.DataFrame({'number': np.arange(100), 'prob': np.full(100, baseline_rate(mode))}).to_csv(
            pred / f'predict_next_{mode}_all_{target}.csv', index=False)
    report = PredictiveEngine().run(tmp_path, now=clock(frame))
    for mode in ('de', 'loto'):
        state = json.loads((tmp_path / 'online' / f'agents_{mode}.json').read_text(encoding='utf-8'))
        assert state['records'][-1]['agent_policy'] == AGENT_POLICY
        assert report['modes'][mode]['agent_policy'] == AGENT_POLICY
        assert report['modes'][mode]['confidence_matrix']['pattern']['current_policy'] == AGENT_POLICY
    assert record_policy({}) == 1
    for bad in (True, 0, AGENT_POLICY + 1, '2'):
        with pytest.raises(ValueError, match='Định nghĩa'):
            record_policy({'agent_policy': bad})


def test_pattern_scores_come_from_the_running_definition_only(tmp_path):
    """Điểm (số kỳ, Brier, logloss, phần lời gần đây) của bản trộn cố định 20% không được đọc như
    bằng chứng cho định nghĩa mới; các hàng khác không đổi định nghĩa nên giữ cả lịch sử."""
    from xsmb_agents.algorithms import AGENT_POLICY
    from xsmb_agents.engine import MetaLearner
    learner = MetaLearner('de', tmp_path / 'agents_de.json')
    p = np.full(100, .01)
    skewed = np.full(100, .005)
    skewed[:50] = .015
    state = learner.state
    for n in (15, 16, 17):
        frame = history(n)
        experts = {'statistical': p, 'probabilistic': p, 'pattern': skewed if n == 15 else p}
        state, _ = online.advance(state, frame, p, clock(frame).date().isoformat(), now=clock(frame),
                                  expert_predictions=experts)
        if n == 16:
            state['records'][-1]['agent_policy'] = AGENT_POLICY
    learner.state = state
    matrix = learner.confidence_matrix()
    current = state['records'][1]['settlement']['scores']['pattern']
    assert matrix['pattern']['draws'] == matrix['pattern']['current_policy_draws'] == 1
    assert matrix['pattern']['all_policies_draws'] == 2
    assert matrix['pattern']['brier'] == pytest.approx(current['brier'])
    assert matrix['pattern']['logloss'] == pytest.approx(current['logloss'])
    assert matrix['pattern']['recent_draws'] == 1
    assert matrix['statistical']['draws'] == matrix['constant']['draws'] == 2


def test_a_ledger_from_a_newer_definition_is_refused_before_anything_is_written(tmp_path):
    """Bản triển khai cũ gặp sổ có định nghĩa mới hơn phải dừng TRƯỚC khi chốt hay ghi sổ nào."""
    import json
    from xsmb_agents import PredictiveEngine
    from xsmb_agents.algorithms import AGENT_POLICY
    frame = history(41)
    frame.to_csv(tmp_path / 'xsmb.csv', index=False)
    pred = tmp_path / 'predict'
    pred.mkdir()
    previous = history(40)
    for day in (previous, frame):
        target = clock(day).date().isoformat()
        for mode in ('de', 'loto'):
            pd.DataFrame({'number': np.arange(100), 'prob': np.full(100, baseline_rate(mode))}).to_csv(
                pred / f'predict_next_{mode}_all_{target}.csv', index=False)
    # Sổ kỳ trước: LOTO mang định nghĩa lạ nhưng checksum đúng (ghi bằng chính save_state).
    for mode in ('de', 'loto'):
        state, record = online.advance(online.new_state(mode, profile='agents'), previous,
                                       np.full(100, baseline_rate(mode)), clock(previous).date().isoformat(),
                                       now=clock(previous),
                                       expert_predictions={name: np.full(100, baseline_rate(mode))
                                                           for name in ('statistical', 'probabilistic', 'pattern')})
        state['records'][-1]['agent_policy'] = AGENT_POLICY + 1 if mode == 'loto' else AGENT_POLICY
        (tmp_path / 'online').mkdir(exist_ok=True)
        online.save_state(tmp_path / 'online' / f'agents_{mode}.json', state)
    before = {mode: (tmp_path / 'online' / f'agents_{mode}.json').read_bytes() for mode in ('de', 'loto')}
    with pytest.raises(ValueError, match='Định nghĩa'):
        PredictiveEngine().run(tmp_path, now=clock(frame))
    for mode in ('de', 'loto'):
        assert (tmp_path / 'online' / f'agents_{mode}.json').read_bytes() == before[mode]
    assert not (tmp_path / 'agents' / 'report.json').exists()
    assert json.loads(before['de'])['records'][-1]['settlement'] is None


def test_agents_card_prints_the_pattern_trust_from_the_running_definition():
    from build_confidence_page import agents_card
    pattern = {'status': 'fitted', 'validation_draws': 30, 'trust': 0.0,
               'validation_skill': {'logloss': -0.004, 'brier': -0.0005}}
    mode = {'n_settled': 3, 'agent_policy': 2, 'weights': dict.fromkeys(online.AGENT_EXPERTS, .2),
            'tuning': {'eta': 4, 'discount': .97},
            'confidence_matrix': {'pattern': {'current_policy_draws': 1}},
            'candidate_top5': [], 'diagnostics': {'pattern': pattern},
            'knowledge': {'similar_contexts': []}}
    payload = {'target_date': '2026-10-21', 'modes': {'de': mode, 'loto': mode}}
    text = agents_card(payload, target_date='2026-10-21')
    assert 'kỹ năng logloss -0,400%' in text and 'độ tin 0,0%' in text
    assert '1 kỳ đã chấm theo định nghĩa này' in text
    old = agents_card({**payload, 'modes': {m: {**mode, 'agent_policy': 1} for m in ('de', 'loto')}},
                      target_date='2026-10-21')
    assert 'độ tin 0,0%' not in old
