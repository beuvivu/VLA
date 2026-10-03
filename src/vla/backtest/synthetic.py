"""Lịch sử tổng hợp có CÀI tín hiệu, để kiểm công cụ đo có phát hiện được không."""

from __future__ import annotations

import numpy as np
import pandas as pd

from vla.features.engineer import History, history_from_frame
from xsmb_domain import FIELD_WIDTHS, PRIZE_FIELDS


def synthetic_history(n: int, seed: int, *, loto_signal: float = 0.5, de_signal: float = 0.15) -> History:
    """Kỳ quay ngẫu nhiên đều, cộng hai tín hiệu cài sẵn.

    LOTO: nếu 37 về ở kỳ t thì giải bảy thứ nhất kỳ t+1 là 73 với xác suất
    ``loto_signal``. Đặc Biệt: hai số cuối kỳ t+1 = hai số cuối kỳ t + 1 (mod
    100) với xác suất ``de_signal``. Đặt cả hai bằng 0 là lịch sử thuần ngẫu nhiên.
    """
    rng = np.random.default_rng(seed)
    values = np.column_stack([rng.integers(0, 10**w, size=n) for _, w in FIELD_WIDTHS])
    seven = PRIZE_FIELDS.index("prize7_1")
    for t in range(1, n):
        if 37 in set((values[t - 1] % 100).tolist()) and rng.random() < loto_signal:
            values[t, seven] = 73
        if rng.random() < de_signal:
            values[t, 0] = values[t, 0] // 100 * 100 + (values[t - 1, 0] % 100 + 1) % 100
    raw = pd.DataFrame(values, columns=list(PRIZE_FIELDS))
    raw.insert(0, "date", pd.date_range("2010-01-01", periods=n, freq="D").strftime("%Y-%m-%d"))
    return history_from_frame(raw)


POWER_SIGNALS = {"loto": {"loto_signal": 0.5, "de_signal": 0.0}, "de": {"loto_signal": 0.0, "de_signal": 0.15}}


def power_history(mode: str, n: int, seed: int) -> History:
    """Lịch sử cho kiểm độ nhạy của MỘT chế độ: chỉ cài tín hiệu của chế độ ấy.

    Đặc Biệt cũng là một trong 27 giải LOTO, nên cài cả hai thì tín hiệu
    "Đặc Biệt + 1" thành thêm một tín hiệu trễ của LOTO và phép đo LOTO không
    còn nói được mô hình bắt đúng tín hiệu 37 → 73.
    """
    return synthetic_history(n, seed, **POWER_SIGNALS[mode])
