from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


PRIZE_COLS = [
    "special","prize1",
    "prize2_1","prize2_2",
    "prize3_1","prize3_2","prize3_3","prize3_4","prize3_5","prize3_6",
    "prize4_1","prize4_2","prize4_3","prize4_4",
    "prize5_1","prize5_2","prize5_3","prize5_4","prize5_5","prize5_6",
    "prize6_1","prize6_2","prize6_3",
    "prize7_1","prize7_2","prize7_3","prize7_4",
]


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
        except Exception:
            continue
        s.add(v % 100)
    return s


def main() -> None:
    ap = argparse.ArgumentParser(description="Fill y labels for recorded prediction history.")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--history-dir", default="data/history")
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
            df.drop(columns=["_tdate"], inplace=True)
            df.to_csv(f, index=False)
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

        df.drop(columns=["_tdate"], inplace=True)
        df["y"] = df["y"].astype("Int64")
        df.to_csv(f, index=False)
        print(f"[OK] updated labels for {mode} history: {f}")


if __name__ == "__main__":
    main()
