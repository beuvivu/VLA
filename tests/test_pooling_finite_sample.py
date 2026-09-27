"""Khóa sai lệch mô men mẫu nhỏ và chặn đầu vào làm nhiễm hậu nghiệm."""

from dataclasses import replace

import numpy as np
import pytest

from hierarchical_pooling import (
    MAX_PRIOR_STRENGTH,
    fit_pooling,
    fit_shrinkage_to_prior,
    fit_shrinkage_to_prior_rows,
    pooled_posterior,
)


def test_small_trial_pooling_removes_only_the_binomial_noise() -> None:
    """Bỏ hệ số 1−1/n sẽ trả κ=4 thay vì κ=3 trên mẫu tính tay này."""
    fit = fit_pooling(np.array([0, 0, 0, 1, 2, 3]), 5)
    assert fit.pooled_rate == pytest.approx(0.2)
    assert fit.prior_strength == pytest.approx(3.0)
    assert fit.between_variance == pytest.approx(0.04)
    assert fit.within_variance == pytest.approx(0.032)
    # Với n=0, dữ liệu không đổi tiên nghiệm; các ô còn lại là cập nhật Beta.
    posterior = pooled_posterior(np.array([0, 1, 3]), np.array([0, 2, 5]), fit)
    np.testing.assert_allclose(posterior, [0.2, 0.32, 0.45])


@pytest.mark.parametrize("unequal", [False, True])
def test_beta_binomial_simulation_recovers_the_generating_strength(unequal) -> None:
    """Mẫu lớn các đơn vị với n nhỏ bắt độ co quá mạnh do bỏ hiệu chỉnh."""
    rng = np.random.default_rng(217)
    n_units = 200_000
    trials = np.resize([2, 3, 5, 8], n_units) if unequal else np.full(n_units, 5)
    rates = rng.beta(2.5, 7.5, size=n_units)
    fit = fit_pooling(rng.binomial(trials, rates), trials)
    assert fit.prior_strength == pytest.approx(10.0, rel=0.04)


def test_single_trial_per_unit_cannot_identify_latent_heterogeneity() -> None:
    """Một quan sát nhị phân mỗi đơn vị không nhận diện được κ của Beta."""
    fit = fit_pooling(np.array([0, 0, 1]), 1)
    assert fit.prior_strength == MAX_PRIOR_STRENGTH
    assert fit.between_variance == 0.0


@pytest.mark.parametrize(
    "counts,trials",
    [
        ([1, 2, np.nan], 5),
        ([1, 2, 3], np.nan),
        ([1, 2, 3], np.inf),
        ([1, 2, 3], [5, 5, np.nan]),
    ],
)
def test_pooling_rejects_nonfinite_observations(counts, trials) -> None:
    """Dữ liệu lỗi phải bị chặn trước khi sinh metadata NaN."""
    with pytest.raises(ValueError):
        fit_pooling(np.asarray(counts), trials)


@pytest.mark.parametrize(
    "counts,trials",
    [
        ([1, 2, np.nan], 5),
        ([1, 2, np.inf], 5),
        ([1, 2, 3], np.nan),
        ([1, 2, 3], np.inf),
        ([1, 2, 3], -1),
        ([-1, 2, 3], 5),
        ([1, 2, 6], 5),
        ([1, 2, 3], [5]),
        ([1, 2, 3], [[5, 5, 5]]),
    ],
)
def test_posterior_rejects_invalid_counts_trials_or_shapes(counts, trials) -> None:
    """Gỡ validation làm hậu nghiệm trả NaN, vượt miền hoặc phát sóng nhầm."""
    fit = fit_pooling(np.array([0, 0, 0, 1, 2, 3]), 5)
    with pytest.raises(ValueError):
        pooled_posterior(np.asarray(counts), trials, fit)


@pytest.mark.parametrize(
    "field,value",
    [
        ("pooled_rate", np.nan),
        ("pooled_rate", -0.1),
        ("pooled_rate", 1.1),
        ("prior_strength", np.inf),
        ("prior_strength", 0),
        ("shrinkage", np.nan),
        ("shrinkage", -0.1),
        ("shrinkage", 1.1),
        ("effective_parameters", np.nan),
        ("effective_parameters", 0),
        ("effective_parameters", 7),
        ("between_variance", np.nan),
        ("between_variance", -0.1),
        ("within_variance", np.inf),
        ("within_variance", -0.1),
        ("n_units", np.nan),
        ("n_units", 2),
        ("n_units", 6.5),
        ("n_trials", np.inf),
        ("n_trials", 0),
    ],
)
def test_posterior_rejects_invalid_fit_metadata(field, value) -> None:
    """Pack mô men hỏng không được dùng để công bố xác suất."""
    fit = fit_pooling(np.array([0, 0, 0, 1, 2, 3]), 5)
    with pytest.raises(ValueError):
        pooled_posterior(np.array([0, 1, 2]), 5, replace(fit, **{field: value}))


@pytest.mark.parametrize("rowwise", [False, True])
def test_prior_centres_recover_strength_with_small_and_zero_trial_cells(rowwise) -> None:
    """Giữ tâm từng ô và hệ số hữu hạn; ô không có phép thử không góp mô men."""
    rng = np.random.default_rng(722)
    n_units = 200_000
    centres = np.resize([0.05, 0.25, 0.7, 0.9], n_units)
    trials = np.resize([2, 5, 8, 3], n_units)
    rates = rng.beta(centres * 10, (1 - centres) * 10)
    counts = rng.binomial(trials, rates)
    counts = np.append(counts, [0, 0, 0])
    trials = np.append(trials, [0, 0, 0])
    centres = np.append(centres, [0.1, 0.5, 0.9])
    if rowwise:
        strength = fit_shrinkage_to_prior_rows(counts[None, :], trials[None, :], centres)[0]
    else:
        strength = fit_shrinkage_to_prior(counts, trials, centres)
    assert strength == pytest.approx(10.0, rel=0.04)


@pytest.mark.parametrize("rowwise", [False, True])
def test_prior_centres_do_not_infer_strength_from_single_trials(rowwise) -> None:
    """Tâm cố định cũng không tạo thông tin về κ từ những ô chỉ có một kỳ."""
    counts = np.array([0, 0, 1])
    if rowwise:
        strength = fit_shrinkage_to_prior_rows(counts[None, :], np.ones(1), np.full(3, 0.2))[0]
    else:
        strength = fit_shrinkage_to_prior(counts, 1, 0.2)
    assert strength == MAX_PRIOR_STRENGTH


@pytest.mark.parametrize("rowwise", [False, True])
@pytest.mark.parametrize(
    "counts,trials,centres",
    [
        ([1, 2, np.nan], [5, 5, 5], [0.2, 0.2, 0.2]),
        ([1, 2, np.inf], [5, 5, 5], [0.2, 0.2, 0.2]),
        ([1, 2, 3], [5, 5, np.nan], [0.2, 0.2, 0.2]),
        ([1, 2, 3], [5, 5, np.inf], [0.2, 0.2, 0.2]),
        ([1, 2, 3], [5, 5, -1], [0.2, 0.2, 0.2]),
        ([-1, 2, 3], [5, 5, 5], [0.2, 0.2, 0.2]),
        ([1, 2, 6], [5, 5, 5], [0.2, 0.2, 0.2]),
        ([1, 2, 3], [5, 5, 5], [0.2, 0.2, np.nan]),
        ([1, 2, 3], [5, 5, 5], [0.2, 0.2, np.inf]),
        ([1, 2, 3], [5, 5, 5], [0.2, 0.2, -0.1]),
        ([1, 2, 3], [5, 5, 5], [0.2, 0.2, 1.1]),
    ],
)
def test_prior_fit_rejects_invalid_observations_or_centres(rowwise, counts, trials, centres) -> None:
    """Ô sai không được âm thầm bỏ qua hay kẹp thành dữ liệu hợp lệ."""
    with pytest.raises(ValueError):
        if rowwise:
            fit_shrinkage_to_prior_rows(np.array([counts]), np.array([trials]), np.array(centres))
        else:
            fit_shrinkage_to_prior(np.array(counts), np.array(trials), np.array(centres))
