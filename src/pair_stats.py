from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from cap_loto_50_stats import build_stats as build_cap_loto_50_stats
from lottery import Lottery
from path_models import build_daily_targets


def compute_reversal_pair_cooccurrence(df_2d: pd.DataFrame) -> pd.DataFrame:
    """Count same-day co-occurrence for the 45 non-double reverse pairs."""

    df_2d = df_2d.sort_values("date").reset_index(drop=True)
    _, loto_targets, _ = build_daily_targets(df_2d)

    counts = np.zeros(100, dtype=np.int32)
    days = np.zeros(100, dtype=np.int32)

    for s in loto_targets:
        for x in range(100):
            a = x // 10
            b = x % 10
            rev = b * 10 + a
            if x < rev:
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

    return (
        pd.DataFrame(rows)
        .sort_values(["rate", "cooccur"], ascending=[False, False])
        .reset_index(drop=True)
    )


def compute_pair_frequency(df_2d: pd.DataFrame) -> pd.DataFrame:
    """Count unordered same-day pair frequency for all distinct loto numbers."""

    df_2d = df_2d.sort_values("date").reset_index(drop=True)
    _, loto_targets, _ = build_daily_targets(df_2d)

    from collections import Counter

    ctr: Counter[tuple[int, int]] = Counter()
    for s in loto_targets:
        arr = sorted(s)
        for i in range(len(arr)):
            for j in range(i + 1, len(arr)):
                ctr[(arr[i], arr[j])] += 1

    rows = [
        {
            "x": pair[0],
            "y": pair[1],
            "count": count,
            "pair": f"{pair[0]:02d}-{pair[1]:02d}",
        }
        for pair, count in ctr.items()
    ]
    return pd.DataFrame(rows).sort_values("count", ascending=False).reset_index(drop=True)


def _write_cap_loto_50_stats(*, data_dir: Path, out_dir: Path) -> None:
    for mode in ("loto", "de"):
        df, summary = build_cap_loto_50_stats(mode, data_dir=data_dir)
        df.to_csv(out_dir / f"cap_loto_50_stats_{mode}.csv", index=False)
        (out_dir / f"cap_loto_50_summary_{mode}.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=str, default="data/pairs")
    ap.add_argument("--data-dir", type=str, default="data")
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

    # The 50-pair system is a different object from arbitrary co-occurrence:
    # 45 AB-BA pairs plus 5 kép-bóng pairs partition the whole 00..99 universe.
    _write_cap_loto_50_stats(data_dir=Path(args.data_dir), out_dir=out_dir)

    print(f"Saved pair stats to {out_dir}")


if __name__ == "__main__":
    main()
