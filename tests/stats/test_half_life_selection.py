from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from stats.statistical_signal import (
    HALF_LIFE_GRID,
    MIN_HALF_LIFE_SELECTION_DAYS,
    select_half_life,
)


def _stationary(days: int, rate: float = 0.2377, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.random((days, 100)) < rate).astype(float)


def test_stationary_heterogeneity_earns_a_longer_window() -> None:
    rng = np.random.default_rng(7)
    rates = np.clip(rng.normal(0.2377, 0.06, size=100), 0.05, 0.6)
    hit = (rng.random((900, 100)) < rates[None, :]).astype(float)

    chosen, scores = select_half_life(hit)
    assert scores is not None
    assert chosen > HALF_LIFE_GRID[0], f"chọn {chosen}; lẽ ra phải dài hơn 45"


def test_homogeneous_noise_keeps_the_incumbent_window() -> None:
    chosen, scores = select_half_life(_stationary(900))
    assert scores is not None
    assert chosen == HALF_LIFE_GRID[0], f"chọn {chosen}; không gì hơn được 45"


def test_a_drifting_history_is_given_a_short_window() -> None:
    rng = np.random.default_rng(1)
    days = 900
    hit = np.empty((days, 100))
    hit[: days // 2] = (rng.random((days // 2, 100)) < 0.35).astype(float)
    hit[days // 2 :] = (rng.random((days - days // 2, 100)) < 0.12).astype(float)

    chosen, scores = select_half_life(hit)
    assert scores is not None
    assert chosen <= 180, f"chọn {chosen}; dữ liệu trôi thì phải dùng cửa sổ ngắn"


def test_indistinguishable_candidates_keep_the_shorter_window() -> None:
    chosen, scores = select_half_life(np.full((600, 100), 1.0))
    assert scores is not None
    assert chosen == HALF_LIFE_GRID[0], f"chọn {chosen} trên dữ liệu không phân biệt được"
    assert max(scores.values()) - min(scores.values()) < 1e-9


def test_a_short_history_refuses_to_choose_and_says_so() -> None:
    chosen, scores = select_half_life(_stationary(MIN_HALF_LIFE_SELECTION_DAYS - 1))
    assert scores is None
    assert chosen == HALF_LIFE_GRID[0]


def test_the_grid_starts_at_the_legacy_value() -> None:
    assert HALF_LIFE_GRID[0] == 45
    assert list(HALF_LIFE_GRID) == sorted(HALF_LIFE_GRID)
    assert len(set(HALF_LIFE_GRID)) == len(HALF_LIFE_GRID)


def test_the_signal_reports_which_half_life_it_chose_and_why() -> None:
    from stats import statistical_signal as ss

    days = 400
    dates = pd.date_range("2025-01-01", periods=days, freq="D")
    rng = np.random.default_rng(5)
    numbers = rng.integers(0, 100, size=(days, 27))
    two = pd.DataFrame({"date": dates, "special": numbers[:, 0]})
    for i in range(1, 27):
        two[f"p{i}"] = numbers[:, i]
    counts = np.zeros((days, 100), dtype=int)
    for t in range(days):
        np.add.at(counts[t], numbers[t], 1)
    sparse = pd.DataFrame(counts)
    sparse.insert(0, "date", dates)

    class _Fake:
        def load(self): return None
        def get_2_digits_data(self): return two.copy()
        def get_sparse_data(self): return sparse.copy()

    original = ss.Lottery
    try:
        ss.Lottery = lambda: _Fake()
        _df, diag = ss.build_statistical_signal("loto")
        _df2, forced = ss.build_statistical_signal("loto", half_life=45)
    finally:
        ss.Lottery = original

    assert diag["half_life_learned"] is True
    assert diag["half_life_days"] in HALF_LIFE_GRID
    assert set(diag["half_life_brier_by_candidate"]) == {str(v) for v in HALF_LIFE_GRID}

    assert forced["half_life_learned"] is False
    assert forced["half_life_days"] == 45
    assert forced["half_life_brier_by_candidate"] is None


@pytest.mark.parametrize("days", [0, 1, 5])
def test_a_degenerate_history_does_not_crash(days: int) -> None:
    chosen, scores = select_half_life(np.zeros((days, 100)))
    assert chosen == HALF_LIFE_GRID[0]
    assert scores is None
