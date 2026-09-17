from __future__ import annotations

"""``_reverse_pair_frequency`` phải tuyến tính theo số hàng, không theo P × N.

Bản trước lồng hai vòng ``kỳ × 50 cặp``, và MỖI lượt quét lại toàn bảng bằng
``df.loc[df["period_key"] == period_key, a]``. Với P kỳ trên N hàng, chi phí là
O(P · 50 · N); ở ``period="day"`` thì P ≈ N nên thành O(50 · N²).

Profile trên lịch sử 4 207 kỳ: hàm này chiếm 606,8 trong 630,8 giây (96,2%) của
``statistical_matrices.py``, 151,7 giây mỗi lần gọi. Sau khi gom một lần và
tính cả 50 cặp trên ma trận boolean, cả script chạy 20 giây thay vì 342.
"""

import time

import numpy as np
import pandas as pd
import pytest

from number_reference import all_cap_loto_50
from statistical_matrices import NUMBER_COLS, _prepare_sparse, _period_series
from statistical_matrices import _reverse_pair_frequency


def _sparse(draws: int, *, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", periods=draws, freq="D").strftime("%Y-%m-%d")
    grid = np.zeros((draws, 100), dtype=int)
    for row in range(draws):
        grid[row, rng.choice(100, size=27, replace=False)] = 1
    return pd.DataFrame({"date": dates, **{str(n): grid[:, n] for n in range(100)}})


def _reference(sparse_df: pd.DataFrame, *, period: str) -> pd.DataFrame:
    """Bản lồng hai vòng viết thẳng theo định nghĩa: chậm, nhưng rõ ràng."""
    df = _prepare_sparse(sparse_df)
    if df.empty:
        return pd.DataFrame()
    df["period_key"] = _period_series(df["date"], period)
    counts = df.groupby("period_key", sort=True)[NUMBER_COLS].sum()
    draws = df.groupby("period_key", sort=True)["date"].nunique()
    pairs = sorted(tuple(sorted(int(m) for m in f)) for f in all_cap_loto_50())

    rows = []
    for key in counts.index:
        for a, b in pairs:
            freq = int(counts.loc[key, a] + counts.loc[key, b])
            a_hit = df.loc[df["period_key"] == key, a] > 0
            b_hit = df.loc[df["period_key"] == key, b] > 0
            rows.append({
                "period_kind": period, "period_key": key,
                "draws": int(draws.loc[key]), "pair": f"{a:02d}-{b:02d}",
                "a": a, "b": b, "freq": freq,
                "days_hit": int((a_hit | b_hit).sum()),
                "cooccur_days": int((a_hit & b_hit).sum()),
                "avg_per_draw": freq / max(int(draws.loc[key]), 1),
            })
    out = pd.DataFrame(rows)
    out["rank_in_period"] = (
        out.groupby("period_key")["freq"].rank(method="dense", ascending=False).astype(int)
    )
    return out.sort_values(["period_key", "rank_in_period", "pair"]).reset_index(drop=True)


@pytest.mark.parametrize("period", ["year", "month", "week", "day"])
def test_it_matches_the_straight_nested_reference(period: str) -> None:
    sparse = _sparse(200)
    fast = _reverse_pair_frequency(sparse, period=period)
    slow = _reference(sparse, period=period)

    assert list(fast.columns) == list(slow.columns)
    assert len(fast) == len(slow)
    for column in slow.columns:
        if pd.api.types.is_numeric_dtype(slow[column]):
            np.testing.assert_allclose(
                fast[column].to_numpy(dtype=float),
                slow[column].to_numpy(dtype=float),
                err_msg=f"{period}/{column}",
            )
        else:
            assert fast[column].equals(slow[column]), f"{period}/{column}"


def test_every_period_yields_exactly_fifty_pairs() -> None:
    """Đúng 50 họ cặp, không có cặp tự-ghép như 77-77."""
    out = _reverse_pair_frequency(_sparse(120), period="month")
    per_period = out.groupby("period_key")["pair"].nunique()
    assert set(per_period.unique()) == {50}, per_period.to_dict()
    assert not (out["a"] == out["b"]).any(), "xuất hiện cặp tự-ghép"


def test_it_is_an_order_of_magnitude_faster_than_the_nested_reference() -> None:
    """So THỜI GIAN THẬT với bản lồng hai vòng, không so tỉ lệ tăng.

    Bản đầu của phép kiểm này đo TỈ LỆ tăng khi gấp bốn số hàng và đòi dưới 10
    lần. Đo lại thì chính bản lồng hai vòng cũng chỉ tăng 4,27 lần trong dải N
    ấy — nên ngưỡng đó không bắt được cả lỗi gốc. Cái phân biệt hai bản là
    HẰNG SỐ: ở N = 600, bản gốc mất 25,0 giây còn bản gom nhóm mất 0,32 giây.

    Ngưỡng 10 lần đặt rất rộng so với 63 lần đo được, nên nó không đỏ vì nhiễu
    máy chạy, mà vẫn đỏ ngay nếu ai đó trả hàm về lối quét từng cặp.
    """
    sparse = _sparse(300)

    start = time.perf_counter()
    fast = _reverse_pair_frequency(sparse, period="day")
    fast_seconds = max(time.perf_counter() - start, 1e-6)

    start = time.perf_counter()
    slow = _reference(sparse, period="day")
    slow_seconds = time.perf_counter() - start

    assert len(fast) == len(slow)
    assert slow_seconds / fast_seconds > 10.0, (
        f"chỉ nhanh hơn bản lồng hai vòng {slow_seconds / fast_seconds:.1f} lần "
        f"({fast_seconds:.4f}s so với {slow_seconds:.4f}s) — hàm có vẻ đã trở lại "
        "lối quét toàn bảng cho từng cặp"
    )
