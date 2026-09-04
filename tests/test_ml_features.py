from __future__ import annotations

import numpy as np

from ml_features import (
    FIELD_WIDTHS,
    FeatureParams,
    build_ml_table_from_history,
    _pairs_indices,
    _path_support_for_day,
    _path_support_matrix,
    _validate_aligned_histories,
)


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


def test_raw_and_two_digit_history_must_share_exact_date_axis() -> None:
    import pandas as pd
    import pytest

    raw = pd.DataFrame({"date": pd.to_datetime(["2026-08-01", "2026-08-02"])})
    two = pd.DataFrame({"date": pd.to_datetime(["2026-08-01", "2026-08-03"])})
    with pytest.raises(ValueError, match="same ordered date axis"):
        _validate_aligned_histories(raw, two)


def test_duplicate_history_dates_are_rejected_before_feature_construction() -> None:
    import pandas as pd
    import pytest

    raw = pd.DataFrame({"date": pd.to_datetime(["2026-08-01", "2026-08-01"])})
    two = raw.copy()
    with pytest.raises(ValueError, match="duplicates"):
        _validate_aligned_histories(raw, two)


def test_full_feature_table_is_invariant_to_future_result_mutation() -> None:
    import pandas as pd

    dates = pd.date_range("2026-08-01", periods=9, freq="D")
    raw_data: dict[str, object] = {"date": dates}
    for offset, (field, width) in enumerate(FIELD_WIDTHS):
        raw_data[field] = [
            (10 ** (width - 1) + 17 * day + offset) % (10**width)
            for day in range(len(dates))
        ]
    raw = pd.DataFrame(raw_data)
    two = raw.copy()
    for field, _ in FIELD_WIDTHS:
        two[field] = two[field].astype(int) % 100

    cutoff = pd.Timestamp("2026-08-06")
    before, _ = build_ml_table_from_history("loto", FeatureParams(), raw, two)
    mutated_raw = raw.copy()
    mutated_two = two.copy()
    future = dates > cutoff
    for field, width in FIELD_WIDTHS:
        mutated_raw.loc[future, field] = 10**width - 1
        mutated_two.loc[future, field] = 99
    after, _ = build_ml_table_from_history(
        "loto", FeatureParams(), mutated_raw, mutated_two
    )

    before_prior = before[pd.to_datetime(before["date"]) <= cutoff].reset_index(drop=True)
    after_prior = after[pd.to_datetime(after["date"]) <= cutoff].reset_index(drop=True)
    pd.testing.assert_frame_equal(before_prior, after_prior)
