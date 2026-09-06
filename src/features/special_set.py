"""Cầu Đặc Biệt: bộ số, chạm, tổng, đầu/đuôi, bóng — và dàn đề tinh gọn.

Phân tích giải Đặc Biệt theo các trục mà giới soi cầu dùng, rồi quy mỗi trục về
một đặc trưng trên 100 con: con này có cùng chạm/tổng/bộ với các giải ĐB gần đây
đến mức nào, so với mức mà một con bất kỳ đạt được do ngẫu nhiên.

``build_dan`` xuất dàn đề tinh gọn từ phong độ tuần của các trục chạm và tổng.
Dàn là danh sách con, không phải lời khuyên đặt cược: nó chỉ nói "các trục đang
mạnh nhất trong cửa sổ gần đây chỉ tới nhóm con này".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

import numpy as np

from bridges.tensor import NUMBER_SPACE
from features.base import FeatureContext
from number_reference import (
    bo,
    bong_am,
    bong_duong,
    digit_sum_mod10,
    head,
    normalize_two_digit,
    tail,
)

_EPS = 1e-9

_HEAD: Final[np.ndarray] = np.array([head(n) for n in range(NUMBER_SPACE)], dtype=np.int16)
_TAIL: Final[np.ndarray] = np.array([tail(n) for n in range(NUMBER_SPACE)], dtype=np.int16)
_SUM: Final[np.ndarray] = np.array(
    [digit_sum_mod10(n) for n in range(NUMBER_SPACE)], dtype=np.int16
)
_BONG_DUONG: Final[np.ndarray] = np.array(
    [int(bong_duong(n)) for n in range(NUMBER_SPACE)], dtype=np.int16
)
_BONG_AM: Final[np.ndarray] = np.array(
    [int(bong_am(n)) for n in range(NUMBER_SPACE)], dtype=np.int16
)
#: ``_BO_ID[n]`` là mã bộ số của ``n``; hai con cùng bộ có cùng mã.
_BO_ID: Final[np.ndarray] = np.array(
    [min(int(item) for item in bo(n)) for n in range(NUMBER_SPACE)], dtype=np.int16
)

DAN_SIZES: Final[tuple[int, ...]] = (36, 64)


def touches(number: int) -> tuple[int, int]:
    """Hai chạm của một con: chữ số đầu và chữ số đuôi."""
    text = normalize_two_digit(number)
    return int(text[0]), int(text[1])


@dataclass
class SpecialSetExtractor:
    """Phong độ của các trục ĐB, quy về đặc trưng trên từng con."""

    window_days: int = 7
    name: str = "special_set"
    description: str = "Bộ số, chạm, tổng và bóng của giải Đặc Biệt gần đây"
    feature_names: tuple[str, ...] = field(
        default_factory=lambda: (
            "touch_rate",
            "sum_rate",
            "bo_rate",
            "shadow_rate",
            "head_rate",
            "tail_rate",
        )
    )

    def extract(self, ctx: FeatureContext) -> np.ndarray:
        out = np.zeros((NUMBER_SPACE, len(self.feature_names)), dtype=np.float64)
        recent = ctx.de_index(self.window_days)
        if recent.size == 0:
            return out

        numbers = np.arange(NUMBER_SPACE)
        # Mỗi trục: tỉ lệ ngày gần đây mà giải ĐB chia sẻ đặc điểm đó với con này.
        out[:, 0] = self._share(recent, numbers, lambda x: np.stack([_HEAD[x], _TAIL[x]], axis=-1))
        out[:, 1] = self._equal_rate(_SUM[recent], _SUM[numbers])
        out[:, 2] = self._equal_rate(_BO_ID[recent], _BO_ID[numbers])
        out[:, 3] = self._shadow_rate(recent, numbers)
        out[:, 4] = self._equal_rate(_HEAD[recent], _HEAD[numbers])
        out[:, 5] = self._equal_rate(_TAIL[recent], _TAIL[numbers])
        return out

    @staticmethod
    def _equal_rate(recent_key: np.ndarray, number_key: np.ndarray) -> np.ndarray:
        return (number_key[:, None] == recent_key[None, :]).mean(axis=1)

    @staticmethod
    def _share(recent: np.ndarray, numbers: np.ndarray, key) -> np.ndarray:
        """Tỉ lệ ngày mà con này dùng chung ít nhất một chạm với giải ĐB."""
        recent_keys = key(recent)
        number_keys = key(numbers)
        shared = (number_keys[:, None, :, None] == recent_keys[None, :, None, :]).any(axis=(2, 3))
        return shared.mean(axis=1)

    @staticmethod
    def _shadow_rate(recent: np.ndarray, numbers: np.ndarray) -> np.ndarray:
        """Tỉ lệ ngày mà con này là bóng âm hoặc bóng dương của giải ĐB."""
        duong = _BONG_DUONG[recent]
        am = _BONG_AM[recent]
        match = (numbers[:, None] == duong[None, :]) | (numbers[:, None] == am[None, :])
        return match.mean(axis=1)

    def build_dan(self, ctx: FeatureContext, size: int = 36) -> list[str]:
        """Dàn đề tinh gọn ``size`` con, chọn theo các trục mạnh nhất trong cửa sổ.

        Không phải lời khuyên đặt cược. Đây là câu "các trục chạm/tổng đang mạnh
        nhất trong cửa sổ gần đây chỉ tới nhóm con này", và câu đó chỉ có giá trị
        nếu chính các trục ấy đo được là hơn ngẫu nhiên — điều mà lớp đo ở giai
        đoạn sau trả lời, không phải hàm này.
        """
        if size <= 0 or size > NUMBER_SPACE:
            raise ValueError(f"kích thước dàn phải trong 1..{NUMBER_SPACE}")
        block = self.extract(ctx)
        # Chạm và tổng là hai trục mà phương pháp dàn đề truyền thống dùng.
        score = block[:, 0] + block[:, 1]
        order = np.lexsort((np.arange(NUMBER_SPACE), -score))
        return [normalize_two_digit(int(n)) for n in order[:size]]
