from __future__ import annotations

"""``_stack_days`` phải xếp đúng ma trận, và xếp trong thời gian TUYẾN TÍNH.

Bản trước lọc lại cả bảng bên trong vòng lặp ngày, tức O(số ngày²). Tệp này
không có phép kiểm nào trước khi tối ưu — nên bất biến được ghim ở đây là
TƯƠNG ĐƯƠNG với một bản tham chiếu viết thẳng theo định nghĩa, chứ không phải
"chạy không lỗi".
"""

import numpy as np
import pandas as pd
import pytest

from ensemble.learn_ensemble_weights import COMPONENT_COLS, _stack_days


def _history(days: list[str], *, seed: int = 0, shuffle: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({
        "target_date": np.repeat(days, 100),
        "number": np.tile(np.arange(100), len(days)),
        "y": rng.integers(0, 2, len(days) * 100).astype(float),
        **{c: rng.random(len(days) * 100) for c in COMPONENT_COLS},
    })
    return frame.sample(frac=1.0, random_state=seed).reset_index(drop=True) if shuffle else frame


def _reference(df: pd.DataFrame, days: list[str]):
    """Bản viết thẳng theo định nghĩa, chậm nhưng không thể hiểu sai."""
    day_list = sorted({d for d in days if d in set(df["target_date"].astype(str))})
    arrays = {c: np.zeros((len(day_list), 100)) for c in COMPONENT_COLS}
    labels = np.zeros((len(day_list), 100))
    for i, day in enumerate(day_list):
        sub = df[df["target_date"].astype(str) == day].sort_values("number")
        for c in COMPONENT_COLS:
            arrays[c][i] = sub[c].to_numpy(dtype=float)
        labels[i] = sub["y"].to_numpy(dtype=float)
    return arrays, labels, day_list


@pytest.mark.parametrize("shuffle", [False, True], ids=["đã sắp", "xáo trộn"])
def test_it_matches_a_straight_reference_implementation(shuffle: bool) -> None:
    days = [f"2026-01-{d:02d}" for d in range(1, 13)]
    df = _history(days, shuffle=shuffle)
    got_arrays, got_labels, got_days = _stack_days(df, days)
    ref_arrays, ref_labels, ref_days = _reference(df, days)

    assert got_days == ref_days
    np.testing.assert_allclose(got_labels, ref_labels)
    for column in COMPONENT_COLS:
        np.testing.assert_allclose(got_arrays[column], ref_arrays[column], err_msg=column)


def test_rows_land_on_the_row_of_their_own_day() -> None:
    """Chốt chặn cho lỗi hoán vị: khoá ngày phải quyết định HÀNG nào.

    Một bản gom nhóm mà dựa vào thứ tự nhóm thay vì tra khoá sẽ vẫn xanh ở
    phép kiểm tương đương nếu thứ tự tình cờ trùng. Ở đây mỗi ngày mang một
    giá trị nhận dạng riêng nên hoán vị là thấy ngay.
    """
    days = [f"2026-02-{d:02d}" for d in range(1, 6)]
    df = _history(days)
    for i, day in enumerate(days):
        df.loc[df["target_date"] == day, COMPONENT_COLS[0]] = float(i)

    arrays, _, day_list = _stack_days(df, days)
    assert day_list == days
    np.testing.assert_allclose(
        arrays[COMPONENT_COLS[0]][:, 0], np.arange(len(days), dtype=float)
    )


def test_days_absent_from_the_frame_are_dropped_not_zero_filled() -> None:
    """Ngày được yêu cầu mà không có dữ liệu phải BỊ LOẠI.

    Giữ lại và điền 0 sẽ đưa một kỳ quay không tồn tại vào phép học trọng số,
    với nhãn toàn 0 — tức dạy mô hình rằng hôm ấy không con nào về.
    """
    days = [f"2026-03-{d:02d}" for d in range(1, 5)]
    df = _history(days)
    asked = [*days, "2026-03-31"]

    arrays, labels, day_list = _stack_days(df, asked)
    assert day_list == days
    assert labels.shape == (len(days), 100)
    for column in COMPONENT_COLS:
        assert arrays[column].shape == (len(days), 100)


def test_it_stays_linear_in_the_number_of_days() -> None:
    """Bốn lần nhiều ngày hơn thì KHÔNG được chậm hơn bốn lần quá nhiều.

    Bản O(số ngày²) cũ ở đây chậm khoảng 11–12 lần. Ngưỡng 8 lần nằm giữa hai
    hình dạng nên nó phân biệt được chúng mà vẫn chịu được nhiễu đo trên máy
    chạy CI.
    """
    import time

    def elapsed(count: int) -> float:
        # Lấy lần nhanh nhất trong ba: nhiễu máy chạy chỉ làm CHẬM thêm, nên tối thiểu là
        # ước lượng ít nhiễu nhất. Một lần đo đơn trên CI ngày 23-10-2026 ra 0,0087 s ->
        # 0,264 s (30 lần) trong khi đo lặp lại cùng mã cho 3,1–4,5 lần.
        days = [f"{2026 + i // 336}-{1 + (i // 28) % 12:02d}-{1 + i % 28:02d}" for i in range(count)]
        df = _history(days)
        runs = []
        for _ in range(3):
            start = time.perf_counter()
            _stack_days(df, days)
            runs.append(time.perf_counter() - start)
        return min(runs)

    # 100 -> 400 ngày: đo 23-10-2026, bản tuyến tính ra 3,4–3,9 lần, bản lọc lại cả bảng
    # mỗi ngày ra 10,9–12,3 lần. Ở 60 -> 240 bản lọc lại chỉ ra 7,8–11,0 lần, sát ngưỡng.
    small = max(elapsed(100), 1e-4)
    large = elapsed(400)
    assert large / small < 8.0, (
        f"4 lần nhiều ngày hơn mà chậm {large / small:.1f} lần — mất tính tuyến tính "
        f"({small:.4f}s -> {large:.4f}s)"
    )
