from __future__ import annotations


import numpy as np
import pandas as pd
import pytest

from research.crosslag_positional_lab import RuleSpec, _date_row_lookup, _next_payload


def _dates(count: int) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.date_range("2015-01-01", periods=count, freq="D"))


def test_the_lookup_maps_every_date_to_its_own_row() -> None:
    dates = _dates(50)
    lookup = _date_row_lookup(dates)
    assert len(lookup) == 50
    for index, stamp in enumerate(dates):
        assert lookup[pd.Timestamp(stamp).normalize()] == index


def test_the_lookup_normalises_so_a_timestamp_with_a_clock_still_matches() -> None:
    stamps = pd.DatetimeIndex(["2015-01-01 13:45", "2015-01-02 07:00"])
    lookup = _date_row_lookup(stamps)
    assert lookup[pd.Timestamp("2015-01-01")] == 0
    assert lookup[pd.Timestamp("2015-01-02")] == 1


@pytest.mark.parametrize("op", ["concat", "lon", "bo", "cham", "tong"])
def test_passing_the_lookup_in_gives_the_same_answer_as_building_it_inside(op) -> None:
    dates = _dates(40)
    rng = np.random.default_rng(0)
    tails = rng.integers(0, 10, size=(40, 27)).astype(np.int16)
    rule = RuleSpec(op=op, position_a=0, position_b=1, lag_a=1, lag_b=2)

    hoisted = _next_payload(rule, dates=dates, tails=tails, lookup=_date_row_lookup(dates))
    inline = _next_payload(rule, dates=dates, tails=tails)
    assert hoisted == inline


def test_it_builds_the_lookup_once_not_once_per_rule() -> None:
    from research import crosslag_positional_lab as lab

    dates = _dates(30)
    rng = np.random.default_rng(1)
    tails = rng.integers(0, 10, size=(30, 27)).astype(np.int16)
    rules = [
        RuleSpec(op="concat", position_a=i % 27, position_b=1, lag_a=1, lag_b=2)
        for i in range(25)
    ]

    calls = 0
    original = lab._date_row_lookup

    def counting(argument):
        nonlocal calls
        calls += 1
        return original(argument)

    lab._date_row_lookup = counting
    try:
        shared = lab._date_row_lookup(dates)
        for rule in rules:
            lab._next_payload(rule, dates=dates, tails=tails, lookup=shared)
    finally:
        lab._date_row_lookup = original

    assert calls == 1, (
        f"dựng bảng tra {calls} lần cho {len(rules)} luật; truyền lookup vào thì "
        "phải dựng đúng một lần"
    )
