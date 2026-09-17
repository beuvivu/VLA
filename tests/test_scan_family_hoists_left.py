from __future__ import annotations

"""``scan_family`` phải dựng ma trận ``left`` MỘT lần cho mỗi ``op_a``.

``left`` chỉ phụ thuộc ``op_a`` (và ``lag_a``), nhưng bản trước dựng nó bên
TRONG vòng ``op_b``, nên mỗi ``op_a`` bị dựng lại 3 lần: 18 lần thay vì 6.

Profile trên lịch sử 4 208 kỳ: ``scan_family`` chiếm 44,4 trong 49,5 giây
(90%), phần lớn là phép tra chỉ số nâng cao dựng ``left`` — không phải phép
nhân ma trận, vốn đã nằm trong BLAS. Sau khi nâng ra: tottime 41,7 -> 24,1
giây, cả script 47 -> 36 giây, và 24 giây còn lại là phép nhân thật
(1,02 TFLOP ở khoảng 42 GFLOPS đơn luồng).

THỨ TỰ KHỐI là bất biến quan trọng nhất: ``hits`` đánh chỉ số theo vị trí
luật, nên đổi thứ tự vòng lặp mà không giữ thứ tự khối sẽ gán sai số liệu cho
mọi luật — im lặng, không ngoại lệ nào.
"""

import numpy as np
import pytest

from bong_bridge_lab import (
    DEFAULT_LAG_PAIRS,
    DIGIT_OPS,
    N_SLOTS,
    OP_NAMES,
    _one_hot,
    scan_family,
)


def _inputs(days: int = 60, seed: int = 0):
    rng = np.random.default_rng(seed)
    digits = rng.integers(0, 10, size=(days, N_SLOTS)).astype(np.int64)
    targets = np.zeros((days, 10, 10), dtype=np.float32)
    for row in range(days):
        for _ in range(27):
            targets[row, rng.integers(0, 10), rng.integers(0, 10)] = 1.0
    day_index = np.arange(10, days)
    return digits, targets, day_index


def _reference(digits, targets, *, day_index, lag_pairs, op_names):
    """Bản lồng ba vòng viết thẳng theo định nghĩa, dựng ``left`` mỗi lượt."""
    blocks, labels = [], []
    flat_targets = targets[day_index].reshape(len(day_index), 100)
    for lag_a, lag_b in lag_pairs:
        src_a = digits[day_index - lag_a]
        src_b = digits[day_index - lag_b]
        for op_b in op_names:
            hot_b = _one_hot(DIGIT_OPS[op_b][src_b])
            for op_a in op_names:
                coded_a = DIGIT_OPS[op_a][src_a]
                left = flat_targets.reshape(len(day_index), 10, 10)[
                    np.arange(len(day_index))[None, :], coded_a.T
                ]
                blocks.append(left.reshape(N_SLOTS, -1) @ hot_b.T)
                labels.append((op_a, op_b, lag_a, lag_b))
    return np.stack(blocks), tuple(labels)


def test_it_matches_the_straight_nested_reference() -> None:
    digits, targets, day_index = _inputs()
    got = scan_family(
        digits, targets, day_index=day_index,
        lag_pairs=DEFAULT_LAG_PAIRS, op_names=OP_NAMES,
    )
    want_hits, want_labels = _reference(
        digits, targets, day_index=day_index,
        lag_pairs=DEFAULT_LAG_PAIRS, op_names=OP_NAMES,
    )
    assert got.labels == want_labels
    assert got.trials == len(day_index)
    np.testing.assert_allclose(got.hits, want_hits)


def test_the_block_order_follows_lag_then_op_b_then_op_a() -> None:
    """``hits`` đánh chỉ số theo vị trí luật, nên thứ tự là phần của hợp đồng."""
    digits, targets, day_index = _inputs(days=40, seed=3)
    result = scan_family(
        digits, targets, day_index=day_index,
        lag_pairs=DEFAULT_LAG_PAIRS, op_names=OP_NAMES,
    )
    expected = [
        (op_a, op_b, lag_a, lag_b)
        for lag_a, lag_b in DEFAULT_LAG_PAIRS
        for op_b in OP_NAMES
        for op_a in OP_NAMES
    ]
    assert list(result.labels) == expected
    assert result.hits.shape == (len(expected), N_SLOTS, N_SLOTS)


@pytest.mark.parametrize("op_a", OP_NAMES)
def test_every_op_a_gets_its_own_left_not_a_shared_one(op_a: str) -> None:
    """Chốt chặn cho lỗi dùng chung sai: mỗi op_a phải có ma trận riêng.

    Một bản nâng sai — dựng ``left`` một lần rồi dùng cho MỌI ``op_a`` — vẫn
    nhanh y như bản đúng và không ném ngoại lệ nào. Chỉ số liệu là sai.
    """
    digits, targets, day_index = _inputs(days=50, seed=7)
    single = scan_family(
        digits, targets, day_index=day_index,
        lag_pairs=((1, 1),), op_names=(op_a,),
    )
    full = scan_family(
        digits, targets, day_index=day_index,
        lag_pairs=((1, 1),), op_names=OP_NAMES,
    )
    position = list(full.labels).index((op_a, op_a, 1, 1))
    np.testing.assert_allclose(full.hits[position], single.hits[0])


def test_distinct_ops_really_produce_distinct_counts() -> None:
    """Nếu ba phép cho cùng kết quả thì hai phép kiểm trên mất sức phân biệt."""
    digits, targets, day_index = _inputs(days=80, seed=11)
    result = scan_family(
        digits, targets, day_index=day_index,
        lag_pairs=((1, 1),), op_names=OP_NAMES,
    )
    sums = {
        label[0]: float(result.hits[i].sum())
        for i, label in enumerate(result.labels)
        if label[0] == label[1]
    }
    assert len(set(sums.values())) > 1, sums
