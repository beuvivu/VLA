from __future__ import annotations

import numpy as np
import pandas as pd

from ml_validation import (
    BootstrapConfig,
    daily_probabilistic_losses,
    evaluate_paired_oos,
    paired_cluster_bootstrap,
    promotion_reasons,
    relative_skill,
)


def _oos_frame(days: int) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "anchor_date": np.repeat(dates, 100),
            "number": np.tile(np.arange(100), days),
        }
    )


def test_loss_skill_direction_is_lower_is_better() -> None:
    assert np.isclose(relative_skill(baseline_loss=0.20, challenger_loss=0.18), 0.10)
    assert relative_skill(baseline_loss=0.20, challenger_loss=0.20) == 0.0
    assert relative_skill(baseline_loss=0.20, challenger_loss=0.22) < 0.0


def test_de_evaluation_matches_normalized_production_distribution() -> None:
    frame = _oos_frame(1)
    y = np.zeros(100, dtype=int)
    y[37] = 1
    raw = np.linspace(0.002, 0.012, 100)
    scaled = raw * 2.0

    base_daily, base_served = daily_probabilistic_losses(
        frame, y, raw, mode="de", probability_name="baseline"
    )
    scaled_daily, scaled_served = daily_probabilistic_losses(
        frame, y, scaled, mode="de", probability_name="challenger"
    )

    assert np.allclose(base_served, scaled_served)
    assert np.isclose(base_served.sum(), 1.0)
    assert np.isclose(float(base_daily.loc[0, "brier"]), float(scaled_daily.loc[0, "brier"]))
    assert np.isclose(
        float(base_daily.loc[0, "logloss"]), float(scaled_daily.loc[0, "logloss"])
    )


def test_date_cluster_bootstrap_is_deterministic_and_paired() -> None:
    daily = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=8, freq="D"),
            "baseline_brier": [0.20] * 8,
            "challenger_brier": [0.19, 0.18, 0.20, 0.17, 0.21, 0.18, 0.19, 0.20],
            "baseline_logloss": [0.50] * 8,
            "challenger_logloss": [0.49, 0.48, 0.50, 0.47, 0.51, 0.48, 0.49, 0.50],
        }
    )
    config = BootstrapConfig(replicates=300, seed=1234, confidence=0.95, minimum_oos_dates=5)
    a = paired_cluster_bootstrap(daily, config=config)
    b = paired_cluster_bootstrap(daily, config=config)

    assert a == b
    assert a["cluster_unit"] == "date"
    assert a["oos_dates"] == 8
    assert a["replicates"] == 300


def test_bootstrap_fails_closed_for_too_few_dates() -> None:
    daily = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=4, freq="D"),
            "baseline_brier": [0.2] * 4,
            "challenger_brier": [0.19] * 4,
            "baseline_logloss": [0.5] * 4,
            "challenger_logloss": [0.49] * 4,
        }
    )
    config = BootstrapConfig(replicates=100, seed=1, confidence=0.95, minimum_oos_dates=5)
    result = paired_cluster_bootstrap(daily, config=config)
    assert result["valid"] is False
    assert result["reason"] == "insufficient_oos_dates"


def test_promotion_requires_both_metrics_and_ci_lower_bounds() -> None:
    assert promotion_reasons(
        brier_skill=0.01,
        logloss_skill=-0.01,
        brier_ci_low=0.001,
        logloss_ci_low=-0.001,
        oos_dates=30,
        minimum_oos_dates=30,
        bootstrap_valid=True,
    ) == ["nonpositive_logloss_skill", "logloss_ci_crosses_zero"]

    reasons = promotion_reasons(
        brier_skill=0.01,
        logloss_skill=0.01,
        brier_ci_low=0.0,
        logloss_ci_low=0.001,
        oos_dates=30,
        minimum_oos_dates=30,
        bootstrap_valid=True,
    )
    assert reasons == ["brier_ci_crosses_zero"]


def test_identical_noise_candidate_is_not_promoted() -> None:
    frame = _oos_frame(35)
    y = np.zeros(len(frame), dtype=int)
    for day in range(35):
        y[day * 100 + (day % 100)] = 1
    p = np.full(len(frame), 0.01, dtype=float)
    report, _ = evaluate_paired_oos(
        frame,
        y,
        p,
        p.copy(),
        mode="de",
        bootstrap=BootstrapConfig(replicates=200, seed=9, minimum_oos_dates=30),
    )
    assert report["promoted"] is False
    assert report["brier_skill"] == 0.0
    assert report["logloss_skill"] == 0.0


def test_known_useful_loto_challenger_can_pass_conservative_gate() -> None:
    days = 40
    frame = _oos_frame(days)
    y = np.zeros(len(frame), dtype=int)
    baseline = np.full(len(frame), 0.10, dtype=float)
    challenger = np.full(len(frame), 0.02, dtype=float)
    for day in range(days):
        idx = day * 100 + 12
        y[idx] = 1
        challenger[idx] = 0.80

    report, _ = evaluate_paired_oos(
        frame,
        y,
        baseline,
        challenger,
        mode="loto",
        bootstrap=BootstrapConfig(replicates=300, seed=77, minimum_oos_dates=30),
    )
    assert report["brier_skill"] > 0.0
    assert report["logloss_skill"] > 0.0
    assert report["brier_ci_low"] > 0.0
    assert report["logloss_ci_low"] > 0.0
    assert report["promoted"] is True


def test_degraded_challenger_is_rejected() -> None:
    days = 35
    frame = _oos_frame(days)
    y = np.zeros(len(frame), dtype=int)
    baseline = np.full(len(frame), 0.01, dtype=float)
    challenger = np.full(len(frame), 0.01, dtype=float)
    for day in range(days):
        target = day % 100
        y[day * 100 + target] = 1
        challenger[day * 100 + target] = 0.001
        challenger[day * 100 + ((target + 1) % 100)] = 0.20

    report, _ = evaluate_paired_oos(
        frame,
        y,
        baseline,
        challenger,
        mode="de",
        bootstrap=BootstrapConfig(replicates=200, seed=88, minimum_oos_dates=30),
    )
    assert report["brier_skill"] < 0.0
    assert report["logloss_skill"] < 0.0
    assert report["promoted"] is False
