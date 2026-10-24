"""Định danh một đường cầu ghép chéo ngày.

Khác biệt so với ``dynamic_cau.PatternSpec``: ở đó hai vị trí nguồn luôn lấy từ
*cùng một ngày* T−1. Ở đây mỗi vị trí mang độ trễ riêng, nên diễn đạt được đúng
thứ đặc tả yêu cầu — vị trí A ở ngày T−k ghép với vị trí B ở ngày T−k+1.

Lớp này chỉ *đặt tên* cho một giả thuyết. Việc chấm điểm nằm ở ``scanner``, và
việc quyết định giả thuyết nào được phép đi tiếp nằm ở ``firewall``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

TRANSFORM_CONCAT: Final[str] = "concat"
TRANSFORM_REVERSE_CONCAT: Final[str] = "reverse_concat"
TRANSFORM_REVERSE_PAIR: Final[str] = "reverse_pair"
TRANSFORM_BO: Final[str] = "bo"

TRANSFORMATIONS: Final[tuple[str, ...]] = (
    TRANSFORM_CONCAT,
    TRANSFORM_REVERSE_CONCAT,
    TRANSFORM_REVERSE_PAIR,
    TRANSFORM_BO,
)

TARGET_LOTO: Final[str] = "loto"
TARGET_LOTO_2_NHAY: Final[str] = "loto_2_nhay"
TARGET_DE: Final[str] = "de"

TARGET_TYPES: Final[tuple[str, ...]] = (TARGET_LOTO, TARGET_LOTO_2_NHAY, TARGET_DE)


@dataclass(frozen=True)
class CrossDayPatternSpec:
    """Một giả thuyết cầu: hai vị trí, hai độ trễ, một phép biến đổi, một bóng."""

    position_a: int
    position_b: int
    lag_a: int
    lag_b: int
    transformation: str = TRANSFORM_CONCAT
    shadow: str = "thuc"

    def __post_init__(self) -> None:
        if self.lag_a < 1 or self.lag_b < 1:
            raise ValueError("độ trễ phải tính bằng số ngày dương")
        if self.transformation not in TRANSFORMATIONS:
            raise ValueError(f"phép biến đổi không hợp lệ: {self.transformation!r}")

    @property
    def span(self) -> int:
        """Biên độ chạy: số ngày mà đường cầu trải qua."""
        return abs(self.lag_a - self.lag_b) + 1

    @property
    def identifier(self) -> str:
        return (
            f"{self.transformation}|{self.shadow}|"
            f"p{self.position_a}@T-{self.lag_a}+p{self.position_b}@T-{self.lag_b}"
        )


def default_lag_pairs(max_span: int = 3) -> tuple[tuple[int, int], ...]:
    """Cặp độ trễ mặc định: lag-1 cùng ngày, rồi ghép chéo A(T−k) với B(T−k+1).

    ``max_span=1`` cho đúng hành vi lag-1 của ``dynamic_cau``; mỗi nấc tăng thêm
    một biên độ ``k`` và nhân đôi kích thước họ giả thuyết, nên giá trị này là
    núm điều khiển trực tiếp của bài toán đa kiểm định.
    """
    if max_span < 1:
        raise ValueError("max_span phải ít nhất bằng 1")
    pairs = [(1, 1)]
    pairs.extend((k, k - 1) for k in range(2, max_span + 1))
    return tuple(pairs)
