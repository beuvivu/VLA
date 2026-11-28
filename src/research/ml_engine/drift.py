from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Final, Literal

import numpy as np
from scipy import stats

from research.ml_engine.capabilities import CAPABILITIES

LOGGER: Final[logging.Logger] = logging.getLogger(__name__)

DriftMethod = Literal["adwin", "ks", "both"]


@dataclass(frozen=True)
class DriftVerdict:

    drifted: bool
    method: str
    statistic: float
    p_value: float | None
    window_size: int
    detail: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        if not self.drifted:
            return f"không trôi lệch (cửa sổ {self.window_size})"
        p_text = "" if self.p_value is None else f", p={self.p_value:.4g}"
        return f"TRÔI LỆCH qua {self.method} (thống kê={self.statistic:.4g}{p_text})"


class _PureAdwin:

    def __init__(self, delta: float = 0.002, max_window: int = 512) -> None:
        if not 0.0 < delta < 1.0:
            raise ValueError("delta phải nằm trong (0, 1)")
        self.delta = float(delta)
        self.window: deque[float] = deque(maxlen=int(max_window))
        self.drift_detected = False
        self.last_difference = 0.0

    @staticmethod
    def _candidate_cuts(n: int) -> np.ndarray:
        offsets = 2 ** np.arange(int(np.log2(max(n - 1, 1))) + 1)
        cuts = np.unique(np.concatenate([offsets, n - offsets, [n // 2]]))
        return cuts[(cuts >= 1) & (cuts < n)]

    def _bound(self, n0: int, n1: int, variance: float, *, n_cuts: int) -> float:
        m = 1.0 / (1.0 / max(n0, 1) + 1.0 / max(n1, 1))
        delta_prime = self.delta / max(n_cuts, 1)
        log_term = np.log(2.0 / delta_prime)
        return float(np.sqrt(2.0 / m * variance * log_term) + 2.0 / (3.0 * m) * log_term)

    def update(self, value: float) -> bool:
        self.window.append(float(value))
        self.drift_detected = False
        n = len(self.window)
        if n < 16:
            return False

        values = np.fromiter(self.window, dtype=float, count=n)
        variance = float(values.var())
        prefix = np.cumsum(values)
        total = prefix[-1]

        cuts = self._candidate_cuts(n)
        left_n, right_n = cuts, n - cuts
        left_mean = prefix[cuts - 1] / left_n
        right_mean = (total - prefix[cuts - 1]) / right_n
        differences = np.abs(left_mean - right_mean)
        bounds = np.array(
            [
                self._bound(int(a), int(b), variance, n_cuts=cuts.size)
                for a, b in zip(left_n, right_n, strict=True)
            ]
        )

        exceeded = np.flatnonzero(differences > bounds)
        if exceeded.size == 0:
            self.last_difference = float(differences.max()) if differences.size else 0.0
            return False

        cut = int(cuts[exceeded[np.argmax(differences[exceeded])]])
        self.last_difference = float(differences[exceeded].max())
        for _ in range(cut):
            self.window.popleft()
        self.drift_detected = True
        return True


class ConceptDriftDetector:

    def __init__(
        self,
        *,
        method: DriftMethod = "both",
        delta: float = 0.002,
        ks_alpha: float = 0.01,
        reference_size: int = 90,
        recent_size: int = 30,
        prefer_river: bool = True,
    ) -> None:
        if method not in ("adwin", "ks", "both"):
            raise ValueError(f"method không hỗ trợ: {method}")
        if recent_size < 8 or reference_size < 8:
            raise ValueError("cửa sổ tham chiếu và cửa sổ gần đây phải có ít nhất 8 quan sát")
        if not 0.0 < ks_alpha < 1.0:
            raise ValueError("ks_alpha phải nằm trong (0, 1)")

        self.method = method
        self.delta = delta
        self.ks_alpha = ks_alpha
        self.reference_size = int(reference_size)
        self.recent_size = int(recent_size)

        river = CAPABILITIES.river if prefer_river else None
        if river is not None:
            try:
                self._adwin: Any = river.drift.ADWIN(delta=delta)
                self.backend = "river"
            except Exception as error:
                LOGGER.warning("Không dùng được ADWIN của river (%s); dùng bản tự cài", error)
                self._adwin = _PureAdwin(delta=delta)
                self.backend = "pure"
        else:
            self._adwin = _PureAdwin(delta=delta)
            self.backend = "pure"

        self._history: deque[float] = deque(maxlen=self.reference_size + self.recent_size)
        self.drift_count = 0


    def _adwin_update(self, value: float) -> tuple[bool, float, int]:
        if self.backend == "river":
            self._adwin.update(value)
            return (
                bool(self._adwin.drift_detected),
                float(getattr(self._adwin, "estimation", 0.0)),
                int(getattr(self._adwin, "width", 0)),
            )
        drifted = self._adwin.update(value)
        return drifted, self._adwin.last_difference, len(self._adwin.window)

    def _ks_check(self) -> tuple[bool, float, float | None]:
        if len(self._history) < self.reference_size + self.recent_size:
            return False, 0.0, None
        values = np.fromiter(self._history, dtype=float, count=len(self._history))
        reference, recent = values[: -self.recent_size], values[-self.recent_size :]
        if np.allclose(reference, reference[0]) and np.allclose(recent, recent[0]):
            return not np.isclose(reference[0], recent[0]), 0.0, None
        result = stats.ks_2samp(reference, recent)
        return bool(result.pvalue < self.ks_alpha), float(result.statistic), float(result.pvalue)


    def update(self, error_value: float) -> DriftVerdict:
        value = float(error_value)
        if not np.isfinite(value):
            raise ValueError(f"error_value phải hữu hạn, nhận {error_value!r}")
        self._history.append(value)

        adwin_drift, adwin_statistic, width = False, 0.0, len(self._history)
        if self.method in ("adwin", "both"):
            adwin_drift, adwin_statistic, width = self._adwin_update(value)

        ks_drift, ks_statistic, ks_p = False, 0.0, None
        if self.method in ("ks", "both"):
            ks_drift, ks_statistic, ks_p = self._ks_check()

        if adwin_drift:
            self.drift_count += 1
            return DriftVerdict(
                drifted=True,
                method=f"adwin/{self.backend}",
                statistic=adwin_statistic,
                p_value=None,
                window_size=width,
                detail={"ks_statistic": ks_statistic, "ks_p_value": ks_p},
            )
        if ks_drift:
            self.drift_count += 1
            return DriftVerdict(
                drifted=True,
                method="ks",
                statistic=ks_statistic,
                p_value=ks_p,
                window_size=width,
                detail={"reference": self.reference_size, "recent": self.recent_size},
            )
        return DriftVerdict(
            drifted=False,
            method="none",
            statistic=ks_statistic,
            p_value=ks_p,
            window_size=width,
        )

    def update_many(self, values: list[float] | np.ndarray) -> list[DriftVerdict]:
        return [self.update(float(value)) for value in np.asarray(values, dtype=float)]

    def reset(self) -> None:
        if self.backend == "river" and CAPABILITIES.river is not None:
            self._adwin = CAPABILITIES.river.drift.ADWIN(delta=self.delta)
        else:
            self._adwin = _PureAdwin(delta=self.delta)
        self._history.clear()
