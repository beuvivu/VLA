"""Kiểm thử bốn extractor đặc trưng soi cầu và khung đăng ký.

Test quan trọng nhất ở đây là **tính nhân quả**: đặc trưng tính tại ngày neo
không được đổi khi tương lai đổi. Rò rỉ tương lai làm mọi phép đo phía sau trở
nên vô nghĩa theo cách rất khó phát hiện — mô hình trông xuất sắc trên backtest
và sụp đổ khi chạy thật.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bridges import DigitTensor
from features import (
    DoubleHitBridgeExtractor,
    FeatureContext,
    FeatureRegistry,
    GeometricBridgeExtractor,
    PatternMemoryExtractor,
    SpecialSetExtractor,
    default_registry,
    pascal_reduce,
    touches,
)
from features.base import validate_block
from xsmb_domain import FIELD_WIDTHS


def _history(days: int, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frame = {"date": pd.date_range("2025-01-01", periods=days, freq="D")}
    for field, width in FIELD_WIDTHS:
        frame[field] = rng.integers(0, 10**width, size=days)
    return pd.DataFrame(frame)


def _tensor(days: int = 220, seed: int = 5) -> DigitTensor:
    return DigitTensor.from_raw(_history(days, seed))


ALL_EXTRACTORS = [
    GeometricBridgeExtractor,
    DoubleHitBridgeExtractor,
    PatternMemoryExtractor,
    SpecialSetExtractor,
]


# --- Nhân quả: test quan trọng nhất ---------------------------------------


@pytest.mark.parametrize("factory", ALL_EXTRACTORS)
def test_extractor_cannot_see_the_future(factory) -> None:
    """Đổi dữ liệu SAU ngày neo không được làm đặc trưng đổi theo."""
    frame = _history(220)
    anchor = 150

    baseline = factory().extract(
        FeatureContext(tensor=DigitTensor.from_raw(frame), anchor_index=anchor)
    )

    tampered = frame.copy()
    rng = np.random.default_rng(99)
    for field, width in FIELD_WIDTHS:
        tampered.loc[anchor + 1 :, field] = rng.integers(
            0, 10**width, size=len(tampered) - anchor - 1
        )
    after = factory().extract(
        FeatureContext(tensor=DigitTensor.from_raw(tampered), anchor_index=anchor)
    )
    assert np.array_equal(baseline, after), f"{factory.__name__} đọc được tương lai"


def test_context_refuses_an_anchor_outside_history() -> None:
    tensor = _tensor(50)
    with pytest.raises(ValueError, match="anchor_index"):
        FeatureContext(tensor=tensor, anchor_index=50)


def test_context_windows_stop_at_the_anchor() -> None:
    tensor = _tensor(80)
    ctx = FeatureContext(tensor=tensor, anchor_index=40)
    assert ctx.history_length == 41
    assert ctx.hits().shape[0] == 41
    assert ctx.hits(10).shape[0] == 10
    assert np.array_equal(ctx.last_digits(), tensor.values[40])


# --- Hợp đồng chung --------------------------------------------------------


@pytest.mark.parametrize("factory", ALL_EXTRACTORS)
def test_extractor_honours_the_shape_contract(factory) -> None:
    extractor = factory()
    block = extractor.extract(FeatureContext(tensor=_tensor(), anchor_index=200))
    assert block.shape == (100, len(extractor.feature_names))
    assert np.all(np.isfinite(block))
    assert validate_block(block, extractor).dtype == np.float64


@pytest.mark.parametrize("factory", ALL_EXTRACTORS)
def test_extractor_works_on_a_very_short_history(factory) -> None:
    """Những ngày đầu chưa đủ lịch sử vẫn phải trả về khối hợp lệ, không nổ."""
    block = factory().extract(FeatureContext(tensor=_tensor(12), anchor_index=1))
    assert np.all(np.isfinite(block))


def test_validate_block_rejects_non_finite_values() -> None:
    extractor = GeometricBridgeExtractor()
    bad = np.full((100, len(extractor.feature_names)), np.nan)
    with pytest.raises(ValueError, match="không hữu hạn"):
        validate_block(bad, extractor)


def test_validate_block_rejects_a_wrong_shape() -> None:
    extractor = GeometricBridgeExtractor()
    with pytest.raises(ValueError, match="hợp đồng"):
        validate_block(np.zeros((100, 1)), extractor)


# --- Cầu hình học ----------------------------------------------------------


def test_pascal_reduce_follows_the_triangle() -> None:
    # [1, 2, 3] -> [(1+2)%10, (2+3)%10] = [3, 5] -> 35
    assert pascal_reduce(np.array([1, 2, 3])) == 35
    # Đã hai chữ số thì giữ nguyên.
    assert pascal_reduce(np.array([7, 4])) == 74
    # Modulo 10 áp ở từng bước, không chỉ ở bước cuối.
    assert pascal_reduce(np.array([9, 9, 9])) == 88


def test_pascal_reduce_needs_at_least_two_digits() -> None:
    with pytest.raises(ValueError, match="hai chữ số"):
        pascal_reduce(np.array([4]))


def test_geometric_marks_exactly_one_pascal_number() -> None:
    block = GeometricBridgeExtractor().extract(FeatureContext(tensor=_tensor(), anchor_index=100))
    assert block[:, 0].sum() == 1.0


def test_geometric_weights_form_a_distribution() -> None:
    block = GeometricBridgeExtractor().extract(FeatureContext(tensor=_tensor(), anchor_index=100))
    for weight_column in (2, 4):
        total = block[:, weight_column].sum()
        assert total == pytest.approx(1.0) or total == pytest.approx(0.0)


# --- Cầu hai nháy ----------------------------------------------------------


def test_double_hit_excess_is_measured_against_the_theoretical_rate() -> None:
    """'Hay nổ kép' chỉ có nghĩa khi đối chiếu với mức ngẫu nhiên."""
    block = DoubleHitBridgeExtractor().extract(FeatureContext(tensor=_tensor(), anchor_index=200))
    rate, excess = block[:, 0], block[:, 1]
    assert np.allclose(rate - excess, rate[0] - excess[0])
    # Trên nhiễu thuần, phần vượt phải dao động quanh 0.
    assert abs(float(excess.mean())) < 0.05


def test_partner_correlation_excludes_a_number_from_itself() -> None:
    """Không trừ đường chéo thì mọi con tự tương quan hoàn hảo với chính nó."""
    block = DoubleHitBridgeExtractor().extract(FeatureContext(tensor=_tensor(), anchor_index=200))
    assert np.abs(block[:, 2]).max() < 0.5


# --- Bạc nhớ và nhịp gan ---------------------------------------------------


def test_memory_probability_is_laplace_smoothed() -> None:
    """Mẫu mỏng không được phép phát ra xác suất 0 hoặc 1."""
    block = PatternMemoryExtractor().extract(FeatureContext(tensor=_tensor(30), anchor_index=25))
    probability = block[:, 0]
    assert (probability > 0).all()
    assert (probability < 1).all()


def test_gap_signals_are_consistent_with_each_other() -> None:
    block = PatternMemoryExtractor().extract(FeatureContext(tensor=_tensor(), anchor_index=200))
    current, ratio = block[:, 2], block[:, 4]
    assert (current >= 0).all()
    assert (ratio >= 0).all()
    # Con vừa về hôm neo có khoảng cách 0.
    assert current.min() == 0.0


def test_gap_zscore_flags_a_number_that_is_overdue() -> None:
    """Cài một con về đều đặn rồi cắt: Z-score của nó phải bật lên rõ rệt."""
    frame = _history(200, seed=21)
    # prize7_1 luân phiên đúng 5 ngày một lần trong nửa đầu, rồi dừng hẳn.
    frame.loc[:, "prize7_1"] = 99
    frame.loc[np.arange(200) % 5 == 0, "prize7_1"] = 42
    frame.loc[150:, "prize7_1"] = 99
    tensor = DigitTensor.from_raw(frame)
    block = PatternMemoryExtractor().extract(FeatureContext(tensor=tensor, anchor_index=199))
    assert block[42, 3] > 2.0, "con quá hạn không được đánh dấu"


# --- Cầu Đặc Biệt và dàn đề ------------------------------------------------


def test_touches_reads_head_and_tail() -> None:
    assert touches(7) == (0, 7)
    assert touches(68) == (6, 8)


def test_special_set_rates_stay_within_zero_and_one() -> None:
    block = SpecialSetExtractor().extract(FeatureContext(tensor=_tensor(), anchor_index=200))
    assert (block >= 0).all() and (block <= 1).all()


def test_dan_has_the_requested_size_and_no_duplicates() -> None:
    ctx = FeatureContext(tensor=_tensor(), anchor_index=200)
    extractor = SpecialSetExtractor()
    for size in (36, 64):
        dan = extractor.build_dan(ctx, size)
        assert len(dan) == size
        assert len(set(dan)) == size
        assert all(len(item) == 2 for item in dan)


def test_dan_is_nested_by_size() -> None:
    """Dàn nhỏ phải nằm trong dàn lớn; nếu không thì thứ hạng không nhất quán."""
    ctx = FeatureContext(tensor=_tensor(), anchor_index=200)
    extractor = SpecialSetExtractor()
    assert set(extractor.build_dan(ctx, 36)) <= set(extractor.build_dan(ctx, 64))


def test_dan_rejects_an_impossible_size() -> None:
    ctx = FeatureContext(tensor=_tensor(), anchor_index=200)
    with pytest.raises(ValueError, match="kích thước dàn"):
        SpecialSetExtractor().build_dan(ctx, 101)


# --- Sổ đăng ký ------------------------------------------------------------


def test_registry_builds_one_matrix_from_every_extractor() -> None:
    registry = default_registry()
    matrix = registry.build_matrix(FeatureContext(tensor=_tensor(), anchor_index=200))
    assert matrix.values.shape[0] == 100
    assert matrix.n_features == len(matrix.columns)
    assert set(matrix.groups) == set(registry.names())
    # Các nhóm phải phủ kín ma trận, không chồng lấn và không để hở cột nào.
    spans = sorted(matrix.groups.values())
    assert spans[0][0] == 0
    assert spans[-1][1] == matrix.n_features
    for (_, stop), (start, _) in zip(spans, spans[1:], strict=False):
        assert stop == start


def test_registry_column_names_are_prefixed_by_group() -> None:
    matrix = default_registry().build_matrix(FeatureContext(tensor=_tensor(), anchor_index=200))
    for name, (start, stop) in matrix.groups.items():
        assert all(c.startswith(f"{name}.") for c in matrix.columns[start:stop])


def test_registry_group_values_match_the_slice() -> None:
    matrix = default_registry().build_matrix(FeatureContext(tensor=_tensor(), anchor_index=200))
    assert np.array_equal(
        matrix.group_values("geometric"), matrix.values[:, matrix.group_slice("geometric")]
    )
    with pytest.raises(KeyError, match="nhóm đặc trưng"):
        matrix.group_slice("khong_co")


def test_registry_rejects_duplicate_names_but_allows_replacement() -> None:
    registry = FeatureRegistry()
    registry.register(GeometricBridgeExtractor())
    with pytest.raises(ValueError, match="trùng tên"):
        registry.register(GeometricBridgeExtractor())
    registry.replace(GeometricBridgeExtractor())
    assert len(registry) == 1
    registry.unregister("geometric")
    assert len(registry) == 0


def test_registry_refuses_to_build_when_empty() -> None:
    with pytest.raises(ValueError, match="chưa đăng ký"):
        FeatureRegistry().build_matrix(FeatureContext(tensor=_tensor(40), anchor_index=20))


def test_registry_reports_unknown_extractor() -> None:
    with pytest.raises(KeyError, match="chưa đăng ký"):
        default_registry().get("khong_ton_tai")
