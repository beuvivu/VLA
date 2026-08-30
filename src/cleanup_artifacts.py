from __future__ import annotations

import argparse
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def _latest_date(xsmb_csv: Path) -> date:
    df = pd.read_csv(xsmb_csv, usecols=["date"])
    if df.empty:
        raise ValueError(f"No rows in {xsmb_csv}")
    return pd.to_datetime(df["date"]).max().date()


def _prune_dated_files(directory: Path, cutoff: date) -> int:
    removed = 0
    if not directory.exists():
        return removed
    for path in directory.iterdir():
        if not path.is_file():
            continue
        match = DATE_RE.search(path.name)
        if not match:
            continue
        try:
            file_date = date.fromisoformat(match.group(1))
        except ValueError:
            continue
        if file_date < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def main() -> None:
    ap = argparse.ArgumentParser(description="Prune redundant dated GitHub artifacts while preserving compact history.")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--retention-days", type=int, default=45)
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    latest = _latest_date(data_dir / "xsmb.csv")
    cutoff = latest - timedelta(days=max(1, args.retention_days))

    removed = 0
    for rel in ["path_ui", "predict"]:
        removed += _prune_dated_files(data_dir / rel, cutoff)

    # Excel daily files are convenience exports; keep only the current one.
    daily_dir = data_dir / "excel" / "daily"
    if daily_dir.exists():
        for path in daily_dir.glob("xsmb_*.xlsx"):
            match = DATE_RE.search(path.name)
            if match and date.fromisoformat(match.group(1)) != latest:
                path.unlink(missing_ok=True)
                removed += 1

    print(f"[OK] artifact cleanup: latest={latest} cutoff={cutoff} removed={removed}")


if __name__ == "__main__":
    main()
