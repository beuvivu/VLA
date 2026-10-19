"""Behavioral checks for causal, bounded hybrid memory."""

import copy
import json
import unittest

import numpy as np

from vlm.multi_agent.memory import KnowledgeBaseManager


class MemoryTests(unittest.TestCase):
    def assert_valid_marginals(self, values, n, k):
        self.assertEqual(values.shape, (n,))
        self.assertTrue(np.all(np.isfinite(values)))
        self.assertTrue(np.all(values >= 0))
        self.assertTrue(np.all(values <= 1))
        self.assertAlmostEqual(float(values.sum()), k)

    def test_cold_start_is_uniform_with_empty_history(self):
        memory = KnowledgeBaseManager(5, 2)
        probabilities, matches = memory.retrieve()
        np.testing.assert_array_equal(probabilities, np.full(5, 0.4))
        self.assertEqual(matches, [])
        self.assertEqual(memory.history.shape, (0, 5))

    def test_recent_signal_uses_only_observed_outcomes(self):
        memory = KnowledgeBaseManager(4, 1, short_window=3)
        memory.ingest(0, [2])
        probabilities, matches = memory.retrieve()
        self.assert_valid_marginals(probabilities, 4, 1)
        self.assertGreater(probabilities[2], probabilities[0])
        self.assertEqual(matches, [])
        np.testing.assert_array_equal(memory.history, [[0, 0, 1, 0]])

    def test_context_is_captured_before_observing_the_result(self):
        left = KnowledgeBaseManager(4, 1)
        right = KnowledgeBaseManager(4, 1)
        for memory in (left, right):
            memory.ingest(0, [0])
        left.ingest(1, [1])
        right.ingest(1, [2])
        left_rule = left.state_dict()["rules"][0]
        right_rule = right.state_dict()["rules"][0]
        self.assertEqual(left_rule["context"], right_rule["context"])
        self.assertNotEqual(left_rule["outcome_counts"], right_rule["outcome_counts"])
        self.assertEqual(left_rule["cycle"], 1)
        self.assertEqual(left_rule["context_cutoff"], 0)
        self.assertEqual(left_rule["support"], 1)

    def test_matches_have_real_observed_support_and_causal_cutoffs(self):
        memory = KnowledgeBaseManager(5, 2, short_window=3)
        for cycle in range(12):
            memory.ingest(cycle, [0, 1])
        probabilities, matches = memory.retrieve()
        self.assert_valid_marginals(probabilities, 5, 2)
        self.assertTrue(matches)
        for match in matches:
            self.assertGreaterEqual(match["support"], 1)
            self.assertLessEqual(match["cycle"], 11)
            self.assertLess(match["context_cutoff"], match["cycle"])
            self.assertGreaterEqual(match["similarity"], 0)
            self.assertLessEqual(match["similarity"], 1)
        self.assertEqual(sum(rule["support"] for rule in memory.state_dict()["rules"]), 11)

    def test_history_and_rules_are_bounded_independently_of_cycle_sequence(self):
        memory = KnowledgeBaseManager(5, 2, short_window=2, max_history=3, max_rules=2)
        for cycle in range(20):
            memory.ingest(cycle, [cycle % 5, (cycle + 1) % 5])
        self.assertEqual(memory.history.shape, (3, 5))
        self.assertLessEqual(len(memory.state_dict()["rules"]), 2)
        self.assertEqual(memory.total_observations, 20)
        memory.ingest(20, [1, 2])
        with self.assertRaises(ValueError):
            memory.ingest(3, [1, 2])

    def test_recent_window_expires_older_outcomes(self):
        memory = KnowledgeBaseManager(4, 1, short_window=2)
        for cycle, label in enumerate([0] * 10 + [1, 1]):
            memory.ingest(cycle, [label])
        probabilities, _ = memory.retrieve()
        self.assertGreater(probabilities[1], probabilities[0])

    def test_invalid_observations_do_not_mutate_state(self):
        memory = KnowledgeBaseManager(5, 2)
        invalid = [
            (1, [0, 1]), (-1, [0, 1]), (True, [0, 1]), (0.0, [0, 1]),
            (0, [0]), (0, [0, 0]), (0, [-1, 1]), (0, [0, 5]),
            (0, [False, 1]), (0, [0.0, 1]), (0, [0, 1, 2]),
            (0, None), (0, "01"),
        ]
        before = memory.state_dict()
        for cycle, outcome in invalid:
            with self.subTest(cycle=cycle, outcome=outcome):
                with self.assertRaises((TypeError, ValueError)):
                    memory.ingest(cycle, outcome)
                self.assertEqual(memory.state_dict(), before)
        memory.ingest(np.int64(0), np.array([1, 2], dtype=np.int64))
        after = memory.state_dict()
        for cycle in (0, 2):
            with self.assertRaises(ValueError):
                memory.ingest(cycle, [1, 2])
            self.assertEqual(memory.state_dict(), after)

    def test_constructor_rejects_invalid_bounds(self):
        for args in [(0, 1), (5, 0), (5, 6), (True, 1), (5, True)]:
            with self.subTest(args=args), self.assertRaises((TypeError, ValueError)):
                KnowledgeBaseManager(*args)
        for kwargs in [
            {"short_window": 0}, {"short_window": 4, "max_history": 3},
            {"max_history": 0}, {"max_rules": 0}, {"max_rules": True},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                KnowledgeBaseManager(5, 2, **kwargs)

    def test_history_is_a_copy(self):
        memory = KnowledgeBaseManager(3, 1)
        memory.ingest(0, [1])
        memory.history[:] = 0
        np.testing.assert_array_equal(memory.history, [[0, 1, 0]])

    def test_state_is_json_and_restart_preserves_subsequent_behavior(self):
        original = KnowledgeBaseManager(6, 2, short_window=3, max_history=5, max_rules=7)
        for cycle in range(18):
            original.ingest(cycle, [cycle % 6, (cycle + 2) % 6])
        serialized = json.dumps(original.state_dict(), allow_nan=False)
        restored = KnowledgeBaseManager(6, 2, short_window=3, max_history=5, max_rules=7)
        restored.load_state_dict(json.loads(serialized))
        self.assertEqual(original.state_dict(), restored.state_dict())
        for cycle in range(18, 24):
            np.testing.assert_array_equal(original.retrieve()[0], restored.retrieve()[0])
            self.assertEqual(original.retrieve()[1], restored.retrieve()[1])
            outcome = [cycle % 6, (cycle + 2) % 6]
            original.ingest(cycle, outcome)
            restored.ingest(cycle, outcome)
        self.assertEqual(original.state_dict(), restored.state_dict())

    def test_state_and_matches_do_not_expose_internal_mutability(self):
        memory = KnowledgeBaseManager(3, 1, short_window=2)
        for cycle in range(5):
            memory.ingest(cycle, [0])
        before = memory.state_dict()
        exported = memory.state_dict()
        exported["history"][0][0] = 99
        exported["rules"][0]["context"][0] = 99
        _, matches = memory.retrieve()
        matches[0]["support"] = 999
        self.assertEqual(memory.state_dict(), before)

    def test_invalid_state_is_rejected_atomically(self):
        memory = KnowledgeBaseManager(4, 1, short_window=2, max_history=3, max_rules=4)
        for cycle in range(8):
            memory.ingest(cycle, [cycle % 4])
        before = memory.state_dict()
        mutations = [
            lambda state: state.update(total_observations=2),
            lambda state: state.update(n=5),
            lambda state: state["history"][0].__setitem__(0, 7),
            lambda state: state["rules"][0].update(cycle=8),
            lambda state: state["rules"][0].update(support=0),
            lambda state: state["rules"][0]["context"].__setitem__(0, float("nan")),
            lambda state: state["rules"][0]["outcome_counts"].__setitem__(0, -1),
            lambda state: state["rules"][0].update(context_cutoff=8),
        ]
        for mutate in mutations:
            bad = copy.deepcopy(before)
            mutate(bad)
            with self.assertRaises((TypeError, ValueError)):
                memory.load_state_dict(bad)
            self.assertEqual(memory.state_dict(), before)

    def test_full_cardinality_remains_certain(self):
        memory = KnowledgeBaseManager(3, 3, short_window=2)
        for cycle in range(7):
            memory.ingest(cycle, [0, 1, 2])
        np.testing.assert_array_equal(memory.retrieve()[0], np.ones(3))


if __name__ == "__main__":
    unittest.main()
