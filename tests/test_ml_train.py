from __future__ import annotations

import numpy as np
import pandas as pd

from ml_train import _recency_weights, _time_splits


def test_recency_weights_accept_series_and_favor_recent_rows() -> None:
    dates = pd.Series(pd.date_range("2026-01-01", periods=5, freq="D"))
    weights = _recency_weights(dates, half_life_days=2.0)
    assert len(weights) == 5
    assert np.all(np.diff(weights) > 0)
    assert np.isclose(weights.mean(), 1.0)


def test_temporal_split_has_untouched_final_validation_block() -> None:
    days = pd.date_range("2025-01-01", periods=200, freq="D")
    cal, select, val = _time_splits(days)
    assert cal < select < val < days[-1]
    assert (days >= val).sum() == 45
