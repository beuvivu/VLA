"""Chuyển chế độ an toàn khi hệ thống không còn đáng tin.

Ngưỡng ``T_min`` phải neo vào miền, không phải chọn tay
--------------------------------------------------------

Một ngưỡng tùy chọn kiểu "dưới 30% thì chuyển chế độ an toàn" có vấn đề: không
ai biện minh được con số đó, nên khi hệ thống chạm ngưỡng, phản xạ tự nhiên là
hạ ngưỡng xuống. Ngưỡng nào cũng có thể chỉnh cho tới khi hệ thống "đạt".

Ở đây ``T_min`` mặc định bằng đúng **tỉ lệ nền của miền** (0.2377). Lập luận
thẳng: chọn Top-K trong 100 con một cách ngẫu nhiên đã cho tỉ lệ trúng bằng
nền. Nếu Top-K của mô hình rơi *xuống dưới* mức đó thì mô hình không chỉ vô ích
mà đang chủ động làm hại — nó xếp hạng tệ hơn cả bốc ngẫu nhiên. Đó là ngưỡng
duy nhất không cần biện minh thêm.

Ba lối vào chế độ an toàn
--------------------------

1. **Hiệu năng sụt** — Hit-Rate trung bình 7 kỳ gần nhất dưới ``T_min``.
2. **Trôi lệch khái niệm** — bộ phát hiện báo phân phối sai số đã đổi.
3. **Lỗi khi khớp** — mô hình ném ngoại lệ; hệ thống không được im lặng đoán
   bừa mà phải lui về nền và nói rõ.

Chế độ an toàn dự đoán gì
--------------------------

Trộn giữa nền của miền và tần suất lịch sử dài hạn, nghiêng hẳn về nền. Đây
không phải "không làm gì": nó là dự đoán *đúng* khi không có bằng chứng nào cho
thấy các con khác nhau — và trên dữ liệu của kho này, đó chính là trường hợp đã
đo được.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

import numpy as np

from ml_engine.schema import BASELINE_RATE, NUMBER_SPACE

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

#: Số kỳ gần nhất dùng để đánh giá hiệu năng.
DEFAULT_WINDOW: Final[int] = 7

#: Số kỳ liên tiếp phải đạt lại ngưỡng trước khi rời chế độ an toàn.
DEFAULT_RECOVERY: Final[int] = 5


class Mode(str, Enum):
    """Chế độ vận hành của hệ thống."""

    NORMAL = "normal"
    SAFE = "safe"


@dataclass
class SafeModeController:
    """Quyết định khi nào tin mô hình và khi nào lui về nền.

    Attributes:
        threshold: ``T_min``; mặc định bằng tỉ lệ nền của miền.
        window: Số kỳ gần nhất dùng để tính hiệu năng.
        recovery_days: Số kỳ liên tiếp phải đạt lại ngưỡng để thoát chế độ an toàn.
        baseline_weight: Trọng số của nền trong dự đoán chế độ an toàn.
    """

    threshold: float = BASELINE_RATE
    window: int = DEFAULT_WINDOW
    recovery_days: int = DEFAULT_RECOVERY
    baseline_weight: float = 0.8
    mode: Mode = Mode.NORMAL
    reason: str = "khởi động ở chế độ bình thường"
    _recent: list[float] = field(default_factory=list)
    _healthy_streak: int = 0
    transitions: list[dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0.0 < self.threshold < 1.0:
            raise ValueError("threshold phải nằm trong (0, 1)")
        if self.window < 1:
            raise ValueError("window phải dương")
        if self.recovery_days < 1:
            raise ValueError("recovery_days phải dương")
        if not 0.0 <= self.baseline_weight <= 1.0:
            raise ValueError("baseline_weight phải nằm trong [0, 1]")

    @property
    def is_safe(self) -> bool:
        """Hệ thống có đang ở chế độ an toàn không."""
        return self.mode is Mode.SAFE

    def _enter_safe(self, reason: str, day_index: int | None) -> None:
        if self.mode is not Mode.SAFE:
            LOGGER.warning("Chuyển sang CHẾ ĐỘ AN TOÀN: %s", reason)
            self.transitions.append({"to": Mode.SAFE.value, "reason": reason, "day": day_index})
        self.mode = Mode.SAFE
        self.reason = reason
        self._healthy_streak = 0

    def _leave_safe(self, reason: str, day_index: int | None) -> None:
        if self.mode is not Mode.NORMAL:
            LOGGER.info("Rời chế độ an toàn: %s", reason)
            self.transitions.append({"to": Mode.NORMAL.value, "reason": reason, "day": day_index})
        self.mode = Mode.NORMAL
        self.reason = reason

    def observe(
        self,
        hit_rate: float,
        *,
        drifted: bool = False,
        model_failed: bool = False,
        day_index: int | None = None,
    ) -> Mode:
        """Nạp kết quả một kỳ và cập nhật chế độ.

        Args:
            hit_rate: Tỉ lệ trúng trên mỗi con trong Top-K của kỳ vừa rồi.
            drifted: Bộ phát hiện trôi lệch có báo động ở kỳ này không.
            model_failed: Mô hình có ném ngoại lệ khi khớp hoặc dự đoán không.
            day_index: Chỉ số ngày, chỉ dùng để ghi nhật ký chuyển chế độ.

        Returns:
            Chế độ sau khi cập nhật.

        Raises:
            ValueError: Khi ``hit_rate`` ngoài ``[0, 1]``.
        """
        if not 0.0 <= hit_rate <= 1.0:
            raise ValueError(f"hit_rate phải nằm trong [0, 1], nhận {hit_rate}")

        self._recent.append(float(hit_rate))
        self._recent = self._recent[-self.window :]

        if model_failed:
            self._enter_safe("mô hình lỗi khi khớp hoặc dự đoán", day_index)
            return self.mode
        if drifted:
            self._enter_safe("bộ phát hiện báo trôi lệch khái niệm", day_index)
            return self.mode

        average = float(np.mean(self._recent))
        # Chỉ xét khi đã đủ cửa sổ: đánh giá trên hai ba kỳ đầu là đo nhiễu.
        if len(self._recent) < self.window:
            return self.mode

        if average < self.threshold:
            self._enter_safe(
                f"Hit-Rate {self.window} kỳ = {average:.4f} < ngưỡng {self.threshold:.4f}",
                day_index,
            )
            return self.mode

        if self.mode is Mode.SAFE:
            # Rời chế độ an toàn cần nhiều kỳ liên tiếp đạt lại, không phải một
            # kỳ may mắn — nếu không hệ thống sẽ dao động vào ra liên tục.
            self._healthy_streak += 1
            if self._healthy_streak >= self.recovery_days:
                self._leave_safe(
                    f"{self._healthy_streak} kỳ liên tiếp đạt ngưỡng (trung bình {average:.4f})",
                    day_index,
                )
        else:
            self.reason = f"Hit-Rate {self.window} kỳ = {average:.4f} ≥ ngưỡng"
        return self.mode

    def safe_probabilities(self, counts: np.ndarray) -> np.ndarray:
        """Dự đoán của chế độ an toàn: nghiêng hẳn về nền của miền.

        Args:
            counts: Ma trận đếm lịch sử đã biết.

        Returns:
            Mảng ``(100,)`` xác suất.
        """
        if counts.shape[0] == 0:
            return np.full(NUMBER_SPACE, BASELINE_RATE)
        empirical = (counts > 0).mean(axis=0)
        weight = self.baseline_weight
        return weight * BASELINE_RATE + (1.0 - weight) * empirical

    def apply(self, counts: np.ndarray, model_probabilities: np.ndarray) -> np.ndarray:
        """Trả xác suất cuối cùng theo chế độ đang hiệu lực.

        Args:
            counts: Ma trận đếm lịch sử đã biết.
            model_probabilities: Xác suất do mô hình khai báo.

        Returns:
            Xác suất của mô hình khi bình thường, của chế độ an toàn khi đã chuyển.
        """
        if self.is_safe:
            return self.safe_probabilities(counts)
        return model_probabilities

    def state(self) -> dict[str, object]:
        """Trạng thái hiện tại, để ghi vào báo cáo chạy."""
        return {
            "mode": self.mode.value,
            "reason": self.reason,
            "threshold": self.threshold,
            "recent_hit_rate": float(np.mean(self._recent)) if self._recent else None,
            "observations": len(self._recent),
            "transitions": list(self.transitions),
        }
