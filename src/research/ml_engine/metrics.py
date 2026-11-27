from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from research.ml_engine.schema import BASELINE_RATE, NUMBER_SPACE
from core.xsmb_domain import LOTO_DRAWS_PER_DAY

_EPSILON: Final[float] = 1e-6

DEFAULT_K_VALUES: Final[tuple[int, ...]] = (3, 5, 10, 27)

DEFAULT_STAKE: Final[float] = 23.0
DEFAULT_PAYOUT: Final[float] = 80.0
BASELINE_OCCURRENCES: Final[float] = LOTO_DRAWS_PER_DAY / NUMBER_SPACE


@dataclass(frozen=True)
class EconomicModel:

    stake: float = DEFAULT_STAKE
    payout: float = DEFAULT_PAYOUT

    def __post_init__(self) -> None:
        if self.stake <= 0 or self.payout <= 0:
            raise ValueError("stake và payout phải dương")
        if self.payout <= self.stake:
            raise ValueError("payout phải lớn hơn stake, nếu không mọi cược đều lỗ")

    @property
    def break_even_rate(self) -> float:
        return self.stake / self.payout

    @property
    def baseline_edge(self) -> float:
        return (BASELINE_OCCURRENCES * self.payout - self.stake) / self.stake

    def required_relative_lift(self) -> float:
        return self.break_even_rate / BASELINE_OCCURRENCES - 1.0


@dataclass(frozen=True)
class DailyScore:

    logloss: float
    brier: float
    baseline_logloss: float
    baseline_brier: float
    hit_rate_at: dict[int, int]
    actual_hits: int
    occurrences_at: dict[int, int]


def validate_probabilities(probabilities: np.ndarray) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if values.shape != (NUMBER_SPACE,):
        raise ValueError(f"probabilities phải có dạng ({NUMBER_SPACE},)")
    if not np.all(np.isfinite(values)):
        raise ValueError("probabilities phải hữu hạn")
    if np.any(values < 0.0) or np.any(values > 1.0):
        raise ValueError("probabilities phải nằm trong [0, 1]")
    return values


def score_day(
    probabilities: np.ndarray,
    outcome: np.ndarray,
    *,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
    counts: np.ndarray | None = None,
) -> DailyScore:
    probabilities = validate_probabilities(probabilities)
    outcome = np.asarray(outcome, dtype=float)
    if outcome.shape != (NUMBER_SPACE,):
        raise ValueError(f"cần hai mảng dạng ({NUMBER_SPACE},)")
    if not np.all(np.isfinite(outcome)) or not np.all((outcome == 0) | (outcome == 1)):
        raise ValueError("outcome phải hữu hạn và nhị phân 0/1")
    occurrences = outcome if counts is None else np.asarray(counts)
    if occurrences.shape != (NUMBER_SPACE,):
        raise ValueError(f"counts phải có dạng ({NUMBER_SPACE},)")
    if (occurrences.dtype.kind not in "buif" or not np.all(np.isfinite(occurrences))
            or np.any(occurrences < 0) or np.any(occurrences != np.floor(occurrences))):
        raise ValueError("counts phải là số nguyên hữu hạn không âm")
    if not np.array_equal(occurrences > 0, outcome > 0):
        raise ValueError("counts phải khớp các con về trong outcome")

    p = np.clip(probabilities, _EPSILON, 1.0 - _EPSILON)
    y = outcome.astype(float)
    b = BASELINE_RATE

    order = np.argsort(-p, kind="stable")
    return DailyScore(
        logloss=float(-np.mean(y * np.log(p) + (1 - y) * np.log1p(-p))),
        brier=float(np.mean((probabilities - y) ** 2)),
        baseline_logloss=float(-np.mean(y * np.log(b) + (1 - y) * np.log1p(-b))),
        baseline_brier=float(np.mean((b - y) ** 2)),
        hit_rate_at={k: int(y[order[:k]].sum()) for k in k_values},
        actual_hits=int(y.sum()),
        occurrences_at={k: int(occurrences[order[:k]].sum()) for k in k_values},
    )


@dataclass(frozen=True)
class PerformanceReport:

    days: int
    logloss: float
    brier: float
    logloss_skill: float
    brier_skill: float
    paired_t: float
    hit_rate_at: dict[int, float]
    random_hit_rate_at: dict[int, float]
    precision_at: dict[int, float]
    recall_at: dict[int, float]
    profit_ratio: dict[int, float]

    @property
    def beats_baseline(self) -> bool:
        return self.logloss_skill > 0.0 and self.paired_t > 1.96

    def describe(self) -> str:
        verdict = "VƯỢT nền" if self.beats_baseline else "không vượt nền"
        hit5 = self.hit_rate_at.get(5, float("nan"))
        return (
            f"{self.days} kỳ · kỹ năng={self.logloss_skill:+.5f} · t={self.paired_t:+.2f} · "
            f"trúng@5={hit5:.3f} · {verdict}"
        )


class PerformanceTracker:

    def __init__(
        self,
        *,
        k_values: tuple[int, ...] = DEFAULT_K_VALUES,
        economics: EconomicModel | None = None,
    ) -> None:
        self.k_values = k_values
        self.economics = economics or EconomicModel()
        self._scores: list[DailyScore] = []

    def add(
        self, probabilities: np.ndarray, outcome: np.ndarray, *, counts: np.ndarray | None = None
    ) -> DailyScore:
        score = score_day(probabilities, outcome, k_values=self.k_values, counts=counts)
        self._scores.append(score)
        return score

    def report(self) -> PerformanceReport:
        if not self._scores:
            raise ValueError("chưa có kỳ nào được chấm")

        model_loss = np.array([s.logloss for s in self._scores])
        base_loss = np.array([s.baseline_logloss for s in self._scores])
        difference = base_loss - model_loss
        spread = difference.std(ddof=1) if difference.size > 1 else 0.0
        t_stat = (
            float(difference.mean() / (spread / np.sqrt(difference.size))) if spread > 0 else 0.0
        )

        brier = float(np.mean([s.brier for s in self._scores]))
        base_brier = float(np.mean([s.baseline_brier for s in self._scores]))
        actual = np.array([s.actual_hits for s in self._scores], dtype=float)

        hit_rate, random_rate, precision, recall, profit = {}, {}, {}, {}, {}
        for k in self.k_values:
            hits = np.array([s.hit_rate_at.get(k, 0) for s in self._scores], dtype=float)
            hit_rate[k] = float(hits.mean())
            random_rate[k] = float((k / NUMBER_SPACE) * actual.mean())
            precision[k] = float((hits / k).mean())
            recall[k] = float((hits / np.maximum(actual, 1.0)).mean())
            occurrences = np.array([s.occurrences_at.get(k, 0) for s in self._scores], dtype=float)
            revenue = occurrences * self.economics.payout
            cost = k * self.economics.stake
            profit[k] = float(((revenue - cost) / cost).mean())

        return PerformanceReport(
            days=len(self._scores),
            logloss=float(model_loss.mean()),
            brier=brier,
            logloss_skill=float((base_loss.mean() - model_loss.mean()) / base_loss.mean()),
            brier_skill=float((base_brier - brier) / base_brier) if base_brier > 0 else 0.0,
            paired_t=t_stat,
            hit_rate_at=hit_rate,
            random_hit_rate_at=random_rate,
            precision_at=precision,
            recall_at=recall,
            profit_ratio=profit,
        )
