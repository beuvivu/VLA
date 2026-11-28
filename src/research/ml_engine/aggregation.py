from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Final

import numpy as np

DEFAULT_LEARNING_RATE: Final[float] = 1.0

DEFAULT_SHARE: Final[float] = 0.001


class AggregationError(ValueError):
    pass


class ExponentialWeights:

    def __init__(
        self,
        arm_names: Iterable[str],
        *,
        learning_rate: float = DEFAULT_LEARNING_RATE,
        share: float = DEFAULT_SHARE,
    ) -> None:
        names = tuple(arm_names)
        if not names:
            raise AggregationError("cần ít nhất một cánh tay")
        if len(set(names)) != len(names):
            raise AggregationError("tên cánh tay bị trùng")
        if not np.isfinite(learning_rate) or learning_rate <= 0.0:
            raise AggregationError("learning_rate phải hữu hạn và dương")
        if not np.isfinite(share) or not 0.0 <= share < 1.0:
            raise AggregationError("share phải nằm trong [0, 1)")
        self.arm_names = names
        self.learning_rate = float(learning_rate)
        self.share = float(share)
        self.updates = 0
        self._log_weights = np.full(len(names), -np.log(len(names)))
        self._cumulative_loss = np.zeros(len(names))

    def _normalised(self) -> np.ndarray:
        weights = np.exp(self._log_weights - self._log_weights.max())
        return weights / weights.sum()

    def weights(self) -> dict[str, float]:
        return {name: float(w) for name, w in zip(self.arm_names, self._normalised(), strict=True)}

    def update(self, losses: Mapping[str, float]) -> None:
        unknown = set(losses) - set(self.arm_names)
        if unknown:
            raise AggregationError(f"cánh tay không tồn tại: {sorted(unknown)}")
        if not losses:
            raise AggregationError("không có loss nào để học")
        given = np.array(list(losses.values()), dtype=float)
        if not np.all(np.isfinite(given)) or np.any(given < 0.0):
            raise AggregationError("loss phải hữu hạn và không âm")
        present = np.array([name in losses for name in self.arm_names])
        values = np.array([losses.get(name, 0.0) for name in self.arm_names], dtype=float)

        log_weights = self._log_weights.copy()
        before = np.logaddexp.reduce(log_weights[present])
        log_weights[present] -= self.learning_rate * values[present]
        log_weights[present] += before - np.logaddexp.reduce(log_weights[present])
        if self.share > 0.0:
            mixed = (1.0 - self.share) * np.exp(log_weights) + self.share / len(log_weights)
            log_weights = np.log(mixed)

        self._log_weights = log_weights
        self._cumulative_loss = self._cumulative_loss + np.where(present, values, 0.0)
        self.updates += 1

    def report(self) -> list[dict[str, float | str]]:
        rows = [
            {"arm": name, "weight": float(w), "cumulative_logloss": float(loss)}
            for name, w, loss in zip(
                self.arm_names, self._normalised(), self._cumulative_loss, strict=True
            )
        ]
        return sorted(rows, key=lambda row: -row["weight"])
