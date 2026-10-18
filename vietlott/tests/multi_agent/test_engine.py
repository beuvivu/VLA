import asyncio
import copy
import tempfile
import unittest
import sqlite3
import json
from contextlib import closing
from pathlib import Path


class EngineContractTests(unittest.TestCase):
    def make(self, *args, **kwargs):
        from vlm.multi_agent.engine import PredictiveEngine
        return PredictiveEngine(*args, **kwargs)

    def test_engine_exists(self):
        self.assertTrue(callable(self.make(5, 2).predict))

    def test_cold_start_is_coherent_uniform(self):
        async def run():
            engine = self.make(5, 2)
            p = await engine.predict(0)
            self.assertEqual(p['mode'], 'uniform_baseline')
            self.assertAlmostEqual(p['selected_set_probability'], .1)
            self.assertAlmostEqual(sum(p['marginals']), 2)
            self.assertEqual(len(p['selected']), 2)
            self.assertAlmostEqual(p['expected_matches'], .8)
            engine.close()
        asyncio.run(run())

    def test_prediction_immutable_idempotency_and_order(self):
        async def run():
            e = self.make(5, 2)
            p = await e.predict(0)
            original = copy.deepcopy(p)
            p['selected'][0] = 999
            self.assertEqual(await e.predict(0), original)
            with self.assertRaises(ValueError):
                await e.predict(1)
            r = await e.observe(0, [1, 3])
            self.assertEqual(await e.observe(0, [3, 1]), r)
            with self.assertRaises(ValueError):
                await e.observe(0, [1, 4])
            self.assertEqual(await e.predict(0), original)
            self.assertEqual((await e.predict(1))['cycle'], 1)
            e.close()
        asyncio.run(run())

    def test_restart_preserves_pending_and_learning(self):
        async def run():
            with tempfile.TemporaryDirectory() as d:
                path = str(Path(d) / 'state.sqlite')
                e = self.make(5, 2, path)
                for t in range(4):
                    await e.predict(t)
                    await e.observe(t, [t % 5, (t + 1) % 5])
                p = await e.predict(4)
                e.close()
                e = self.make(5, 2, path)
                self.assertEqual(await e.predict(4), p)
                await e.observe(4, [0, 1])
                e.close()
                e = self.make(5, 2, path)
                self.assertEqual((await e.predict(5))['cycle'], 5)
                e.close()
        asyncio.run(run())

    def test_invalid_feedback_does_not_mutate(self):
        async def run():
            e = self.make(5, 2)
            p = await e.predict(0)
            for bad in ([1, 1], [True, 2], [1, 8], [1.0, 2]):
                with self.assertRaises(ValueError):
                    await e.observe(0, bad)
                self.assertEqual(await e.predict(0), p)
            e.close()
        asyncio.run(run())

    def test_stale_writer_is_rejected_then_can_retry(self):
        async def run():
            with tempfile.TemporaryDirectory() as d:
                path = str(Path(d) / 'state.sqlite')
                a, b = self.make(5, 2, path), self.make(5, 2, path)
                p = await a.predict(0)
                with self.assertRaises(RuntimeError):
                    await b.predict(0)
                self.assertEqual(await b.predict(0), p)
                a.close()
                b.close()
        asyncio.run(run())

    def test_config_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / 'state.sqlite')
            e = self.make(5, 2, path)
            with self.assertRaises(ValueError):
                self.make(6, 2, path)
            e.close()

    def test_inconsistent_checkpoint_pending_is_rejected(self):
        async def run():
            with tempfile.TemporaryDirectory() as d:
                path = str(Path(d) / 'state.sqlite')
                e = self.make(5, 2, path)
                await e.predict(0)
                e.close()
                with closing(sqlite3.connect(path)) as connection, connection:
                    state = json.loads(connection.execute('SELECT payload FROM checkpoint').fetchone()[0])
                    state['pending']['public']['marginals'] = [1., 1., 0., 0., 0.]
                    connection.execute('UPDATE checkpoint SET payload=?', (json.dumps(state),))
                with self.assertRaises(ValueError):
                    self.make(5, 2, path)
        asyncio.run(run())

    def test_invalid_meta_checkpoint_is_rejected(self):
        from vlm.multi_agent.meta import MetaLearner
        meta = MetaLearner(5, 2)
        state = meta.state_dict()
        for key, value in [('losses', [[0]]), ('count', -1), ('log_e_value', float('nan'))]:
            bad = copy.deepcopy(state)
            bad[key] = value
            with self.assertRaises(ValueError):
                meta.load_state_dict(bad)
            self.assertEqual(meta.state_dict(), state)

    def test_certain_outcome_can_restart_without_negative_roundoff_loss(self):
        async def run():
            for n in (1, 6):
                with tempfile.TemporaryDirectory() as d:
                    path = str(Path(d) / 'certain.sqlite')
                    e = self.make(n, n, path)
                    await e.predict(0)
                    result = await e.observe(0, list(range(n)))
                    self.assertGreaterEqual(result['log_loss'], 0)
                    e.close()
                    e = self.make(n, n, path)
                    self.assertEqual((await e.predict(1))['selected_set_probability'], 1)
                    e.close()
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
