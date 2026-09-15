"""Kiểm hệ 50 cặp LOTO — module trước đó ở mức phủ 0 %.

Hệ này chia trọn 00-99 thành 45 cặp đảo cộng 5 cặp kép-bóng. Nó KHÔNG giả
định quan hệ miền là dự báo được; nó đo xem hai thành viên một cặp có hành xử
giống nhau trong lịch sử hay không. Vì thế mọi con số nó phát ra đều là bằng
chứng mô tả, và một phép đo sai ở đây sẽ âm thầm bẻ cong bằng chứng chứ không
làm chương trình nổ.

Mọi kỳ vọng bên dưới đều tính tay được từ khung dữ liệu bé ngay tại chỗ.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cap_loto_50_stats  # noqa: E402
from cap_loto_50_stats import (  # noqa: E402
    _current_cau_scores,
    _current_gap,
    _hit_matrices,
    _phi,
    _window_metrics,
    build_stats,
)


def _frame(rows: list[tuple[str, list[int]]]) -> pd.DataFrame:
    """Khung hai chữ số: ``date``, ``special`` (giá trị đầu), rồi các vị trí.

    ``_hit_matrices`` gom MỌI cột khác ``date`` vào ma trận lô, và đọc riêng
    cột ``special`` để dựng ma trận đề — nên cột ấy là bắt buộc.
    """
    width = max(len(values) for _, values in rows)
    records = []
    for day, values in rows:
        padded = list(values) + [values[-1]] * (width - len(values))
        record: dict[str, object] = {"date": pd.Timestamp(day), "special": padded[0]}
        record.update({f"p{i}": v for i, v in enumerate(padded[1:], start=1)})
        records.append(record)
    return pd.DataFrame(records)


# --- Hệ số phi -------------------------------------------------------------


def test_phi_matches_the_closed_form_on_a_hand_built_contingency_table() -> None:
    """phi là hệ số tương quan của hai biến nhị phân, tính từ bảng 2x2.

    Kiểm bằng một bảng tính tay chứ không gọi lại chính công thức đang kiểm.
    """
    # n11=3, n10=1, n01=1, n00=5
    x = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0], dtype=bool)
    y = np.array([1, 1, 1, 0, 1, 0, 0, 0, 0, 0], dtype=bool)
    expected = (3 * 5 - 1 * 1) / ((4 * 6 * 4 * 6) ** 0.5)
    assert _phi(x, y) == pytest.approx(expected)
    assert _phi(x, y) == pytest.approx(0.5833333333)


def test_phi_is_symmetric_and_extreme_at_perfect_agreement() -> None:
    x = np.array([1, 0, 1, 0, 1, 0], dtype=bool)
    y = np.array([0, 1, 0, 1, 0, 1], dtype=bool)
    assert _phi(x, y) == pytest.approx(-1.0), "hoàn toàn nghịch nhau"
    assert _phi(x, x) == pytest.approx(1.0), "hoàn toàn trùng nhau"
    assert _phi(x, y) == pytest.approx(_phi(y, x)), "phi phải đối xứng"


def test_phi_returns_zero_rather_than_nan_when_a_member_never_varies() -> None:
    """Một thành viên không đổi làm mẫu số bằng 0.

    Trả NaN ở đây sẽ len vào cột trung bình của bản tóm tắt và biến cả con số
    ấy thành NaN. 0.0 là giá trị đúng nghiệp vụ: không có tương quan đo được.
    """
    constant = np.ones(8, dtype=bool)
    varying = np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=bool)
    value = _phi(constant, varying)
    assert value == 0.0
    assert not np.isnan(value)


# --- Gan theo kỳ -----------------------------------------------------------


def test_current_gap_counts_draws_after_the_last_hit() -> None:
    """Gan là SỐ KỲ trôi qua sau kỳ trúng gần nhất, không tính chính kỳ ấy."""
    assert _current_gap(np.array([1, 0, 0, 0], dtype=bool)) == 3
    assert _current_gap(np.array([0, 0, 0, 1], dtype=bool)) == 0, "trúng ở kỳ cuối"
    assert _current_gap(np.array([1, 0, 1, 0], dtype=bool)) == 1, "chỉ tính lần cuối"


def test_never_hit_reports_the_whole_history_not_zero() -> None:
    """Chưa từng về thì gan bằng toàn bộ số kỳ — 0 sẽ đọc thành "vừa mới về"."""
    assert _current_gap(np.zeros(9, dtype=bool)) == 9


# --- Chỉ số theo cửa sổ ----------------------------------------------------


def test_any_and_both_rates_are_different_questions() -> None:
    """``pair_any`` là MỘT TRONG HAI về; ``pair_both`` là CẢ HAI cùng về.

    Lẫn hai đại lượng này là đúng cái bug từng làm bảng cặp báo sai. Ở đây
    chúng phải tách hẳn nhau trên cùng một bộ dữ liệu.
    """
    x = np.array([1, 1, 0, 0], dtype=bool)
    y = np.array([1, 0, 1, 0], dtype=bool)
    m = _window_metrics(x, y, 4)

    assert m["pair_any_rate_4d"] == pytest.approx(0.75), "3/4 kỳ có ít nhất một con"
    assert m["pair_both_rate_4d"] == pytest.approx(0.25), "chỉ 1/4 kỳ có cả hai"
    assert m["a_rate_4d"] == pytest.approx(0.5)
    assert m["b_rate_4d"] == pytest.approx(0.5)
    assert m["member_rate_gap_4d"] == pytest.approx(0.0)
    assert m["member_balance_4d"] == pytest.approx(1.0), "hai vế đều nhau"


def test_window_reads_the_tail_of_history_not_the_head() -> None:
    """Cửa sổ N kỳ phải lấy N kỳ GẦN NHẤT; lấy nhầm đầu dãy là đọc quá khứ xa."""
    x = np.array([1, 1, 1, 1, 0, 0], dtype=bool)
    y = np.zeros(6, dtype=bool)
    m = _window_metrics(x, y, 2)
    assert m["a_rate_2d"] == 0.0, "hai kỳ cuối con a không về"

    m_all = _window_metrics(x, y, 6)
    assert m_all["a_rate_6d"] == pytest.approx(4 / 6)


def test_rates_are_measured_over_draws_that_exist_not_the_requested_window() -> None:
    """Xin 365 kỳ khi mới có 3 kỳ thì mẫu số là 3, không phải 365.

    ``build_stats`` luôn gọi cả ba cửa sổ 30/90/365 trên cùng một lịch sử, nên
    kho mới dựng bao giờ cũng rơi vào tình huống này. Đệm 0 cho đủ cửa sổ sẽ
    kéo mọi tỷ lệ xuống gần 0 và làm cả bảng bằng chứng vô nghĩa.
    """
    x = np.array([1, 1, 1], dtype=bool)
    y = np.array([1, 0, 1], dtype=bool)
    m = _window_metrics(x, y, 365)

    assert m["a_rate_365d"] == pytest.approx(1.0)
    assert m["b_rate_365d"] == pytest.approx(2 / 3), "mẫu số là 3 kỳ có thật"
    assert m["pair_any_rate_365d"] == pytest.approx(1.0)


def test_balance_falls_as_the_two_members_diverge() -> None:
    """``member_balance`` là 1 khi hai vế bằng nhau và giảm dần khi lệch."""
    even = _window_metrics(
        np.array([1, 1, 0, 0], dtype=bool), np.array([1, 1, 0, 0], dtype=bool), 4
    )
    skewed = _window_metrics(
        np.array([1, 1, 1, 1], dtype=bool), np.array([1, 0, 0, 0], dtype=bool), 4
    )
    assert even["member_balance_4d"] == pytest.approx(1.0)
    assert skewed["member_balance_4d"] == pytest.approx(0.25)
    assert 0.0 <= skewed["member_balance_4d"] < even["member_balance_4d"]


def test_empty_window_returns_neutral_values_instead_of_dividing_by_zero() -> None:
    m = _window_metrics(np.array([], dtype=bool), np.array([], dtype=bool), 0)
    assert m["pair_any_rate_0d"] == 0.0
    assert m["member_balance_0d"] == 1.0


# --- Ma trận trúng ---------------------------------------------------------


def test_a_number_drawn_twice_in_one_draw_still_counts_as_one_hit_day() -> None:
    """Ma trận lô là NHỊ PHÂN theo kỳ: số nháy không được nhân đôi ngày trúng."""
    dates, loto, de = _hit_matrices(_frame([("2026-01-01", [11, 11, 22])]))

    assert loto.dtype == np.bool_
    assert loto[0, 11] and loto[0, 22]
    assert int(loto[0].sum()) == 2, "hai con khác nhau, không phải ba lần về"
    assert list(dates) == [pd.Timestamp("2026-01-01")]


def test_de_matrix_marks_exactly_one_number_per_draw() -> None:
    """Mỗi kỳ có đúng một giải Đặc Biệt, lấy hai số cuối."""
    _dates, _loto, de = _hit_matrices(
        _frame([("2026-01-01", [95, 52]), ("2026-01-02", [7, 88])])
    )
    assert int(de[0].sum()) == 1 and de[0, 95]
    assert int(de[1].sum()) == 1 and de[1, 7]


def test_history_is_sorted_by_date_before_anything_is_measured() -> None:
    """Gan và cửa sổ đều đọc theo thứ tự dãy, nên dãy phải được sắp trước."""
    unsorted = _frame([("2026-01-03", [33]), ("2026-01-01", [11]), ("2026-01-02", [22])])
    dates, loto, _de = _hit_matrices(unsorted)

    assert list(dates) == [
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-01-02"),
        pd.Timestamp("2026-01-03"),
    ]
    assert loto[0, 11] and loto[2, 33], "hàng phải đi theo ngày, không theo thứ tự tệp"


def test_empty_history_fails_loudly_instead_of_emitting_empty_evidence() -> None:
    """Kho rỗng ở đây là lỗi vận hành: phát ra bảng rỗng sẽ trông như dữ liệu thật."""
    with pytest.raises(RuntimeError, match="No two-digit history"):
        _hit_matrices(pd.DataFrame(columns=["date", "special"]))


# --- Neo cầu kèo -----------------------------------------------------------


def _write_cau(tmp_path: Path, anchor: str) -> Path:
    ai_ml = tmp_path / "ai_ml"
    ai_ml.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"number_str": "07", "cau_score": 0.8, "anchor_date": anchor},
            {"number_str": "70", "cau_score": 0.4, "anchor_date": anchor},
        ]
    ).to_csv(ai_ml / "cau_keo_loto_all.csv", index=False)
    return tmp_path


def test_cau_scores_load_only_when_anchored_to_the_same_history_end(
    tmp_path: Path,
) -> None:
    data_dir = _write_cau(tmp_path, "2026-01-02")
    scores = _current_cau_scores("loto", data_dir, expected_anchor="2026-01-02")
    assert scores == {"07": 0.8, "70": 0.4}


def test_a_stale_cau_artifact_is_dropped_whole_rather_than_partly_used(
    tmp_path: Path,
) -> None:
    """Tệp cầu kèo neo vào ngày khác là số liệu của một mốc khác.

    Trộn nó vào bảng hôm nay sẽ tạo ra bằng chứng lệch mốc — kiểu sai không
    bao giờ nổ, chỉ âm thầm sai. Bỏ TRỌN tệp là cách duy nhất an toàn.
    """
    data_dir = _write_cau(tmp_path, "2026-01-01")
    assert _current_cau_scores("loto", data_dir, expected_anchor="2026-01-02") == {}


def test_a_missing_or_malformed_cau_artifact_is_not_an_error(tmp_path: Path) -> None:
    """Không có tệp cầu kèo là trạng thái bình thường lúc dựng lần đầu."""
    assert _current_cau_scores("loto", tmp_path, expected_anchor="2026-01-02") == {}

    ai_ml = tmp_path / "ai_ml"
    ai_ml.mkdir(parents=True, exist_ok=True)
    (ai_ml / "cau_keo_loto_all.csv").write_text("khong,phai,cot,can\n1,2,3,4\n", encoding="utf-8")
    assert _current_cau_scores("loto", tmp_path, expected_anchor="2026-01-02") == {}


# --- Bảng hoàn chỉnh -------------------------------------------------------


class _FakeLottery:
    def __init__(self, two_digits: pd.DataFrame) -> None:
        self._two = two_digits

    def load(self) -> None:
        return None

    def get_2_digits_data(self) -> pd.DataFrame:
        return self._two.copy()


@pytest.fixture()
def _history(monkeypatch: pytest.MonkeyPatch) -> pd.DataFrame:
    frame = _frame(
        [
            ("2026-01-01", [7, 70, 11]),
            ("2026-01-02", [7, 22, 33]),
            ("2026-01-03", [70, 44, 55]),
        ]
    )
    monkeypatch.setattr(cap_loto_50_stats, "Lottery", lambda: _FakeLottery(frame))
    return frame


def test_the_partition_covers_every_number_exactly_once(
    _history: pd.DataFrame, tmp_path: Path
) -> None:
    """50 cặp phải chia TRỌN 00-99, mỗi con đúng một lần — đó là định nghĩa.

    Thiếu hay trùng một con thì mọi con số gộp theo cặp đều tính trên một
    tập khác với 00-99, và không cột nào trong bảng cho thấy điều đó.
    """
    df, summary = build_stats("loto", data_dir=tmp_path)

    assert len(df) == 50
    members = [*df["a"].tolist(), *df["b"].tolist()]
    assert sorted(members) == [f"{n:02d}" for n in range(100)]
    assert summary["reverse_pair_count"] == 45
    assert summary["kep_bong_pair_count"] == 5


def test_pair_columns_agree_with_a_hand_count_of_the_history(
    _history: pd.DataFrame, tmp_path: Path
) -> None:
    """Cặp 07-70: 07 về kỳ 1 và 2, 70 về kỳ 1 và 3.

    Vậy "một trong hai" đủ cả ba kỳ, còn "cả hai" chỉ một kỳ. Hai cột ấy phải
    ra đúng 3 và 1 chứ không được bằng nhau.
    """
    df, _summary = build_stats("loto", data_dir=tmp_path)
    row = df[df["pair_id"] == "07-70"].iloc[0]

    assert int(row["history_days"]) == 3
    assert int(row["a_hit_days"]) == 2 and int(row["b_hit_days"]) == 2
    assert int(row["pair_any_hit_days"]) == 3
    assert int(row["pair_both_hit_days"]) == 1
    assert int(row["pair_xor_hit_days"]) == 2
    assert float(row["jaccard"]) == pytest.approx(1 / 3)
    assert int(row["gap_a"]) == 1, "07 về lần cuối ở kỳ giữa"
    assert int(row["gap_b"]) == 0, "70 về ở kỳ cuối"
    assert int(row["gap_pair"]) == 0


def test_de_mode_reads_only_the_special_prize(
    _history: pd.DataFrame, tmp_path: Path
) -> None:
    """Ở chế độ đề, mỗi kỳ chỉ có ĐÚNG một con trúng dù kỳ ấy có ba con lô.

    Hệ quả kiểm được: không cặp nào có thể "cả hai cùng về", vì hai thành viên
    là hai con khác nhau mà mỗi kỳ chỉ có một Đặc Biệt. Cột ``pair_both_hit_days``
    khác 0 ở chế độ đề nghĩa là ma trận đề đã nhiễm dữ liệu lô.
    """
    df, _summary = build_stats("de", data_dir=tmp_path)
    assert int(df["a_hit_days"].sum() + df["b_hit_days"].sum()) == 3, "ba kỳ, ba con đề"
    assert int(df["pair_both_hit_days"].sum()) == 0

    # Đặc Biệt ba kỳ lần lượt là 07, 07, 70.
    row = df[df["pair_id"] == "07-70"].iloc[0]
    assert int(row["a_hit_days"]) == 2
    assert int(row["b_hit_days"]) == 1
    assert int(row["pair_any_hit_days"]) == 3, "cặp này chiếm trọn cả ba kỳ"
    assert int(row["pair_both_hit_days"]) == 0


def test_an_unknown_mode_is_rejected_before_any_data_is_read(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="mode must be loto or de"):
        build_stats("dac_biet", data_dir=tmp_path)
