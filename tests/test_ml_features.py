from __future__ import annotations

import numpy as np

from ml_features import _pairs_indices, _path_support_for_day, _path_support_matrix


def test_vectorized_path_support_matches_single_day_reference() -> None:
    rng = np.random.default_rng(123)
    raw = [rng.integers(0, 10, size=12, dtype=np.uint8) for _ in range(9)]
    i, j = _pairs_indices(12)
    lag_max = 4

    matrix = _path_support_matrix(raw, lag_max, i, j)
    assert matrix.shape == (9, 100)
    for t in range(len(raw)):
        expected = _path_support_for_day(raw, t, lag_max, i, j)
        np.testing.assert_array_equal(matrix[t], expected)


def test_path_support_includes_anchor_day_but_not_future_day() -> None:
    # Feature row t predicts t+1. The anchor draw t is already observed and may
    # be used; using t+1 would be leakage. Day 0 is 00 pairs and day 1 is 99.
    raw = [np.zeros(5, dtype=np.uint8), np.full(5, 9, dtype=np.uint8)]
    i, j = _pairs_indices(5)
    matrix = _path_support_matrix(raw, lag_max=30, I=i, J=j)

    assert matrix[0, 0] == len(i)
    assert matrix[0, 99] == 0
    assert matrix[1, 0] == len(i)
    assert matrix[1, 99] == len(i)


def test_target_weekday_features_refer_to_prediction_day() -> None:
    import pandas as pd

    from ml_features import _target_weekday_components

    dates = pd.DatetimeIndex(["2026-08-30", "2026-08-31"])  # Sunday, Monday
    target, sin_v, cos_v = _target_weekday_components(dates)

    assert target.tolist() == [0, 1]  # Monday, Tuesday
    assert sin_v.shape == (2,)
    assert cos_v.shape == (2,)


def test_target_weekday_rate_never_uses_future_label() -> None:
    import pandas as pd

    from ml_features import _target_weekday_rate

    dates = pd.date_range("2026-08-24", periods=8, freq="D")
    hit = np.zeros((8, 100), dtype=bool)
    # Put a future hit on the last row. Earlier rows' features must be unchanged.
    baseline = _target_weekday_rate(dates, hit)
    hit[-1, 42] = True
    changed = _target_weekday_rate(dates, hit)

    np.testing.assert_allclose(baseline[:-1, 42], changed[:-1, 42])
