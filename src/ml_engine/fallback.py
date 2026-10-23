"""Cổng độ tin: chỉ tin phép trộn khi kỹ năng ngoài mẫu đo được của nó dương.

Luật của kho, không phải ngưỡng chọn tay
-----------------------------------------

Dự báo công bố là ``p = trust·trộn + (1 − trust)·nền`` với
``trust = ml_train.model_trust(s_logloss, s_brier) = clip(20·min(s), 0, 1)``, s là
kỹ năng tương đối của phép trộn so với nền trên ``window`` kỳ gần nhất đã chấm.
Đó là cùng luật của thành phần ML production, cầu-kèo và tác tử mẫu hình: không
có kỹ năng thì không tin. Chưa đủ ``min_days`` kỳ đo thì trust = 0.

Kỹ năng đo trên phép trộn TRƯỚC cổng. Đo trên dự báo đã qua cổng thì khi trust
về 0 dự báo trùng nền, kỹ năng bằng 0 mãi mãi và cổng không bao giờ mở lại.

Vì sao bỏ ngưỡng Hit-Rate 7 kỳ (20-10-2026)
-------------------------------------------

Bản trước vào chế độ an toàn khi Hit-Rate@10 trung bình 7 kỳ dưới nền 0,2377.
Với 70 lượt chọn, độ lệch chuẩn của tỉ lệ ấy là 0,051 — một mô hình đúng bằng
nền rơi dưới ngưỡng khoảng một nửa số kỳ. Trên 192 kỳ thật nó bật 62% thời gian
và vào ra 19 lần: phán đoán bằng tung đồng xu. Hit-Rate lại không phải quy tắc
chấm chặt, nên nó còn bỏ qua đúng thứ cần canh — mức xác suất.

Ba lối về nền
--------------

1. **Không có kỹ năng** — s ≤ 0 trên cửa sổ, hoặc chưa đủ kỳ đo.
2. **Trôi lệch khái niệm** — bằng chứng cũ mô tả một chế độ đã qua, nên bị xoá;
   cổng đo lại từ đầu.
3. **Lỗi khi khớp hoặc dự đoán** — bộ dự báo đang chạy không còn là bộ đã được
   đo, nên bằng chứng cũng bị xoá.
"""

from __future__ import annotations

import logging
from collections import deque
from enum import Enum
from typing import Final

import numpy as np

from ml_engine.schema import BASELINE_RATE
from ml.ml_train import model_trust

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

#: Số kỳ gần nhất dùng để đo kỹ năng của phép trộn.
DEFAULT_WINDOW: Final[int] = 60

#: Số kỳ tối thiểu đã chấm trước khi cổng được phép mở.
DEFAULT_MIN_DAYS: Final[int] = 30


class Mode(str, Enum):
    """Chế độ vận hành: ``SAFE`` khi trust = 0, tức dự báo đúng bằng nền."""

    NORMAL = "normal"
    SAFE = "safe"


class SafeModeController:
    """Quyết định mức tin phép trộn từ kỹ năng ngoài mẫu của chính nó.

    Attributes:
        window: Số kỳ gần nhất dùng để đo kỹ năng.
        min_days: Số kỳ tối thiểu trước khi trust được dương.
        trust: Mức tin hiện hành trong ``[0, 1]``.
        mode: ``SAFE`` khi trust = 0.
        reason: Lý do của mức tin hiện hành.
        transitions: Nhật ký chuyển chế độ.
    """

    def __init__(self, *, window: int = DEFAULT_WINDOW, min_days: int = DEFAULT_MIN_DAYS) -> None:
        if window < 1:
            raise ValueError("window phải dương")
        if not 1 <= min_days <= window:
            raise ValueError("min_days phải nằm trong [1, window]")
        self.window = window
        self.min_days = min_days
        self.trust = 0.0
        self.mode = Mode.SAFE
        self.reason = f"chưa có kỳ nào đo kỹ năng (cần {min_days})"
        self.skill: dict[str, float] | None = None
        self.transitions: list[dict[str, object]] = []
        self._evidence: deque[tuple[float, float, float, float]] = deque(maxlen=window)

    @property
    def is_safe(self) -> bool:
        """Dự báo hiện hành có đúng bằng nền không."""
        return self.mode is Mode.SAFE

    def _set(self, trust: float, reason: str, day_index: int | None) -> None:
        mode = Mode.SAFE if trust <= 0.0 else Mode.NORMAL
        if mode is not self.mode:
            log = LOGGER.warning if mode is Mode.SAFE else LOGGER.info
            log("Độ tin → %s: %s", mode.value, reason)
            self.transitions.append({"to": mode.value, "reason": reason, "day": day_index})
        self.trust = float(trust)
        self.mode = mode
        self.reason = reason

    def observe(
        self,
        *,
        logloss: float,
        brier: float,
        baseline_logloss: float,
        baseline_brier: float,
        drifted: bool = False,
        model_failed: bool = False,
        day_index: int | None = None,
    ) -> Mode:
        """Nạp điểm một kỳ của phép trộn (trước cổng) và cập nhật mức tin.

        Args:
            logloss: Log-loss trung bình mỗi con của phép trộn.
            brier: Brier trung bình mỗi con của phép trộn.
            baseline_logloss: Log-loss của nền trên cùng kỳ.
            baseline_brier: Brier của nền trên cùng kỳ.
            drifted: Bộ phát hiện trôi lệch có báo động ở kỳ này không.
            model_failed: Có cánh tay lỗi khi khớp hoặc dự đoán cho kỳ này không.
            day_index: Chỉ số ngày, chỉ dùng để ghi nhật ký.

        Returns:
            Chế độ sau khi cập nhật.

        Raises:
            ValueError: Khi điểm không hữu hạn, âm, hoặc điểm nền bằng 0.
        """
        scores = (logloss, brier, baseline_logloss, baseline_brier)
        if not all(np.isfinite(value) and value >= 0.0 for value in scores):
            raise ValueError("điểm phải hữu hạn và không âm")
        if baseline_logloss <= 0.0 or baseline_brier <= 0.0:
            raise ValueError("điểm của nền phải dương")

        if model_failed:
            self._evidence.clear()
            self.skill = None
            self._set(0.0, "mô hình lỗi khi khớp hoặc dự đoán; đo kỹ năng lại từ đầu", day_index)
            return self.mode
        if drifted:
            self._evidence.clear()
            self.skill = None
            self._set(0.0, "bộ phát hiện báo trôi lệch khái niệm; đo kỹ năng lại từ đầu", day_index)
            return self.mode

        self._evidence.append(tuple(float(value) for value in scores))
        if len(self._evidence) < self.min_days:
            self._set(0.0, f"mới đo {len(self._evidence)}/{self.min_days} kỳ kỹ năng", day_index)
            return self.mode

        loss, score, base_loss, base_score = np.mean(np.asarray(self._evidence), axis=0)
        self.skill = {
            "logloss": float((base_loss - loss) / base_loss),
            "brier": float((base_score - score) / base_score),
            "days": len(self._evidence),
        }
        trust = model_trust(self.skill["logloss"], self.skill["brier"])
        self._set(
            trust,
            f"kỹ năng {len(self._evidence)} kỳ: log-loss {self.skill['logloss']:+.5f}, "
            f"Brier {self.skill['brier']:+.5f} → độ tin {trust:.3f}",
            day_index,
        )
        return self.mode

    def apply(self, model_probabilities: np.ndarray) -> np.ndarray:
        """Dự báo công bố: ``trust·trộn + (1 − trust)·nền``."""
        model = np.asarray(model_probabilities, dtype=float)
        return self.trust * model + (1.0 - self.trust) * BASELINE_RATE

    def state(self) -> dict[str, object]:
        """Trạng thái hiện tại, để ghi vào báo cáo chạy."""
        return {
            "mode": self.mode.value,
            "trust": self.trust,
            "reason": self.reason,
            "window": self.window,
            "min_days": self.min_days,
            "skill": self.skill,
            "observations": len(self._evidence),
            "transitions": list(self.transitions),
        }
