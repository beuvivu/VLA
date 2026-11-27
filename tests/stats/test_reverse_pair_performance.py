from __future__ import annotations


import time

import numpy as np
import pandas as pd
import pytest

from core.number_reference import all_cap_loto_50
from stats.statistical_matrices import NUMBER_COLS, _prepare_sparse, _period_series
from stats.statistical_matrices import _reverse_pair_frequency


def _sparse(draws: int, *, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", periods=draws, freq="D").strftime("%Y-%m-%d")
    grid = np.zeros((draws, 100), dtype=int)
    for row in range(draws):
        grid[row, rng.choice(100, size=27, replace=False)] = 1
    return pd.DataFrame({"date": dates, **{str(n): grid[:, n] for n in range(100)}})


def _reference(sparse_df: pd.DataFrame, *, period: str) -> pd.DataFrame:
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
    out = _reverse_pair_frequency(_sparse(120), period="month")
    per_period = out.groupby("period_key")["pair"].nunique()
    assert set(per_period.unique()) == {50}, per_period.to_dict()
    assert not (out["a"] == out["b"]).any(), "xuất hiện cặp tự-ghép"


def test_it_is_an_order_of_magnitude_faster_than_the_nested_reference() -> None:
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
