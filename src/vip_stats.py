from __future__ import annotations

"""
VIP-style statistics inspired by common Vietnamese lottery analysis pages:
- Head table (Đầu 0..9 -> 00..09 counts) for a lookback window.
- "Gan" by sum group (tổng) and by digit touch (chạm), including for Đề (2 digits of special).
These are descriptive statistics only (no betting advice).

Sources of UI inspiration:
- Head-table layout (Đầu x … y lần). 
- rongbachkim shows "gan theo tổng" and "gan theo chạm". 
"""

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from lottery import Lottery


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _last_n_days(df_2d: pd.DataFrame, n: int) -> pd.DataFrame:
    df_2d = df_2d.sort_values("date").reset_index(drop=True)
    if n <= 0:
        return df_2d
    return df_2d.iloc[-n:].copy()


def head_table(df_2d: pd.DataFrame) -> pd.DataFrame:
    """
    Return a table:
      head, number, count
    where head in 0..9 and number in 00..99.
    """
    vals = df_2d.drop(columns=["date"]).to_numpy(dtype=int) % 100
    flat = vals.ravel()
    counts = np.bincount(flat, minlength=100)

    rows = []
    for head in range(10):
        for tail in range(10):
            num = head * 10 + tail
            rows.append({"head": head, "number": f"{num:02d}", "count": int(counts[num])})
    return pd.DataFrame(rows)


def _days_since_last_hit(series_days: list[date], hits_mask: np.ndarray) -> int | None:
    """
    hits_mask aligned with series_days; True means condition hit on that day.
    Return days since last hit (0 means hit on latest day). None if never.
    """
    idx = np.where(hits_mask)[0]
    if idx.size == 0:
        return None
    last_i = idx[-1]
    return (series_days[-1] - series_days[last_i]).days


def gap_by_sum_and_touch(df_2d: pd.DataFrame, *, mode: str = "loto") -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    mode:
      - loto: check any appearance in that day
      - de: only special %100
    """
    df_2d = df_2d.sort_values("date").reset_index(drop=True)
    days = [pd.to_datetime(x).to_pydatetime().date() for x in df_2d["date"]]

    if mode == "de":
        nums_by_day = [set([int(x) % 100]) for x in df_2d["special"].to_numpy(dtype=int)]
    else:
        vals = df_2d.drop(columns=["date"]).to_numpy(dtype=int) % 100
        nums_by_day = [set(map(int, row.tolist())) for row in vals]

    # Sum groups for 2-digit numbers: 0..18 (00..99)
    sum_rows = []
    for s in range(19):
        hits = np.array([any((n // 10 + n % 10) == s for n in nums) for nums in nums_by_day], dtype=bool)
        gap = _days_since_last_hit(days, hits)
        sum_rows.append({"sum": s, "gap_days": gap if gap is not None else -1})
    sum_df = pd.DataFrame(sum_rows).sort_values(["gap_days"], ascending=False)

    # Touch digits (chạm) 0..9: any number contains that digit (either head or tail)
    touch_rows = []
    for d in range(10):
        hits = np.array([any((n // 10) == d or (n % 10) == d for n in nums) for nums in nums_by_day], dtype=bool)
        gap = _days_since_last_hit(days, hits)
        touch_rows.append({"digit": d, "gap_days": gap if gap is not None else -1})
    touch_df = pd.DataFrame(touch_rows).sort_values(["gap_days"], ascending=False)

    return sum_df, touch_df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback-days", type=int, default=30, help="Window for head table counts")
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    df_2d = lot.get_2_digits_data()
    if df_2d.empty:
        raise SystemExit("No data loaded. Run src/sync.py first.")

    out_dir = Path("data") / "vip"
    _ensure_dir(out_dir)

    win = _last_n_days(df_2d, args.lookback_days)
    ht = head_table(win)
    ht.to_csv(out_dir / f"head_table_{args.lookback_days}d.csv", index=False)
    ht.to_json(out_dir / f"head_table_{args.lookback_days}d.json", orient="records", indent=2)

    for mode in ["loto", "de"]:
        sum_df, touch_df = gap_by_sum_and_touch(df_2d, mode=mode)
        sum_df.to_csv(out_dir / f"gap_sum_{mode}.csv", index=False)
        touch_df.to_csv(out_dir / f"gap_touch_{mode}.csv", index=False)

    print("Saved VIP stats under:", out_dir)


if __name__ == "__main__":
    main()
