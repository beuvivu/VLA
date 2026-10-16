"""Exact distribution and deterministic expert learning checks."""

import asyncio
import copy
import itertools
import json
import math
import unittest

import numpy as np

from vlm.multi_agent.models import AlgorithmEnsemble, SubsetDistribution


class SubsetDistributionTests(unittest.TestCase):
    def test_matches_enumeration_for_every_cardinality(self):
        logits = np.array([-2.2, 0.1, 1.8, 0.5, -0.7])
        for k in range(1, len(logits) + 1):
            with self.subTest(k=k):
                distribution = SubsetDistribution(logits, k)
                subsets = list(itertools.combinations(range(5), k))
                raw = np.array([sum(logits[list(s)]) for s in subsets])
                normalizer = np.logaddexp.reduce(raw)
                expected = np.zeros(5)
                for subset, value in zip(subsets, raw):
                    probability = math.exp(value - normalizer)
                    expected[list(subset)] += probability
                    self.assertAlmostEqual(distribution.log_prob(subset), value - normalizer, places=12)
                np.testing.assert_allclose(distribution.marginals, expected, atol=1e-12)
                self.assertAlmostEqual(float(distribution.marginals.sum()), k, places=12)

    def test_extreme_logits_and_shift_invariance(self):
        for logits in ([1000, -1000, 999, -999, 0], [1e308, -1e308, 0, 1e308, -1e308]):
            for k in range(1, 6):
                distribution = SubsetDistribution(logits, k)
                self.assertTrue(np.all(np.isfinite(distribution.marginals)))
                self.assertTrue(np.all(distribution.marginals >= 0))
                self.assertTrue(np.all(distribution.marginals <= 1))
                self.assertAlmostEqual(float(distribution.marginals.sum()), k, places=12)
                self.assertLessEqual(distribution.log_prob(list(range(k))), 0)
        a = SubsetDistribution([-2, 0, 3, 1], 2)
        b = SubsetDistribution(np.array([-2, 0, 3, 1]) + 1e6, 2)
        np.testing.assert_allclose(a.marginals, b.marginals, atol=1e-12)
        self.assertEqual(SubsetDistribution([1e308] * 5, 5).log_prob(range(5)), 0)
        tied = SubsetDistribution([1e308, 1e308, 0, -1e308, -1e308], 4)
        self.assertAlmostEqual(tied.log_prob([0, 1, 2, 3]), -math.log(2), places=12)
        np.testing.assert_allclose(tied.marginals, [1, 1, 1, .5, .5])
        uniform_extreme = SubsetDistribution([1e308] * 5, 2)
        np.testing.assert_allclose(uniform_extreme.marginals, np.full(5, .4))
        self.assertAlmostEqual(uniform_extreme.log_prob([0, 4]), -math.log(10))

    def test_validation_and_defensive_marginals(self):
        for logits in ([0, math.nan], [0, math.inf], [], [[1, 2]]):
            with self.subTest(logits=logits), self.assertRaises(ValueError):
                SubsetDistribution(logits, 1)
        for k in (0, -1, 4, 1.2, True):
            with self.subTest(k=k), self.assertRaises(ValueError):
                SubsetDistribution([0, 0, 0], k)
        distribution = SubsetDistribution([0, 1, 2], 2)
        for outcome in ([0, 0], [0], [0, 3], [-1, 1], [True, 1], [0.0, 1.0]):
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                distribution.log_prob(outcome)
        marginal = distribution.marginals
        marginal[:] = 0
        self.assertAlmostEqual(float(distribution.marginals.sum()), 2)


class AlgorithmEnsembleTests(unittest.TestCase):
    def setUp(self):
        self.n, self.k = 5, 2
        self.model = AlgorithmEnsemble(self.n, self.k, seed=7)
        self.history = np.array([[1, 0, 1, 0, 0], [0, 1, 0, 1, 0], [1, 0, 1, 0, 0]], dtype=float)
        self.retrieved = np.full(self.n, self.k / self.n)

    def forecasts(self, history=None, retrieved=None):
        return asyncio.run(self.model.predict(self.history if history is None else history,
                                              self.retrieved if retrieved is None else retrieved))

    def test_predict_is_read_only_and_finite(self):
        before = copy.deepcopy(self.model.state_dict())
        history = self.history.copy()
        retrieved = self.retrieved.copy()
        first = self.forecasts()
        second = self.forecasts()
        self.assertEqual(first, second)
        self.assertEqual(len({f.name for f in first}), 3)
        self.assertEqual(before, self.model.state_dict())
        np.testing.assert_array_equal(history, self.history)
        np.testing.assert_array_equal(retrieved, self.retrieved)
        for forecast in first:
            self.assertEqual(len(forecast.logits), self.n)
            self.assertTrue(np.all(np.isfinite(forecast.logits)))
            self.assertAlmostEqual(float(SubsetDistribution(forecast.logits, self.k).marginals.sum()), self.k)
        json.dumps(before, allow_nan=False)

    def test_statistical_and_markov_experts_use_observed_patterns(self):
        repeated = np.tile([[1, 1, 0, 0, 0]], (30, 1))
        forecasts = self.forecasts(repeated)
        for forecast in forecasts[:2]:
            marginals = SubsetDistribution(forecast.logits, self.k).marginals
            self.assertGreater(float(marginals[:2].mean()), float(marginals[2:].mean()))
        self.assertGreater(forecasts[0].evidence['ngram_matches']['1'], 0)
        self.assertGreater(forecasts[1].evidence['transition_pairs'], 0)

    def test_online_neural_learning_reduces_pattern_loss(self):
        outcome = np.array([1, 0, 1, 0, 0])
        history = np.tile(outcome, (8, 1))
        before = self.forecasts(history)[2]
        loss_before = -SubsetDistribution(before.logits, self.k).log_prob([0, 2])
        for _ in range(150):
            self.model.learn(history, outcome)
        after = self.forecasts(history)[2]
        loss_after = -SubsetDistribution(after.logits, self.k).log_prob([0, 2])
        self.assertLess(loss_after, 0.2 * loss_before)
        self.assertTrue(np.all(np.isfinite(after.logits)))
        json.dumps(self.model.state_dict(), allow_nan=False)

    def test_state_round_trip_and_subsequent_learning_replay(self):
        self.model.learn(self.history, np.array([0, 1, 0, 1, 0]))
        state = json.loads(json.dumps(self.model.state_dict(), allow_nan=False))
        clone = AlgorithmEnsemble(self.n, self.k, seed=99)
        clone.load_state_dict(state)
        self.assertEqual(self.forecasts(), asyncio.run(clone.predict(self.history, self.retrieved)))
        outcome = np.array([1, 0, 0, 0, 1])
        self.model.learn(self.history, outcome)
        clone.learn(self.history, outcome)
        self.assertEqual(self.model.state_dict(), clone.state_dict())
        bad = copy.deepcopy(state)
        bad['weights']['w1'][0][0] = math.nan
        snapshot = clone.state_dict()
        with self.assertRaises(ValueError):
            clone.load_state_dict(bad)
        self.assertEqual(snapshot, clone.state_dict())

    def test_strict_input_validation_and_cold_start(self):
        forecasts = self.forecasts(np.empty((0, self.n)))
        self.assertTrue(all(np.all(np.isfinite(f.logits)) for f in forecasts))
        for history, retrieved in ((np.ones((1, self.n)), self.retrieved),
                                   (self.history, np.zeros(self.n)),
                                   (self.history, np.full(self.n, math.nan)),
                                   (self.history, np.array([-.1, .5, .5, .5, .6]))):
            with self.assertRaises(ValueError):
                self.forecasts(history, retrieved)
        with self.assertRaises(ValueError):
            self.model.learn(self.history, np.array([1, 1, 1, 0, 0]))


if __name__ == '__main__':
    unittest.main()
