from __future__ import annotations

import logging
from collections import deque
from enum import Enum
from typing import Final

import numpy as np

from research.ml_engine.schema import BASELINE_RATE
from ml.ml_train import model_trust

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

DEFAULT_WINDOW: Final[int] = 60

DEFAULT_MIN_DAYS: Final[int] = 30


class Mode(str, Enum):

    NORMAL = "normal"
    SAFE = "safe"


class SafeModeController:

    def __init__(self, *, window: int = DEFAULT_WINDOW, min_days: int = DEFAULT_MIN_DAYS) -> None:
        if window < 1:
            raise ValueError("window phải dương")
        if not 1 <= min_days <= window:
            raise ValueError("min_days phải nằm trong [1, window]")
        self.window = window
        self.min_days = min_days
        self.trust = 0.0
        self.mode = Mode.SAFE
        self.reason = f"chưa có kỳ nào đo kỹ năng (cần {min_days})"
        self.skill: dict[str, float] | None = None
        self.transitions: list[dict[str, object]] = []
        self._evidence: deque[tuple[float, float, float, float]] = deque(maxlen=window)

    @property
    def is_safe(self) -> bool:
        return self.mode is Mode.SAFE

    def _set(self, trust: float, reason: str, day_index: int | None) -> None:
        mode = Mode.SAFE if trust <= 0.0 else Mode.NORMAL
        if mode is not self.mode:
            log = LOGGER.warning if mode is Mode.SAFE else LOGGER.info
            log("Độ tin → %s: %s", mode.value, reason)
            self.transitions.append({"to": mode.value, "reason": reason, "day": day_index})
        self.trust = float(trust)
        self.mode = mode
        self.reason = reason

    def observe(
        self,
        *,
        logloss: float,
        brier: float,
        baseline_logloss: float,
        baseline_brier: float,
        drifted: bool = False,
        model_failed: bool = False,
        day_index: int | None = None,
    ) -> Mode:
        scores = (logloss, brier, baseline_logloss, baseline_brier)
        if not all(np.isfinite(value) and value >= 0.0 for value in scores):
            raise ValueError("điểm phải hữu hạn và không âm")
        if baseline_logloss <= 0.0 or baseline_brier <= 0.0:
            raise ValueError("điểm của nền phải dương")

        if model_failed:
            self._evidence.clear()
            self.skill = None
            self._set(0.0, "mô hình lỗi khi khớp hoặc dự đoán; đo kỹ năng lại từ đầu", day_index)
            return self.mode
        if drifted:
            self._evidence.clear()
            self.skill = None
            self._set(0.0, "bộ phát hiện báo trôi lệch khái niệm; đo kỹ năng lại từ đầu", day_index)
            return self.mode

        self._evidence.append(tuple(float(value) for value in scores))
        if len(self._evidence) < self.min_days:
            self._set(0.0, f"mới đo {len(self._evidence)}/{self.min_days} kỳ kỹ năng", day_index)
            return self.mode

        loss, score, base_loss, base_score = np.mean(np.asarray(self._evidence), axis=0)
        self.skill = {
            "logloss": float((base_loss - loss) / base_loss),
            "brier": float((base_score - score) / base_score),
            "days": len(self._evidence),
        }
        trust = model_trust(self.skill["logloss"], self.skill["brier"])
        self._set(
            trust,
            f"kỹ năng {len(self._evidence)} kỳ: log-loss {self.skill['logloss']:+.5f}, "
            f"Brier {self.skill['brier']:+.5f} → độ tin {trust:.3f}",
            day_index,
        )
        return self.mode

    def apply(self, model_probabilities: np.ndarray) -> np.ndarray:
        model = np.asarray(model_probabilities, dtype=float)
        return self.trust * model + (1.0 - self.trust) * BASELINE_RATE

    def state(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "trust": self.trust,
            "reason": self.reason,
            "window": self.window,
            "min_days": self.min_days,
            "skill": self.skill,
            "observations": len(self._evidence),
            "transitions": list(self.transitions),
        }
