"""Quy tắc tổng – bóng – chạm phải ra ĐÚNG từng con số mà loạt bài tuần đã in.

Ba kỳ gốc, chép nguyên từ ``data/xsmb.csv`` để phép kiểm không phụ thuộc dữ
liệu tải về sau. Số mong đợi là số in trong bài (dạng ``xyx`` = ``xy`` và ``yx``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import digit_sum_rules as r
from xsmb_domain import FIELD_WIDTHS

COLUMNS = [field for field, _ in FIELD_WIDTHS]
ROWS = {
    "2026-09-27": [55473, 64870, 68612, 77718, 52620, 19062, 416, 15268, 86933, 43655, 2733, 3480,
                   8327, 4199, 674, 566, 5241, 4304, 1545, 9354, 280, 841, 911, 70, 34, 24, 41],
    "2026-10-01": [40208, 92635, 24807, 62639, 16892, 82700, 92965, 40504, 68709, 38492, 6537, 7453,
                   7691, 9434, 3349, 1896, 5752, 6691, 6935, 4650, 390, 655, 395, 50, 15, 7, 4],
    "2026-10-04": [82951, 28235, 82614, 47824, 33386, 23385, 9503, 43582, 60243, 4348, 2251, 1053,
                   3431, 9308, 3969, 7927, 5509, 2889, 4781, 1038, 237, 580, 604, 90, 89, 26, 59],
}


def _row(day: str) -> pd.Series:
    return pd.Series(dict(zip(COLUMNS, ROWS[day], strict=True), date=day))


def _xyx(*codes: str) -> list[int]:
    """``"676"`` → [67, 76]; ``"030"`` → [3, 30]; ``"88"`` → [88]."""
    out: set[int] = set()
    for code in codes:
        out.update({int(code[:2]), int(code[1:])} if len(code) == 3 else {int(code)})
    return sorted(out)


@pytest.mark.parametrize(
    "day, dau, duoi, cham",
    [
        # 28-09: "tổng 2 số cuối ĐB 73 → 0, bóng 5"; "2 số đầu 55 → 0"; "giải nhất 70 → 7, bóng 2"
        ("2026-09-27", [0, 5], [0, 5], [2, 7]),
        # 02-10: chỉ in chạm — "giải nhất 35 → 8, bóng 3"
        ("2026-10-01", None, None, [3, 8]),
        # 05-10: "51 → 6, bóng 1"; "82 → 0, bóng 5"; "35 → 8, bóng 3"
        ("2026-10-04", [1, 6], [0, 5], [3, 8]),
    ],
)
def test_head_tail_and_touch_digits_match_the_articles(day, dau, duoi, cham) -> None:
    row = _row(day)
    if dau is not None:
        assert r.dau_db(row) == dau
        assert r.duoi_db(row) == duoi
    assert r.cham(row) == cham


def test_touch_set_is_every_touch_paired_both_ways_with_the_first_three_special_digits() -> None:
    # 28-09: "Chạm 2: 252 – 202 – 242 – 292; Chạm 7: 757 – 707 – 747 – 797" (ĐB 55473).
    assert r.dan_cham(_row("2026-09-27")) == _xyx(
        "252", "202", "242", "292", "757", "707", "747", "797")
    # 02-10: "Chạm 8: 848 – 898 – 808 – 858 – 828 – 878; Chạm 3: 343 – 393 – 303 – 353 – 323 – 373".
    assert r.dan_cham(_row("2026-10-01")) == _xyx(
        "848", "898", "808", "858", "828", "878", "343", "393", "303", "353", "323", "373")


@pytest.mark.parametrize(
    "day, g5, vip",
    [
        ("2026-09-27", "545", "030"),  # 0566 → 05 tổng 5; 4304 → 04 tổng 4; 68612 → 12 tổng 3; 64870 → 64 tổng 0
        ("2026-10-01", "909", "171"),  # 1896 → 18 tổng 9; 6691 → 91 tổng 0; 24807 → 07 tổng 7; 92635 → 92 tổng 1
        ("2026-10-04", "676", "050"),  # 7927 → 79 tổng 6; 2889 → 89 tổng 7; 82614 → 14 tổng 5; 28235 → 28 tổng 0
    ],
)
def test_loto_pairs_match_the_articles(day, g5, vip) -> None:
    row = _row(day)
    assert r.lo_g5(row) == _xyx(g5)
    assert r.lo_vip(row) == _xyx(vip)


def test_previous_draw_summary_is_counted_from_the_board() -> None:
    """Kỳ 04-10: bài in nháy 51, 89; về cả cặp 080, 090, 353; câm đầu 7; đầu 8, đuôi 9 nhiều nhất."""
    s = r.tong_hop_ky(_row("2026-10-04"))
    assert (s["de"], s["de_dau"], s["de_duoi"], s["de_tong"]) == ("51", 5, 1, 6)
    assert s["lo_kep"] == []
    assert s["lo_nhay"] == {"51": 2, "89": 2}
    assert s["lo_ca_cap"] == [8, 9, 35]
    assert (s["cam_dau"], s["cam_duoi"]) == ([7], [])
    assert (s["dau_nhieu_nhat"], s["duoi_nhieu_nhat"]) == ([8], [9])


def test_zero_padding_follows_each_prize_width() -> None:
    """G5 ``566`` là ``0566``: bỏ số 0 đầu thì 2 số đầu thành 56 và cặp lô sai."""
    assert r.giai(_row("2026-09-27"), "prize5_2") == "0566"
    assert r.giai(_row("2026-10-04"), "special") == "82951"


def _history(days: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = {field: rng.integers(0, 10**width, size=days) for field, width in FIELD_WIDTHS}
    data["date"] = pd.date_range("2020-01-06", periods=days, freq="D").strftime("%Y-%m-%d")
    return pd.DataFrame(data)


def test_backtest_expectation_is_the_exact_chance_of_a_same_size_random_pick() -> None:
    raw = _history(400, seed=3)
    rows = {row["rule"]: row for row in r.backtest(raw)}
    assert rows["dau_db"]["expected_rate"] == pytest.approx(0.2)
    assert rows["duoi_db"]["expected_rate"] == pytest.approx(0.2)
    # Cặp lộn khác nhau: 1 − 0,98²⁷; cặp kép chỉ một số: 1 − 0,99²⁷ — trung bình nằm giữa.
    assert 1 - 0.99**27 < rows["lo_g5"]["expected_rate"] <= 1 - 0.98**27
    # Lịch sử ngẫu nhiên: không quy tắc nào được lệch khỏi chọn bừa quá xa.
    assert all(abs(row["z"]) < 4 for row in rows.values())


def test_backtest_finds_a_rule_that_really_works() -> None:
    """Phép đo không mù: cài để đầu ĐB kỳ sau LUÔN là tổng 2 số cuối ĐB kỳ trước."""
    raw = _history(400, seed=4)
    special = raw["special"].to_numpy().copy()
    for t in range(1, len(special)):
        head = r.tong(f"{special[t - 1]:05d}"[-2:])
        special[t] = special[t] // 100 * 100 + head * 10 + special[t] % 10
    raw["special"] = special
    rows = {row["rule"]: row for row in r.backtest(raw)}
    assert rows["dau_db"]["hit_rate"] == pytest.approx(1.0)
    assert rows["dau_db"]["z"] > 20


def test_frame_scoring_counts_a_week_as_won_by_a_single_hit() -> None:
    """Khung 7 kỳ: hai chữ số đầu "nổ" với xác suất 1 − 0,8⁷ ngay cả khi chọn bừa."""
    rows = {row["rule"]: row for row in r.frame_backtest(_history(700, seed=5))}
    assert rows["dau_db"]["expected_rate"] == pytest.approx(1 - 0.8**7)
    assert rows["dau_db"]["frames"] == 99  # mỗi Chủ Nhật có đủ khung 7 kỳ phía sau
    # Dàn chạm mở hai khung mỗi tuần: Chủ Nhật → thứ Hai–Năm, thứ Năm → thứ Sáu–Chủ Nhật.
    assert rows["dan_cham"]["frames"] == 199
