from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from dtos import Result


def _valid_kwargs() -> dict[str, object]:
    return {
        "date": date(2026, 9, 1),
        "special": 0,
        "prize1": 99999,
        "prize2_1": 0,
        "prize2_2": 99999,
        "prize3_1": 1,
        "prize3_2": 2,
        "prize3_3": 3,
        "prize3_4": 4,
        "prize3_5": 5,
        "prize3_6": 99999,
        "prize4_1": 0,
        "prize4_2": 9999,
        "prize4_3": 1,
        "prize4_4": 2,
        "prize5_1": 3,
        "prize5_2": 4,
        "prize5_3": 5,
        "prize5_4": 6,
        "prize5_5": 7,
        "prize5_6": 9999,
        "prize6_1": 0,
        "prize6_2": 1,
        "prize6_3": 999,
        "prize7_1": 0,
        "prize7_2": 1,
        "prize7_3": 98,
        "prize7_4": 99,
    }


def test_valid_integer_representation_including_leading_zero_values():
    result = Result(**_valid_kwargs())
    assert result.special == 0
    assert result.prize7_1 == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("special", -1),
        ("special", 100000),
        ("prize4_1", 10000),
        ("prize6_1", 1000),
        ("prize7_1", 100),
    ],
)
def test_out_of_range_prize_values_are_rejected(field: str, value: int):
    kwargs = _valid_kwargs()
    kwargs[field] = value
    with pytest.raises(ValidationError):
        Result(**kwargs)
