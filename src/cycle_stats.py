from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from lottery import Lottery


def _gap_series_calendar(
    hit_dates: list[date],
    all_dates: list[date],
) -> tuple[int, int, float, float]:
    """Return absence gaps in real calendar days.

    ``current_gap`` is calendar days since the latest hit. ``max_gap`` includes
    the left/right boundary absence and completed between-hit absence segments.
    ``mean_gap``/``median_gap`` describe completed/boundary-left absence segments,
    preserving the historical cycle-table intent without treating missing rows as
    elapsed lottery days.
    """
    if not all_dates:
        return 0, 0, float("nan"), float("nan")
    if not hit_dates:
        span = (all_dates[-1] - all_dates[0]).days + 1
        return span, span, float("nan"), float("nan")

    hit_dates = sorted(hit_dates)
    leading = max(0, (hit_dates[0] - all_dates[0]).days)
    completed_absences = [
        max(0, (b - a).days - 1) for a, b in zip(hit_dates, hit_dates[1:])
    ]
    current_gap = max(0, (all_dates[-1] - hit_dates[-1]).days)
    observed = [leading, *completed_absences, current_gap]
    historical = [leading, *completed_absences]
    mean_gap = float(np.mean(historical)) if historical else float("nan")
    median_gap = float(np.median(historical)) if historical else float("nan")
    return int(current_gap), int(max(observed)), mean_gap, median_gap


def build_cycle_tables(out_dir: str = "data/cycle") -> None:
    lot = Lottery()
    lot.load()
    df2 = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    if df2.empty:
        raise SystemExit("No data available. Run src/sync.py first.")

    dates = [d.to_pydatetime().date() for d in pd.to_datetime(df2["date"])]

    # DE: 2 digits from special
    de = (df2["special"].astype(int) % 100).tolist()

    rows_de = []
    for x in range(100):
        hit_dates = [dates[i] for i, v in enumerate(de) if v == x]
        cur_gap, max_gap, mean_gap, median_gap = _gap_series_calendar(hit_dates, dates)
        rows_de.append(
            {
                "number": f"{x:02d}",
                "count": len(hit_dates),
                "current_gap": cur_gap,
                "max_gap": max_gap,
                "mean_gap": mean_gap,
                "median_gap": median_gap,
                "last_seen": hit_dates[-1].isoformat() if hit_dates else None,
                "gap_unit": "calendar_days_absent",
            }
        )
    de_df = pd.DataFrame(rows_de).sort_values(["current_gap", "max_gap"], ascending=[False, False])

    # LOTO: any 2-digit appearance in day
    cols = [c for c in df2.columns if c != "date"]
    loto_sets = [set(int(r[c]) for c in cols) for _, r in df2.iterrows()]
    rows_loto = []
    for x in range(100):
        hit_dates = [dates[i] for i, s in enumerate(loto_sets) if x in s]
        cur_gap, max_gap, mean_gap, median_gap = _gap_series_calendar(hit_dates, dates)
        rows_loto.append(
            {
                "number": f"{x:02d}",
                "count": len(hit_dates),
                "current_gap": cur_gap,
                "max_gap": max_gap,
                "mean_gap": mean_gap,
                "median_gap": median_gap,
                "last_seen": hit_dates[-1].isoformat() if hit_dates else None,
                "gap_unit": "calendar_days_absent",
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
            sub = de_df[de_df["number"].isin([f"{x:02d}" for x in xs])]
            agg_rows.append(
                {
                    "group": name,
                    "value": g,
                    "max_current_gap": int(sub["current_gap"].max()),
                    "max_max_gap": int(sub["max_gap"].max()),
                    "mean_count": float(sub["count"].mean()),
                    "gap_unit": "calendar_days_absent",
                }
            )
    pd.DataFrame(agg_rows).to_csv(out / "cycle_de_groups.csv", index=False)

    print(f"Saved cycle tables to: {out.resolve()}")


if __name__ == "__main__":
    build_cycle_tables()
