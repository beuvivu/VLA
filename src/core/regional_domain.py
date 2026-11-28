from __future__ import annotations

from fractions import Fraction
from math import comb
from typing import Final

PRIZE_SPECS: Final[tuple[tuple[str, int, int], ...]] = (
    ("G.8", 1, 2), ("G.7", 1, 3), ("G.6", 3, 4), ("G.5", 1, 4),
    ("G.4", 7, 5), ("G.3", 2, 5), ("G.2", 1, 5), ("G.1", 1, 5), ("ĐB", 1, 6),
)
SPECIAL_PRIZE: Final[str] = "ĐB"
REGIONS: Final[dict[str, str]] = {"mt": "Miền Trung", "mn": "Miền Nam"}

SLOTS: Final[tuple[tuple[str, int], ...]] = tuple(
    (name, position) for name, count, _ in PRIZE_SPECS for position in range(1, count + 1)
)
SLOT_WIDTHS: Final[tuple[int, ...]] = tuple(width for _, count, width in PRIZE_SPECS for _ in range(count))
SPECIAL_SLOT: Final[int] = SLOTS.index((SPECIAL_PRIZE, 1))

CAGES: Final[int] = max(SLOT_WIDTHS)
CAGE_NAMES: Final[tuple[str, ...]] = ("đơn vị", "chục", "trăm", "nghìn", "chục nghìn", "trăm nghìn")
CAGE_OF_DIGIT: Final[tuple[int, ...]] = tuple(
    width - 1 - index for width in SLOT_WIDTHS for index in range(width)
)

LOTO_DRAWS_PER_STATION: Final[int] = len(SLOTS)
TOTAL_DIGITS: Final[int] = sum(SLOT_WIDTHS)
NUMBER_SPACE: Final[int] = 100
UNIFORM_TWO_DIGIT_RATE: Final[float] = 1.0 / NUMBER_SPACE

LOTO_BASELINE_RATE: Final[float] = 1.0 - (1.0 - UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_STATION
DE_BASELINE_RATE: Final[float] = UNIFORM_TWO_DIGIT_RATE
PAIR_COOCCURRENCE_RATE: Final[float] = (
    1.0
    - 2.0 * (1.0 - UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_STATION
    + (1.0 - 2.0 * UNIFORM_TWO_DIGIT_RATE) ** LOTO_DRAWS_PER_STATION
)


def baseline_rate(mode: str) -> float:
    if mode == "loto":
        return LOTO_BASELINE_RATE
    if mode == "de":
        return DE_BASELINE_RATE
    raise ValueError("mode phải là 'loto' hoặc 'de'")


def nhay_distribution(slots: int = LOTO_DRAWS_PER_STATION, size: int = NUMBER_SPACE) -> tuple[float, ...]:
    if slots < 0 or size < 1:
        raise ValueError("slots ≥ 0 và size ≥ 1")
    total = Fraction(size) ** slots
    return tuple(float(Fraction(comb(slots, k) * (size - 1) ** (slots - k)) / total) for k in range(slots + 1))


def _surjections(n: int, parts: int) -> int:
    return sum((-1) ** j * comb(parts, j) * (parts - j) ** n for j in range(parts + 1))


def distinct_count_distribution(slots: int = LOTO_DRAWS_PER_STATION, size: int = NUMBER_SPACE) -> tuple[float, ...]:
    if slots < 0 or size < 1:
        raise ValueError("slots ≥ 0 và size ≥ 1")
    total = Fraction(size) ** slots
    return tuple(
        float(Fraction(comb(size, d) * _surjections(slots, d)) / total) for d in range(min(slots, size) + 1)
    )
