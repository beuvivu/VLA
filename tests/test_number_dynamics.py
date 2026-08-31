from __future__ import annotations

import numpy as np

from number_dynamics import build_dynamics_signal, transition_posterior


def _synthetic_loto(days: int = 240) -> np.ndarray:
    rng = np.random.default_rng(7)
    hit = (rng.random((days, 100)) < 0.16).astype(np.int8)
    # Inject a clear lag-1 relationship to verify that the transition matrix can
    # recover signal while still applying Bayesian shrinkage.
    for t in range(days - 1):
        if hit[t, 12]:
            hit[t + 1, 34] = 1
    return hit


def test_transition_matrix_recovers_injected_relationship() -> None:
    hit = _synthetic_loto()
    _, lift, trials, _ = transition_posterior(hit, prior_strength=30.0)
    assert lift.shape == (100, 100)
    assert trials[12] > 20
    assert lift[12, 34] > 1.15


def test_loto_dynamics_outputs_are_finite_and_bounded() -> None:
    artifacts = build_dynamics_signal(_synthetic_loto(), mode="loto")
    current = artifacts.current.sort_values("number")
    assert len(current) == 100
    assert artifacts.transition_prob.shape == (100, 101)
    assert artifacts.transition_lift.shape == (100, 101)
    assert artifacts.cooccurrence_phi.shape == (100, 101)
    assert len(artifacts.lag_dependency) == 100 * 2 * 6
    assert np.isfinite(current["prob"].to_numpy()).all()
    assert ((current["prob"] > 0) & (current["prob"] < 1)).all()
    assert 0.15 <= artifacts.diagnostics["global_dynamics_reliability"] <= 0.80


def test_de_dynamics_is_a_normalized_distribution() -> None:
    days = 320
    sequence = np.array([(7 * t + 13) % 100 for t in range(days)], dtype=int)
    hit = np.zeros((days, 100), dtype=np.int8)
    hit[np.arange(days), sequence] = 1

    artifacts = build_dynamics_signal(hit, mode="de")
    p = artifacts.current.sort_values("number")["prob"].to_numpy(dtype=float)
    assert np.isfinite(p).all()
    assert np.isclose(p.sum(), 1.0, atol=1e-10)
    assert (p > 0).all()


def test_cooccurrence_phi_is_symmetric_with_unit_diagonal() -> None:
    artifacts = build_dynamics_signal(_synthetic_loto(), mode="loto")
    phi = artifacts.cooccurrence_phi.drop(columns=["source"]).to_numpy(dtype=float)
    assert np.allclose(phi, phi.T, atol=1e-12)
    assert np.allclose(np.diag(phi), 1.0, atol=1e-12)
    assert np.nanmax(np.abs(phi)) <= 1.0 + 1e-12
