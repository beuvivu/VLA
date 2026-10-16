"""Nhóm chuyên gia lồng nhau: giữ nguyên phân phối tập khi nối vào pipeline thật."""
from __future__ import annotations

from copy import deepcopy

import numpy as np
from scipy.special import logsumexp

from vlm.multi_agent.memory import KnowledgeBaseManager
from vlm.multi_agent.meta import EXPERT_NAMES, MetaLearner, mixture_marginals
from vlm.multi_agent.models import AlgorithmEnsemble, SubsetDistribution


class MultiAgentExpert:
    """Ba lớp cùng bộ nhớ và meta; checkpoint/giao dịch do MLForecaster quản lý.

    Các điểm số ở đây là hồi cứu theo thứ tự thời gian. Chỉ ledger live của
    MLForecaster được dùng để chứng nhận và quyết định xác suất công bố.
    """

    def __init__(self, n: int, k: int, seed: int = 42) -> None:
        self.n, self.k, self.seed = n, k, seed
        self.knowledge = KnowledgeBaseManager(n, k)
        self.ensemble = AlgorithmEnsemble(n, k, seed)
        self.meta = MetaLearner(n, k)

    def _packet(self) -> dict:
        history = self.knowledge.history
        retrieved, matches = self.knowledge.retrieve()
        forecasts = self.ensemble.predict_sync(history, retrieved)
        by_name = {f.name: f for f in forecasts}
        logits = [np.clip(by_name[name].logits, -4, 4).tolist()
                  for name in EXPERT_NAMES[:-1]] + [[0.] * self.n]
        context = self.meta.context(history)
        weights = self.meta.weights(context)
        temperature = self.meta.temperature()
        distributions = [SubsetDistribution(np.array(z) / temperature, self.k) for z in logits]
        return {'logits': logits, 'weights': weights.tolist(), 'context': context,
                'temperature': temperature,
                'public': {'mode': 'adaptive', 'marginals': mixture_marginals(distributions, weights).tolist()},
                'matches': matches,
                'explanations': [{'expert': f.name, 'evidence': f.evidence} for f in forecasts]}

    def distribution(self) -> tuple[np.ndarray, np.ndarray]:
        """Trả bốn phân phối con; tuyệt đối không xấp xỉ mixture bằng tích các biên."""
        packet = self._packet()
        z = np.array(packet['logits']) / packet['temperature']
        return np.exp(z - z.max(axis=1, keepdims=True)), np.array(packet['weights'])

    def group_log_likelihood(self, expert_log_likelihoods: np.ndarray) -> float:
        """Gộp likelihood bốn con theo đúng trọng số trước khi nhận nhãn."""
        if np.asarray(expert_log_likelihoods).shape != (4,):
            raise ValueError('Nhóm đa thuật toán phải có đúng bốn likelihood.')
        weights = self.meta.weights(self.meta.context(self.knowledge.history))
        return float(logsumexp(np.log(weights) + expert_log_likelihoods))

    def learn(self, outcome: np.ndarray) -> None:
        """Chấm snapshot trước, cập nhật meta/neural/bộ nhớ sau, mỗi kỳ đúng một lần."""
        row = self.ensemble._history(np.asarray(outcome).reshape(1, -1))[0]
        packet = self._packet()
        labels = np.flatnonzero(row).tolist()
        cycle = self.knowledge.total_observations
        self.meta.update(packet, labels)
        self.ensemble.learn(self.knowledge.history, row)
        self.knowledge.ingest(cycle, labels)

    def report(self) -> dict:
        """Chẩn đoán đọc từ trạng thái thật, phân biệt rõ hồi cứu với bằng chứng live."""
        packet = self._packet()
        return {'observations': self.knowledge.total_observations,
                'weights': dict(zip(EXPERT_NAMES, packet['weights'], strict=True)),
                'temperature': packet['temperature'],
                'context': 'shift' if packet['context'] else 'stable',
                'short_window': self.knowledge.short_window,
                'retained_observations': len(self.knowledge.history),
                'memory_matches': deepcopy(packet['matches']),
                'explanations': deepcopy(packet['explanations']),
                'calibration': self.meta.diagnostics(),
                'evaluation': 'retrospective_prequential_exploratory',
                'scope': 'main_set_only',
                'note': 'Trọng số này tham gia luật dự báo. Độ tin cậy công bố chỉ lấy từ sổ live.'}

    def to_dict(self) -> dict:
        return {'n': self.n, 'k': self.k, 'seed': self.seed,
                'knowledge': self.knowledge.state_dict(), 'ensemble': self.ensemble.state_dict(),
                'meta': self.meta.state_dict()}

    @classmethod
    def from_dict(cls, data: dict, *, n: int, k: int, seed: int) -> MultiAgentExpert:
        if (data['n'], data['k'], data['seed']) != (n, k, seed):
            raise ValueError('Checkpoint nhóm đa thuật toán khác cấu hình.')
        out = cls(n, k, seed)
        out.knowledge.load_state_dict(data['knowledge'])
        out.ensemble.load_state_dict(data['ensemble'])
        out.meta.load_state_dict(data['meta'])
        if out.knowledge.total_observations != out.meta.count or out.ensemble.steps != out.meta.count:
            raise ValueError('Số kỳ học của các lớp không đồng nhất.')
        return out
