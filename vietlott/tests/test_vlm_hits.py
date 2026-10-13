"""Số khớp H: mốc siêu bội, khoảng tin cậy, công suất, danh mục nhiều vé."""
from itertools import combinations
from math import comb

import numpy as np
import pytest
from scipy import stats

from vlm.forecast.hits import (
    clopper_pearson, detectable_lift, draws_needed, fair_hit_pmf, hit_count, poisson_binomial_sf,
    portfolio_summary, summarize_hits,
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
    assert single['any_ticket']['ge3']['fair_rate'] == pytest.approx(fair[3:].sum(), abs=0.003)
    copies = portfolio_summary([[[1, 2, 3, 4, 5, 6]] * 5] * 30, drawn, 45, simulations=40_000)
    assert copies['any_ticket']['ge3']['fair_rate'] == pytest.approx(single['any_ticket']['ge3']['fair_rate'])
    assert copies['mean_pairwise_overlap'] == 6 and copies['mean_coverage'] == pytest.approx(0.2)
    spread = portfolio_summary([[[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]] * 30, drawn, 45, simulations=40_000)
    assert spread['any_ticket']['ge3']['fair_rate'] > single['any_ticket']['ge3']['fair_rate']
    with pytest.raises(ValueError):
        portfolio_summary([[[1, 2, 3, 4, 5, 6]], [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]], drawn[:2], 45)


def test_monte_carlo_error_accounts_for_simulations_shared_by_every_draw():
    """Cùng một danh mục trên 30 kỳ: sai số của tổng là 30 × sai số một kỳ, không phải √30 ×."""
    rng = np.random.default_rng(9)
    drawn = [sorted(rng.choice(45, 6, replace=False) + 1) for _ in range(30)]
    one = portfolio_summary([[[1, 2, 3, 4, 5, 6]]], drawn[:1], 45, simulations=20_000)
    many = portfolio_summary([[[1, 2, 3, 4, 5, 6]]] * 30, drawn, 45, simulations=20_000)
    assert many['any_ticket']['ge3']['monte_carlo_se'] == pytest.approx(30 * one['any_ticket']['ge3']['monte_carlo_se'], rel=1e-6)
