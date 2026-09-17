from __future__ import annotations

"""Log tầm quan trọng đặc trưng phải đo ĐÚNG hai đại lượng, và không nói quá.

Bản đầu của module này có ba lỗi, cả ba lộ ra khi đọc kỹ đầu ra thay vì tin nó:

1. Bỏ một thành phần ra khiến 212/231 kỳ loto không còn thành phần nào (cầu và
   thống kê chỉ có từ 2026-08-12), nên tổng trọng số về 0, vector về 0, và
   logloss nổ — đo được Δ = +2,51 trong khi cả metric chỉ ~0,546.
2. Δ cỡ 1e-8 vẫn được dán nhãn "có ích rõ rệt" chỉ vì khoảng tin bootstrap hẹp
   hơn nó — ý nghĩa THỐNG KÊ bị nhầm thành ý nghĩa THỰC TIỄN.
3. Bootstrap lấy mẫu trên toàn bộ ngày kể cả ngày không so được.
"""

import numpy as np
import pandas as pd
import pytest

from ensemble_components import COMPONENT_KEYS
from ensemble_utils import EnsembleWeights, floor_distribution
from feature_attribution import (
    MATERIAL_EFFECT_FLOOR,
    _day_matrices,
    decision_share,
    leave_one_out,
    per_number_attribution,
)


def _history(days: int, *, only_ml_after: int | None = None, seed: int = 0) -> pd.DataFrame:
    """Lịch sử giả với tuỳ chọn 'chỉ có ml' ở phần đầu, đúng như kho thật."""
    rng = np.random.default_rng(seed)
    rows = []
    for index in range(days):
        day = f"2026-01-{index + 1:02d}"
        winner = int(rng.integers(0, 100))
        sparse = only_ml_after is not None and index < only_ml_after
        for number in range(100):
            rows.append({
                "target_date": day,
                "number": number,
                "y": 1.0 if number == winner else 0.0,
                "p_ml": 0.01 + rng.normal(0, 0.0005),
                "p_cau": 0.0 if sparse else 0.01 + rng.normal(0, 0.0005),
                "p_stat": 0.0 if sparse else 0.01 + rng.normal(0, 0.0005),
                "p_active": 0.0 if sparse else 0.01 + rng.normal(0, 0.0005),
                "p_stable": 0.0 if sparse else 0.01 + rng.normal(0, 0.0005),
            })
    return pd.DataFrame(rows)


def _weights() -> np.ndarray:
    w = EnsembleWeights(w_ml=0.25, w_cau=0.30, w_stat=0.20, w_active=0.125, w_stable=0.125)
    return np.asarray([getattr(w, f"w_{key}") for key in COMPONENT_KEYS], dtype=float)


def test_dropping_a_component_never_compares_a_day_it_emptied() -> None:
    """Chốt chặn cho lỗi 1: Δ không được nổ vì tổng trọng số về 0.

    Ở đây 20 kỳ đầu chỉ có ``ml``. Bỏ ``ml`` ra thì 20 kỳ ấy trắng thành phần.
    Nếu vẫn đem so, logloss của chúng nhảy lên hàng chục và Δ vượt hẳn metric.
    """
    history = _history(30, only_ml_after=20)
    days, vectors, masks, labels = _day_matrices(history, "de")
    rows = leave_one_out(
        vectors, masks, labels, _weights(),
        mode="de", rng=np.random.default_rng(1),
    )
    ml_row = next(r for r in rows if r["component"] == "ml")
    assert ml_row["days_comparable"] == 10, ml_row
    assert ml_row["days_comparable"] < ml_row["days_total"]
    assert abs(ml_row["logloss_delta"]) < 1.0, (
        f"Δ = {ml_row['logloss_delta']:+.4f} — dấu hiệu kỳ trắng thành phần "
        "vẫn bị đem so"
    )


def test_a_statistically_tiny_effect_is_not_called_useful() -> None:
    """Chốt chặn cho lỗi 2: khác 0 không đủ, phải ĐÁNG KỂ.

    Bản đầu của phép kiểm này chỉ khẳng định một HÀM Ý ("nếu đáng kể thì phải
    vượt sàn"), nên khi không thành phần nào khác 0 thì thân vòng lặp không bao
    giờ chạy và phép kiểm xanh một cách RỖNG — đột biến gỡ sàn đã lọt qua.

    Ở đây dựng hẳn một thành phần tốt hơn một cách CÓ HỆ THỐNG nhưng bé xíu:
    nó cộng thêm 1e-7 cho đúng con sẽ về, ở mọi kỳ. Hiệu ứng nhất quán nên
    khoảng tin loại được 0; độ lớn thì nhỏ hơn sàn 0,1% hàng nghìn lần.
    """
    days_count = 60
    rng = np.random.default_rng(11)
    rows_data = []
    for index in range(days_count):
        day = f"2026-03-{index + 1:02d}" if index < 31 else f"2026-04-{index - 30:02d}"
        winner = int(rng.integers(0, 100))
        for number in range(100):
            shared = 0.01 + rng.normal(0, 0.0004)
            rows_data.append({
                "target_date": day, "number": number,
                "y": 1.0 if number == winner else 0.0,
                "p_ml": shared,
                # nhích ĐÚNG con sẽ về, mọi kỳ: nhất quán nhưng bé xíu
                "p_cau": shared + (1e-7 if number == winner else 0.0),
                "p_stat": shared, "p_active": shared, "p_stable": shared,
            })
    history = pd.DataFrame(rows_data)

    days, vectors, masks, labels = _day_matrices(history, "de")
    rows = leave_one_out(
        vectors, masks, labels, _weights(),
        mode="de", rng=np.random.default_rng(2),
    )
    cau = next(r for r in rows if r["component"] == "cau")

    assert cau["distinguishable_from_zero"], (
        "fixture phải cho một hiệu ứng KHÁC 0 về mặt thống kê, nếu không phép "
        f"kiểm lại rỗng: {cau}"
    )
    assert cau["logloss_relative"] < MATERIAL_EFFECT_FLOOR, cau
    assert not cau["materially_useful"], (
        f"Δ chỉ {cau['logloss_relative'] * 100:.6f}% của metric mà vẫn bị gọi "
        "là có ích — ý nghĩa thống kê đang bị nhầm thành ý nghĩa thực tiễn"
    )

    for row in rows:
        if row.get("logloss_delta") is None:
            continue
        if row["materially_useful"]:
            assert row["logloss_relative"] >= MATERIAL_EFFECT_FLOOR, row
            assert row["distinguishable_from_zero"], row


def test_decision_share_measures_deviation_not_weight() -> None:
    """Thành phần PHẲNG không được nhận công, dù trọng số có lớn.

    Trọng số hiệu dụng một mình không trả lời "ai chọn con số": cả năm thành
    phần đều có trung bình xấp xỉ nền, nên chỉ ĐỘ LỆCH tạo ra thứ hạng.
    """
    rng = np.random.default_rng(3)
    vectors = np.zeros((5, len(COMPONENT_KEYS), 100))
    vectors[:, :, :] = 0.01
    # chỉ `stat` có độ lệch; các thành phần khác phẳng tuyệt đối
    vectors[:, COMPONENT_KEYS.index("stat"), :] = 0.01 + rng.normal(0, 0.002, (5, 100))
    masks = np.ones((5, len(COMPONENT_KEYS)))
    share = decision_share(vectors, masks, _weights(), base_rate=0.01)
    assert share["stat"] > 0.99, share
    for key in COMPONENT_KEYS:
        if key != "stat":
            assert share[key] < 0.01, (key, share)


def test_per_number_drivers_only_list_available_components() -> None:
    history = _history(12, only_ml_after=6)
    days, vectors, masks, _ = _day_matrices(history, "de")
    early = per_number_attribution(vectors, masks, _weights(), day_position=0, base_rate=0.01)
    assert early, "phải có ít nhất một con được xếp hạng"
    assert {d["component"] for d in early[0]["drivers"]} == {"ml"}, early[0]["drivers"]


def test_the_floor_never_declares_an_outcome_impossible() -> None:
    """``floor_distribution`` là lý do bảng quy trách đo đúng mô hình xuất bản."""
    ranking_not_distribution = np.zeros(100)
    ranking_not_distribution[:42] = 1.0 / 42
    floored = floor_distribution(ranking_not_distribution)
    assert floored.min() > 0.0
    assert floored.min() == pytest.approx(0.05 / 100)
    assert floored.sum() == pytest.approx(1.0)
    # Thứ hạng giữ nguyên: sàn chỉ chặn đuôi dưới.
    order_before = np.argsort(-ranking_not_distribution)[:42]
    order_after = np.argsort(-floored)[:42]
    assert set(order_before) == set(order_after)


def test_the_floor_is_a_no_op_on_a_healthy_distribution() -> None:
    """Rào an toàn không được làm méo đầu vào lành.

    Đo trên dự đoán thật 2026-09-18: lệch tương đối lớn nhất 0,118% và thứ hạng
    10 con đầu không đổi.
    """
    healthy = np.full(100, 0.01)
    assert floor_distribution(healthy) == pytest.approx(healthy)


@pytest.mark.parametrize("share", [-0.1, 1.0, 1.5])
def test_an_invalid_floor_share_is_refused(share: float) -> None:
    with pytest.raises(ValueError, match="share"):
        floor_distribution(np.full(100, 0.01), share=share)
