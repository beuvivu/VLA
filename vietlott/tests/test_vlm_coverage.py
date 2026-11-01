"""Danh mục vé công bố: rời nhau, dựng từ luật ĐÃ ghi trước kỳ quay theo quy tắc ghi trong sổ.

Hai lỗi dựng lại: Power 14-10-2026 — hệ số nhiễu của ``lag2`` đứng đầu nên ``Law.top`` chép nguyên
kỳ #1409 làm vé đầu và năm vé chung 5/6 số; Mega — năm vé chung 5 số nên "ít nhất một vé trúng ≥ 2
số" chỉ 30,6% thay vì 70,9% với cùng năm vé.
"""
import json
from copy import deepcopy
from datetime import datetime
from itertools import combinations
from math import comb

import numpy as np
import pytest

from vietlott_engine.core.products import ProductCode
from vietlott_engine.forecast.data import CONFIGS
from vlm.database.schema import VN
from vlm.forecast.distribution import COVERAGE_RULE, PUBLISHED_TOP_N, Law, coverage_tickets
from vlm.forecast.hits import any_ticket_tail


def _law(product: ProductCode, boosted: list[int], lift: float = 1.02) -> Law:
    """Luật gần đều như luật ML thật (tỉ số ≈ 1,01–1,02), sáu số ``boosted`` nhích lên cùng một lượng."""
    spec = CONFIGS[product].components['main']
    values = np.ones((1, spec.n))
    values[0, np.array(boosted) - 1] = lift
    values[0] *= 1 + 1e-4 * np.arange(spec.n)[::-1] / spec.n  # nhiễu nhỏ, thứ hạng tất định
    return Law(spec, values, np.array([1.0]))


PAST_DRAW = [14, 17, 21, 23, 24, 39]


def test_law_top_reproduces_the_past_draw_and_near_duplicate_tickets():
    """Lỗi gốc: một nhóm sáu số cùng nhích là vé đầu nguyên vẹn, và năm vé chung 5/6 số."""
    tops, _ = _law(ProductCode.POWER_655, PAST_DRAW).top(PUBLISHED_TOP_N)
    assert tops[0]['numbers'] == PAST_DRAW
    assert min(len(set(a['numbers']) & set(b['numbers'])) for a, b in combinations(tops, 2)) >= 4


@pytest.mark.parametrize('product,covered,past', [(ProductCode.MEGA_645, 30, [3, 9, 16, 29, 30, 44]),
                                                  (ProductCode.POWER_655, 30, PAST_DRAW),
                                                  (ProductCode.LOTTO_535, 25, [2, 10, 11, 19, 22])])
def test_coverage_tickets_are_disjoint_and_never_copy_the_boosted_group(product, covered, past):
    spec = CONFIGS[product].components['main']
    law = _law(product, past)
    assert law.top(PUBLISHED_TOP_N)[0][0]['numbers'] == past  # Law.top chép nguyên kỳ cũ
    tickets = coverage_tickets(law)
    assert len(tickets) == PUBLISHED_TOP_N and all(len(t) == spec.k == len(set(t)) for t in tickets)
    assert len({v for t in tickets for v in t}) == covered
    # Chia xoay vòng theo hạng: nhóm nhích lên trải ra mọi vé, không vé nào giữ quá 2 số của nó.
    assert max(len(set(t) & set(past)) for t in tickets) <= 2
    ranked = sorted(range(1, spec.n + 1), key=lambda v: (-law.marginals()[v - 1], v))[:covered]
    assert {v for t in tickets for v in t} == set(ranked)
    assert ranked[0] in tickets[0] and ranked[PUBLISHED_TOP_N] in tickets[0] and ranked[1] in tickets[1]


def test_disjoint_tickets_raise_the_any_ticket_two_hit_rate_exactly():
    spec = CONFIGS[ProductCode.MEGA_645].components['main']
    current = [[15, 25, 26, 29, 38, 44], [15, 25, 26, 29, 35, 44], [15, 25, 26, 29, 30, 44],
               [12, 15, 25, 26, 29, 44], [15, 25, 26, 35, 38, 44]]  # năm vé đã phát cho Mega #1576
    disjoint = coverage_tickets(_law(ProductCode.MEGA_645, PAST_DRAW))
    before, after = any_ticket_tail(current, spec.n, spec.k)[2], any_ticket_tail(disjoint, spec.n, spec.k)[2]
    assert before == pytest.approx(0.3064, abs=1e-4) and after == pytest.approx(0.70948, abs=1e-5)


def test_coverage_needs_a_set_law_that_fits_the_drum():
    with pytest.raises(ValueError):
        coverage_tickets(_law(ProductCode.MEGA_645, PAST_DRAW), count=8)


def _issue(rule: str | None, boosted: list[int]) -> dict:
    spec = CONFIGS[ProductCode.POWER_655].components['main']
    values = np.ones((1, spec.n)); values[0, np.array(boosted) - 1] = 1.02
    pending = {'target_id': 2, 'target_date': '2026-10-04', 'target_time': '2026-10-04T18:00:00+07:00',
               'made_at': '2026-10-03T08:00:00+07:00', 'based_on_id': 1, 'based_on_date': '2026-10-02',
               'draws_on_last_date': 1, 'history_sha256': 'abc',
               'laws': {'main': {'values': values.tolist(), 'mixture': [1]}}}
    if rule:
        pending['ticket_rule'] = rule
    return {'event': 'issue', 'product': 'power655', 'target_id': 2, 'history_sha256': 'abc',
            'config': {'search_nodes': 1000}, 'pending': pending}


def test_the_published_tickets_follow_the_rule_recorded_with_the_issue(monkeypatch):
    """Lần ghi có ``ticket_rule`` → danh mục rời nhau kèm mốc chính xác; lần ghi cũ giữ đúng vé đã phát."""
    from vlm.web import dashboard as db

    monkeypatch.setattr(db, '_valid_issue', lambda code, entry, now: True)
    now = datetime(2026, 10, 3, 12, tzinfo=VN)
    new = db._from_issue(ProductCode.POWER_655, _issue(COVERAGE_RULE, PAST_DRAW), now)
    main = new['components'][0]
    tickets = [t['numbers'] for t in main['top']]
    assert len({v for t in tickets for v in t}) == 30
    assert main['coverage']['any_ticket_ge']['2'] == pytest.approx(any_ticket_tail(tickets, 55, 6)[2])
    assert main['coverage']['one_ticket_ge']['2'] == pytest.approx(
        1 - (comb(49, 6) + 6 * comb(49, 5)) / comb(55, 6))
    old = db._from_issue(ProductCode.POWER_655, _issue(None, PAST_DRAW), now)
    assert old['components'][0]['top'][0]['numbers'] == PAST_DRAW and 'coverage' not in old['components'][0]


def test_the_ml_issue_records_the_ticket_rule_with_the_frozen_law():
    from vlm.forecast.pipeline import MLConfig, MLForecaster

    model = MLForecaster(ProductCode.MEGA_645, MLConfig(backends=()))
    model.last_id, model.last_date, model.draws_on_last_date = 1574, '2026-10-11', 1
    model.prefix_hash = 'abc'
    assert model.issue('2026-10-14T18:00:00+07:00', '2026-10-11T20:00:00+07:00')
    assert model.pending['ticket_rule'] == COVERAGE_RULE
    assert json.loads(json.dumps(model.pending))['ticket_rule'] == COVERAGE_RULE


def test_comparisons_score_the_disjoint_tickets_that_were_shown(tmp_path, monkeypatch):
    from vlm.web import dashboard as db
    from vlm.web.dashboard import build_dashboard

    seed, data, forecasts = tmp_path/'seed', tmp_path/'data', tmp_path/'forecast'
    seed.mkdir(parents=True); forecasts.mkdir(parents=True)
    (seed/'power655.jsonl').write_text(
        json.dumps({'id': 1, 'date': '2026-10-02', 'result': [1, 2, 3, 4, 5, 7], 'bonus_number': 8}) + '\n'
        + json.dumps({'id': 2, 'date': '2026-10-04', 'result': [1, 2, 3, 4, 5, 6], 'bonus_number': 9}) + '\n',
        encoding='utf-8')
    (forecasts/'ml-ledger.jsonl').write_text(json.dumps(_issue(COVERAGE_RULE, PAST_DRAW)) + '\n', encoding='utf-8')
    monkeypatch.setattr(db, '_valid_issue', lambda code, entry, now: True)
    snap = build_dashboard(data, seed, forecasts, now=datetime(2026, 10, 4, 19, tzinfo=VN))
    power = next(p for p in snap['products'] if p['product'] == 'power655')
    (match,) = power['comparisons']
    shown = [t['numbers'] for t in match['components'][0]['top']]
    assert [t['numbers'] for t in match['tickets']] == shown and len({v for t in shown for v in t}) == 30
    assert [t['hits'] for t in match['tickets']] == [len(set(t) & {1, 2, 3, 4, 5, 6}) for t in shown]
    assert deepcopy(match['components'][0]['coverage'])['rule'] == COVERAGE_RULE


# --- coverage-v2: mỗi vé Lotto 5/35 mang một số đặc biệt khác nhau (31-10-2026) ------------------------

def _lotto_issue(rule: str | None) -> dict:
    main = CONFIGS[ProductCode.LOTTO_535].components['main']
    values = np.ones((1, main.n)) * (1 + 1e-4 * np.arange(main.n)[::-1] / main.n)
    special = np.ones((1, 1, 12)); special[0, 0, [6, 2, 9, 0, 11]] = [1.05, 1.04, 1.03, 1.02, 1.01]
    pending = {'target_id': 2, 'target_date': '2026-10-04', 'target_time': '2026-10-04T21:00:00+07:00',
               'made_at': '2026-10-04T14:00:00+07:00', 'based_on_id': 1, 'based_on_date': '2026-10-04',
               'draws_on_last_date': 1, 'history_sha256': 'abc',
               'laws': {'main': {'values': values.tolist(), 'mixture': [1]},
                        'special': {'values': special.tolist(), 'mixture': [1]}}}
    if rule:
        pending['ticket_rule'] = rule
    return {'event': 'issue', 'product': 'lotto535', 'target_id': 2, 'history_sha256': 'abc',
            'config': {'search_nodes': 1000}, 'pending': pending}


def test_coverage_specials_are_distinct_and_ranked_by_their_marginal():
    from vlm.forecast.distribution import coverage_specials

    spec = CONFIGS[ProductCode.LOTTO_535].components['special']
    issue = _lotto_issue(None)['pending']['laws']['special']
    law = Law(spec, np.array(issue['values']), np.array(issue['mixture']))
    assert coverage_specials(law) == [7, 3, 10, 1, 12]  # ký hiệu = chỉ số + 1
    with pytest.raises(ValueError):
        coverage_specials(_law(ProductCode.LOTTO_535, [1, 2, 3, 4, 5]))


def test_the_any_ticket_prize_rate_is_exact_over_every_lotto_draw():
    """Vét cạn mọi bộ năm số chính × 12 số đặc biệt, chấm bằng CHÍNH bảng giải của trò chơi."""
    from itertools import combinations as combos

    from vietlott_engine.core.games import get_game
    from vlm.web.dashboard import prize_coverage

    game = get_game('lotto535')
    tickets = [list(range(1 + 5 * j, 6 + 5 * j)) for j in range(5)]
    draws = np.array(list(combos(range(1, 36), 5)))
    member = np.zeros((len(draws), 36), dtype=bool)
    np.put_along_axis(member, draws, True, axis=1)
    hits = np.stack([member[:, t].sum(axis=1) for t in tickets], axis=1)
    for specials in ([1, 2, 3, 4, 5], [1] * 5):
        wins = np.zeros(len(draws))
        for special in range(1, 13):
            won = np.zeros(len(draws), dtype=bool)
            for j, own in enumerate(specials):
                tier = np.array([game.classify(int(h), own == special) is not None for h in range(6)])
                won |= tier[hits[:, j]]
            wins += won
        exact = wins.sum() / (len(draws) * 12)
        got = prize_coverage(ProductCode.LOTTO_535, tickets, len(set(specials)))
        assert got['any_ticket_prize'] == pytest.approx(exact, abs=1e-12)
    assert got['shared_special_prize'] == pytest.approx(exact, abs=1e-12)  # vòng cuối: chung một số
    assert got['one_ticket_prize'] == pytest.approx(game.p_any_prize)


def test_a_v2_issue_pairs_each_lotto_ticket_with_its_own_special_and_scores_it(monkeypatch):
    from vlm.database.schema import DrawRecord
    from vlm.web import dashboard as db

    monkeypatch.setattr(db, '_valid_issue', lambda code, entry, now: True)
    now = datetime(2026, 10, 4, 15, tzinfo=VN)
    new = db._from_issue(ProductCode.LOTTO_535, _lotto_issue(COVERAGE_RULE), now)
    main, special = new['components']
    assert special['per_ticket'] and [s['numbers'][0] for s in special['top']] == [7, 3, 10, 1, 12]
    assert main['coverage']['rule'] == COVERAGE_RULE == 'coverage-v2'
    assert main['coverage']['any_ticket_prize'] == pytest.approx(0.4571, abs=1e-4)
    assert main['coverage']['shared_special_prize'] == pytest.approx(0.1469, abs=1e-4)
    old = db._from_issue(ProductCode.LOTTO_535, _lotto_issue('coverage-v1'), now)
    assert 'per_ticket' not in old['components'][1] and 'any_ticket_prize' not in old['components'][0]['coverage']
    assert old['components'][0]['coverage']['rule'] == 'coverage-v1'

    tickets = [t['numbers'] for t in main['top']]
    draw = DrawRecord.from_legacy('lotto535', {'id': 2, 'date': '2026-10-04', 'result': tickets[3][:2] + [31, 32, 33],
                                               'bonus_number': 1})
    scored = db.compare_prediction(new, draw)['tickets']
    assert [t['special'] for t in scored] == [7, 3, 10, 1, 12]
    assert [t['bonus_hit'] for t in scored] == [False, False, False, True, False]
    assert scored[3]['tier'] == 'consolation'
    legacy = db.compare_prediction(old, draw)['tickets']
    assert {t['special'] for t in legacy} == {7} and not any(t['bonus_hit'] for t in legacy)
