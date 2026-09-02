from __future__ import annotations

import numpy as np

from markov_stats import build_markov_chain


def test_exclusive_markov_chain_counts_smoothing_and_row_sums() -> None:
    chain = build_markov_chain([0, 1, 0, 1, 1], alpha=1.0, states=[0, 1])

    np.testing.assert_array_equal(chain.transition_counts, [[0, 2], [1, 1]])
    np.testing.assert_array_equal(chain.outgoing_counts, [2, 2])
    np.testing.assert_allclose(chain.transition_probabilities, [[0.25, 0.75], [0.5, 0.5]])
    np.testing.assert_allclose(chain.transition_probabilities.sum(axis=1), 1.0)


def test_markov_smoothing_assigns_uniform_probability_to_unseen_state() -> None:
    chain = build_markov_chain([0], alpha=0.5, states=[0, 1, 2])
    np.testing.assert_allclose(chain.transition_probabilities[1], [1 / 3] * 3)
