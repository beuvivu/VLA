from __future__ import annotations

from core.lottery_codes import write_code_csv


import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import beta as beta_dist

from core.calendar_alignment import require_daily_contiguous
from ensemble.ensemble_utils import normalize_distribution
from ensemble.hierarchical_pooling import PoolingFit, fit_pooling
from ensemble.opinion_pool import (
    SIGNIFICANCE_SIGMAS,
    PoolAudit,
    PoolParams,
    apply_pool,
    fit_pool,
)
from ingest.lottery import Lottery
from stats.number_dynamics import build_dynamics_signal, export_dynamics


def _exp_weights(n: int, half_life: float) -> np.ndarray:
    age = np.arange(n - 1, -1, -1, dtype=float)
    return np.power(0.5, age / max(float(half_life), 1.0))


def _effective_n(weights: np.ndarray) -> float:
    s = float(weights.sum())
    q = float(np.square(weights).sum())
    return 0.0 if q <= 0 else s * s / q


def _weighted_counts(
    observations: np.ndarray, weights: np.ndarray
) -> tuple[np.ndarray, float]:
    scale = float(np.max(weights, initial=0.0))
    if scale <= 0.0:
        return np.zeros(observations.shape[1], dtype=float), 0.0
    relative = weights / scale
    ess = _effective_n(relative)
    rates = (observations * relative[:, None]).sum(axis=0) / relative.sum()
    return rates * ess, ess


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


def _eb_parameters(
    counts: np.ndarray, trials: float, prior_strength: float | None
) -> tuple[np.ndarray, np.ndarray]:
    if prior_strength is None:
        fit = fit_pooling(counts, float(trials))
        kappa, mean = fit.prior_strength, fit.pooled_rate
    else:
        kappa = float(prior_strength)
        mean = float(counts.sum() / (trials * counts.size))
    a0 = max(1e-6, mean * kappa)
    b0 = max(1e-6, (1.0 - mean) * kappa)
    return a0 + counts, b0 + (trials - counts)


def _eb_posterior(
    counts: np.ndarray, trials: float, prior_strength: float | None
) -> np.ndarray:
    if trials <= 0.0:
        return np.full(counts.shape, 1.0 / max(counts.size, 1), dtype=float)
    alpha, beta = _eb_parameters(counts, trials, prior_strength)
    return alpha / (alpha + beta)


SIGNAL_COMPONENT_WEIGHTS: tuple[float, float, float] = (0.55, 0.25, 0.20)
POOL_SELECTION_DAYS = 300


def select_signal_pool(
    hit: np.ndarray,
    dates: pd.Series,
    *,
    mode: str,
    half_life: int,
    eval_days: int = POOL_SELECTION_DAYS,
) -> tuple[PoolParams | None, PoolAudit | None]:
    days = int(hit.shape[0])
    start = max(200, days - eval_days)
    if days - start < 60:
        return None, None

    cube, labels = [], []
    for t in range(start, days):
        past = hit[:t]
        w = _exp_weights(t, half_life)
        counts, ess = _weighted_counts(past, w)
        ewm = _eb_posterior(counts, ess, None)

        target_weekday = int(pd.Timestamp(dates.iloc[t]).weekday())
        mask = np.array(
            [pd.Timestamp(d).weekday() == target_weekday for d in dates.iloc[:t]]
        )
        weekday_rows = past[mask]
        weekday = _eb_posterior(
            weekday_rows.sum(axis=0) if len(weekday_rows) else np.zeros(100),
            float(len(weekday_rows)),
            None,
        )
        window = past[-min(90, t):]
        p90 = _eb_posterior(window.sum(axis=0), float(len(window)), None)

        cube.append(np.vstack([ewm, weekday, p90]))
        labels.append(hit[t])

    return fit_pool(
        mode,  # type: ignore[arg-type]
        np.stack(cube),
        np.stack(labels),
        np.asarray(SIGNAL_COMPONENT_WEIGHTS),
    )


def _loto_signal(
    hit: np.ndarray,
    dates: pd.Series,
    target_weekday: int,
    *,
    half_life: int,
    prior_strength: float | None,
    pool: PoolParams | None = None,
) -> pd.DataFrame:
    n = hit.shape[0]
    baseline = float(hit.mean())

    w = _exp_weights(n, half_life)
    counts, ess = _weighted_counts(hit, w)
    alpha, beta = _eb_parameters(counts, ess, prior_strength)
    ewm = alpha / (alpha + beta)

    weekday_mask = dates.dt.day_of_week.to_numpy() == int(target_weekday)
    weekday_hit = hit[weekday_mask]
    wk_hits = weekday_hit.sum(axis=0) if len(weekday_hit) else np.zeros(100)
    wk_n = int(len(weekday_hit))
    weekday = _eb_posterior(wk_hits, float(wk_n), prior_strength)

    window_probs: dict[int, np.ndarray] = {}
    for window in (30, 90, 365):
        h = hit[-min(window, n) :]
        window_probs[window] = _eb_posterior(
            h.sum(axis=0), float(len(h)), prior_strength
        )

    stack = np.vstack([_logit(window_probs[w]) for w in (30, 90, 365)])
    instability = np.std(stack, axis=0)
    stability = np.exp(-0.55 * instability)

    components = np.vstack([ewm, weekday, window_probs[90]])
    if pool is None:
        raw = np.tensordot(np.asarray(SIGNAL_COMPONENT_WEIGHTS), components, axes=(0, 0))
    else:
        raw = apply_pool("loto", components, pool)
    prob = baseline + stability * (raw - baseline)
    prob = np.clip(prob, 1e-5, 1 - 1e-5)

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
    onehot: np.ndarray, weights: np.ndarray, prior_strength: float | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    counts, ess = _weighted_counts(onehot, weights)
    if prior_strength is None:
        kappa = (
            fit_pooling(counts, ess).prior_strength
            if ess > 0.0 and counts.size >= 3
            else 100.0
        )
    else:
        kappa = float(prior_strength)
    prior = np.full(100, kappa / 100.0, dtype=float)
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
    prior_strength: float | None,
) -> pd.DataFrame:
    n = onehot.shape[0]
    uniform = np.full(100, 0.01, dtype=float)
    w = _exp_weights(n, half_life)
    ewm, ci_low, ci_high = _de_posterior(onehot, w, prior_strength)

    weekday_mask = dates.dt.day_of_week.to_numpy() == int(target_weekday)
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


LEARN_PRIOR_STRENGTH: float | None = None

HALF_LIFE_GRID: tuple[int, ...] = (45, 90, 180, 365, 730, 1460)
LEARN_HALF_LIFE: int | None = None
MIN_HALF_LIFE_SELECTION_DAYS = 200
HALF_LIFE_HOLDOUT = 0.25
_FLOAT_NOISE = 1e-12


def select_half_life(
    hit: np.ndarray,
    *,
    grid: tuple[int, ...] = HALF_LIFE_GRID,
    holdout_fraction: float = HALF_LIFE_HOLDOUT,
) -> tuple[int, dict[str, float] | None]:
    days = int(hit.shape[0])
    split = int(round(days * (1.0 - holdout_fraction)))
    if days < MIN_HALF_LIFE_SELECTION_DAYS or split <= 1 or days - split <= 1:
        return int(grid[0]), None

    per_day: dict[int, np.ndarray] = {}
    for half_life in grid:
        errors = []
        for t in range(split, days):
            past = hit[:t]
            w = _exp_weights(t, half_life)
            counts, ess = _weighted_counts(past, w)
            p = _eb_posterior(counts, ess, None)
            errors.append(float(np.mean((p - hit[t]) ** 2)))
        per_day[half_life] = np.asarray(errors, dtype=float)
    scores = {str(hl): float(errors.mean()) for hl, errors in per_day.items()}

    best_hl = min(grid, key=lambda hl: (scores[str(hl)], hl))
    best_errors = per_day[best_hl]
    n_days = max(best_errors.size, 1)

    tied = []
    for half_life in grid:
        delta = per_day[half_life] - best_errors
        standard_error = float(np.std(delta, ddof=1) / np.sqrt(n_days)) if n_days > 1 else 0.0
        if float(delta.mean()) <= SIGNIFICANCE_SIGMAS * standard_error + _FLOAT_NOISE:
            tied.append(half_life)

    return int(min(tied)), scores


def _resolve_prior_strength(
    observations: np.ndarray, prior_strength: float | None
) -> tuple[float, PoolingFit | None]:
    if prior_strength is not None:
        return float(prior_strength), None
    fit = fit_pooling(observations.sum(axis=0), float(observations.shape[0]))
    return fit.prior_strength, fit


def build_statistical_signal(
    mode: str,
    *,
    half_life: int | None = LEARN_HALF_LIFE,
    prior_strength: float | None = LEARN_PRIOR_STRENGTH,
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
        _strength, pooling = _resolve_prior_strength(hit, prior_strength)
        chosen_half_life, half_life_scores = (
            (half_life, None) if half_life is not None else select_half_life(hit)
        )
        pool, pool_audit = None, None
        df = _de_signal(
            hit,
            dates,
            target.weekday(),
            half_life=chosen_half_life,
            prior_strength=prior_strength,
        )
    elif mode == "loto":
        hit = (
            sparse.drop(columns=["date"]).to_numpy(dtype=int) > 0
        ).astype(np.int8)
        dates = sparse["date"]
        _strength, pooling = _resolve_prior_strength(hit, prior_strength)
        chosen_half_life, half_life_scores = (
            (half_life, None) if half_life is not None else select_half_life(hit)
        )
        pool, pool_audit = select_signal_pool(
            hit, dates, mode="loto", half_life=chosen_half_life
        )
        df = _loto_signal(
            hit,
            dates,
            target.weekday(),
            half_life=chosen_half_life,
            prior_strength=prior_strength,
            pool=pool,
        )
    else:
        raise ValueError(mode)

    df, dynamics_diag = _blend_dynamics(df, hit, dates, mode=mode)
    df["number_str"] = df["number"].map(lambda x: f"{int(x):02d}")
    df["anchor_date"] = anchor.isoformat()
    df["target_date"] = target.isoformat()
    df = df.sort_values("prob", ascending=False, ignore_index=True, kind="stable")

    diagnostics = {
        "schema_version": 3,
        "mode": mode,
        "generated_at_utc": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "anchor_date": anchor.isoformat(),
        "target_date": target.isoformat(),
        "history_days": int(len(two)),
        "half_life_days": chosen_half_life,
        "half_life_learned": half_life_scores is not None,
        "half_life_brier_by_candidate": half_life_scores,
        "pool": None if pool_audit is None else {
            "kind": pool_audit.chosen,
            "sharpness": pool_audit.sharpness,
            "selected": pool_audit.selected,
            "brier_by_candidate": pool_audit.brier_by_candidate,
            "holdout_days": pool_audit.holdout_days,
            "verdict": pool_audit.describe(),
        },
        "prior_strength": _strength,
        "prior_strength_learned": pooling is not None,
        "pooling": None if pooling is None else {
            "pooled_rate": pooling.pooled_rate,
            "shrinkage": pooling.shrinkage,
            "effective_parameters": pooling.effective_parameters,
            "fully_pooled": pooling.fully_pooled,
            "between_variance": pooling.between_variance,
            "within_variance": pooling.within_variance,
            "verdict": pooling.describe(),
        },
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
    ap.add_argument("--half-life", type=int, default=None)
    ap.add_argument("--prior-strength", type=float, default=None)
    ap.add_argument("--out-dir", default="data/stats/statistical_signal")
    ap.add_argument("--dynamics-out-dir", default="data/stats/number_dynamics")
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
        write_code_csv(df, out / f"predict_next_{mode}_stat_all.csv", index=False)
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
