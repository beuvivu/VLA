"""Khoá lại lý do DỪNG của B3: tần suất nền toàn cục không trôi.

Đây là phép kiểm bảo vệ một quyết định KHÔNG làm gì. Nếu về sau ai đó muốn
thêm mô hình không gian trạng thái cho tần suất nền, phép kiểm này phải đỏ
trước — nghĩa là họ phải đo lại và chứng minh dữ liệu đã đổi, chứ không phải
thêm tham số vì nghe hợp lý.

Lý do cơ học đứng sau: số giải mỗi kỳ là cố định, nên tần suất nền chỉ xê dịch
được qua số con trùng trong cùng một kỳ. Nó bị chặn chặt từ trong thiết kế trò
chơi.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import number_dynamics as nd  # noqa: E402

BURN_IN = 400


@pytest.fixture(scope="module")
def base_rate() -> np.ndarray:
    _, hit = nd.build_hit_matrix_from_lottery("loto")
    return hit.mean(axis=1)


def test_the_rate_drifts_no_more_than_a_time_shuffled_copy(base_rate) -> None:
    """Trôi chậm: so phương sai trung bình trượt 90 kỳ với hoán vị thời gian.

    Số đo đầy đủ (2 000 hoán vị): quan sát 2,137e-06, vô hiệu 2,399e-06,
    p một phía = 0,656 — chuỗi thật trôi ÍT HƠN chuỗi xáo trộn.
    """
    window = 90
    kernel = np.ones(window) / window

    def rolling_variance(series: np.ndarray) -> float:
        return float(np.var(np.convolve(series, kernel, mode="valid"), ddof=1))

    observed = rolling_variance(base_rate)
    rng = np.random.default_rng(0)
    null = np.array(
        [rolling_variance(rng.permutation(base_rate)) for _ in range(300)]
    )
    p_value = float((null >= observed).mean())
    assert p_value > 0.05, f"tần suất nền đã bắt đầu trôi: p = {p_value:.4f}"


def test_the_rate_carries_no_usable_autocorrelation(base_rate) -> None:
    """z quan sát được: -1,05 / +0,10 / -0,03 / -2,41 / +0,78 / +0,43.

    Một giá trị vượt 2 trên sáu phép thử là đúng mức kỳ vọng ngẫu nhiên, nên
    phép kiểm đòi ĐA SỐ nằm trong ngưỡng chứ không đòi tất cả — đòi tất cả là
    một phép kiểm sẽ đỏ vì may rủi.
    """
    centred = base_rate - base_rate.mean()
    denominator = float(centred @ centred)
    standard_error = 1.0 / np.sqrt(len(base_rate))
    z_scores = [
        abs(float(centred[lag:] @ centred[:-lag]) / denominator) / standard_error
        for lag in (1, 2, 7, 30, 90, 365)
    ]
    assert sum(z > 2.0 for z in z_scores) <= 1
    assert max(z_scores) < 3.5


@pytest.mark.parametrize("alpha", [0.01, 0.1, 0.3])
def test_a_local_level_filter_is_worse_than_the_plain_running_mean(
    base_rate, alpha: float
) -> None:
    """Phép đo đã quyết định việc dừng B3.

    Thiệt hại tăng đơn điệu theo độ nhạy — đó là hình dạng của một mô hình
    đuổi theo nhiễu, không phải chuyện chưa chỉnh đúng tham số.

        α = 0,01  t = +2,36    α = 0,1  t = +5,59    α = 0,3  t = +9,43
    """
    n = len(base_rate)
    running_total = float(base_rate[:BURN_IN].sum())
    running_count = BURN_IN
    level = float(base_rate[:BURN_IN].mean())
    mean_errors: list[float] = []
    filter_errors: list[float] = []
    for t in range(BURN_IN, n):
        actual = float(base_rate[t])
        mean_errors.append((actual - running_total / running_count) ** 2)
        filter_errors.append((actual - level) ** 2)
        running_total += actual
        running_count += 1
        level = (1.0 - alpha) * level + alpha * actual

    delta = np.asarray(filter_errors) - np.asarray(mean_errors)
    standard_error = float(np.std(delta, ddof=1) / np.sqrt(delta.size))
    t_stat = float(delta.mean() / standard_error)
    assert t_stat > 2.0, (
        f"bộ lọc mức cục bộ α={alpha} nay tốt hơn trung bình chạy (t={t_stat:+.2f}); "
        "phải đo lại quyết định dừng B3 trước khi sửa phép kiểm này"
    )
