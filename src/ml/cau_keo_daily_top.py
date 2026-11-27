from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

from core.safe_io import read_csv_or_empty
from core.paths import REPO_ROOT

MODES = ("de", "loto")
TOP = 10
DAILY_DIR = Path("ai_ml") / "daily"
FIELDS = ["predict_for_date", "rank", "number", "cau_score", "prob"]


def top_by_cau_score(df: pd.DataFrame, limit: int = TOP) -> pd.DataFrame:
    if df.empty or "cau_score" not in df.columns:
        return pd.DataFrame()
    score = pd.to_numeric(df["cau_score"], errors="coerce").fillna(0.0)
    order = score.sort_values(ascending=False, kind="mergesort").index
    return df.loc[order].head(limit)


def daily_path(data_dir: Path, mode: str, day: str) -> Path:
    return data_dir / DAILY_DIR / f"cau_keo_{mode}_top{TOP}_{day}.csv"


def write_daily_top(data_dir: Path, mode: str) -> Path | None:
    table = read_csv_or_empty(
        data_dir / "ai_ml" / f"cau_keo_{mode}_top20.csv",
        dtype={"number_str": str, "predict_for_date": str},
    )
    if table.empty or "predict_for_date" not in table.columns:
        return None
    days = {str(v)[:10] for v in table["predict_for_date"].dropna()}
    if len(days) != 1:
        raise ValueError(f"cau_keo_{mode}_top20.csv nhắm nhiều ngày: {sorted(days)}")
    (day,) = days
    top = top_by_cau_score(table)
    path = daily_path(data_dir, mode, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for rank, row in enumerate(top.to_dict("records"), 1):
            writer.writerow({
                "predict_for_date": day,
                "rank": rank,
                "number": f"{int(row['number_str']):02d}",
                "cau_score": row["cau_score"],
                "prob": row.get("prob", ""),
            })
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    args = parser.parse_args()
    for mode in MODES:
        path = write_daily_top(Path(args.data_dir), mode)
        print(f"{mode}: {path if path else 'chưa có bảng cầu-kèo'}")


if __name__ == "__main__":
    main()
