from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from lottery import Lottery


def _gap_series(hit_days: list[int], n: int) -> tuple[int, int, float, float]:
    """Return (current_gap, max_gap, mean_gap, median_gap) in days between hits.
    hit_days: sorted list of day indices where hit occurs.
    n: total days
    """
    if not hit_days:
        return n, n, float("nan"), float("nan")
    gaps = []
    prev = -1
    for d in hit_days:
        gaps.append(d - prev - 1)
        prev = d
    # gap after last hit to end
    current_gap = (n - 1) - hit_days[-1]
    max_gap = max(gaps + [current_gap])
    mean_gap = float(np.mean(gaps)) if gaps else float("nan")
    median_gap = float(np.median(gaps)) if gaps else float("nan")
    return int(current_gap), int(max_gap), mean_gap, median_gap


def build_cycle_tables(out_dir: str = "data/cycle") -> None:
    lot = Lottery()
    lot.load()
    df2 = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    if df2.empty:
        raise SystemExit("No data available. Run src/sync.py first.")

    dates = [d.to_pydatetime().date() for d in pd.to_datetime(df2["date"])]
    n = len(dates)

    # DE: 2 digits from special
    de = (df2["special"].astype(int) % 100).tolist()

    rows_de = []
    for x in range(100):
        hit_days = [i for i, v in enumerate(de) if v == x]
        cur_gap, max_gap, mean_gap, median_gap = _gap_series(hit_days, n)
        rows_de.append(
            {
                "number": f"{x:02d}",
                "count": len(hit_days),
                "current_gap": cur_gap,
                "max_gap": max_gap,
                "mean_gap": mean_gap,
                "median_gap": median_gap,
                "last_seen": dates[hit_days[-1]].isoformat() if hit_days else None,
            }
        )
    de_df = pd.DataFrame(rows_de).sort_values(["current_gap", "max_gap"], ascending=[False, False])

    # LOTO: any 2-digit appearance in day
    cols = [c for c in df2.columns if c != "date"]
    loto_sets = [set(int(r[c]) for c in cols) for _, r in df2.iterrows()]
    rows_loto = []
    for x in range(100):
        hit_days = [i for i, s in enumerate(loto_sets) if x in s]
        cur_gap, max_gap, mean_gap, median_gap = _gap_series(hit_days, n)
        rows_loto.append(
            {
                "number": f"{x:02d}",
                "count": len(hit_days),
                "current_gap": cur_gap,
                "max_gap": max_gap,
                "mean_gap": mean_gap,
                "median_gap": median_gap,
                "last_seen": dates[hit_days[-1]].isoformat() if hit_days else None,
            }
        )
    loto_df = pd.DataFrame(rows_loto).sort_values(["count", "current_gap"], ascending=[False, False])

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    de_df.to_csv(out / "cycle_de.csv", index=False)
    loto_df.to_csv(out / "cycle_loto.csv", index=False)

    # Aggregates by head/tail/total (DE)
    def head(x: int) -> int:
        return x // 10

    def tail(x: int) -> int:
        return x % 10

    def total(x: int) -> int:
        return (x // 10 + x % 10) % 10

    agg_rows = []
    for name, fn, k in [("head", head, 10), ("tail", tail, 10), ("total", total, 10)]:
        for g in range(k):
            xs = [x for x in range(100) if fn(x) == g]
            # Use worst (max current_gap) as conservative metric
            sub = de_df[de_df["number"].isin([f"{x:02d}" for x in xs])]
            agg_rows.append(
                {
                    "group": name,
                    "value": g,
                    "max_current_gap": int(sub["current_gap"].max()),
                    "max_max_gap": int(sub["max_gap"].max()),
                    "mean_count": float(sub["count"].mean()),
                }
            )
    pd.DataFrame(agg_rows).to_csv(out / "cycle_de_groups.csv", index=False)

    print(f"Saved cycle tables to: {out.resolve()}")


if __name__ == "__main__":
    build_cycle_tables()
