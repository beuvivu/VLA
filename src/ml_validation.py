from __future__ import annotations

"""Shared probabilistic validation primitives for temporal ML challengers.

The module deliberately evaluates what production serves:
- Loto uses 100 Bernoulli marginals per draw;
- De uses one categorical distribution over 00..99 per draw.

Uncertainty is estimated with a paired date-cluster bootstrap. Candidate rows
inside one draw are never resampled independently.
"""

from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd

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

    def __post_init__(self) -> None:
        if self.replicates < 100:
            raise ValueError("bootstrap_replicates must be >= 100")
        if not 0.50 < self.confidence < 1.0:
            raise ValueError("promotion_ci must be between 0.50 and 1.0")
        if self.minimum_oos_dates < 5:
            raise ValueError("minimum_oos_dates must be >= 5")

    def with_seed(self, seed: int) -> "BootstrapConfig":
        return replace(self, seed=int(seed))


def relative_skill(*, baseline_loss: float, challenger_loss: float) -> float:
    """Return (baseline - challenger) / baseline; positive means improvement."""
    if (
        not np.isfinite(baseline_loss)
        or not np.isfinite(challenger_loss)
        or baseline_loss <= 0.0
    ):
        return float("-inf")
    return float((baseline_loss - challenger_loss) / baseline_loss)


def _validate_probability_vector(prob: np.ndarray, *, name: str) -> np.ndarray:
    out = np.asarray(prob, dtype=float)
    if out.ndim != 1 or not np.isfinite(out).all():
        raise ValueError(f"{name} probabilities must be a finite 1-D vector")
    if np.any((out < 0.0) | (out > 1.0)):
        raise ValueError(f"{name} probabilities must be within [0, 1]")
    return out


def _prepare_observations(
    frame: pd.DataFrame,
    y: np.ndarray | pd.Series,
    baseline_prob: np.ndarray,
    challenger_prob: np.ndarray,
) -> pd.DataFrame:
    if not {"anchor_date", "number"}.issubset(frame.columns):
        raise ValueError("evaluation frame requires anchor_date and number")

    target = np.asarray(y, dtype=int)
    baseline = _validate_probability_vector(baseline_prob, name="baseline")
    challenger = _validate_probability_vector(challenger_prob, name="challenger")
    if not (len(frame) == len(target) == len(baseline) == len(challenger)):
        raise ValueError("frame/target/probability length mismatch")
    if not np.isin(target, [0, 1]).all():
        raise ValueError("targets must be binary")

    obs = pd.DataFrame(
        {
            "date": pd.to_datetime(frame["anchor_date"], errors="raise").dt.normalize(),
            "number": pd.to_numeric(frame["number"], errors="raise").astype(int),
            "target": target,
            "baseline_prob": baseline,
            "challenger_prob": challenger,
        }
    )
    if obs.duplicated(["date", "number"]).any():
        raise ValueError("duplicate date/number rows in OOS evaluation")

    expected = set(range(100))
    for day, sub in obs.groupby("date", sort=True):
        if len(sub) != 100 or set(sub["number"].tolist()) != expected:
            raise ValueError(f"{day.date()}: OOS date must contain exactly 00..99")
    return obs.sort_values(["date", "number"]).reset_index(drop=True)


def daily_probabilistic_losses(
    frame: pd.DataFrame,
    y: np.ndarray | pd.Series,
    prob: np.ndarray,
    *,
    mode: Mode,
    probability_name: str = "probability",
) -> tuple[pd.DataFrame, np.ndarray]:
    """Evaluate one prediction stream in the exact production probability space."""
    checked = _validate_probability_vector(prob, name=probability_name)
    dummy = checked.copy()
    obs = _prepare_observations(frame, y, checked, dummy)
    served = np.empty(len(obs), dtype=float)
    rows: list[dict[str, object]] = []

    for day, idx in obs.groupby("date", sort=True).groups.items():
        loc = np.asarray(list(idx), dtype=int)
        sub = obs.loc[loc]
        raw = sub["baseline_prob"].to_numpy(dtype=float)
        target = sub["target"].to_numpy(dtype=int)

        if mode == "de":
            if int(target.sum()) != 1:
                raise ValueError(
                    f"{pd.Timestamp(day).date()}: De evaluation requires exactly one positive"
                )
            p = normalize_distribution(np.clip(raw, 0.0, None))
            y_idx = int(np.argmax(target))
            brier = categorical_brier(p, y_idx)
            logloss = categorical_logloss(p, y_idx)
        else:
            p = np.clip(raw, 1e-9, 1.0 - 1e-9)
            brier = bernoulli_brier(p, target)
            logloss = bernoulli_logloss(p, target)

        served[loc] = p
        rows.append(
            {
                "date": pd.Timestamp(day),
                "rows": int(len(sub)),
                "brier": float(brier),
                "logloss": float(logloss),
            }
        )

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True), served


def _paired_daily_losses(
    frame: pd.DataFrame,
    y: np.ndarray | pd.Series,
    baseline_prob: np.ndarray,
    challenger_prob: np.ndarray,
    *,
    mode: Mode,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    obs = _prepare_observations(frame, y, baseline_prob, challenger_prob)
    baseline_daily, baseline_served = daily_probabilistic_losses(
        obs.rename(columns={"date": "anchor_date"}),
        obs["target"].to_numpy(dtype=int),
        obs["baseline_prob"].to_numpy(dtype=float),
        mode=mode,
        probability_name="baseline",
    )
    challenger_daily, challenger_served = daily_probabilistic_losses(
        obs.rename(columns={"date": "anchor_date"}),
        obs["target"].to_numpy(dtype=int),
        obs["challenger_prob"].to_numpy(dtype=float),
        mode=mode,
        probability_name="challenger",
    )
    if not baseline_daily["date"].equals(challenger_daily["date"]):
        raise ValueError("baseline/challenger OOS dates are not paired")

    paired = baseline_daily.rename(
        columns={"brier": "baseline_brier", "logloss": "baseline_logloss"}
    ).copy()
    paired["challenger_brier"] = challenger_daily["brier"].to_numpy(dtype=float)
    paired["challenger_logloss"] = challenger_daily["logloss"].to_numpy(dtype=float)
    paired["brier_delta"] = paired["baseline_brier"] - paired["challenger_brier"]
    paired["logloss_delta"] = paired["baseline_logloss"] - paired["challenger_logloss"]
    return paired, baseline_served, challenger_served


def paired_cluster_bootstrap(
    daily: pd.DataFrame,
    *,
    config: BootstrapConfig,
) -> dict[str, object]:
    """Paired bootstrap over DATE clusters; duplicated sampled dates keep multiplicity."""
    required = {
        "date",
        "baseline_brier",
        "challenger_brier",
        "baseline_logloss",
        "challenger_logloss",
    }
    if not required.issubset(daily.columns):
        raise ValueError(f"bootstrap daily table missing {sorted(required - set(daily.columns))}")
    if daily["date"].duplicated().any():
        raise ValueError("bootstrap input must have one aggregate row per OOS date")

    n_dates = int(len(daily))
    if n_dates < config.minimum_oos_dates:
        return {
            "valid": False,
            "cluster_unit": "date",
            "oos_dates": n_dates,
            "replicates": int(config.replicates),
            "seed": int(config.seed),
            "confidence": float(config.confidence),
            "brier_ci_low": float("nan"),
            "brier_ci_high": float("nan"),
            "logloss_ci_low": float("nan"),
            "logloss_ci_high": float("nan"),
            "reason": "insufficient_oos_dates",
        }

    brier_delta = (
        pd.to_numeric(daily["baseline_brier"], errors="raise").to_numpy(dtype=float)
        - pd.to_numeric(daily["challenger_brier"], errors="raise").to_numpy(dtype=float)
    )
    logloss_delta = (
        pd.to_numeric(daily["baseline_logloss"], errors="raise").to_numpy(dtype=float)
        - pd.to_numeric(daily["challenger_logloss"], errors="raise").to_numpy(dtype=float)
    )
    if not np.isfinite(brier_delta).all() or not np.isfinite(logloss_delta).all():
        return {
            "valid": False,
            "cluster_unit": "date",
            "oos_dates": n_dates,
            "replicates": int(config.replicates),
            "seed": int(config.seed),
            "confidence": float(config.confidence),
            "brier_ci_low": float("nan"),
            "brier_ci_high": float("nan"),
            "logloss_ci_low": float("nan"),
            "logloss_ci_high": float("nan"),
            "reason": "invalid_metrics",
        }

    rng = np.random.default_rng(config.seed)
    sample_idx = rng.integers(0, n_dates, size=(config.replicates, n_dates))
    # Indexing keeps duplicate dates as duplicate clusters; no deduplication occurs.
    boot_brier = brier_delta[sample_idx].mean(axis=1)
    boot_logloss = logloss_delta[sample_idx].mean(axis=1)
    alpha = (1.0 - config.confidence) / 2.0
    lo, hi = alpha, 1.0 - alpha
    return {
        "valid": True,
        "cluster_unit": "date",
        "oos_dates": n_dates,
        "replicates": int(config.replicates),
        "seed": int(config.seed),
        "confidence": float(config.confidence),
        "brier_ci_low": float(np.quantile(boot_brier, lo)),
        "brier_ci_high": float(np.quantile(boot_brier, hi)),
        "logloss_ci_low": float(np.quantile(boot_logloss, lo)),
        "logloss_ci_high": float(np.quantile(boot_logloss, hi)),
        "reason": "ok",
    }


def promotion_reasons(
    *,
    brier_skill: float,
    logloss_skill: float,
    brier_ci_low: float,
    logloss_ci_low: float,
    oos_dates: int,
    minimum_oos_dates: int,
    bootstrap_valid: bool,
) -> list[str]:
    """Return fail-closed machine-readable reasons; empty means the gate passes."""
    reasons: list[str] = []
    values = [brier_skill, logloss_skill, brier_ci_low, logloss_ci_low]
    if not all(np.isfinite(v) for v in values):
        reasons.append("invalid_metrics")
    if int(oos_dates) < int(minimum_oos_dates):
        reasons.append("insufficient_oos_dates")
    if not bootstrap_valid:
        reasons.append("bootstrap_failure")
    if np.isfinite(brier_skill) and brier_skill <= 0.0:
        reasons.append("nonpositive_brier_skill")
    if np.isfinite(logloss_skill) and logloss_skill <= 0.0:
        reasons.append("nonpositive_logloss_skill")
    if np.isfinite(brier_ci_low) and brier_ci_low <= 0.0:
        reasons.append("brier_ci_crosses_zero")
    if np.isfinite(logloss_ci_low) and logloss_ci_low <= 0.0:
        reasons.append("logloss_ci_crosses_zero")
    return list(dict.fromkeys(reasons))


def evaluate_paired_oos(
    frame: pd.DataFrame,
    y: np.ndarray | pd.Series,
    baseline_prob: np.ndarray,
    challenger_prob: np.ndarray,
    *,
    mode: Mode,
    bootstrap: BootstrapConfig,
) -> tuple[dict[str, object], pd.DataFrame]:
    """Evaluate matched OOS observations and return a conservative promotion gate."""
    daily, baseline_served, challenger_served = _paired_daily_losses(
        frame,
        y,
        baseline_prob,
        challenger_prob,
        mode=mode,
    )
    baseline_brier = float(daily["baseline_brier"].mean())
    challenger_brier = float(daily["challenger_brier"].mean())
    baseline_logloss = float(daily["baseline_logloss"].mean())
    challenger_logloss = float(daily["challenger_logloss"].mean())
    brier_delta = float(baseline_brier - challenger_brier)
    logloss_delta = float(baseline_logloss - challenger_logloss)
    brier_skill = relative_skill(
        baseline_loss=baseline_brier, challenger_loss=challenger_brier
    )
    logloss_skill = relative_skill(
        baseline_loss=baseline_logloss, challenger_loss=challenger_logloss
    )
    boot = paired_cluster_bootstrap(daily, config=bootstrap)
    reasons = promotion_reasons(
        brier_skill=brier_skill,
        logloss_skill=logloss_skill,
        brier_ci_low=float(boot["brier_ci_low"]),
        logloss_ci_low=float(boot["logloss_ci_low"]),
        oos_dates=len(daily),
        minimum_oos_dates=bootstrap.minimum_oos_dates,
        bootstrap_valid=bool(boot["valid"]),
    )
    report: dict[str, object] = {
        "mode": mode,
        "oos_dates": int(len(daily)),
        "oos_rows": int(daily["rows"].sum()),
        "baseline_brier": baseline_brier,
        "challenger_brier": challenger_brier,
        "brier_improvement": brier_delta,
        "brier_skill": brier_skill,
        "brier_ci_low": float(boot["brier_ci_low"]),
        "brier_ci_high": float(boot["brier_ci_high"]),
        "baseline_logloss": baseline_logloss,
        "challenger_logloss": challenger_logloss,
        "logloss_improvement": logloss_delta,
        "logloss_skill": logloss_skill,
        "logloss_ci_low": float(boot["logloss_ci_low"]),
        "logloss_ci_high": float(boot["logloss_ci_high"]),
        "bootstrap": boot,
        "promoted": not reasons,
        "rejection_reasons": reasons,
        "probability_space": "categorical_100" if mode == "de" else "bernoulli_marginals",
    }
    daily = daily.copy()
    daily["baseline_served_prob_sum"] = np.nan
    daily["challenger_served_prob_sum"] = np.nan
    if mode == "de":
        # Forensic assertion: every served De date is a normalized categorical distribution.
        obs = _prepare_observations(frame, y, baseline_prob, challenger_prob)
        dates = obs["date"].to_numpy()
        for day in daily["date"]:
            mask = dates == np.datetime64(pd.Timestamp(day))
            daily.loc[daily["date"] == day, "baseline_served_prob_sum"] = float(
                baseline_served[mask].sum()
            )
            daily.loc[daily["date"] == day, "challenger_served_prob_sum"] = float(
                challenger_served[mask].sum()
            )
    return report, daily
