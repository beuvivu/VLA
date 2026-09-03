from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from markov_stats import build_markov_chain, compute_markov_for_loto


def test_exclusive_markov_chain_counts_smoothing_and_row_sums() -> None:
    chain = build_markov_chain([0, 1, 0, 1, 1], alpha=1.0, states=[0, 1])

    np.testing.assert_array_equal(chain.transition_counts, [[0, 2], [1, 1]])
    np.testing.assert_array_equal(chain.outgoing_counts, [2, 2])
    np.testing.assert_allclose(chain.transition_probabilities, [[0.25, 0.75], [0.5, 0.5]])
    np.testing.assert_allclose(chain.transition_probabilities.sum(axis=1), 1.0)


def test_markov_smoothing_assigns_uniform_probability_to_unseen_state() -> None:
    chain = build_markov_chain([0], alpha=0.5, states=[0, 1, 2])
    np.testing.assert_allclose(chain.transition_probabilities[1], [1 / 3] * 3)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"alpha": True},
        {"alpha": "1"},
        {"states": [0, 1.5]},
    ],
)
def test_exclusive_markov_chain_rejects_ambiguous_numeric_types(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        build_markov_chain([0, 1], **kwargs)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="observations"):
        build_markov_chain([0, 1.5])  # type: ignore[list-item]


@pytest.mark.parametrize(
    ("alpha", "beta"),
    [
        (float("nan"), 1.0),
        (1.0, float("inf")),
        (-1.0, 1.0),
        (0.0, 0.0),
        (True, 1.0),
    ],
)
def test_binary_markov_rejects_invalid_smoothing(alpha: float, beta: float) -> None:
    with pytest.raises(ValueError, match="alpha"):
        compute_markov_for_loto(pd.DataFrame(), alpha=alpha, beta=beta)
