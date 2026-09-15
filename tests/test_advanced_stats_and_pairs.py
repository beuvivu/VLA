"""Kiểm các bảng thống kê nâng cao vốn KHÔNG có test nào phủ.

``advanced_stats.py`` (199 lệnh) và ``pair_stats.py`` (72 lệnh) đều ở mức phủ
0 % trước tệp này, trong khi chúng sinh ra số liệu hiển thị trực tiếp. Hai bug
số liệu tìm được trong đợt rà soát đều nằm trong vùng không phủ — đó không
phải trùng hợp.

Mọi kỳ vọng ở đây đều tính TAY được từ khung dữ liệu bé ngay trong từng phép
kiểm, chứ không lấy lại kết quả của chính hàm đang kiểm.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from advanced_stats import (  # noqa: E402
    compute_cycle_stats,
    compute_daily_nhay_stats,
    compute_frequency,
    compute_head_tail_total,
    compute_lo_roi,
    compute_overdue,
    compute_special_total_overdue,
)
from pair_stats import (  # noqa: E402
    compute_pair_frequency,
    compute_reversal_pair_cooccurrence,
)


def _counts_frame(rows: list[tuple[str, dict[int, int]]]) -> pd.DataFrame:
    """Khung RỘNG: cột ``date`` cộng 100 cột đếm số lần về 0..99."""
    records = []
    for day, counts in rows:
        record: dict[str, object] = {"date": pd.Timestamp(day)}
        for number in range(100):
            record[number] = counts.get(number, 0)
        records.append(record)
    return pd.DataFrame(records)


def _two_digit_frame(rows: list[tuple[str, list[int]]]) -> pd.DataFrame:
    """Khung hai chữ số: cột ``date``, cột ``special``, rồi một cột mỗi vị trí.

    Cột ``special`` là bắt buộc chứ không phải trang trí: ``build_daily_targets``
    đọc thẳng ``df["special"]`` để dựng dãy đề, nên khung thiếu cột ấy sẽ nổ
    ``KeyError`` trước khi chạm tới phép đếm cặp. Giá trị ĐẦU TIÊN của mỗi kỳ
    đóng vai giải Đặc Biệt, và vì mọi cột khác ``date`` đều được gom vào tập lô
    nên tập lô của một kỳ đúng bằng tập các giá trị liệt kê.
    """
    width = max(len(values) for _, values in rows)
    records = []
    for day, values in rows:
        padded = list(values) + [values[-1]] * (width - len(values))
        record: dict[str, object] = {"date": pd.Timestamp(day), "special": padded[0]}
        record.update({f"p{i}": v for i, v in enumerate(padded[1:], start=1)})
        records.append(record)
    return pd.DataFrame(records)


# --- Số nháy ---------------------------------------------------------------


def test_nhay_buckets_count_days_not_occurrences() -> None:
    """``days_2`` là SỐ NGÀY con ấy về đúng hai lần, không phải tổng số lần.

    Nhầm hai đại lượng này thì một con về 2 lần trong một ngày duy nhất sẽ
    trông giống một con về 1 lần trong hai ngày khác nhau.
    """
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
    """Con chưa từng về phải ra 0 ở mọi nhóm, không phải bị bỏ khỏi bảng."""
    frame = _counts_frame([("2026-01-01", {7: 1})])
    out = compute_daily_nhay_stats(frame).set_index("value")
    assert len(out) == 100, "bảng phải phủ đủ 00-99"
    assert int(out.loc[42, "max_nhay"]) == 0
    assert int(out.loc[42, "days_1"]) == 0


# --- Hai mặt tần suất, và hai đơn vị gan -----------------------------------


def test_frequency_reports_occurrences_and_hit_draws_as_separate_columns() -> None:
    """``freq`` là tổng số LẦN về, ``days_hit`` là số KỲ có mặt.

    Một con về ba lần trong một kỳ và một con về một lần ở ba kỳ có cùng
    ``freq`` nhưng khác hẳn nhau; gộp hai cột lại là xoá mất phân biệt ấy.
    """
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
    """``compute_overdue`` đếm NGÀY LỊCH; ``compute_cycle_stats`` đếm KỲ QUAY.

    Đây là chủ ý chứ không phải mâu thuẫn bỏ quên: một bên trả lời "bao lâu rồi
    chưa về", bên kia trả lời "bỏ qua bao nhiêu kỳ". XSMB nghỉ Tết và nghỉ
    01-22/04/2020 nên hai con số ấy tách xa nhau đúng ở những đợt nghỉ. Phép
    kiểm này khoá cả hai lại: ai "sửa" một bên cho giống bên kia sẽ thấy đỏ,
    thay vì lặng lẽ làm một trong hai bảng sai.

    Cả hai dùng CÙNG một quy ước biên: đếm số đơn vị trọn vẹn nằm sau kỳ trúng
    gần nhất và trước mốc tính. Chỉ khác nhau ở đơn vị — ngày lịch với kỳ quay.
    """
    frame = _counts_frame(
        [
            ("2026-01-01", {7: 1}),
            # Nghỉ chín ngày — không có kỳ nào ở giữa.
            ("2026-01-11", {3: 1}),
            ("2026-01-12", {3: 1}),
        ]
    )

    calendar = compute_overdue(frame).set_index("value")
    draws = compute_cycle_stats(frame).set_index("value")

    # Mốc là ngày kế tiếp sau kỳ cuối (2026-01-13).
    # Ngày lịch trọn vẹn giữa 01-01 và 01-13: 01-02..01-12 = 11.
    # Kỳ quay trọn vẹn trong quãng ấy: 01-11 và 01-12 = 2.
    assert int(calendar.loc[7, "days_since_last"]) == 11
    assert int(draws.loc[7, "current_gap"]) == 2
    assert int(calendar.loc[7, "days_since_last"]) > int(draws.loc[7, "current_gap"]), (
        "nghỉ giữa chừng luôn làm bản theo ngày lịch phồng lên so với bản theo kỳ"
    )

    # Con 03 về ở chính kỳ cuối: cả hai đơn vị đều phải là 0, không lệch nhau.
    assert int(calendar.loc[3, "days_since_last"]) == 0
    assert int(draws.loc[3, "current_gap"]) == 0


# --- Đầu / Đuôi / Tổng -----------------------------------------------------


def test_total_is_head_plus_tail_modulo_ten() -> None:
    """"Tổng" của một con lô là (đầu + đuôi) chia lấy dư 10.

    Đây là quy ước miền, không phải phép cộng thường: 95 có tổng 4 chứ không
    phải 14. Quên phép chia dư thì cột Tổng nhận giá trị 10-18, vốn không tồn
    tại trong miền.
    """
    frame = _two_digit_frame([("2026-01-01", [95, 52, 7, 88])])
    head, tail, total = compute_head_tail_total(frame)

    assert dict(zip(head["head"], head["count"], strict=True))[9] == 1  # 95 -> đầu 9
    assert dict(zip(tail["tail"], tail["count"], strict=True))[5] == 1  # 95 -> đuôi 5

    totals = dict(zip(total["total"], total["count"], strict=True))
    # 95 -> (9+5)%10 = 4 ; 52 -> 7 ; 07 -> 7 ; 88 -> 6
    assert totals[4] == 1
    assert totals[7] == 2
    assert totals[6] == 1
    assert max(total["total"]) <= 9, "Tổng phải nằm trong 0-9"


# --- Lô rơi ----------------------------------------------------------------


def test_lo_roi_separates_total_occurrences_from_distinct_days() -> None:
    """``count_in_window`` đếm LẦN về, ``days_in_window`` đếm NGÀY về.

    Một con về hai lần trong CÙNG một kỳ khác hẳn một con về một lần ở hai kỳ
    khác nhau, dù tổng số lần bằng nhau.
    """
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
    """``window_draws`` cắt theo SỐ KỲ gần nhất, kể cả khi lịch có lỗ hổng."""
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


# --- Tổng Đặc Biệt và chạm Đặc Biệt ----------------------------------------------------


def test_special_total_and_cham_read_only_the_last_two_digits() -> None:
    """Tổng Đặc Biệt và chạm Đặc Biệt đều tính trên HAI SỐ CUỐI của giải Đặc Biệt."""
    raw = pd.DataFrame(
        [
            {"date": "2026-01-01", "special": 12395},  # hai số cuối 95 -> tổng 4
            {"date": "2026-01-05", "special": 90052},  # hai số cuối 52 -> tổng 7
        ]
    )
    total_df, cham_df = compute_special_total_overdue(raw)

    totals = total_df.set_index("total")
    assert str(totals.loc[4, "last_seen"]) == "2026-01-01"
    assert int(totals.loc[4, "days_since_last"]) == 4
    assert str(totals.loc[7, "last_seen"]) == "2026-01-05"
    assert int(totals.loc[7, "days_since_last"]) == 0

    cham = cham_df.set_index("digit")
    # 95 chạm 9 và 5; 52 chạm 5 và 2. Chữ số 5 có ở cả hai kỳ -> gan 0.
    assert int(cham.loc[5, "days_since_last"]) == 0
    assert int(cham.loc[9, "days_since_last"]) == 4
    assert pd.isna(cham.loc[7, "days_since_last"]), "chữ số chưa từng chạm phải để trống"


# --- Cặp lộn ---------------------------------------------------------------


def test_reverse_pair_cooccurrence_requires_BOTH_members() -> None:
    """Cặp lộn "cùng về" nghĩa là CẢ HAI con cùng có mặt trong một kỳ.

    Khác hẳn định nghĩa "cặp về" của bảng gan, vốn là MỘT TRONG HAI. Lẫn hai
    định nghĩa này từng làm 50 cặp báo "chưa từng về" suốt 2 394 kỳ.
    """
    frame = _two_digit_frame(
        [
            ("2026-01-01", [12, 21, 34]),  # 12 và 21 cùng về
            ("2026-01-02", [12, 55, 66]),  # chỉ 12
        ]
    )
    out = compute_reversal_pair_cooccurrence(frame).set_index("a")

    assert int(out.loc[12, "cooccur"]) == 1, "chỉ kỳ đầu có cả hai"
    assert int(out.loc[12, "days"]) == 2, "mẫu số là mọi kỳ, không phải số kỳ trúng"
    assert float(out.loc[12, "rate"]) == 0.5, "tỷ lệ là cùng-về / tổng số kỳ"
    assert int(out.loc[34, "cooccur"]) == 0, "43 không hề về"


def test_reverse_pair_table_covers_the_forty_five_non_double_pairs() -> None:
    """Chỉ 45 cặp đảo thật; số kép (11, 22, ...) đảo lại chính nó nên bị loại."""
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
    """Một kỳ có k con KHÁC NHAU sinh ra đúng k*(k-1)/2 cặp, mỗi cặp một lần.

    Trùng lặp trong cùng một kỳ không được nhân đôi cặp: 11 về hai lần vẫn chỉ
    là một con trong tập của kỳ đó.
    """
    frame = _two_digit_frame(
        [
            ("2026-01-01", [11, 11, 22, 33]),  # tập {11, 22, 33} -> 3 cặp
            ("2026-01-02", [11, 22, 44]),  # tập {11, 22, 44} -> 3 cặp
        ]
    )
    out = compute_pair_frequency(frame)
    counts = {(int(r["x"]), int(r["y"])): int(r["count"]) for _, r in out.iterrows()}

    assert counts[(11, 22)] == 2, "cặp này có ở cả hai kỳ"
    assert counts[(11, 33)] == 1
    assert counts[(22, 44)] == 1
    assert (33, 44) not in counts, "hai con chưa từng cùng một kỳ"
    assert sum(counts.values()) == 6


@pytest.mark.parametrize("frame", [pd.DataFrame(), pd.DataFrame(columns=["date"])])
def test_empty_input_returns_an_empty_table_instead_of_raising(frame: pd.DataFrame) -> None:
    """Kho rỗng là trạng thái hợp lệ lúc dựng lần đầu, không phải lỗi."""
    assert compute_daily_nhay_stats(frame).empty
    assert compute_lo_roi(frame).empty
