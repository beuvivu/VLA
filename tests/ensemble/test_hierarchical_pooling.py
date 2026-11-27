from __future__ import annotations

import numpy as np
import pytest

from ensemble.hierarchical_pooling import (
    MAX_PRIOR_STRENGTH,
    MIN_NUMBERS,
    fit_pooling,
    pooled_posterior,
)


def test_homogeneous_units_are_pooled_hard() -> None:
    rng = np.random.default_rng(0)
    trials = 2000
    fit = fit_pooling(rng.binomial(trials, 0.2377, size=100), trials)

    assert fit.shrinkage > 0.8, fit.describe()
    assert fit.effective_parameters < 25.0, fit.describe()
    assert fit.pooled_rate == pytest.approx(0.2377, abs=0.01)


def test_genuinely_different_units_are_kept_apart() -> None:
    rng = np.random.default_rng(1)
    trials = 2000
    rates = np.clip(rng.normal(0.2377, 0.03, size=100), 0.01, 0.99)
    fit = fit_pooling(rng.binomial(trials, rates), trials)

    assert fit.shrinkage < 0.3, fit.describe()
    assert fit.effective_parameters > 70.0, fit.describe()
    assert not fit.fully_pooled


def test_no_excess_variance_means_fully_pooled_not_a_negative_strength() -> None:
    fit = fit_pooling(np.full(100, 500.0), 2000.0)
    assert fit.fully_pooled
    assert fit.prior_strength == MAX_PRIOR_STRENGTH
    assert fit.between_variance == 0.0
    assert "Co ngót HOÀN TOÀN" in fit.describe()
    assert 1.0 < fit.effective_parameters < 1.5
    assert f"{fit.effective_parameters:.2f}" in fit.describe()


def test_shrinkage_weakens_as_evidence_accumulates() -> None:
    rng = np.random.default_rng(2)
    rates = np.clip(rng.normal(0.24, 0.03, size=100), 0.01, 0.99)
    shrinkages = [
        fit_pooling(rng.binomial(n, rates), n).shrinkage for n in (200, 1000, 5000)
    ]
    assert shrinkages[0] > shrinkages[1] > shrinkages[2], shrinkages


def test_the_posterior_lies_between_the_raw_rate_and_the_pooled_mean() -> None:
    rng = np.random.default_rng(3)
    trials = 400
    counts = rng.binomial(trials, 0.24, size=100).astype(float)
    fit = fit_pooling(counts, trials)
    posterior = pooled_posterior(counts, trials, fit)

    raw = counts / trials
    low = np.minimum(raw, fit.pooled_rate)
    high = np.maximum(raw, fit.pooled_rate)
    assert np.all(posterior >= low - 1e-9)
    assert np.all(posterior <= high + 1e-9)
    assert posterior.max() - posterior.min() < raw.max() - raw.min()


def test_unequal_trial_counts_are_handled_by_weighting() -> None:
    counts = np.array([240.0, 240.0, 240.0, 1.0])
    trials = np.array([1000.0, 1000.0, 1000.0, 1.0])
    fit = fit_pooling(counts, trials)
    assert fit.pooled_rate == pytest.approx(721.0 / 3001.0, abs=1e-9)
    assert fit.pooled_rate < 0.25

    assert fit.shrinkage == pytest.approx(0.0883755874474333), (
        f"co ngót {fit.shrinkage:.6f} quá thấp — nhiều khả năng đang dùng "
        "trung bình cộng của số phép thử"
    )


def test_extreme_heterogeneity_drives_the_prior_strength_down_to_single_digits() -> None:
    rng = np.random.default_rng(9)
    trials = 2000
    rates = np.linspace(0.05, 0.95, 100)
    fit = fit_pooling(rng.binomial(trials, rates), trials)

    assert 2.0 < fit.prior_strength < 3.5, (
        f"κ = {fit.prior_strength:.3f}; ngoài dải này thì công thức mô men "
        "đã lệch (thiếu hoặc thừa số hạng -1)"
    )
    assert fit.shrinkage < 0.01
    assert fit.effective_parameters > 99.0, "khác biệt thật thì phải giữ gần đủ tham số"


@pytest.mark.parametrize(
    ("counts", "trials", "match"),
    [
        (np.array([1.0, 2.0]), 10.0, "ít nhất"),
        (np.array([1.0, 2.0, 3.0]), 0.0, "ít nhất một phép thử"),
        (np.array([1.0, 2.0, 3.0]), np.array([10.0, 10.0]), "cùng hình dạng"),
        (np.array([-1.0, 2.0, 3.0]), 10.0, r"\[0, số phép thử\]"),
        (np.array([11.0, 2.0, 3.0]), 10.0, r"\[0, số phép thử\]"),
    ],
)
def test_invalid_input_is_refused(counts, trials, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        fit_pooling(counts, trials)


def test_the_minimum_unit_count_is_stated_not_implied() -> None:
    assert MIN_NUMBERS >= 3
    fit = fit_pooling(np.array([100.0, 120.0, 110.0]), 500.0)
    assert fit.n_units == 3


def test_each_posterior_learns_its_own_shrinkage() -> None:
    import pandas as pd

    from stats.statistical_signal import _loto_signal

    dates = pd.date_range("2026-01-05", periods=40 * 7, freq="D")
    rng = np.random.default_rng(4)
    hit = (rng.random((len(dates), 100)) < 0.2377).astype(np.int8)
    monday = np.array([d.weekday() == 0 for d in dates])
    hit[monday, 7] = 1
    hit[~monday, 7] = 0

    out = _loto_signal(hit, pd.Series(dates), 0, half_life=45, prior_strength=None)
    others = out[out["number"] != 7]["weekday_prob"].to_numpy(dtype=float)
    assert float(out.loc[7, "weekday_prob"]) > others.max() * 1.5, (
        "κ học riêng cho hậu nghiệm theo thứ phải giữ được nhịp thứ Hai"
    )


def test_the_signal_reports_its_effective_parameter_count() -> None:
    import pandas as pd

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
    finally:
        ss.Lottery = original

    assert diag["prior_strength_learned"] is True
    pooling = diag["pooling"]
    assert 1.0 <= pooling["effective_parameters"] <= 100.0
    assert 0.0 <= pooling["shrinkage"] <= 1.0
    assert "verdict" in pooling

    try:
        ss.Lottery = lambda: _Fake()
        _df2, diag2 = ss.build_statistical_signal("loto", prior_strength=80.0)
    finally:
        ss.Lottery = original
    assert diag2["prior_strength_learned"] is False
    assert diag2["prior_strength"] == 80.0
    assert diag2["pooling"] is None
