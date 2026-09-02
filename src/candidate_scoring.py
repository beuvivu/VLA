from __future__ import annotations

"""Configurable candidate ranking; scores are not calibrated probabilities."""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping

import numpy as np
import pandas as pd

from frequency_stats import FrequencyConfig, NUMBER_COLUMNS, compute_frequency_stats, history_before
from gap_cycle_stats import compute_gap_stats

Mode = Literal["loto", "de"]
EMAInitialization = Literal["zero", "first", "historical_mean"]


@dataclass(frozen=True)
class ScoringWeights:
    frequency: float = 0.35
    gap: float = 0.0
    recency: float = 0.25
    ema: float = 0.40
    cycle: float = 0.0
    conditional: float = 0.0
    pattern: float = 0.0

    def __post_init__(self) -> None:
        values = self.as_dict().values()
        if any(not np.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("scoring weights must be finite and non-negative")
        if sum(values) <= 0.0:
            raise ValueError("at least one scoring weight must be positive")

    def as_dict(self) -> dict[str, float]:
        return {
            "frequency": float(self.frequency),
            "gap": float(self.gap),
            "recency": float(self.recency),
            "ema": float(self.ema),
            "cycle": float(self.cycle),
            "conditional": float(self.conditional),
            "pattern": float(self.pattern),
        }


@dataclass(frozen=True)
class ScoringConfig:
    lookback_days: int = 30
    ema_span: int = 14
    minimum_history: int = 5
    ema_initialization: EMAInitialization = "zero"
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    conditional_scores: Mapping[int, float] = field(default_factory=dict)
    pattern_scores: Mapping[int, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.lookback_days < 1:
            raise ValueError("lookback_days must be >= 1")
        if self.ema_span < 1:
            raise ValueError("ema_span must be >= 1")
        if self.minimum_history < 1:
            raise ValueError("minimum_history must be >= 1")
        if self.ema_initialization not in {"zero", "first", "historical_mean"}:
            raise ValueError("unknown EMA initialization")
        for name, scores in (
            ("conditional_scores", self.conditional_scores),
            ("pattern_scores", self.pattern_scores),
        ):
            normalized: dict[int, float] = {}
            for number, value in scores.items():
                try:
                    canonical_number = int(number)
                    canonical_value = float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"invalid {name} entry: {number}={value}") from exc
                if (
                    not 0 <= canonical_number <= 99
                    or not np.isfinite(canonical_value)
                    or not 0.0 <= canonical_value <= 1.0
                ):
                    raise ValueError(f"invalid {name} entry: {number}={value}")
                if canonical_number in normalized:
                    raise ValueError(f"duplicate canonical {name} number: {canonical_number:02d}")
                normalized[canonical_number] = canonical_value
            object.__setattr__(self, name, MappingProxyType(normalized))


@dataclass(frozen=True)
class CandidateScore:
    number: int
    number_str: str
    score: float
    component_scores: Mapping[str, float | None]
    evidence: Mapping[str, object]
    explanation: tuple[str, ...]
    feature_provenance: Mapping[str, str]


def _normalize(values: np.ndarray) -> np.ndarray:
    finite = np.isfinite(values)
    if not bool(finite.any()):
        return np.zeros_like(values, dtype=float)
    low, high = float(np.min(values[finite])), float(np.max(values[finite]))
    out = np.zeros_like(values, dtype=float)
    if high > low:
        out[finite] = (values[finite] - low) / (high - low)
    return out


def _ema(hit: np.ndarray, *, span: int, initialization: EMAInitialization) -> np.ndarray:
    if len(hit) == 0:
        return np.zeros(100, dtype=float)
    alpha = 2.0 / (span + 1.0)
    if initialization == "zero":
        state = np.zeros(100, dtype=float)
        start = 0
    elif initialization == "first":
        state = hit[0].astype(float)
        start = 1
    else:
        state = hit.astype(float).mean(axis=0)
        start = 0
    for row in hit[start:]:
        state = alpha * row.astype(float) + (1.0 - alpha) * state
    return state


def rank_candidates(
    history: pd.DataFrame,
    as_of_date: object,
    mode: Mode,
    config: ScoringConfig | None = None,
) -> list[CandidateScore]:
    """Rank 00..99 from strictly historical, normalized descriptive signals."""
    if mode not in {"loto", "de"}:
        raise ValueError("mode must be loto or de")
    cfg = config or ScoringConfig()
    window = history_before(
        history,
        as_of_date,
        config=FrequencyConfig(lookback_days=cfg.lookback_days),
    )
    frequency = compute_frequency_stats(
        history, as_of_date, lookback_days=cfg.lookback_days
    ).set_index("number")
    gap = compute_gap_stats(history, as_of_date, lookback_days=cfg.lookback_days).set_index(
        "number"
    )
    hit = window.loc[:, list(NUMBER_COLUMNS)].to_numpy(dtype=int, copy=False) > 0

    frequency_score = _normalize(frequency["occurrence_count"].to_numpy(dtype=float))
    current_gap = gap["current_gap_draws"].to_numpy(dtype=float)
    recency_score = 1.0 / (1.0 + current_gap)
    gap_score = np.nan_to_num(gap["gap_percentile"].to_numpy(dtype=float), nan=0.0)
    ema_raw = _ema(hit, span=cfg.ema_span, initialization=cfg.ema_initialization)
    ema_score = _normalize(ema_raw)
    median_gap = gap["median_gap_draws"].to_numpy(dtype=float)
    cycle_raw = np.divide(
        1.0,
        1.0 + np.abs(current_gap - median_gap),
        out=np.zeros(100, dtype=float),
        where=np.isfinite(median_gap),
    )

    weights = cfg.weights.as_dict()
    provenance = {
        "frequency": "frequency_stats.compute_frequency_stats",
        "gap": "gap_cycle_stats.compute_gap_stats.gap_percentile",
        "recency": "gap_cycle_stats.compute_gap_stats.current_gap_draws",
        "ema": "candidate_scoring._ema",
        "cycle": "gap_cycle_stats.compute_gap_stats.median_gap_draws",
        "conditional": "ScoringConfig.conditional_scores",
        "pattern": "ScoringConfig.pattern_scores",
    }
    results: list[CandidateScore] = []
    for number in range(100):
        components: dict[str, float | None] = {
            "frequency": float(frequency_score[number]),
            "gap": float(gap_score[number]),
            "recency": float(recency_score[number]),
            "ema": float(ema_score[number]),
            "cycle": float(cycle_raw[number]),
            "conditional": (
                float(cfg.conditional_scores[number]) if number in cfg.conditional_scores else None
            ),
            "pattern": (
                float(cfg.pattern_scores[number]) if number in cfg.pattern_scores else None
            ),
        }
        usable = {
            name: value
            for name, value in components.items()
            if value is not None and weights[name] > 0.0
        }
        denominator = sum(weights[name] for name in usable)
        score = (
            sum(weights[name] * float(value) for name, value in usable.items()) / denominator
            if denominator > 0.0 and len(window) >= cfg.minimum_history
            else 0.0
        )
        missing = [
            name for name, value in components.items() if value is None and weights[name] > 0
        ]
        explanation = [
            f"frequency occurrences={int(frequency.loc[number, 'occurrence_count'])}",
            f"current gap={int(current_gap[number])} completed draw(s)",
            f"EMA span={cfg.ema_span}, initialization={cfg.ema_initialization}",
            "score is a ranking index, not a calibrated probability",
        ]
        if missing:
            explanation.append(f"missing optional components excluded: {', '.join(missing)}")
        results.append(
            CandidateScore(
                number=number,
                number_str=f"{number:02d}",
                score=float(score),
                component_scores=MappingProxyType(components),
                evidence=MappingProxyType(
                    {
                        "history_draws": len(window),
                        "occurrence_count": int(frequency.loc[number, "occurrence_count"]),
                        "draw_count": int(frequency.loc[number, "draw_count"]),
                        "current_gap_draws": int(current_gap[number]),
                        "ema_raw": float(ema_raw[number]),
                    }
                ),
                explanation=tuple(explanation),
                feature_provenance=MappingProxyType(provenance),
            )
        )
    return sorted(results, key=lambda item: (-item.score, item.number))
