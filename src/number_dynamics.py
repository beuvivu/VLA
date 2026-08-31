from __future__ import annotations

"""Leakage-safe higher-order numerical dynamics for the 00..99 universe.

The module estimates descriptive/forecast-support signals using only observations
available through the anchor draw:
- hierarchical Bayesian first-order cross-number transition matrices;
- second-order per-number Markov state posteriors;
- empirical-Bayes renewal/hazard probabilities by current gap;
- multi-lag conditional kernels (1, 2, 3, 7, 14, 28 days);
- recent-vs-long regime drift with Jensen-Shannon diagnostics;
- same-draw co-occurrence phi matrices for structural inspection.

The estimates are aggressively shrunk toward historical baselines. They are
probabilistic ranking evidence, not deterministic lottery rules.
"""

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from ensemble_utils import normalize_distribution
from lottery import Lottery

Mode = Literal["loto", "de"]
LAGS = (1, 2, 3, 7, 14, 28)


@dataclass(frozen=True)
class DynamicsArtifacts:
    current: pd.DataFrame
    transition_prob: pd.DataFrame
    transition_lift: pd.DataFrame
    cooccurrence_phi: pd.DataFrame
    lag_dependency: pd.DataFrame
    diagnostics: dict


def _clip_prob(p: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(p, dtype=float), 1e-6, 1.0 - 1e-6)


def _js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    p = normalize_distribution(np.clip(np.asarray(p, dtype=float), 1e-12, None))
    q = normalize_distribution(np.clip(np.asarray(q, dtype=float), 1e-12, None))
    m = 0.5 * (p + q)
    return float(
        0.5 * np.sum(p * np.log(p / m))
        + 0.5 * np.sum(q * np.log(q / m))
    )


def _baseline(hit: np.ndarray, prior_strength: float) -> np.ndarray:
    n = max(len(hit), 1)
    global_rate = float(np.mean(hit)) if hit.size else 0.01
    global_rate = float(np.clip(global_rate, 1e-5, 1 - 1e-5))
    hits = hit.sum(axis=0, dtype=np.float64)
    return (hits + prior_strength * global_rate) / (n + prior_strength)


def transition_posterior(
    hit: np.ndarray, *, prior_strength: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """P(target[t+1]=1 | source[t]=1), shrunk to target baselines."""
    h = np.asarray(hit, dtype=np.int8)
    if h.ndim != 2 or h.shape[1] != 100:
        raise ValueError("hit must have shape (n_days, 100)")
    base = _baseline(h, prior_strength=max(20.0, prior_strength * 0.5))
    if len(h) < 2:
        post = np.tile(base, (100, 1))
        return post, np.ones_like(post), np.zeros(100), base

    src = h[:-1].astype(np.float64)
    dst = h[1:].astype(np.float64)
    trials = src.sum(axis=0)
    pair = src.T @ dst
    post = (pair + prior_strength * base[None, :]) / (
        trials[:, None] + prior_strength
    )
    lift = post / np.maximum(base[None, :], 1e-9)
    return post, lift, trials, base


def _markov2_current(
    hit: np.ndarray, *, prior_strength: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-number P(hit_next | hit_{t-1}, hit_t) with hierarchical shrinkage."""
    h = np.asarray(hit, dtype=np.int8)
    base = _baseline(h, prior_strength=max(20.0, prior_strength * 0.5))
    if len(h) < 3:
        return base.copy(), np.zeros(100, dtype=np.int8), np.zeros(100)

    success = np.zeros((4, 100), dtype=np.float64)
    trials = np.zeros((4, 100), dtype=np.float64)
    cols = np.arange(100)
    for t in range(1, len(h) - 1):
        state = 2 * h[t - 1] + h[t]
        outcome = h[t + 1]
        trials[state, cols] += 1.0
        success[state, cols] += outcome

    state_now = (2 * h[-2] + h[-1]).astype(np.int8)
    s = success[state_now, cols]
    n = trials[state_now, cols]
    prob = (s + prior_strength * base) / (n + prior_strength)
    reliability = n / (n + prior_strength)
    return prob, state_now, reliability


def _gap_hazard_current(
    hit: np.ndarray, *, max_gap: int, prior_strength: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
    """Empirical-Bayes hazard by gap, shared across numbers for sample efficiency."""
    h = np.asarray(hit, dtype=np.int8)
    n_days, n_numbers = h.shape
    base = _baseline(h, prior_strength=max(20.0, prior_strength * 0.5))
    denom = np.zeros(max_gap + 1, dtype=np.float64)
    numer = np.zeros(max_gap + 1, dtype=np.float64)

    last_seen = np.full(n_numbers, -1, dtype=np.int32)
    for t in range(n_days):
        seen = last_seen >= 0
        gaps = np.where(seen, t - last_seen, max_gap)
        gaps = np.clip(gaps, 1, max_gap)
        np.add.at(denom, gaps, 1.0)
        hit_idx = np.where(h[t] > 0)[0]
        if hit_idx.size:
            np.add.at(numer, gaps[hit_idx], 1.0)
            last_seen[hit_idx] = t

    global_rate = float(np.clip(np.mean(h), 1e-6, 1 - 1e-6))
    hazard = (numer + prior_strength * global_rate) / (denom + prior_strength)

    current_gap = np.empty(n_numbers, dtype=np.int32)
    for j in range(n_numbers):
        idx = np.where(h[:, j] > 0)[0]
        current_gap[j] = 0 if idx.size and idx[-1] == n_days - 1 else (
            n_days - 1 - idx[-1] if idx.size else max_gap - 1
        )
    next_gap = np.clip(current_gap + 1, 1, max_gap)
    raw = hazard[next_gap]

    evidence = denom[next_gap]
    reliability = evidence / (evidence + 4.0 * prior_strength)
    prob = base + reliability * (raw - global_rate)

    table = pd.DataFrame(
        {
            "gap": np.arange(max_gap + 1, dtype=int),
            "trials": denom,
            "hits": numer,
            "posterior_hazard": hazard,
        }
    )
    return _clip_prob(prob), next_gap, reliability, table


def _lag_kernel_current(
    hit: np.ndarray, *, lags: tuple[int, ...], prior_strength: float
) -> tuple[np.ndarray, pd.DataFrame]:
    """Same-number multi-lag conditional kernels using only known lag states."""
    h = np.asarray(hit, dtype=np.int8)
    base = _baseline(h, prior_strength=max(20.0, prior_strength * 0.5))
    weighted = np.zeros(100, dtype=np.float64)
    weight_sum = np.zeros(100, dtype=np.float64)
    rows: list[dict[str, float | int]] = []

    for lag in lags:
        if len(h) <= lag:
            continue
        src = h[:-lag]
        dst = h[lag:]
        for state in (0, 1):
            mask = src == state
            trials = mask.sum(axis=0, dtype=np.float64)
            hits = (mask & (dst > 0)).sum(axis=0, dtype=np.float64)
            post = (hits + prior_strength * base) / (trials + prior_strength)
            current_state = h[-lag]
            active = current_state == state
            rel = trials / (trials + prior_strength)
            lag_weight = (1.0 / np.sqrt(float(lag))) * rel
            weighted[active] += post[active] * lag_weight[active]
            weight_sum[active] += lag_weight[active]

            for j in range(100):
                rows.append(
                    {
                        "number": j,
                        "lag": lag,
                        "state": state,
                        "trials": float(trials[j]),
                        "hits": float(hits[j]),
                        "posterior_prob": float(post[j]),
                        "lift_vs_baseline": float(post[j] / max(base[j], 1e-9)),
                    }
                )

    prob = np.where(
        weight_sum > 0,
        weighted / np.maximum(weight_sum, 1e-12),
        base,
    )
    return _clip_prob(prob), pd.DataFrame(rows)


def _regime_current(
    hit: np.ndarray, *, recent: int, long: int, prior_strength: float
) -> tuple[np.ndarray, np.ndarray, float, float, float]:
    h = np.asarray(hit, dtype=np.int8)
    base = _baseline(h, prior_strength=max(20.0, prior_strength))
    r = h[-min(recent, len(h)) :]
    l = h[-min(long, len(h)) :]
    r_hits = r.sum(axis=0, dtype=np.float64)
    l_hits = l.sum(axis=0, dtype=np.float64)
    recent_prob = (r_hits + prior_strength * base) / (len(r) + prior_strength)
    long_prob = (l_hits + prior_strength * base) / (len(l) + prior_strength)
    recent_dist = normalize_distribution(np.clip(r_hits + 0.5, 1e-12, None))
    long_dist = normalize_distribution(np.clip(l_hits + 0.5, 1e-12, None))
    js = _js_divergence(recent_dist, long_dist)
    entropy_recent = float(-np.sum(recent_dist * np.log(recent_dist)))
    entropy_long = float(-np.sum(long_dist * np.log(long_dist)))
    stability = float(np.exp(-8.0 * js))
    regime_prob = base + stability * (recent_prob - base)
    regime_log_ratio = np.log(
        np.maximum(recent_prob, 1e-9) / np.maximum(long_prob, 1e-9)
    )
    return _clip_prob(regime_prob), regime_log_ratio, js, entropy_recent, entropy_long


def _cooccurrence_phi(hit: np.ndarray, shrink_strength: float = 60.0) -> np.ndarray:
    h = np.asarray(hit, dtype=np.float64)
    if len(h) < 2:
        return np.zeros((100, 100), dtype=np.float64)
    p = h.mean(axis=0)
    joint = (h.T @ h) / float(len(h))
    cov = joint - p[:, None] * p[None, :]
    var = np.maximum(p * (1.0 - p), 1e-12)
    denom = np.sqrt(var[:, None] * var[None, :])
    phi = cov / np.maximum(denom, 1e-12)
    phi *= len(h) / (len(h) + shrink_strength)
    np.fill_diagonal(phi, 1.0)
    return np.clip(phi, -1.0, 1.0)


def build_dynamics_signal(
    hit: np.ndarray,
    *,
    mode: Mode,
    transition_prior: float | None = None,
) -> DynamicsArtifacts:
    h = np.asarray(hit, dtype=np.int8)
    if h.ndim != 2 or h.shape[1] != 100 or len(h) == 0:
        raise ValueError("hit must be a non-empty (n_days, 100) matrix")

    if transition_prior is None:
        transition_prior = 45.0 if mode == "loto" else 160.0
    markov_prior = 35.0 if mode == "loto" else 100.0
    hazard_prior = 60.0 if mode == "loto" else 180.0
    lag_prior = 45.0 if mode == "loto" else 120.0
    regime_prior = 35.0 if mode == "loto" else 100.0
    max_gap = 60 if mode == "loto" else 200

    trans, lift, trials, base = transition_posterior(
        h, prior_strength=transition_prior
    )
    active = np.where(h[-1] > 0)[0]
    if active.size:
        trans_raw = trans[active].mean(axis=0)
        active_trials = float(np.mean(trials[active]))
        trans_rel = active_trials / (active_trials + transition_prior)
    else:
        trans_raw = base.copy()
        trans_rel = 0.0
    trans_current = base + trans_rel * (trans_raw - base)

    markov2, markov_state, markov_rel = _markov2_current(
        h, prior_strength=markov_prior
    )
    hazard, next_gap, hazard_rel, hazard_table = _gap_hazard_current(
        h, max_gap=max_gap, prior_strength=hazard_prior
    )
    lag_prob, lag_table = _lag_kernel_current(
        h, lags=LAGS, prior_strength=lag_prior
    )
    regime, regime_log_ratio, js, ent_recent, ent_long = _regime_current(
        h, recent=30, long=180, prior_strength=regime_prior
    )

    components = [base, markov2, hazard, trans_current, lag_prob, regime]
    if mode == "de":
        components = [
            normalize_distribution(np.clip(x, 1e-12, None)) for x in components
        ]
    base_c, markov2_c, hazard_c, trans_c, lag_c, regime_c = components

    raw = (
        0.20 * base_c
        + 0.20 * markov2_c
        + 0.17 * hazard_c
        + 0.20 * trans_c
        + 0.13 * lag_c
        + 0.10 * regime_c
    )

    evidence_rel = min(1.0, len(h) / 365.0)
    stability = float(np.exp(-6.0 * js))
    global_rel = float(
        np.clip(0.15 + 0.65 * evidence_rel * stability, 0.15, 0.80)
    )
    signal = base_c + global_rel * (raw - base_c)
    if mode == "de":
        signal = normalize_distribution(np.clip(signal, 1e-12, None))
    else:
        signal = _clip_prob(signal)

    current = pd.DataFrame(
        {
            "number": np.arange(100, dtype=int),
            "number_str": [f"{x:02d}" for x in range(100)],
            "prob": signal,
            "baseline_prob": base_c,
            "markov2_prob": markov2_c,
            "markov2_state": markov_state,
            "markov2_reliability": markov_rel,
            "hazard_prob": hazard_c,
            "next_gap": next_gap,
            "hazard_reliability": hazard_rel,
            "transition_prob": trans_c,
            "lag_kernel_prob": lag_c,
            "regime_prob": regime_c,
            "regime_log_ratio": regime_log_ratio,
            "dynamics_reliability": global_rel,
        }
    ).sort_values("prob", ascending=False, ignore_index=True)

    columns = [f"{x:02d}" for x in range(100)]
    trans_df = pd.DataFrame(trans, columns=columns)
    trans_df.insert(0, "source", columns)
    lift_df = pd.DataFrame(lift, columns=columns)
    lift_df.insert(0, "source", columns)
    phi_df = pd.DataFrame(_cooccurrence_phi(h), columns=columns)
    phi_df.insert(0, "source", columns)

    diagnostics = {
        "schema_version": 1,
        "mode": mode,
        "history_days": int(len(h)),
        "active_numbers_last_draw": int(active.size),
        "transition_prior_strength": float(transition_prior),
        "transition_active_mean_trials": float(
            np.mean(trials[active]) if active.size else 0.0
        ),
        "regime_js_divergence_30_vs_180": js,
        "entropy_recent": ent_recent,
        "entropy_long": ent_long,
        "global_dynamics_reliability": global_rel,
        "hazard_nonzero_bins": int((hazard_table["trials"] > 0).sum()),
        "generated_at_utc": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "interpretation": (
            "Higher-order Bayesian dynamics are shrinkage-regularized statistical "
            "evidence. They do not imply deterministic numerical laws."
        ),
    }

    return DynamicsArtifacts(
        current=current,
        transition_prob=trans_df,
        transition_lift=lift_df,
        cooccurrence_phi=phi_df,
        lag_dependency=lag_table,
        diagnostics=diagnostics,
    )


def build_hit_matrix_from_lottery(mode: Mode) -> tuple[pd.DatetimeIndex, np.ndarray]:
    lot = Lottery()
    lot.load()
    two = lot.get_2_digits_data().copy()
    sparse = lot.get_sparse_data().copy()
    if two.empty or sparse.empty:
        raise RuntimeError("No lottery data loaded")
    two["date"] = pd.to_datetime(two["date"])
    sparse["date"] = pd.to_datetime(sparse["date"])
    if mode == "loto":
        hit = (sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0).astype(
            np.int8
        )
        return pd.DatetimeIndex(sparse["date"]), hit

    de = (two["special"].astype(int).to_numpy() % 100).astype(int)
    onehot = np.zeros((len(de), 100), dtype=np.int8)
    onehot[np.arange(len(de)), de] = 1
    return pd.DatetimeIndex(two["date"]), onehot


def export_dynamics(mode: Mode, out_dir: Path) -> DynamicsArtifacts:
    dates, hit = build_hit_matrix_from_lottery(mode)
    artifacts = build_dynamics_signal(hit, mode=mode)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts.current.to_csv(out_dir / f"current_dynamics_{mode}.csv", index=False)
    artifacts.transition_prob.to_csv(
        out_dir / f"transition_prob_lag1_{mode}.csv", index=False
    )
    artifacts.transition_lift.to_csv(
        out_dir / f"transition_lift_lag1_{mode}.csv", index=False
    )
    artifacts.cooccurrence_phi.to_csv(
        out_dir / f"cooccurrence_phi_{mode}.csv", index=False
    )
    artifacts.lag_dependency.to_csv(
        out_dir / f"lag_dependency_{mode}.csv", index=False
    )
    diag = dict(artifacts.diagnostics)
    diag["anchor_date"] = str(dates.max().date())
    (out_dir / f"diagnostics_{mode}.json").write_text(
        json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return artifacts


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build higher-order Bayesian number-dynamics matrices."
    )
    ap.add_argument("--mode", choices=["loto", "de", "both"], default="both")
    ap.add_argument("--out-dir", default="data/number_dynamics")
    args = ap.parse_args()
    modes = ["loto", "de"] if args.mode == "both" else [args.mode]
    for mode in modes:
        artifacts = export_dynamics(mode, Path(args.out_dir))
        print(
            f"[OK] number dynamics {mode}: "
            f"reliability={artifacts.diagnostics['global_dynamics_reliability']:.3f}"
        )


if __name__ == "__main__":
    main()
