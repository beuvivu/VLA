from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

FIELD_WIDTHS: dict[str, int] = {
    "special": 5,
    "prize1": 5,
    "prize2_1": 5,
    "prize2_2": 5,
    "prize3_1": 5,
    "prize3_2": 5,
    "prize3_3": 5,
    "prize3_4": 5,
    "prize3_5": 5,
    "prize3_6": 5,
    "prize4_1": 4,
    "prize4_2": 4,
    "prize4_3": 4,
    "prize4_4": 4,
    "prize5_1": 4,
    "prize5_2": 4,
    "prize5_3": 4,
    "prize5_4": 4,
    "prize5_5": 4,
    "prize5_6": 4,
    "prize6_1": 3,
    "prize6_2": 3,
    "prize6_3": 3,
    "prize7_1": 2,
    "prize7_2": 2,
    "prize7_3": 2,
    "prize7_4": 2,
}


def _write(out_path: str, payload: dict[str, Any]) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _missing_dates(dates: pd.Series, *, start, end) -> list[str]:
    expected = pd.date_range(start=start, end=end, freq="D").date
    have = set(dates.tolist())
    return [d.isoformat() for d in expected if d not in have]


def _range_issues(df: pd.DataFrame) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for col, width in FIELD_WIDTHS.items():
        if col not in df.columns:
            issues.append({"column": col, "reason": "missing_column"})
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        bad = s.isna() | (s < 0) | (s >= 10**width)
        if bad.any():
            issues.append(
                {
                    "column": col,
                    "reason": "out_of_range_or_non_numeric",
                    "bad_count": int(bad.sum()),
                    "min": None if s.dropna().empty else int(s.min()),
                    "max": None if s.dropna().empty else int(s.max()),
                    "expected_width": width,
                }
            )
    return issues


def _leading_zero_examples(df: pd.DataFrame) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for col, width in FIELD_WIDTHS.items():
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        mask = s.notna() & (s.astype(int).astype(str).str.len() < width)
        if mask.any():
            first = df.loc[mask, ["date", col]].head(1).iloc[0]
            value = int(first[col])
            examples.append({"column": col, "date": str(first["date"]), "csv_value": value, "excel_text": str(value).zfill(width)})
    return examples


def _sparse_issues(data_dir: Path) -> dict[str, Any]:
    sparse_path = data_dir / "xsmb-sparse.csv"
    if not sparse_path.exists():
        return {"ok": False, "reason": "missing xsmb-sparse.csv"}

    df = pd.read_csv(sparse_path)
    if "date" not in df.columns:
        return {"ok": False, "reason": "missing date column"}

    sums = df.drop(columns=["date"]).sum(axis=1)
    bad = sums != 27
    return {
        "ok": bool(not bad.any()),
        "rows": int(len(df)),
        "bad_row_count": int(bad.sum()),
        "expected_sum_per_draw": 27,
        "bad_dates": df.loc[bad, "date"].astype(str).head(50).tolist(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate data completeness, recency, schema, and Excel-readiness.")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--lookback-days", type=int, default=60)
    ap.add_argument("--out", default="data/health.json")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    xsmb = data_dir / "xsmb.csv"
    if not xsmb.exists():
        out = {"ok": False, "reason": "missing xsmb.csv"}
        _write(args.out, out)
        print("[FAIL] xsmb.csv missing")
        return

    df = pd.read_csv(xsmb)
    if "date" not in df.columns or df.empty:
        out = {"ok": False, "reason": "empty_or_missing_date"}
        _write(args.out, out)
        print("[FAIL]", out["reason"])
        return

    df["date"] = pd.to_datetime(df["date"]).dt.date
    last = df["date"].max()
    first = df["date"].min()
    start = last - timedelta(days=int(args.lookback_days))

    missing = _missing_dates(df["date"], start=start, end=last)
    full_missing = _missing_dates(df["date"], start=first, end=last)
    duplicate_dates = df["date"][df["date"].duplicated()].astype(str).tolist()

    range_issues = _range_issues(df)
    sparse = _sparse_issues(data_dir)
    zero_examples = _leading_zero_examples(df)

    out = {
        "ok": len(missing) == 0 and not duplicate_dates and not range_issues and bool(sparse.get("ok", False)),
        "latest_date": last.isoformat(),
        "last_date": last.isoformat(),
        "first_date": first.isoformat(),
        "row_count": int(len(df)),
        "lookback_days": int(args.lookback_days),
        "missing_count": len(missing),
        "missing_dates": missing[:200],
        "full_missing_count": len(full_missing),
        "full_missing_dates": full_missing[:500],
        "duplicate_dates": duplicate_dates[:200],
        "range_issues": range_issues,
        "sparse_check": sparse,
        "leading_zero_examples": zero_examples[:50],
        "excel_note": "Use data/excel/*.xlsx for Excel consumption; lottery codes are written as text to preserve leading zeroes.",
    }
    _write(args.out, out)
    print("[OK]" if out["ok"] else "[WARN]", "health written to", args.out)


if __name__ == "__main__":
    main()
