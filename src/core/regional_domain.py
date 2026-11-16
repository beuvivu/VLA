"""Cấu trúc kỳ quay của MỘT ĐÀI miền Trung / miền Nam và các hằng số xác suất suy ra.

Một đài quay 18 giải mỗi kỳ (G.8 hai chữ số … Đặc Biệt sáu chữ số), khác hẳn 27 giải của XSMB
(`core.xsmb_domain`). Dùng hằng số của XSMB cho đài miền là sai MỨC NỀN: một con lô có mặt ở một
đài với xác suất ``1 − 0,99¹⁸ ≈ 16,55%``, không phải ``1 − 0,99²⁷ ≈ 23,77%``.

Mỗi đài là một bộ lồng cầu riêng, quay theo lịch tuần riêng. Module này chỉ mô tả MỘT đài; việc
gộp nhiều đài là quyết định của nơi phân tích (`stats.regional_stats`), không phải của miền.

Module thuần Python (không numpy/pandas) để bộ thu thập (`ingest.regional_lottery`) đọc cùng một
bố cục giải mà không kéo thêm thư viện.
"""

from __future__ import annotations

from fractions import Fraction
from math import comb
from typing import Final

#: (tên giải, số lượng giải, số chữ số) theo thứ tự in của bảng kết quả, G.8 trước, Đặc Biệt cuối.
PRIZE_SPECS: Final[tuple[tuple[str, int, int], ...]] = (
    ("G.8", 1, 2), ("G.7", 1, 3), ("G.6", 3, 4), ("G.5", 1, 4),
    ("G.4", 7, 5), ("G.3", 2, 5), ("G.2", 1, 5), ("G.1", 1, 5), ("ĐB", 1, 6),
)
SPECIAL_PRIZE: Final[str] = "ĐB"
#: Mã miền → tên hiển thị.
REGIONS: Final[dict[str, str]] = {"mt": "Miền Trung", "mn": "Miền Nam"}

#: (giải, vị trí trong giải) của 18 ô kết quả, theo thứ tự in.
SLOTS: Final[tuple[tuple[str, int], ...]] = tuple(
    (name, position) for name, count, _ in PRIZE_SPECS for position in range(1, count + 1)
)
#: Số chữ số của từng ô trong ``SLOTS``.
SLOT_WIDTHS: Final[tuple[int, ...]] = tuple(width for _, count, width in PRIZE_SPECS for _ in range(count))
#: Chỉ số của giải Đặc Biệt trong ``SLOTS``.
SPECIAL_SLOT: Final[int] = SLOTS.index((SPECIAL_PRIZE, 1))

#: Số lồng cầu của một kỳ: mỗi HÀNG (đơn vị, chục, … trăm nghìn) là một lồng mười quả 0–9. Giải
#: ``w`` chữ số dùng ``w`` lồng thấp nhất, nên mọi giải cùng rút hàng đơn vị từ MỘT lồng.
CAGES: Final[int] = max(SLOT_WIDTHS)
CAGE_NAMES: Final[tuple[str, ...]] = ("đơn vị", "chục", "trăm", "nghìn", "chục nghìn", "trăm nghìn")
#: Lồng của từng chữ số in (theo thứ tự ``SLOTS``, trái sang phải): 0 = đơn vị … 5 = trăm nghìn.
CAGE_OF_DIGIT: Final[tuple[int, ...]] = tuple(
    width - 1 - index for width in SLOT_WIDTHS for index in range(width)
)

#: Số con lô (hai số cuối) một đài cho ra mỗi kỳ.
LOTO_DRAWS_PER_STATION: Final[int] = len(SLOTS)
#: Tổng số chữ số in của một kỳ.
TOTAL_DIGITS: Final[int] = sum(SLOT_WIDTHS)
NUMBER_SPACE: Final[int] = 100
UNIFORM_TWO_DIGIT_RATE: Final[float] = 1.0 / NUMBER_SPACE

#: P(một con 00..99 có mặt ít nhất một lần trong kỳ của một đài) khi các giải độc lập và đều.
LOTO_BASELINE_RATE: Final[float] = 1.0 - (1.0 - UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_STATION
#: P(hai số cuối Đặc Biệt của một đài bằng một con cho trước).
DE_BASELINE_RATE: Final[float] = UNIFORM_TWO_DIGIT_RATE
#: P(hai con CỤ THỂ cùng có mặt trong một kỳ) — bao hàm–loại trừ, không phải bình phương mức nền.
PAIR_COOCCURRENCE_RATE: Final[float] = (
    1.0
    - 2.0 * (1.0 - UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_STATION
    + (1.0 - 2.0 * UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_STATION
)


def baseline_rate(mode: str) -> float:
    """Mức nền của một con trong một kỳ của một đài: ``loto`` (có mặt) hoặc ``de`` (đuôi Đặc Biệt)."""
    if mode == "loto":
        return LOTO_BASELINE_RATE
    if mode == "de":
        return DE_BASELINE_RATE
    raise ValueError("mode phải là 'loto' hoặc 'de'")


def nhay_distribution(slots: int = LOTO_DRAWS_PER_STATION, size: int = NUMBER_SPACE) -> tuple[float, ...]:
    """Phân phối chính xác số nháy của MỘT con trong một kỳ: ``Binomial(slots, 1/size)``.

    Phần tử ``k`` là P(con ấy về đúng ``k`` nháy), ``k = 0 … slots``.
    """
    if slots < 0 or size < 1:
        raise ValueError("slots ≥ 0 và size ≥ 1")
    total = Fraction(size) ** slots
    return tuple(float(Fraction(comb(slots, k) * (size - 1) ** (slots - k)) / total) for k in range(slots + 1))


def _surjections(n: int, parts: int) -> int:
    """Số cách xếp ``n`` giải vào đúng ``parts`` con, con nào cũng có giải (bao hàm–loại trừ)."""
    return sum((-1) ** j * comb(parts, j) * (parts - j) ** n for j in range(parts + 1))


def distinct_count_distribution(slots: int = LOTO_DRAWS_PER_STATION, size: int = NUMBER_SPACE) -> tuple[float, ...]:
    """Phân phối chính xác số con KHÁC NHAU về trong một kỳ (bài toán chiếm chỗ).

    ``P(D = d) = C(size, d) · Surj(slots, d) / size^slots``, tính bằng số nguyên nên không sai số
    làm tròn. Phần tử ``d`` là P(đúng ``d`` con khác nhau), ``d = 0 … min(slots, size)``. Kỳ vọng
    của nó là ``size · (1 − (1 − 1/size)^slots)``: 16,55 con với một đài miền, 23,77 với XSMB.
    """
    if slots < 0 or size < 1:
        raise ValueError("slots ≥ 0 và size ≥ 1")
    total = Fraction(size) ** slots
    return tuple(
        float(Fraction(comb(size, d) * _surjections(slots, d)) / total) for d in range(min(slots, size) + 1)
    )
