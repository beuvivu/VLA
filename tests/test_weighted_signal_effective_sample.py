"""Cỡ mẫu hiệu dụng thống nhất cho hậu nghiệm, khoảng khả tín và replay."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import beta

import statistical_signal as ss


def _three_days():
    """Ba kỳ có 20, 40, 60 số trúng để tách nền thường và nền có trọng số."""
    hit = np.zeros((3, 100))
    hit[0, :20] = 1
    hit[1, :40] = 1
    hit[2, :60] = 1
    dates = pd.Series(pd.date_range("2026-01-01", periods=3))
    return hit, dates


@pytest.mark.parametrize("prior_strength,alpha,beta_shape", [(7.0, 568 / 105, 437 / 105), (None, 274 / 105, 101 / 105)])
def test_loto_point_and_interval_use_one_effective_beta_posterior(monkeypatch, prior_strength, alpha, beta_shape):
    """Tính tay: weights 1,2,3 có ESS=18/7, tâm7/15; κ học đúng bằng1."""
    hit, dates = _three_days()
    monkeypatch.setattr(ss, "_exp_weights", lambda n, half_life: np.array([1.0, 2.0, 3.0]))
    out = ss._loto_signal(hit, dates, 1, half_life=45, prior_strength=prior_strength)
    assert out.loc[25, "effective_sample_size"] == pytest.approx(18 / 7)
    assert out.loc[25, "ewm_prob"] == pytest.approx(alpha / (alpha + beta_shape))
    assert out.loc[25, "credible_low"] == pytest.approx(beta.ppf(0.025, alpha, beta_shape))
    assert out.loc[25, "credible_high"] == pytest.approx(beta.ppf(0.975, alpha, beta_shape))
    assert out["ewm_prob"].sum() > 1.0, "LOTO giữ xác suất marginal, không ép tổng1"


@pytest.mark.parametrize("prior_strength", [None, 7.0])
def test_rescaling_weights_cannot_change_loto_predictions_or_intervals(monkeypatch, prior_strength):
    """Dùng tổng trọng số làm số kỳ sẽ đổi kết quả dù trọng số tương đối giữ nguyên."""
    hit, dates = _three_days()
    columns = ["prob", "ewm_prob", "credible_low", "credible_high", "effective_sample_size"]
    values = []
    for scale in (1.0, 13.0, 1e-200, 1e200):
        monkeypatch.setattr(ss, "_exp_weights", lambda n, half_life, scale=scale: np.array([1.0, 2.0, 3.0]) * scale)
        values.append(ss._loto_signal(hit, dates, 1, half_life=45, prior_strength=prior_strength)[columns].to_numpy())
    for scaled in values[1:]:
        np.testing.assert_allclose(scaled, values[0], rtol=1e-11, atol=1e-13)


@pytest.mark.parametrize("prior_strength", [None, 7.0])
def test_rescaling_weights_cannot_change_categorical_posterior_or_intervals(prior_strength):
    """Đặc Biệt đổi đơn vị weights vẫn phải giữ phân phối và độ bất định."""
    onehot = np.zeros((3, 100))
    onehot[np.arange(3), [0, 1, 1]] = 1
    weights = np.array([1.0, 2.0, 3.0])
    reference = ss._de_posterior(onehot, weights, prior_strength)
    for scale in (13.0, 1e-200, 1e200):
        result = ss._de_posterior(onehot, weights * scale, prior_strength)
        np.testing.assert_allclose(result, reference, rtol=1e-11, atol=1e-13)
        assert result[0].sum() == pytest.approx(1.0)


def test_categorical_point_and_intervals_use_the_same_effective_dirichlet_counts():
    """κ=7, ESS=18/7, số1 có count=15/7 nên alpha1=1549/700."""
    onehot = np.zeros((3, 100))
    onehot[np.arange(3), [0, 1, 1]] = 1
    point, low, high = ss._de_posterior(onehot, np.array([1.0, 2.0, 3.0]), 7.0)
    assert point[1] == pytest.approx(1549 / 6700)
    assert low[1] == pytest.approx(beta.ppf(0.025, 1549 / 700, 5151 / 700))
    assert high[1] == pytest.approx(beta.ppf(0.975, 1549 / 700, 5151 / 700))


@pytest.mark.parametrize("selector", ["half_life", "pool"])
def test_selection_scores_are_invariant_to_the_units_of_recency_weights(monkeypatch, selector):
    """Cổng lựa chọn phải chấm cùng ESS như khi công bố, kể cả khi đổi đơn vị weights."""
    rng = np.random.default_rng(421)
    hit = (rng.random((280, 100)) < np.linspace(0.03, 0.85, 100)).astype(float)
    dates = pd.Series(pd.date_range("2025-01-01", periods=280))
    original = ss._exp_weights
    results = []
    for scale in (1.0, 13.0):
        monkeypatch.setattr(ss, "_exp_weights", lambda n, half_life, scale=scale: original(n, half_life) * scale)
        if selector == "half_life":
            chosen, scores = ss.select_half_life(hit, grid=(45, 180))
        else:
            chosen, audit = ss.select_signal_pool(hit, dates, mode="loto", half_life=45)
            assert audit is not None
            scores = audit.brier_by_candidate
        results.append((chosen, scores))
    assert results[0][0] == results[1][0]
    assert results[0][1] == pytest.approx(results[1][1], rel=1e-12, abs=1e-14)


def test_backtest_uses_the_same_effective_posterior_as_publication(monkeypatch):
    """Replay phải dùng công thức ESS đúng trên mẫu κ=1 đã tính độc lập."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "backtest_pooling.py"
    spec = importlib.util.spec_from_file_location("backtest_pooling_effective_sample", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_exp_weights", lambda n, half_life: np.array([1.0, 2.0, 3.0]))
    hit, _ = _three_days()
    dates = pd.Series(pd.date_range("2026-01-01", periods=4))
    actual = module._components(np.vstack([hit, np.zeros(100)]), dates, 3, 45)
    assert actual[0, 25] == pytest.approx(274 / 375)
