"""Independent probability, prequential scoring, and transaction counterexamples."""
import asyncio
import copy
import itertools
import json
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np


class DistributionInvariants(unittest.TestCase):
    def test_identical_marginals_do_not_erase_mixture_dependence(self):
        from vlm.multi_agent.meta import mixture_log_prob, mixture_marginals
        from vlm.multi_agent.models import SubsetDistribution

        # The two components favor opposite pairs. Their mixture has uniform
        # inclusion marginals, but almost all mass on just two of six subsets.
        components = [SubsetDistribution([5, 5, -5, -5], 2),
                      SubsetDistribution([-5, -5, 5, 5], 2)]
        marginals = mixture_marginals(components, [.5, .5])
        self.assertTrue(np.allclose(marginals, [.5] * 4))
        masses = {subset: math.exp(mixture_log_prob(components, [.5, .5], subset))
                  for subset in itertools.combinations(range(4), 2)}
        self.assertAlmostEqual(sum(masses.values()), 1.0, places=12)
        self.assertGreater(masses[(0, 1)], .49)
        self.assertLess(masses[(0, 2)], .001)
        self.assertGreater(masses[(0, 1)] - 1 / 6, .3)


class MetaInvariants(unittest.TestCase):
    @staticmethod
    def oracle(logits, temperature, weights, outcome):
        """Small-space enumeration independent of the production DP."""
        subsets = list(itertools.combinations(range(len(logits[0])), len(outcome)))
        probabilities = []
        expert_probabilities = []
        for row in logits:
            masses = np.array([math.exp(sum(row[i] for i in subset) / temperature)
                               for subset in subsets])
            probabilities.append(masses / masses.sum())
            expert_probabilities.append(float(masses[subsets.index(tuple(outcome))] / masses.sum()))
        mixture = np.asarray(weights) @ np.asarray(probabilities)
        marginals = [sum(probability for subset, probability in zip(subsets, mixture) if i in subset)
                     for i in range(len(logits[0]))]
        return float(mixture[subsets.index(tuple(outcome))]), expert_probabilities, marginals

    def test_temperatures_and_context_are_scored_from_frozen_forecast(self):
        from vlm.multi_agent.meta import MetaLearner

        meta = MetaLearner(4, 2)
        logits = [[6, 2, -2, -6], [2, 4, -4, -2], [-3, 1, 3, -1], [0, 0, 0, 0]]
        frozen_weights = [.1, .2, .3, .4]
        outcome = (0, 1)
        candidates = [self.oracle(logits, temp, frozen_weights, outcome)
                      for temp in meta.temperatures]
        previous_temperature_losses = np.array([4., 1., 8.])
        previous_expert_losses = np.array([[1., 2., 3., 4.], [5., 6., 7., 8.]])
        meta.count = 20
        meta.temperature_losses = previous_temperature_losses.copy()
        meta.losses = previous_expert_losses.copy()
        self.assertEqual(meta.temperature(), 2.)
        # The pending forecast selected 4 before current meta state was updated.
        # Current context weights also differ from these recorded weights.
        pending = {'weights': frozen_weights, 'logits': logits, 'temperature': 4., 'context': 1,
                   'public': {'mode': 'adaptive', 'marginals': candidates[2][2]}}
        summary = meta.update(pending, outcome)
        expected_losses = np.array([-math.log(candidate[0]) for candidate in candidates])
        np.testing.assert_allclose(meta.temperature_losses,
                                   .98 * previous_temperature_losses + expected_losses)
        np.testing.assert_allclose(meta.losses[0], previous_expert_losses[0])
        np.testing.assert_allclose(meta.losses[1],
                                   .98 * previous_expert_losses[1] - np.log(candidates[2][1]))
        self.assertAlmostEqual(summary['log_loss'], expected_losses[2], places=12)
        self.assertAlmostEqual(summary['shadow_log_gain'], math.log(6) - expected_losses[2], places=12)

    def test_evidence_accumulator_survives_diagnostic_retention_and_adverse_cycles(self):
        from vlm.multi_agent.meta import MetaLearner

        meta = MetaLearner(3, 1)
        row = [math.log(.6), math.log(.3), math.log(.1)]
        pending = {'weights': [.25] * 4, 'logits': [row[:] for _ in range(4)],
                   'temperature': 1., 'context': 0,
                   'public': {'mode': 'adaptive', 'marginals': [.6, .3, .1]}}
        for _ in range(300):
            meta.update(pending, [0])
        self.assertEqual(meta.count, 300)
        self.assertLess(len(meta.records), meta.count)
        self.assertAlmostEqual(meta.log_e_value, 300 * math.log(1.8), places=9)
        self.assertTrue(meta.evidence()['adaptive_enabled'])
        for _ in range(180):
            meta.update(pending, [2])
        self.assertAlmostEqual(meta.log_e_value,
                               300 * math.log(1.8) + 180 * math.log(.3), places=9)
        self.assertFalse(meta.evidence()['adaptive_enabled'])


class EngineInvariants(unittest.IsolatedAsyncioTestCase):
    def make(self, *args, **kwargs):
        from vlm.multi_agent.engine import PredictiveEngine
        return PredictiveEngine(*args, **kwargs)

    async def train(self, engine, count, n=5):
        for cycle in range(count):
            await engine.predict(cycle)
            await engine.observe(cycle, [cycle % n, (cycle + 2) % n])

    async def test_old_feedback_replay_preserves_new_pending_forecast(self):
        engine = self.make(5, 2)
        try:
            await engine.predict(0)
            feedback = await engine.observe(0, [0, 2])
            pending = await engine.predict(1)
            self.assertEqual(await engine.observe(0, [2, 0]), feedback)
            self.assertEqual(await engine.predict(1), pending)
            with self.assertRaises(ValueError):
                await engine.observe(0, [0, 3])
            self.assertEqual(await engine.predict(1), pending)
            await engine.observe(1, [1, 4])
        finally:
            engine.close()

    async def test_same_instance_concurrency_is_idempotent(self):
        engine = self.make(5, 2)
        try:
            predictions = await asyncio.gather(*(engine.predict(0) for _ in range(8)))
            self.assertTrue(all(p == predictions[0] for p in predictions))
            feedbacks = await asyncio.gather(*(engine.observe(0, [1, 4]) for _ in range(8)))
            self.assertTrue(all(r == feedbacks[0] for r in feedbacks))
            self.assertEqual((await engine.predict(1))['evidence']['cycles_scored'], 1)
        finally:
            engine.close()

    async def test_sqlite_failure_restores_all_learned_state_before_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = self.make(5, 2, str(Path(directory) / 'fault.sqlite'))
            control = self.make(5, 2)
            try:
                await self.train(engine, 7)
                await self.train(control, 7)
                pending = await engine.predict(7)
                self.assertEqual(await control.predict(7), pending)
                checkpoint = copy.deepcopy(engine.store.load())
                # This aborts after StateStore has updated its checkpoint inside
                # the transaction, exercising SQLite rollback and live rollback.
                engine.store.connection.execute('''
                    CREATE TRIGGER reject_feedback BEFORE INSERT ON outcomes
                    BEGIN SELECT RAISE(ABORT, 'injected disk constraint'); END
                ''')
                with self.assertRaises(sqlite3.IntegrityError):
                    await engine.observe(7, [1, 3])
                self.assertEqual(engine.store.load(), checkpoint)
                self.assertIsNone(engine.store.lookup('outcomes', 7))
                self.assertEqual(await engine.predict(7), pending)
                engine.store.connection.execute('DROP TRIGGER reject_feedback')
                self.assertEqual(await engine.observe(7, [1, 3]),
                                 await control.observe(7, [1, 3]))
                # A missed neural update/RNG rollback may only appear next time.
                self.assertEqual(await engine.predict(8), await control.predict(8))
            finally:
                engine.close()
                control.close()

    async def test_restart_matches_uninterrupted_learning_across_many_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'restart.sqlite')
            durable, control = self.make(5, 2, path), self.make(5, 2)
            try:
                for cycle in range(24):
                    prediction = await durable.predict(cycle)
                    self.assertEqual(prediction, await control.predict(cycle))
                    if cycle % 3 == 0:
                        durable.close()
                        durable = self.make(5, 2, path)
                        self.assertEqual(await durable.predict(cycle), prediction)
                    outcome = [cycle % 5, (cycle + 2) % 5]
                    self.assertEqual(await durable.observe(cycle, outcome),
                                     await control.observe(cycle, outcome))
                    if cycle % 4 == 0:
                        durable.close()
                        durable = self.make(5, 2, path)
            finally:
                durable.close()
                control.close()

    async def test_shadow_likelihood_ratio_has_conditional_uniform_mean_one(self):
        # Rebuild the exact same past, then integrate the issued shadow score
        # over ALL possible next outcomes. Product-of-marginals scoring fails
        # this martingale prerequisite even if its inclusion marginals sum k.
        ratios = []
        deployed_masses = []
        for outcome in itertools.combinations(range(4), 2):
            engine = self.make(4, 2)
            try:
                for cycle in range(6):
                    await engine.predict(cycle)
                    await engine.observe(cycle, [0, 1])
                prediction = await engine.predict(6)
                summary = await engine.observe(6, outcome)
                self.assertEqual(prediction['mode'], 'uniform_baseline')
                self.assertAlmostEqual(summary['log_loss'], math.log(6), places=12)
                target = np.array([float(i in outcome) for i in range(4)])
                expected_brier = float(np.mean((np.array(prediction['marginals']) - target) ** 2))
                self.assertAlmostEqual(summary['brier'], expected_brier, places=12)
                ratios.append(math.exp(summary['shadow_log_gain']))
                deployed_masses.append(math.exp(-summary['log_loss']))
            finally:
                engine.close()
        self.assertAlmostEqual(sum(ratios) / len(ratios), 1, places=11)
        self.assertAlmostEqual(sum(deployed_masses), 1, places=11)
        self.assertGreater(max(ratios) - min(ratios), .1)

    async def test_public_outputs_remain_finite_and_joint_probability_coherent(self):
        engine = self.make(4, 2)
        try:
            for cycle in range(72):
                prediction = await engine.predict(cycle)
                json.dumps(prediction, allow_nan=False)
                selected = prediction['selected']
                marginals = np.asarray(prediction['marginals'])
                probability = prediction['selected_set_probability']
                self.assertEqual(len(set(selected)), 2)
                self.assertTrue(np.all((marginals >= 0) & (marginals <= 1)))
                self.assertAlmostEqual(float(marginals.sum()), 2, places=10)
                self.assertAlmostEqual(prediction['expected_matches'],
                                       float(marginals[selected].sum()), places=10)
                self.assertGreaterEqual(probability, max(0, float(marginals[selected].sum()) - 1) - 1e-10)
                self.assertLessEqual(probability, float(marginals[selected].min()) + 1e-10)
                weights = prediction['expert_weights']
                self.assertTrue(all(weight > 0 for weight in weights.values()))
                self.assertAlmostEqual(sum(weights.values()), 1, places=12)
                summary = await engine.observe(cycle, [0, 1])
                json.dumps(summary, allow_nan=False)
                self.assertGreaterEqual(summary['log_loss'], -1e-10)
                self.assertGreaterEqual(summary['brier'], 0)
                self.assertLessEqual(summary['brier'], 1)
        finally:
            engine.close()


class StoreInvariants(unittest.TestCase):
    def test_duplicate_ledger_insert_cannot_advance_checkpoint(self):
        from vlm.multi_agent.store import StateStore

        store = StateStore(':memory:', {'n': 5, 'k': 2})
        try:
            revision = store.commit(0, {'value': 'first'}, forecast={'cycle': 0, 'x': 1})
            with self.assertRaises(sqlite3.IntegrityError):
                store.commit(revision, {'value': 'must roll back'},
                             forecast={'cycle': 0, 'x': 2})
            self.assertEqual(store.load(), (revision, {'value': 'first'}))
            self.assertEqual(store.lookup('forecasts', 0), {'cycle': 0, 'x': 1})
        finally:
            store.close()


if __name__ == '__main__':
    unittest.main()
