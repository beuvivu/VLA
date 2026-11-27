from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from stats import number_dynamics as nd  # noqa: E402

BURN_IN = 400


@pytest.fixture(scope="module")
def base_rate() -> np.ndarray:
    _, hit = nd.build_hit_matrix_from_lottery("loto")
    return hit.mean(axis=1)


def test_the_rate_drifts_no_more_than_a_time_shuffled_copy(base_rate) -> None:
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
    centred = base_rate - base_rate.mean()
    denominator = float(centred @ centred)
    standard_error = 1.0 / np.sqrt(len(base_rate))
    z_scores = [
        abs(float(centred[lag:] @ centred[:-lag]) / denominator) / standard_error
        for lag in (1, 2, 7, 30, 90, 365)
    ]
    assert sum(z > 2.0 for z in z_scores) <= 1
    assert max(z_scores) < 3.5


ALPHAS = (0.01, 0.1, 0.3)


def _filter_penalty(base_rate, alpha: float) -> float:
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
    return float(delta.mean() / standard_error)


def test_a_local_level_filter_is_worse_than_the_plain_running_mean(base_rate) -> None:
    t_stats = [_filter_penalty(base_rate, alpha) for alpha in ALPHAS]
    shown = ", ".join(f"α={a}: {t:+.2f}" for a, t in zip(ALPHAS, t_stats, strict=True))

    for alpha, t_stat in zip(ALPHAS, t_stats, strict=True):
        assert t_stat > -2.0, (
            f"bộ lọc mức cục bộ α={alpha} nay TỐT HƠN trung bình chạy "
            f"({t_stat:+.2f} SE); phải đo lại quyết định dừng B3 trước khi "
            f"sửa phép kiểm này. Toàn bảng: {shown}"
        )

    assert t_stats == sorted(t_stats), (
        "thiệt hại không còn tăng đơn điệu theo độ nhạy — mất đúng hình dạng "
        f"'đuổi theo nhiễu' vốn là lý do dừng B3. Toàn bảng: {shown}"
    )

    for alpha, t_stat in zip(ALPHAS[1:], t_stats[1:], strict=True):
        assert t_stat > 2.0, (
            f"ở mức nhạy thật α={alpha}, thiệt hại không còn có ý nghĩa "
            f"({t_stat:+.2f} SE). Toàn bảng: {shown}"
        )
