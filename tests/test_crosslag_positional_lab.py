from __future__ import annotations

import numpy as np
import pandas as pd

from crosslag_positional_lab import (
    RuleSpec,
    _calendar_source_indices,
    evaluate_lab,
    generate_rules,
    payload_for_digits,
)


def _history(days: int = 90) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2026-01-01", periods=days, freq="D")
    rng = np.random.default_rng(23)
    cols = ["special"] + [f"p{i}" for i in range(1, 27)]
    values = rng.integers(0, 100, size=(days, 27))
    two = pd.DataFrame(values, columns=cols)
    two.insert(0, "date", dates)

    presence = np.zeros((days, 100), dtype=int)
    for t, row in enumerate(values):
        presence[t, np.unique(row)] = 1
    sparse = pd.DataFrame(presence, columns=[str(i) for i in range(100)])
    sparse.insert(0, "date", dates)
    return two, sparse


def test_payload_operators_match_legacy_semantics():
    assert payload_for_digits("concat", 2, 3) == (23,)
    assert payload_for_digits("lon", 2, 3) == (23, 32)
    assert set(payload_for_digits("bo", 2, 3)) == {23, 28, 73, 78, 32, 82, 37, 87}
    assert payload_for_digits("cham", 8) == (8,)
    assert payload_for_digits("tong", 8, 7) == (5,)


def test_same_position_cross_day_rule_is_represented():
    rules = generate_rules(n_positions=2, lag_pairs=((1, 2),), ops=("concat",))
    assert RuleSpec("concat", 0, 0, 1, 2) in rules


def test_lon_removes_only_true_same_source_duplicate():
    same_day = generate_rules(n_positions=2, lag_pairs=((1, 1),), ops=("lon",))
    cross_day = generate_rules(n_positions=2, lag_pairs=((1, 2),), ops=("lon",))
    assert RuleSpec("lon", 0, 0, 1, 1) not in same_day
    assert RuleSpec("lon", 0, 0, 1, 2) in cross_day


def test_calendar_lag_does_not_substitute_previous_row_when_day_missing():
    dates = pd.DatetimeIndex(pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-04"]))
    lag1 = _calendar_source_indices(dates, 1)
    assert lag1.tolist() == [-1, 0, -1]


def test_lab_is_chronological_fdr_controlled_and_never_production_eligible():
    two, sparse = _history(100)
    table, report = evaluate_lab(
        two,
        sparse,
        lag_pairs=((1, 1), (1, 2)),
        ops=("concat", "lon", "cham", "tong"),
        warmup=30,
    )
    assert not table.empty
    assert report["research_only"] is True
    assert report["production_wired"] is False
    assert (table["production_eligible"] == False).all()  # noqa: E712
    assert table["train_q_value_fdr"].between(0, 1).all()
    assert table["train_bonferroni_p"].between(0, 1).all()
    assert pd.Timestamp(report["train_end_date"]) < pd.Timestamp(report["validation_end_date"])
    assert int(report["holdout_days"]) > 0


def test_crosslag_next_payload_uses_only_dates_before_target():
    two, sparse = _history(80)
    table, _ = evaluate_lab(
        two,
        sparse,
        lag_pairs=((1, 2),),
        ops=("concat",),
        warmup=30,
    )
    row = table[(table["position_a"] == 0) & (table["position_b"] == 0)].iloc[0]
    target = pd.Timestamp(row["next_target_date"])
    latest = pd.to_datetime(two["date"]).max()
    assert target == latest + pd.Timedelta(days=1)
    # With lag 1/2, both source dates are strictly before the target.
    assert target - pd.Timedelta(days=int(row["lag_a_days"])) <= latest
    assert target - pd.Timedelta(days=int(row["lag_b_days"])) <= latest
