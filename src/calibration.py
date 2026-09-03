from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Literal, Tuple

import numpy as np

from ensemble_utils import clip01, logit, sigmoid, normalize_distribution, softmax_from_logp


Mode = Literal["loto", "de"]


@dataclass(frozen=True)
class CalibParams:
    mode: Mode
    # loto: sigmoid(a*logit(p)+b)
    a: float = 1.0
    b: float = 0.0
    # de: temperature scaling on log probs
    temperature: float = 1.0

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool) or not isinstance(value, Real)
            for value in (self.a, self.b, self.temperature)
        ):
            raise ValueError("calibration parameters must be real numbers")
        values = np.array([self.a, self.b, self.temperature], dtype=float)
        if self.mode not in {"loto", "de"}:
            raise ValueError("calibration mode must be 'loto' or 'de'")
        if not np.isfinite(values).all():
            raise ValueError("calibration parameters must be finite")
        if self.temperature <= 0.0:
            raise ValueError("calibration temperature must be > 0")

    def as_dict(self) -> dict:
        return {"mode": self.mode, "a": float(self.a), "b": float(self.b), "temperature": float(self.temperature)}


def apply_calibration(mode: Mode, p: np.ndarray, params: CalibParams) -> np.ndarray:
    if params.mode != mode:
        raise ValueError("calibration mode does not match prediction mode")
    values = np.asarray(p, dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("probabilities to calibrate must be finite")
    if bool(((values < 0.0) | (values > 1.0)).any()):
        raise ValueError("probabilities to calibrate must be inside [0, 1]")
    if mode == "de":
        # temperature scaling
        t = float(max(1e-6, params.temperature))
        logp = np.log(clip01(values, eps=1e-12)) / t
        return normalize_distribution(softmax_from_logp(logp))
    # loto
    x = logit(clip01(values, eps=1e-6))
    z = params.a * x + params.b
    return clip01(sigmoid(z), eps=1e-6)


def learn_calibration(
    mode: Mode,
    probs_by_day: np.ndarray,  # shape (D,100)
    y_by_day: np.ndarray,      # shape (D,100) (Bernoulli for loto) OR one-hot for de
    sample_weight_by_day: np.ndarray | None = None,  # shape (D,)
) -> CalibParams:
    """Learn calibration parameters on recent window.

    - de: optimize temperature T to minimize mean categorical logloss.
    - loto: optimize (a,b) to minimize mean Bernoulli logloss across all numbers.
    """
    try:
        from scipy.optimize import minimize
    except Exception:  # pragma: no cover
        minimize = None

    D = probs_by_day.shape[0]
    w_day = sample_weight_by_day if sample_weight_by_day is not None else np.ones(D, dtype=float)

    if mode == "de":
        # y_by_day expected one-hot (exactly one 1 per day)
        y_idx = np.argmax(y_by_day, axis=1).astype(int)

        def loss_T(x: np.ndarray) -> float:
            T = float(x[0])
            T = float(np.clip(T, 0.3, 5.0))
            ll = 0.0
            tot = 0.0
            for i in range(D):
                p = clip01(probs_by_day[i], eps=1e-12)
                logp = np.log(p) / T
                pT = normalize_distribution(softmax_from_logp(logp))
                ll_i = -np.log(clip01(pT[y_idx[i]], eps=1e-12))
                ll += w_day[i] * ll_i
                tot += w_day[i]
            return float(ll / max(1e-12, tot))

        if minimize is None:
            # fallback coarse scan
            Ts = np.linspace(0.5, 3.0, 26)
            bestT, bestL = 1.0, float("inf")
            for T in Ts:
                L = loss_T(np.array([T]))
                if L < bestL:
                    bestL, bestT = L, float(T)
            return CalibParams(mode="de", temperature=bestT)

        res = minimize(loss_T, x0=np.array([1.0]), bounds=[(0.3, 5.0)], method="L-BFGS-B")
        T = float(res.x[0]) if res.success else 1.0
        T = float(np.clip(T, 0.3, 5.0))
        return CalibParams(mode="de", temperature=T)

    # loto
    # flatten across day and number (D*100)
    P = clip01(probs_by_day, eps=1e-6).reshape(-1)
    Y = y_by_day.reshape(-1).astype(float)

    # weight each day equally but allow decay via w_day
    W = np.repeat(w_day, 100)

    def loss_ab(x: np.ndarray) -> float:
        a = float(np.clip(x[0], 0.1, 5.0))
        b = float(np.clip(x[1], -5.0, 5.0))
        z = a * logit(P) + b
        p2 = clip01(sigmoid(z), eps=1e-6)
        ll = -(Y * np.log(p2) + (1.0 - Y) * np.log(1.0 - p2))
        return float(np.sum(W * ll) / max(1e-12, np.sum(W)))

    if minimize is None:
        # fallback: keep identity
        return CalibParams(mode="loto", a=1.0, b=0.0)

    res = minimize(
        loss_ab,
        x0=np.array([1.0, 0.0]),
        bounds=[(0.1, 5.0), (-5.0, 5.0)],
        method="L-BFGS-B",
    )
    if not res.success:
        return CalibParams(mode="loto", a=1.0, b=0.0)
    a, b = float(res.x[0]), float(res.x[1])
    return CalibParams(mode="loto", a=a, b=b)
