from __future__ import annotations

"""Shared leakage-safe validation primitives for probabilistic challengers.

This module contains no lottery-specific feature engineering. It standardizes
mode-aware losses, paired draw-cluster bootstrap uncertainty, and fail-closed
promotion decisions so experimental features cannot enter production from a
point estimate alone.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np

from ensemble_utils import (
    bernoulli_brier,
    bernoulli_logloss,
    categorical_brier,
    categorical_logloss,
    normalize_distribution,
)

Mode = Literal["loto", "de"]


@dataclass(frozen=True)
class BootstrapConfig:
    replicates: int = 1000
    seed: int = 20260902
    confidence: float = 0.95
    minimum_oos_dates: int = 30

    def validate(self) -> None:
        if self.replicates < 100:
            raise ValueError("bootstrap replicates must be >= 100")
        if not 0.50 < self.confidence < 1.0:
            raise ValueError("bootstrap confidence must be between 0.50 and 1.0")
        if self.minimum_oos_dates < 2:
            raise ValueError("minimum_oos_dates must be >= 2")


@dataclass(frozen=True)
class LossPair:
    brier: float
    logloss: float


@dataclass(frozen=True)
class ImprovementCI:
    brier_delta: float
    logloss_delta: float
    brier_low: float
    brier_high: float
    logloss_low: float
    logloss_high: float
    replicates: int
    confidence: float
    seed: int


@dataclass(frozen=True)
class PromotionDecision:
    promoted: bool
    reason: str
    brier_skill: float
    logloss_skill: float


def _as_float_vector(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if not np.all(np.isfinite(arr)):
        raise ValueError("probability vector contains NaN/inf")
    return arr


def _as_binary_vector(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if not np.all(np.isin(arr, [0.0, 1.0])):
        raise ValueError("labels must be binary")
    return arr


def score_draw(mode: Mode, probability: np.ndarray, y: np.ndarray) -> LossPair:
    """Score one complete 00..99 candidate cluster in production probability space."""
    p = _as_float_vector(probability)
    target = _as_binary_vector(y)
    if len(p) != 100 or len(target) != 100:
        raise ValueError("one draw must contain exactly 100 candidate rows")

    if mode == "de":
        if int(target.sum()) != 1:
            raise ValueError("de draw must have exactly one positive class")
        p = normalize_distribution(np.clip(p, 0.0, None))
        idx = int(np.argmax(target))
        return LossPair(
            brier=categorical_brier(p, idx),
            logloss=categorical_logloss(p, idx),
        )

    if mode != "loto":
        raise ValueError(f"unknown mode: {mode}")
    p = np.clip(p, 1e-12, 1.0 - 1e-12)
    return LossPair(
        brier=bernoulli_brier(p, target),
        logloss=bernoulli_logloss(p, target),
    )


def score_by_date(
    mode: Mode,
    dates: np.ndarray,
    probability: np.ndarray,
    y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return unique dates plus per-date Brier and LogLoss losses.

    Every date must contain the complete 100-number universe. This keeps metric
    aggregation and bootstrap aligned to the lottery draw rather than treating
    correlated candidate rows as independent observations.
    """
    d = np.asarray(dates).reshape(-1)
    p = _as_float_vector(probability)
    target = _as_binary_vector(y)
    if not (len(d) == len(p) == len(target)):
        raise ValueError("dates/probabilities/labels length mismatch")

    unique = np.unique(d)
    brier: list[float] = []
    logloss: list[float] = []
    for day in unique:
        mask = d == day
        if int(mask.sum()) != 100:
            raise ValueError(f"date {day!r} does not contain exactly 100 candidate rows")
        loss = score_draw(mode, p[mask], target[mask])
        brier.append(loss.brier)
        logloss.append(loss.logloss)
    return unique, np.asarray(brier, dtype=float), np.asarray(logloss, dtype=float)


def paired_cluster_bootstrap(
    mode: Mode,
    dates: np.ndarray,
    baseline_probability: np.ndarray,
    challenger_probability: np.ndarray,
    y: np.ndarray,
    *,
    config: BootstrapConfig,
) -> ImprovementCI:
    """Paired date-level bootstrap of baseline-minus-challenger loss improvement."""
    config.validate()
    days_b, brier_b, ll_b = score_by_date(mode, dates, baseline_probability, y)
    days_c, brier_c, ll_c = score_by_date(mode, dates, challenger_probability, y)
    if not np.array_equal(days_b, days_c):
        raise ValueError("baseline/challenger OOS date clusters are not identical")
    n = len(days_b)
    if n < config.minimum_oos_dates:
        raise ValueError(
            f"insufficient OOS dates: {n} < {config.minimum_oos_dates}"
        )

    brier_delta = brier_b - brier_c
    ll_delta = ll_b - ll_c
    if not np.all(np.isfinite(brier_delta)) or not np.all(np.isfinite(ll_delta)):
        raise ValueError("non-finite bootstrap inputs")

    rng = np.random.default_rng(config.seed)
    reps_b = np.empty(config.replicates, dtype=float)
    reps_l = np.empty(config.replicates, dtype=float)
    for i in range(config.replicates):
        sampled = rng.integers(0, n, size=n)
        # Index sampling preserves repeated-date multiplicity exactly and keeps
        # baseline/challenger paired within every sampled draw cluster.
        reps_b[i] = float(np.mean(brier_delta[sampled]))
        reps_l[i] = float(np.mean(ll_delta[sampled]))

    alpha = (1.0 - config.confidence) / 2.0
    b_low, b_high = np.quantile(reps_b, [alpha, 1.0 - alpha])
    l_low, l_high = np.quantile(reps_l, [alpha, 1.0 - alpha])
    return ImprovementCI(
        brier_delta=float(np.mean(brier_delta)),
        logloss_delta=float(np.mean(ll_delta)),
        brier_low=float(b_low),
        brier_high=float(b_high),
        logloss_low=float(l_low),
        logloss_high=float(l_high),
        replicates=config.replicates,
        confidence=config.confidence,
        seed=config.seed,
    )


def relative_skill(baseline_loss: float, challenger_loss: float) -> float:
    if not np.isfinite(baseline_loss) or not np.isfinite(challenger_loss):
        return float("nan")
    if baseline_loss <= 0.0:
        return float("nan")
    return float((baseline_loss - challenger_loss) / baseline_loss)


def decide_promotion(
    *,
    baseline: LossPair,
    challenger: LossPair,
    ci: ImprovementCI | None,
    oos_dates: int,
    minimum_oos_dates: int,
) -> PromotionDecision:
    """Fail-closed scientific promotion gate for an experimental challenger."""
    b_skill = relative_skill(baseline.brier, challenger.brier)
    l_skill = relative_skill(baseline.logloss, challenger.logloss)
    values = [
        baseline.brier,
        baseline.logloss,
        challenger.brier,
        challenger.logloss,
        b_skill,
        l_skill,
    ]
    if not all(np.isfinite(v) for v in values):
        return PromotionDecision(False, "invalid_metric", b_skill, l_skill)
    if oos_dates < minimum_oos_dates:
        return PromotionDecision(False, "insufficient_oos_dates", b_skill, l_skill)
    if b_skill <= 0.0:
        return PromotionDecision(False, "negative_brier_skill", b_skill, l_skill)
    if l_skill <= 0.0:
        return PromotionDecision(False, "negative_logloss_skill", b_skill, l_skill)
    if ci is None:
        return PromotionDecision(False, "bootstrap_missing", b_skill, l_skill)
    ci_values = [ci.brier_low, ci.brier_high, ci.logloss_low, ci.logloss_high]
    if not all(np.isfinite(v) for v in ci_values):
        return PromotionDecision(False, "bootstrap_invalid", b_skill, l_skill)
    if ci.brier_low <= 0.0:
        return PromotionDecision(False, "brier_ci_crosses_zero", b_skill, l_skill)
    if ci.logloss_low <= 0.0:
        return PromotionDecision(False, "logloss_ci_crosses_zero", b_skill, l_skill)
    return PromotionDecision(True, "positive_oos_with_ci", b_skill, l_skill)
