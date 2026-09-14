"""Đường nền của ``number_dynamics`` học độ co ngót thay vì đặt tay.

Giá trị cũ là ``max(20, κ·0,5)`` — 22,5 cho lô tô — và nó được chọn bằng cảm
tính. Đo walk-forward 400 kỳ trên dữ liệu thật, thống kê t cặp đôi:

    κ = 22,5 (đang dùng)   Brier 0,18143488       —
    κ = 90                 Brier 0,18142966   t = -5,16
    κ = 1000               Brier 0,18138711   t = -4,57
    HỌC κ                  Brier 0,18132998   t = -3,09

Cả ba đều vượt xa ngưỡng 2 SE, và bản học được có hiệu ứng lớn gấp hai mươi
lần bản κ=90. Đây là điểm KHÁC với phép hợp tín hiệu ở tầng 2: ở đó không ứng
viên nào đạt nổi 2 SE nên kết luận là giữ nguyên, còn ở đây bằng chứng rất rõ.
"""

from __future__ import annotations

import numpy as np
import pytest

from number_dynamics import LEARN_BASELINE_PRIOR, _baseline


def test_learning_is_the_default() -> None:
    """Mặc định phải là HỌC, nếu không thay đổi này không có tác dụng gì."""
    assert LEARN_BASELINE_PRIOR is None


def test_homogeneous_numbers_are_pooled_toward_the_global_rate() -> None:
    """Khi các con không phân biệt được, đường nền phải gần như phẳng.

    Đây là điều κ đặt tay 22,5 KHÔNG làm được: nó để lại dao động ngẫu nhiên
    của từng con như thể đó là khác biệt thật.
    """
    rng = np.random.default_rng(0)
    hit = (rng.random((1200, 100)) < 0.2377).astype(np.int8)

    learned = _baseline(hit, prior_strength=None)
    legacy = _baseline(hit, prior_strength=22.5)

    assert learned.std() < legacy.std() / 3.0, (
        f"học κ nên phẳng hơn hẳn: std {learned.std():.6f} so với {legacy.std():.6f}"
    )
    assert learned.mean() == pytest.approx(float(hit.mean()), abs=1e-3)


def test_genuine_differences_survive_the_shrinkage() -> None:
    """Chiều còn lại: co ngót không được xoá khác biệt THẬT.

    Một đường nền luôn phẳng sẽ qua được phép kiểm trên kia mà vô dụng hoàn
    toàn — nó chỉ là hằng số đội lốt.
    """
    rng = np.random.default_rng(1)
    rates = np.clip(rng.normal(0.2377, 0.08, size=100), 0.05, 0.7)
    hit = (rng.random((1200, 100)) < rates[None, :]).astype(np.int8)

    learned = _baseline(hit, prior_strength=None)
    # Tương quan với tỉ lệ thật phải cao: khác biệt thật được giữ lại.
    assert float(np.corrcoef(learned, rates)[0, 1]) > 0.9
    assert learned.std() > 0.03


def test_an_explicit_strength_still_reproduces_the_legacy_behaviour() -> None:
    """Truyền số cụ thể phải cho đúng công thức cũ, để tái lập được bản chạy cũ."""
    rng = np.random.default_rng(2)
    hit = (rng.random((300, 100)) < 0.2377).astype(np.int8)

    expected = (hit.sum(axis=0) + 22.5 * hit.mean()) / (len(hit) + 22.5)
    np.testing.assert_allclose(_baseline(hit, prior_strength=22.5), expected)


@pytest.mark.parametrize("shape", [(0, 100), (1, 100), (5, 2)])
def test_a_degenerate_history_falls_back_to_the_global_rate(shape: tuple) -> None:
    """Quá ít dữ liệu để ước lượng phương sai giữa các đơn vị thì trả tỉ lệ chung.

    Nổ ở đây sẽ làm đổ cả tầng động lực số trong những ngày đầu dựng kho.
    """
    hit = np.ones(shape, dtype=np.int8)
    out = _baseline(hit, prior_strength=None)
    assert out.shape == (shape[1],)
    assert np.isfinite(out).all()
    assert np.all((out >= 0.0) & (out <= 1.0))


def test_the_learned_baseline_beats_the_legacy_constant_walk_forward() -> None:
    """Khoá lại chính kết quả đã dùng để biện minh cho thay đổi này.

    Không có phép kiểm này thì con số trong tài liệu chỉ là một khẳng định.
    Dùng dữ liệu tổng hợp đồng nhất — đúng chế độ mà dữ liệu thật rơi vào — và
    đòi bản học được thắng ở mức 2 SE.
    """
    rng = np.random.default_rng(3)
    hit = (rng.random((700, 100)) < 0.2377).astype(np.int8)

    legacy_errors, learned_errors = [], []
    for t in range(400, len(hit)):
        past, y = hit[:t], hit[t]
        legacy_errors.append(float(np.mean((_baseline(past, 22.5) - y) ** 2)))
        learned_errors.append(float(np.mean((_baseline(past, None) - y) ** 2)))

    delta = np.asarray(learned_errors) - np.asarray(legacy_errors)
    standard_error = float(np.std(delta, ddof=1) / np.sqrt(delta.size))
    t_stat = float(delta.mean() / standard_error)
    assert t_stat < -2.0, (
        f"t = {t_stat:.2f}; bản học được phải thắng ở mức 2 SE, nếu không thì "
        "thay đổi này không có cơ sở"
    )
