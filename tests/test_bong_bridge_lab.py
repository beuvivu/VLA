"""Phòng thí nghiệm cầu bóng: máy dò phải đúng TRƯỚC khi tin kết luận của nó.

Một kết luận "không tìm thấy đường cầu nào" chỉ có giá trị nếu máy dò thật sự
bắt được đường cầu khi đường cầu tồn tại. Nên tệp này kiểm cả hai chiều: cấy
tín hiệu vào thì phải BẮT ĐƯỢC, và trên nhiễu thuần thì phải IM LẶNG.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

import bong_bridge_lab as lab


def _synthetic(days: int, seed: int = 11):
    rng = np.random.default_rng(seed)
    digits = rng.integers(0, 10, size=(days, lab.N_SLOTS)).astype(np.int8)
    targets = (rng.random((days, 10, 10)) < 0.238).astype(np.float32)
    return digits, targets


def test_digit_matrix_pads_by_declared_width_not_string_length() -> None:
    """Kho lưu bằng số nguyên nên số 0 đứng đầu đã mất.

    Giải bảy ``5`` phải thành ``05``. Đệm theo độ dài chuỗi thay vì theo độ
    rộng khai báo sẽ đẩy lệch toàn bộ hệ toạ độ đi một ô, và mọi đường cầu tìm
    được sau đó là đường cầu của một bảng kết quả không tồn tại.
    """
    row = {"date": pd.Timestamp("2026-01-01"), "special": 5, "prize1": 12345}
    for prize, (count, _) in lab.PRIZE_LAYOUT.items():
        for index in range(1, count + 1):
            column = prize if count == 1 else f"{prize}_{index}"
            row.setdefault(column, 7)
    matrix = lab.digit_matrix(pd.DataFrame([row]))

    assert list(matrix[0, :5]) == [0, 0, 0, 0, 5], "Đặc Biệt 5 phải là 00005"
    assert list(matrix[0, 5:10]) == [1, 2, 3, 4, 5]
    assert list(matrix[0, -2:]) == [0, 7], "giải bảy 7 phải là 07"


def test_digit_matrix_rejects_a_value_wider_than_its_prize() -> None:
    """Giá trị dài hơn ô là dấu hiệu dữ liệu hỏng, không phải chuyện cắt bớt."""
    row = {"date": pd.Timestamp("2026-01-01")}
    for prize, (count, _) in lab.PRIZE_LAYOUT.items():
        for index in range(1, count + 1):
            row[prize if count == 1 else f"{prize}_{index}"] = 7
    row["prize7_1"] = 123
    with pytest.raises(ValueError, match="prize7_1"):
        lab.digit_matrix(pd.DataFrame([row]))


def test_scan_matches_a_naive_implementation() -> None:
    """Lõi quét dùng một mẹo nhân ma trận; phải khớp bản lặp thẳng từng ô.

    Mẹo gộp trục (kỳ, chữ số) để 11 449 cặp ô thành một phép nhân ma trận. Nó
    nhanh gấp hàng trăm lần, và cũng đúng là kiểu mã mà lỗi ẩn được trong đó.
    """
    digits, targets = _synthetic(60)
    day_index = np.arange(3, 60)
    lag_pairs = ((1, 1), (1, 2))
    result = lab.scan_family(digits, targets, day_index=day_index, lag_pairs=lag_pairs)

    rng = np.random.default_rng(3)
    for rule_id, (op_a, op_b, lag_a, lag_b) in enumerate(result.labels):
        for _ in range(12):
            i = int(rng.integers(0, lab.N_SLOTS))
            j = int(rng.integers(0, lab.N_SLOTS))
            expected = sum(
                targets[t, lab.DIGIT_OPS[op_a][digits[t - lag_a, i]],
                        lab.DIGIT_OPS[op_b][digits[t - lag_b, j]]]
                for t in day_index
            )
            assert result.hits[rule_id, i, j] == pytest.approx(expected), (op_a, op_b, i, j)


def test_usable_days_drops_a_lag_that_would_cross_a_missing_draw() -> None:
    """XSMB có ngày nghỉ, nên lùi MỘT HÀNG đôi khi là lùi HAI NGÀY.

    Để lọt chuyện này là tự bịa ra quan hệ giữa hai kỳ không kề nhau — đúng
    loại lỗi làm một đường cầu vô nghĩa trông như có thật.
    """
    dates = pd.Series(pd.to_datetime(
        ["2026-01-01", "2026-01-02", "2026-01-04", "2026-01-05", "2026-01-06"]
    ))
    keep = lab.usable_days(dates, ((1, 1),), warmup=0)
    kept = set(dates.iloc[keep])
    assert pd.Timestamp("2026-01-04") not in kept, "03/01 nghỉ nên 04/01 không tra được lag 1"
    assert pd.Timestamp("2026-01-05") in kept
    assert pd.Timestamp("2026-01-06") in kept


def test_target_matrix_keeps_the_two_base_rates_apart() -> None:
    """Nền của lô là 0,2378 còn của Đặc Biệt là 0,01 — lệch hai mươi lần.

    Dùng chung một nền cho cả hai đích làm mọi lift của Đặc Biệt sai gấp bội.
    """
    columns = ["date", "special"] + [f"c{i}" for i in range(26)]
    rng = np.random.default_rng(5)
    frame = pd.DataFrame(
        {"date": pd.date_range("2026-01-01", periods=400)}
        | {c: rng.integers(0, 100, 400) for c in columns[1:]}
    )
    loto = lab.target_matrix(frame, "loto")
    de = lab.target_matrix(frame, "de")
    assert de.sum(axis=(1, 2)).max() == 1.0, "Đặc Biệt chỉ có đúng một ô mỗi kỳ"
    assert de.mean() == pytest.approx(0.01)
    assert 0.20 < loto.mean() < 0.28
    with pytest.raises(ValueError, match="mode"):
        lab.target_matrix(frame, "cả hai")


def test_rule_table_uses_the_exact_binomial_tail() -> None:
    """Ở đích Đặc Biệt, n·p chỉ khoảng 24 — vùng xấp xỉ chuẩn lệch thấy rõ."""
    hits = np.zeros((1, lab.N_SLOTS, lab.N_SLOTS), dtype=np.float32)
    hits[0, 0, 0] = 700.0
    scan = lab.ScanResult(hits, 2400, (("goc", "goc", 1, 1),))
    table = lab.rule_table(scan, 0.2379)
    best = table.loc[table["hits"].idxmax()]
    assert best["p_value"] == pytest.approx(stats.binom.sf(699, 2400, 0.2379))
    assert best["lift"] == pytest.approx((700 / 2400) / 0.2379)
    assert (table["p_bonferroni"] <= 1.0).all()


def test_reality_check_finds_a_bridge_that_is_really_there() -> None:
    """MÁY DÒ PHẢI KÊU KHI CÓ TÍN HIỆU.

    Không có phép kiểm này thì kết luận "không tìm thấy đường cầu nào" không
    phân biệt được với "máy dò hỏng". Ở đây cấy một đường cầu thật: chữ số ô 0
    của kỳ trước ghép chữ số ô 1 của kỳ trước LUÔN có mặt trong kết quả hôm
    sau. Máy phải bắt được, với p nhỏ.
    """
    days = 500
    digits, targets = _synthetic(days, seed=21)
    for t in range(1, days):
        targets[t, digits[t - 1, 0], digits[t - 1, 1]] = 1.0

    day_index = np.arange(3, days)
    check = lab.reality_check(
        digits, targets, day_index=day_index, lag_pairs=((1, 1),),
        permutations=30, seed=1,
    )
    assert check["observed_max_lift"] > 1.8, check
    assert check["p_value"] < 0.05, check


def test_reality_check_stays_quiet_on_pure_noise() -> None:
    """Và PHẢI IM LẶNG KHI KHÔNG CÓ GÌ.

    Nửa còn lại của phép hiệu chuẩn. Một máy dò kêu cả trên nhiễu thì kết luận
    "có đường cầu" cũng vô giá trị hệt như chiều ngược lại.
    """
    digits, targets = _synthetic(500, seed=33)
    check = lab.reality_check(
        digits, targets, day_index=np.arange(3, 500), lag_pairs=((1, 1),),
        permutations=30, seed=2,
    )
    assert check["p_value"] > 0.05, check


def test_follow_through_scores_train_winners_on_untouched_days() -> None:
    """Chọn luật ở một lát, chấm ở lát khác — cách duy nhất tách thật khỏi ảo.

    Nếu hàm này lỡ chấm luật trên chính lát đã chọn nó, mọi đường cầu sẽ trông
    như chạy tiếp hoàn hảo và cả phòng thí nghiệm trở thành máy sinh ảo giác.
    """
    days = 400
    digits, targets = _synthetic(days, seed=44)
    train = np.arange(3, 250)
    valid = np.arange(250, 330)
    holdout = np.arange(330, days)
    scan = lab.scan_family(digits, targets, day_index=train, lag_pairs=((1, 1),))
    table = lab.rule_table(scan, float(targets[train].mean()))
    out = lab.follow_through(digits, targets, (train, valid, holdout), table, top=5)

    assert len(out) == 5
    assert (out["validation_days"] == len(valid)).all()
    assert (out["holdout_days"] == len(holdout)).all()
    # Luật chọn bằng hậu nghiệm trên nhiễu: train cao, ngoài mẫu rơi về nền.
    assert out["train_lift"].min() > 1.05
    assert out["validation_lift"].mean() < out["train_lift"].mean()


def test_ngu_hanh_is_exactly_the_bong_duong_mapping() -> None:
    """Kim 2–7, Mộc 5–0, Thủy 1–6, Hỏa 3–8, Thổ 4–9 chính là bóng dương.

    Khoá lại vì nó đổi thiết kế: Ngũ Hành KHÔNG sinh thêm giả thuyết nào cho
    bộ quét. Thêm một cột riêng cho nó là nhân đôi cùng một luật rồi tự phạt
    mình bằng hiệu chỉnh đa phép thử cho phần thừa ấy.
    """
    ngu_hanh = {"kim": 2, "moc": 5, "thuy": 1, "hoa": 3, "tho": 4}
    bong_cua_ngu_hanh = {"kim": 7, "moc": 0, "thuy": 6, "hoa": 8, "tho": 9}
    for element, digit in ngu_hanh.items():
        assert lab.DIGIT_OPS["duong"][digit] == bong_cua_ngu_hanh[element], element


def test_the_published_page_reports_out_of_sample_lift() -> None:
    """Trang phải hiện độ nâng NGOÀI MẪU, không chỉ độ nâng trên tập huấn luyện.

    Chỉ hiện cột huấn luyện là đúng cách mọi trang soi cầu đánh lừa người đọc:
    đường cầu nào cũng đẹp trên chính những kỳ đã dùng để chọn nó. Đo được ở
    dự án này: cầu mạnh nhất trong 206.082 luật đạt 1,235 khi huấn luyện rồi
    rơi về 0,913 trên tập giữ lại.
    """
    from pathlib import Path

    page = Path(__file__).resolve().parents[1] / "docs" / "research-lab.html"
    html = page.read_text(encoding="utf-8")
    start = html.find("Cầu bóng trên toàn bộ")
    assert start > 0, "trang thiếu hẳn phần cầu bóng"
    section = html[start : start + 4000]
    for column in ("Độ nâng (huấn luyện)", "Kiểm định", "Giữ lại"):
        assert column in section, f"thiếu cột {column!r}"
