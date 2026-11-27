from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from stats import number_dynamics as nd  # noqa: E402
from ensemble.hierarchical_pooling import (  # noqa: E402
    MAX_PRIOR_STRENGTH,
    fit_shrinkage_to_prior,
    fit_shrinkage_to_prior_rows,
)

HAND_LOTO = dict(
    transition_prior=45.0,
    markov_prior=35.0,
    hazard_prior=60.0,
    lag_prior=45.0,
    regime_prior=35.0,
)


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2020-01-01", periods=n, freq="D")


def _iid(days: int, rate: float = 0.185, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.random((days, 100)) < rate).astype(np.int8)


def test_learning_is_the_default_for_all_five_components() -> None:
    h = _iid(400)
    diag = nd.build_dynamics_signal(hit=h, dates=_dates(400), mode="loto").diagnostics
    assert diag["component_priors_learned"] == {
        "transition": True,
        "markov2": True,
        "hazard": True,
        "lag": True,
        "regime": True,
    }


def test_explicit_numbers_are_passed_through_untouched() -> None:
    h = _iid(400)
    diag = nd.build_dynamics_signal(
        hit=h, dates=_dates(400), mode="loto", **HAND_LOTO
    ).diagnostics
    learned = diag["component_prior_strengths"]
    assert learned["transition_median"] == 45.0
    assert learned["markov2_by_state"] == [35.0] * 4
    assert learned["hazard"] == 60.0
    assert learned["lag_median"] == 45.0
    assert learned["regime_recent"] == 35.0
    assert learned["regime_long"] == 35.0
    assert not any(diag["component_priors_learned"].values())


def test_a_finite_strength_is_not_by_itself_evidence_of_signal() -> None:
    collapsed_fractions = []
    for seed in range(6):
        h = _iid(600, seed=seed)
        _, _, _, _, kappa = nd.transition_posterior(h, prior_strength=None)
        collapsed_fractions.append(float((kappa >= MAX_PRIOR_STRENGTH).mean()))
    assert 0.25 < min(collapsed_fractions)
    assert max(collapsed_fractions) < 0.85


def test_learning_moves_numbers_far_less_than_hand_picked_on_noise() -> None:
    h = _iid(600)
    learned = nd.build_dynamics_signal(
        hit=h, dates=_dates(600), mode="loto"
    ).current.sort_values("number")
    hand = nd.build_dynamics_signal(
        hit=h, dates=_dates(600), mode="loto", **HAND_LOTO
    ).current.sort_values("number")
    for column in ("transition_prob", "markov2_prob", "lag_kernel_prob"):
        learned_drift = np.median(
            np.abs(learned[column].to_numpy() - learned["baseline_prob"].to_numpy())
        )
        hand_drift = np.median(
            np.abs(hand[column].to_numpy() - hand["baseline_prob"].to_numpy())
        )
        assert learned_drift < hand_drift / 4.0, column


def test_an_injected_transition_keeps_the_component_alive() -> None:
    rng = np.random.default_rng(3)
    h = (rng.random((700, 100)) < 0.185).astype(np.int8)
    for t in range(1, len(h)):
        if h[t - 1, 12]:
            h[t, 34] = 1
    _, _, _, _, kappa = nd.transition_posterior(h, prior_strength=None)
    assert kappa[12] < MAX_PRIOR_STRENGTH
    others = np.delete(kappa, 12)
    assert float(np.median(others)) >= MAX_PRIOR_STRENGTH


def test_learned_transition_still_recovers_that_injected_relationship() -> None:
    rng = np.random.default_rng(3)
    h = (rng.random((700, 100)) < 0.185).astype(np.int8)
    for t in range(1, len(h)):
        if h[t - 1, 12]:
            h[t, 34] = 1
    _, lift, _, _, _ = nd.transition_posterior(h, prior_strength=None)
    assert lift[12, 34] > 1.5


def test_regime_learns_two_different_strengths_for_two_window_lengths() -> None:
    h = _iid(500)
    out = nd._regime_current(h, recent=30, long=180, prior_strength=None)
    recent_prior, long_prior = out[5], out[6]
    assert recent_prior != long_prior


def test_lag_learns_one_strength_per_lag_state_cell() -> None:
    h = _iid(500)
    _, _, priors = nd._lag_kernel_current(h, lags=nd.LAGS, prior_strength=None)
    assert len(priors) == 2 * len(nd.LAGS)
    assert len(set(priors)) > 1


def test_short_history_returns_a_usable_strength_instead_of_none() -> None:
    _, _, _, _, kappa = nd.transition_posterior(
        np.zeros((1, 100), np.int8), prior_strength=None
    )
    assert kappa.shape == (100,)
    assert np.all(kappa == MAX_PRIOR_STRENGTH)
    out = nd._markov2_current(np.zeros((2, 100), np.int8), prior_strength=None)
    assert out[3].shape == (4,)
    assert np.all(out[3] == MAX_PRIOR_STRENGTH)


@pytest.mark.parametrize("mode", ["loto", "de"])
def test_learned_priors_do_not_break_the_probability_contract(mode: str) -> None:
    h = _iid(400)
    art = nd.build_dynamics_signal(hit=h, dates=_dates(400), mode=mode)
    prob = art.current["prob"].to_numpy()
    assert np.all(np.isfinite(prob))
    assert np.all(prob > 0.0) and np.all(prob < 1.0)
    if mode == "de":
        assert prob.sum() == pytest.approx(1.0)


FROZEN_THROUGH = pd.Timestamp("2026-11-13")


def test_learned_beats_hand_picked_on_real_walk_forward() -> None:
    dates, hit = nd.build_hit_matrix_from_lottery("loto")
    stop = int(dates.searchsorted(FROZEN_THROUGH, side="right"))
    assert dates[stop - 1] == FROZEN_THROUGH and stop >= 120
    hand_err: list[float] = []
    learn_err: list[float] = []
    for t in range(stop - 120, stop):
        h, dd, y = hit[:t], dates[:t], hit[t].astype(float)
        a = nd.build_dynamics_signal(hit=h, dates=dd, mode="loto", **HAND_LOTO)
        b = nd.build_dynamics_signal(hit=h, dates=dd, mode="loto")
        ga = a.current.sort_values("number")["prob"].to_numpy()
        gb = b.current.sort_values("number")["prob"].to_numpy()
        hand_err.append(float(np.mean((ga - y) ** 2)))
        learn_err.append(float(np.mean((gb - y) ** 2)))
    delta = np.asarray(learn_err) - np.asarray(hand_err)
    assert delta.mean() < 0.0


def test_prior_fit_returns_full_shrinkage_when_deviation_is_pure_noise() -> None:
    rng = np.random.default_rng(11)
    prior_rate = 0.2
    trials = np.full(200, 500.0)
    successes = rng.binomial(500, prior_rate, size=200).astype(float)
    kappa = fit_shrinkage_to_prior(successes, trials, np.full(200, prior_rate))
    assert kappa == MAX_PRIOR_STRENGTH


def test_prior_fit_returns_a_finite_strength_when_units_genuinely_differ() -> None:
    trials = np.full(200, 500.0)
    rates = np.linspace(0.10, 0.30, 200)
    successes = rates * 500.0
    kappa = fit_shrinkage_to_prior(successes, trials, np.full(200, 0.2))
    assert kappa < MAX_PRIOR_STRENGTH
    assert kappa == pytest.approx(51.6, rel=0.05)


def test_prior_fit_needs_at_least_three_usable_units() -> None:
    assert fit_shrinkage_to_prior(
        np.array([1.0, 2.0]), np.array([10.0, 10.0]), np.full(2, 0.2)
    ) == MAX_PRIOR_STRENGTH


def test_prior_fit_rejects_mismatched_shapes() -> None:
    with pytest.raises(ValueError):
        fit_shrinkage_to_prior(np.zeros(5), np.ones(4), np.full(5, 0.2))


def test_hazard_learns_its_own_strength_rather_than_the_hand_picked_60() -> None:
    dates, hit = nd.build_hit_matrix_from_lottery("loto")
    diag = nd.build_dynamics_signal(
        hit=hit, dates=dates, mode="loto"
    ).diagnostics["component_prior_strengths"]
    assert diag["hazard"] != 60.0
    _, _, _, _, direct = nd._gap_hazard_current(hit, max_gap=60, prior_strength=None)
    assert diag["hazard"] == pytest.approx(direct)


def test_markov_uses_the_strength_of_the_state_each_number_is_actually_in() -> None:
    rng = np.random.default_rng(5)
    h = (rng.random((800, 100)) < 0.185).astype(np.int8)
    for t in range(2, len(h)):
        idx = np.where((h[t - 2] == 1) & (h[t - 1] == 1))[0]
        if idx.size:
            h[t, idx] = (rng.random(idx.size) < 0.6).astype(np.int8)

    prob, state_now, reliability, state_prior = nd._markov2_current(
        h, prior_strength=None
    )
    assert len(set(state_prior.tolist())) == 4, "cần bốn κ khác nhau mới kiểm được"
    assert len(set(state_now.tolist())) > 1, "cần nhiều trạng thái mới kiểm được"
    assert state_prior[3] == min(state_prior)

    success = np.zeros((4, 100))
    trials = np.zeros((4, 100))
    cols = np.arange(100)
    for t in range(1, len(h) - 1):
        trials[2 * h[t - 1] + h[t], cols] += 1.0
        success[2 * h[t - 1] + h[t], cols] += h[t + 1]
    n = trials[state_now, cols]
    expected = n / (n + state_prior[state_now])
    np.testing.assert_allclose(reliability, expected)
    assert np.isfinite(prob).all()


def test_prior_fit_drops_zero_trial_units_instead_of_poisoning_the_estimate() -> None:
    rates = np.linspace(0.10, 0.30, 200)
    successes = np.concatenate([rates * 500.0, np.zeros(5)])
    trials = np.concatenate([np.full(200, 500.0), np.zeros(5)])
    prior = np.full(205, 0.2)
    with_zeros = fit_shrinkage_to_prior(successes, trials, prior)
    assert with_zeros < MAX_PRIOR_STRENGTH
    assert with_zeros == pytest.approx(
        fit_shrinkage_to_prior(successes[:200], trials[:200], prior[:200])
    )


@pytest.mark.parametrize("trials_per_row", [5, 24, 240])
def test_the_null_rate_of_finite_strengths_does_not_fall_with_more_data(
    trials_per_row: int,
) -> None:
    rng = np.random.default_rng(0)
    base = np.full(100, 0.185)
    trials = np.full(100, float(trials_per_row))
    fractions = []
    for _ in range(12):
        hits = rng.binomial(trials_per_row, 0.185, size=(100, 100)).astype(float)
        kappa = fit_shrinkage_to_prior_rows(hits, trials, base)
        fractions.append(float((kappa < MAX_PRIOR_STRENGTH).mean()))
    assert 0.35 < float(np.mean(fractions)) < 0.62
