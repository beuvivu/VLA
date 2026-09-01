from __future__ import annotations

import numpy as np
import pandas as pd

from legacy_advanced_diagnostics import (
    aggregate_transition_independence,
    full_special_acf,
    rolling_coverage,
    weekday_special_tail_contingency,
)


def _frames(days: int = 80) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2026-01-01", periods=days, freq="D")
    rng = np.random.default_rng(17)
    raw = pd.DataFrame({"date": dates, "special": rng.integers(0, 100000, size=days)})
    hit = rng.random((days, 100)) < 0.24
    sparse = pd.DataFrame(hit.astype(int), columns=[str(i) for i in range(100)])
    sparse.insert(0, "date", dates)
    return raw, sparse


def test_aggregate_transition_is_valid_2x2_test():
    _, sparse = _frames()
    out = aggregate_transition_independence(sparse)
    table = out["table"]
    assert sum(int(v) for v in table.values()) == (len(sparse) - 1) * 100
    assert 0.0 <= float(out["p_value"]) <= 1.0
    assert 0.0 <= float(out["p_next_given_hit"]) <= 1.0
    assert 0.0 <= float(out["p_next_given_absent"]) <= 1.0


def test_weekday_special_tail_has_7x10_contract():
    raw, _ = _frames()
    out = weekday_special_tail_contingency(raw)
    table = np.asarray(out["table"], dtype=int)
    assert table.shape == (7, 10)
    assert int(table.sum()) == len(raw)
    assert 0.0 <= float(out["p_value"]) <= 1.0


def test_full_special_acf_has_bartlett_and_fdr():
    raw, _ = _frames(120)
    out = full_special_acf(raw, max_lag=15)
    assert len(out) == 15
    assert out["p_value"].between(0, 1).all()
    assert out["q_value_fdr"].between(0, 1).all()
    assert (out["bartlett_lower"] < 0).all()
    assert (out["bartlett_upper"] > 0).all()


def test_full_special_acf_constant_series_is_safe():
    raw, _ = _frames(50)
    raw["special"] = 12345
    out = full_special_acf(raw, max_lag=5)
    assert (out["acf"] == 0.0).all()
    assert (out["p_value"] == 1.0).all()


def test_rolling_coverage_preserves_legacy_and_empirical_benchmarks():
    _, sparse = _frames(60)
    out = rolling_coverage(sparse, windows=(3, 7, 14))
    assert out["window_days"].astype(int).tolist() == [3, 7, 14]
    assert out["observed_min_distinct"].between(0, 100).all()
    assert out["observed_max_distinct"].between(0, 100).all()
    assert out["legacy_uniform_expected"].between(0, 100).all()
    assert out["empirical_marginal_expected"].between(0, 100).all()
