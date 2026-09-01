from __future__ import annotations

"""Canonical two-digit number ontology used by research/statistics modules.

This module contains deterministic combinatorics only.  It deliberately has no
prediction logic so that concepts such as reverse, bóng, bộ, chạm, tổng and kép
have one definition across the repository.
"""

from functools import lru_cache

BONG: dict[int, int] = {
    0: 5,
    1: 6,
    2: 7,
    3: 8,
    4: 9,
    5: 0,
    6: 1,
    7: 2,
    8: 3,
    9: 4,
}


def normalize_two_digit(value: int | str) -> str:
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid two-digit value: {value!r}") from exc
    if not 0 <= n <= 99:
        raise ValueError(f"Two-digit value outside 00..99: {value!r}")
    return f"{n:02d}"


def head(value: int | str) -> int:
    return int(normalize_two_digit(value)[0])


def tail(value: int | str) -> int:
    return int(normalize_two_digit(value)[1])


def digit_sum(value: int | str) -> int:
    s = normalize_two_digit(value)
    return int(s[0]) + int(s[1])


def digit_sum_mod10(value: int | str) -> int:
    return digit_sum(value) % 10


def reverse(value: int | str) -> str:
    return normalize_two_digit(value)[::-1]


def bong_digit(value: int) -> int:
    if value not in BONG:
        raise ValueError(f"Digit outside 0..9: {value!r}")
    return BONG[value]


def bong(value: int | str) -> str:
    s = normalize_two_digit(value)
    return f"{BONG[int(s[0])]}{BONG[int(s[1])]}"


@lru_cache(maxsize=100)
def bo(value: int | str) -> frozenset[str]:
    """Return the bóng/reverse family containing ``value``.

    The family is the Cartesian product of each digit and its bóng, including
    reversed orientation.  Depending on symmetry it contains 4 or 8 values.
    """

    s = normalize_two_digit(value)
    x, y = int(s[0]), int(s[1])
    xs = {x, BONG[x]}
    ys = {y, BONG[y]}
    out: set[str] = set()
    for a in xs:
        for b in ys:
            out.add(f"{a}{b}")
            out.add(f"{b}{a}")
    return frozenset(out)


def all_bo() -> tuple[frozenset[str], ...]:
    families = {bo(i) for i in range(100)}
    return tuple(sorted(families, key=lambda group: (min(group), len(group))))


def dan_cham(digit: int) -> tuple[str, ...]:
    if not 0 <= digit <= 9:
        raise ValueError("digit must be in 0..9")
    return tuple(f"{n:02d}" for n in range(100) if digit in (n // 10, n % 10))


def dan_dau(digit: int) -> tuple[str, ...]:
    if not 0 <= digit <= 9:
        raise ValueError("digit must be in 0..9")
    return tuple(f"{digit}{d}" for d in range(10))


def dan_duoi(digit: int) -> tuple[str, ...]:
    if not 0 <= digit <= 9:
        raise ValueError("digit must be in 0..9")
    return tuple(f"{d}{digit}" for d in range(10))


def dan_tong_mod10(total: int) -> tuple[str, ...]:
    if not 0 <= total <= 9:
        raise ValueError("total must be in 0..9")
    return tuple(f"{n:02d}" for n in range(100) if digit_sum_mod10(n) == total)


def kep_bang() -> tuple[str, ...]:
    return tuple(f"{d}{d}" for d in range(10))


def kep_lech() -> tuple[str, ...]:
    return tuple(f"{d}{BONG[d]}" for d in range(10))


def sat_kep() -> tuple[str, ...]:
    return tuple(f"{a}{b}" for a in range(10) for b in range(10) if abs(a - b) == 1)


def reference_catalog() -> dict[str, object]:
    return {
        "bong": {str(k): v for k, v in BONG.items()},
        "bo_count": len(all_bo()),
        "kep_bang": list(kep_bang()),
        "kep_lech": list(kep_lech()),
        "sat_kep": list(sat_kep()),
        "touch_cardinality": {str(d): len(dan_cham(d)) for d in range(10)},
        "sum_mod10_cardinality": {str(d): len(dan_tong_mod10(d)) for d in range(10)},
    }
