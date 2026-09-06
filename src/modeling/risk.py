"""Bộ lọc rủi ro: chặn bẫy lô gan.

Một con càng lâu không về càng dễ trông như "sắp phải về". Với xổ số công bằng
thì niềm tin đó sai — mỗi kỳ độc lập với kỳ trước, nên khoảng cách dài không làm
tăng xác suất. Bộ lọc này không sửa xác suất theo hướng nào cả; nó chỉ **đánh
dấu** các con đã vượt ngưỡng nhịp gan để phần trình bày nói rõ ra, và tùy chọn
loại chúng khỏi danh sách gợi ý.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from bridges.tensor import NUMBER_SPACE
from features import FeatureContext, PatternMemoryExtractor
from number_reference import normalize_two_digit

DEFAULT_GAN_THRESHOLD_DAYS = 15


@dataclass
class GanFilter:
    """Đánh dấu và (tùy chọn) loại các con có nhịp gan vượt ngưỡng."""

    threshold_days: int = DEFAULT_GAN_THRESHOLD_DAYS
    exclude: bool = False

    def gaps(self, ctx: FeatureContext) -> np.ndarray:
        """Số ngày kể từ lần về gần nhất, cho cả 100 con."""
        block = PatternMemoryExtractor().extract(ctx)
        return block[:, 2]

    def flagged(self, ctx: FeatureContext) -> list[str]:
        gaps = self.gaps(ctx)
        return [normalize_two_digit(int(n)) for n in np.flatnonzero(gaps > self.threshold_days)]

    def apply(self, probabilities: np.ndarray, ctx: FeatureContext) -> np.ndarray:
        """Trả về xác suất đã lọc; giữ nguyên nếu chỉ ở chế độ cảnh báo.

        Khi loại, phần xác suất bị lấy đi được chia lại cho các con còn lại nếu
        đầu vào là phân phối tổng bằng 1 — bỏ qua bước đó sẽ tạo ra một phân
        phối hụt, và mọi phép chấm log-loss phía sau sẽ sai lệch.
        """
        if probabilities.shape != (NUMBER_SPACE,):
            raise ValueError(f"xác suất phải là vector {NUMBER_SPACE} phần tử")
        if not self.exclude:
            return probabilities

        keep = self.gaps(ctx) <= self.threshold_days
        if not keep.any():
            return probabilities
        filtered = np.where(keep, probabilities, 0.0)
        total = float(probabilities.sum())
        if abs(total - 1.0) < 1e-6:
            return filtered / max(filtered.sum(), 1e-12)
        return filtered
