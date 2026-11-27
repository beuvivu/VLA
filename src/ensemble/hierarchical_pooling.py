from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np

MAX_PRIOR_STRENGTH: Final[float] = 1e6
MIN_NUMBERS: Final[int] = 3


@dataclass(frozen=True)
class PoolingFit:

    pooled_rate: float
    prior_strength: float
    shrinkage: float
    effective_parameters: float
    between_variance: float
    within_variance: float
    n_units: int
    n_trials: float

    @property
    def fully_pooled(self) -> bool:
        return self.prior_strength >= MAX_PRIOR_STRENGTH

    def describe(self) -> str:
        if self.fully_pooled:
            return (
                f"Co ngót HOÀN TOÀN: {self.n_units} đơn vị không phân biệt được nhau "
                f"trên {self.n_trials:.0f} kỳ (phương sai giữa các đơn vị {self.between_variance:.3e} "
                f"không vượt phương sai trong nội bộ {self.within_variance:.3e}). "
                f"Tham số hiệu dụng: {self.effective_parameters:.2f} trên {self.n_units}."
            )
        return (
            f"Co ngót {self.shrinkage:.1%} về trung bình chung {self.pooled_rate:.4f} "
            f"(κ = {self.prior_strength:.1f} trên {self.n_trials:.0f} kỳ). "
            f"Tham số hiệu dụng: {self.effective_parameters:.2f} trên {self.n_units}."
        )


def _validate_counts(
    counts: np.ndarray, n: np.ndarray, *, allow_zero: bool
) -> np.ndarray:
    if n.shape != counts.shape:
        raise ValueError("successes và trials phải cùng hình dạng")
    if not np.all(np.isfinite(counts)) or not np.all(np.isfinite(n)):
        raise ValueError("successes và trials phải hữu hạn")
    if np.any(n < 0) or (not allow_zero and np.any(n == 0)):
        raise ValueError("mọi đơn vị phải có ít nhất một phép thử" if not allow_zero
                         else "số phép thử không được âm")
    tolerance = 1e-9 * np.maximum(np.abs(n), 1.0)
    if np.any(counts < -tolerance) or np.any(counts > n + tolerance):
        raise ValueError("số lần thành công phải nằm trong [0, số phép thử]")
    return np.clip(counts, 0.0, n)


def _validate_prior_mean(m: np.ndarray) -> None:
    if not np.all(np.isfinite(m)) or np.any(m < 0.0) or np.any(m > 1.0):
        raise ValueError("prior_mean phải hữu hạn và nằm trong [0, 1]")


def fit_pooling(successes: np.ndarray, trials: np.ndarray | float) -> PoolingFit:
    counts = np.asarray(successes, dtype=float).reshape(-1)
    n_units = counts.size
    if n_units < MIN_NUMBERS:
        raise ValueError(f"cần ít nhất {MIN_NUMBERS} đơn vị để ước lượng độ co ngót")
    n = np.asarray(trials, dtype=float)
    if n.ndim == 0:
        n = np.full(n_units, float(n))
    counts = _validate_counts(counts, n, allow_zero=False)

    rates = counts / n
    pooled = float(counts.sum() / n.sum())
    harmonic_n = float(n_units / np.sum(1.0 / n))

    observed_variance = float(np.var(rates, ddof=1))
    within = float(pooled * (1.0 - pooled) / harmonic_n)
    finite_trial_factor = 1.0 - 1.0 / harmonic_n
    between = (
        (observed_variance - within) / finite_trial_factor
        if finite_trial_factor > 0.0 else 0.0
    )

    if not np.isfinite(between) or between <= 0.0 or pooled <= 0.0 or pooled >= 1.0:
        kappa = MAX_PRIOR_STRENGTH
    else:
        kappa = float(pooled * (1.0 - pooled) / between - 1.0)
        kappa = float(np.clip(kappa, 1e-6, MAX_PRIOR_STRENGTH))

    shrinkage = float(kappa / (kappa + harmonic_n))
    return PoolingFit(
        pooled_rate=pooled,
        prior_strength=kappa,
        shrinkage=shrinkage,
        effective_parameters=1.0 + (n_units - 1.0) * (1.0 - shrinkage),
        between_variance=max(between, 0.0),
        within_variance=within,
        n_units=n_units,
        n_trials=float(np.mean(n)),
    )


def pooled_posterior(
    successes: np.ndarray, trials: np.ndarray | float, fit: PoolingFit
) -> np.ndarray:
    counts = np.asarray(successes, dtype=float).reshape(-1)
    n = np.asarray(trials, dtype=float)
    if n.ndim == 0:
        n = np.full(counts.size, float(n))
    counts = _validate_counts(counts, n, allow_zero=True)
    metadata = (
        fit.pooled_rate, fit.prior_strength, fit.shrinkage,
        fit.effective_parameters, fit.between_variance, fit.within_variance,
        fit.n_units, fit.n_trials,
    )
    if (
        not np.all(np.isfinite(metadata))
        or not 0.0 <= fit.pooled_rate <= 1.0
        or fit.prior_strength <= 0.0
        or not 0.0 <= fit.shrinkage <= 1.0
        or fit.n_units < MIN_NUMBERS
        or int(fit.n_units) != fit.n_units
        or not 1.0 <= fit.effective_parameters <= fit.n_units
        or fit.between_variance < 0.0
        or fit.within_variance < 0.0
        or fit.n_trials <= 0.0
    ):
        raise ValueError("metadata PoolingFit phải hữu hạn và đúng miền")
    a0 = fit.prior_strength * fit.pooled_rate
    b0 = fit.prior_strength * (1.0 - fit.pooled_rate)
    return (a0 + counts) / (a0 + b0 + n)


def fit_shrinkage_to_prior(
    successes: np.ndarray,
    trials: np.ndarray | float,
    prior_mean: np.ndarray | float,
) -> float:
    counts = np.asarray(successes, dtype=float).reshape(-1)
    n = np.asarray(trials, dtype=float)
    if n.ndim == 0:
        n = np.full(counts.size, float(n))
    n = n.reshape(-1)
    m = np.asarray(prior_mean, dtype=float)
    if m.ndim == 0:
        m = np.full(counts.size, float(m))
    m = m.reshape(-1)
    if n.shape != counts.shape or m.shape != counts.shape:
        raise ValueError("successes, trials và prior_mean phải cùng hình dạng")
    counts = _validate_counts(counts, n, allow_zero=True)
    _validate_prior_mean(m)
    usable = n > 0
    if int(usable.sum()) < MIN_NUMBERS:
        return MAX_PRIOR_STRENGTH

    counts = counts[usable]
    n = n[usable]
    m = np.clip(m[usable], 1e-9, 1.0 - 1e-9)
    counts = np.clip(counts, 0.0, n)

    rates = counts / n
    deviation = float(np.mean((rates - m) ** 2))
    within = float(np.mean(m * (1.0 - m) / n))
    between = deviation - within

    latent_scale = float(np.mean(m * (1.0 - m) * (1.0 - 1.0 / n)))
    if not np.isfinite(between) or between <= 0.0 or latent_scale <= 0.0:
        return MAX_PRIOR_STRENGTH
    kappa = latent_scale / between - 1.0
    if not np.isfinite(kappa):
        return MAX_PRIOR_STRENGTH
    return float(np.clip(kappa, 1e-6, MAX_PRIOR_STRENGTH))


def fit_shrinkage_to_prior_rows(
    successes: np.ndarray,
    trials: np.ndarray,
    prior_mean: np.ndarray,
) -> np.ndarray:
    counts = np.asarray(successes, dtype=float)
    if counts.ndim != 2:
        raise ValueError("successes phải có hai chiều (n_rows, n_units)")
    n_rows, n_units = counts.shape
    n = np.asarray(trials, dtype=float)
    if n.ndim == 1:
        n = np.broadcast_to(n[:, None], counts.shape)
    if n.shape != counts.shape:
        raise ValueError("trials phải phát sóng được về hình của successes")
    m = np.asarray(prior_mean, dtype=float).reshape(-1)
    if m.size != n_units:
        raise ValueError("prior_mean phải cùng số đơn vị với successes")
    counts = _validate_counts(counts, n, allow_zero=True)
    _validate_prior_mean(m)
    m = np.clip(m, 1e-9, 1.0 - 1e-9)

    out = np.full(n_rows, MAX_PRIOR_STRENGTH, dtype=float)
    usable = n > 0
    enough = usable.sum(axis=1) >= MIN_NUMBERS
    if not np.any(enough):
        return out

    safe_n = np.where(usable, n, 1.0)
    rates = np.where(usable, np.clip(counts, 0.0, safe_n) / safe_n, 0.0)
    dev = np.where(usable, (rates - m[None, :]) ** 2, 0.0)
    within_cell = np.where(usable, m[None, :] * (1.0 - m[None, :]) / safe_n, 0.0)
    k = usable.sum(axis=1)
    k_safe = np.maximum(k, 1)

    between = dev.sum(axis=1) / k_safe - within_cell.sum(axis=1) / k_safe
    latent_cell = np.where(
        usable, m[None, :] * (1.0 - m[None, :]) * (1.0 - 1.0 / safe_n), 0.0
    )
    latent_scale = latent_cell.sum(axis=1) / k_safe
    good = enough & np.isfinite(between) & (between > 0.0) & (latent_scale > 0.0)
    kappa = np.divide(
        latent_scale,
        np.where(good, between, 1.0),
        out=np.full(n_rows, np.inf),
        where=good,
    ) - 1.0
    out[good] = np.clip(kappa[good], 1e-6, MAX_PRIOR_STRENGTH)
    out[~np.isfinite(out)] = MAX_PRIOR_STRENGTH
    return out


def random_effects_posterior(
    successes: np.ndarray, trials: np.ndarray, *, variances: np.ndarray | None = None
) -> tuple[np.ndarray, float, float]:
    counts = np.asarray(successes, dtype=float).reshape(-1)
    n = np.asarray(trials, dtype=float).reshape(-1)
    counts = _validate_counts(counts, n, allow_zero=True)
    used = n > 0
    if not used.any():
        raise ValueError("cần ít nhất một nhóm có phép thử")
    m = float(counts[used].sum() / n[used].sum())
    post = np.full(counts.size, m)
    if used.sum() < 2 or not 0.0 < m < 1.0:
        return post, m, 0.0
    rates = counts[used] / n[used]
    if variances is None:
        v = m * (1.0 - m) / n[used]
    else:
        v = np.asarray(variances, dtype=float).reshape(-1)
        if v.shape != counts.shape or not np.all(np.isfinite(v[used])) or np.any(v[used] <= 0):
            raise ValueError("variances phải cùng hình, hữu hạn và dương ở mọi nhóm có phép thử")
        v = v[used]
    tau2 = dersimonian_laird_tau2(rates, v)
    post[used] = m + tau2 / (tau2 + v) * (rates - m)
    return post, m, tau2


def dersimonian_laird_tau2(rates: np.ndarray, variances: np.ndarray) -> float:
    r = np.asarray(rates, dtype=float).reshape(-1)
    v = np.asarray(variances, dtype=float).reshape(-1)
    if r.size < 2:
        return 0.0
    w = 1.0 / v
    center = float(np.sum(w * r) / w.sum())
    q = float(np.sum(w * (r - center) ** 2))
    scale = float(w.sum() - np.sum(w**2) / w.sum())
    return max(0.0, (q - (r.size - 1)) / scale) if scale > 0 else 0.0
