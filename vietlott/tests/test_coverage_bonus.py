"""Coverage chấm số Jackpot 2 Power từ lồng còn lại, cùng luật phân hạng vé."""
from dataclasses import replace
from itertools import combinations
from math import comb

import numpy as np
import pytest

from vietlott_engine.core.games import MEGA_645, POWER_655, LOTTO_535, PrizeTier
from vietlott_engine.game_theory.coverage import _masks, _sim_draws, _thresholds, _win_matrix, optimise_coverage


def test_power_simulation_draws_a_bonus_outside_the_six_main_numbers():
    main, bonus = _sim_draws(POWER_655, 1000, np.random.default_rng(9))
    assert np.all((1 <= bonus) & (bonus <= 55))
    assert not np.any(main & _masks(bonus[:, None]))


def test_power_jp2_coverage_matches_classification_and_exact_probability():
    """Mỗi lớp m số trùng có đúng 6-m số trên vé trong 49 số còn lại."""
    ticket = set(range(1, 7))
    draws, bonuses, probabilities, expected = [], [], [], []
    for matched in range(7):
        main = set(range(1, matched + 1)) | set(range(7, 13 - matched))
        for bonus_hits, remaining in ((True, ticket - main),
                                      (False, set(range(1, 56)) - main - ticket)):
            if not remaining:
                continue
            draws.append(sorted(main))
            bonuses.append(min(remaining))
            probabilities.append(POWER_655.match_probability(matched) * len(remaining) / 49)
            tier = POWER_655.classify(matched, bonus_hits)
            expected.append(tier is not None and tier.name in ('jackpot1', 'jackpot2'))
    wins = _win_matrix(POWER_655, _masks(np.array([sorted(ticket)])), np.array([0]),
                       _masks(np.array(draws)), np.array(bonuses), _thresholds(POWER_655, 'jackpot2'))[0]
    np.testing.assert_array_equal(wins, expected)
    # JP1 có một bộ; JP2 có sáu bộ thay đúng một số bằng bóng đặc biệt.
    assert np.dot(wins, probabilities) == pytest.approx(7 / comb(55, 6))


def test_power_jp2_optimisation_and_random_baseline_count_bonus_winners():
    """Lồng nhỏ giữ đúng cơ chế Power để mức hiếm có thể kiểm bằng mẫu hữu hạn."""
    spec = replace(POWER_655, pool_size=8, pick=3, tiers=(
        PrizeTier('jackpot1', 3), PrizeTier('jackpot2', 2, bonus_required=True),
        PrizeTier('first', 2, fixed_amount=40_000_000)))
    result = optimise_coverage(spec, 1, 'jackpot2', sim_draws=400, eval_draws=20_000,
                               candidates=16, local_rounds=1, seed=12)
    # Liệt kê độc lập cả bộ chính và từng bóng rút từ phần còn lại.
    ticket = {1, 2, 3}
    outcomes = [(set(main), bonus) for main in combinations(range(1, 9), 3)
                for bonus in range(1, 9) if bonus not in main]
    exact = sum(len(ticket & main) == 3 or (len(ticket & main) == 2 and bonus in ticket)
                for main, bonus in outcomes) / len(outcomes)
    assert exact == pytest.approx(4 / comb(8, 3))
    assert result.p_at_least_one == pytest.approx(exact, abs=.008)
    assert result.p_random_tickets == pytest.approx(exact, abs=.008)
    assert result.expected_prizes_per_draw == pytest.approx(exact)
    assert result.upper_bound == pytest.approx(exact)


@pytest.mark.parametrize('spec,ticket,main,ticket_special,draw_special,min_tier,want', [
    (MEGA_645, [1, 2, 3, 4, 5, 6], [1, 2, 3, 7, 8, 9], 0, 0, 'third', True),
    (MEGA_645, [1, 2, 3, 4, 5, 6], [1, 2, 7, 8, 9, 10], 0, 0, 'third', False),
    (LOTTO_535, [1, 2, 3, 4, 5], [1, 2, 6, 7, 8], 9, 9, 'consolation', True),
    (LOTTO_535, [1, 2, 3, 4, 5], [1, 2, 6, 7, 8], 9, 8, 'consolation', False),
    (LOTTO_535, [1, 2, 3, 4, 5], [1, 2, 3, 4, 8], 9, 8, 'second', False),
])
def test_mega_and_lotto_coverage_keep_their_prize_conditions(
        spec, ticket, main, ticket_special, draw_special, min_tier, want):
    wins = _win_matrix(spec, _masks(np.array([ticket])), np.array([ticket_special]),
                       _masks(np.array([main])), np.array([draw_special]), _thresholds(spec, min_tier))
    assert bool(wins[0, 0]) is want
