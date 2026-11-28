from __future__ import annotations

import numpy as np
from pydantic import BaseModel
from scipy import stats
from scipy.special import gammaln

from vietlott_engine.core.history import DrawHistory, decay_weights


class NumberPosterior(BaseModel):
    number: int
    alpha: float
    inclusion_probability: float
    ci_low: float
    ci_high: float
    lift: float


class PredictiveScore(BaseModel):
    decay: float
    draws_scored: int
    mean_log_score_gain: float
    standard_error: float
    t_statistic: float


class BayesianReport(BaseModel):
    game: str
    draws: int
    alpha0: float
    decay: float
    effective_draws: float
    numbers: list[NumberPosterior]
    log_bayes_factor_vs_uniform: float
    empirical_bayes_alpha0: float
    predictive: PredictiveScore | None = None


class DirichletMultinomialModel:

    def __init__(self, n: int, k: int, alpha0: float = 1.0, decay: float = 1.0) -> None:
        if alpha0 <= 0:
            raise ValueError("alpha0 must be positive")
        if not 0 < decay <= 1:
            raise ValueError("decay must be in (0, 1]")
        self.n, self.k, self.alpha0, self.decay = n, k, alpha0, decay
        self.alpha = np.full(n, alpha0, dtype=np.float64)
        self.effective_draws = 0.0

    def fit(self, h: DrawHistory) -> "DirichletMultinomialModel":
        w = decay_weights(len(h), self.decay)
        self.alpha = self.alpha0 + h.counts(w)
        self.effective_draws = float(w.sum())
        return self

    @property
    def posterior_mean(self) -> np.ndarray:
        return self.alpha / self.alpha.sum()

    @property
    def inclusion_probabilities(self) -> np.ndarray:
        return np.clip(self.k * self.posterior_mean, 0.0, 1.0)

    def credible_intervals(self, level: float = 0.95) -> tuple[np.ndarray, np.ndarray]:
        a_total = self.alpha.sum()
        lo = stats.beta.ppf((1 - level) / 2, self.alpha, a_total - self.alpha)
        hi = stats.beta.ppf((1 + level) / 2, self.alpha, a_total - self.alpha)
        return np.clip(self.k * lo, 0, 1), np.clip(self.k * hi, 0, 1)

    @staticmethod
    def log_marginal_likelihood(counts: np.ndarray, alpha0: float) -> float:
        counts = np.asarray(counts, dtype=np.float64)
        n, total = counts.size, counts.sum()
        a = n * alpha0
        return float(gammaln(a) - gammaln(a + total) + np.sum(gammaln(alpha0 + counts) - gammaln(alpha0)))

    @classmethod
    def log_bayes_factor_vs_uniform(cls, counts: np.ndarray, alpha0: float) -> float:
        counts = np.asarray(counts, dtype=np.float64)
        return cls.log_marginal_likelihood(counts, alpha0) - counts.sum() * np.log(1.0 / counts.size)

    @classmethod
    def empirical_bayes_alpha0(cls, counts: np.ndarray, grid: np.ndarray | None = None) -> float:
        grid = np.logspace(-1, 5, 61) if grid is None else grid
        scores = [cls.log_marginal_likelihood(counts, a) for a in grid]
        return float(grid[int(np.argmax(scores))])

    def predictive_log_score(self, h: DrawHistory, start: int = 100) -> PredictiveScore:
        inc = h.incidence.astype(np.float64)
        d = len(h)
        if d <= start + 1:
            raise ValueError("not enough draws to score")
        base = self.k / self.n
        c = np.zeros(self.n)
        for t in range(start):
            c = self.decay * c + inc[t]
        gains = []
        for t in range(start, d):
            a = self.alpha0 + c
            q = np.clip(self.k * a / a.sum(), 1e-9, 1 - 1e-9)
            x = inc[t]
            ll_model = np.sum(x * np.log(q) + (1 - x) * np.log(1 - q))
            ll_base = np.sum(x * np.log(base) + (1 - x) * np.log(1 - base))
            gains.append(ll_model - ll_base)
            c = self.decay * c + x
        from vietlott_engine.inference.predictive import diebold_mariano

        dm = diebold_mariano(np.asarray(gains))
        return PredictiveScore(
            decay=self.decay,
            draws_scored=len(gains),
            mean_log_score_gain=dm.mean_differential,
            standard_error=dm.hac_standard_error,
            t_statistic=dm.statistic,
        )

    def sample_tickets(self, n_tickets: int, rng: np.random.Generator, temperature: float = 1.0) -> list[tuple[int, ...]]:
        logits = np.log(self.posterior_mean) / max(temperature, 1e-9)
        out = []
        for _ in range(n_tickets):
            g = logits + rng.gumbel(size=self.n)
            out.append(tuple(sorted(int(i) + 1 for i in np.argpartition(-g, self.k)[: self.k])))
        return out


def tune_decay(h: DrawHistory, grid: tuple[float, ...] = (0.9, 0.95, 0.98, 0.99, 0.995, 1.0), alpha0: float = 1.0, start: int = 100) -> list[PredictiveScore]:
    return [DirichletMultinomialModel(h.n, h.k, alpha0, lam).predictive_log_score(h, start) for lam in grid]


def bayesian_report(h: DrawHistory, alpha0: float = 1.0, decay: float = 1.0, level: float = 0.95, score_from: int | None = 100) -> BayesianReport:
    h.require(10)
    model = DirichletMultinomialModel(h.n, h.k, alpha0, decay).fit(h)
    lo, hi = model.credible_intervals(level)
    incl = model.inclusion_probabilities
    base = h.k / h.n
    counts = h.counts()
    numbers = [
        NumberPosterior(
            number=i + 1,
            alpha=float(model.alpha[i]),
            inclusion_probability=float(incl[i]),
            ci_low=float(lo[i]),
            ci_high=float(hi[i]),
            lift=float(incl[i] / base),
        )
        for i in range(h.n)
    ]
    predictive = None
    if score_from is not None and len(h) > score_from + 20:
        predictive = model.predictive_log_score(h, score_from)
    return BayesianReport(
        game=h.spec.code.value,
        draws=len(h),
        alpha0=alpha0,
        decay=decay,
        effective_draws=model.effective_draws,
        numbers=sorted(numbers, key=lambda x: -x.inclusion_probability),
        log_bayes_factor_vs_uniform=DirichletMultinomialModel.log_bayes_factor_vs_uniform(counts, alpha0),
        empirical_bayes_alpha0=DirichletMultinomialModel.empirical_bayes_alpha0(counts),
        predictive=predictive,
    )
