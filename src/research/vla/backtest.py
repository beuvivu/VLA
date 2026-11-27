from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

import numpy as np

from core.xsmb_domain import LOTO_DRAWS_PER_DAY


Mode = Literal["loto", "de"]
EPS = 1e-6


@dataclass(frozen=True)
class Payout:
    lo_cost: float = 23.0
    lo_win_per_hit: float = 80.0
    de_cost: float = 1.0
    de_win: float = 70.0


def cumulative_reference(mode: Mode, hit: np.ndarray, targets: np.ndarray) -> np.ndarray:
    targets = np.asarray(targets, dtype=np.int64)
    if mode == "de":
        return np.full((len(targets), 100), 0.01)
    rate = np.cumsum(hit.mean(axis=1))[targets - 1] / targets
    return np.repeat(rate[:, None], 100, axis=1)


def daily_logloss(mode: Mode, p: np.ndarray, hits: np.ndarray) -> np.ndarray:
    if mode == "de":
        q = np.clip(p / p.sum(axis=1, keepdims=True), EPS, 1.0)
        return -np.log((q * hits).sum(axis=1))
    q = np.clip(p, EPS, 1 - EPS)
    return -(hits * np.log(q) + (1 - hits) * np.log(1 - q)).mean(axis=1)


def daily_brier(mode: Mode, p: np.ndarray, hits: np.ndarray) -> np.ndarray:
    if mode == "de":
        q = p / p.sum(axis=1, keepdims=True)
        return ((q - hits) ** 2).sum(axis=1)
    return ((p - hits) ** 2).mean(axis=1)


def top_k(p: np.ndarray, k: int) -> np.ndarray:
    order = np.lexsort((np.broadcast_to(np.arange(p.shape[1]), p.shape), -p), axis=1)
    return order[:, :k]


def expected_hits_per_number(p: np.ndarray) -> np.ndarray:
    q = 1.0 - np.power(np.clip(1.0 - p, EPS, 1.0), 1.0 / LOTO_DRAWS_PER_DAY)
    return LOTO_DRAWS_PER_DAY * q


def roi_top_k(mode: Mode, p: np.ndarray, counts: np.ndarray, special: np.ndarray, k: int, pay: Payout) -> dict:
    chosen = top_k(p, k)
    rows = np.arange(len(p))[:, None]
    if mode == "loto":
        cost = k * pay.lo_cost * len(p)
        win = pay.lo_win_per_hit * counts[rows, chosen].sum()
    else:
        cost = k * pay.de_cost * len(p)
        win = pay.de_win * (chosen == special[:, None]).sum()
    return {"stake": float(cost), "return": float(win), "roi": float(win / cost - 1.0) if cost else 0.0}


def roi_positive_ev(mode: Mode, p: np.ndarray, counts: np.ndarray, special: np.ndarray, pay: Payout) -> dict:
    if mode == "loto":
        ev = pay.lo_win_per_hit * expected_hits_per_number(p) - pay.lo_cost
        bet = ev > 0
        cost = pay.lo_cost * bet.sum()
        win = pay.lo_win_per_hit * (counts * bet).sum()
    else:
        q = p / p.sum(axis=1, keepdims=True)
        bet = pay.de_win * q - pay.de_cost > 0
        cost = pay.de_cost * bet.sum()
        win = pay.de_win * bet[np.arange(len(p)), special].sum()
    return {
        "bets": int(bet.sum()),
        "days_with_bets": int(bet.any(axis=1).sum()),
        "stake": float(cost),
        "return": float(win),
        "roi": float(win / cost - 1.0) if cost else None,
    }


def calibration_table(mode: Mode, p: np.ndarray, hits: np.ndarray, bins: int = 10) -> list[dict]:
    q = p / p.sum(axis=1, keepdims=True) if mode == "de" else p
    flat, y = q.reshape(-1), hits.reshape(-1)
    edges = np.quantile(flat, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, flat, side="right") - 1, 0, bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        if m.any():
            out.append({"bin": b, "count": int(m.sum()), "predicted": float(flat[m].mean()), "observed": float(y[m].mean())})
    return out


def paired(model: np.ndarray, reference: np.ndarray) -> dict:
    d = np.asarray(reference) - np.asarray(model)
    se = float(d.std(ddof=1) / np.sqrt(len(d))) if len(d) > 1 else float("nan")
    return {"mean_gain": float(d.mean()), "se": se, "z": float(d.mean() / se) if se and se > 0 else 0.0}


def evaluate(
    mode: Mode,
    p: np.ndarray,
    counts: np.ndarray,
    special: np.ndarray,
    reference: np.ndarray,
    *,
    ks: tuple[int, ...] = (5, 10, 20),
    pay: Payout | None = None,
) -> dict:
    pay = pay or Payout()
    if mode == "loto":
        hits = (counts > 0).astype(np.float64)
    else:
        hits = np.zeros(p.shape)
        hits[np.arange(len(p)), special] = 1.0
    ll = daily_logloss(mode, p, hits)
    ll_ref = daily_logloss(mode, reference, hits)
    br = daily_brier(mode, p, hits)
    br_ref = daily_brier(mode, reference, hits)
    out: dict = {
        "days": int(len(p)),
        "logloss": float(ll.mean()),
        "logloss_reference": float(ll_ref.mean()),
        "logloss_skill": float(1.0 - ll.mean() / ll_ref.mean()),
        "brier": float(br.mean()),
        "brier_reference": float(br_ref.mean()),
        "brier_skill": float(1.0 - br.mean() / br_ref.mean()),
        "vs_reference": paired(ll, ll_ref),
        "calibration": calibration_table(mode, p, hits),
        "top_k": {},
        "roi_top_k": {},
        "roi_positive_ev": roi_positive_ev(mode, p, counts, special, pay),
    }
    rows = np.arange(len(p))[:, None]
    for k in ks:
        chosen = top_k(p, k)
        got = hits[rows, chosen]
        if mode == "loto":
            base = float(hits.mean())
            out["top_k"][str(k)] = {
                "hits_per_day": float(got.sum(axis=1).mean()),
                "hit_rate": float(got.mean()),
                "random_hit_rate": base,
                "any_hit": float((got.sum(axis=1) > 0).mean()),
            }
        else:
            out["top_k"][str(k)] = {"hit_rate": float(got.sum(axis=1).mean()), "random_hit_rate": k / 100.0}
        out["roi_top_k"][str(k)] = roi_top_k(mode, p, counts, special, k, pay)
    return out


class Model(Protocol):
    def fit(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> Model: ...

    def predict(self, X: np.ndarray, hit: np.ndarray, rows: np.ndarray) -> np.ndarray: ...


@dataclass
class WalkForwardResult:
    targets: np.ndarray
    probs: np.ndarray
    refits: list[dict] = field(default_factory=list)


def run(
    factory: Callable[[], Model],
    X: np.ndarray,
    hit: np.ndarray,
    first_target: int,
    last_target: int,
    *,
    refit_every: int = 50,
    max_train_rows: int | None = None,
    on_refit: Callable[[dict], None] | None = None,
) -> WalkForwardResult:
    if first_target < 2 or last_target >= len(hit) or first_target > last_target:
        raise ValueError("khoảng kỳ đích không hợp lệ")
    targets = np.arange(first_target, last_target + 1)
    probs = np.zeros((len(targets), 100))
    refits: list[dict] = []
    for start in range(first_target, last_target + 1, refit_every):
        stop = min(start + refit_every, last_target + 1)
        train_rows = np.arange(0, start - 1)
        if max_train_rows is not None:
            train_rows = train_rows[-max_train_rows:]
        if train_rows.size and train_rows.max() + 1 >= start:
            raise AssertionError("huấn luyện chạm vào kỳ đang chấm")
        model = factory().fit(X, hit, train_rows)
        pred_rows = np.arange(start - 1, stop - 1)
        probs[start - first_target : stop - first_target] = model.predict(X, hit, pred_rows)
        info = {"first_target": int(start), "last_target": int(stop - 1), "train_rows": int(train_rows.size),
                "last_label": int(train_rows.max() + 1) if train_rows.size else -1}
        for key in ("rounds",):
            if hasattr(model, key):
                info[key] = getattr(model, key)
        prior = getattr(model, "prior", None)
        if prior is not None:
            info["prior_half_life"] = float(prior.half_life)
            info["prior_alpha"] = float(prior.alpha)
        refits.append(info)
        if on_refit:
            on_refit(info)
    return WalkForwardResult(targets, probs, refits)
