from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from calendar_alignment import consecutive_next_pairs
from lottery import Lottery
from path_models import build_daily_targets


def compute_markov_for_loto(df_2d: pd.DataFrame, alpha: float = 1.0, beta: float = 1.0) -> pd.DataFrame:
    """Estimate same-number next-calendar-day transition probabilities.

    For each number x in 00..99:
      p_hit_given_hit = P(hit_t=1 | hit_{t-1 calendar day}=1)
      p_hit_given_miss = P(hit_t=1 | hit_{t-1 calendar day}=0)

    Missing dates are skipped rather than collapsing a multi-day jump into a
    one-day Markov transition. Probabilities use Beta smoothing.
    """
    df_2d = df_2d.sort_values("date").reset_index(drop=True)
    dates, loto_targets, _ = build_daily_targets(df_2d)
    n = len(loto_targets)
    if n < 2:
        return pd.DataFrame()

    hit = np.zeros((n, 100), dtype=bool)
    for t, nums in enumerate(loto_targets):
        if nums:
            hit[t, np.fromiter((int(x) for x in nums), dtype=np.int16)] = True

    source_idx, target_idx = consecutive_next_pairs(dates)
    if source_idx.size == 0:
        return pd.DataFrame()

    prev_hit = hit[source_idx]
    curr_hit = hit[target_idx]

    prev1_total = prev_hit.sum(axis=0, dtype=np.int32)
    prev0_total = (~prev_hit).sum(axis=0, dtype=np.int32)
    prev1_curr1 = (prev_hit & curr_hit).sum(axis=0, dtype=np.int32)
    prev0_curr1 = ((~prev_hit) & curr_hit).sum(axis=0, dtype=np.int32)

    p11 = (prev1_curr1 + alpha) / (prev1_total + alpha + beta)
    p01 = (prev0_curr1 + alpha) / (prev0_total + alpha + beta)

    df = pd.DataFrame(
        {
            "number": np.arange(100, dtype=np.int32),
            "calendar_transition_days": int(source_idx.size),
            "prev1_total": prev1_total,
            "prev1_curr1": prev1_curr1,
            "p_hit_given_hit": p11,
            "prev0_total": prev0_total,
            "prev0_curr1": prev0_curr1,
            "p_hit_given_miss": p01,
            "lift": p11 / np.maximum(p01, 1e-9),
        }
    ).sort_values(["lift", "p_hit_given_hit"], ascending=[False, False])

    return df.reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="data/markov/markov_loto.csv")
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--beta", type=float, default=1.0)
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    df_2d = lot.get_2_digits_data()
    if df_2d.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = compute_markov_for_loto(df_2d, alpha=args.alpha, beta=args.beta)
    df.to_csv(out_path, index=False)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
