"""Tín hiệu phải ĐI QUA được các tầng, và phép hợp phải được CHỌN chứ không đặt tay."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import number_dynamics as nd  # noqa: E402

BASE_RATE = 0.2378


def _inject(hit: np.ndarray, amount: float, seed: int = 0) -> np.ndarray:
    """P(34 về | 12 về hôm trước) = tần suất nền × (1 + amount).

    Một định nghĩa DUY NHẤT cho cả tệp. Hai kịch bản đo trước đây dùng hai
    định nghĩa khác nhau (0,9 và 0,37) và cho hai kết luận trái ngược về cùng
    một câu hỏi — sai lầm ấy không được lặp lại.
    """
    rng = np.random.default_rng(seed)
    h = hit.copy().astype(np.int8)
    if amount <= 0:
        return h
    target = min(0.98, BASE_RATE * (1.0 + amount))
    for t in range(1, len(h)):
        if h[t - 1, 12]:
            h[t, 34] = 1 if rng.random() < target else 0
    return h


@pytest.fixture(scope="module")
def real() -> tuple[pd.DatetimeIndex, np.ndarray]:
    return nd.build_hit_matrix_from_lottery("loto")


def test_arithmetic_pooling_can_never_sharpen_beyond_its_inputs() -> None:
    """Giới hạn CẤU TRÚC, không phải chuyện chỉnh tham số."""
    base = np.full(100, 0.2)
    trans = np.tile(base, (100, 1))
    trans[12] = 0.9
    active = np.arange(24)
    pooled = nd._pool_active_rows("arithmetic", trans, base, active)
    assert pooled.max() <= trans[active].max() + 1e-12
    assert pooled.min() >= trans[active].min() - 1e-12
    # Một hàng nói 0,9 trên 24 hàng thì kết quả chỉ nhích lên chút.
    assert pooled[0] < 0.25


def test_log_odds_pooling_can_sharpen_past_every_input() -> None:
    base = np.full(100, 0.2)
    trans = np.tile(base, (100, 1))
    trans[12] = 0.9
    active = np.arange(24)
    pooled = nd._pool_active_rows("logodds", trans, base, active)
    # 23 hàng nói đúng bằng đường nền nên không đóng góp gì; hàng thứ 24 nói 0,9.
    assert pooled[0] == pytest.approx(0.9, abs=1e-6)


def test_pooling_with_no_active_rows_returns_the_baseline() -> None:
    base = np.linspace(0.1, 0.3, 100)
    trans = np.tile(base, (100, 1))
    for kind in nd.POOL_KINDS:
        np.testing.assert_allclose(
            nd._pool_active_rows(kind, trans, base, np.array([], dtype=int)), base
        )


def test_real_data_keeps_the_arithmetic_pool_by_a_wide_margin(real) -> None:
    dates, hit = real
    kind, diagnostics = nd.select_transition_pool(hit)
    assert kind == "arithmetic"
    # Dương nghĩa là log-odds TỆ HƠN. Biên rất rộng, không phải sát ngưỡng.
    assert diagnostics["t_statistic"] > 4.0
    assert diagnostics["holdout_days"] > 400


def test_a_strong_injected_relationship_switches_the_pool(real) -> None:
    _, hit = real
    kind, diagnostics = nd.select_transition_pool(_inject(hit, 2.0))
    assert kind == "logodds"
    assert diagnostics["t_statistic"] < -nd.SIGNIFICANCE_SIGMAS


def test_a_weak_injected_relationship_does_not_switch_the_pool(real) -> None:
    """Cổng 2 SE phải GIỮ bản đương nhiệm khi bằng chứng chưa đủ."""
    _, hit = real
    kind, _ = nd.select_transition_pool(_inject(hit, 0.25))
    assert kind == "arithmetic"


def test_short_history_falls_back_without_crashing() -> None:
    rng = np.random.default_rng(0)
    h = (rng.random((50, 100)) < 0.2378).astype(np.int8)
    kind, diagnostics = nd.select_transition_pool(h)
    assert kind == "arithmetic"
    assert diagnostics["holdout_days"] == 0


def test_the_transition_component_is_not_shrunk_a_second_time(real) -> None:
    """Phép kiểm hồi quy cho một lỗi THẬT đã lọt vào kho mã.

    Bản trước nhân thêm một cổng ``trans_rel`` dựng từ κ TRUNG VỊ của các hàng
    đang hoạt động. Khi chỉ một hàng mang tin, trung vị là 1 000 000 nên cổng
    đóng ở mức 0,0006 và trả xác suất về ĐÚNG BẰNG đường nền — xoá sạch một
    quan hệ mà chính bộ ước lượng đã tìm ra đúng (0,8729 so với nền 0,3539).

    ``trans`` đã là hậu nghiệm co ngót theo κ riêng của từng hàng rồi; co ngót
    lần hai bằng một đại lượng không có nghĩa thống kê nào là sai.
    """
    dates, hit = real
    h = _inject(hit, 2.0)
    moved, baselines = [], []
    for t in range(len(h) - 60, len(h)):
        if not h[t - 1, 12]:
            continue
        cur = nd.build_dynamics_signal(
            hit=h[:t], dates=dates[:t], mode="loto"
        ).current.sort_values("number")
        moved.append(float(cur["transition_prob"].to_numpy()[34]))
        baselines.append(float(cur["baseline_prob"].to_numpy()[34]))
    assert len(moved) > 5
    assert np.mean(moved) > np.mean(baselines) + 0.05


def test_the_gate_holds_the_incumbent_when_the_challenger_merely_leads(real) -> None:
    """Dẫn trước KHÔNG phải thắng — đó là toàn bộ ý nghĩa của cổng 2 SE.

    Ở mức tiêm +150 % (hạt giống 0 và 1), log-odds đã tốt hơn về trung bình
    nhưng chỉ ở mức t = -1,60 và t = -1,16. Nếu bỏ cổng và chỉ cần "tốt hơn là
    đổi" thì kiến trúc sẽ đổi ở đây, và đổi kiến trúc theo một chênh lệch
    dưới hai sai số chuẩn là cách nhiễu tự phong mình thành phát hiện.

    Đo ở các mức lân cận, ba hạt giống (dương nghĩa là log-odds tệ hơn):

        +120 %   +2,16   +0,60   +1,15
        +140 %   -0,00   -0,89   +0,73
        +150 %   -1,60   -1,16   -0,03
        +160 %   -2,65   -1,44   -0,53   ← hạt 0 vượt cổng, đổi
    """
    _, hit = real
    for seed, expected_t in ((0, -1.60), (1, -1.16)):
        kind, diagnostics = nd.select_transition_pool(_inject(hit, 1.5, seed=seed))
        t_statistic = diagnostics["t_statistic"]
        assert t_statistic < 0.0, "cần trường hợp log-odds ĐANG dẫn mới kiểm được"
        assert t_statistic > -nd.SIGNIFICANCE_SIGMAS, "cần dẫn mà CHƯA đủ 2 SE"
        assert t_statistic == pytest.approx(expected_t, abs=0.15)
        assert kind == "arithmetic"
