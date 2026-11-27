from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stats.advanced_stats import (  # noqa: E402
    compute_cycle_stats,
    compute_daily_nhay_stats,
    compute_frequency,
    compute_head_tail_total,
    compute_lo_roi,
    compute_overdue,
    compute_special_total_overdue,
)
from stats.pair_stats import (  # noqa: E402
    compute_pair_frequency,
    compute_reversal_pair_cooccurrence,
)


def _counts_frame(rows: list[tuple[str, dict[int, int]]]) -> pd.DataFrame:
    records = []
    for day, counts in rows:
        record: dict[str, object] = {"date": pd.Timestamp(day)}
        for number in range(100):
            record[number] = counts.get(number, 0)
        records.append(record)
    return pd.DataFrame(records)


def _two_digit_frame(rows: list[tuple[str, list[int]]]) -> pd.DataFrame:
    width = max(len(values) for _, values in rows)
    records = []
    for day, values in rows:
        padded = list(values) + [values[-1]] * (width - len(values))
        record: dict[str, object] = {"date": pd.Timestamp(day), "special": padded[0]}
        record.update({f"p{i}": v for i, v in enumerate(padded[1:], start=1)})
        records.append(record)
    return pd.DataFrame(records)


def test_nhay_buckets_count_days_not_occurrences() -> None:
    frame = _counts_frame(
        [
            ("2026-01-01", {7: 2, 3: 1}),
            ("2026-01-02", {7: 1, 3: 4}),
            ("2026-01-03", {7: 3}),
        ]
    )
    out = compute_daily_nhay_stats(frame).set_index("value")

    seven = out.loc[7]
    assert (int(seven["days_1"]), int(seven["days_2"]), int(seven["days_3"])) == (1, 1, 1)
    assert int(seven["days_4_plus"]) == 0
    assert int(seven["max_nhay"]) == 3

    three = out.loc[3]
    assert int(three["days_1"]) == 1
    assert int(three["days_4_plus"]) == 1, "về 4 lần trong một ngày phải rơi vào nhóm 4+"
    assert int(three["max_nhay"]) == 4


def test_a_number_that_never_appears_has_every_bucket_at_zero() -> None:
    frame = _counts_frame([("2026-01-01", {7: 1})])
    out = compute_daily_nhay_stats(frame).set_index("value")
    assert len(out) == 100, "bảng phải phủ đủ 00-99"
    assert int(out.loc[42, "max_nhay"]) == 0
    assert int(out.loc[42, "days_1"]) == 0


def test_frequency_reports_occurrences_and_hit_draws_as_separate_columns() -> None:
    frame = _counts_frame(
        [
            ("2026-01-01", {7: 3, 3: 1}),
            ("2026-01-02", {3: 1}),
            ("2026-01-03", {3: 1}),
        ]
    )
    out = compute_frequency(frame, window_days=365).set_index("value")

    assert (int(out.loc[7, "freq"]), int(out.loc[7, "days_hit"])) == (3, 1)
    assert (int(out.loc[3, "freq"]), int(out.loc[3, "days_hit"])) == (3, 3)
    assert int(out.loc[7, "max_nhay"]) == 3
    assert int(out.loc[3, "max_nhay"]) == 1


def test_the_two_overdue_facades_keep_deliberately_different_units() -> None:
    frame = _counts_frame(
        [
            ("2026-01-01", {7: 1}),
            ("2026-01-11", {3: 1}),
            ("2026-01-12", {3: 1}),
        ]
    )

    calendar = compute_overdue(frame).set_index("value")
    draws = compute_cycle_stats(frame).set_index("value")

    assert int(calendar.loc[7, "days_since_last"]) == 11
    assert int(draws.loc[7, "current_gap"]) == 2
    assert int(calendar.loc[7, "days_since_last"]) > int(draws.loc[7, "current_gap"]), (
        "nghỉ giữa chừng luôn làm bản theo ngày lịch phồng lên so với bản theo kỳ"
    )

    assert int(calendar.loc[3, "days_since_last"]) == 0
    assert int(draws.loc[3, "current_gap"]) == 0


def test_total_is_head_plus_tail_modulo_ten() -> None:
    frame = _two_digit_frame([("2026-01-01", [95, 52, 7, 88])])
    head, tail, total = compute_head_tail_total(frame)

    assert dict(zip(head["head"], head["count"], strict=True))[9] == 1
    assert dict(zip(tail["tail"], tail["count"], strict=True))[5] == 1

    totals = dict(zip(total["total"], total["count"], strict=True))
    assert totals[4] == 1
    assert totals[7] == 2
    assert totals[6] == 1
    assert max(total["total"]) <= 9, "Tổng phải nằm trong 0-9"


def test_lo_roi_separates_total_occurrences_from_distinct_days() -> None:
    frame = _two_digit_frame(
        [
            ("2026-01-01", [11, 11, 22]),
            ("2026-01-02", [22, 33, 44]),
        ]
    )
    out = compute_lo_roi(frame, window_draws=7).set_index("value")

    assert int(out.loc[11, "count_in_window"]) == 2
    assert int(out.loc[11, "days_in_window"]) == 1, "hai lần nhưng trong MỘT kỳ"

    assert int(out.loc[22, "count_in_window"]) == 2
    assert int(out.loc[22, "days_in_window"]) == 2, "hai lần ở HAI kỳ"

    assert 33 not in out.index, "về đúng một lần thì không phải lô rơi"


def test_lo_roi_window_counts_draws_not_calendar_days() -> None:
    frame = _two_digit_frame(
        [
            ("2026-01-01", [11, 11]),
            ("2026-02-01", [22, 22]),
            ("2026-02-02", [33, 33]),
        ]
    )
    out = compute_lo_roi(frame, window_draws=2).set_index("value")
    assert 11 not in out.index, "kỳ đầu nằm ngoài cửa sổ hai kỳ"
    assert int(out.loc[22, "count_in_window"]) == 2
    assert int(out.loc[33, "count_in_window"]) == 2


def test_special_total_and_cham_read_only_the_last_two_digits() -> None:
    raw = pd.DataFrame(
        [
            {"date": "2026-01-01", "special": 12395},
            {"date": "2026-01-05", "special": 90052},
        ]
    )
    total_df, cham_df = compute_special_total_overdue(raw)

    totals = total_df.set_index("total")
    assert str(totals.loc[4, "last_seen"]) == "2026-01-01"
    assert int(totals.loc[4, "days_since_last"]) == 4
    assert str(totals.loc[7, "last_seen"]) == "2026-01-05"
    assert int(totals.loc[7, "days_since_last"]) == 0

    cham = cham_df.set_index("digit")
    assert int(cham.loc[5, "days_since_last"]) == 0
    assert int(cham.loc[9, "days_since_last"]) == 4
    assert pd.isna(cham.loc[7, "days_since_last"]), "chữ số chưa từng chạm phải để trống"


def test_reverse_pair_cooccurrence_requires_BOTH_members() -> None:
    frame = _two_digit_frame(
        [
            ("2026-01-01", [12, 21, 34]),
            ("2026-01-02", [12, 55, 66]),
        ]
    )
    out = compute_reversal_pair_cooccurrence(frame).set_index("a")

    assert int(out.loc[12, "cooccur"]) == 1, "chỉ kỳ đầu có cả hai"
    assert int(out.loc[12, "days"]) == 2, "mẫu số là mọi kỳ, không phải số kỳ trúng"
    assert float(out.loc[12, "rate"]) == 0.5, "tỷ lệ là cùng-về / tổng số kỳ"
    assert int(out.loc[34, "cooccur"]) == 0, "43 không hề về"


def test_reverse_pair_table_covers_the_forty_five_non_double_pairs() -> None:
    frame = _two_digit_frame([("2026-01-01", [12, 21])])
    out = compute_reversal_pair_cooccurrence(frame)
    assert len(out) == 45
    assert all(
        a < b for a, b in zip(out["a"], out["b"], strict=True)
    ), "phải là cặp không thứ tự"
    assert all(
        a % 11 != 0 for a in out["a"]
    ), "số kép đảo lại chính nó nên không có mặt"


def test_pair_frequency_counts_each_unordered_pair_once_per_draw() -> None:
    frame = _two_digit_frame(
        [
            ("2026-01-01", [11, 11, 22, 33]),
            ("2026-01-02", [11, 22, 44]),
        ]
    )
    out = compute_pair_frequency(frame)
    counts = {(int(r["x"]), int(r["y"])): int(r["count"]) for _, r in out.iterrows()}

    assert counts[(11, 22)] == 2, "cặp này có ở cả hai kỳ"
    assert counts[(11, 33)] == 1
    assert counts[(22, 44)] == 1
    assert (33, 44) not in counts, "hai con chưa từng cùng một kỳ"
    assert sum(counts.values()) == 6


def test_pairs_tied_on_count_are_listed_by_pair_number() -> None:
    frame = _two_digit_frame(
        [
            ("2026-01-01", [90, 80]),
            ("2026-01-02", [70, 60]),
            ("2026-01-03", [50, 40]),
            ("2026-01-04", [33, 61]),
            ("2026-01-05", [33, 61]),
        ]
    )
    out = compute_pair_frequency(frame)
    assert out["pair"].tolist() == ["33-61", "40-50", "60-70", "80-90"]


@pytest.mark.parametrize("frame", [pd.DataFrame(), pd.DataFrame(columns=["date"])])
def test_empty_input_returns_an_empty_table_instead_of_raising(frame: pd.DataFrame) -> None:
    assert compute_daily_nhay_stats(frame).empty
    assert compute_lo_roi(frame).empty
