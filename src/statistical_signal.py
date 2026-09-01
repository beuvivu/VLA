from __future__ import annotations

"""Conservative empirical-Bayes statistical signal for the 00..99 universe.

This component combines:
- recency-weighted Bayesian frequency;
- target-weekday posterior;
- 30/90/365-calendar-day shrinkage;
- stability/credible intervals;
- higher-order number dynamics (Markov-2, renewal hazard, lag kernels,
  cross-number lag-1 transition matrices, and regime drift).

Every day/lag/window interpretation is evaluated only on a verified daily-
contiguous canonical calendar. All dynamic evidence is strongly shrunk toward
historical baselines. The output is a calibrated ranking component for the wider
ML/path ensemble, not a claim of deterministic numerical predictability.
"""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist

from calendar_alignment import require_daily_contiguous
from ensemble_utils import normalize_distribution
from lottery import Lottery
from number_dynamics import build_dynamics_signal, export_dynamics


def _exp_weights(n: int, half_life: float) -> np.ndarray:
    age = np.arange(n - 1, -1, -1, dtype=float)
    return np.power(0.5, age / max(float(half_life), 1.0))


def _effective_n(weights: np.ndarray) -> float:
    s = float(weights.sum())
    q = float(np.square(weights).sum())
    return 0.0 if q <= 0 else s * s / q


def _logit(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def _js_divergence(p: np.ndarray, q: np.ndarray) -> float:
    p = normalize_distribution(np.clip(p.astype(float), 1e-12, None))
    q = normalize_distribution(np.clip(q.astype(float), 1e-12, None))
    m = 0.5 * (p + q)
    return float(
        0.5 * np.sum(p * np.log(p / m))
        + 0.5 * np.sum(q * np.log(q / m))
    )


def _loto_signal(
    hit: np.ndarray,
    dates: pd.Series,
    target_weekday: int,
    *,
    half_life: int,
    prior_strength: float,
) -> pd.DataFrame:
    n = hit.shape[0]
    baseline = float(hit.mean())
    a0 = max(1e-6, baseline * prior_strength)
    b0 = max(1e-6, (1 - baseline) * prior_strength)

    w = _exp_weights(n, half_life)
    weighted_hits = (hit * w[:, None]).sum(axis=0)
    weighted_trials = float(w.sum())
    ewm = (a0 + weighted_hits) / (a0 + b0 + weighted_trials)

    weekday_mask = dates.dt.weekday.to_numpy() == int(target_weekday)
    weekday_hit = hit[weekday_mask]
    wk_hits = weekday_hit.sum(axis=0) if len(weekday_hit) else np.zeros(100)
    wk_n = int(len(weekday_hit))
    weekday = (a0 + wk_hits) / (a0 + b0 + wk_n)

    window_probs: dict[int, np.ndarray] = {}
    for window in (30, 90, 365):
        h = hit[-min(window, n) :]
        window_probs[window] = (a0 + h.sum(axis=0)) / (
            a0 + b0 + len(h)
        )

    stack = np.vstack([_logit(window_probs[w]) for w in (30, 90, 365)])
    instability = np.std(stack, axis=0)
    stability = np.exp(-0.55 * instability)

    raw = 0.55 * ewm + 0.25 * weekday + 0.20 * window_probs[90]
    prob = baseline + stability * (raw - baseline)
    prob = np.clip(prob, 1e-5, 1 - 1e-5)

    ess = _effective_n(w)
    weighted_rate = weighted_hits / max(weighted_trials, 1e-12)
    alpha = a0 + weighted_rate * ess
    beta = b0 + (1 - weighted_rate) * ess
    ci_low = beta_dist.ppf(0.025, alpha, beta)
    ci_high = beta_dist.ppf(0.975, alpha, beta)

    return pd.DataFrame(
        {
            "number": np.arange(100, dtype=int),
            "prob": prob,
            "baseline_prob": baseline,
            "ewm_prob": ewm,
            "weekday_prob": weekday,
            "p30": window_probs[30],
            "p90": window_probs[90],
            "p365": window_probs[365],
            "stability": stability,
            "credible_low": ci_low,
            "credible_high": ci_high,
            "effective_sample_size": ess,
            "weekday_trials": wk_n,
        }
    )


def _de_posterior(
    onehot: np.ndarray, weights: np.ndarray, prior_strength: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    prior = np.full(100, prior_strength / 100.0, dtype=float)
    counts = (onehot * weights[:, None]).sum(axis=0)
    alpha = prior + counts
    total = float(alpha.sum())
    p = alpha / total
    low = beta_dist.ppf(0.025, alpha, np.maximum(total - alpha, 1e-9))
    high = beta_dist.ppf(0.975, alpha, np.maximum(total - alpha, 1e-9))
    return p, low, high


def _de_signal(
    onehot: np.ndarray,
    dates: pd.Series,
    target_weekday: int,
    *,
    half_life: int,
    prior_strength: float,
) -> pd.DataFrame:
    n = onehot.shape[0]
    uniform = np.full(100, 0.01, dtype=float)
    w = _exp_weights(n, half_life)
    ewm, ci_low, ci_high = _de_posterior(onehot, w, prior_strength)

    weekday_mask = dates.dt.weekday.to_numpy() == int(target_weekday)
    weekday_rows = onehot[weekday_mask]
    weekday = (
        _de_posterior(
            weekday_rows, np.ones(len(weekday_rows)), prior_strength
        )[0]
        if len(weekday_rows)
        else uniform
    )

    window_probs: dict[int, np.ndarray] = {}
    for window in (30, 90, 365):
        h = onehot[-min(window, n) :]
        window_probs[window] = _de_posterior(
            h, np.ones(len(h)), prior_strength
        )[0]

    drift = np.array(
        [
            _js_divergence(window_probs[30], window_probs[90]),
            _js_divergence(window_probs[90], window_probs[365]),
            _js_divergence(window_probs[30], window_probs[365]),
        ]
    )
    global_stability = float(np.exp(-10.0 * drift.mean()))
    raw = normalize_distribution(
        0.55 * ewm + 0.25 * weekday + 0.20 * window_probs[90]
    )
    prob = normalize_distribution(
        uniform + global_stability * (raw - uniform)
    )

    return pd.DataFrame(
        {
            "number": np.arange(100, dtype=int),
            "prob": prob,
            "baseline_prob": 0.01,
            "ewm_prob": ewm,
            "weekday_prob": weekday,
            "p30": window_probs[30],
            "p90": window_probs[90],
            "p365": window_probs[365],
            "stability": global_stability,
            "credible_low": ci_low,
            "credible_high": ci_high,
            "effective_sample_size": _effective_n(w),
            "weekday_trials": int(len(weekday_rows)),
        }
    )


def _blend_dynamics(
    df: pd.DataFrame,
    hit: np.ndarray,
    dates: pd.Series,
    *,
    mode: str,
) -> tuple[pd.DataFrame, dict]:
    dynamics = build_dynamics_signal(hit, dates=dates, mode=mode)  # type: ignore[arg-type]
    dyn = dynamics.current.rename(
        columns={
            "prob": "dynamics_prob",
            "baseline_prob": "dynamics_baseline_prob",
            "transition_prob": "cross_transition_prob",
        }
    )
    keep = [
        "number",
        "dynamics_prob",
        "dynamics_baseline_prob",
        "markov2_prob",
        "markov2_state",
        "markov2_reliability",
        "hazard_prob",
        "next_gap",
        "hazard_reliability",
        "cross_transition_prob",
        "lag_kernel_prob",
        "regime_prob",
        "regime_log_ratio",
        "dynamics_reliability",
    ]
    merged = df.merge(dyn[keep], on="number", how="left")
    merged["base_stat_prob"] = merged["prob"].astype(float)

    dyn_weight = 0.30 if mode == "loto" else 0.20
    combined = (
        (1.0 - dyn_weight) * merged["base_stat_prob"].to_numpy(dtype=float)
        + dyn_weight * merged["dynamics_prob"].to_numpy(dtype=float)
    )
    if mode == "de":
        combined = normalize_distribution(np.clip(combined, 1e-12, None))
    else:
        combined = np.clip(combined, 1e-5, 1 - 1e-5)
    merged["prob"] = combined

    dyn_diag = {
        "dynamics_weight_in_stat_signal": dyn_weight,
        "global_dynamics_reliability": float(
            dynamics.diagnostics["global_dynamics_reliability"]
        ),
        "regime_js_divergence_30_vs_180": float(
            dynamics.diagnostics["regime_js_divergence_30_vs_180"]
        ),
        "transition_active_mean_trials": float(
            dynamics.diagnostics["transition_active_mean_trials"]
        ),
        "calendar_contiguous": bool(dynamics.diagnostics["calendar_contiguous"]),
    }
    return merged, dyn_diag


def build_statistical_signal(
    mode: str,
    *,
    half_life: int = 45,
    prior_strength: float = 80.0,
) -> tuple[pd.DataFrame, dict]:
    lot = Lottery()
    lot.load()
    two = lot.get_2_digits_data().copy()
    sparse = lot.get_sparse_data().copy()
    if two.empty or sparse.empty:
        raise RuntimeError("No lottery data loaded")
    two["date"] = pd.to_datetime(two["date"])
    sparse["date"] = pd.to_datetime(sparse["date"])

    two_calendar = require_daily_contiguous(
        two["date"], context="statistical signal two-digit history"
    )
    sparse_calendar = require_daily_contiguous(
        sparse["date"], context="statistical signal sparse history"
    )
    if not two_calendar.equals(sparse_calendar):
        raise ValueError("two-digit and sparse statistical histories are not date-aligned")

    anchor = two_calendar[-1].date()
    target = anchor + timedelta(days=1)

    if mode == "de":
        de = (two["special"].astype(int).to_numpy() % 100).astype(int)
        hit = np.zeros((len(de), 100), dtype=np.int8)
        hit[np.arange(len(de)), de] = 1
        dates = two["date"]
        df = _de_signal(
            hit,
            dates,
            target.weekday(),
            half_life=half_life,
            prior_strength=prior_strength,
        )
    elif mode == "loto":
        hit = (
            sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0
        ).astype(np.int8)
        dates = sparse["date"]
        df = _loto_signal(
            hit,
            dates,
            target.weekday(),
            half_life=half_life,
            prior_strength=prior_strength,
        )
    else:
        raise ValueError(mode)

    df, dynamics_diag = _blend_dynamics(df, hit, dates, mode=mode)
    df["number_str"] = df["number"].map(lambda x: f"{int(x):02d}")
    df["anchor_date"] = anchor.isoformat()
    df["target_date"] = target.isoformat()
    df.sort_values("prob", ascending=False, inplace=True, ignore_index=True)

    diagnostics = {
        "schema_version": 3,
        "mode": mode,
        "generated_at_utc": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "anchor_date": anchor.isoformat(),
        "target_date": target.isoformat(),
        "history_days": int(len(two)),
        "half_life_days": half_life,
        "prior_strength": prior_strength,
        "mean_stability": float(df["stability"].mean()),
        "min_stability": float(df["stability"].min()),
        "max_stability": float(df["stability"].max()),
        **dynamics_diag,
        "interpretation": (
            "Empirical-Bayes + higher-order dynamics component. Markov, "
            "transition, hazard, lag and regime evidence is shrinkage-regularized, "
            "calendar-validated, and used only as probabilistic ranking support."
        ),
    }
    return df, diagnostics


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Build conservative empirical-Bayes + higher-order dynamics "
            "statistical prediction component."
        )
    )
    ap.add_argument("--mode", choices=["loto", "de", "both"], default="both")
    ap.add_argument("--half-life", type=int, default=45)
    ap.add_argument("--prior-strength", type=float, default=80.0)
    ap.add_argument("--out-dir", default="data/statistical_signal")
    ap.add_argument("--dynamics-out-dir", default="data/number_dynamics")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    modes = ["loto", "de"] if args.mode == "both" else [args.mode]
    for mode in modes:
        df, diag = build_statistical_signal(
            mode,
            half_life=args.half_life,
            prior_strength=args.prior_strength,
        )
        df.to_csv(out / f"predict_next_{mode}_stat_all.csv", index=False)
        (out / f"diagnostics_{mode}.json").write_text(
            json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        export_dynamics(mode, Path(args.dynamics_out_dir))
        print(
            f"[OK] statistical signal {mode}: "
            f"target={diag['target_date']} -> {out}"
        )


if __name__ == "__main__":
    main()
