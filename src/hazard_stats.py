from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from lottery import Lottery
from path_models import build_daily_targets


def hazard_curve_loto(df_2d: pd.DataFrame, max_gap: int = 60) -> pd.DataFrame:
    """Aggregate hazard by gap for loto hits.
    For each day and each number, gap = days since last hit (capped).
    hazard(g) = P(hit today | current gap == g).
    """
    df_2d = df_2d.sort_values("date").reset_index(drop=True)
    _, loto_targets, _ = build_daily_targets(df_2d)
    n = len(loto_targets)
    if n == 0:
        return pd.DataFrame()

    last_seen = np.full(100, -10**9, dtype=np.int32)
    # denominators: how many (day,number) had gap=g
    denom = np.zeros(max_gap + 1, dtype=np.int64)
    numer = np.zeros(max_gap + 1, dtype=np.int64)

    for t in range(n):
        hit_mask = np.zeros(100, dtype=bool)
        for x in loto_targets[t]:
            hit_mask[int(x)] = True

        gaps = t - last_seen
        gaps = np.clip(gaps, 0, max_gap)

        # count denom for all numbers
        for g in gaps.tolist():
            denom[g] += 1

        # count numer for hit numbers
        for x in np.where(hit_mask)[0]:
            g = int(gaps[x])
            numer[g] += 1
            last_seen[x] = t

    p = numer / np.maximum(denom, 1)
    df = pd.DataFrame({"gap": np.arange(max_gap + 1), "denom": denom, "hits": numer, "hazard": p})
    return df


def hazard_curve_de(df_2d: pd.DataFrame, max_gap: int = 200) -> pd.DataFrame:
    """Hazard by gap for the special-2digits value (de).
    We track for each number x=00..99 its gap since last time it appeared as de.
    hazard(g) = P(de == x today | gap(x) == g) aggregated across x and days.
    """
    df_2d = df_2d.sort_values("date").reset_index(drop=True)
    dates, _, de_targets = build_daily_targets(df_2d)
    n = len(dates)
    if n == 0:
        return pd.DataFrame()

    last_seen = np.full(100, -10**9, dtype=np.int32)
    denom = np.zeros(max_gap + 1, dtype=np.int64)
    numer = np.zeros(max_gap + 1, dtype=np.int64)

    for t in range(n):
        x = int(de_targets[t])
        gaps = t - last_seen
        gaps = np.clip(gaps, 0, max_gap)
        for g in gaps.tolist():
            denom[g] += 1
        g = int(gaps[x])
        numer[g] += 1
        last_seen[x] = t

    p = numer / np.maximum(denom, 1)
    return pd.DataFrame({"gap": np.arange(max_gap + 1), "denom": denom, "hits": numer, "hazard": p})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=str, default="data/hazard")
    ap.add_argument("--max-gap-loto", type=int, default=60)
    ap.add_argument("--max-gap-de", type=int, default=200)
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    df_2d = lot.get_2_digits_data()
    if df_2d.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    hazard_curve_loto(df_2d, max_gap=args.max_gap_loto).to_csv(out_dir / "hazard_loto.csv", index=False)
    hazard_curve_de(df_2d, max_gap=args.max_gap_de).to_csv(out_dir / "hazard_de.csv", index=False)
    print(f"Saved hazard curves to {out_dir}")


if __name__ == "__main__":
    main()
