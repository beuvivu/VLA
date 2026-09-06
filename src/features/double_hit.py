"""Cầu hai nháy và tương quan xiên cặp.

Hai đặc trưng độc lập nhau:

* **Mật độ nổ kép** — tần suất một con về từ hai nháy trở lên trong cửa sổ gần
  đây, so với tỉ lệ nền lý thuyết chứ không so với chính nó.
* **Tương quan xiên cặp** — với mỗi con, mức độ nó hay về cùng ngày với những
  con vừa về ở ngày neo. Dùng hệ số Pearson trên ma trận trúng 0/1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from bridges.tensor import NUMBER_SPACE
from features.base import FeatureContext
from xsmb_domain import LOTO_DRAWS_PER_DAY, UNIFORM_TWO_DIGIT_RATE

_EPS = 1e-9

#: P(một con cụ thể về từ hai nháy trở lên trong một kỳ) dưới giả thiết đều.
_TWO_NHAY_BASELINE: float = float(
    1.0
    - (1.0 - UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_DAY
    - LOTO_DRAWS_PER_DAY
    * UNIFORM_TWO_DIGIT_RATE
    * (1.0 - UNIFORM_TWO_DIGIT_RATE) ** (LOTO_DRAWS_PER_DAY - 1)
)


@dataclass
class DoubleHitBridgeExtractor:
    """Mật độ nổ kép và tương quan cùng về giữa các con."""

    window_days: int = 30
    correlation_days: int = 180
    name: str = "double_hit"
    description: str = "Mật độ nổ kép 30 kỳ và tương quan xiên cặp"
    feature_names: tuple[str, ...] = field(
        default_factory=lambda: (
            "double_rate",
            "double_excess",
            "partner_correlation",
            "partner_cohit_rate",
        )
    )

    def extract(self, ctx: FeatureContext) -> np.ndarray:
        out = np.zeros((NUMBER_SPACE, len(self.feature_names)), dtype=np.float64)

        counts = ctx.counts(self.window_days)
        if counts.size:
            double_rate = (counts >= 2).mean(axis=0)
            out[:, 0] = double_rate
            # So với tỉ lệ nền lý thuyết: "hay nổ kép" chỉ có nghĩa khi đối chiếu
            # với mức mà một con bất kỳ nổ kép do ngẫu nhiên.
            out[:, 1] = double_rate - _TWO_NHAY_BASELINE

        hits = ctx.hits(self.correlation_days).astype(np.float64)
        today = ctx.hits(1)[0] if ctx.history_length else np.zeros(NUMBER_SPACE, bool)
        if hits.shape[0] >= 2 and today.any():
            out[:, 2], out[:, 3] = self._partner_signals(hits, today)
        return out

    @staticmethod
    def _partner_signals(hits: np.ndarray, today: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Tương quan trung bình và tỉ lệ cùng về với các con vừa ra hôm nay."""
        centred = hits - hits.mean(axis=0, keepdims=True)
        norms = np.sqrt((centred**2).sum(axis=0))
        # Con không bao giờ về (hoặc về mọi ngày) có phương sai 0; đặt chuẩn hóa
        # bằng 1 để phép chia trả 0 thay vì vô cực.
        safe = np.where(norms > _EPS, norms, 1.0)
        correlation = (centred.T @ centred) / np.outer(safe, safe)
        np.fill_diagonal(correlation, 0.0)

        partners = np.flatnonzero(today)
        mean_correlation = correlation[:, partners].mean(axis=1)

        cohit = hits.T @ hits[:, partners]
        appearances = np.maximum(hits.sum(axis=0), 1.0)[:, None]
        mean_cohit = (cohit / appearances).mean(axis=1)
        return mean_correlation, mean_cohit
