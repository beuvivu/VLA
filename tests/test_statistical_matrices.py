from __future__ import annotations

import pandas as pd

from statistical_matrices import (
    _de_sparse_from_raw,
    _period_frequency_from_sparse,
    _prepare_sparse,
    _reverse_pair_frequency,
    _rhythm_from_sparse,
    _special_boards,
)


def test_period_frequency_preserves_00_label() -> None:
    sparse = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02"],
            "0": [1, 0],
            "1": [0, 2],
        }
    )
    df = _period_frequency_from_sparse(_prepare_sparse(sparse), period="day", mode="loto")
    row = df[(df["period_key"] == "2026-01-01") & (df["number"] == 0)].iloc[0]
    assert row["number_str"] == "00"
    assert int(row["freq"]) == 1


def test_special_boards_week_and_month() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2026-01-05", "2026-01-06"],  # Monday, Tuesday
            "special": [12304, 9007],
        }
    )
    week_board, month_board, year_freq, month_freq = _special_boards(raw)
    assert "T2" in week_board.columns
    assert week_board.iloc[-1]["T2"] == "04"
    assert week_board.iloc[-1]["T3"] == "07"
    assert month_board.iloc[-1]["05"] == "04"
    assert month_board.iloc[-1]["06"] == "07"
    assert set(year_freq["number_str"]) == {"04", "07"}
    assert set(month_freq["number_str"]) == {"04", "07"}


def test_de_sparse_and_rhythm() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "special": [10000, 10001, 10000],
        }
    )
    de_sparse = _de_sparse_from_raw(raw)
    assert int(de_sparse.loc[0, 0]) == 1
    assert int(de_sparse.loc[1, 1]) == 1
    rhythm = _rhythm_from_sparse(de_sparse, mode="de")
    zero = rhythm[rhythm["number_str"] == "00"].iloc[0]
    assert int(zero["current_gap"]) == 0
    assert int(zero["hit_count"]) == 2


def test_reverse_pair_frequency_uses_kep_bong_instead_of_self_pairs() -> None:
    sparse = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02"],
            "22": [1, 0],
            "77": [0, 1],
            "13": [1, 0],
            "31": [0, 1],
        }
    )
    out = _reverse_pair_frequency(_prepare_sparse(sparse), period="day")

    # One canonical 50-pair row per family and date; no double can become AA-AA.
    assert len(out) == 100
    assert "77-77" not in set(out["pair"])
    assert set(out["pair"]) >= {"22-77", "13-31"}

    kep_bong = out[out["pair"] == "22-77"].sort_values("period_key")
    assert kep_bong["freq"].tolist() == [1, 1]
    assert kep_bong["days_hit"].tolist() == [1, 1]
    assert kep_bong["cooccur_days"].tolist() == [0, 0]


def test_reverse_pair_frequency_has_all_five_kep_bong_families() -> None:
    sparse = pd.DataFrame(
        {
            "date": ["2026-01-01"],
            "00": [1],
            "11": [1],
            "22": [1],
            "33": [1],
            "44": [1],
            "55": [0],
            "66": [0],
            "77": [0],
            "88": [0],
            "99": [0],
        }
    )
    out = _reverse_pair_frequency(_prepare_sparse(sparse), period="day")
    pairs = set(out["pair"])
    expected = {
        "00": "00-55",
        "11": "11-66",
        "22": "22-77",
        "33": "33-88",
        "44": "44-99",
    }
    assert set(expected.values()) <= pairs
    for source, pair in expected.items():
        row = out[out["pair"] == pair].iloc[0]
        assert int(row["freq"]) == 1, source
