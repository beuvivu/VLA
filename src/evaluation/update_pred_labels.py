from __future__ import annotations

from evaluation.record_pred_history import write_history

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from core.xsmb_domain import PRIZE_FIELDS

logger = logging.getLogger(__name__)


PRIZE_COLS = list(PRIZE_FIELDS)


def _load_xsmb(xsmb_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(xsmb_csv)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _loto_set(row: pd.Series) -> set[int]:
    s: set[int] = set()
    for c in PRIZE_COLS:
        if c not in row or pd.isna(row[c]):
            continue
        try:
            v = int(row[c])
        except (TypeError, ValueError) as exc:
            logger.debug("Bỏ qua giá trị giải không hợp lệ tại %s: %r (%s)", c, row[c], exc)
            continue
        s.add(v % 100)
    return s


def main() -> None:
    ap = argparse.ArgumentParser(description="Fill y labels for recorded prediction history.")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--history-dir", default="data/evaluation/history")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    hist_dir = Path(args.history_dir)

    xsmb = _load_xsmb(data_dir / "xsmb.csv")
    last_date = xsmb["date"].max()
    lookup = xsmb.set_index("date")

    for mode in ["loto", "de"]:
        f = hist_dir / f"pred_{mode}.csv"
        if not f.exists():
            print(f"[SKIP] {f} not found")
            continue

        df = pd.read_csv(f)
        if "y" not in df.columns:
            df["y"] = np.nan

        df["_tdate"] = pd.to_datetime(df["target_date"]).dt.date
        need = df["y"].isna() & (df["_tdate"] <= last_date)
        if not need.any():
            df = df.drop(columns=["_tdate"])
            write_history(df, f)
            print(f"[OK] labels already up to date for {mode}")
            continue

        for tdate in sorted(df.loc[need, "_tdate"].unique()):
            if tdate not in lookup.index:
                continue
            row = lookup.loc[tdate]
            if mode == "de":
                y_true = int(row["special"]) % 100
                df.loc[df["_tdate"] == tdate, "y"] = (
                    df.loc[df["_tdate"] == tdate, "number"].astype(int) == y_true
                ).astype(int)
            else:
                s = _loto_set(row)
                df.loc[df["_tdate"] == tdate, "y"] = (
                    df.loc[df["_tdate"] == tdate, "number"].astype(int).isin(s)
                ).astype(int)

        df = df.drop(columns=["_tdate"])
        write_history(df, f)
        print(f"[OK] updated labels for {mode} history: {f}")


if __name__ == "__main__":
    main()
