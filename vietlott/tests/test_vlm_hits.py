"""Số khớp H: mốc siêu bội, khoảng tin cậy, công suất, danh mục nhiều vé."""
from itertools import combinations, product
from math import comb

import numpy as np
import pytest
from scipy import stats

from vlm.forecast.hits import (
    any_ticket_tail, clopper_pearson, detectable_lift, draws_needed, fair_hit_pmf, hit_count, poisson_binomial_sf,
    portfolio_summary, predictable_p_value, summarize_hits,
)


def test_fair_pmf_matches_enumeration_and_the_published_rates():
    n, k, ticket = 9, 3, 4
    counts = np.zeros(ticket + 1)
    for drawn in combinations(range(n), k):
        counts[len(set(drawn) & set(range(ticket)))] += 1
    np.testing.assert_allclose(fair_hit_pmf(n, k, ticket), counts / comb(n, k))
    mega, power = fair_hit_pmf(45), fair_hit_pmf(55)
    assert mega.sum() == pytest.approx(1) and power.sum() == pytest.approx(1)
    assert mega[4:].sum() == pytest.approx((15 * 741 + 6 * 39 + 1) / comb(45, 6))
    assert power[4:].sum() == pytest.approx((15 * 1176 + 6 * 49 + 1) / comb(55, 6))


def test_hit_count_rejects_tickets_that_break_the_rules():
    assert hit_count([1, 2, 3, 4, 5, 6], [4, 5, 6, 7, 8, 9], 45) == 3
    for ticket in ([1, 1, 2, 3, 4, 5], [0, 1, 2, 3, 4, 5], [1, 2, 3, 4, 5, 46]):
        with pytest.raises(ValueError):
            hit_count(ticket, [4, 5, 6, 7, 8, 9], 45)


def test_summary_counts_draws_and_uses_exact_binomial_tails():
    hits = [0] * 300 + [1] * 60 + [3] * 3 + [4] * 2
    out = summarize_hits(hits, 45)
    assert out['draws'] == 365 and out['counts'][:5] == [300, 60, 0, 3, 2]
    ge4 = out['levels']['ge4']
    p0 = fair_hit_pmf(45)[4:].sum()
    assert ge4['reached'] == 2 and ge4['expected'] == pytest.approx(365 * p0)
    assert ge4['p_value_greater'] == pytest.approx(stats.binom.sf(1, 365, p0))
    assert out['levels']['ge3']['reached'] == 5
    low, high = clopper_pearson(0, 382)
    assert low == 0 and high == pytest.approx(1 - 0.025 ** (1 / 382))


def test_fair_tickets_are_not_called_better_and_cheating_tickets_are():
    rng = np.random.default_rng(1)
    draws = [sorted(rng.choice(45, 6, replace=False) + 1) for _ in range(2000)]
    fair = [hit_count(sorted(rng.choice(45, 6, replace=False) + 1), d, 45) for d in draws]
    cheat = [hit_count(list(d[:4]) + [v for v in range(1, 46) if v not in d][:2], d, 45) for d in draws]
    assert summarize_hits(fair, 45)['levels']['ge3']['p_value_greater'] > 0.01
    assert summarize_hits(cheat, 45)['levels']['ge4']['p_value_greater'] < 1e-12


def test_power_analysis_is_consistent_with_the_exact_test():
    p0 = float(fair_hit_pmf(45)[4:].sum())
    small, large = detectable_lift(p0, 382), detectable_lift(p0, 3000)
    assert large['lift'] < small['lift']
    c = small['critical_reached']
    assert stats.binom.sf(c - 1, 382, p0) <= 0.05 < stats.binom.sf(c - 2, 382, p0)
    assert stats.binom.sf(c - 1, 382, small['rate']) == pytest.approx(0.8, abs=1e-6)
    needed = draws_needed(p0, 2.0)
    crit = detectable_lift(p0, needed)
    assert crit['lift'] <= 2.0 + 1e-9


def _power(p0: float, lift: float, draws: int) -> float:
    c = detectable_lift(p0, draws)['critical_reached']
    return float(stats.binom.sf(c - 1, draws, lift * p0))


def test_draws_needed_is_the_smallest_sample_despite_the_sawtooth_power():
    """Công suất phép kiểm rời rạc răng cưa: tìm nhị phân trả số kỳ quá lớn (Mega ×2: 6.899 thay vì 6.502)."""
    p0, lift = 0.05, 2.0
    needed = draws_needed(p0, lift)
    assert _power(p0, lift, needed) >= 0.8
    assert all(_power(p0, lift, n) < 0.8 for n in range(1, needed))
    mega = float(fair_hit_pmf(45)[4:].sum())
    assert draws_needed(mega, 2.0) < 6899


def test_poisson_binomial_reduces_to_binomial():
    assert poisson_binomial_sf(3, [0.1] * 20) == pytest.approx(stats.binom.sf(2, 20, 0.1))
    assert poisson_binomial_sf(0, [0.3, 0.6]) == pytest.approx(1)


def test_portfolio_separates_per_ticket_from_any_ticket_and_needs_fixed_size():
    rng = np.random.default_rng(2)
    drawn = [sorted(rng.choice(45, 6, replace=False) + 1) for _ in range(30)]
    single = portfolio_summary([[[1, 2, 3, 4, 5, 6]]] * 30, drawn, 45, simulations=40_000)
    fair = fair_hit_pmf(45)
    assert single['any_ticket']['ge3']['fair_rate'] == pytest.approx(fair[3:].sum(), rel=1e-12)
    assert single['exact_draws'] == 30 and single['any_ticket']['ge3']['monte_carlo_se'] == 0
    copies = portfolio_summary([[[1, 2, 3, 4, 5, 6]] * 5] * 30, drawn, 45, simulations=40_000)
    assert copies['any_ticket']['ge3']['fair_rate'] == pytest.approx(single['any_ticket']['ge3']['fair_rate'])
    assert copies['mean_pairwise_overlap'] == 6 and copies['mean_coverage'] == pytest.approx(0.2)
    spread = portfolio_summary([[[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]] * 30, drawn, 45, simulations=40_000)
    assert spread['any_ticket']['ge3']['fair_rate'] > single['any_ticket']['ge3']['fair_rate']
    spread_mc = portfolio_summary([[[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]] * 30, drawn, 45, simulations=40_000, exact_limit=0)
    assert spread_mc['monte_carlo_draws'] == 30
    assert spread_mc['any_ticket']['ge3']['fair_rate'] == pytest.approx(spread['any_ticket']['ge3']['fair_rate'], abs=0.003)
    ge3 = spread['any_ticket']['ge3']
    best = [max(hit_count(t, d, 45) for t in ([1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12])) for d in drawn]
    assert ge3['p_value_greater'] == pytest.approx(predictable_p_value([b >= 3 for b in best], [ge3['fair_rate']] * 30), rel=1e-9)
    with pytest.raises(ValueError):
        portfolio_summary([[[1, 2, 3, 4, 5, 6]], [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]], drawn[:2], 45)


def test_monte_carlo_error_accounts_for_simulations_shared_by_every_draw():
    """Cùng một danh mục trên 30 kỳ: sai số của tổng là 30 × sai số một kỳ, không phải √30 ×."""
    rng = np.random.default_rng(9)
    drawn = [sorted(rng.choice(45, 6, replace=False) + 1) for _ in range(30)]
    one = portfolio_summary([[[1, 2, 3, 4, 5, 6]]], drawn[:1], 45, simulations=20_000, exact_limit=0)
    many = portfolio_summary([[[1, 2, 3, 4, 5, 6]]] * 30, drawn, 45, simulations=20_000, exact_limit=0)
    assert many['monte_carlo_draws'] == 30 and one['any_ticket']['ge3']['monte_carlo_se'] > 0
    assert many['any_ticket']['ge3']['monte_carlo_se'] == pytest.approx(30 * one['any_ticket']['ge3']['monte_carlo_se'], rel=1e-6)


def test_draws_needed_scans_up_to_the_limit_before_giving_up():
    """Mốc nhân đôi vượt ``limit`` không được bỏ đoạn giữa: p₀ = 0,1, ×2 cần 78 kỳ, ``limit`` = 100 (mốc 64 chưa đủ)."""
    p0, lift = 0.1, 2.0
    reached = [n for n in range(1, 201) if _power(p0, lift, n) >= 0.8]
    assert reached[0] == 78
    for limit in range(1, 201):
        expected = reached[0] if reached[0] <= limit else None
        assert draws_needed(p0, lift, limit=limit) == expected, limit


def test_detectable_lift_reports_an_unattainable_sample_instead_of_lift_one_over_p0():
    """Một kỳ với p₀ = 0,1 cần 2 kỳ đạt để bác bỏ: công suất bằng 0 ở mọi tỷ lệ, không phải "phát hiện ×10"."""
    out = detectable_lift(0.1, 1)
    assert out['critical_reached'] == 2 and out['attainable'] is False
    assert out['rate'] is None and out['lift'] is None
    ok = detectable_lift(0.1, 30)
    assert ok['attainable'] is True and ok['critical_reached'] <= 30
    assert stats.binom.sf(ok['critical_reached'] - 1, 30, ok['rate']) == pytest.approx(0.8, abs=1e-6)


def _enumerated_tail(tickets, n, k):
    counts = np.zeros(k + 1)
    for drawn in combinations(range(1, n + 1), k):
        counts[max(len(set(drawn) & set(t)) for t in tickets)] += 1
    return counts[::-1].cumsum()[::-1] / comb(n, k)


@pytest.mark.parametrize('tickets', [
    [[1, 2, 3, 4], [3, 4, 5, 6], [7, 8, 9, 10], [1, 5, 9, 11]],
    [[1, 2, 3, 4], [1, 2, 3, 5], [1, 2, 3, 6]],
    [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]],
    [[2, 4, 6, 8]] * 3,
])
def test_any_ticket_tail_matches_enumeration_of_every_draw(tickets):
    """Phân phối của số khớp TỐT NHẤT trong danh mục khớp liệt kê mọi C(12, 4) kết quả."""
    np.testing.assert_allclose(any_ticket_tail(tickets, 12, 4), _enumerated_tail(tickets, 12, 4), rtol=1e-12)
    assert any_ticket_tail(tickets, 12, 4, limit=1) is None


def test_rare_portfolio_hits_get_their_exact_null_not_zero():
    """Một vé trúng đủ 6 số: mốc là 1/C(45, 6), không phải 0 vì 20.000 mô phỏng chưa gặp lần nào."""
    six = portfolio_summary([[[1, 2, 3, 4, 5, 6]]], [[1, 2, 3, 4, 5, 6]], 45)['any_ticket']['ge6']
    assert six['fair_rate'] == pytest.approx(1 / comb(45, 6), rel=1e-12)
    assert six['p_value_fixed_portfolios'] == pytest.approx(1 / comb(45, 6), rel=1e-12)
    assert 0 < six['p_value_greater'] < 1
    disjoint = [[6 * i + j for j in range(1, 7)] for i in range(5)]
    five = portfolio_summary([disjoint], [[1, 2, 3, 4, 5, 6]], 45)['any_ticket']
    assert five['ge6']['fair_rate'] == pytest.approx(5 / comb(45, 6), rel=1e-12)
    assert five['ge5']['fair_rate'] == pytest.approx(5 * fair_hit_pmf(45)[5:].sum(), rel=1e-12)
    fallback = portfolio_summary([disjoint], [[1, 2, 3, 4, 5, 6]], 45, exact_limit=0)['any_ticket']['ge6']
    assert 1 / comb(45, 6) <= fallback['fair_rate'] <= 5 / comb(45, 6) and fallback['p_value_greater'] > 0


#: p_t phụ thuộc kỳ trước (danh mục học lại theo kết quả): sau một lần đạt, kỳ sau chắc chắn đạt.
ADAPTIVE = {(): 0.08, (0,): 0.08, (1,): 1.0, (0, 0): 0.5, (0, 1): 0.25, (1, 0): 0.5, (1, 1): 0.5}


def _exact_rejection(rule, design, horizon, alpha=0.05):
    """P(rule ≤ α) dưới H₀, liệt kê mọi dãy kết quả: P(X_t = 1 | quá khứ) = design[quá khứ]."""
    total = 0.0
    for xs in product((0, 1), repeat=horizon):
        prob, ps = 1.0, []
        for t in range(horizon):
            ps.append(design[xs[:t]])
            prob *= ps[-1] if xs[t] else 1 - ps[-1]
        if prob and rule(xs, ps) <= alpha:
            total += prob
    return total


def test_adaptive_portfolios_need_a_p_value_valid_for_predictable_probabilities():
    """Poisson–nhị thức trên dãy p đã thực hiện bác bỏ 5,84% ở α = 5% khi p_t học theo kết quả; e-process không vượt α."""
    pb = _exact_rejection(lambda xs, ps: poisson_binomial_sf(sum(xs), ps), ADAPTIVE, 3)
    assert pb == pytest.approx(0.0584, abs=1e-4)
    assert _exact_rejection(predictable_p_value, ADAPTIVE, 3) <= 0.05
    rng = np.random.default_rng(5)
    for _ in range(200):
        design = {h: float(rng.choice([0.01, 0.05, 0.1, 0.3, 0.6, 1.0])) for t in range(4) for h in product((0, 1), repeat=t)}
        for alpha in (0.05, 0.2):
            assert _exact_rejection(predictable_p_value, design, 4, alpha) <= alpha + 1e-12


def test_the_predictable_p_value_detects_a_real_lift_and_impossible_hits():
    rng = np.random.default_rng(3)
    p = rng.uniform(0.02, 0.2, 400)
    assert predictable_p_value(rng.random(400) < 3 * p, p) < 1e-6
    assert predictable_p_value(rng.random(400) < p, p) > 0.05
    assert predictable_p_value([False, True], [0.5, 0.0]) == 0
    with pytest.raises(ValueError):
        predictable_p_value([True], [0.1], lifts=[1.0])
