from __future__ import annotations

import numpy as np
import pytest

from ensemble.opinion_pool import (
    MIN_SELECTION_DAYS,
    SIGNIFICANCE_SIGMAS,
    PoolParams,
    apply_pool,
    fit_pool,
)


def _cube(probs_per_day: np.ndarray) -> np.ndarray:
    return np.asarray(probs_per_day, dtype=float)


def test_arithmetic_pooling_can_never_be_sharper_than_its_inputs() -> None:
    components = np.tile(np.concatenate([np.full(3, 0.40), np.full(97, 0.20)]), (3, 1))
    pooled = apply_pool("loto", components, PoolParams("linear", (1, 1, 1), 0.2377))
    assert pooled.max() <= components.max() + 1e-12
    assert pooled.min() >= components.min() - 1e-12


def test_log_pooling_sharpens_when_the_sources_agree() -> None:
    components = np.tile(np.concatenate([np.full(3, 0.40), np.full(97, 0.20)]), (3, 1))
    pooled = apply_pool(
        "loto", components, PoolParams("log", (1, 1, 1), 0.2377, sharpness=2.0)
    )
    assert pooled.max() > components.max(), "trộn log phải vượt được đầu vào"


@pytest.mark.parametrize("sharpness", [0.0, 0.5, 1.0, 2.0])
def test_zero_sharpness_returns_exactly_the_baseline(sharpness: float) -> None:
    components = np.tile(np.linspace(0.05, 0.6, 100), (3, 1))
    pooled = apply_pool("loto", components, PoolParams("log", (1, 1, 1), 0.2377, sharpness))
    if sharpness == 0.0:
        np.testing.assert_allclose(pooled, 0.2377, atol=1e-9)
    else:
        assert pooled.std() > 0.0


def test_de_mode_output_stays_a_distribution() -> None:
    rng = np.random.default_rng(0)
    components = rng.dirichlet(np.full(100, 5.0), size=4)
    for params in (
        PoolParams("linear", (1, 1, 1, 1), 0.01),
        PoolParams("log", (1, 1, 1, 1), 0.01, sharpness=2.0),
    ):
        assert float(apply_pool("de", components, params).sum()) == pytest.approx(1.0)


def test_pure_noise_keeps_the_incumbent_arithmetic_pool() -> None:
    rng = np.random.default_rng(1)
    days, base = 400, 0.2377
    cube = _cube(np.clip(rng.normal(base, 0.02, size=(days, 3, 100)), 0.01, 0.99))
    labels = (rng.random((days, 100)) < base).astype(float)

    params, audit = fit_pool("loto", cube, labels, np.array([0.55, 0.25, 0.20]))
    assert audit.selected
    assert params.kind == "linear", audit.describe()


def test_strong_independent_evidence_flips_the_gate_to_log_pooling() -> None:
    rng = np.random.default_rng(2)
    days, base = 500, 0.2377
    true_rate = np.clip(rng.normal(base, 0.12, size=100), 0.03, 0.9)

    cube = np.empty((days, 3, 100))
    labels = np.empty((days, 100))
    for t in range(days):
        for k in range(3):
            noisy = np.clip(true_rate + rng.normal(0.0, 0.05, size=100), 0.01, 0.99)
            cube[t, k] = base + 0.35 * (noisy - base)
        labels[t] = (rng.random(100) < true_rate).astype(float)

    params, audit = fit_pool("loto", cube, labels, np.array([1.0, 1.0, 1.0]))
    assert audit.selected
    assert params.kind == "log", audit.describe()
    assert params.sharpness > 1.0, "bằng chứng độc lập phải làm SẮC lên"


def test_the_threshold_demands_real_evidence_not_a_coin_flip() -> None:
    assert SIGNIFICANCE_SIGMAS >= 2.0


def test_a_short_history_refuses_to_choose_and_says_so() -> None:
    rng = np.random.default_rng(3)
    days = MIN_SELECTION_DAYS - 1
    cube = _cube(np.full((days, 3, 100), 0.2377))
    labels = (rng.random((days, 100)) < 0.2377).astype(float)

    params, audit = fit_pool("loto", cube, labels, np.array([0.55, 0.25, 0.20]))
    assert audit.selected is False
    assert params.kind == "linear"
    assert "Không chọn được" in audit.describe()


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"weights": ()}, "ít nhất một thành phần"),
        ({"weights": (-1.0, 1.0)}, "không âm"),
        ({"weights": (0.0, 0.0)}, "tổng trọng số"),
        ({"baseline": 0.0}, "tần suất nền"),
        ({"baseline": 1.0}, "tần suất nền"),
        ({"sharpness": -1.0}, "độ sắc"),
    ],
)
def test_invalid_pool_parameters_are_refused(kwargs: dict, match: str) -> None:
    base = {"kind": "linear", "weights": (1.0, 1.0), "baseline": 0.2377}
    with pytest.raises(ValueError, match=match):
        PoolParams(**{**base, **kwargs})


def test_a_component_count_mismatch_is_refused() -> None:
    with pytest.raises(ValueError, match="không khớp"):
        apply_pool(
            "loto", np.full((2, 100), 0.2), PoolParams("linear", (1, 1, 1), 0.2377)
        )
