'Thống kê cửa sổ ngắn và bộ nhớ ngữ cảnh số học có giới hạn.'

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Integral

import numpy as np


def _integer(value: object, name: str, minimum: int = 0) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer")
    result = int(value)
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


@dataclass
class _Association:
    context: np.ndarray
    outcome_counts: np.ndarray
    support: int
    first_cycle: int
    cycle: int

    def state_dict(self) -> dict:
        return {
            "context": self.context.tolist(),
            "outcome_counts": self.outcome_counts.tolist(),
            "support": self.support,
            "first_cycle": self.first_cycle,
            "cycle": self.cycle,
            "context_cutoff": self.cycle - 1,
        }


class KnowledgeBaseManager:
    'Lưu các liên hệ ngữ cảnh/kết quả đã quan sát cùng thống kê gần đây.\n\nNgữ cảnh được chụp trước khi biết kết quả. Độ tương đồng chỉ mô tả liên hệ, không xác lập nhân quả.'

    def __init__(
        self,
        n: int,
        k: int,
        short_window: int = 30,
        max_history: int = 512,
        max_rules: int = 1024,
    ) -> None:
        self.n = _integer(n, "n", 1)
        self.k = _integer(k, "k", 1)
        if self.k > self.n:
            raise ValueError("k must not exceed n")
        self.short_window = _integer(short_window, "short_window", 1)
        self.max_history = _integer(max_history, "max_history", 1)
        self.max_rules = _integer(max_rules, "max_rules", 1)
        if self.max_history < self.short_window:
            raise ValueError("max_history must be at least short_window")
        self._history: deque[np.ndarray] = deque(maxlen=self.max_history)
        self._rules: list[_Association] = []
        self._total_observations = 0

    @property
    def total_observations(self) -> int:
        'Tổng số kỳ đã quan sát, độc lập với giới hạn lưu lịch sử.'
        return self._total_observations

    @property
    def history(self) -> np.ndarray:
        'Ma trận kết quả theo thời gian, trả bản sao tách khỏi trạng thái.'
        if not self._history:
            return np.empty((0, self.n), dtype=np.uint8)
        return np.stack(self._history)

    def _recent(self) -> np.ndarray:
        return self.history[-self.short_window :]

    def _context(self) -> np.ndarray | None:
        recent = self._recent()
        if len(recent) == 0:
            return None
        uniform = np.full(self.n, self.k / self.n)
        frequencies = (recent.sum(axis=0) + 4.0 * uniform) / (len(recent) + 4.0)
        return np.concatenate((frequencies, recent[-1]))

    def _validate_outcome(self, outcome: Sequence[int]) -> np.ndarray:
        if isinstance(outcome, (str, bytes)) or not isinstance(outcome, (Sequence, np.ndarray)):
            raise TypeError("outcome must be a sequence of integer labels")
        if isinstance(outcome, np.ndarray) and outcome.ndim != 1:
            raise ValueError("outcome must be one-dimensional")
        labels = [_integer(label, "outcome label") for label in outcome]
        if len(labels) != self.k or len(set(labels)) != self.k:
            raise ValueError(f"outcome must contain exactly {self.k} distinct labels")
        if any(label >= self.n for label in labels):
            raise ValueError("outcome label is outside the population")
        vector = np.zeros(self.n, dtype=np.uint8)
        vector[labels] = 1
        return vector

    def ingest(self, cycle: int, outcome: Sequence[int]) -> None:
        'Xác thực đầy đủ rồi ghi kỳ tiếp theo, không sửa state khi đầu vào sai.'
        cycle = _integer(cycle, "cycle")
        if cycle != self._total_observations:
            raise ValueError(f"expected cycle {self._total_observations}, got {cycle}")
        vector = self._validate_outcome(outcome)
        context = self._context()  # The result has not entered history yet.
        if context is not None:
            existing = next(
                (index for index, rule in enumerate(self._rules) if np.array_equal(rule.context, context)),
                None,
            )
            if existing is None:
                rule = _Association(context, vector.astype(np.int64), 1, cycle, cycle)
            else:
                rule = self._rules.pop(existing)
                rule.outcome_counts += vector
                rule.support += 1
                rule.cycle = cycle
            self._rules.append(rule)
            if len(self._rules) > self.max_rules:
                self._rules.pop(0)
        self._history.append(vector)
        self._total_observations += 1

    def retrieve(self) -> tuple[np.ndarray, list[dict]]:
        'Trả xác suất biên tổng k và bằng chứng của tối đa tám ngữ cảnh.'
        uniform = np.full(self.n, self.k / self.n)
        context = self._context()
        if context is None:
            return uniform, []

        recent = self._recent()
        recent_signal = (recent.sum(axis=0) + 4.0 * uniform) / (len(recent) + 4.0)
        recent_weight = 0.35 * min(len(recent) / self.short_window, 1.0)
        scored = []
        context_norm = np.linalg.norm(context)
        for rule in self._rules:
            similarity = float(np.dot(context, rule.context) / (context_norm * np.linalg.norm(rule.context)))
            similarity = min(max(similarity, 0.0), 1.0)
            if similarity >= 0.9:
                scored.append((similarity, rule))
        scored.sort(key=lambda item: (item[0], item[1].cycle), reverse=True)
        scored = scored[:8]

        matches = []
        long_signal = uniform
        long_weight = 0.0
        if scored:
            weighted_counts = np.zeros(self.n)
            weighted_support = 0.0
            for similarity, rule in scored:
                weight = similarity ** 8
                weighted_counts += weight * rule.outcome_counts
                weighted_support += weight * rule.support
                matches.append({
                    "similarity": similarity,
                    "support": rule.support,
                    "first_cycle": rule.first_cycle,
                    "cycle": rule.cycle,
                    "context_cutoff": rule.cycle - 1,
                })
            long_signal = weighted_counts / weighted_support
            long_weight = 0.25 * weighted_support / (weighted_support + 8.0)
        probabilities = (
            (1.0 - recent_weight - long_weight) * uniform
            + recent_weight * recent_signal
            + long_weight * long_signal
        )
        # Each constituent is a valid marginal vector; this removes roundoff in
        # their total without turning marginal values into categorical masses.
        probabilities *= self.k / probabilities.sum()
        return probabilities, matches

    def state_dict(self) -> dict:
        'Xuất bản checkpoint JSON hữu hạn, không chia sẻ vùng nhớ nội bộ.'
        return {
            "version": 1,
            "n": self.n,
            "k": self.k,
            "short_window": self.short_window,
            "max_history": self.max_history,
            "max_rules": self.max_rules,
            "total_observations": self._total_observations,
            "history": self.history.tolist(),
            "rules": [rule.state_dict() for rule in self._rules],
        }

    def load_state_dict(self, state: dict) -> None:
        'Xác thực toàn bộ checkpoint rồi thay trạng thái nguyên tử.'
        if not isinstance(state, dict):
            raise TypeError("memory state must be a dictionary")
        try:
            version = _integer(state["version"], "version", 1)
            n = _integer(state["n"], "n", 1)
            k = _integer(state["k"], "k", 1)
            if version != 1 or (n, k) != (self.n, self.k):
                raise ValueError("incompatible memory checkpoint")
            short_window = _integer(state["short_window"], "short_window", 1)
            max_history = _integer(state["max_history"], "max_history", short_window)
            max_rules = _integer(state["max_rules"], "max_rules", 1)
            total = _integer(state["total_observations"], "total_observations")
            rows = state["history"]
            if not isinstance(rows, list) or len(rows) != min(total, max_history):
                raise ValueError("history length is inconsistent with the observation count")
            history = []
            for row in rows:
                if not isinstance(row, list) or len(row) != n:
                    raise ValueError("history must be a matrix with n columns")
                values = [_integer(value, "history value") for value in row]
                if any(value > 1 for value in values) or sum(values) != k:
                    raise ValueError("history rows must be binary outcomes of cardinality k")
                history.append(np.array(values, dtype=np.uint8))
            rules = self._load_rules(state["rules"], total, max_rules)
        except KeyError as error:
            raise ValueError(f"memory checkpoint is missing {error.args[0]}") from error

        self.short_window = short_window
        self.max_history = max_history
        self.max_rules = max_rules
        self._history = deque(history, maxlen=max_history)
        self._rules = rules
        self._total_observations = total

    def _load_rules(self, saved: list, total: int, max_rules: int) -> list[_Association]:
        if not isinstance(saved, list) or len(saved) > max_rules:
            raise ValueError("invalid number of context associations")
        rules = []
        previous_cycle = 0
        total_support = 0
        contexts = set()
        for item in saved:
            if not isinstance(item, dict):
                raise ValueError("each context association must be a dictionary")
            support = _integer(item["support"], "support", 1)
            first_cycle = _integer(item["first_cycle"], "first_cycle", 1)
            cycle = _integer(item["cycle"], "cycle", first_cycle)
            cutoff = _integer(item["context_cutoff"], "context_cutoff")
            if cycle >= total or cycle <= previous_cycle or cutoff != cycle - 1:
                raise ValueError("context associations must have causal, ordered observation cycles")
            if support > cycle - first_cycle + 1:
                raise ValueError("context support exceeds available observed successors")
            raw_context = item["context"]
            if not isinstance(raw_context, list) or len(raw_context) != 2 * self.n:
                raise ValueError("context vector must contain 2*n numeric values")
            if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float)) for value in raw_context):
                raise TypeError("context values must be numeric")
            context = np.asarray(raw_context, dtype=float)
            if not np.all(np.isfinite(context)) or np.any(context < 0) or np.any(context > 1):
                raise ValueError("context values must be finite marginals")
            if not np.isclose(context[:self.n].sum(), self.k) or not np.isclose(context[self.n:].sum(), self.k):
                raise ValueError("context vectors must have cardinality k")
            if np.any((context[self.n:] != 0) & (context[self.n:] != 1)):
                raise ValueError("the last outcome in a context must be binary")
            key = tuple(raw_context)
            if key in contexts:
                raise ValueError("duplicate context associations")
            contexts.add(key)
            raw_counts = item["outcome_counts"]
            if not isinstance(raw_counts, list) or len(raw_counts) != self.n:
                raise ValueError("outcome counts must contain n integers")
            counts = [_integer(value, "outcome count") for value in raw_counts]
            if any(value > support for value in counts) or sum(counts) != support * self.k:
                raise ValueError("outcome counts are inconsistent with observed support")
            rules.append(_Association(context, np.array(counts, dtype=np.int64), support, first_cycle, cycle))
            previous_cycle = cycle
            total_support += support
        if total_support > max(total - 1, 0):
            raise ValueError("context support exceeds the number of observed successors")
        return rules
