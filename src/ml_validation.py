from __future__ import annotations

"""Reusable temporal validation and production-gating primitives.

Candidate-number rows from one lottery draw are correlated.  Uncertainty is
therefore estimated by resampling whole dates, never individual rows.  All
improvements use ``baseline loss - challenger loss`` so positive values mean
that the challenger is better for both Brier score and LogLoss.
"""

from dataclasses import dataclass
from numbers import Integral, Real
from typing import Protocol, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss


class ProbabilityModel(Protocol):
    def predict_proba(self, values: np.ndarray) -> np.ndarray: ...


@dataclass(frozen=True)
class ValidationConfig:
    bootstrap_replicates: int = 1_000
    bootstrap_seed: int = 20260902
    confidence_level: float = 0.95
    minimum_oos_dates: int = 30
    minimum_skill: float = 0.0

    def __post_init__(self) -> None:
        integer_fields = {
            "bootstrap_replicates": self.bootstrap_replicates,
            "bootstrap_seed": self.bootstrap_seed,
            "minimum_oos_dates": self.minimum_oos_dates,
        }
        for name, value in integer_fields.items():
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise ValueError(f"{name} must be an integer")
        real_fields = {
            "confidence_level": self.confidence_level,
            "minimum_skill": self.minimum_skill,
        }
        for name, value in real_fields.items():
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(f"{name} must be a real number")
        if self.bootstrap_replicates < 1:
            raise ValueError("bootstrap_replicates must be >= 1")
        if self.bootstrap_seed < 0:
            raise ValueError("bootstrap_seed must be >= 0")
        if (
            not np.isfinite(self.confidence_level)
            or not 0.0 < self.confidence_level < 1.0
        ):
            raise ValueError("confidence_level must be between 0 and 1")
        if self.minimum_oos_dates < 1:
            raise ValueError("minimum_oos_dates must be >= 1")
        if not np.isfinite(self.minimum_skill) or self.minimum_skill < 0.0:
            raise ValueError("minimum_skill must be >= 0")


@dataclass(frozen=True)
class PredictionEvaluation:
    y_true: np.ndarray
    probability: np.ndarray
    dates: np.ndarray
    brier: float
    logloss: float

    @property
    def oos_rows(self) -> int:
        return int(len(self.y_true))

    @property
    def oos_dates(self) -> int:
        return int(len(pd.unique(self.dates)))


@dataclass(frozen=True)
class ImprovementInterval:
    estimate: float
    lower: float
    upper: float

    def as_dict(self) -> dict[str, float]:
        return {
            "estimate": float(self.estimate),
            "lower": float(self.lower),
            "upper": float(self.upper),
        }


@dataclass(frozen=True)
class PromotionDecision:
    promoted: bool
    rejection_reasons: tuple[str, ...]
    baseline_brier: float
    challenger_brier: float
    brier_improvement: ImprovementInterval
    brier_skill: float
    baseline_logloss: float
    challenger_logloss: float
    logloss_improvement: ImprovementInterval
    logloss_skill: float
    oos_dates: int
    oos_rows: int
    bootstrap_replicates: int
    bootstrap_seed: int
    confidence_level: float

    def as_dict(self) -> dict[str, object]:
        return {
            "promoted": bool(self.promoted),
            "rejection_reasons": list(self.rejection_reasons),
            "oos_dates": int(self.oos_dates),
            "oos_rows": int(self.oos_rows),
            "baseline_brier": float(self.baseline_brier),
            "challenger_brier": float(self.challenger_brier),
            "brier_improvement": self.brier_improvement.estimate,
            "brier_skill": float(self.brier_skill),
            "brier_improvement_ci": {
                "confidence_level": float(self.confidence_level),
                "lower": self.brier_improvement.lower,
                "upper": self.brier_improvement.upper,
            },
            "baseline_logloss": float(self.baseline_logloss),
            "challenger_logloss": float(self.challenger_logloss),
            "logloss_improvement": self.logloss_improvement.estimate,
            "logloss_skill": float(self.logloss_skill),
            "logloss_improvement_ci": {
                "confidence_level": float(self.confidence_level),
                "lower": self.logloss_improvement.lower,
                "upper": self.logloss_improvement.upper,
            },
            "bootstrap_replicates": int(self.bootstrap_replicates),
            "bootstrap_seed": int(self.bootstrap_seed),
        }


def _validated_vectors(
    y_true: Sequence[int] | np.ndarray,
    probability: Sequence[float] | np.ndarray,
    dates: Sequence[object] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    y = np.asarray(y_true, dtype=int).reshape(-1)
    p = np.asarray(probability, dtype=float).reshape(-1)
    d = pd.to_datetime(np.asarray(dates).reshape(-1), errors="coerce").to_numpy()
    if len(y) == 0 or len(y) != len(p) or len(y) != len(d):
        raise ValueError("y_true, probability, and dates must be non-empty and equal length")
    if not np.isin(y, [0, 1]).all():
        raise ValueError("y_true must contain only binary labels")
    if not np.isfinite(p).all() or bool(((p < 0.0) | (p > 1.0)).any()):
        raise ValueError("probabilities must be finite values in [0, 1]")
    if pd.isna(d).any():
        raise ValueError("dates must be valid and non-null")
    return y, p, d


def evaluate_predictions(
    y_true: Sequence[int] | np.ndarray,
    probability: Sequence[float] | np.ndarray,
    dates: Sequence[object] | np.ndarray,
) -> PredictionEvaluation:
    y, p, d = _validated_vectors(y_true, probability, dates)
    clipped = np.clip(p, 1e-9, 1.0 - 1e-9)
    return PredictionEvaluation(
        y_true=y,
        probability=p,
        dates=d,
        brier=float(brier_score_loss(y, p)),
        logloss=float(log_loss(y, np.column_stack([1.0 - clipped, clipped]), labels=[0, 1])),
    )


def relative_skill(baseline_loss: float, challenger_loss: float) -> float:
    """Return relative loss reduction; positive means improvement."""
    if not np.isfinite(baseline_loss) or not np.isfinite(challenger_loss) or baseline_loss <= 0.0:
        return float("nan")
    return float((baseline_loss - challenger_loss) / baseline_loss)


def assert_temporal_partitions(
    dates: Sequence[object] | np.ndarray,
    train_mask: Sequence[bool] | np.ndarray,
    calibration_mask: Sequence[bool] | np.ndarray,
    test_mask: Sequence[bool] | np.ndarray,
) -> None:
    """Verify strict date-level train/calibration/test ordering and separation."""
    d = pd.to_datetime(np.asarray(dates).reshape(-1), errors="raise").normalize()
    masks = [
        np.asarray(mask, dtype=bool).reshape(-1)
        for mask in (train_mask, calibration_mask, test_mask)
    ]
    if any(len(mask) != len(d) for mask in masks):
        raise ValueError("partition masks must match dates")
    if any(not bool(mask.any()) for mask in masks):
        raise ValueError("train, calibration, and test partitions must be non-empty")
    if np.sum(np.column_stack(masks), axis=1).max() > 1:
        raise ValueError("a row belongs to more than one temporal partition")

    train_dates, calibration_dates, test_dates = [set(d[mask]) for mask in masks]
    if (
        train_dates & calibration_dates
        or train_dates & test_dates
        or calibration_dates & test_dates
    ):
        raise ValueError("the same draw date cannot cross temporal partitions")
    if max(train_dates) >= min(calibration_dates):
        raise ValueError("training dates must precede calibration dates")
    if max(calibration_dates) >= min(test_dates):
        raise ValueError("calibration dates must precede test dates")


def predict_with_feature_allowlist(
    model: ProbabilityModel,
    frame: pd.DataFrame,
    features: Sequence[str],
) -> np.ndarray:
    """Predict using only the explicit production feature allowlist."""
    allowlist = list(features)
    if not allowlist or len(allowlist) != len(set(allowlist)):
        raise ValueError("feature allowlist must be non-empty and contain no duplicates")
    missing = [feature for feature in allowlist if feature not in frame.columns]
    if missing:
        raise ValueError(f"feature allowlist columns missing from frame: {missing}")
    values = frame.loc[:, allowlist].astype(np.float32).to_numpy()
    if not np.isfinite(values).all():
        raise ValueError("production features must be finite")
    prediction = np.asarray(model.predict_proba(values), dtype=float)
    if prediction.ndim != 2 or prediction.shape != (len(frame), 2):
        raise ValueError("predict_proba must return shape (rows, 2)")
    probability = prediction[:, 1]
    if not np.isfinite(probability).all() or bool(
        ((probability < 0.0) | (probability > 1.0)).any()
    ):
        raise ValueError("model returned probabilities outside [0, 1]")
    return probability


def _paired_date_bootstrap(
    baseline: PredictionEvaluation,
    challenger: PredictionEvaluation,
    *,
    config: ValidationConfig,
) -> tuple[np.ndarray, np.ndarray]:
    if not np.array_equal(baseline.y_true, challenger.y_true):
        raise ValueError("baseline and challenger must use identical OOS labels")
    if not np.array_equal(baseline.dates, challenger.dates):
        raise ValueError("baseline and challenger must use identical OOS dates and rows")

    unique_dates = pd.unique(baseline.dates)
    groups = [np.flatnonzero(baseline.dates == date) for date in unique_dates]
    rng = np.random.default_rng(config.bootstrap_seed)
    brier_delta = np.empty(config.bootstrap_replicates, dtype=float)
    logloss_delta = np.empty(config.bootstrap_replicates, dtype=float)
    for replicate in range(config.bootstrap_replicates):
        sampled = rng.integers(0, len(groups), size=len(groups))
        # Concatenation intentionally preserves duplicate sampled dates and all
        # correlated candidate rows belonging to each sampled draw.
        idx = np.concatenate([groups[int(i)] for i in sampled])
        y = baseline.y_true[idx]
        base = evaluate_predictions(y, baseline.probability[idx], baseline.dates[idx])
        candidate = evaluate_predictions(y, challenger.probability[idx], challenger.dates[idx])
        brier_delta[replicate] = base.brier - candidate.brier
        logloss_delta[replicate] = base.logloss - candidate.logloss
    return brier_delta, logloss_delta


def compare_paired_predictions(
    baseline: PredictionEvaluation,
    challenger: PredictionEvaluation,
    *,
    config: ValidationConfig | None = None,
    temporal_checks_pass: bool,
) -> PromotionDecision:
    """Compare paired OOS forecasts and apply the conservative promotion gate."""
    cfg = config or ValidationConfig()
    brier_samples, logloss_samples = _paired_date_bootstrap(baseline, challenger, config=cfg)
    tail = (1.0 - cfg.confidence_level) / 2.0
    brier_estimate = baseline.brier - challenger.brier
    logloss_estimate = baseline.logloss - challenger.logloss
    brier_interval = ImprovementInterval(
        estimate=float(brier_estimate),
        lower=float(np.quantile(brier_samples, tail)),
        upper=float(np.quantile(brier_samples, 1.0 - tail)),
    )
    logloss_interval = ImprovementInterval(
        estimate=float(logloss_estimate),
        lower=float(np.quantile(logloss_samples, tail)),
        upper=float(np.quantile(logloss_samples, 1.0 - tail)),
    )
    brier_skill = relative_skill(baseline.brier, challenger.brier)
    logloss_skill = relative_skill(baseline.logloss, challenger.logloss)

    reasons: list[str] = []
    numeric = [
        baseline.brier,
        challenger.brier,
        baseline.logloss,
        challenger.logloss,
        brier_skill,
        logloss_skill,
        brier_interval.lower,
        logloss_interval.lower,
    ]
    if not np.isfinite(numeric).all():
        reasons.append("invalid_configuration")
    if not temporal_checks_pass:
        reasons.append("temporal_leakage")
    if baseline.oos_dates < cfg.minimum_oos_dates:
        reasons.append("insufficient_oos_dates")
    if not np.isfinite(brier_skill) or brier_skill <= cfg.minimum_skill:
        reasons.append("negative_brier_skill")
    if not np.isfinite(logloss_skill) or logloss_skill <= cfg.minimum_skill:
        reasons.append("negative_logloss_skill")
    if not np.isfinite(brier_interval.lower) or brier_interval.lower <= 0.0:
        reasons.append("brier_ci_crosses_zero")
    if not np.isfinite(logloss_interval.lower) or logloss_interval.lower <= 0.0:
        reasons.append("logloss_ci_crosses_zero")

    return PromotionDecision(
        promoted=not reasons,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
        baseline_brier=baseline.brier,
        challenger_brier=challenger.brier,
        brier_improvement=brier_interval,
        brier_skill=brier_skill,
        baseline_logloss=baseline.logloss,
        challenger_logloss=challenger.logloss,
        logloss_improvement=logloss_interval,
        logloss_skill=logloss_skill,
        oos_dates=baseline.oos_dates,
        oos_rows=baseline.oos_rows,
        bootstrap_replicates=cfg.bootstrap_replicates,
        bootstrap_seed=cfg.bootstrap_seed,
        confidence_level=cfg.confidence_level,
    )
