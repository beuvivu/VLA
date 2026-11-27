from __future__ import annotations

import numpy as np
from pydantic import BaseModel
from scipy import stats
from scipy.special import betaln, gammaln

from vietlott_engine.core.history import DrawHistory


def _log_binom_coef(d: int, x: np.ndarray) -> np.ndarray:
    return gammaln(d + 1) - gammaln(x + 1) - gammaln(d - x + 1)


def log_marginal_kappa(counts: np.ndarray, draws: int, mu: float, kappa: np.ndarray) -> np.ndarray:
    x = np.asarray(counts, dtype=np.float64)[None, :]
    a = (mu * kappa)[:, None]
    b = ((1 - mu) * kappa)[:, None]
    return np.sum(_log_binom_coef(draws, x) + betaln(x + a, draws - x + b) - betaln(a, b), axis=1)


def log_likelihood_fair(counts: np.ndarray, draws: int, mu: float) -> float:
    x = np.asarray(counts, dtype=np.float64)
    return float(np.sum(_log_binom_coef(draws, x) + x * np.log(mu) + (draws - x) * np.log1p(-mu)))


class NumberShrinkage(BaseModel):
    number: int
    raw_rate: float
    pooled_rate: float
    shrinkage: float
    posterior_sd: float


class HierarchicalReport(BaseModel):
    game: str
    draws: int
    base_rate: float
    tau_relative_median: float
    tau_relative_upper95: float
    log10_bayes_factor_heterogeneous_vs_fair: float
    log10_bayes_factor_material_vs_fair: float
    material_spread: float
    posterior_prob_fair_within_1pct: float
    fair_ticket_rtp: float
    pooled_best_ticket: list[int]
    pooled_best_ticket_rtp: float
    upper95_best_ticket_rtp: float
    numbers: list[NumberShrinkage]
    interpretation: str


def hierarchical_report(h: DrawHistory, grid_size: int = 400, material: float = 0.05) -> HierarchicalReport:
    n, k, d = h.n, h.k, len(h)
    mu = k / n
    counts = h.counts()
    r = np.logspace(-3, 0, grid_size)
    kappa = mu * (1 - mu) / (r * mu) ** 2 - 1
    valid = kappa > 1e-6
    r, kappa = r[valid], kappa[valid]
    loglik = log_marginal_kappa(counts, d, mu, kappa)
    log_prior = np.full(r.size, -np.log(r.size))
    log_post = loglik + log_prior
    m = log_post.max()
    post = np.exp(log_post - m)
    post /= post.sum()
    cdf = np.cumsum(post)
    r_med = float(r[np.searchsorted(cdf, 0.5)])
    r_hi = float(r[min(np.searchsorted(cdf, 0.95), r.size - 1)])
    log_evidence_het = float(m + np.log(np.sum(np.exp(log_post - m))))
    log_fair = log_likelihood_fair(counts, d, mu)
    log10_bf = (log_evidence_het - log_fair) / np.log(10)
    mat = r >= material
    lm = loglik[mat]
    log_evidence_mat = float(lm.max() + np.log(np.mean(np.exp(lm - lm.max()))))
    log10_bf_mat = (log_evidence_mat - log_fair) / np.log(10)

    theta_mean = (counts[None, :] + mu * kappa[:, None]) / (d + kappa[:, None])
    a_post = counts[None, :] + mu * kappa[:, None]
    b_post = d - counts[None, :] + (1 - mu) * kappa[:, None]
    theta_var = a_post * b_post / ((a_post + b_post) ** 2 * (a_post + b_post + 1))
    pooled = post @ theta_mean
    second = post @ (theta_var + theta_mean**2)
    sd = np.sqrt(np.maximum(second - pooled**2, 0))
    raw = counts / d
    with np.errstate(invalid="ignore", divide="ignore"):
        shrink = np.where(np.abs(raw - mu) > 1e-12, 1 - (pooled - mu) / (raw - mu), 1.0)
    numbers = [
        NumberShrinkage(number=i + 1, raw_rate=float(raw[i]), pooled_rate=float(pooled[i]), shrinkage=float(np.clip(shrink[i], 0, 1)), posterior_sd=float(sd[i]))
        for i in np.argsort(-np.abs(raw - mu))
    ]
    p_within = float(post[r <= 0.01].sum())
    from vietlott_engine.inference.power import ticket_rtp

    best6 = np.argsort(-pooled)[:k]
    tgt = np.full(n, (k - pooled[best6].sum()) / (n - k))
    tgt[best6] = pooled[best6]
    blom = stats.norm.ppf((n - np.arange(1, k + 1) + 1 - 0.375) / (n + 0.25))
    tgt_hi = np.full(n, 0.0)
    top = mu * (1 + r_hi * blom)
    tgt_hi[:k] = top
    tgt_hi[k:] = (k - top.sum()) / (n - k)
    fair_rtp = ticket_rtp(h.spec, np.full(n, mu), np.arange(1, k + 1))
    pooled_rtp = ticket_rtp(h.spec, tgt, best6 + 1)
    upper_rtp = ticket_rtp(h.spec, tgt_hi, np.arange(1, k + 1))
    verdict = (
        f"Data favour a fair machine over a material spread (≥{material:.0%} of k/n) by 10^{-log10_bf_mat:.1f}:1"
        if log10_bf_mat < -0.5
        else f"Data favour a material spread (≥{material:.0%}) by 10^{log10_bf_mat:.1f}:1"
        if log10_bf_mat > 0.5
        else "Evidence about material heterogeneity is inconclusive"
    )
    return HierarchicalReport(
        game=h.spec.code.value,
        draws=d,
        base_rate=mu,
        tau_relative_median=r_med,
        tau_relative_upper95=r_hi,
        log10_bayes_factor_heterogeneous_vs_fair=float(log10_bf),
        log10_bayes_factor_material_vs_fair=float(log10_bf_mat),
        material_spread=material,
        posterior_prob_fair_within_1pct=p_within,
        fair_ticket_rtp=fair_rtp,
        pooled_best_ticket=sorted(int(i + 1) for i in best6),
        pooled_best_ticket_rtp=pooled_rtp,
        upper95_best_ticket_rtp=upper_rtp,
        numbers=numbers,
        interpretation=(
            f"{verdict}. Between-number spread of inclusion rates: posterior median "
            f"{r_med:.1%} of k/n, 95% upper bound {r_hi:.1%}. Raw hot/cold deviations are shrunk by "
            f"~{np.median([x.shrinkage for x in numbers]):.0%} toward k/n. Playing the six best pooled numbers is worth "
            f"RTP {pooled_rtp:.2%} vs {fair_rtp:.2%} for any ticket (95% upper case: {upper_rtp:.2%})."
        ),
    )
