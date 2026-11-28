from __future__ import annotations

from core.lottery_codes import write_code_csv


import argparse
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from stats.frequency_stats import compute_frequency_stats
from stats.gap_cycle_stats import compute_gap_stats
from ingest.lottery import Lottery, RepoPaths


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdvancedOutputs:
    data_dir: Path

    @classmethod
    def from_paths(cls, paths: RepoPaths) -> AdvancedOutputs:
        return cls(data_dir=paths.data_dir / "stats" / "advanced")


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _as_of_date(df: pd.DataFrame) -> date:
    if df.empty:
        raise ValueError("Empty dataframe")
    return pd.to_datetime(df["date"]).max().to_pydatetime().date()


def _filter_last_days(df: pd.DataFrame, *, days: int) -> pd.DataFrame:
    if df.empty:
        return df
    last = pd.to_datetime(df["date"]).max()
    return df[(df["date"] > last - pd.Timedelta(days=days)) & (df["date"] <= last)].copy()


def _flatten_2d_values(two_digit_df: pd.DataFrame) -> np.ndarray:
    if two_digit_df.empty:
        return np.array([], dtype=np.int16)
    vals = (two_digit_df.drop(columns=["date"]).to_numpy(dtype=np.int16, copy=False) % 100).ravel()
    return vals


def _dump_table(df: pd.DataFrame, *, out_dir: Path, name: str) -> None:
    _ensure_dir(out_dir)
    write_code_csv(df, out_dir / f"{name}.csv", index=False)


def compute_frequency(sparse_df: pd.DataFrame, *, window_days: int) -> pd.DataFrame:
    if sparse_df.empty:
        return pd.DataFrame(columns=["value", "freq", "days_hit", "max_nhay"])
    target = pd.to_datetime(sparse_df["date"]).max().normalize() + pd.Timedelta(days=1)
    canonical = compute_frequency_stats(
        sparse_df, target, lookback_days=window_days
    )
    out = canonical.rename(
        columns={
            "number": "value",
            "occurrence_count": "freq",
            "draw_count": "days_hit",
            "max_occurrences_per_draw": "max_nhay",
        }
    )[["value", "freq", "days_hit", "max_nhay", "number_str"]].rename(
        columns={"number_str": "value_str"}
    )
    return out.sort_values(["freq", "days_hit"], ascending=False).reset_index(drop=True)


def compute_overdue(sparse_df: pd.DataFrame) -> pd.DataFrame:
    if sparse_df.empty:
        return pd.DataFrame(columns=["value", "last_seen", "days_since_last", "value_str"])
    target = pd.to_datetime(sparse_df["date"]).max().normalize() + pd.Timedelta(days=1)
    canonical = compute_gap_stats(sparse_df, target)
    out = canonical.rename(
        columns={
            "number": "value",
            "last_seen_date": "last_seen",
            "current_gap_calendar_days": "days_since_last",
            "number_str": "value_str",
        }
    )[["value", "last_seen", "days_since_last", "value_str"]]
    out.loc[out["last_seen"].isna(), "days_since_last"] = pd.NA
    out["days_since_last"] = out["days_since_last"].astype("Int64")
    return out.sort_values("days_since_last", ascending=False, na_position="last", kind="stable").reset_index(drop=True)


def compute_cycle_stats(sparse_df: pd.DataFrame, *, window_days: int = 365 * 2) -> pd.DataFrame:
    if sparse_df.empty:
        cols = ["value", "hits", "current_gap", "min_gap", "max_gap", "mean_gap"]
        return pd.DataFrame(columns=cols)
    target = pd.to_datetime(sparse_df["date"]).max().normalize() + pd.Timedelta(days=1)
    canonical = compute_gap_stats(
        sparse_df,
        target,
        lookback_days=window_days,
    )
    out = canonical.rename(
        columns={
            "number": "value",
            "hit_draws": "hits",
            "current_gap_draws": "current_gap",
            "minimum_interval_draws": "min_gap",
            "maximum_interval_draws": "max_gap",
            "mean_interval_draws": "mean_gap",
            "number_str": "value_str",
        }
    )[["value", "hits", "current_gap", "min_gap", "max_gap", "mean_gap", "value_str"]]
    return out.sort_values(["current_gap", "hits"], ascending=[False, True]).reset_index(drop=True)


def compute_daily_nhay_stats(sparse_df: pd.DataFrame, *, window_days: int = 365 * 2) -> pd.DataFrame:
    window = _filter_last_days(sparse_df, days=window_days)
    if window.empty:
        cols = ["value", "days_1", "days_2", "days_3", "days_4_plus", "max_nhay"]
        return pd.DataFrame(columns=cols)

    mat = window.drop(columns=["date"]).to_numpy(copy=False)
    rows: list[dict[str, int]] = []
    for n in range(100):
        col = mat[:, n]
        rows.append(
            {
                "value": n,
                "days_1": int(np.sum(col == 1)),
                "days_2": int(np.sum(col == 2)),
                "days_3": int(np.sum(col == 3)),
                "days_4_plus": int(np.sum(col >= 4)),
                "max_nhay": int(np.max(col)) if col.size else 0,
            }
        )

    out = pd.DataFrame(rows)
    out["value_str"] = out["value"].apply(lambda v: f"{int(v):02d}")
    return out.sort_values(["days_4_plus", "days_3", "days_2", "days_1"], ascending=False).reset_index(drop=True)


def compute_head_tail_total(two_digit_df: pd.DataFrame, *, window_days: int = 20) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    window = _filter_last_days(two_digit_df, days=window_days)
    values = _flatten_2d_values(window)
    if values.size == 0:
        empty = pd.DataFrame(columns=["value", "count"])
        return empty, empty, empty

    tens = values // 10
    ones = values % 10
    total = (tens + ones) % 10

    head = pd.Series(tens).value_counts().sort_index().reset_index()
    head.columns = ["head", "count"]

    tail = pd.Series(ones).value_counts().sort_index().reset_index()
    tail.columns = ["tail", "count"]

    tot = pd.Series(total).value_counts().sort_index().reset_index()
    tot.columns = ["total", "count"]

    return head, tail, tot


def compute_special_total_overdue(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if raw_df.empty:
        empty = pd.DataFrame(columns=["key", "last_seen", "days_since_last"])
        return empty, empty

    df = raw_df[["date", "special"]].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    as_of = df["date"].max()

    last2 = (df["special"].astype(int) % 100).astype(int)
    tens = last2 // 10
    ones = last2 % 10
    totals = (tens + ones) % 10

    total_rows: list[dict[str, object]] = []
    for t in range(10):
        mask = totals == t
        if mask.any():
            last_seen = df.loc[mask, "date"].max()
            days = int((as_of - last_seen).days)
            total_rows.append({"total": t, "last_seen": last_seen.date(), "days_since_last": days})
        else:
            total_rows.append({"total": t, "last_seen": None, "days_since_last": None})
    total_df = pd.DataFrame(total_rows).sort_values("days_since_last", ascending=False, na_position="last", kind="stable")

    cham_rows: list[dict[str, object]] = []
    for d in range(10):
        mask = (tens == d) | (ones == d)
        if mask.any():
            last_seen = df.loc[mask, "date"].max()
            days = int((as_of - last_seen).days)
            cham_rows.append({"digit": d, "last_seen": last_seen.date(), "days_since_last": days})
        else:
            cham_rows.append({"digit": d, "last_seen": None, "days_since_last": None})
    cham_df = pd.DataFrame(cham_rows).sort_values("days_since_last", ascending=False, na_position="last", kind="stable")

    return total_df.reset_index(drop=True), cham_df.reset_index(drop=True)


def compute_lo_roi(two_digit_df: pd.DataFrame, *, window_draws: int = 7) -> pd.DataFrame:
    if two_digit_df.empty:
        return pd.DataFrame(columns=["value", "count_in_window", "days_in_window"])

    df = two_digit_df.sort_values("date", kind="stable").tail(window_draws)
    flat = _flatten_2d_values(df)
    if flat.size == 0:
        return pd.DataFrame(columns=["value", "count_in_window", "days_in_window"])

    counts = np.bincount(flat, minlength=100)
    mat = df.drop(columns=["date"]).to_numpy(dtype=np.int16, copy=False) % 100
    days_in_window = np.zeros(100, dtype=int)
    for i in range(mat.shape[0]):
        days_in_window[np.unique(mat[i])] += 1

    out = pd.DataFrame(
        {
            "value": np.arange(100, dtype=int),
            "count_in_window": counts.astype(int),
            "days_in_window": days_in_window,
        }
    )
    out = out[out["count_in_window"] >= 2].copy()
    out["value_str"] = out["value"].apply(lambda v: f"{int(v):02d}")
    return out.sort_values(["count_in_window", "days_in_window"], ascending=False).reset_index(drop=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Generate advanced lottery statistics (XSMB).")
    parser.add_argument("--freq-days", type=int, default=99, help="Window (days) for frequency tables.")
    parser.add_argument("--headtail-days", type=int, default=20, help="Window (days) for head/tail/total.")
    parser.add_argument("--cycle-days", type=int, default=365 * 2, help="Window (days) for cycle/nháy stats.")
    parser.add_argument("--lo-roi-draws", type=int, default=7, help="Window (draws) for lo-rơi repeats.")
    parser.add_argument("--min-overdue", type=int, default=10, help="Threshold for overdue list (days).")
    args = parser.parse_args()

    lottery = Lottery()
    lottery.load()

    raw = lottery.get_raw_data()
    two = lottery.get_2_digits_data()
    sparse = lottery.get_sparse_data()
    if raw.empty or sparse.empty:
        logger.warning("No data found. Run src/ingest/sync.py first.")
        return

    paths = RepoPaths.from_module()
    out = AdvancedOutputs.from_paths(paths)
    _ensure_dir(out.data_dir)

    as_of = _as_of_date(raw)
    logger.info("Advanced stats as-of: %s", as_of)

    freq = compute_frequency(sparse, window_days=args.freq_days)
    _dump_table(freq, out_dir=out.data_dir, name=f"freq_{args.freq_days}d")

    overdue = compute_overdue(sparse)
    _dump_table(overdue, out_dir=out.data_dir, name="overdue")
    overdue_list = overdue[overdue["days_since_last"].fillna(-1).astype(int) >= args.min_overdue].copy()
    _dump_table(overdue_list, out_dir=out.data_dir, name=f"overdue_ge_{args.min_overdue}d")

    cycles = compute_cycle_stats(sparse, window_days=args.cycle_days)
    _dump_table(cycles, out_dir=out.data_dir, name=f"cycles_{args.cycle_days}d")

    nhay = compute_daily_nhay_stats(sparse, window_days=args.cycle_days)
    _dump_table(nhay, out_dir=out.data_dir, name=f"nhay_{args.cycle_days}d")

    head, tail, total = compute_head_tail_total(two, window_days=args.headtail_days)
    _dump_table(head, out_dir=out.data_dir, name=f"head_{args.headtail_days}d")
    _dump_table(tail, out_dir=out.data_dir, name=f"tail_{args.headtail_days}d")
    _dump_table(total, out_dir=out.data_dir, name=f"total_{args.headtail_days}d")

    total_db, cham_db = compute_special_total_overdue(raw)
    _dump_table(total_db, out_dir=out.data_dir, name="special_total_overdue")
    _dump_table(cham_db, out_dir=out.data_dir, name="special_cham_overdue")

    lo_roi = compute_lo_roi(two, window_draws=args.lo_roi_draws)
    _dump_table(lo_roi, out_dir=out.data_dir, name=f"lo_roi_last_{args.lo_roi_draws}_draws")

    logger.info("Done. Outputs: %s", out.data_dir)


if __name__ == "__main__":
    main()
