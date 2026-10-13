"""Challenger Mega/Power: đặc trưng nhân quả, luật k-trong-n đúng ràng buộc, học được tín hiệu cài sẵn."""
from itertools import combinations

import numpy as np
import pytest

from vlm.forecast import challengers as ch


def _fair(t: int, n: int = 45, k: int = 6, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = np.zeros((t, n), dtype=bool)
    for row in x:
        row[rng.choice(n, k, replace=False)] = True
    return x


def _planted(t: int, eta: np.ndarray, k: int, seed: int = 1) -> np.ndarray:
    """Rút đúng luật conditional Bernoulli với log-trọng số η (hàng t)."""
    from vietlott_engine.game_theory.popularity import sample_product_subsets

    rng = np.random.default_rng(seed)
    x = np.zeros((t, eta.shape[1]), dtype=bool)
    for i in range(t):
        x[i, sample_product_subsets(np.exp(eta[i]), k, 1, rng)[0] - 1] = True
    return x


def test_features_of_draw_t_never_read_draw_t_or_later():
    x = _fair(80)
    weekdays = np.arange(81) % 7
    base = ch.causal_features(x, weekdays)
    for t in (10, 40, 79):
        changed = x.copy()
        changed[t:] = np.roll(changed[t:], 7, axis=1)
        np.testing.assert_array_equal(ch.causal_features(changed, weekdays)[: t + 1], base[: t + 1])
    assert base.shape == (81, 45, len(ch.FEATURES)) and np.isfinite(base).all()


def test_lag_link_counts_other_numbers_of_the_previous_draw_not_itself():
    x = np.zeros((4, 6), dtype=bool)
    for t, row in enumerate(([0, 3], [0, 2], [0, 1], [0, 3])):   # số 1 về cả bốn kỳ
        x[t, row] = True
    feat = ch.causal_features(x, np.zeros(5, dtype=int))[4]
    link = feat[:, ch.FEATURES.index('lag_link')]
    p0 = 2 / 6

    def lift(together: int, base: int) -> float:
        rate = (together + 20 * p0) / (base + 20)
        return float(np.log(rate / (1 - rate)) - np.log(p0 / (1 - p0)))

    # Số 1 (trong kỳ trước) chỉ có bạn là số 4: 4 về kỳ 1 rồi 1 về kỳ 2 — một lần trên một lần.
    # Nếu tính cả "1 → 1" (ba lần lặp) thì đó là lag1, không phải đồng xuất hiện.
    assert link[0] == pytest.approx(lift(1, 1))
    # Số 2 ngoài kỳ trước: bạn 1 (1 → 2 một lần trên ba) và 4 (chưa lần nào trên một).
    assert link[1] == pytest.approx((lift(1, 3) + lift(0, 1)) / 2)


def test_conditional_bernoulli_law_is_normalised_and_fair_at_zero():
    n, k = 7, 3
    rng = np.random.default_rng(3)
    eta = rng.normal(0, 0.7, n)
    total = 0.0
    for subset in combinations(range(n), k):
        row = np.zeros((1, n), dtype=bool)
        row[0, list(subset)] = True
        main, _ = ch.cb_log_likelihood(eta[None], row)
        total += np.exp(main[0])
        bonus_total = 0.0
        for b in set(range(n)) - set(subset):
            _, extra = ch.cb_log_likelihood(eta[None], row, np.array([b + 1]))
            bonus_total += np.exp(extra[0])
        assert bonus_total == pytest.approx(1)
    assert total == pytest.approx(1)
    pi = ch.cb_marginals(eta[None], k)[0]
    assert pi.sum() == pytest.approx(k) and ((pi > 0) & (pi < 1)).all()
    x = _fair(5, n, k)
    main, extra = ch.cb_log_likelihood(np.zeros((5, n)), x, np.array([next(i + 1 for i in range(n) if not r[i]) for r in x]))
    fair_main, fair_bonus = ch.fair_log_likelihood(n, k, True)
    np.testing.assert_allclose(main, fair_main)
    np.testing.assert_allclose(extra, fair_bonus)
    np.testing.assert_allclose(ch.cb_marginals(np.zeros((1, n)), k), k / n)


def test_temperature_keeps_the_game_constraints():
    eta = np.random.default_rng(4).normal(0, 1, (3, 45))
    for tau in (0.0, 0.3, 1.0, 1.7):
        pi = ch.cb_marginals(tau * eta, 6)
        np.testing.assert_allclose(pi.sum(axis=1), 6)
        assert ((pi >= 0) & (pi <= 1)).all()


def test_conditional_logit_gradient_and_planted_signal_recovery():
    t, n, k = 600, 20, 4
    rng = np.random.default_rng(5)
    phi = rng.normal(0, 1, (t, n, 2))
    beta = np.array([0.8, 0.0])
    x = _planted(t, phi @ beta, k)
    fitted = ch.fit_conditional_logit(phi, x, l2=0.01)
    assert fitted[0] == pytest.approx(0.8, abs=0.15) and abs(fitted[1]) < 0.15
    fair = ch.fit_conditional_logit(phi, _fair(t, n, k, seed=6), l2=0.01)
    assert np.abs(fair).max() < 0.15


def test_walk_forward_scores_each_draw_before_its_label():
    t, n, k = 200, 20, 4
    rng = np.random.default_rng(7)
    phi = rng.normal(0, 1, (t, n, 2))
    x = _fair(t, n, k)
    eta = ch.causal_walk_forward(phi, x, [0, 1], 0.1, 100, 200, 10)
    for cut in (120, 155, 199):
        changed = x.copy()
        changed[cut:] = np.roll(changed[cut:], 3, axis=1)
        again = ch.causal_walk_forward(phi, changed, [0, 1], 0.1, 100, 200, 10)
        np.testing.assert_allclose(again[: cut - 100 + 1], eta[: cut - 100 + 1])


def test_shrink_and_temperature_find_a_planted_hot_set_and_nothing_in_fair_draws():
    t, n, k = 900, 45, 6
    eta = np.zeros((t, n))
    eta[:, :6] = 0.6
    planted = _planted(t, eta, k)
    score = ch.shrink_scores(planted, None, 20.0)
    assert ch.fit_temperature(score[400:t], planted[400:], bounds=(-3, 3)) > 0.5
    fair = _fair(t, n, k, seed=8)
    assert abs(ch.fit_temperature(ch.shrink_scores(fair, None, 20.0)[400:t], fair[400:], bounds=(-3, 3))) < 0.8
