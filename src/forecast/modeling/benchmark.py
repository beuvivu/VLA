from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from scipy import stats
from scipy.special import logsumexp
from sklearn.cluster import KMeans
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier

from soi_cau.bridges.scanner import NUMBER_SPACE
from core.xsmb_domain import LOTO_BASELINE_RATE, LOTO_DRAWS_PER_DAY

BASELINE_RATE: float = LOTO_BASELINE_RATE

_EPSILON: float = 1e-6


def _clip(probabilities: np.ndarray) -> np.ndarray:
    return np.clip(probabilities, _EPSILON, 1.0 - _EPSILON)


class SequenceModel(Protocol):

    name: str
    family: str

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        ...


class UniformBaseline:

    name = "Nền đồng đều"
    family = "baseline"

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        return np.full(NUMBER_SPACE, BASELINE_RATE)


class EmpiricalFrequency:

    name = "Tần suất kinh nghiệm"
    family = "frequentist"

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        return _clip((history > 0).mean(axis=0))


class BetaBinomialShrinkage:

    name = "Co rút Beta–Nhị thức"
    family = "bayesian"

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        hits = (history > 0).astype(float)
        m = hits.shape[0]
        if m < 2:
            return np.full(NUMBER_SPACE, BASELINE_RATE)
        rates = hits.mean(axis=0)
        grand = float(rates.mean())
        observed_var = float(rates.var(ddof=1))
        sampling_var = grand * (1.0 - grand) / m
        signal_var = observed_var - sampling_var
        if signal_var <= 0:
            return np.full(NUMBER_SPACE, grand)
        strength = max(grand * (1.0 - grand) / signal_var - 1.0, 0.0)
        a, b = grand * strength, (1.0 - grand) * strength
        return _clip((a + hits.sum(axis=0)) / (a + b + m))


class MarkovChain:

    family = "markov"

    def __init__(self, order: int = 1, pooled: bool = True) -> None:
        self.order = int(order)
        self.pooled = bool(pooled)
        scope = "gộp" if pooled else "riêng từng con"
        self.name = f"Xích Markov bậc {self.order} ({scope})"

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        hits = (history > 0).astype(np.int64)
        k = self.order
        if hits.shape[0] <= k + 1:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        windows = np.stack([hits[i : hits.shape[0] - k + i] for i in range(k)], axis=0)
        weights = (2 ** np.arange(k))[:, None, None]
        states = (windows * weights).sum(axis=0)
        outcomes = hits[k:]
        n_states = 2**k

        if self.pooled:
            successes = np.bincount(states.ravel(), weights=outcomes.ravel(), minlength=n_states)
            totals = np.bincount(states.ravel(), minlength=n_states)
            table = (successes + 1.0) / (totals + 2.0)
            current = (hits[-k:] * (2 ** np.arange(k))[:, None]).sum(axis=0)
            return _clip(table[current])

        probabilities = np.empty(NUMBER_SPACE)
        prior = 4.0
        for number in range(NUMBER_SPACE):
            state_col, outcome_col = states[:, number], outcomes[:, number]
            current = int((hits[-k:, number] * (2 ** np.arange(k))).sum())
            mask = state_col == current
            total = int(mask.sum())
            successes = float(outcome_col[mask].sum())
            probabilities[number] = (successes + prior * BASELINE_RATE) / (total + prior)
        return _clip(probabilities)


class GapHazard:

    name = "Nguy cơ theo độ gan"
    family = "survival"

    def __init__(self, max_gap: int = 12, prior: float = 40.0) -> None:
        self.max_gap = int(max_gap)
        self.prior = float(prior)

    def _current_gaps(self, hits: np.ndarray) -> np.ndarray:
        n = hits.shape[0]
        last = np.where(hits.any(axis=0), n - 1 - np.argmax(hits[::-1], axis=0), -1)
        return np.minimum(n - 1 - last, self.max_gap)

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        hits = history > 0
        n = hits.shape[0]
        if n < 30:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        successes = np.zeros(self.max_gap + 1)
        totals = np.zeros(self.max_gap + 1)
        gaps = np.zeros(NUMBER_SPACE, dtype=np.int64)
        for day in range(n):
            bucket = np.minimum(gaps, self.max_gap)
            np.add.at(totals, bucket, 1)
            np.add.at(successes, bucket, hits[day].astype(float))
            gaps = np.where(hits[day], 0, gaps + 1)

        hazard = (successes + self.prior * BASELINE_RATE) / (totals + self.prior)
        return _clip(hazard[self._current_gaps(hits)])


class HiddenMarkovRegime:

    name = "HMM hai chế độ"
    family = "state-space"

    def __init__(self, iterations: int = 30, seed: int = 0) -> None:
        self.iterations = int(iterations)
        self.seed = int(seed)

    @staticmethod
    def _forward_backward(
        log_emission: np.ndarray, log_transition: np.ndarray, log_start: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        n, k = log_emission.shape
        log_alpha = np.empty((n, k))
        log_alpha[0] = log_start + log_emission[0]
        for t in range(1, n):
            log_alpha[t] = log_emission[t] + logsumexp(
                log_alpha[t - 1][:, None] + log_transition, axis=0
            )
        log_beta = np.zeros((n, k))
        for t in range(n - 2, -1, -1):
            log_beta[t] = logsumexp(log_transition + log_emission[t + 1] + log_beta[t + 1], axis=1)
        log_gamma = log_alpha + log_beta
        log_gamma -= logsumexp(log_gamma, axis=1, keepdims=True)
        return np.exp(log_gamma), log_alpha

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        observations = (history > 0).sum(axis=1).astype(float)
        n = observations.size
        if n < 40 or observations.std() < 1e-9:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        rng = np.random.default_rng(self.seed)
        mu = np.array(
            [observations.mean() - observations.std(), observations.mean() + observations.std()]
        )
        sigma = np.full(2, max(observations.std(), 1e-3))
        transition = np.array([[0.8, 0.2], [0.2, 0.8]])
        start = np.array([0.5, 0.5])

        for _ in range(self.iterations):
            log_emission = np.stack(
                [stats.norm.logpdf(observations, mu[i], sigma[i]) for i in range(2)], axis=1
            )
            gamma, _ = self._forward_backward(log_emission, np.log(transition), np.log(start))
            weights = gamma.sum(axis=0)
            if np.any(weights < 1e-8):
                break
            mu = (gamma * observations[:, None]).sum(axis=0) / weights
            sigma = np.sqrt((gamma * (observations[:, None] - mu) ** 2).sum(axis=0) / weights)
            sigma = np.maximum(sigma, 1e-3)
            joint = gamma[:-1, :, None] * gamma[1:, None, :]
            transition = joint.sum(axis=0)
            transition /= np.maximum(transition.sum(axis=1, keepdims=True), 1e-12)
            start = gamma[0] / gamma[0].sum()
            _ = rng

        log_emission = np.stack(
            [stats.norm.logpdf(observations, mu[i], sigma[i]) for i in range(2)], axis=1
        )
        gamma, _ = self._forward_backward(log_emission, np.log(transition), np.log(start))
        next_state = gamma[-1] @ transition
        expected_distinct = float(next_state @ mu)
        return np.full(
            NUMBER_SPACE, float(np.clip(expected_distinct / NUMBER_SPACE, _EPSILON, 1 - _EPSILON))
        )


class ClusterRate:

    family = "clustering"

    def __init__(self, n_clusters: int = 4, seed: int = 0) -> None:
        self.n_clusters = int(n_clusters)
        self.seed = int(seed)
        self.name = f"Phân cụm k-means (k={self.n_clusters})"

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        hits = history > 0
        n = hits.shape[0]
        if n < 60:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        rate = hits.mean(axis=0)
        double_rate = (history >= 2).mean(axis=0)
        gaps = np.array(
            [
                np.diff(np.flatnonzero(hits[:, i])).mean() if hits[:, i].sum() >= 2 else float(n)
                for i in range(NUMBER_SPACE)
            ]
        )
        profile = np.stack([rate, double_rate, gaps / n], axis=1)
        profile = (profile - profile.mean(axis=0)) / np.maximum(profile.std(axis=0), 1e-9)

        labels = KMeans(n_clusters=self.n_clusters, n_init=4, random_state=self.seed).fit_predict(
            profile
        )
        probabilities = np.empty(NUMBER_SPACE)
        for cluster in range(self.n_clusters):
            mask = labels == cluster
            observations = mask.sum() * n
            cluster_rate = float(hits[:, mask].mean()) if mask.any() else BASELINE_RATE
            weight = observations / (observations + 2000.0)
            probabilities[mask] = weight * cluster_rate + (1 - weight) * BASELINE_RATE
        return _clip(probabilities)


def build_features(history: np.ndarray, day: int) -> np.ndarray:
    past = history[:day] > 0
    if past.shape[0] < 30:
        return np.zeros((NUMBER_SPACE, 8))

    windows = (10, 30, 90)
    columns = [past[-w:].mean(axis=0) for w in windows]

    last_seen = np.where(past.any(axis=0), past.shape[0] - 1 - np.argmax(past[::-1], axis=0), -1)
    gap = past.shape[0] - 1 - last_seen
    columns.append(np.minimum(gap, 30) / 30.0)
    columns.append(past[-1].astype(float))
    columns.append(past[-2].astype(float) if past.shape[0] >= 2 else np.zeros(NUMBER_SPACE))
    columns.append((history[:day][-30:] >= 2).mean(axis=0))
    columns.append(np.array([(n // 10 + n % 10) / 18.0 for n in range(NUMBER_SPACE)]))
    return np.stack(columns, axis=1)


class SupervisedModel:

    family = "supervised"

    def __init__(self, name: str, factory, refit_every: int = 14, window: int = 240) -> None:
        self.name = name
        self._factory = factory
        self.refit_every = int(refit_every)
        self.window = int(window)
        self._model = None
        self._fitted_at = -1

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        n = history.shape[0]
        if n < 90:
            return np.full(NUMBER_SPACE, BASELINE_RATE)

        if self._model is None or n - self._fitted_at >= self.refit_every:
            start = max(30, n - self.window)
            rows, targets = [], []
            for day in range(start, n):
                rows.append(build_features(history, day))
                targets.append((history[day] > 0).astype(int))
            x = np.concatenate(rows, axis=0)
            y = np.concatenate(targets, axis=0)
            if len(np.unique(y)) < 2:
                return np.full(NUMBER_SPACE, BASELINE_RATE)
            self._model = self._factory()
            self._model.fit(x, y)
            self._fitted_at = n

        return _clip(self._model.predict_proba(build_features(history, n))[:, 1])


def gradient_boosting(refit_every: int = 14) -> SupervisedModel:
    return SupervisedModel(
        "Cây tăng cường gradient",
        lambda: HistGradientBoostingClassifier(
            max_depth=3,
            max_iter=120,
            learning_rate=0.05,
            l2_regularization=1.0,
            random_state=0,
        ),
        refit_every=refit_every,
    )


def high_capacity_network(refit_every: int = 30) -> SupervisedModel:
    return SupervisedModel(
        "Mạng nơ-ron dung lượng cao",
        lambda: MLPClassifier(
            hidden_layer_sizes=(64, 64), max_iter=300, random_state=0, alpha=1e-4
        ),
        refit_every=refit_every,
    )


@dataclass(frozen=True)
class Evaluation:

    name: str
    family: str
    days: int
    logloss: float
    brier: float
    baseline_logloss: float
    baseline_brier: float
    paired_t: float
    hit_at_27: float
    baseline_hit_at_27: float
    calibration_error: float

    @property
    def logloss_skill(self) -> float:
        return (self.baseline_logloss - self.logloss) / self.baseline_logloss

    @property
    def brier_skill(self) -> float:
        return (self.baseline_brier - self.brier) / self.baseline_brier

    @property
    def beats_baseline(self) -> bool:
        return self.logloss_skill > 0 and self.paired_t > 1.96

    def describe(self) -> str:
        verdict = "VƯỢT nền" if self.beats_baseline else "không vượt nền"
        return (
            f"{self.name:<30} kỹ năng={self.logloss_skill:>+9.5f}  "
            f"t={self.paired_t:>+6.2f}  trúng@27={self.hit_at_27:>5.2f}  "
            f"lệch hiệu chuẩn={self.calibration_error:.4f}  {verdict}"
        )


def _calibration_error(probabilities: np.ndarray, outcomes: np.ndarray, bins: int = 10) -> float:
    edges = np.quantile(probabilities, np.linspace(0, 1, bins + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    total = 0.0
    for i in range(bins):
        mask = (probabilities > edges[i]) & (probabilities <= edges[i + 1])
        if mask.sum() == 0:
            continue
        total += mask.mean() * abs(probabilities[mask].mean() - outcomes[mask].mean())
    return float(total)


def walk_forward(counts: np.ndarray, model: SequenceModel, *, warmup: int = 120) -> Evaluation:
    n = counts.shape[0]
    daily_logloss, daily_baseline, rows = [], [], []
    hit_at_27, baseline_hit = [], []

    for day in range(warmup, n):
        probabilities = np.asarray(model.predict_next(counts[:day]), dtype=float)
        outcome = (counts[day] > 0).astype(float)
        p = _clip(probabilities)

        daily_logloss.append(-float(np.mean(outcome * np.log(p) + (1 - outcome) * np.log1p(-p))))
        b = BASELINE_RATE
        daily_baseline.append(-float(np.mean(outcome * np.log(b) + (1 - outcome) * np.log1p(-b))))
        rows.append((p, outcome))
        top = np.argsort(-p, kind="stable")[:LOTO_DRAWS_PER_DAY]
        hit_at_27.append(float(outcome[top].sum()))
        baseline_hit.append(float(outcome.sum()) * LOTO_DRAWS_PER_DAY / NUMBER_SPACE)

    model_scores = np.array(daily_logloss)
    baseline_scores = np.array(daily_baseline)
    difference = baseline_scores - model_scores
    t_stat = (
        float(difference.mean() / (difference.std(ddof=1) / np.sqrt(difference.size)))
        if difference.std(ddof=1) > 0
        else 0.0
    )

    all_p = np.concatenate([p for p, _ in rows])
    all_y = np.concatenate([y for _, y in rows])
    return Evaluation(
        name=model.name,
        family=model.family,
        days=int(model_scores.size),
        logloss=float(model_scores.mean()),
        brier=float(np.mean((all_p - all_y) ** 2)),
        baseline_logloss=float(baseline_scores.mean()),
        baseline_brier=float(np.mean((BASELINE_RATE - all_y) ** 2)),
        paired_t=t_stat,
        hit_at_27=float(np.mean(hit_at_27)),
        baseline_hit_at_27=float(np.mean(baseline_hit)),
        calibration_error=_calibration_error(all_p, all_y),
    )


def default_models() -> list[SequenceModel]:
    return [
        UniformBaseline(),
        EmpiricalFrequency(),
        BetaBinomialShrinkage(),
        MarkovChain(order=1, pooled=True),
        MarkovChain(order=2, pooled=True),
        MarkovChain(order=1, pooled=False),
        GapHazard(),
        HiddenMarkovRegime(),
        ClusterRate(n_clusters=4),
        gradient_boosting(),
        high_capacity_network(),
    ]


__all__ = [
    "BASELINE_RATE",
    "BetaBinomialShrinkage",
    "ClusterRate",
    "EmpiricalFrequency",
    "Evaluation",
    "GapHazard",
    "HiddenMarkovRegime",
    "LogisticRegression",
    "MarkovChain",
    "SequenceModel",
    "SupervisedModel",
    "UniformBaseline",
    "build_features",
    "default_models",
    "gradient_boosting",
    "high_capacity_network",
    "walk_forward",
]


class ShrinkageEnsemble:

    name = "Kết hợp co rút"
    family = "ensemble"

    def __init__(
        self,
        models: list[SequenceModel] | None = None,
        *,
        evidence_window: int = 90,
        alpha: float = 0.05,
        revalidate_every: int = 14,
    ) -> None:
        self.models = (
            models
            if models is not None
            else [
                BetaBinomialShrinkage(),
                MarkovChain(order=1, pooled=True),
                GapHazard(),
                gradient_boosting(),
            ]
        )
        self.evidence_window = int(evidence_window)
        self.alpha = float(alpha)
        self.revalidate_every = int(revalidate_every)
        self._weights: np.ndarray | None = None
        self._validated_at = -1

    @property
    def threshold(self) -> float:
        return float(stats.norm.isf(self.alpha / (2 * max(len(self.models), 1))))

    def _evidence(self, history: np.ndarray) -> np.ndarray:
        window = min(self.evidence_window, history.shape[0] // 2)
        start = history.shape[0] - window
        statistics = np.zeros(len(self.models))
        for index, model in enumerate(self.models):
            differences = []
            for day in range(start, history.shape[0]):
                p = _clip(np.asarray(model.predict_next(history[:day]), dtype=float))
                outcome = (history[day] > 0).astype(float)
                model_loss = -np.mean(outcome * np.log(p) + (1 - outcome) * np.log1p(-p))
                b = BASELINE_RATE
                baseline_loss = -np.mean(outcome * np.log(b) + (1 - outcome) * np.log1p(-b))
                differences.append(baseline_loss - model_loss)
            values = np.asarray(differences)
            spread = values.std(ddof=1)
            statistics[index] = (
                values.mean() / (spread / np.sqrt(values.size)) if spread > 0 else 0.0
            )
        return statistics

    def weights(self, history: np.ndarray) -> np.ndarray:
        if self._weights is None or history.shape[0] - self._validated_at >= self.revalidate_every:
            excess = np.maximum(self._evidence(history) - self.threshold, 0.0) ** 2
            total = excess.sum()
            self._weights = np.append(excess / (total + 1.0), 1.0 / (total + 1.0))
            self._validated_at = history.shape[0]
        return self._weights

    def predict_next(self, history: np.ndarray) -> np.ndarray:
        if history.shape[0] < self.evidence_window * 2:
            return np.full(NUMBER_SPACE, BASELINE_RATE)
        weights = self.weights(history)
        stacked = np.stack(
            [np.asarray(m.predict_next(history), dtype=float) for m in self.models]
            + [np.full(NUMBER_SPACE, BASELINE_RATE)]
        )
        return _clip(weights @ stacked)


__all__ += ["ShrinkageEnsemble"]
