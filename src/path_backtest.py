from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from calendar_alignment import consecutive_next_pairs, normalize_dates
from lottery import Lottery
from path_models import PathParams, build_daily_targets
from path_prob import predict_next_day

Mode = Literal["loto", "de"]
Kind = Literal["active", "stable"]


@dataclass
class BacktestResult:
    date: str
    kind: str
    mode: str
    k: int
    hit: int
    hits_count: int
    support_paths: int
    mean_prob: float


def _eval_one_day(
    df_raw: pd.DataFrame,
    df_2d: pd.DataFrame,
    *,
    idx_train_end: int,
    target_idx: int,
    params: PathParams,
    mode: Mode,
    kind: Kind,
    top_k: int,
) -> tuple[int, int, int, float]:
    """Train through one anchor draw and score its exact next-calendar-day target."""
    dates = normalize_dates(df_2d["date"])
    if target_idx >= len(dates) or (dates[target_idx] - dates[idx_train_end]).days != 1:
        raise ValueError("path backtest target must be exactly one calendar day after anchor")

    df_raw_train = df_raw.iloc[: idx_train_end + 1].copy()
    df_2d_train = df_2d.iloc[: idx_train_end + 1].copy()

    pred = predict_next_day(
        df_raw=df_raw_train,
        df_2digits=df_2d_train,
        params=params,
        mode=mode,
        kind=kind,
        top_numbers=top_k,
    )
    if pred.empty:
        return 0, 0, 0, 0.0

    _, loto_targets, de_targets = build_daily_targets(df_2d)
    if mode == "loto":
        actual_set = loto_targets[target_idx]
        hit_flags = [1 if int(n) in actual_set else 0 for n in pred["number"].tolist()]
    else:
        actual = int(de_targets[target_idx])
        hit_flags = [1 if int(n) == actual else 0 for n in pred["number"].tolist()]

    return (
        int(any(hit_flags)),
        int(sum(hit_flags)),
        int(pred["support_paths_count"].sum()),
        float(pred["prob"].mean()),
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["loto", "de"], required=True)
    ap.add_argument("--kind", choices=["active", "stable"], required=True)
    ap.add_argument("--lag-max", type=int, default=30)
    ap.add_argument("--window-days", type=int, default=365)
    ap.add_argument("--min-trials", type=int, default=60)
    ap.add_argument("--min-max-streak", type=int, default=3)
    ap.add_argument("--min-current-streak", type=int, default=3)
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--bt-days", type=int, default=180)
    ap.add_argument("--out", type=str, default="data/path/backtest.csv")
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
    df_raw = lot.get_raw_data().sort_values("date").reset_index(drop=True)
    df_2d = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    if df_raw.empty or df_2d.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    raw_dates = normalize_dates(df_raw["date"])
    two_dates = normalize_dates(df_2d["date"])
    if not raw_dates.equals(two_dates):
        raise SystemExit("Raw and two-digit histories are not date-aligned")

    source_idx, target_idx = consecutive_next_pairs(raw_dates)
    if source_idx.size == 0:
        raise SystemExit("No exact next-calendar-day trials available for backtest")
    # Keep the most recent requested number of legitimate calendar transitions.
    if args.bt_days > 0:
        source_idx = source_idx[-args.bt_days :]
        target_idx = target_idx[-args.bt_days :]

    res: list[BacktestResult] = []
    for idx_train_end, idx_target in zip(source_idx.tolist(), target_idx.tolist()):
        d = raw_dates[idx_target].date().isoformat()
        hit, hits_count, support_paths, mean_prob = _eval_one_day(
            df_raw,
            df_2d,
            idx_train_end=int(idx_train_end),
            target_idx=int(idx_target),
            params=params,
            mode=args.mode,  # type: ignore[arg-type]
            kind=args.kind,  # type: ignore[arg-type]
            top_k=args.top_k,
        )
        res.append(
            BacktestResult(
                date=d,
                kind=args.kind,
                mode=args.mode,
                k=args.top_k,
                hit=hit,
                hits_count=hits_count,
                support_paths=support_paths,
                mean_prob=mean_prob,
            )
        )

    out_df = pd.DataFrame([r.__dict__ for r in res])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)

    if not out_df.empty:
        summary = {
            "days": int(out_df.shape[0]),
            "calendar_next_day_only": True,
            "hit_rate@k": float(out_df["hit"].mean()),
            "mean_hits_in_topk": float(out_df["hits_count"].mean()),
            "mean_support_paths": float(out_df["support_paths"].mean()),
            "mean_pred_prob": float(out_df["mean_prob"].mean()),
        }
        summary_path = out_path.with_name(out_path.stem + "_summary.json")
        summary_path.write_text(pd.Series(summary).to_json(indent=2), encoding="utf-8")
        print(summary)

    print(f"Saved backtest to {out_path}")


if __name__ == "__main__":
    main()
