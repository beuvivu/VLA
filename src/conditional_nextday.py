from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from lottery import Lottery
from path_models import build_daily_targets


def compute_loto_nextday_given_special(df_2d: pd.DataFrame) -> pd.DataFrame:
    """Compute P(loto=x on day t+1 | special_2d on day t = s) for all s,x in 00..99.

    Output long-form:
      special, number, trials, hits, p
    Where trials = count of days where special==s and day+1 exists.
    hits = count of those days where number appears in loto at day+1.
    """
    df_2d = df_2d.sort_values("date").reset_index(drop=True)

    dates, loto_targets, de_targets = build_daily_targets(df_2d)
    n = len(dates)

    trials = np.zeros(100, dtype=np.int32)
    hits = np.zeros((100, 100), dtype=np.int32)  # [special][number]

    for t in range(n - 1):
        s = int(de_targets[t])  # today's special 2-digit
        trials[s] += 1
        next_set = loto_targets[t + 1]
        for x in next_set:
            hits[s, int(x)] += 1

    rows = []
    for s in range(100):
        tr = int(trials[s])
        if tr == 0:
            continue
        for x in range(100):
            h = int(hits[s, x])
            p = h / tr
            rows.append({"special": s, "number": x, "trials": tr, "hits": h, "p": p})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20, help="Top numbers per special to export")
    ap.add_argument("--out-dir", type=str, default="data/conditional")
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    df_2d = lot.get_2_digits_data()
    if df_2d.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    long_df = compute_loto_nextday_given_special(df_2d)
    long_df.to_csv(out_dir / "loto_nextday_given_special_long.csv", index=False)

    # Also export top-N per special
    top_df = (
        long_df.sort_values(["special", "p", "hits"], ascending=[True, False, False])
        .groupby("special")
        .head(args.top)
        .reset_index(drop=True)
    )
    top_df.to_csv(out_dir / f"loto_nextday_given_special_top{args.top}.csv", index=False)

    print(f"Saved {out_dir}/loto_nextday_given_special_long.csv")
    print(f"Saved {out_dir}/loto_nextday_given_special_top{args.top}.csv")


if __name__ == "__main__":
    main()
