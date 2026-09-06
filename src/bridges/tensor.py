"""Ma trận chữ số theo vị trí trên bảng kết quả, dựng một lần cho toàn lịch sử.

Mọi phép quét cầu đều đọc từ đây thay vì tự cắt lại DataFrame, nên chi phí dựng
trả một lần và phần quét còn lại thuần NumPy.

Ràng buộc lịch là bắt buộc chứ không tùy chọn: ghép chéo ngày nói "vị trí A ở
ngày T−k", và chỉ số hàng chỉ tương đương ngày lịch khi chuỗi ngày liền mạch.
Trên chuỗi có lỗ hổng, ``values[t - k]`` lặng lẽ trỏ sang một ngày khác và mọi
đường cầu tìm được đều sai — nên lớp này từ chối dựng thay vì trả kết quả hỏng.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from calendar_alignment import require_daily_contiguous
from xsmb_domain import (
    FIELD_WIDTHS,
    TOTAL_DIGITS,
    build_position_labels,
    raw_digit_matrix,
)

NUMBER_SPACE: Final[int] = 100

#: Chỉ số cột của hai chữ số cuối mỗi giải trong luồng chữ số phẳng.
#: Hai chữ số cuối của một giải chính là con lô tô mà giải đó sinh ra.
_LAST_TWO: Final[tuple[tuple[int, int], ...]] = tuple(
    (offset + width - 2, offset + width - 1)
    for offset, width in zip(
        np.cumsum([0, *[w for _, w in FIELD_WIDTHS[:-1]]]).tolist(),
        [w for _, w in FIELD_WIDTHS],
        strict=True,
    )
)


@dataclass(frozen=True)
class DigitTensor:
    """Lịch sử đã số hóa: chữ số theo vị trí, số trúng theo ngày.

    ``values`` có dạng ``(số ngày, 107)`` kiểu ``uint8``; ``values[t, p]`` là chữ
    số ở vị trí ``p`` của ngày ``dates[t]``. ``loto_counts[t, n]`` là số lần con
    ``n`` xuất hiện trong ngày ``t`` (0, 1 hoặc nhiều hơn — cầu hai nháy cần đếm
    chứ không chỉ cần có), và ``de_index[t]`` là hai chữ số cuối của giải Đặc Biệt.
    """

    values: np.ndarray
    dates: pd.DatetimeIndex
    position_labels: tuple[str, ...]
    loto_counts: np.ndarray
    de_index: np.ndarray

    def __post_init__(self) -> None:
        if self.values.ndim != 2 or self.values.shape[1] != TOTAL_DIGITS:
            raise ValueError(f"values phải có dạng (n, {TOTAL_DIGITS})")
        if len(self.dates) != self.values.shape[0]:
            raise ValueError("dates và values phải cùng độ dài")
        if self.loto_counts.shape != (self.values.shape[0], NUMBER_SPACE):
            raise ValueError(f"loto_counts phải có dạng (n, {NUMBER_SPACE})")
        if self.de_index.shape != (self.values.shape[0],):
            raise ValueError("de_index phải có một phần tử mỗi ngày")

    @property
    def n_days(self) -> int:
        return int(self.values.shape[0])

    @property
    def n_positions(self) -> int:
        return int(self.values.shape[1])

    def loto_hits(self) -> np.ndarray:
        """Ma trận ``(ngày, 100)`` kiểu bool: con số có về trong ngày hay không."""
        return self.loto_counts > 0

    def loto_double_hits(self) -> np.ndarray:
        """Ma trận ``(ngày, 100)`` kiểu bool cho tiêu chí hai nháy."""
        return self.loto_counts >= 2

    @classmethod
    def from_raw(cls, df_raw: pd.DataFrame) -> DigitTensor:
        """Dựng từ bảng kết quả thô, sau khi bắt buộc chuỗi ngày liền mạch."""
        if "date" not in df_raw.columns:
            raise ValueError("bảng kết quả thô thiếu cột 'date'")
        frame = df_raw.sort_values("date").reset_index(drop=True)
        dates = require_daily_contiguous(frame["date"], context="quét cầu ghép chéo ngày")

        values = raw_digit_matrix(frame)
        labels = tuple(build_position_labels())

        # Hai chữ số cuối của mỗi giải là con lô tô của giải đó; đếm bằng
        # bincount theo hàng thay vì vòng lặp Python trên từng ngày.
        n_days = values.shape[0]
        pairs = np.empty((n_days, len(_LAST_TWO)), dtype=np.int16)
        for slot, (hi, lo) in enumerate(_LAST_TWO):
            pairs[:, slot] = values[:, hi].astype(np.int16) * 10 + values[:, lo]

        counts = np.zeros((n_days, NUMBER_SPACE), dtype=np.uint8)
        rows = np.repeat(np.arange(n_days), pairs.shape[1])
        np.add.at(counts, (rows, pairs.ravel()), 1)

        # Giải Đặc Biệt là trường đầu tiên, nên hai chữ số cuối của nó là cột 0.
        de_index = pairs[:, 0].astype(np.int16)

        return cls(
            values=values,
            dates=dates,
            position_labels=labels,
            loto_counts=counts,
            de_index=de_index,
        )
