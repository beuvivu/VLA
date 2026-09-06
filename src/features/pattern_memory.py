"""Bạc nhớ ma trận và nhịp gan.

* **Bạc nhớ** — bảng xác suất điều kiện P(con Y về ngày T | con X về ngày T−1)
  cho toàn bộ 100×100 cặp, làm trơn Laplace. Với mỗi con, đặc trưng là mức bạc
  nhớ trung bình từ những con vừa về ở ngày neo.
* **Nhịp gan** — Z-score của khoảng cách hiện tại so với phân bố khoảng cách của
  chính con đó. Đây là thước "sắp gãy gan", và cũng chính là đại lượng mà bộ lọc
  rủi ro ở giai đoạn sau dùng để chặn bẫy lô gan.

Cả hai đều so với đường cơ sở chứ không đọc giá trị tuyệt đối: một xác suất điều
kiện 0,24 nghe như tín hiệu cho tới khi biết tỉ lệ nền cũng là 0,2374.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from bridges.tensor import NUMBER_SPACE
from features.base import FeatureContext
from xsmb_domain import baseline_rate

_EPS = 1e-9
_LAPLACE = 1.0


@dataclass
class PatternMemoryExtractor:
    """Bảng bạc nhớ có làm trơn, và Z-score nhịp gan."""

    memory_days: int = 365
    name: str = "pattern_memory"
    description: str = "Bạc nhớ ma trận điều kiện và Z-score nhịp gan"
    feature_names: tuple[str, ...] = field(
        default_factory=lambda: (
            "memory_prob",
            "memory_excess",
            "gap_current",
            "gap_zscore",
            "gap_ratio",
        )
    )

    def extract(self, ctx: FeatureContext) -> np.ndarray:
        out = np.zeros((NUMBER_SPACE, len(self.feature_names)), dtype=np.float64)
        hits = ctx.hits(self.memory_days)
        if hits.shape[0] >= 2:
            out[:, 0], out[:, 1] = self._memory_signals(hits, ctx.hits(1)[0])

        full = ctx.hits()
        if full.shape[0]:
            out[:, 2], out[:, 3], out[:, 4] = self._gap_signals(full)
        return out

    @staticmethod
    def _memory_signals(hits: np.ndarray, today: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """P(Y hôm nay | X hôm qua), làm trơn Laplace, lấy trung bình theo X."""
        previous = hits[:-1].astype(np.float64)
        following = hits[1:].astype(np.float64)
        joint = previous.T @ following
        occurrences = previous.sum(axis=0)[:, None]
        # Laplace: con X chỉ mới về vài lần không được phép phát ra xác suất 0
        # hay 1 chỉ vì mẫu quá mỏng.
        table = (joint + _LAPLACE) / (occurrences + _LAPLACE * NUMBER_SPACE)

        partners = np.flatnonzero(today)
        if partners.size == 0:
            return np.zeros(NUMBER_SPACE), np.zeros(NUMBER_SPACE)
        probability = table[partners].mean(axis=0)
        return probability, probability - baseline_rate("loto")

    @staticmethod
    def _gap_signals(
        hits: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Khoảng cách hiện tại, Z-score của nó, và tỉ lệ so với khoảng cách trung bình."""
        n_days = hits.shape[0]
        current = np.full(NUMBER_SPACE, float(n_days))
        zscore = np.zeros(NUMBER_SPACE)
        ratio = np.zeros(NUMBER_SPACE)

        for number in range(NUMBER_SPACE):
            days = np.flatnonzero(hits[:, number])
            if days.size == 0:
                continue
            current[number] = float(n_days - 1 - days[-1])
            if days.size < 3:
                continue
            intervals = np.diff(days).astype(np.float64)
            mean = float(intervals.mean())
            std = float(intervals.std(ddof=1)) if intervals.size > 1 else 0.0
            if std > _EPS:
                zscore[number] = (current[number] - mean) / std
            if mean > _EPS:
                ratio[number] = current[number] / mean
        return current, zscore, ratio
