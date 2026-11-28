from __future__ import annotations

import math
from collections.abc import Callable
from functools import partial
from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy import stats

from core.xsmb_domain import LOTO_DRAWS_PER_DAY, UNIFORM_TWO_DIGIT_RATE

NUMBER_SPACE: Final[int] = 100
DEFAULT_SIMULATIONS: Final[int] = 2000
DEFAULT_SEED: Final[int] = 20260906


@dataclass(frozen=True)
class TestResult:

    name: str
    question: str
    statistic: float
    p_value: float
    null_mean: float
    null_sd: float
    simulations: int

    @property
    def z_score(self) -> float:
        return (self.statistic - self.null_mean) / self.null_sd if self.null_sd > 0 else 0.0

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05

    def describe(self) -> str:
        verdict = "CÓ cấu trúc" if self.significant else "không phân biệt được với ngẫu nhiên"
        return (
            f"{self.name:<34} thống kê={self.statistic:>10.4f}  "
            f"z={self.z_score:>+6.2f}  p={self.p_value:.4f}  {verdict}"
        )


def simulate_draws(n_days: int, rng: np.random.Generator) -> np.ndarray:
    draws = rng.integers(0, NUMBER_SPACE, size=(n_days, LOTO_DRAWS_PER_DAY))
    counts = np.zeros((n_days, NUMBER_SPACE), dtype=np.int16)
    rows = np.repeat(np.arange(n_days), LOTO_DRAWS_PER_DAY)
    np.add.at(counts, (rows, draws.ravel()), 1)
    return counts


def monte_carlo_test(
    name: str,
    question: str,
    statistic_of: Callable[[np.ndarray], float],
    observed_counts: np.ndarray,
    *,
    simulations: int = DEFAULT_SIMULATIONS,
    seed: int = DEFAULT_SEED,
    two_sided: bool = True,
) -> TestResult:
    observed = float(statistic_of(observed_counts))
    rng = np.random.default_rng(seed)
    n_days = observed_counts.shape[0]

    null = np.empty(simulations, dtype=float)
    for i in range(simulations):
        null[i] = statistic_of(simulate_draws(n_days, rng))

    if two_sided:
        extreme = int(np.sum(np.abs(null - null.mean()) >= abs(observed - null.mean())))
    else:
        extreme = int(np.sum(null >= observed))
    p_value = (extreme + 1) / (simulations + 1)

    return TestResult(
        name=name,
        question=question,
        statistic=observed,
        p_value=float(p_value),
        null_mean=float(null.mean()),
        null_sd=float(null.std(ddof=1)),
        simulations=simulations,
    )


def marginal_chi_square(counts: np.ndarray) -> float:
    totals = counts.sum(axis=0).astype(float)
    expected = totals.sum() / NUMBER_SPACE
    return float(((totals - expected) ** 2 / expected).sum())


def dispersion_index(counts: np.ndarray) -> float:
    distinct = (counts > 0).sum(axis=1).astype(float)
    return float(distinct.var(ddof=1) / max(distinct.mean(), 1e-9))


def lag1_mutual_information(counts: np.ndarray) -> float:
    hits = counts > 0
    previous, following = hits[:-1], hits[1:]
    n = previous.shape[0]
    if n < 2:
        return 0.0

    both = previous.T.astype(np.float64) @ following.astype(np.float64)
    px = previous.sum(axis=0).astype(np.float64)[:, None]
    py = following.sum(axis=0).astype(np.float64)[None, :]
    total = float(n)

    joint = (
        np.stack(
            [
                both,
                px - both,
                py - both,
                total - px - py + both,
            ]
        )
        / total
    )
    marginal = np.stack(
        [
            (px / total) * (py / total),
            (px / total) * (1 - py / total),
            (1 - px / total) * (py / total),
            (1 - px / total) * (1 - py / total),
        ]
    )
    mask = joint > 0
    contrib = np.zeros_like(joint)
    contrib[mask] = joint[mask] * np.log2(joint[mask] / np.maximum(marginal[mask], 1e-300))
    return float(contrib.sum() / (NUMBER_SPACE * NUMBER_SPACE))


def gap_distribution_distance(counts: np.ndarray) -> float:
    hits = counts > 0
    gaps: list[int] = []
    for number in range(NUMBER_SPACE):
        days = np.flatnonzero(hits[:, number])
        if days.size >= 2:
            gaps.extend(np.diff(days).tolist())
    if len(gaps) < 30:
        return 0.0
    observed = np.sort(np.asarray(gaps, dtype=np.int64))
    rate = 1.0 - (1.0 - UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_DAY
    support = np.arange(1, int(observed[-1]) + 1)
    empirical = np.searchsorted(observed, support, side="right") / observed.size
    theoretical = stats.geom(rate).cdf(support)
    return float(np.max(np.abs(empirical - theoretical)))


def spectral_peak(counts: np.ndarray) -> float:
    series = (counts > 0).sum(axis=1).astype(float)
    series = series - series.mean()
    power = np.abs(np.fft.rfft(series)) ** 2
    power = power[1:]
    total = power.sum()
    return float(power.max() / total) if total > 0 else 0.0


def weekday_effect(counts: np.ndarray, weekdays: np.ndarray | None = None) -> float:
    hits = (counts > 0).sum(axis=1).astype(float)
    labels = np.arange(hits.size) % 7 if weekdays is None else np.asarray(weekdays)
    if labels.size != hits.size:
        raise ValueError("weekdays phải có đúng một nhãn cho mỗi kỳ")
    means = np.array([hits[labels == day].mean() if (labels == day).any() else 0.0 for day in range(7)])
    present = np.array([(labels == day).any() for day in range(7)])
    return float(means[present].max() - means[present].min())


def hot_number_persistence(counts: np.ndarray) -> float:
    half = counts.shape[0] // 2
    first = counts[:half].sum(axis=0).astype(float)
    second = counts[half:].sum(axis=0).astype(float)
    if first.std() < 1e-9 or second.std() < 1e-9:
        return 0.0
    return float(np.corrcoef(first, second)[0, 1])


TESTS: Final[tuple[tuple[str, str, Callable[[np.ndarray], float], bool], ...]] = (
    (
        "Đồng đều biên (chi-square)",
        "Có con nào ra nhiều/ít hơn mức ngẫu nhiên không?",
        marginal_chi_square,
        False,
    ),
    (
        "Chỉ số phân tán",
        "Các kỳ có 'vón cục' hơn mức đa thức không?",
        dispersion_index,
        True,
    ),
    (
        "Thông tin tương hỗ trễ-1",
        "Kết quả hôm qua có nói gì về hôm nay không? (bạc nhớ)",
        lag1_mutual_information,
        False,
    ),
    (
        "Phân bố khoảng cách (KS)",
        "Nhịp gan có lệch khỏi phân bố hình học không?",
        gap_distribution_distance,
        False,
    ),
    (
        "Đỉnh phổ (Fisher g)",
        "Có chu kỳ tuần/tháng nào không?",
        spectral_peak,
        False,
    ),
    (
        "Hiệu ứng thứ trong tuần",
        "Tần suất có khác nhau theo thứ không?",
        weekday_effect,
        False,
    ),
    (
        "Độ bền của 'số nóng'",
        "Con hay về nửa đầu có tiếp tục hay về nửa sau không?",
        hot_number_persistence,
        True,
    ),
)


def run_battery(
    counts: np.ndarray,
    *,
    simulations: int = DEFAULT_SIMULATIONS,
    seed: int = DEFAULT_SEED,
    weekdays: np.ndarray | None = None,
) -> list[TestResult]:
    return [
        monte_carlo_test(
            name,
            question,
            partial(weekday_effect, weekdays=weekdays) if statistic is weekday_effect else statistic,
            counts,
            simulations=simulations,
            seed=seed,
            two_sided=two_sided,
        )
        for name, question, statistic, two_sided in TESTS
    ]


@dataclass(frozen=True)
class PowerAnalysis:

    n_days: int
    baseline: float
    alpha: float
    power: float
    hypotheses: int
    detectable_lift: float

    @property
    def relative_lift(self) -> float:
        return self.detectable_lift / self.baseline

    def describe(self) -> str:
        return (
            f"{self.hypotheses:>9,} giả thuyết → cần chênh tuyệt đối "
            f"{self.detectable_lift:+.4f} (tương đối {self.relative_lift:+.1%}) "
            f"mới phát hiện được ở công suất {self.power:.0%}"
        )


def minimum_detectable_lift(
    n_days: int,
    *,
    baseline: float,
    alpha: float = 0.05,
    power: float = 0.80,
    hypotheses: int = 1,
) -> PowerAnalysis:
    if not 0 < baseline < 1:
        raise ValueError("baseline phải nằm trong (0, 1)")
    if hypotheses < 1:
        raise ValueError("hypotheses phải ít nhất bằng 1")

    adjusted_alpha = alpha / hypotheses
    z_alpha = stats.norm.isf(adjusted_alpha / 2)
    z_power = stats.norm.isf(1 - power)
    standard_error = math.sqrt(baseline * (1 - baseline) / n_days)
    return PowerAnalysis(
        n_days=n_days,
        baseline=baseline,
        alpha=alpha,
        power=power,
        hypotheses=hypotheses,
        detectable_lift=(z_alpha + z_power) * standard_error,
    )
