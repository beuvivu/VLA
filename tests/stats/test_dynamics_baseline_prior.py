from __future__ import annotations

import numpy as np
import pytest

from stats.number_dynamics import LEARN_BASELINE_PRIOR, _baseline


def test_learning_is_the_default() -> None:
    assert LEARN_BASELINE_PRIOR is None


def test_homogeneous_numbers_are_pooled_toward_the_global_rate() -> None:
    rng = np.random.default_rng(0)
    hit = (rng.random((1200, 100)) < 0.2377).astype(np.int8)

    learned = _baseline(hit, prior_strength=None)
    legacy = _baseline(hit, prior_strength=22.5)

    assert learned.std() < legacy.std() / 3.0, (
        f"học κ nên phẳng hơn hẳn: std {learned.std():.6f} so với {legacy.std():.6f}"
    )
    assert learned.mean() == pytest.approx(float(hit.mean()), abs=1e-3)


def test_genuine_differences_survive_the_shrinkage() -> None:
    rng = np.random.default_rng(1)
    rates = np.clip(rng.normal(0.2377, 0.08, size=100), 0.05, 0.7)
    hit = (rng.random((1200, 100)) < rates[None, :]).astype(np.int8)

    learned = _baseline(hit, prior_strength=None)
    assert float(np.corrcoef(learned, rates)[0, 1]) > 0.9
    assert learned.std() > 0.03


def test_an_explicit_strength_still_reproduces_the_legacy_behaviour() -> None:
    rng = np.random.default_rng(2)
    hit = (rng.random((300, 100)) < 0.2377).astype(np.int8)

    expected = (hit.sum(axis=0) + 22.5 * hit.mean()) / (len(hit) + 22.5)
    np.testing.assert_allclose(_baseline(hit, prior_strength=22.5), expected)


@pytest.mark.parametrize("shape", [(0, 100), (1, 100), (5, 2)])
def test_a_degenerate_history_falls_back_to_the_global_rate(shape: tuple) -> None:
    hit = np.ones(shape, dtype=np.int8)
    out = _baseline(hit, prior_strength=None)
    assert out.shape == (shape[1],)
    assert np.isfinite(out).all()
    assert np.all((out >= 0.0) & (out <= 1.0))


def test_the_learned_baseline_beats_the_legacy_constant_walk_forward() -> None:
    rng = np.random.default_rng(3)
    hit = (rng.random((700, 100)) < 0.2377).astype(np.int8)

    legacy_errors, learned_errors = [], []
    for t in range(400, len(hit)):
        past, y = hit[:t], hit[t]
        legacy_errors.append(float(np.mean((_baseline(past, 22.5) - y) ** 2)))
        learned_errors.append(float(np.mean((_baseline(past, None) - y) ** 2)))

    delta = np.asarray(learned_errors) - np.asarray(legacy_errors)
    standard_error = float(np.std(delta, ddof=1) / np.sqrt(delta.size))
    t_stat = float(delta.mean() / standard_error)
    assert t_stat < -2.0, (
        f"t = {t_stat:.2f}; bản học được phải thắng ở mức 2 SE, nếu không thì "
        "thay đổi này không có cơ sở"
    )
