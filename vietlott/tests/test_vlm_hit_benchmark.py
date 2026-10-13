"""Giao thức benchmark: dữ liệu đóng băng, chia đoạn, nhân quả, chấm đúng mô hình, luật đề bạt."""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from vietlott_engine.core.products import ProductCode
from vietlott_engine.forecast.data import CONFIGS, Series
from vlm.forecast import challengers as ch
from vlm.forecast import hit_benchmark as hb

ROOT = Path(__file__).resolve().parents[1]


def _synthetic(t: int, n: int = 45, k: int = 6, hot: float = 0.0, seed: int = 0) -> Series:
    """Lịch sử kiểu Mega; ``hot`` > 0 cài tín hiệu thật: sáu số đầu có log-trọng số +hot."""
    from vietlott_engine.game_theory.popularity import sample_product_subsets

    rng = np.random.default_rng(seed)
    w = np.ones(n)
    w[:6] = np.exp(hot)
    x = np.zeros((t, n), dtype=bool)
    for row in x:
        row[sample_product_subsets(w, k, 1, rng)[0] - 1] = True
    days = np.arange(np.datetime64('2016-07-20'), np.datetime64('2016-07-20') + np.timedelta64(3 * t, 'D'), 3)[:t]
    return Series(ProductCode.MEGA_645, np.arange(1, t + 1), days.astype(str),
                  {'main': {'X': x, 'bonus': np.zeros(t, dtype=np.int16)}})


def test_the_manifest_hashes_every_project_module_that_ran():
    """Thiếu module p DM hay Holm thì đổi kết luận mà manifest không đổi."""
    import hashlib

    manifest = hb.source_manifest()
    for name in ('vietlott_engine/inference/predictive.py', 'vietlott_engine/inference/multiple_testing.py',
                 'vietlott_engine/forecast/data.py', 'vietlott_engine/game_theory/popularity.py',
                 'vlm/forecast/hits.py', 'vlm/forecast/challengers.py', 'vlm/forecast/hit_benchmark.py'):
        assert manifest[name] == hashlib.sha256((ROOT / 'src' / name).read_bytes()).hexdigest()
    assert all(name.endswith('.py') for name in manifest)


def test_split_partitions_the_scored_draws_in_time_order():
    split = hb.make_split(1574)
    segments = split.segments()
    assert segments['dev'][0] == hb.PROTOCOL['warmup'] and segments['test'][1] == 1574
    assert segments['dev'][1] == segments['validation'][0] and segments['validation'][1] == segments['test'][0]
    sizes = {name: b - a for name, (a, b) in segments.items()}
    assert sum(sizes.values()) == 1574 - 300 and sizes['test'] == pytest.approx(0.3 * 1274, abs=1)
    with pytest.raises(ValueError):
        hb.make_split(320)


@pytest.mark.parametrize('product', ['mega645', 'power655'])
def test_frozen_history_is_contiguous_and_stops_at_the_registered_draw(product):
    series, provenance = hb.load_frozen_series(product, ROOT)
    last = hb.PROTOCOL['frozen_last_id'][product]
    assert list(series.draw_ids) == list(range(1, last + 1)) and provenance['last_id'] == last
    assert (series.obs['main']['X'].sum(axis=1) == 6).all()
    if product == 'power655':
        rows = np.arange(len(series))
        assert not series.obs['main']['X'][rows, series.obs['main']['bonus'] - 1].any()


def test_a_journal_that_contradicts_the_seed_stops_the_benchmark(tmp_path):
    (tmp_path / 'data' / 'results').mkdir(parents=True)
    shutil.copytree(ROOT / 'data' / 'seed', tmp_path / 'data' / 'seed')
    lines = (ROOT / 'data' / 'results' / 'results.jsonl').read_text(encoding='utf-8').splitlines()
    first = json.loads(next(line for line in lines if '"mega645"' in line))
    first['winning_numbers'] = [1, 2, 3, 4, 5, 6] if first['winning_numbers'] != [1, 2, 3, 4, 5, 6] else [1, 2, 3, 4, 5, 7]
    (tmp_path / 'data' / 'results' / 'results.jsonl').write_text(json.dumps(first) + '\n', encoding='utf-8')
    seed_last = max(int(json.loads(r)['id']) for r in (ROOT / 'data' / 'seed' / 'power645.jsonl').read_text().splitlines())
    if first['draw_id'] <= seed_last:
        with pytest.raises(ValueError, match='mâu thuẫn'):
            hb.load_frozen_series('mega645', tmp_path)
    else:
        with pytest.raises(ValueError, match='thiếu kỳ'):
            hb.load_frozen_series('mega645', tmp_path)


def test_rebuilt_legacy_law_scores_exactly_what_the_engine_scores():
    series, _ = hb.load_frozen_series('power655', ROOT)
    head = series.head(80)
    laws, increments = hb.run_legacy(head, 40, 80)
    records = hb._law_records(laws, head, 40)
    gains = np.array([r['main_gain'] + r['bonus_gain'] for r in records])
    np.testing.assert_allclose(gains, increments, atol=1e-9)
    for law, record in zip(laws, records):
        np.testing.assert_allclose(law.marginals().sum(), 6)
        assert record['ticket'] == sorted(int(i) + 1 for i in np.argsort(-law.marginals(), kind='stable')[:6])


def test_both_ml_arms_score_the_ticket_their_own_law_would_issue(monkeypatch):
    """Nhánh ML + τ từng chấm 6 số biên cao nhất, không phải Law.top của luật đã hiệu chuẩn."""
    from vietlott_engine.forecast.data import SetSpec
    from vlm.forecast.distribution import Law

    series = _synthetic(10)
    rng = np.random.default_rng(4)
    laws = [Law(SetSpec(45, 6), rng.uniform(0.5, 2.0, (2, 45)), np.array([0.6, 0.4])) for _ in range(5)]
    issued = [40, 41, 42, 43, 44, 45]
    seen = []

    def fake_top(self, count, max_nodes=20000):
        seen.append((count, max_nodes))
        return [{'numbers': issued if count == hb.PUBLISHED_TOP_N else [1, 2, 3, 4, 5, 7]}], False

    monkeypatch.setattr(Law, 'top', fake_top)
    portfolios = [[[1, 2, 3, 4, 5, 6]] * 5 for _ in laws]
    plain, tempered = hb.ml_arm_records(laws, portfolios, series, 5, 0.7, 123)
    assert [r['ticket'] for r in plain] == [[1, 2, 3, 4, 5, 6]] * 5
    assert [r['ticket'] for r in tempered] == [issued] * 5 and seen == [(hb.PUBLISHED_TOP_N, 123)] * 5
    for t, record in enumerate(tempered, start=5):
        drawn = set((np.flatnonzero(series.obs['main']['X'][t]) + 1).tolist())
        assert record['hits'] == len(drawn & set(issued))


def test_power_bonus_is_scored_separately_and_never_counted_as_a_main_hit():
    spec = CONFIGS[ProductCode.POWER_655].components['main']
    row = np.zeros(55)
    row[[0, 1, 2, 3, 4, 5]] = 1
    record = hb._record(1, '2026-01-01', row, 7, -15.0, -3.9, np.full(55, 6 / 55), [1, 2, 3, 7, 8, 9], spec)
    assert record['hits'] == 3                       # số 7 là số đặc biệt, không cộng vào H
    assert record['bonus_gain'] == pytest.approx(-3.9 - ch.fair_log_likelihood(55, 6, True)[1])


def test_paired_tests_refuse_mismatched_draws_and_do_not_test_identical_laws():
    a = [{'id': i, 'main_gain': 0.0, 'bonus_gain': 0.0} for i in range(10)]
    assert hb.paired_test(a, None)['p_value_greater'] == 1.0 and hb.paired_test(a, None)['identical']
    with pytest.raises(ValueError):
        hb.paired_test(a, [{'id': i + 1, 'main_gain': 0.0, 'bonus_gain': 0.0} for i in range(10)])


def test_challenger_choices_never_read_the_test_segment():
    series = _synthetic(420)
    split = hb.make_split(len(series))
    chosen = hb.select_challengers(series, split)
    changed = _synthetic(420)
    changed.obs['main']['X'][split.val_end:] = np.roll(changed.obs['main']['X'][split.val_end:], 11, axis=1)
    again = hb.select_challengers(changed, split)
    for name in ('shrink', 'causal'):
        assert json.dumps(again[name], default=str) == json.dumps(chosen[name], default=str)


def test_the_protocol_finds_a_planted_signal_and_finds_nothing_in_fair_draws():
    for hot, expect in ((0.7, True), (0.0, False)):
        series = _synthetic(1000, hot=hot, seed=3)
        split = hb.make_split(len(series))
        chosen = hb.select_challengers(series, split)
        eta = hb.challenger_eta(series, chosen, split.val_end, split.end)['shrink']
        records = hb._eta_records(eta, series, split.val_end)
        test = hb.paired_test(records, None)
        assert (test['mean_difference_nats'] > 0 and test['p_value_greater'] < hb.PROTOCOL['alpha']) is expect


def _fake_results(gain: float, p: float, incumbents_beaten: bool = True, brier: float = 0.1) -> dict:
    vs = {'mean_difference_nats': gain, 'p_value_greater': p, 'thirds': [gain] * 3}
    inc = {'mean_difference_nats': gain if incumbents_beaten else -gain, 'p_value_greater': p if incumbents_beaten else 0.9}
    test = {c: {'vs_fair': vs, 'vs_legacy': inc, 'vs_ml': inc} for c in hb.CANDIDATES}
    seg = {c: {'mean_log_gain_nats': gain, 'brier': brier, 'brier_fair': 0.1} for c in hb.CANDIDATES}
    return {'tests': {'test': test}, 'segments': {'test': seg, 'validation': seg}}


def _both(**kwargs) -> dict:
    return {product: _fake_results(**kwargs) for product in hb.PROTOCOL['products']}


def test_promotion_requires_every_registered_condition_and_corrects_for_multiplicity():
    win = hb.promotion_decision(_both(gain=0.01, p=1e-6))
    assert win['verdict'] == 'challenger_eligible'
    # p = 0,01 đơn lẻ < α nhưng Holm trên 8 ứng viên × sản phẩm đẩy lên 0,08.
    assert hb.promotion_decision(_both(gain=0.01, p=0.01))['verdict'] == 'keep_production'
    assert not hb.promotion_decision(_both(gain=0.01, p=1e-6, incumbents_beaten=False))['mega645:shrink']['eligible_for_prospective_trial']
    assert not hb.promotion_decision(_both(gain=0.01, p=1e-6, brier=0.2))['mega645:shrink']['eligible_for_prospective_trial']
    assert not hb.promotion_decision(_both(gain=-0.01, p=1e-6))['mega645:shrink']['eligible_for_prospective_trial']


def test_a_partial_run_keeps_the_full_holm_family_and_cannot_promote():
    """Chạy một sản phẩm: họ Holm vẫn 8 giả thuyết (p = 0,01 → 0,08), và lượt thiếu không đề bạt ai."""
    partial = hb.promotion_decision({'mega645': _fake_results(0.01, 0.01)})
    assert partial['verdict'] == 'incomplete_run'
    assert partial['mega645:shrink']['holm_p_vs_fair'] == pytest.approx(0.08)
    assert not any(v['eligible_for_prospective_trial'] for v in partial.values() if isinstance(v, dict))
    no_ml = _both(gain=0.01, p=1e-6)
    for product in no_ml.values():
        del product['tests']['test']['ml_tempered']
    assert hb.promotion_decision(no_ml)['verdict'] == 'incomplete_run'


def test_the_causal_temperature_is_fitted_on_the_stream_that_is_scored():
    """τ của challenger nhân quả phải chỉnh trên ĐÚNG chuỗi η được chấm (học lại từ warmup)."""
    series = _synthetic(1000, hot=0.7, seed=3)
    split = hb.make_split(len(series))
    assert (split.dev_end - split.warmup) % hb.PROTOCOL['refit_every'] != 0   # lịch lệch nếu học lại từ dev_end
    chosen = hb.select_challengers(series, split)
    causal = chosen['causal']
    assert causal['groups']
    raw = hb.challenger_eta(series, {**chosen, 'causal': {**causal, 'tau_validation': 1.0}}, split.warmup, split.val_end)['causal']
    x = series.obs['main']['X']
    expected = ch.fit_temperature(raw[split.dev_end - split.warmup:], x[split.dev_end:split.val_end], None,
                                  hb.PROTOCOL['temperature_bounds'])
    assert causal['tau_validation'] == pytest.approx(expected, abs=1e-9)


def _load_artifacts(directory: Path) -> dict:
    import gzip

    out = {}
    for product in hb.PROTOCOL['products']:
        with gzip.open(directory / f'{product}.json.gz', 'rt', encoding='utf-8') as stream:
            out[product] = json.load(stream)
    return out


def test_the_committed_artifacts_were_produced_under_the_current_protocol():
    """Đổi PROTOCOL mà không chạy lại thì báo cáo đã commit không còn là số đo của giao thức đang khai."""
    assert hb.protocol_mismatches(_load_artifacts(ROOT / 'reports' / 'vlm' / 'hit-benchmark')) == []


def test_rendering_refuses_artifacts_from_another_protocol(tmp_path, monkeypatch):
    import gzip
    import runpy

    changed = json.loads(json.dumps(hb.PROTOCOL))
    changed['alpha'] = 0.1
    assert hb.protocol_mismatches({'mega645': {'protocol': json.loads(json.dumps(hb.PROTOCOL))}}) == []
    assert hb.protocol_mismatches({'mega645': {'protocol': changed}, 'power655': {}}) == ['mega645', 'power655']
    for product in hb.PROTOCOL['products']:
        with gzip.open(tmp_path / f'{product}.json.gz', 'wt', encoding='utf-8') as stream:
            json.dump({'protocol': changed}, stream)
    monkeypatch.chdir(ROOT)
    main = runpy.run_path(str(ROOT / 'scripts' / 'hit_benchmark.py'))['main']
    report = tmp_path / 'report.md'
    with pytest.raises(SystemExit, match='PROTOCOL'):
        main(['--render-only', '--out-dir', str(tmp_path), '--report', str(report)])
    assert not report.exists()
