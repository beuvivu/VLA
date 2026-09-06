"""Kiểm thử bộ quét cầu ghép chéo ngày và cổng kiểm định bắt buộc.

Hai nhóm test quan trọng nhất ở đây:

* **Hiệu chuẩn.** Trên lịch sử ngẫu nhiên thuần, tỉ lệ giả thuyết lọt ngưỡng
  p<0,05 phải xấp xỉ 5% ở *mọi* phép biến đổi. Bản đầu của bộ quét chấm cầu
  ``bo`` (đặt 8 con) bằng tỉ lệ nền của 1 con, cho 100% lọt ngưỡng — nghĩa là
  cổng chống phát hiện giả sẽ xác nhận toàn bộ họ giả thuyết.
* **Độ nhạy.** Một đường cầu được cài sẵn phải sống sót. Nếu thiếu test này,
  kết quả "không cầu nào sống sót" trên dữ liệu thật không phân biệt được với
  một bộ quét hỏng.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bridges import DigitTensor, BridgeScanner, default_lag_pairs
from bridges.firewall import FirewallGate
from bridges.scanner import baseline_rate_table, target_baseline_rate
from bridges.shadow import (
    KIND_BONG_AM,
    KIND_BONG_DUONG,
    KIND_THUC,
    apply_shadow,
    shadow_table,
)
from bridges.spec import CrossDayPatternSpec
from xsmb_domain import FIELD_WIDTHS, LOTO_DRAWS_PER_DAY, PRIZE_FIELDS


def _random_history(days: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frame = {"date": pd.date_range("2025-01-01", periods=days, freq="D")}
    for field, width in FIELD_WIDTHS:
        frame[field] = rng.integers(0, 10**width, size=days)
    return pd.DataFrame(frame)


# --- DigitTensor -----------------------------------------------------------


def test_tensor_matches_the_draw_contract() -> None:
    tensor = DigitTensor.from_raw(_random_history(60))
    assert tensor.n_positions == 107
    # Mỗi kỳ sinh đúng 27 con lô tô, một con mỗi giải.
    assert set(tensor.loto_counts.sum(axis=1).tolist()) == {LOTO_DRAWS_PER_DAY}
    assert tensor.loto_hits().dtype == bool
    assert ((tensor.de_index >= 0) & (tensor.de_index < 100)).all()


def test_tensor_refuses_a_history_with_calendar_gaps() -> None:
    """Ghép chéo ngày nói 'T−k'; chỉ số hàng chỉ bằng ngày lịch khi liền mạch."""
    frame = _random_history(30)
    with_gap = pd.concat([frame.iloc[:10], frame.iloc[12:]], ignore_index=True)
    with pytest.raises(ValueError, match="contiguous calendar days"):
        DigitTensor.from_raw(with_gap)


def test_tensor_counts_double_hits_separately() -> None:
    tensor = DigitTensor.from_raw(_random_history(200))
    assert (tensor.loto_double_hits() <= tensor.loto_hits()).all()
    assert tensor.loto_double_hits().sum() < tensor.loto_hits().sum()


# --- Bóng số ---------------------------------------------------------------


def test_shadow_tables_match_the_specification() -> None:
    duong = shadow_table(KIND_BONG_DUONG)
    am = shadow_table(KIND_BONG_AM)
    for source, target in ((0, 5), (1, 6), (2, 7), (3, 8), (4, 9)):
        assert duong[source] == target
    for source, target in ((0, 7), (1, 4), (2, 9), (3, 6), (5, 8)):
        assert am[source] == target


def test_shadow_is_an_involution() -> None:
    """Bóng của bóng là chính nó; sai điều này thì quét song song đếm trùng."""
    digits = np.arange(10, dtype=np.uint8)
    for kind in (KIND_BONG_DUONG, KIND_BONG_AM):
        assert np.array_equal(apply_shadow(kind, apply_shadow(kind, digits)), digits)
    assert np.array_equal(apply_shadow(KIND_THUC, digits), digits)


def test_shadow_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="bóng"):
        shadow_table("bong_tim")


# --- Đặc tả cầu ------------------------------------------------------------


def test_cross_day_spec_reports_its_span() -> None:
    assert CrossDayPatternSpec(0, 1, lag_a=1, lag_b=1).span == 1
    assert CrossDayPatternSpec(0, 1, lag_a=3, lag_b=2).span == 2
    assert "T-3" in CrossDayPatternSpec(0, 1, lag_a=3, lag_b=2).identifier


def test_default_lag_pairs_grow_the_family_one_span_at_a_time() -> None:
    assert default_lag_pairs(1) == ((1, 1),)
    assert default_lag_pairs(3) == ((1, 1), (2, 1), (3, 2))


# --- Đường cơ sở theo số con đặt cược --------------------------------------


def test_baseline_rate_grows_with_the_number_of_bets() -> None:
    """Đây là lỗi đã suýt lọt: chấm cầu 8 con bằng tỉ lệ nền của 1 con."""
    rates = [target_baseline_rate("loto", m) for m in (1, 2, 4, 8)]
    assert rates == sorted(rates)
    assert rates[0] == pytest.approx(0.2374, abs=1e-3)
    assert rates[-1] == pytest.approx(0.8947, abs=1e-3)
    # ĐB loại trừ nhau nên tỉ lệ tăng tuyến tính.
    assert target_baseline_rate("de", 8) == pytest.approx(0.08)


def test_two_nhay_baseline_is_below_the_single_hit_baseline() -> None:
    for m in (1, 2, 4, 8):
        assert target_baseline_rate("loto_2_nhay", m) < target_baseline_rate("loto", m)


def test_baseline_table_is_indexed_by_bet_count() -> None:
    table = baseline_rate_table("loto")
    assert table[0] == 0.0
    assert table[1] == pytest.approx(target_baseline_rate("loto", 1))


# --- Hiệu chuẩn: test lẽ ra đã bắt được lỗi --------------------------------


@pytest.mark.parametrize("target_type", ["loto", "de"])
def test_every_transformation_is_calibrated_under_pure_noise(target_type: str) -> None:
    """Trên nhiễu thuần, mọi phép biến đổi phải cho ~5% lọt ngưỡng p<0,05.

    Bản đầu của bộ quét cho 100% với ``bo`` và 99% với ``reverse_pair`` vì chấm
    chúng bằng tỉ lệ nền của giả thuyết một con. Ở mức đó, cổng chống phát hiện
    giả sẽ xác nhận toàn bộ họ và cả thiết kế mất tác dụng.
    """
    tensor = DigitTensor.from_raw(_random_history(320, seed=11))
    scanner = BridgeScanner(max_span=1, shadows=(KIND_THUC,))
    result = scanner.scan(tensor, target_type=target_type)

    by_transform = result.frame.groupby("transformation")["p_value"].apply(
        lambda s: float((s < 0.05).mean())
    )
    assert len(by_transform) == 4
    for transformation, rate in by_transform.items():
        assert rate < 0.12, f"{transformation} lọt {rate:.1%}, quá xa mức 5%"


def test_precision_tracks_the_expected_rate_under_pure_noise() -> None:
    tensor = DigitTensor.from_raw(_random_history(320, seed=13))
    result = BridgeScanner(max_span=1, shadows=(KIND_THUC,)).scan(tensor)
    frame = result.frame
    gap = (frame["precision"] - frame["expected_rate"]).abs().mean()
    assert gap < 0.02, f"lệch trung bình {gap:.4f} giữa quan sát và kỳ vọng"


# --- Độ nhạy: bộ quét có tìm được tín hiệu thật không ----------------------


def _plant_bridge(days: int, seed: int = 3) -> pd.DataFrame:
    """Cài một đường cầu chắc chắn: hai chữ số đầu của ĐB hôm trước ra prize7_1.

    Vị trí nguồn 0 và 1 là ``special.d0`` và ``special.d1``, nên cặp
    (0, 1, lag 1, concat) sẽ trúng mọi ngày.
    """
    frame = _random_history(days, seed=seed)
    special = frame["special"].to_numpy()
    planted = (special // 1000) % 100  # hai chữ số đầu của giải ĐB 5 chữ số
    frame.loc[1:, "prize7_1"] = planted[:-1]
    return frame


def test_scanner_finds_a_planted_bridge() -> None:
    """Không có test này, 'không cầu nào sống sót' và 'bộ quét hỏng' giống hệt nhau."""
    tensor = DigitTensor.from_raw(_plant_bridge(200))
    scanner = BridgeScanner(max_span=1, shadows=(KIND_THUC,))
    result = scanner.scan(tensor, target_type="loto")

    planted = result.frame[
        (result.frame["position_a"] == 0)
        & (result.frame["position_b"] == 1)
        & (result.frame["transformation"] == "concat")
    ]
    assert len(planted) == 1
    assert planted["precision"].iloc[0] == pytest.approx(1.0)
    assert planted["current_streak"].iloc[0] == result.n_days_evaluated


def test_firewall_lets_a_planted_bridge_through() -> None:
    tensor = DigitTensor.from_raw(_plant_bridge(200))
    scanner = BridgeScanner(max_span=1, shadows=(KIND_THUC,))
    result = scanner.scan(tensor, target_type="loto")
    survivors = FirewallGate(permutations=5).screen(result, tensor, scanner)

    assert not survivors.is_empty
    assert survivors.tested == result.n_hypotheses
    kept = survivors.bridges
    assert ((kept["position_a"] == 0) & (kept["position_b"] == 1)).any()


# --- Cổng kiểm định --------------------------------------------------------


def test_firewall_rejects_everything_on_pure_noise() -> None:
    tensor = DigitTensor.from_raw(_random_history(320, seed=17))
    scanner = BridgeScanner(max_span=1, shadows=(KIND_THUC,))
    result = scanner.scan(tensor, target_type="loto")
    survivors = FirewallGate(permutations=3).screen(result, tensor, scanner)

    assert survivors.is_empty
    # Số giả thuyết đã thử luôn được mang theo, kể cả khi không ai sống sót.
    assert survivors.tested == result.n_hypotheses
    assert "đã thử" in survivors.describe()


def test_null_distribution_is_taken_over_the_whole_family() -> None:
    """Phân phối rỗng phải lấy trên toàn họ, không trên phần đã sàng lọc.

    Lấy trên phần sống sót — vốn được chọn *vì* mạnh — sẽ hạ thấp phân phối rỗng
    một cách giả tạo và cho gần như mọi tập sống sót đều 'đạt'.
    """
    tensor = DigitTensor.from_raw(_random_history(200, seed=19))
    scanner = BridgeScanner(max_span=1, shadows=(KIND_THUC,))
    target = scanner._target_for(tensor, "loto")

    whole_family = scanner.family_max_skill(tensor, target, "loto")
    result = scanner.scan(tensor, target_type="loto")
    best_in_frame = float((result.frame["precision"] - result.frame["expected_rate"]).max())
    assert whole_family == pytest.approx(best_in_frame, abs=1e-9)


def test_firewall_rejects_an_invalid_q_value() -> None:
    with pytest.raises(ValueError, match="q_value"):
        FirewallGate(q_value=1.5)


def test_scanner_rejects_unknown_configuration() -> None:
    with pytest.raises(ValueError, match="bóng"):
        BridgeScanner(shadows=("bong_tim",))
    with pytest.raises(ValueError, match="biến đổi"):
        BridgeScanner(transformations=("pascal",))
    with pytest.raises(ValueError, match="mục tiêu"):
        BridgeScanner(max_span=1).scan(
            DigitTensor.from_raw(_random_history(40)), target_type="xien"
        )


def test_scanner_refuses_history_shorter_than_the_longest_lag() -> None:
    tensor = DigitTensor.from_raw(_random_history(3))
    with pytest.raises(ValueError, match="quá ngắn"):
        BridgeScanner(max_span=5).scan(tensor)


def test_prize_fields_cover_every_position_used_by_the_scanner() -> None:
    """Bộ quét đánh số vị trí theo luồng chữ số phẳng; hai bên phải khớp."""
    tensor = DigitTensor.from_raw(_random_history(40))
    assert len(tensor.position_labels) == tensor.n_positions
    assert tensor.position_labels[0].startswith(PRIZE_FIELDS[0])
