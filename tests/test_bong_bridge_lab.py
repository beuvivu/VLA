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


def test_monte_carlo_p_value_never_claims_certainty_from_a_finite_sample() -> None:
    """``b/B`` trả về 0,0000 khi không mẫu nhiễu nào vượt — tức khẳng định xác
    suất BẰNG 0 từ 60 lần rút ngẫu nhiên.

    Đó đúng là con số tạo ra một "phát hiện" giả: nó biến bằng chứng chỉ đủ
    nói ``p < 0,0487`` thành một tuyên bố tuyệt đối. Ước lượng đúng là
    ``(1+b)/(1+B)``, không bao giờ chạm 0, và phải đi kèm cận trên thật của
    chính nó.
    """
    days = 320
    digits, targets = _synthetic(days, seed=77)
    for t in range(1, days):                      # cấy một đường cầu áp đảo
        targets[t, digits[t - 1, 0], digits[t - 1, 1]] = 1.0
    check = lab.reality_check(
        digits, targets, day_index=np.arange(3, days), lag_pairs=((1, 1),),
        permutations=20, seed=4,
    )
    assert check["null_exceed_count"] == 0, "ca kiểm phải thật sự không có mẫu nào vượt"
    assert check["p_value"] > 0.0, "ước lượng không bao giờ được trả về 0"
    assert check["p_value"] == pytest.approx(1.0 / 21.0)
    assert check["p_value_upper_95"] > check["p_value"], "cận trên phải nới ra, không thắt lại"
    assert check["p_value_upper_95"] == pytest.approx(1.0 - 0.05 ** (1 / 20), rel=1e-6)


def test_null_lift_uses_the_baseline_of_the_window_it_actually_scored() -> None:
    """Lift của nhiễu phải chia cho nền của CHÍNH cửa sổ đã dịch.

    Biên độ của lỗi này nhỏ ở cấu hình thật — cửa sổ chấm phủ gần trọn chuỗi
    nên dịch vòng hầu như không đổi nền, đo được chỉ 0,71%. Nhưng nó là lỗi
    có thật, sửa không tốn gì, và với cửa sổ ngắn thì nó lớn hẳn lên. Nên
    phép kiểm ở đây TẤT ĐỊNH chứ không thống kê: dựng lại đúng dãy dịch theo
    cùng hạt giống rồi so khớp từng con số, vì một sai lệch 0,7% thì không
    khẳng định thống kê nào bắt nổi.
    """
    days, window = 240, 40
    rng = np.random.default_rng(12)
    digits = rng.integers(0, 10, (days, lab.N_SLOTS)).astype(np.int8)
    targets = np.zeros((days, 10, 10), np.float32)
    for t in range(days):                     # bậc thang: nửa đầu thưa, nửa sau dày
        rate = 0.05 if t < days // 2 else 0.40
        targets[t] = (rng.random((10, 10)) < rate).astype(np.float32)

    day_index = np.arange(3, window)          # cửa sổ NGẮN -> dịch đổi nền rất mạnh
    check = lab.reality_check(
        digits, targets, day_index=day_index, lag_pairs=((1, 1),),
        permutations=8, seed=6,
    )

    base = float(targets[day_index].mean())
    replay = np.random.default_rng(6)
    correct, naive = [], []
    for _ in range(8):
        shift = int(replay.integers(1, days))
        rolled = np.roll(targets, shift, axis=0)
        shifted_base = float(rolled[day_index].mean())
        if shifted_base <= 0.0:
            continue
        trial = lab.scan_family(digits, rolled, day_index=day_index, lag_pairs=((1, 1),))
        peak = float(trial.hits.max() / trial.trials)
        correct.append(peak / shifted_base)
        naive.append(peak / base)

    # Ngưỡng 1e-6 chứ không phải 1e-9: lõi quét là một phép nhân ma trận
    # float32, và BLAS đa luồng cộng dồn theo thứ tự không tất định nên hai
    # lượt chạy cùng dữ liệu lệch nhau ở chữ số thứ tám. Đó là giới hạn tái
    # lập của phép tính, không phải khác biệt logic — và vẫn chặt hơn ba bậc
    # so với khoảng cách giữa hai cách chia.
    assert check["null_max_lift_mean"] == pytest.approx(float(np.mean(correct)), rel=1e-6)
    gap = abs(float(np.mean(naive)) - float(np.mean(correct))) / float(np.mean(correct))
    assert gap > 1e-2, f"ca kiểm phải thật sự phân biệt hai cách chia, chênh mới {gap:.2%}"
    assert check["null_max_lift_mean"] != pytest.approx(float(np.mean(naive)), rel=1e-3)


def test_a_family_too_small_to_score_reports_nothing_instead_of_crashing() -> None:
    """Dữ liệu quá ngắn để sinh luật nào là trạng thái HỢP LỆ.

    Bảng rỗng có mọi cột ở kiểu object và ``nlargest`` ném ``TypeError`` chứ
    không trả về bảng rỗng — một bước pipeline chạy với ``allow_fail`` sẽ nuốt
    mất lỗi ấy và để lại báo cáo của hôm trước.
    """
    digits, targets = _synthetic(60)
    empty = pd.DataFrame(
        columns=["lift", "q_value_fdr", "op_a", "op_b", "lag_a", "lag_b", "slot_a", "slot_b"]
    )
    out = lab.follow_through(
        digits, targets, (np.arange(3, 20), np.arange(20, 40), np.arange(40, 60)), empty, 50
    )
    assert out.empty
    assert "validation_lift" in out.columns, "bảng rỗng vẫn phải giữ đúng hợp đồng cột"
    assert lab._first(out, "validation_lift") is None
    assert lab._mean(out, "holdout_lift") is None


def test_negative_prize_values_are_rejected_at_the_door() -> None:
    """``zfill`` biến −5 thành "000-5" — dài đúng bằng ô nên lọt phép kiểm độ
    dài, rồi vỡ mãi sâu bên trong bằng một thông báo không chỉ ra được cột nào.
    """
    row = {"date": pd.Timestamp("2026-01-01")}
    for prize, (count, _) in lab.PRIZE_LAYOUT.items():
        for index in range(1, count + 1):
            row[prize if count == 1 else f"{prize}_{index}"] = 7
    row["prize7_1"] = -5
    with pytest.raises(ValueError, match="prize7_1.*âm"):
        lab.digit_matrix(pd.DataFrame([row]))


def test_reality_check_refuses_a_window_with_no_wins_at_all() -> None:
    """Nền bằng 0 thì lift là phép chia cho 0 — phải từ chối, không trả về vô cực."""
    digits, _ = _synthetic(80)
    empty_targets = np.zeros((80, 10, 10), np.float32)
    # Khớp thông báo CỦA ĐÚNG cổng này. Biểu thức "nền bằng 0" còn khớp cả
    # cổng "mọi lượt hoán vị đều cho nền bằng 0" ở cuối hàm, nên bỏ cổng đầu
    # đi mà phép kiểm vẫn xanh — đã đo bằng đột biến.
    with pytest.raises(ValueError, match="không có kỳ nào trúng"):
        lab.reality_check(digits, empty_targets, day_index=np.arange(3, 80),
                          lag_pairs=((1, 1),), permutations=3, seed=1)
    with pytest.raises(ValueError, match="ít nhất một lần hoán vị"):
        lab.reality_check(digits, _synthetic(80)[1], day_index=np.arange(3, 80),
                          lag_pairs=((1, 1),), permutations=0, seed=1)
