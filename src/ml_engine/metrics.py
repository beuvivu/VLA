"""Chỉ số đánh giá, và lý do không dùng độ chính xác thuần túy.

Độ chính xác là chỉ số tệ nhất có thể ở miền này
--------------------------------------------------

Tỉ lệ về nền là 23.77%, nên một mô hình luôn nói "không về" đạt **76.23% độ
chính xác** mà không mang một bit thông tin nào. Bất kỳ báo cáo nào nêu độ chính
xác mà không nêu nền đều vô nghĩa, và con số đó luôn nghe ấn tượng.

Bộ chỉ số ở đây chia làm ba nhóm, mỗi nhóm bắt một dạng hỏng mà nhóm khác bỏ
sót:

* **Quy tắc chấm điểm chặt** (log-loss, Brier) — đạt cực trị khi và chỉ khi mô
  hình khai báo đúng xác suất thật. Đây là nhóm dùng để *quyết định*.
* **Chỉ số xếp hạng** (Hit-Rate@K, precision, recall) — thứ người dùng thực sự
  quan tâm, nhưng không phải quy tắc chặt: một mô hình có thể nhích thứ hạng
  lên chút ít trong khi làm hỏng hoàn toàn mức xác suất. Dùng để *báo cáo*.
* **Kinh tế** (kỳ vọng lời/lỗ) — dịch hiệu năng sang đơn vị mà người chơi thật
  sự chịu.

Ngưỡng hòa vốn là con số quan trọng nhất trong tệp này
-------------------------------------------------------

Với luật chi trả LOTO thông thường (đặt 23, nhận 80 mỗi nháy), số nháy kỳ vọng
cần để hòa vốn là ``23/80 = 0.2875`` trên mỗi con mỗi kỳ. Nền là
``27/100 = 0.27`` nháy, nên cần cải thiện **tương đối +6.48%** để hòa vốn.
Xác suất về ít nhất một lần (23.77%) chỉ dùng chấm xác suất và Hit-Rate;
không thể dùng thay số nháy để tính doanh thu hay suy công suất kiểm định ROI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from ml_engine.schema import BASELINE_RATE, NUMBER_SPACE
from core.xsmb_domain import LOTO_DRAWS_PER_DAY

_EPSILON: Final[float] = 1e-6

#: Các mức K mặc định cho Hit-Rate@K.
DEFAULT_K_VALUES: Final[tuple[int, ...]] = (3, 5, 10, 27)

#: Luật chi trả LOTO thông thường, đơn vị nghìn đồng cho một điểm.
DEFAULT_STAKE: Final[float] = 23.0
DEFAULT_PAYOUT: Final[float] = 80.0
BASELINE_OCCURRENCES: Final[float] = LOTO_DRAWS_PER_DAY / NUMBER_SPACE


@dataclass(frozen=True)
class EconomicModel:
    """Luật chi trả dùng để quy hiệu năng ra tiền.

    Attributes:
        stake: Chi phí đặt một điểm.
        payout: Số tiền nhận về cho mỗi nháy của một điểm.
    """

    stake: float = DEFAULT_STAKE
    payout: float = DEFAULT_PAYOUT

    def __post_init__(self) -> None:
        if self.stake <= 0 or self.payout <= 0:
            raise ValueError("stake và payout phải dương")
        if self.payout <= self.stake:
            raise ValueError("payout phải lớn hơn stake, nếu không mọi cược đều lỗ")

    @property
    def break_even_rate(self) -> float:
        """Số nháy kỳ vọng trên mỗi con mỗi kỳ cần có để hòa vốn."""
        return self.stake / self.payout

    @property
    def baseline_edge(self) -> float:
        """Lợi thế (âm) với số nháy nền, tính theo tỉ lệ đặt cược."""
        return (BASELINE_OCCURRENCES * self.payout - self.stake) / self.stake

    def required_relative_lift(self) -> float:
        """Mức cải thiện số nháy tương đối so với nền để hòa vốn."""
        return self.break_even_rate / BASELINE_OCCURRENCES - 1.0


@dataclass(frozen=True)
class DailyScore:
    """Điểm của một kỳ.

    Attributes:
        logloss: Log-loss trung bình trên 100 con.
        brier: Điểm Brier trung bình trên 100 con.
        baseline_logloss: Log-loss của nền trên cùng kết quả.
        baseline_brier: Điểm Brier của nền.
        hit_rate_at: Số con trúng trong Top-K, theo từng K.
        actual_hits: Tổng số con thực về trong kỳ.
        occurrences_at: Tổng số nháy trong Top-K, chỉ dùng tính tiền thưởng.
    """

    logloss: float
    brier: float
    baseline_logloss: float
    baseline_brier: float
    hit_rate_at: dict[int, int]
    actual_hits: int
    occurrences_at: dict[int, int]


def validate_probabilities(probabilities: np.ndarray) -> np.ndarray:
    """Kiểm vector xác suất trước khi trộn, chấm hay cập nhật trạng thái."""
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
    """Chấm một kỳ.

    Args:
        probabilities: Mảng ``(100,)`` xác suất khai báo.
        outcome: Mảng ``(100,)`` giá trị 0/1, con đó có về hay không.
        k_values: Các mức K cần tính Hit-Rate.
        counts: Số nháy thực cho 100 con, phải khớp ``outcome``. Khi không
            truyền, chỉ biết mỗi con về ít nhất một nháy nên dùng ``outcome``.

    Returns:
        Điểm của kỳ đó.

    Raises:
        ValueError: Khi hình dạng sai hoặc xác suất ngoài ``[0, 1]``.
    """
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

    order = np.argsort(-p)
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
    """Tổng hợp hiệu năng trên nhiều kỳ.

    Attributes:
        days: Số kỳ đã chấm.
        logloss: Log-loss trung bình.
        brier: Brier trung bình.
        logloss_skill: Kỹ năng log-loss so với nền.
        brier_skill: Kỹ năng Brier so với nền.
        paired_t: Thống kê t ghép cặp ở mức ngày.
        hit_rate_at: Hit-Rate trung bình theo K.
        random_hit_rate_at: Hit-Rate kỳ vọng khi chọn ngẫu nhiên, theo K.
        precision_at: Độ chính xác Top-K.
        recall_at: Độ bao phủ Top-K.
        profit_ratio: Tỉ suất lời/lỗ khi đặt Top-K, theo K.
    """

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
        """Vượt nền *và* chênh lệch lớn hơn nhiễu ngày qua ngày."""
        return self.logloss_skill > 0.0 and self.paired_t > 1.96

    def describe(self) -> str:
        """Dòng tóm tắt để ghi nhật ký."""
        verdict = "VƯỢT nền" if self.beats_baseline else "không vượt nền"
        hit5 = self.hit_rate_at.get(5, float("nan"))
        return (
            f"{self.days} kỳ · kỹ năng={self.logloss_skill:+.5f} · t={self.paired_t:+.2f} · "
            f"trúng@5={hit5:.3f} · {verdict}"
        )


class PerformanceTracker:
    """Tích lũy điểm theo ngày và tổng hợp thành báo cáo.

    Ví dụ:
        >>> tracker = PerformanceTracker()
        >>> import numpy as np
        >>> outcome = np.zeros(100); outcome[:24] = 1
        >>> tracker.add(np.full(100, 0.2377), outcome)
        >>> tracker.report().days
        1

    Attributes:
        k_values: Các mức K được theo dõi.
        economics: Luật chi trả dùng để tính lời/lỗ.
    """

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
        """Chấm và ghi nhận một kỳ.

        Args:
            probabilities: Xác suất khai báo cho 100 con.
            outcome: Kết quả thật, 0/1 cho 100 con.
            counts: Số nháy thực; khi thiếu chỉ ghi một nháy cho mỗi con về.

        Returns:
            Điểm của kỳ vừa thêm.
        """
        score = score_day(probabilities, outcome, k_values=self.k_values, counts=counts)
        self._scores.append(score)
        return score

    def report(self) -> PerformanceReport:
        """Tổng hợp toàn bộ kỳ đã ghi nhận.

        Returns:
            Báo cáo hiệu năng.

        Raises:
            ValueError: Khi chưa có kỳ nào được chấm.
        """
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
            # Kỳ vọng khi chọn ngẫu nhiên K con: K/100 × số con thực về. Đây mới
            # là mốc so đúng, không phải 0.
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
