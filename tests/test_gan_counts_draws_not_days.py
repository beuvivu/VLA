"""Gan phải đếm theo KỲ QUAY, không theo ngày lịch.

XSMB nghỉ Tết hằng năm và nghỉ 01-22/04/2020. Đếm theo ngày lịch thì mọi con
lô đều bị cộng thêm đúng số ngày nghỉ ngay sau mỗi đợt — một con vừa về cách
đây hai kỳ có thể hiện thành "gan 25 ngày".

Trang lo-gan.html đếm theo kỳ và nói rõ điều đó ngay trên trang, nhưng bảng
``loto_rhythm.csv`` nuôi bốn builder khác lại lấy cột ``*_calendar_days``.
Hai mặt cùng một khái niệm mà lệch định nghĩa thì luôn có một mặt sai.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from advanced_stats import compute_cycle_stats  # noqa: E402
from gap_cycle_stats import compute_gap_stats  # noqa: E402


def _sparse(rows: list[tuple[str, list[int]]]) -> pd.DataFrame:
    """Dựng khung lịch sử RỘNG: cột ``date`` cộng 100 cột đếm lần về 0..99."""
    records = []
    for day, numbers in rows:
        record: dict[str, object] = {"date": day}
        for number in range(100):
            record[number] = numbers.count(number)
        records.append(record)
    return pd.DataFrame(records)


def test_current_gap_counts_draws_across_a_suspension() -> None:
    """Một đợt nghỉ dài không được làm gan phồng lên.

    Lịch có bốn kỳ: 01/01, 02/01, rồi nghỉ 20 ngày, rồi 22/01 và 23/01.
    Con 7 về lần cuối ở kỳ thứ hai, sau đó còn HAI kỳ nữa trôi qua.

    Gan đúng = 2 kỳ. Đếm theo ngày lịch sẽ ra 20 — gấp mười lần.
    """
    frame = _sparse(
        [
            ("2020-01-01", [7, 1]),
            ("2020-01-02", [7, 2]),
            ("2020-01-22", [3]),
            ("2020-01-23", [4]),
        ]
    )
    cycle = compute_cycle_stats(frame).set_index("value")
    assert int(cycle.loc[7, "current_gap"]) == 2

    # Cùng dữ liệu, cột lịch của API gốc cho con số phồng — đây chính là thứ
    # bảng này từng lấy nhầm.
    cutoff = pd.Timestamp("2020-01-24")
    canonical = compute_gap_stats(frame, cutoff).set_index("number")
    assert int(canonical.loc[7, "current_gap_draws"]) == 2
    assert int(canonical.loc[7, "current_gap_calendar_days"]) == 21


def test_interval_columns_are_in_draws_too() -> None:
    """min/mean/max phải cùng ĐƠN VỊ với current_gap.

    Trộn một cột theo kỳ với ba cột theo ngày thì bốn con số cạnh nhau trong
    cùng một hàng không so sánh được với nhau.
    """
    frame = _sparse(
        [
            ("2020-01-01", [7]),
            ("2020-01-02", [0]),
            ("2020-01-03", [7]),
            ("2020-01-25", [7]),
            ("2020-01-26", [0]),
        ]
    )
    cycle = compute_cycle_stats(frame).set_index("value")
    # Con 7 về ở kỳ 1, 3, 4 -> khoảng cách theo KỲ là 2 và 1.
    assert float(cycle.loc[7, "min_gap"]) == 1.0
    assert float(cycle.loc[7, "max_gap"]) == 2.0
    assert float(cycle.loc[7, "mean_gap"]) == 1.5


def test_published_rhythm_table_matches_a_draw_count_recomputation() -> None:
    """Bảng đã sinh phải khớp phép đếm theo kỳ tính lại từ dữ liệu gốc."""
    rhythm = ROOT / "data" / "advanced" / "loto_rhythm.csv"
    raw = ROOT / "data" / "xsmb.csv"
    if not (rhythm.exists() and raw.exists()):
        return

    widths = [("special", 5), ("prize1", 5), ("prize2_1", 5), ("prize2_2", 5)]
    widths += [(f"prize3_{i}", 5) for i in range(1, 7)]
    widths += [(f"prize4_{i}", 4) for i in range(1, 5)]
    widths += [(f"prize5_{i}", 4) for i in range(1, 7)]
    widths += [(f"prize6_{i}", 3) for i in range(1, 4)]
    widths += [(f"prize7_{i}", 2) for i in range(1, 5)]

    draws = pd.read_csv(raw, dtype=str).sort_values("date").reset_index(drop=True)
    per_draw = [
        {int(str(row[field]).strip().zfill(width)[-2:]) for field, width in widths}
        for _, row in draws.iterrows()
    ]
    total = len(per_draw)
    expected = {}
    for number in range(100):
        seen = [i for i, s in enumerate(per_draw) if number in s]
        if seen:
            expected[number] = total - seen[-1] - 1

    table = pd.read_csv(rhythm)
    table = table[table["mode"] == "loto"]
    mismatched = [
        (int(r["number"]), int(r["current_gap"]), expected[int(r["number"])])
        for _, r in table.iterrows()
        if int(r["number"]) in expected and int(r["current_gap"]) != expected[int(r["number"])]
    ]
    assert not mismatched, f"gan đã sinh lệch phép đếm theo kỳ: {mismatched[:5]}"


# --- Hai hàm cùng tên tham số, hai đơn vị khác nhau -------------------------


def test_the_two_recency_weightings_use_different_units_on_purpose() -> None:
    """``half_life_days`` mang hai nghĩa ở hai nơi — neo cả hai lại.

    ``learn_ensemble_weights._day_weights`` đếm theo SỐ KỲ (khoảng cách chỉ số
    hàng); ``meta_predictor._recency_row_weights`` đếm theo NGÀY LỊCH thật. Đo
    trên lịch sử hiện có: đặt nửa đời 30 thì hai cách cho trọng số lệch trung
    vị 9,6 % và tối đa 44,6 %, nên nhầm lẫn giữa chúng không hề vô hại.

    Phép kiểm này không phán cách nào đúng — nó chỉ chặn việc một người sửa
    một hàm theo hiểu biết về hàm kia.
    """

    from learn_ensemble_weights import _day_weights
    from meta_predictor import _recency_row_weights

    # Bốn kỳ, nhưng kỳ cuối cách kỳ trước đó 20 NGÀY.
    days = ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-23"]

    by_draw = _day_weights(days, 2)
    # Đếm theo kỳ: tuổi là 3, 2, 1, 0 -> tỉ lệ giữa hai kỳ liền nhau luôn như nhau.
    assert by_draw[-1] / by_draw[-2] == pytest.approx(2 ** (1 / 2), rel=1e-9)

    by_calendar = _recency_row_weights(pd.Series(days), 2.0)
    # Đếm theo lịch: kỳ áp chót cách 20 ngày nên bị phạt nặng hơn hẳn, tới mức
    # chạm sàn 0,05 mà hàm kia không hề có.
    assert by_calendar[-1] / by_calendar[-2] > 10.0


def test_shipped_rhythm_builder_also_counts_draws() -> None:
    """``_rhythm_from_sparse`` là hàm THẬT SỰ ghi ra loto_rhythm.csv.

    Phép kiểm đối chiếu bảng đã sinh ở trên không đủ để canh nó: hôm nay lịch
    sử không có đợt nghỉ nào gần đây nên đếm theo lịch và theo kỳ trùng nhau,
    và một phép kiểm chỉ đỏ khi hai cách tình cờ lệch thì không canh gì cả.

    Ở đây dựng hẳn một đợt nghỉ 20 ngày để hai cách buộc phải khác nhau.
    """
    from statistical_matrices import _rhythm_from_sparse

    frame = _sparse(
        [
            ("2020-01-01", [7]),
            ("2020-01-02", [0]),
            ("2020-01-03", [0]),
            ("2020-01-23", [0]),
        ]
    )
    out = _rhythm_from_sparse(frame, mode="loto").set_index("number")

    # Con 7 về ở kỳ đầu; sau đó còn ba kỳ nữa -> gan 3 KỲ, không phải 22 ngày.
    assert int(out.loc[7, "current_gap"]) == 3

    # Con 0 về ở kỳ 2, 3, 4 -> khoảng cách theo KỲ là 1 và 1, không phải 1 và 20.
    assert out.loc[0, "last_10_intervals"] == "1|1"
    assert int(out.loc[0, "max_gap"]) == 1

    # rhythm_pressure là current_gap / mean_gap: chỉ có nghĩa khi cùng đơn vị.
    assert float(out.loc[0, "rhythm_pressure"]) == pytest.approx(0.0)
