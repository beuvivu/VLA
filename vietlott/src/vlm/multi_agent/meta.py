'Hedge theo ngữ cảnh, chọn nhiệt độ theo thời gian và kiểm toán bằng chứng.'
from __future__ import annotations

import math
import copy
from collections.abc import Sequence
from numbers import Integral

import numpy as np

from .models import SubsetDistribution


EXPERT_NAMES = ('statistical', 'bayesian_markov_graph', 'temporal_neural', 'uniform')


def mixture_log_prob(distributions: Sequence[SubsetDistribution], weights: Sequence[float],
                     outcome: Sequence[int]) -> float:
    values = np.array([math.log(float(w)) + d.log_prob(outcome)
                       for w, d in zip(weights, distributions, strict=True)])
    # A proper mixture has probability at most one; remove positive ulp noise.
    return min(0.0, float(np.logaddexp.reduce(values)))


def mixture_marginals(distributions: Sequence[SubsetDistribution], weights: Sequence[float]) -> np.ndarray:
    return sum((float(w) * d.marginals for w, d in zip(weights, distributions, strict=True)),
               start=np.zeros(len(distributions[0].marginals)))


class MetaLearner:
    'Chỉ cập nhật loss trên các dự báo đã khóa trước khi biết kết quả.\n\nE-process kiểm giả thuyết phân phối đều có điều kiện, không reset hay discount. Loss dùng để thích nghi không phải mức tin cậy đã hiệu chuẩn.'

    def __init__(self, n: int, k: int) -> None:
        self.n, self.k = n, k
        self.temperatures = (1.0, 2.0, 4.0)
        self.eta, self.discount, self.floor = .3, .98, .03
        self.losses = np.zeros((2, 4))
        self.temperature_losses = np.zeros(3)
        self.count = 0
        self.log_e_value = 0.0
        self.records: list[dict] = []
        self.expert_brier = np.zeros(4)
        self.alpha, self.minimum_evidence = .05, 64

    @property
    def uniform_log_loss(self) -> float:
        return math.log(math.comb(self.n, self.k))

    def context(self, history: np.ndarray) -> int:
        if len(history) < 40:
            return 0
        # Total variation of normalized inclusion frequencies (sum one).
        distance = np.abs(history[-20:].mean(axis=0) - history[-40:-20].mean(axis=0)).sum() / (2 * self.k)
        return int(distance > .25)

    def weights(self, context: int) -> np.ndarray:
        scores = -self.eta * self.losses[context]
        soft = np.exp(scores - scores.max())
        soft /= soft.sum()
        return (1 - self.floor) * soft + self.floor / 4

    def temperature(self) -> float:
        return self.temperatures[int(np.argmin(self.temperature_losses))] if self.count >= 16 else 1.0

    def evidence(self) -> dict:
        recent = self.records[-64:]
        gain = float(np.mean([r['shadow_log_gain'] for r in recent])) if recent else 0.0
        enabled = (self.count >= self.minimum_evidence
                   and self.log_e_value >= math.log(1 / self.alpha) and gain > 0)
        return {'cycles_scored': self.count, 'log_e_value': self.log_e_value,
                'log_e_threshold': math.log(1 / self.alpha), 'alpha': self.alpha,
                'minimum_cycles': self.minimum_evidence, 'recent_shadow_mean_log_gain': gain,
                'adaptive_enabled': bool(enabled),
                'null_hypothesis': 'Every next k-subset is conditionally uniform.',
                'interpretation': 'Evidence against the null; not future accuracy or profit.'}

    def diagnostics(self) -> dict:
        if not self.records:
            return {'sample_cycles': 0, 'calibration_status': 'insufficient_evidence'}
        probabilities = np.array([r['marginals'] for r in self.records])
        outcomes = np.array([r['target'] for r in self.records])
        bins = []
        edges = np.linspace(0.0, 1.0, 11)
        # Integer membership has no gaps from separately rounded float edges.
        membership = np.minimum(np.searchsorted(edges, probabilities, side='right') - 1, 9)
        for index, (left, right) in enumerate(zip(edges[:-1], edges[1:], strict=True)):
            mask = membership == index
            if mask.any():
                bins.append({'lower': float(left), 'upper': float(min(1, right)),
                             'label_observations': int(mask.sum()),
                             'mean_probability': float(probabilities[mask].mean()),
                             'observed_rate': float(outcomes[mask].mean())})
        return {'sample_cycles': len(self.records),
                'mean_log_loss': float(np.mean([r['log_loss'] for r in self.records])),
                'mean_brier': float(np.mean([r['brier'] for r in self.records])),
                'calibration_bins': bins,
                'calibration_status': 'empirical_only_no_calibration_guarantee',
                'note': 'Labels within a cycle are dependent; bin counts are not independent trials.'}

    def update(self, pending: dict, outcome: Sequence[int]) -> dict:
        target = np.zeros(self.n)
        target[list(outcome)] = 1
        weights = pending['weights']
        base_logits = pending['logits']
        candidate_losses = []
        candidates = []
        for temp in self.temperatures:
            distributions = [SubsetDistribution(np.array(v) / temp, self.k) for v in base_logits]
            candidates.append(distributions)
            candidate_losses.append(-mixture_log_prob(distributions, weights, outcome))
        chosen = self.temperatures.index(pending['temperature'])
        shadow_loss = candidate_losses[chosen]
        distributions = candidates[chosen]
        expert_losses = np.array([-d.log_prob(outcome) for d in distributions])
        context = pending['context']  # Never infer context from the outcome.
        self.losses[context] = self.discount * self.losses[context] + expert_losses
        self.temperature_losses = self.discount * self.temperature_losses + candidate_losses
        self.expert_brier = .98 * self.expert_brier + .02 * np.array([
            float(np.mean((d.marginals - target) ** 2)) for d in distributions])
        issued = pending['public']
        actual_loss = shadow_loss if issued['mode'] == 'adaptive' else self.uniform_log_loss
        brier = float(np.mean((np.array(issued['marginals']) - target) ** 2))
        gain = self.uniform_log_loss - shadow_loss
        self.log_e_value += gain
        self.count += 1
        record = {'log_loss': float(actual_loss), 'brier': brier, 'shadow_log_gain': float(gain),
                  'marginals': issued['marginals'], 'target': target.tolist()}
        self.records.append(record)
        self.records = self.records[-256:]
        return {'log_loss': float(actual_loss), 'brier': brier, 'shadow_log_gain': float(gain),
                'updated_weights': dict(zip(EXPERT_NAMES, self.weights(context).tolist(), strict=True)),
                'confidence_matrix': {
                    name: {'discounted_log_loss': float(self.losses[context, j]),
                           'ewma_brier': float(self.expert_brier[j])}
                    for j, name in enumerate(EXPERT_NAMES)},
                'next_temperature': self.temperature(), 'evidence': self.evidence()}

    def state_dict(self) -> dict:
        return {'losses': self.losses.tolist(), 'temperature_losses': self.temperature_losses.tolist(),
                'count': self.count, 'log_e_value': self.log_e_value, 'records': copy.deepcopy(self.records),
                'expert_brier': self.expert_brier.tolist()}

    def load_state_dict(self, state: dict) -> None:
        try:
            losses = np.array(state['losses'], dtype=float)
            temperatures = np.array(state['temperature_losses'], dtype=float)
            brier = np.array(state['expert_brier'], dtype=float)
            count, log_e = state['count'], float(state['log_e_value'])
            records = copy.deepcopy(state['records'])
            if (losses.shape != (2, 4) or temperatures.shape != (3,) or brier.shape != (4,)
                    or not all(np.isfinite(a).all() and (a >= 0).all() for a in (losses, temperatures, brier))
                    or (brier > 1).any() or not math.isfinite(log_e)
                    or isinstance(count, bool) or not isinstance(count, Integral) or count < 0
                    or not isinstance(records, list) or len(records) != min(count, 256)):
                raise ValueError('Invalid meta-learner checkpoint.')
            for record in records:
                probabilities = np.array(record['marginals'], dtype=float)
                target = np.array(record['target'], dtype=float)
                metrics = [record['log_loss'], record['brier'], record['shadow_log_gain']]
                if (probabilities.shape != (self.n,) or target.shape != (self.n,)
                        or not np.isfinite(probabilities).all() or not np.isfinite(metrics).all()
                        or (probabilities < 0).any() or (probabilities > 1).any()
                        or not np.isclose(probabilities.sum(), self.k)
                        or not np.isin(target, (0, 1)).all() or target.sum() != self.k
                        or record['log_loss'] < -1e-10 or not 0 <= record['brier'] <= 1):
                    raise ValueError('Invalid prospective diagnostic record.')
        except (KeyError, TypeError, OverflowError) as error:
            raise ValueError('Malformed meta-learner checkpoint.') from error
        self.losses, self.temperature_losses, self.expert_brier = losses, temperatures, brier
        self.count, self.log_e_value, self.records = int(count), log_e, records
