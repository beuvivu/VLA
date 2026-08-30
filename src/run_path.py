from __future__ import annotations

import argparse
from pathlib import Path

from lottery import Lottery
from path_models import PathParams
from path_prob import fit_paths, paths_to_dataframe, predict_next_day


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["loto", "de"], required=True)
    ap.add_argument("--lag-max", type=int, default=30)
    ap.add_argument("--window-days", type=int, default=365)
    ap.add_argument("--min-trials", type=int, default=60)
    ap.add_argument("--min-max-streak", type=int, default=3)
    ap.add_argument("--min-current-streak", type=int, default=3)
    ap.add_argument("--top-rules-per-lag", type=int, default=300)
    ap.add_argument("--top-numbers", type=int, default=20)
    ap.add_argument("--out-dir", type=str, default="data/path")
    args = ap.parse_args()

    params = PathParams(
        lag_max=args.lag_max,
        window_days=args.window_days,
        min_trials=args.min_trials,
        min_max_streak=args.min_max_streak,
        min_current_streak=args.min_current_streak,
        top_rules_per_lag=args.top_rules_per_lag,
    )

    lot = Lottery()
    lot.load()
    df_raw = lot.get_raw_data()
    df_2d = lot.get_2_digits_data()
    if df_raw.empty or df_2d.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stats, _, _ = fit_paths(df_raw=df_raw, df_2digits=df_2d, params=params, mode=args.mode)
    paths_df = paths_to_dataframe(stats)
    paths_df.to_csv(out_dir / f"paths_{args.mode}.csv", index=False)

    pred_active = predict_next_day(
        df_raw=df_raw,
        df_2digits=df_2d,
        params=params,
        mode=args.mode,
        kind="active",
        top_numbers=args.top_numbers,
    )
    pred_stable = predict_next_day(
        df_raw=df_raw,
        df_2digits=df_2d,
        params=params,
        mode=args.mode,
        kind="stable",
        top_numbers=args.top_numbers,
    )

    pred_active.to_csv(out_dir / f"predict_next_{args.mode}_active.csv", index=False)
    pred_stable.to_csv(out_dir / f"predict_next_{args.mode}_stable.csv", index=False)

    print("ACTIVE (current_streak):")
    print(pred_active)
    print("\nSTABLE (max_streak):")
    print(pred_stable)


if __name__ == "__main__":
    main()
