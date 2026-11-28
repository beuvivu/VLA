from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ingest.lottery import Lottery
from core.path_models import build_daily_targets


def _calendar_ordinals(df_2d: pd.DataFrame) -> np.ndarray:
    dates = pd.DatetimeIndex(pd.to_datetime(df_2d["date"]).dt.normalize())
    if len(dates) == 0:
        return np.zeros(0, dtype=np.int32)
    return np.asarray((dates - dates[0]).days, dtype=np.int32)


def hazard_curve_loto(df_2d: pd.DataFrame, max_gap: int = 60) -> pd.DataFrame:
    df_2d = df_2d.sort_values("date", kind="stable").reset_index(drop=True)
    _, loto_targets, _ = build_daily_targets(df_2d)
    ordinals = _calendar_ordinals(df_2d)
    n = len(loto_targets)
    if n == 0:
        return pd.DataFrame()

    max_gap = max(1, int(max_gap))
    last_seen = np.full(100, -1, dtype=np.int64)
    seen = np.zeros(100, dtype=bool)
    denom = np.zeros(max_gap + 1, dtype=np.int64)
    numer = np.zeros(max_gap + 1, dtype=np.int64)
    left_censored_risk = 0
    left_censored_hits = 0

    for t in range(n):
        day = int(ordinals[t])
        hit_mask = np.zeros(100, dtype=bool)
        for x in loto_targets[t]:
            hit_mask[int(x)] = True

        gaps = np.clip(day - last_seen, 0, max_gap).astype(np.int32)
        denom += np.bincount(gaps[seen], minlength=max_gap + 1)
        left_censored_risk += int((~seen).sum())

        hit_numbers = np.flatnonzero(hit_mask)
        if hit_numbers.size:
            observed = hit_numbers[seen[hit_numbers]]
            if observed.size:
                numer += np.bincount(gaps[observed], minlength=max_gap + 1)
            left_censored_hits += int(hit_numbers.size - observed.size)
            last_seen[hit_numbers] = day
            seen[hit_numbers] = True

    p = numer / np.maximum(denom, 1)
    out = pd.DataFrame(
        {
            "gap": np.arange(max_gap + 1),
            "denom": denom,
            "hits": numer,
            "hazard": p,
            "gap_unit": "calendar_days_since_previous_hit",
        }
    )
    out["censored_bucket"] = out["gap"] == max_gap
    out.attrs["left_censored_risk_days"] = left_censored_risk
    out.attrs["left_censored_hits"] = left_censored_hits
    return out


def hazard_curve_de(df_2d: pd.DataFrame, max_gap: int = 200) -> pd.DataFrame:
    df_2d = df_2d.sort_values("date", kind="stable").reset_index(drop=True)
    dates, _, de_targets = build_daily_targets(df_2d)
    ordinals = _calendar_ordinals(df_2d)
    n = len(dates)
    if n == 0:
        return pd.DataFrame()

    max_gap = max(1, int(max_gap))
    last_seen = np.full(100, -1, dtype=np.int64)
    seen = np.zeros(100, dtype=bool)
    denom = np.zeros(max_gap + 1, dtype=np.int64)
    numer = np.zeros(max_gap + 1, dtype=np.int64)
    left_censored_risk = 0
    left_censored_hits = 0

    for t in range(n):
        day = int(ordinals[t])
        x = int(de_targets[t])
        gaps = np.clip(day - last_seen, 0, max_gap).astype(np.int32)
        denom += np.bincount(gaps[seen], minlength=max_gap + 1)
        left_censored_risk += int((~seen).sum())
        if seen[x]:
            numer[int(gaps[x])] += 1
        else:
            left_censored_hits += 1
        last_seen[x] = day
        seen[x] = True

    p = numer / np.maximum(denom, 1)
    out = pd.DataFrame(
        {
            "gap": np.arange(max_gap + 1),
            "denom": denom,
            "hits": numer,
            "hazard": p,
            "gap_unit": "calendar_days_since_previous_hit",
        }
    )
    out["censored_bucket"] = out["gap"] == max_gap
    out.attrs["left_censored_risk_days"] = left_censored_risk
    out.attrs["left_censored_hits"] = left_censored_hits
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=str, default="data/stats/hazard")
    ap.add_argument("--max-gap-loto", type=int, default=60)
    ap.add_argument("--max-gap-de", type=int, default=200)
    args = ap.parse_args()

    lot = Lottery()
    lot.load()
    df_2d = lot.get_2_digits_data()
    if df_2d.empty:
        raise SystemExit("No data loaded. Run src/ingest/sync.py first.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    hazard_curve_loto(df_2d, max_gap=args.max_gap_loto).to_csv(out_dir / "hazard_loto.csv", index=False)
    hazard_curve_de(df_2d, max_gap=args.max_gap_de).to_csv(out_dir / "hazard_de.csv", index=False)
    print(f"Saved hazard curves to {out_dir}")


if __name__ == "__main__":
    main()
