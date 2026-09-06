"""Bộ kiểm định cấu trúc cho chuỗi kết quả xổ số.

Vì sao cần bộ này trước mọi mô hình
------------------------------------

Một mô hình dự đoán chỉ có ý nghĩa nếu dữ liệu mang cấu trúc để học. Đi thẳng
vào LSTM hay XGBoost mà bỏ qua bước này là cách phổ biến nhất để tự thuyết phục
mình rằng nhiễu là tín hiệu: mô hình đủ lớn luôn khớp được tập huấn luyện, và
nếu không có đối chứng thì kết quả trông y hệt một phát hiện thật.

Bộ kiểm định ở đây hỏi câu hỏi ngược lại và rẻ hơn nhiều: *chuỗi này có khác
một chuỗi ngẫu nhiên công bằng ở điểm nào không?* Mỗi phép kiểm nhắm vào một
dạng cấu trúc cụ thể mà các phương pháp soi cầu ngầm giả định là có.

Giá trị p lấy bằng Monte Carlo
-------------------------------

Mọi giá trị p đều hiệu chuẩn bằng mô phỏng chứ không dùng phân phối tiệm cận.
Lý do: với 391 kỳ, xấp xỉ tiệm cận của một số thống kê (đặc biệt là kiểm định
chuỗi và kiểm định phổ) lệch đáng kể, và đúng chiều làm ta tin nhầm có tín
hiệu. Mô phỏng thì đúng theo định nghĩa, chỉ tốn thời gian.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy import stats

from xsmb_domain import LOTO_DRAWS_PER_DAY, UNIFORM_TWO_DIGIT_RATE

NUMBER_SPACE: Final[int] = 100
DEFAULT_SIMULATIONS: Final[int] = 2000
DEFAULT_SEED: Final[int] = 20260906


@dataclass(frozen=True)
class TestResult:
    """Kết quả một phép kiểm, kèm cách đọc."""

    name: str
    question: str
    statistic: float
    p_value: float
    null_mean: float
    null_sd: float
    simulations: int

    @property
    def z_score(self) -> float:
        """Vị trí của giá trị quan sát trong phân phối rỗng, tính bằng độ lệch chuẩn."""
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
    """Sinh ``n_days`` kỳ quay công bằng, trả về ma trận đếm ``(n_days, 100)``.

    Mô hình sinh: mỗi kỳ rút 27 con độc lập, đều trên 00–99, CÓ hoàn lại — đúng
    cơ chế của xổ số miền Bắc, nơi hai giải khác nhau có thể cho cùng một con.
    """
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
    """Chạy một phép kiểm với phân phối rỗng lấy bằng mô phỏng."""
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
    # +1 ở cả tử và mẫu: ước lượng không chệch, và không bao giờ trả p=0 — một
    # giá trị p bằng 0 là lời khẳng định mạnh hơn số lần mô phỏng cho phép.
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


# --------------------------------------------------------------------------
# Các thống kê kiểm định
# --------------------------------------------------------------------------


def marginal_chi_square(counts: np.ndarray) -> float:
    """Tần suất tổng của 100 con có lệch khỏi phân bố đều không.

    Đây là phép kiểm cơ bản nhất mà mọi phương pháp "số nóng / số lạnh" ngầm
    giả định là sẽ bác bỏ.
    """
    totals = counts.sum(axis=0).astype(float)
    expected = totals.sum() / NUMBER_SPACE
    return float(((totals - expected) ** 2 / expected).sum())


def dispersion_index(counts: np.ndarray) -> float:
    """Phương sai số con phân biệt mỗi kỳ, so với mức đa thức.

    Lớn hơn kỳ vọng nghĩa là các kỳ "vón cục" — một số kỳ ra nhiều số trùng bất
    thường. Đó là dạng cấu trúc mà cầu "hai nháy" ngầm giả định.
    """
    distinct = (counts > 0).sum(axis=1).astype(float)
    return float(distinct.var(ddof=1) / max(distinct.mean(), 1e-9))


def lag1_mutual_information(counts: np.ndarray) -> float:
    """Thông tin tương hỗ giữa tập số ngày T−1 và ngày T.

    Cơ sở của toàn bộ phương pháp "bạc nhớ": nếu con X hôm qua thật sự nói điều
    gì về con Y hôm nay thì thông tin tương hỗ phải dương một cách có ý nghĩa.
    Đo bằng bit, dùng ước lượng plug-in trên bảng 2×2 gộp cho mọi cặp (X, Y).
    """
    hits = counts > 0
    previous, following = hits[:-1], hits[1:]
    n = previous.shape[0]
    if n < 2:
        return 0.0

    # Bảng liên hợp gộp: với mỗi cặp con (x, y), đếm bốn tổ hợp có/không.
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
    # Trung bình trên mọi cặp con: một con số duy nhất, so sánh được qua mô phỏng.
    return float(contrib.sum() / (NUMBER_SPACE * NUMBER_SPACE))


def gap_distribution_distance(counts: np.ndarray) -> float:
    """Khoảng cách giữa phân bố khoảng cách quan sát và phân bố hình học.

    Với chuỗi độc lập, khoảng cách giữa hai lần một con về tuân theo phân bố
    hình học. Mọi phương pháp "nhịp gan", "điểm rơi" đều giả định phân bố thật
    lệch khỏi hình học. Đo bằng khoảng cách Kolmogorov–Smirnov dạng rời rạc.

    Phải tự tính chứ không gọi ``scipy.stats.kstest``: hàm đó giả định biến
    liên tục nên so hàm phân phối lý thuyết với hàm phân phối kinh nghiệm
    *ngay trước* mỗi điểm dữ liệu. Khoảng cách nhỏ nhất luôn bằng 1, nên số
    hạng ``F(1) - 0 = p`` luôn có mặt và át mọi sai lệch thật khi phần khớp
    còn lại tốt — thống kê đứng yên ở đúng ``p`` với mọi chuỗi, tức là không
    còn là phép kiểm. So tại chính các điểm giá đỡ thì hết hiện tượng đó.
    """
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
    """Đỉnh phổ lớn nhất của chuỗi số con phân biệt theo ngày.

    Bắt tính chu kỳ: nếu tồn tại nhịp tuần, nhịp tháng hay bất kỳ chu kỳ nào,
    nó hiện ra thành một đỉnh trội trong phổ. Chuẩn hóa theo tổng công suất nên
    so sánh được giữa các chuỗi — đây chính là thống kê g của Fisher.
    """
    series = (counts > 0).sum(axis=1).astype(float)
    series = series - series.mean()
    power = np.abs(np.fft.rfft(series)) ** 2
    power = power[1:]  # bỏ thành phần một chiều
    total = power.sum()
    return float(power.max() / total) if total > 0 else 0.0


def weekday_effect(counts: np.ndarray) -> float:
    """Chênh lệch lớn nhất về tần suất giữa các thứ trong tuần.

    Ở đây dùng chỉ số ngày chia 7 làm đại diện cho thứ, đủ để bắt bất kỳ nhịp
    bảy ngày nào mà không cần lịch thật — và nhờ vậy phép mô phỏng cũng dùng
    đúng định nghĩa đó.
    """
    hits = (counts > 0).sum(axis=1).astype(float)
    groups = [hits[i::7] for i in range(7)]
    means = np.array([g.mean() if g.size else 0.0 for g in groups])
    return float(means.max() - means.min())


def hot_number_persistence(counts: np.ndarray) -> float:
    """Tương quan giữa tần suất nửa đầu và nửa sau của lịch sử.

    Nếu tồn tại "số nóng" bền vững, con hay về ở nửa đầu phải tiếp tục hay về ở
    nửa sau — tức hệ số tương quan dương rõ rệt.
    """
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
) -> list[TestResult]:
    """Chạy toàn bộ bộ kiểm định trên ma trận đếm quan sát."""
    return [
        monte_carlo_test(
            name,
            question,
            statistic,
            counts,
            simulations=simulations,
            seed=seed,
            two_sided=two_sided,
        )
        for name, question, statistic, two_sided in TESTS
    ]


# --------------------------------------------------------------------------
# Phân tích công suất
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PowerAnalysis:
    """Hiệu ứng nhỏ nhất mà lịch sử hiện có đủ sức phát hiện."""

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
    """Chênh lệch nhỏ nhất phát hiện được với ``n_days`` ngày quan sát.

    Đây là con số quyết định việc có nên xây mô hình phức tạp hay không. Nếu
    hiệu ứng nhỏ nhất phát hiện được lớn hơn hẳn bất kỳ hiệu ứng nào hợp lý
    trong miền, thì dữ liệu KHÔNG đủ để phân biệt mô hình tốt với mô hình may
    mắn — và mọi kết quả dương tính sẽ là dương tính giả.

    Hiệu chỉnh đa kiểm định theo Bonferroni: thử ``hypotheses`` giả thuyết thì
    ngưỡng mỗi phép kiểm là ``alpha / hypotheses``.
    """
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
