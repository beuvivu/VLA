from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from lottery import Lottery
from path_models import build_daily_targets


def compute_reversal_pair_cooccurrence(df_2d: pd.DataFrame) -> pd.DataFrame:
    """Count how often a number and its reverse (ab and ba) co-occur in the same day (loto set)."""
    df_2d = df_2d.sort_values("date").reset_index(drop=True)
    dates, loto_targets, _ = build_daily_targets(df_2d)

    counts = np.zeros(100, dtype=np.int32)
    days = np.zeros(100, dtype=np.int32)

    for s in loto_targets:
        for x in range(100):
            a = x // 10
            b = x % 10
            rev = b * 10 + a
            if x < rev:  # count each pair once using the smaller label
                days[x] += 1
                if (x in s) and (rev in s):
                    counts[x] += 1

    rows = []
    for x in range(100):
        a = x // 10
        b = x % 10
        rev = b * 10 + a
        if x < rev:
            d = int(days[x])
            c = int(counts[x])
            rows.append(
                {
                    "pair": f"{x:02d}-{rev:02d}",
                    "a": x,
                    "b": rev,
                    "days": d,
                    "cooccur": c,
                    "rate": c / d if d else 0.0,
                }
            )

    return pd.DataFrame(rows).sort_values(["rate", "cooccur"], ascending=[False, False]).reset_index(drop=True)


def compute_pair_frequency(df_2d: pd.DataFrame) -> pd.DataFrame:
    """Count unordered pair frequency within a day for all numbers (combinatorial).

    For each day, for each unordered pair (x<y) present in loto set, increment count.
    This can get large; we export only top pairs.
    """
    df_2d = df_2d.sort_values("date").reset_index(drop=True)
    _, loto_targets, _ = build_daily_targets(df_2d)

    from collections import Counter

    ctr: Counter[tuple[int, int]] = Counter()
    for s in loto_targets:
        arr = sorted(s)
        for i in range(len(arr)):
            for j in range(i + 1, len(arr)):
                ctr[(arr[i], arr[j])] += 1

    rows = [{"x": k[0], "y": k[1], "count": v, "pair": f"{k[0]:02d}-{k[1]:02d}"} for k, v in ctr.items()]
    return pd.DataFrame(rows).sort_values("count", ascending=False).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=str, default="data/pairs")
    ap.add_argument("--top", type=int, default=300)
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    df_2d = lot.get_2_digits_data()
    if df_2d.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rev = compute_reversal_pair_cooccurrence(df_2d)
    rev.to_csv(out_dir / "reversal_pair_cooccurrence.csv", index=False)

    pairs = compute_pair_frequency(df_2d).head(args.top)
    pairs.to_csv(out_dir / f"top_unordered_pairs_top{args.top}.csv", index=False)

    print(f"Saved pair stats to {out_dir}")


if __name__ == "__main__":
    main()
