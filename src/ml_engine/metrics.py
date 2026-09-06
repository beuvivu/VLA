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

Với luật chi trả lô tô thông thường (đặt 23, trúng được 80), tỉ lệ trúng cần để
hòa vốn là ``23/80 = 28.75%``, trong khi nền là 23.77%. Nghĩa là hệ thống phải
đạt mức cải thiện **tương đối +21%** chỉ để *không lỗ*.

Con số đó gần như trùng với mức chênh lệch nhỏ nhất mà 391 kỳ đủ sức phát hiện
(+25.4%). Hai đại lượng này đến từ hai phép tính hoàn toàn độc lập, và việc
chúng gặp nhau nói lên điều cốt lõi: **ngưỡng để có lãi nằm đúng ở ranh giới
khả năng phát hiện của dữ liệu**. Một hệ thống báo rằng nó vượt ngưỡng đó, trên
lịch sử cỡ này, gần như chắc chắn đang đo may rủi.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

from ml_engine.schema import BASELINE_RATE, NUMBER_SPACE

_EPSILON: Final[float] = 1e-6

#: Các mức K mặc định cho Hit-Rate@K.
DEFAULT_K_VALUES: Final[tuple[int, ...]] = (3, 5, 10, 27)

#: Luật chi trả lô tô thông thường, đơn vị nghìn đồng cho một điểm.
DEFAULT_STAKE: Final[float] = 23.0
DEFAULT_PAYOUT: Final[float] = 80.0


@dataclass(frozen=True)
class EconomicModel:
    """Luật chi trả dùng để quy hiệu năng ra tiền.

    Attributes:
        stake: Chi phí đặt một điểm.
        payout: Số tiền nhận về khi một điểm trúng.
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
        """Tỉ lệ trúng cần có để hòa vốn."""
        return self.stake / self.payout

    @property
    def baseline_edge(self) -> float:
        """Lợi thế (âm) của người chơi ở đúng tỉ lệ nền, tính theo tỉ lệ đặt cược."""
        return (BASELINE_RATE * self.payout - self.stake) / self.stake

    def required_relative_lift(self) -> float:
        """Mức cải thiện tương đối so với nền để hòa vốn."""
        return self.break_even_rate / BASELINE_RATE - 1.0


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
    """

    logloss: float
    brier: float
    baseline_logloss: float
    baseline_brier: float
    hit_rate_at: dict[int, int]
    actual_hits: int


def score_day(
    probabilities: np.ndarray,
    outcome: np.ndarray,
    *,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
) -> DailyScore:
    """Chấm một kỳ.

    Args:
        probabilities: Mảng ``(100,)`` xác suất khai báo.
        outcome: Mảng ``(100,)`` giá trị 0/1, con đó có về hay không.
        k_values: Các mức K cần tính Hit-Rate.

    Returns:
        Điểm của kỳ đó.

    Raises:
        ValueError: Khi hình dạng sai hoặc xác suất ngoài ``[0, 1]``.
    """
    if probabilities.shape != (NUMBER_SPACE,) or outcome.shape != (NUMBER_SPACE,):
        raise ValueError(f"cần hai mảng dạng ({NUMBER_SPACE},)")
    if np.any(probabilities < 0.0) or np.any(probabilities > 1.0):
        raise ValueError("probabilities phải nằm trong [0, 1]")

    p = np.clip(probabilities, _EPSILON, 1.0 - _EPSILON)
    y = outcome.astype(float)
    b = BASELINE_RATE

    order = np.argsort(-p)
    return DailyScore(
        logloss=float(-np.mean(y * np.log(p) + (1 - y) * np.log1p(-p))),
        brier=float(np.mean((p - y) ** 2)),
        baseline_logloss=float(-np.mean(y * np.log(b) + (1 - y) * np.log1p(-b))),
        baseline_brier=float(np.mean((b - y) ** 2)),
        hit_rate_at={k: int(y[order[:k]].sum()) for k in k_values},
        actual_hits=int(y.sum()),
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

    def add(self, probabilities: np.ndarray, outcome: np.ndarray) -> DailyScore:
        """Chấm và ghi nhận một kỳ.

        Args:
            probabilities: Xác suất khai báo cho 100 con.
            outcome: Kết quả thật, 0/1 cho 100 con.

        Returns:
            Điểm của kỳ vừa thêm.
        """
        score = score_day(probabilities, outcome, k_values=self.k_values)
        self._scores.append(score)
        return score

    def recent_hit_rate(self, k: int, window: int = 7) -> float:
        """Tỉ lệ trúng trung bình trên mỗi con trong Top-K, tính trên cửa sổ gần nhất.

        Args:
            k: Mức K.
            window: Số kỳ gần nhất đưa vào tính.

        Returns:
            Tỉ lệ trong ``[0, 1]``; trả 0 khi chưa có dữ liệu.
        """
        recent = self._scores[-window:]
        if not recent:
            return 0.0
        return float(np.mean([score.hit_rate_at.get(k, 0) / k for score in recent]))

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
            revenue = hits * self.economics.payout
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
