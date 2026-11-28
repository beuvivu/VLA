from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from stats import number_dynamics as nd

BASE_RATE = 0.2378


def _inject(hit: np.ndarray, amount: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    h = hit.copy().astype(np.int8)
    if amount <= 0:
        return h
    target = min(0.98, BASE_RATE * (1.0 + amount))
    for t in range(1, len(h)):
        if h[t - 1, 12]:
            h[t, 34] = 1 if rng.random() < target else 0
    return h


MEASURED_DRAWS = 4207


@pytest.fixture(scope="module")
def real() -> tuple[pd.DatetimeIndex, np.ndarray]:
    dates, hit = nd.build_hit_matrix_from_lottery("loto")
    return dates[:MEASURED_DRAWS], hit[:MEASURED_DRAWS]


def test_arithmetic_pooling_can_never_sharpen_beyond_its_inputs() -> None:
    base = np.full(100, 0.2)
    trans = np.tile(base, (100, 1))
    trans[12] = 0.9
    active = np.arange(24)
    pooled = nd._pool_active_rows("arithmetic", trans, base, active)
    assert pooled.max() <= trans[active].max() + 1e-12
    assert pooled.min() >= trans[active].min() - 1e-12
    assert pooled[0] < 0.25


def test_log_odds_pooling_can_sharpen_past_every_input() -> None:
    base = np.full(100, 0.2)
    trans = np.tile(base, (100, 1))
    trans[12] = 0.9
    active = np.arange(24)
    pooled = nd._pool_active_rows("logodds", trans, base, active)
    assert pooled[0] == pytest.approx(0.9, abs=1e-6)


def test_pooling_with_no_active_rows_returns_the_baseline() -> None:
    base = np.linspace(0.1, 0.3, 100)
    trans = np.tile(base, (100, 1))
    for kind in nd.POOL_KINDS:
        np.testing.assert_allclose(
            nd._pool_active_rows(kind, trans, base, np.array([], dtype=int)), base
        )


def test_real_data_keeps_the_arithmetic_pool_by_a_wide_margin(real) -> None:
    dates, hit = real
    kind, diagnostics = nd.select_transition_pool(hit)
    assert kind == "arithmetic"
    assert diagnostics["t_statistic"] > 4.0
    assert diagnostics["holdout_days"] > 400


def test_a_strong_injected_relationship_switches_the_pool(real) -> None:
    _, hit = real
    kind, diagnostics = nd.select_transition_pool(_inject(hit, 2.0))
    assert kind == "logodds"
    assert diagnostics["t_statistic"] < -nd.SIGNIFICANCE_SIGMAS


def test_a_weak_injected_relationship_does_not_switch_the_pool(real) -> None:
    _, hit = real
    kind, _ = nd.select_transition_pool(_inject(hit, 0.25))
    assert kind == "arithmetic"


def test_when_the_two_pools_coincide_the_test_reports_no_difference_not_rounding_noise() -> None:
    rng = np.random.default_rng(5)
    days = 1200
    h = np.zeros((days, 100), dtype=np.int8)
    h[np.arange(days), rng.integers(0, 100, size=days)] = 1
    kind, diagnostics = nd.select_transition_pool(h)
    assert kind == "arithmetic"
    assert diagnostics["holdout_days"] > 0
    assert diagnostics["t_statistic"] == 0.0
    assert diagnostics["brier_arithmetic"] == pytest.approx(diagnostics["brier_logodds"], abs=1e-15)


def test_short_history_falls_back_without_crashing() -> None:
    rng = np.random.default_rng(0)
    h = (rng.random((50, 100)) < 0.2378).astype(np.int8)
    kind, diagnostics = nd.select_transition_pool(h)
    assert kind == "arithmetic"
    assert diagnostics["holdout_days"] == 0


def test_the_transition_component_is_not_shrunk_a_second_time(real) -> None:
    dates, hit = real
    h = _inject(hit, 2.0)
    moved, baselines = [], []
    for t in range(len(h) - 60, len(h)):
        if not h[t - 1, 12]:
            continue
        cur = nd.build_dynamics_signal(
            hit=h[:t], dates=dates[:t], mode="loto"
        ).current.sort_values("number")
        moved.append(float(cur["transition_prob"].to_numpy()[34]))
        baselines.append(float(cur["baseline_prob"].to_numpy()[34]))
    assert len(moved) > 5
    assert np.mean(moved) > np.mean(baselines) + 0.05


def test_the_gate_holds_the_incumbent_when_the_challenger_merely_leads(real) -> None:
    _, hit = real
    for seed, expected_t in ((1, -1.62), (3, -1.81)):
        kind, diagnostics = nd.select_transition_pool(_inject(hit, 1.10, seed=seed))
        t_statistic = diagnostics["t_statistic"]
        assert t_statistic < 0.0, "cần trường hợp log-odds ĐANG dẫn mới kiểm được"
        assert t_statistic > -nd.SIGNIFICANCE_SIGMAS, "cần dẫn mà CHƯA đủ 2 SE"
        assert t_statistic == pytest.approx(expected_t, abs=0.15)
        assert kind == "arithmetic"
