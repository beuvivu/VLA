from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from lottery import Lottery
from path_models import PathParams, build_daily_targets
from path_prob import (
    fit_paths,
    predict_from_fitted_paths_full,
    prepare_path_history,
)
from xsmb_domain import baseline_rate

Mode = Literal["loto", "de"]
Kind = Literal["active", "stable"]


@dataclass
class EvalResult:
    day: date
    brier: float
    logloss: float
    # A score is meaningless without something to beat.  Every evaluated day now
    # also scores the no-information constant (1-0.99^27 for lô tô, 0.01 for ĐB).
    # If the model cannot beat this, its ranking is noise however plausible the
    # probabilities look.
    baseline_brier: float = float("nan")
    baseline_logloss: float = float("nan")


def _safe_logloss(p: np.ndarray, y: np.ndarray, eps: float = 1e-12) -> float:
    p = np.clip(p, eps, 1 - eps)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(((p - y) ** 2).mean())


def _reliability_bins(p: np.ndarray, y: np.ndarray, bins: int = 10) -> pd.DataFrame:
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.digitize(p, edges, right=True) - 1
    idx = np.clip(idx, 0, bins - 1)

    rows = []
    for b in range(bins):
        m = idx == b
        if not m.any():
            continue
        rows.append(
            {
                "bin": b,
                "p_mean": float(p[m].mean()),
                "y_mean": float(y[m].mean()),
                "count": int(m.sum()),
            }
        )
    return pd.DataFrame(rows)


def evaluate(
    *,
    df_raw: pd.DataFrame,
    df_2d: pd.DataFrame,
    params: PathParams,
    mode: Mode,
    kind: Kind,
    eval_days: int = 180,
) -> tuple[list[EvalResult], pd.DataFrame]:
    dates, loto_targets, de_targets = build_daily_targets(df_2d)

    n = len(dates)
    start = max(0, n - eval_days)

    # For each target day t, train on history ending at t-1 (so last_date == dates[t-1]),
    # then predict_next_day -> probabilities for day t.
    daily: list[EvalResult] = []
    all_p: list[float] = []
    all_y: list[int] = []

    # Every day of the walk-forward previously re-derived the digit matrix, the
    # per-day target sets and the days x pairs table from the whole prefix.
    # They do not depend on the anchor, so they are built once here; fit_paths
    # still only reads rows up to its anchor index, so the walk-forward remains
    # strictly causal.
    prepared = prepare_path_history(df_raw, df_2d)

    for t in range(start, n):
        if t == 0:
            continue
        anchor = dates[t - 1]

        # BUG FIX: ``predict_next_day`` filters out numbers with no supporting
        # path before returning, so the reconstructed vector had holes at
        # probability 0.  For ĐB the vector had already been normalised *before*
        # that filter, so the evaluated distribution did not sum to 1; any day
        # whose winning number was filtered out scored a log-loss of ~27.6
        # against a probability that the model never actually asserted.
        # ``predict_from_fitted_paths_full`` always returns all 100 numbers.
        stats_t, raw_by_date, dates_t = fit_paths(
            params=params, mode=mode, anchor_date=anchor, prepared=prepared
        )
        pred = predict_from_fitted_paths_full(
            stats=stats_t,
            raw_by_date=raw_by_date,
            dates=dates_t,
            params=params,
            kind=kind,
            mode=mode,
            anchor_date=anchor,
        )
        if pred.empty:
            continue

        p = np.zeros(100, dtype=np.float64)
        p[pred["number"].to_numpy(dtype=int)] = pred["prob"].to_numpy(dtype=float)

        if mode == "loto":
            yset = loto_targets[t]
            y = np.zeros(100, dtype=np.float64)
            for v in yset:
                y[int(v)] = 1.0
        else:
            y = np.zeros(100, dtype=np.float64)
            y[int(de_targets[t])] = 1.0

        const = np.full(100, baseline_rate(mode), dtype=np.float64)
        daily.append(
            EvalResult(
                day=dates[t],
                brier=_brier(p, y),
                logloss=_safe_logloss(p, y),
                baseline_brier=_brier(const, y),
                baseline_logloss=_safe_logloss(const, y),
            )
        )
        all_p.extend(p.tolist())
        all_y.extend(y.tolist())

    rel = _reliability_bins(np.array(all_p, dtype=np.float64), np.array(all_y, dtype=np.float64), bins=10)
    return daily, rel


def plot_reliability(rel: pd.DataFrame, out_path: Path, title: str) -> None:
    plt.figure()
    plt.plot([0, 1], [0, 1])
    plt.plot(rel["p_mean"], rel["y_mean"], marker="o")
    plt.xlabel("Mean predicted probability (bin)")
    plt.ylabel("Empirical frequency")
    plt.title(title)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["loto", "de"], required=True)
    ap.add_argument("--kind", choices=["active", "stable"], required=True)
    ap.add_argument("--eval-days", type=int, default=180)
    ap.add_argument("--lag-max", type=int, default=30)
    ap.add_argument("--window-days", type=int, default=365)
    ap.add_argument("--min-trials", type=int, default=60)
    ap.add_argument("--min-max-streak", type=int, default=3)
    ap.add_argument("--min-current-streak", type=int, default=3)
    args = ap.parse_args()

    params = PathParams(
        lag_max=args.lag_max,
        window_days=args.window_days,
        min_trials=args.min_trials,
        min_max_streak=args.min_max_streak,
        min_current_streak=args.min_current_streak,
    )

    lot = Lottery()
    lot.load()
    df_raw = lot.get_raw_data()
    df_2d = lot.get_2_digits_data()
    if df_raw.empty or df_2d.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    daily, rel = evaluate(df_raw=df_raw, df_2d=df_2d, params=params, mode=args.mode, kind=args.kind, eval_days=args.eval_days)

    out_dir = Path("data") / "prob_eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    daily_df = pd.DataFrame(
        [
            {
                "day": r.day.isoformat(),
                "brier": r.brier,
                "logloss": r.logloss,
                "baseline_brier": r.baseline_brier,
                "baseline_logloss": r.baseline_logloss,
            }
            for r in daily
        ]
    )
    daily_df.to_csv(out_dir / f"daily_{args.mode}_{args.kind}.csv", index=False)
    rel.to_csv(out_dir / f"reliability_{args.mode}_{args.kind}.csv", index=False)

    img_path = Path("images") / "prob_eval" / f"reliability_{args.mode}_{args.kind}.png"
    plot_reliability(rel, img_path, title=f"Reliability diagram: {args.mode} / {args.kind}")

    print("Saved:", out_dir / f"daily_{args.mode}_{args.kind}.csv")
    print("Saved:", out_dir / f"reliability_{args.mode}_{args.kind}.csv")
    print("Saved:", img_path)
    if daily_df.empty:
        print("No evaluated days.")
        return

    # Report skill against the constant baseline with a paired 95% interval, so
    # "the model looks reasonable" cannot be mistaken for "the model helps".
    for metric in ("brier", "logloss"):
        model = daily_df[metric].to_numpy(dtype=float)
        base = daily_df[f"baseline_{metric}"].to_numpy(dtype=float)
        diff = model - base
        half_width = (
            1.96 * float(np.std(diff, ddof=1)) / np.sqrt(len(diff)) if len(diff) > 1 else float("nan")
        )
        skill = 1.0 - model.mean() / base.mean() if base.mean() else float("nan")
        verdict = (
            "WORSE than constant" if diff.mean() - half_width > 0
            else "BETTER than constant" if diff.mean() + half_width < 0
            else "indistinguishable from constant"
        )
        print(
            f"Mean {metric}: {model.mean():.6f}  baseline: {base.mean():.6f}  "
            f"skill: {skill:+.4%}  paired diff: {diff.mean():+.6f} ± {half_width:.6f}  -> {verdict}"
        )


if __name__ == "__main__":
    main()
