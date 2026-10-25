"""Xác suất biên bộ số phải ổn định cả khi một số có trọng số lớn hơn hẳn."""
from itertools import combinations

import numpy as np
import pytest

from vietlott_engine.core.products import ProductCode
from vietlott_engine.forecast.data import Series, SetSpec
from vietlott_engine.forecast.engine import Forecaster, inclusion_probabilities
from vietlott_engine.game_theory.popularity import sample_product_subsets
from vlm.forecast.distribution import Law


def test_small_biased_mixture_marginals_match_enumerated_subset_probabilities():
    weights = np.exp(np.array([[2., -2., -2., -2., -2., -2., -2., -2.],
                               [-2., -2., -2., -2., -2., -2., -2., 2.]]))
    subsets = list(combinations(range(8), 6))
    probabilities = np.array([[np.prod(row[list(subset)]) for subset in subsets] for row in weights])
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    expected = np.zeros((2, 8))
    for i, subset in enumerate(subsets):
        expected[:, list(subset)] += probabilities[:, i, None]
    law = Law(SetSpec(8, 6), weights, np.array([.6, .4]))
    np.testing.assert_allclose(law.marginals(), np.array([.6, .4]) @ expected, rtol=0, atol=2e-13)
    for i, subset in enumerate(subsets):
        assert law.probability([v + 1 for v in subset]) == pytest.approx(np.array([.6, .4]) @ probabilities[:, i])


def test_keno_one_heavy_number_has_the_analytic_inclusion_probability():
    weights = np.exp(np.array([[2., *([-2.] * 79)]]))
    # Chia hai nhánh có/không có số nặng: r*C(79,19) và C(79,20).
    ratio = np.exp(4.)
    heavy = ratio * 20 / (60 + ratio * 20)
    expected = np.array([heavy, *([(20 - heavy) / 79] * 79)])
    np.testing.assert_allclose(inclusion_probabilities(weights, 20)[0], expected, rtol=0, atol=2e-13)
    law = Law(SetSpec(80, 20), weights, np.array([1.]))
    np.testing.assert_allclose(law.marginals(), expected, rtol=0, atol=2e-13)


@pytest.mark.parametrize('weights,expected', [
    (np.full(80, 1e300), np.full(80, .25)),
    (np.full(80, 1e-300), np.full(80, .25)),
    (np.array([1e300, *([1e-300] * 79)]), np.array([1., *([19 / 79] * 79)])),
    (np.array([*([1e300] * 20), *([1e-300] * 60)]), np.array([*([1.] * 20), *([0.] * 60)])),
])
def test_extreme_positive_finite_weights_keep_valid_marginals(weights, expected):
    with np.errstate(over='raise', invalid='raise', divide='raise'):
        actual = inclusion_probabilities(weights[None, :], 20)[0]
    np.testing.assert_allclose(actual, expected, rtol=0, atol=2e-12)
    assert np.isfinite(actual).all() and np.all((0 <= actual) & (actual <= 1))
    assert actual.sum() == pytest.approx(20, abs=2e-12)


def test_fair_and_sampled_subset_laws_agree_with_their_marginals():
    np.testing.assert_allclose(inclusion_probabilities(np.ones((1, 80)), 20), .25, rtol=0, atol=2e-14)
    weights = np.exp(np.array([2., -2., -2., -2., -2., -2., -2., -2.]))
    draws = sample_product_subsets(weights, 6, 30_000, np.random.default_rng(41))
    rates = np.bincount(draws.ravel(), minlength=9)[1:] / len(draws)
    np.testing.assert_allclose(inclusion_probabilities(weights[None, :], 6)[0], rates, rtol=0, atol=.01)


def test_legacy_keno_forecast_keeps_probability_bounds_after_learning_a_bias():
    rng = np.random.default_rng(7)
    observations = np.zeros((1000, 80), dtype=bool)
    observations[:, 0] = True
    for row in observations:
        row[rng.choice(np.arange(1, 80), 19, replace=False)] = True
    series = Series(ProductCode.KENO, np.arange(1, 1001),
                    np.full(1000, np.datetime64('2026-10-01')),
                    {'main': {'X': observations, 'bonus': np.zeros(1000, dtype=np.int16)}})
    model = Forecaster('keno')
    model.update(series)
    forecast = model.forecast().components[0].set
    marginals = np.array([number.p for number in forecast.numbers])
    assert np.isfinite(marginals).all() and np.all((0 <= marginals) & (marginals <= 1))
    assert marginals.sum() == pytest.approx(20, abs=5e-5)  # Bản công bố làm tròn sáu chữ số.
    assert forecast.numbers[0].symbol == '1' and .95 < forecast.numbers[0].p < 1
