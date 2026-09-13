"""Gộp thông tin có phân cấp: học độ co ngót thay vì đặt tay.

Vì sao đây là hướng duy nhất nâng được công suất: ``randomness_report.json``
đo được ngưỡng phát hiện +15,8 % tương đối với 100 giả thuyết, nhưng chỉ
+10,3 % với một. Mô hình phân cấp không thêm sức chứa — nó BỚT đi, kéo số tham
số hiệu dụng từ 100 xuống gần 1.

Điều một bộ ước lượng co ngót phải làm đúng là PHÂN BIỆT hai chế độ. Co ngót
hoàn toàn lúc nào cũng "an toàn" và vô dụng; không co ngót bao giờ cũng giữ
được mọi tín hiệu lẫn mọi nhiễu. Mọi phép kiểm ở đây khoá cả hai chiều.
"""

from __future__ import annotations

import numpy as np
import pytest

from hierarchical_pooling import (
    MAX_PRIOR_STRENGTH,
    MIN_NUMBERS,
    fit_pooling,
    pooled_posterior,
)


def test_homogeneous_units_are_pooled_hard() -> None:
    """Khi mọi đơn vị thật sự cùng tỉ lệ, co ngót mạnh là câu trả lời ĐÚNG.

    Không phải mô hình thất bại: giữ 100 ước lượng rời rạc khi dữ liệu không
    phân biệt được chúng chỉ là giữ 100 bản sao của nhiễu.
    """
    rng = np.random.default_rng(0)
    trials = 2000
    fit = fit_pooling(rng.binomial(trials, 0.2377, size=100), trials)

    assert fit.shrinkage > 0.8, fit.describe()
    assert fit.effective_parameters < 25.0, fit.describe()
    assert fit.pooled_rate == pytest.approx(0.2377, abs=0.01)


def test_genuinely_different_units_are_kept_apart() -> None:
    """Chiều còn lại, và là chiều dễ mất nhất.

    Một bộ ước lượng luôn co ngót hoàn toàn sẽ qua được phép kiểm trên kia mà
    vô dụng hoàn toàn. Ca này cài khác biệt thật và đòi nó giữ lại.
    """
    rng = np.random.default_rng(1)
    trials = 2000
    rates = np.clip(rng.normal(0.2377, 0.03, size=100), 0.01, 0.99)
    fit = fit_pooling(rng.binomial(trials, rates), trials)

    assert fit.shrinkage < 0.3, fit.describe()
    assert fit.effective_parameters > 70.0, fit.describe()
    assert not fit.fully_pooled


def test_no_excess_variance_means_fully_pooled_not_a_negative_strength() -> None:
    """Phần phương sai vượt âm phải ra co ngót hoàn toàn, không phải κ âm.

    Đây là trường hợp THƯỜNG GẶP NHẤT với dữ liệu của kho, không phải ca biên
    cần né: nó chính là câu trả lời "các con số không phân biệt được nhau".
    """
    # Mọi đơn vị có đúng cùng số lần thành công: phương sai quan sát bằng 0,
    # tức thấp hơn cả mức dao động nhị thức.
    fit = fit_pooling(np.full(100, 500.0), 2000.0)
    assert fit.fully_pooled
    assert fit.prior_strength == MAX_PRIOR_STRENGTH
    assert fit.between_variance == 0.0
    assert "Co ngót HOÀN TOÀN" in fit.describe()
    # Ở mức trần κ vẫn còn một phần tự do rất nhỏ: κ/(κ+n) < 1 nên tham số hiệu
    # dụng là 1,20 chứ không phải đúng 1,00. Thông điệp phải in số THẬT ấy —
    # in cứng "1,00" là để một sai lệch nhỏ sống sót qua mọi lần đọc.
    assert 1.0 < fit.effective_parameters < 1.5
    assert f"{fit.effective_parameters:.2f}" in fit.describe()


def test_shrinkage_weakens_as_evidence_accumulates() -> None:
    """Nhiều dữ liệu hơn thì mỗi đơn vị được tự nói nhiều hơn.

    Đây là tính chất định nghĩa của co ngót Bayes thực nghiệm: cùng một κ,
    càng nhiều phép thử thì trọng số dồn về dữ liệu riêng của đơn vị.
    """
    rng = np.random.default_rng(2)
    rates = np.clip(rng.normal(0.24, 0.03, size=100), 0.01, 0.99)
    shrinkages = [
        fit_pooling(rng.binomial(n, rates), n).shrinkage for n in (200, 1000, 5000)
    ]
    assert shrinkages[0] > shrinkages[1] > shrinkages[2], shrinkages


def test_the_posterior_lies_between_the_raw_rate_and_the_pooled_mean() -> None:
    """Co ngót là phép nội suy: không bao giờ vọt ra ngoài hai đầu."""
    rng = np.random.default_rng(3)
    trials = 400
    counts = rng.binomial(trials, 0.24, size=100).astype(float)
    fit = fit_pooling(counts, trials)
    posterior = pooled_posterior(counts, trials, fit)

    raw = counts / trials
    low = np.minimum(raw, fit.pooled_rate)
    high = np.maximum(raw, fit.pooled_rate)
    assert np.all(posterior >= low - 1e-9)
    assert np.all(posterior <= high + 1e-9)
    # Và nó phải NÉN dải giá trị lại, nếu không thì đã không co ngót gì.
    assert posterior.max() - posterior.min() < raw.max() - raw.min()


def test_unequal_trial_counts_are_handled_by_weighting() -> None:
    """Đơn vị được thử nhiều hơn mang nhiều thông tin hơn.

    Trung bình thường sẽ để một đơn vị hiếm với tỉ lệ cực đoan kéo lệch cả
    trung bình chung; trung bình có trọng số thì không.
    """
    counts = np.array([240.0, 240.0, 240.0, 1.0])
    trials = np.array([1000.0, 1000.0, 1000.0, 1.0])
    fit = fit_pooling(counts, trials)
    # Ba đơn vị lớn nói 0,24; đơn vị một-phép-thử nói 1,0. Trung bình thường
    # sẽ ra 0,43; trung bình có trọng số phải bám sát 0,24.
    assert fit.pooled_rate == pytest.approx(721.0 / 3001.0, abs=1e-9)
    assert fit.pooled_rate < 0.25

    # Và số phép thử hiệu dụng phải là trung bình ĐIỀU HOÀ, không phải cộng.
    # Điều hoà ở đây là 3,99 còn cộng là 750,2 — chênh gần hai trăm lần, nên
    # độ co ngót ra 0,176 thay vì 0,0011. Không khẳng định chỗ này thì một
    # đột biến đổi điều hoà thành cộng đi lọt.
    assert fit.shrinkage > 0.1, (
        f"co ngót {fit.shrinkage:.6f} quá thấp — nhiều khả năng đang dùng "
        "trung bình cộng của số phép thử"
    )


def test_extreme_heterogeneity_drives_the_prior_strength_down_to_single_digits() -> None:
    """Chế độ κ NHỎ, nơi công thức mô men phải chính xác tới từng đơn vị.

    Với κ hàng nghìn, lệch một không đo được. Với κ cỡ 2-3 thì lệch một là sai
    hơn ba mươi phần trăm — nên phải có một ca ép κ xuống vùng ấy, nếu không
    công thức chỉ được kiểm ở nơi nó không thể sai.
    """
    rng = np.random.default_rng(9)
    trials = 2000
    rates = np.linspace(0.05, 0.95, 100)
    fit = fit_pooling(rng.binomial(trials, rates), trials)

    assert 2.0 < fit.prior_strength < 3.5, (
        f"κ = {fit.prior_strength:.3f}; ngoài dải này thì công thức mô men "
        "đã lệch (thiếu hoặc thừa số hạng -1)"
    )
    assert fit.shrinkage < 0.01
    assert fit.effective_parameters > 99.0, "khác biệt thật thì phải giữ gần đủ tham số"


@pytest.mark.parametrize(
    ("counts", "trials", "match"),
    [
        (np.array([1.0, 2.0]), 10.0, "ít nhất"),
        (np.array([1.0, 2.0, 3.0]), 0.0, "ít nhất một phép thử"),
        (np.array([1.0, 2.0, 3.0]), np.array([10.0, 10.0]), "cùng hình dạng"),
        (np.array([-1.0, 2.0, 3.0]), 10.0, r"\[0, số phép thử\]"),
        (np.array([11.0, 2.0, 3.0]), 10.0, r"\[0, số phép thử\]"),
    ],
)
def test_invalid_input_is_refused(counts, trials, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        fit_pooling(counts, trials)


def test_the_minimum_unit_count_is_stated_not_implied() -> None:
    """Hai đơn vị không đủ để ước lượng phương sai giữa các đơn vị."""
    assert MIN_NUMBERS >= 3
    fit = fit_pooling(np.array([100.0, 120.0, 110.0]), 500.0)
    assert fit.n_units == 3


# --- Nối vào tín hiệu thống kê ---------------------------------------------


def test_each_posterior_learns_its_own_shrinkage() -> None:
    """κ của tần suất chung KHÔNG được áp cho hậu nghiệm theo thứ.

    Hai phép đo trả lời hai câu hỏi gộp khác nhau. Dùng chung một κ có hướng
    sai rõ ràng: tần suất chung đồng nhất kéo κ lên rất lớn, rồi κ ấy nghiền
    nát một nhịp theo thứ CÓ THẬT.

    Bản đầu tôi viết đúng lỗi ấy, và phép kiểm nhịp thứ Hai bắt được: biên tách
    của con 42 tụt từ 1,87 lần xuống 1,08 lần.
    """
    import pandas as pd

    from statistical_signal import _loto_signal

    # Tần suất chung hoàn toàn đồng nhất, nhưng con 7 chỉ về vào thứ Hai.
    dates = pd.date_range("2026-01-05", periods=40 * 7, freq="D")
    rng = np.random.default_rng(4)
    hit = (rng.random((len(dates), 100)) < 0.2377).astype(np.int8)
    monday = np.array([d.weekday() == 0 for d in dates])
    hit[monday, 7] = 1
    hit[~monday, 7] = 0

    out = _loto_signal(hit, pd.Series(dates), 0, half_life=45, prior_strength=None)
    others = out[out["number"] != 7]["weekday_prob"].to_numpy(dtype=float)
    assert float(out.loc[7, "weekday_prob"]) > others.max() * 1.5, (
        "κ học riêng cho hậu nghiệm theo thứ phải giữ được nhịp thứ Hai"
    )


def test_the_signal_reports_its_effective_parameter_count() -> None:
    """Số tham số hiệu dụng là con số nối thẳng tới công suất thống kê.

    Không báo cáo nó thì lập luận "gộp giúp phát hiện dễ hơn" không kiểm được.
    """
    import pandas as pd

    import statistical_signal as ss

    days = 400
    dates = pd.date_range("2025-01-01", periods=days, freq="D")
    rng = np.random.default_rng(5)
    numbers = rng.integers(0, 100, size=(days, 27))

    two = pd.DataFrame({"date": dates, "special": numbers[:, 0]})
    for i in range(1, 27):
        two[f"p{i}"] = numbers[:, i]
    counts = np.zeros((days, 100), dtype=int)
    for t in range(days):
        np.add.at(counts[t], numbers[t], 1)
    sparse = pd.DataFrame(counts)
    sparse.insert(0, "date", dates)

    class _Fake:
        def load(self): return None
        def get_2_digits_data(self): return two.copy()
        def get_sparse_data(self): return sparse.copy()

    original = ss.Lottery
    try:
        ss.Lottery = lambda: _Fake()
        _df, diag = ss.build_statistical_signal("loto")
    finally:
        ss.Lottery = original

    assert diag["prior_strength_learned"] is True
    pooling = diag["pooling"]
    assert 1.0 <= pooling["effective_parameters"] <= 100.0
    assert 0.0 <= pooling["shrinkage"] <= 1.0
    assert "verdict" in pooling

    # Ép một giá trị cụ thể thì phải báo là KHÔNG học.
    try:
        ss.Lottery = lambda: _Fake()
        _df2, diag2 = ss.build_statistical_signal("loto", prior_strength=80.0)
    finally:
        ss.Lottery = original
    assert diag2["prior_strength_learned"] is False
    assert diag2["prior_strength"] == 80.0
    assert diag2["pooling"] is None
