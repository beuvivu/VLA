from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ml_validation import (
    BootstrapConfig,
    ImprovementCI,
    LossPair,
    decide_promotion,
    paired_cluster_bootstrap,
    relative_skill,
    score_by_date,
    score_draw,
)


def _clusters(days: int = 40) -> tuple[np.ndarray, np.ndarray]:
    dates = np.repeat(np.arange(days), 100)
    y = np.zeros(days * 100, dtype=int)
    for day in range(days):
        y[day * 100 + (7 * day) % 100] = 1
    return dates, y


def test_metric_direction_and_relative_skill() -> None:
    baseline = 0.20
    better = 0.18
    worse = 0.22
    assert relative_skill(baseline, better) > 0.0
    assert relative_skill(baseline, baseline) == 0.0
    assert relative_skill(baseline, worse) < 0.0


def test_de_scoring_matches_production_normalization() -> None:
    y = np.zeros(100, dtype=int)
    y[27] = 1
    p = np.linspace(1.0, 2.0, 100)
    a = score_draw("de", p, y)
    b = score_draw("de", 17.0 * p, y)
    assert np.isclose(a.brier, b.brier)
    assert np.isclose(a.logloss, b.logloss)


def test_score_by_date_rejects_split_draw_cluster() -> None:
    dates = np.repeat(np.arange(2), 100)[:-1]
    p = np.full(len(dates), 0.1)
    y = np.zeros(len(dates), dtype=int)
    with pytest.raises(ValueError, match="100 candidate"):
        score_by_date("loto", dates, p, y)


def test_cluster_bootstrap_is_deterministic_and_paired() -> None:
    dates, y = _clusters(40)
    baseline = np.full(len(y), 0.01)
    challenger = baseline.copy()
    # Give the challenger a small, genuine per-draw advantage at the known target.
    for day in range(40):
        idx = day * 100 + (7 * day) % 100
        challenger[idx] = 0.03
    cfg = BootstrapConfig(replicates=400, seed=991, confidence=0.95, minimum_oos_dates=30)
    a = paired_cluster_bootstrap(
        "de", dates, baseline, challenger, y, config=cfg
    )
    b = paired_cluster_bootstrap(
        "de", dates, baseline, challenger, y, config=cfg
    )
    assert a == b
    assert a.brier_delta > 0.0
    assert a.logloss_delta > 0.0


def test_cluster_bootstrap_preserves_date_multiplicity() -> None:
    dates, y = _clusters(30)
    baseline = np.full(len(y), 0.01)
    challenger = baseline.copy()
    for day in range(30):
        challenger[day * 100 + (7 * day) % 100] = 0.02
    cfg = BootstrapConfig(replicates=200, seed=7, minimum_oos_dates=30)
    ci = paired_cluster_bootstrap(
        "de", dates, baseline, challenger, y, config=cfg
    )
    assert ci.replicates == 200
    assert ci.seed == 7
    assert ci.brier_low <= ci.brier_delta <= ci.brier_high
    assert ci.logloss_low <= ci.logloss_delta <= ci.logloss_high


def test_promotion_fails_closed_for_one_bad_metric_or_ci_crossing_zero() -> None:
    baseline = LossPair(brier=0.20, logloss=0.50)
    challenger = LossPair(brier=0.19, logloss=0.49)
    crossing = ImprovementCI(
        brier_delta=0.01,
        logloss_delta=0.01,
        brier_low=-0.001,
        brier_high=0.02,
        logloss_low=0.001,
        logloss_high=0.02,
        replicates=1000,
        confidence=0.95,
        seed=1,
    )
    decision = decide_promotion(
        baseline=baseline,
        challenger=challenger,
        ci=crossing,
        oos_dates=40,
        minimum_oos_dates=30,
    )
    assert decision.promoted is False
    assert decision.reason == "brier_ci_crosses_zero"

    bad_ll = LossPair(brier=0.19, logloss=0.51)
    decision = decide_promotion(
        baseline=baseline,
        challenger=bad_ll,
        ci=crossing,
        oos_dates=40,
        minimum_oos_dates=30,
    )
    assert decision.promoted is False
    assert decision.reason == "negative_logloss_skill"


def test_promotion_rejects_zero_and_insufficient_history() -> None:
    baseline = LossPair(0.20, 0.50)
    same = LossPair(0.20, 0.50)
    ci = ImprovementCI(
        brier_delta=0.0,
        logloss_delta=0.0,
        brier_low=0.0,
        brier_high=0.0,
        logloss_low=0.0,
        logloss_high=0.0,
        replicates=1000,
        confidence=0.95,
        seed=2,
    )
    assert decide_promotion(
        baseline=baseline,
        challenger=same,
        ci=ci,
        oos_dates=40,
        minimum_oos_dates=30,
    ).promoted is False
    assert decide_promotion(
        baseline=baseline,
        challenger=LossPair(0.19, 0.49),
        ci=ci,
        oos_dates=10,
        minimum_oos_dates=30,
    ).reason == "insufficient_oos_dates"
