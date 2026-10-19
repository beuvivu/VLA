'Điều phối dự báo trước phản hồi, giao dịch nguyên tử và khôi phục trạng thái.'
from __future__ import annotations

import asyncio
import copy
import math
from collections.abc import Sequence
from numbers import Integral

import numpy as np

from .memory import KnowledgeBaseManager
from .meta import EXPERT_NAMES, MetaLearner, mixture_log_prob, mixture_marginals
from .models import AlgorithmEnsemble, SubsetDistribution
from .store import StateStore


class PredictiveEngine:
    'Mỗi engine ứng với một không gian kết quả; nhãn đánh số từ 0.\n\nMỗi kỳ chỉ có một dự báo chờ kết quả. Writer cũ phải nạp lại trạng thái và thử lại.'

    def __init__(self, n: int, k: int, database: str = ':memory:', seed: int = 42) -> None:
        if (isinstance(n, bool) or isinstance(k, bool) or not isinstance(n, Integral)
                or not isinstance(k, Integral) or not 1 <= k <= n <= 200):
            raise ValueError('Require integers 1 <= k <= n <= 200.')
        if isinstance(seed, bool) or not isinstance(seed, Integral) or seed < 0:
            raise ValueError('seed must be a nonnegative integer.')
        self.n, self.k, self.seed = int(n), int(k), int(seed)
        self.store = StateStore(database, {'n': self.n, 'k': self.k, 'seed': self.seed, 'schema': 1})
        self._lock = asyncio.Lock()
        self._closed = False
        try:
            self._reload()
        except BaseException:
            self.store.close()
            raise

    def _reload(self) -> None:
        self.revision, state = self.store.load()
        self.knowledge = KnowledgeBaseManager(self.n, self.k)
        self.ensemble = AlgorithmEnsemble(self.n, self.k, self.seed)
        self.meta = MetaLearner(self.n, self.k)
        self.next_cycle = 0
        self.pending: dict | None = None
        if state:
            if state.get('schema') != 1:
                raise ValueError('Unsupported checkpoint schema.')
            self.knowledge.load_state_dict(state['knowledge'])
            self.ensemble.load_state_dict(state['ensemble'])
            self.meta.load_state_dict(state['meta'])
            self.next_cycle, self.pending = state['next_cycle'], state['pending']
            if (isinstance(self.next_cycle, bool) or not isinstance(self.next_cycle, int)
                    or self.next_cycle < 0 or self.next_cycle != self.meta.count
                    or self.next_cycle != self.knowledge.total_observations):
                raise ValueError('Checkpoint observation counts are inconsistent.')
            if self.pending is not None:
                if (not isinstance(self.pending, dict)
                        or self.pending.get('public', {}).get('cycle') != self.next_cycle
                        or self.store.lookup('forecasts', self.next_cycle) != self.pending['public']):
                    raise ValueError('Pending forecast differs from its immutable ledger.')

    def _state(self) -> dict:
        return {'schema': 1, 'next_cycle': self.next_cycle, 'pending': self.pending,
                'knowledge': self.knowledge.state_dict(), 'ensemble': self.ensemble.state_dict(),
                'meta': self.meta.state_dict()}

    def _check(self, cycle: int) -> None:
        if self._closed:
            raise RuntimeError('Engine is closed.')
        if isinstance(cycle, bool) or not isinstance(cycle, Integral) or cycle < 0:
            raise ValueError('cycle must be a nonnegative integer.')
        latest, _ = self.store.load()
        if latest != self.revision:
            self._reload()
            raise RuntimeError('Stale writer: state reloaded; retry the operation.')

    def _outcome(self, values: Sequence[int]) -> tuple[int, ...]:
        items = tuple(values)
        if len(items) != self.k or any(isinstance(v, bool) or not isinstance(v, Integral)
                                      or not 0 <= v < self.n for v in items):
            raise ValueError('Outcome must contain exactly k valid distinct integer labels.')
        result = tuple(sorted(int(v) for v in items))
        if len(set(result)) != self.k:
            raise ValueError('Duplicate labels are not allowed.')
        return result

    async def predict(self, cycle: int) -> dict:
        async with self._lock:
            self._check(cycle)
            historical = self.store.lookup('forecasts', int(cycle))
            if historical is not None:
                return historical
            if cycle != self.next_cycle or self.pending is not None:
                raise ValueError('Predict the next cycle only; resolve its pending outcome first.')
            try:
                history = self.knowledge.history.copy()
                retrieved, matches = self.knowledge.retrieve()
                forecasts = await self.ensemble.predict(history, retrieved)
                by_name = {f.name: f for f in forecasts}
                if set(by_name) != set(EXPERT_NAMES[:-1]):
                    raise ValueError('Ensemble expert names differ from the model contract.')
                logits = [list(by_name[name].logits) for name in EXPERT_NAMES[:-1]] + [[0.] * self.n]
                context = self.meta.context(history)
                weights = self.meta.weights(context)
                temp = self.meta.temperature()
                distributions = [SubsetDistribution(np.array(v) / temp, self.k) for v in logits]
                shadow_marginals = mixture_marginals(distributions, weights)
                evidence = self.meta.evidence()
                mode = 'adaptive' if evidence['adaptive_enabled'] else 'uniform_baseline'
                marginals = shadow_marginals if mode == 'adaptive' else np.full(self.n, self.k / self.n)
                # Selection maximizes expected overlap; it need not be the joint MAP subset.
                selected = sorted(np.argsort(-marginals, kind='stable')[:self.k].tolist())
                log_probability = (mixture_log_prob(distributions, weights, selected)
                                   if mode == 'adaptive' else -self.meta.uniform_log_loss)
                probability = math.exp(log_probability)
                explanations = [
                    {'expert': name, 'weight': float(weights[j]),
                     'selected_label_marginals': {str(i): float(distributions[j].marginals[i])
                                                  for i in selected},
                     'evidence': by_name[name].evidence if name in by_name else {'assumption': 'uniform'}}
                    for j, name in enumerate(EXPERT_NAMES)]
                risks = ['Model probabilities are estimates; calibration is measured prospectively.',
                         'Historical similarity and recurrence do not establish causality.',
                         'Distribution drift, source errors and small samples can invalidate estimates.']
                if mode == 'uniform_baseline':
                    risks.append('Insufficient prospective evidence: deployed forecast is uniform.')
                public = {
                    'cycle': int(cycle), 'n': self.n, 'k': self.k, 'trained_through_cycle': self.next_cycle - 1,
                    'selected': selected, 'marginals': marginals.tolist(),
                    'selected_set_probability': probability, 'confidence_score_pct': 100 * probability,
                    'confidence_event': 'The entire selected unordered subset exactly matches the next outcome.',
                    'expected_matches': float(marginals[selected].sum()),
                    'selection_objective': 'maximize_expected_overlap_not_joint_MAP',
                    'expert_weights': dict(zip(EXPERT_NAMES, weights.tolist(), strict=True)),
                    'temperature': temp, 'context': 'shift' if context else 'stable', 'mode': mode,
                    'uniform_set_probability': math.exp(-self.meta.uniform_log_loss),
                    'evidence': evidence, 'calibration': self.meta.diagnostics(),
                    'memory_matches': matches, 'explanations': explanations, 'risks': risks}
                self.pending = {'public': public, 'logits': logits, 'weights': weights.tolist(),
                                'temperature': temp, 'context': context}
                self.revision = self.store.commit(self.revision, self._state(), forecast=public)
                return copy.deepcopy(public)
            except BaseException:
                self._reload()
                raise

    async def observe(self, cycle: int, outcome: Sequence[int]) -> dict:
        async with self._lock:
            self._check(cycle)
            labels = self._outcome(outcome)
            prior = self.store.lookup('outcomes', int(cycle))
            if prior is not None:
                if prior['outcome'] != list(labels):
                    raise ValueError('Conflicting outcome: immutable feedback already exists.')
                return prior
            if cycle != self.next_cycle or self.pending is None:
                raise ValueError('Commit the next-cycle forecast before observing its outcome.')
            try:
                target = np.zeros(self.n)
                target[list(labels)] = 1
                metrics = self.meta.update(self.pending, labels)
                self.ensemble.learn(self.knowledge.history.copy(), target)
                self.knowledge.ingest(int(cycle), labels)
                result = {'cycle': int(cycle), 'outcome': list(labels), **metrics}
                self.next_cycle += 1
                self.pending = None
                self.revision = self.store.commit(self.revision, self._state(), outcome=result)
                return copy.deepcopy(result)
            except BaseException:
                self._reload()
                raise

    def close(self) -> None:
        if not self._closed:
            self.store.close()
            self._closed = True
