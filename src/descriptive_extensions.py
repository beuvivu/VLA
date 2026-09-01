from __future__ import annotations

"""Extended descriptive statistics preserved from the legacy repositories.

The outputs are intentionally descriptive. They provide user-facing recency,
head-table, sum/touch gap and pair evidence without feeding any score directly
into the production predictor. Any artifact labeled in ``days`` uses real
calendar dates; draw-index intervals remain explicitly labeled ``*_draws``.
"""

import argparse
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from lottery import Lottery
from number_reference import digit_sum, digit_sum_mod10


def _date_series(two: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(two["date"]).reset_index(drop=True)


def _presence_sets(two: pd.DataFrame) -> list[set[int]]:
    values = two.drop(columns=["date"]).to_numpy(dtype=int) % 100
    return [set(map(int, row)) for row in values]


def _de_values(two: pd.DataFrame) -> np.ndarray:
    return (two["special"].to_numpy(dtype=int) % 100).astype(int)


def build_head_table(two: pd.DataFrame, *, lookback_days: int) -> pd.DataFrame:
    """Count 00..99 occurrences inside an inclusive calendar-day window."""
    if two.empty or "date" not in two.columns:
        raise ValueError("head table requires non-empty data with a date column")
    days = max(1, int(lookback_days))
    work = two.copy()
    work["date"] = pd.to_datetime(work["date"]).dt.normalize()
    latest = work["date"].max()
    start = latest - pd.Timedelta(days=days - 1)
    view = work[(work["date"] >= start) & (work["date"] <= latest)]
    flat = (view.drop(columns=["date"]).to_numpy(dtype=int) % 100).ravel()
    counts = np.bincount(flat, minlength=100)
    return pd.DataFrame(
        {
            "lookback_days": days,
            "window_start": start.date().isoformat(),
            "window_end": latest.date().isoformat(),
            "draw_rows": int(len(view)),
            "head": np.repeat(np.arange(10), 10),
            "number": np.arange(100),
            "number_str": [f"{n:02d}" for n in range(100)],
            "count": counts,
        }
    )


def _group_gap_rows(
    two: pd.DataFrame, *, mode: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = _date_series(two)
    if mode == "de":
        day_sets = [{int(x)} for x in _de_values(two)]
    elif mode == "loto":
        day_sets = _presence_sets(two)
    else:
        raise ValueError("mode must be loto or de")

    latest = dates.iloc[-1]

    def gap_for(predicate) -> tuple[int, str | None, int]:
        idx = [
            i
            for i, nums in enumerate(day_sets)
            if any(predicate(n) for n in nums)
        ]
        if not idx:
            return int((latest - dates.iloc[0]).days) + 1, None, 0
        last_i = idx[-1]
        return (
            int((latest - dates.iloc[last_i]).days),
            dates.iloc[last_i].date().isoformat(),
            len(idx),
        )

    sum_rows: list[dict[str, object]] = []
    for total in range(19):
        gap, last_date, hits = gap_for(
            lambda n, total=total: digit_sum(n) == total
        )
        sum_rows.append(
            {
                "mode": mode,
                "digit_sum": total,
                "gap_days": gap,
                "last_date": last_date,
                "hit_days": hits,
            }
        )

    mod_rows: list[dict[str, object]] = []
    for total in range(10):
        gap, last_date, hits = gap_for(
            lambda n, total=total: digit_sum_mod10(n) == total
        )
        mod_rows.append(
            {
                "mode": mode,
                "sum_mod10": total,
                "gap_days": gap,
                "last_date": last_date,
                "hit_days": hits,
            }
        )

    touch_rows: list[dict[str, object]] = []
    for d in range(10):
        gap, last_date, hits = gap_for(
            lambda n, d=d: d in (n // 10, n % 10)
        )
        touch_rows.append(
            {
                "mode": mode,
                "digit": d,
                "gap_days": gap,
                "last_date": last_date,
                "hit_days": hits,
            }
        )

    return (
        pd.DataFrame(sum_rows).sort_values(
            "gap_days", ascending=False, ignore_index=True
        ),
        pd.DataFrame(mod_rows).sort_values(
            "gap_days", ascending=False, ignore_index=True
        ),
        pd.DataFrame(touch_rows).sort_values(
            "gap_days", ascending=False, ignore_index=True
        ),
    )


def build_number_recency(
    two: pd.DataFrame, *, mode: str, recent_dates: int = 8
) -> pd.DataFrame:
    dates = _date_series(two)
    latest = dates.iloc[-1]
    if mode == "de":
        day_sets = [{int(x)} for x in _de_values(two)]
    elif mode == "loto":
        day_sets = _presence_sets(two)
    else:
        raise ValueError("mode must be loto or de")

    appearances: list[list[int]] = [[] for _ in range(100)]
    for i, nums in enumerate(day_sets):
        for n in nums:
            appearances[n].append(i)

    rows: list[dict[str, object]] = []
    for n, idx in enumerate(appearances):
        if idx:
            intervals = np.diff(idx).astype(float)
            last_i = idx[-1]
            recent = [
                dates.iloc[i].date().isoformat()
                for i in idx[-recent_dates:][::-1]
            ]
            mean_interval = float(intervals.mean()) if intervals.size else None
            median_interval = (
                float(np.median(intervals)) if intervals.size else None
            )
            last_date = dates.iloc[last_i].date().isoformat()
            days_since = int((latest - dates.iloc[last_i]).days)
        else:
            recent = []
            mean_interval = median_interval = None
            last_date = None
            days_since = int((latest - dates.iloc[0]).days) + 1
        rows.append(
            {
                "mode": mode,
                "number": n,
                "number_str": f"{n:02d}",
                "hit_days": len(idx),
                "last_date": last_date,
                "days_since": days_since,
                "mean_interval_draws": mean_interval,
                "median_interval_draws": median_interval,
                "recent_dates": json.dumps(recent, ensure_ascii=False),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["days_since", "hit_days"],
        ascending=[False, False],
        ignore_index=True,
    )


def build_pair_recency(
    two: pd.DataFrame, *, top: int = 300, recent_dates: int = 6
) -> pd.DataFrame:
    dates = _date_series(two)
    sets = _presence_sets(two)
    n_days = len(sets)
    single = np.zeros(100, dtype=int)
    pair_count: dict[tuple[int, int], int] = defaultdict(int)
    pair_dates: dict[tuple[int, int], list[int]] = defaultdict(list)

    for i, nums in enumerate(sets):
        ordered = sorted(nums)
        single[ordered] += 1
        for a, b in combinations(ordered, 2):
            pair_count[(a, b)] += 1
            pair_dates[(a, b)].append(i)

    rows: list[dict[str, object]] = []
    for (a, b), count in pair_count.items():
        pa = single[a] / max(n_days, 1)
        pb = single[b] / max(n_days, 1)
        observed = count / max(n_days, 1)
        expected = pa * pb
        lift = observed / expected if expected > 0 else 0.0
        idx = pair_dates[(a, b)]
        last_i = idx[-1]
        rows.append(
            {
                "a": a,
                "a_str": f"{a:02d}",
                "b": b,
                "b_str": f"{b:02d}",
                "cooccurrence_days": count,
                "support": observed,
                "independence_expected": expected,
                "lift": lift,
                "last_date": dates.iloc[last_i].date().isoformat(),
                "days_since": int(
                    (dates.iloc[-1] - dates.iloc[last_i]).days
                ),
                "recent_dates": json.dumps(
                    [
                        dates.iloc[j].date().isoformat()
                        for j in idx[-recent_dates:][::-1]
                    ],
                    ensure_ascii=False,
                ),
            }
        )

    if not rows:
        return pd.DataFrame()
    return (
        pd.DataFrame(rows)
        .sort_values(
            ["lift", "cooccurrence_days"], ascending=[False, False]
        )
        .head(top)
        .reset_index(drop=True)
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Extended descriptive/recency statistics."
    )
    ap.add_argument("--out-dir", default="data/descriptive_ext")
    ap.add_argument("--head-windows", default="30,90,365")
    ap.add_argument("--pair-top", type=int, default=300)
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    two = lot.get_2_digits_data().sort_values("date").reset_index(drop=True)
    if two.empty:
        raise SystemExit("No data loaded")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    windows = sorted(
        {
            max(1, int(x))
            for x in args.head_windows.split(",")
            if x.strip()
        }
    )
    for window in windows:
        build_head_table(two, lookback_days=window).to_csv(
            out / f"head_table_{window}d.csv", index=False
        )

    for mode in ("loto", "de"):
        raw_sum, mod_sum, touch = _group_gap_rows(two, mode=mode)
        raw_sum.to_csv(out / f"gap_digit_sum_{mode}.csv", index=False)
        mod_sum.to_csv(out / f"gap_sum_mod10_{mode}.csv", index=False)
        touch.to_csv(out / f"gap_touch_{mode}.csv", index=False)
        recency = build_number_recency(two, mode=mode)
        recency.to_csv(out / f"number_recency_{mode}.csv", index=False)

    pairs = build_pair_recency(two, top=max(10, args.pair_top))
    pairs.to_csv(out / "pair_recency_loto.csv", index=False)

    manifest = {
        "latest_date": pd.to_datetime(two["date"]).max().date().isoformat(),
        "draw_days": int(len(two)),
        "head_windows": windows,
        "head_window_semantics": "inclusive calendar-day windows",
        "pair_rows": int(len(pairs)),
        "note": (
            "Descriptive evidence only; these outputs do not alter production "
            "prediction weights."
        ),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] descriptive extensions -> {out}")


if __name__ == "__main__":
    main()
