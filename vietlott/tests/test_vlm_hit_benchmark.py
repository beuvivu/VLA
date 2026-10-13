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


def test_promotion_requires_every_registered_condition_and_corrects_for_multiplicity():
    win = hb.promotion_decision({'mega645': _fake_results(0.01, 1e-6)})
    assert win['verdict'] == 'challenger_eligible'
    # p = 0,02 đơn lẻ < α nhưng Holm trên 4 ứng viên đẩy lên 0,08.
    holm = hb.promotion_decision({'mega645': _fake_results(0.01, 0.02)})
    assert holm['verdict'] == 'keep_production'
    assert not hb.promotion_decision({'mega645': _fake_results(0.01, 1e-6, incumbents_beaten=False)})['mega645:shrink']['eligible_for_prospective_trial']
    assert not hb.promotion_decision({'mega645': _fake_results(0.01, 1e-6, brier=0.2)})['mega645:shrink']['eligible_for_prospective_trial']
    assert not hb.promotion_decision({'mega645': _fake_results(-0.01, 1e-6)})['mega645:shrink']['eligible_for_prospective_trial']
