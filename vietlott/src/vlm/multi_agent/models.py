'Phân phối tập đúng k phần tử và ba chuyên gia học từ quá khứ.'

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from numbers import Integral
from typing import Sequence

import numpy as np


def _cardinality(n: int, k: int) -> tuple[int, int]:
    if (isinstance(n, bool) or not isinstance(n, Integral) or n < 1 or
            isinstance(k, bool) or not isinstance(k, Integral) or not 1 <= k <= n):
        raise ValueError('n and k must be integers with 1 <= k <= n')
    return int(n), int(k)


class SubsetDistribution:
    'P(S) tỷ lệ với exp(tổng logit của S), chỉ trên tập có đúng k phần tử. Quy hoạch động miền log tính chuẩn hóa và các biên trong O(nk).'

    def __init__(self, logits: Sequence[float], k: int):
        try:
            values = np.asarray(logits, dtype=np.longdouble)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError('logits must be a finite vector') from exc
        if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
            raise ValueError('logits must be a nonempty finite vector')
        self.n, self.k = _cardinality(len(values), k)
        self._order = np.argsort(-values, kind='stable')
        self._logits = values[self._order].copy()
        self._rank = np.empty(self.n, dtype=int)
        self._rank[self._order] = np.arange(self.n)
        self._dp = np.full((self.n + 1, self.k + 1), -np.inf, dtype=np.longdouble)
        self._dp[:, 0] = 0
        for i, value in enumerate(self._logits, 1):
            for j in range(1, min(i, self.k) + 1):
                # Normalize each column by the best j-subset's score. Sorting
                # makes its baseline identical across rows, so even 1e308 ties
                # retain their log multiplicity rather than losing log(2).
                penalty = value - self._logits[j - 1]
                self._dp[i, j] = np.logaddexp(self._dp[i - 1, j],
                                             self._dp[i - 1, j - 1] + penalty)
        self._marginals: np.ndarray | None = None

    def _differentiate(self) -> np.ndarray:
        if self.k == self.n:
            return np.ones(self.n)
        adjoint = np.zeros_like(self._dp)
        adjoint[self.n, self.k] = 1
        marginal = np.zeros(self.n, dtype=np.longdouble)
        for i in range(self.n, 0, -1):
            for j in range(min(i, self.k) + 1):
                mass = adjoint[i, j]
                if mass == 0:
                    continue
                if j == 0:
                    adjoint[i - 1, 0] += mass
                    continue
                excluded = self._dp[i - 1, j]
                included = (self._dp[i - 1, j - 1] +
                            (self._logits[i - 1] - self._logits[j - 1]))
                if np.isneginf(excluded):
                    probability = np.longdouble(1)
                elif np.isneginf(included):
                    probability = np.longdouble(0)
                else:
                    difference = included - excluded
                    exponential = np.exp(-abs(difference))
                    probability = (1 / (1 + exponential) if difference >= 0
                                   else exponential / (1 + exponential))
                marginal[i - 1] += mass * probability
                adjoint[i - 1, j - 1] += mass * probability
                adjoint[i - 1, j] += mass * (1 - probability)
        result = np.empty(self.n)
        result[self._order] = np.asarray(np.clip(marginal, 0, 1), dtype=float)
        return result

    @property
    def marginals(self) -> np.ndarray:
        'Trả bản sao xác suất xuất hiện từng nhãn, có tổng bằng k.'
        if self._marginals is None:
            self._marginals = self._differentiate()
        return self._marginals.copy()

    def log_prob(self, outcome: Sequence[int]) -> float:
        try:
            labels = list(outcome)
        except TypeError as exc:
            raise ValueError('outcome must contain k distinct integer labels') from exc
        if (len(labels) != self.k or
                any(isinstance(i, (bool, np.bool_)) or not isinstance(i, Integral)
                    or not 0 <= i < self.n for i in labels) or
                len(set(labels)) != self.k):
            raise ValueError('outcome must contain k distinct integer labels in 0..n-1')
        if self.k == self.n:
            return 0.0
        selected = self._logits[np.sort(self._rank[labels])]
        deficit = np.sum(selected - self._logits[:self.k], dtype=np.longdouble)
        value = deficit - self._dp[self.n, self.k]
        # IEEE double cannot represent a log loss larger than its maximum.
        return min(0.0, float(value))


@dataclass(frozen=True)
class ExpertForecast:
    name: str
    logits: tuple[float, ...]
    evidence: dict


class AlgorithmEnsemble:
    'Thống kê có smoothing, liên hệ Markov/đồ thị và MLP trực tuyến. Dự báo chỉ đọc snapshot; gradient NLL bằng xác suất biên trừ nhãn thực.'

    def __init__(self, n: int, k: int, seed: int = 42):
        self.n, self.k = _cardinality(n, k)
        if isinstance(seed, bool) or not isinstance(seed, Integral) or seed < 0:
            raise ValueError('seed must be a nonnegative integer')
        self.seed, self.steps = int(seed), 0
        self.hidden = max(8, min(32, 2 * self.n))
        self.learning_rate, self.l2 = 0.08, 0.0001
        generator = np.random.default_rng(self.seed)
        self.w1 = generator.normal(0, 1 / np.sqrt(3 * self.n), (self.hidden, 3 * self.n))
        self.b1 = np.zeros(self.hidden)
        self.w2 = generator.normal(0, 0.1 / np.sqrt(self.hidden), (self.n, self.hidden))
        self.b2 = np.zeros(self.n)

    def _history(self, history: np.ndarray) -> np.ndarray:
        try:
            array = np.array(history, dtype=float, copy=True)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError('history must be a finite binary matrix') from exc
        if (array.ndim != 2 or array.shape[1] != self.n or
                not np.all(np.isfinite(array)) or not np.all((array == 0) | (array == 1)) or
                not np.all(array.sum(axis=1) == self.k)):
            raise ValueError('history must have shape (t, n) with exactly k binary labels per row')
        array.setflags(write=False)
        return array

    def _retrieved(self, retrieved: np.ndarray) -> np.ndarray:
        try:
            scores = np.array(retrieved, dtype=float, copy=True)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError('retrieved scores must be a finite vector') from exc
        if (scores.shape != (self.n,) or not np.all(np.isfinite(scores)) or
                np.any(scores < 0) or not np.isclose(scores.sum(), self.k, rtol=1e-9, atol=1e-9)):
            raise ValueError('retrieved scores must be nonnegative with shape (n,) and sum k')
        scores.setflags(write=False)
        return scores

    @staticmethod
    def _forecast(name: str, logits: np.ndarray, evidence: dict) -> ExpertForecast:
        centered = logits - np.mean(logits)
        return ExpertForecast(name, tuple(float(x) for x in centered), evidence)

    def _statistical(self, history: np.ndarray, retrieved: np.ndarray) -> ExpertForecast:
        t = len(history)
        prior = self.k / self.n
        frequency = (history.sum(axis=0) + 2 * prior) / (t + 2)
        logits = np.log(frequency)
        matches: dict[str, int] = {}
        for order in (1, 2):
            targets = [history[i] for i in range(order, t)
                       if np.array_equal(history[i - order:i], history[-order:])]
            matches[str(order)] = len(targets)
            if targets:
                conditional = (np.sum(targets, axis=0) + 2 * frequency) / (len(targets) + 2)
                strength = min(0.5, len(targets) / (len(targets) + 4))
                logits += strength * (np.log(conditional) - np.log(frequency))
        lag_evidence = []
        if t >= 4:
            baseline_overlap = float(np.dot(frequency, frequency))
            for lag in range(1, min(12, t // 2) + 1):
                pairs = t - lag
                overlap = float(np.sum(history[:-lag] * history[lag:]) / pairs)
                excess = max(0.0, (overlap - baseline_overlap) / self.k)
                reliability = excess * pairs / (pairs + 8)
                if reliability > 0:
                    logits += 0.3 * reliability * (history[-lag] - prior)
                    lag_evidence.append({'lag': lag, 'pairs': pairs, 'weight': reliability})
        return self._forecast('statistical', logits, {
            'history_rows': t, 'ngram_matches': matches, 'lag_associations': lag_evidence,
            'smoothing_mass': 2.0,
        })

    def _bayesian(self, history: np.ndarray, retrieved: np.ndarray) -> ExpertForecast:
        t, prior, alpha = len(history), self.k / self.n, 2.0
        if t:
            counts = history.sum(axis=0)
            frequency = (counts + alpha * prior) / (t + alpha)
            last = history[-1]
            if t > 1:
                transition = history[:-1].T @ history[1:]
                posterior = (transition + alpha * frequency) / (history[:-1].sum(axis=0)[:, None] + alpha)
                markov = (last @ posterior) / self.k
            else:
                markov = frequency
            cooccurrence = history.T @ history
            np.fill_diagonal(cooccurrence, 0)
            if self.k > 1:
                graph = last @ cooccurrence + alpha * frequency
                graph *= self.k / graph.sum()
            else:
                graph = frequency
        else:
            markov = graph = np.full(self.n, prior)
        memory = (retrieved + alpha * prior) / (1 + alpha)
        logits = 0.65 * np.log(markov) + 0.25 * np.log(graph) + 0.1 * np.log(memory)
        return self._forecast('bayesian_markov_graph', logits, {
            'history_rows': t, 'transition_pairs': max(0, t - 1),
            'cooccurrence_rows': t, 'prior_mass': alpha,
            'interpretation': 'smoothed predictive associations; no causal identification',
        })

    def _features(self, history: np.ndarray) -> np.ndarray:
        if not len(history):
            return np.zeros(3 * self.n)
        prior = self.k / self.n
        return np.concatenate((history[-1] - prior, history[-5:].mean(axis=0) - prior,
                               history.mean(axis=0) - prior))

    def _neural(self, history: np.ndarray, weights: tuple[np.ndarray, ...], steps: int) -> ExpertForecast:
        w1, b1, w2, b2 = weights
        hidden = np.tanh(w1 @ self._features(history) + b1)
        return self._forecast('temporal_neural', w2 @ hidden + b2, {
            'history_rows': len(history), 'training_steps': steps,
            'features': ['last_observation', 'last_five_mean', 'history_mean'],
            'objective': 'exact_fixed_cardinality_log_loss',
        })

    def predict_sync(self, history: np.ndarray, retrieved: np.ndarray) -> list[ExpertForecast]:
        'Cùng ba phép tính bất biến, dùng trong giao dịch đồng bộ của engine Vietlott.'
        frozen_history, frozen_retrieved = self._history(history), self._retrieved(retrieved)
        weights = tuple(array.copy() for array in (self.w1, self.b1, self.w2, self.b2))
        return [self._statistical(frozen_history, frozen_retrieved),
                self._bayesian(frozen_history, frozen_retrieved),
                self._neural(frozen_history, weights, self.steps)]

    async def predict(self, history: np.ndarray, retrieved: np.ndarray) -> list[ExpertForecast]:
        'Điều phối ba chuyên gia trên cùng snapshot bất biến.'
        frozen_history, frozen_retrieved = self._history(history), self._retrieved(retrieved)
        weights = tuple(array.copy() for array in (self.w1, self.b1, self.w2, self.b2))
        for array in weights:
            array.setflags(write=False)
        steps = self.steps
        return list(await asyncio.gather(
            asyncio.to_thread(self._statistical, frozen_history, frozen_retrieved),
            asyncio.to_thread(self._bayesian, frozen_history, frozen_retrieved),
            asyncio.to_thread(self._neural, frozen_history, weights, steps),
        ))

    def learn(self, history: np.ndarray, outcome: np.ndarray) -> None:
        'Học đúng một kết quả nhị phân, với lịch sử chưa chứa kết quả đó.'
        frozen_history = self._history(history)
        try:
            observed = np.asarray(outcome, dtype=float)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError('outcome must be a binary n-vector with k labels') from exc
        if (observed.shape != (self.n,) or not np.all(np.isfinite(observed)) or
                not np.all((observed == 0) | (observed == 1)) or observed.sum() != self.k):
            raise ValueError('outcome must be a binary n-vector with k labels')
        x = self._features(frozen_history)
        hidden = np.tanh(self.w1 @ x + self.b1)
        gradient = SubsetDistribution(self.w2 @ hidden + self.b2, self.k).marginals - observed
        hidden_gradient = (self.w2.T @ gradient) * (1 - hidden * hidden)
        gradients = (np.outer(hidden_gradient, x) + self.l2 * self.w1, hidden_gradient,
                     np.outer(gradient, hidden) + self.l2 * self.w2, gradient)
        norm = float(np.sqrt(sum(float(np.sum(g * g)) for g in gradients)))
        rate = self.learning_rate / np.sqrt(1 + self.steps / 200) * min(1.0, 5.0 / max(norm, 1e-12))
        updated = [weight - rate * grad for weight, grad in
                   zip((self.w1, self.b1, self.w2, self.b2), gradients)]
        if not all(np.all(np.isfinite(array)) for array in updated):
            raise FloatingPointError('neural update produced nonfinite parameters')
        self.w1, self.b1, self.w2, self.b2 = updated
        self.steps += 1

    def state_dict(self) -> dict:
        return {'version': 1, 'n': self.n, 'k': self.k, 'seed': self.seed, 'steps': self.steps,
                'learning_rate': self.learning_rate, 'l2': self.l2,
                'weights': {name: getattr(self, name).tolist() for name in ('w1', 'b1', 'w2', 'b2')}}

    def load_state_dict(self, state: dict) -> None:
        'Xác thực toàn bộ JSON an toàn trước khi thay trạng thái đang dùng.'
        try:
            if (state['version'] != 1 or state['n'] != self.n or state['k'] != self.k or
                    any(isinstance(state[field], bool) or not isinstance(state[field], Integral) or
                        state[field] < 0 for field in ('seed', 'steps'))):
                raise ValueError('snapshot schema or dimensions do not match')
            rate, l2 = float(state['learning_rate']), float(state['l2'])
            if not np.isfinite(rate) or not 0 < rate <= 1 or not np.isfinite(l2) or not 0 <= l2 <= 1:
                raise ValueError('invalid optimizer configuration')
            arrays = [np.array(state['weights'][name], dtype=float, copy=True)
                      for name in ('w1', 'b1', 'w2', 'b2')]
            shapes = [(self.hidden, 3 * self.n), (self.hidden,), (self.n, self.hidden), (self.n,)]
            if any(array.shape != shape or not np.all(np.isfinite(array))
                   for array, shape in zip(arrays, shapes)):
                raise ValueError('invalid neural parameters')
        except (KeyError, TypeError, OverflowError) as exc:
            raise ValueError('invalid model snapshot') from exc
        self.w1, self.b1, self.w2, self.b2 = arrays
        self.seed, self.steps = int(state['seed']), int(state['steps'])
        self.learning_rate, self.l2 = rate, l2
