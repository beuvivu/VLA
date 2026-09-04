from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
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
        finite = pd.Series(np.isfinite(s.to_numpy(dtype=float)), index=s.index)
        integral = s.eq(np.trunc(s))
        bad = s.isna() | ~finite | ~integral | (s < 0) | (s >= 10**width)
        if bad.any():
            valid = s[~bad]
            issues.append(
                {
                    "column": col,
                    "reason": "out_of_range_non_integer_or_non_numeric",
                    "bad_count": int(bad.sum()),
                    "min": None if valid.empty else int(valid.min()),
                    "max": None if valid.empty else int(valid.max()),
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
        finite = pd.Series(np.isfinite(s.to_numpy(dtype=float)), index=s.index)
        valid = s.notna() & finite & s.eq(np.trunc(s)) & s.ge(0)
        rendered = s.where(valid).map(
            lambda value: "" if pd.isna(value) else str(int(value))
        )
        mask = valid & rendered.str.len().lt(width)
        if mask.any():
            first = df.loc[mask, ["date", col]].head(1).iloc[0]
            value = int(first[col])
            examples.append(
                {
                    "column": col,
                    "date": str(first["date"]),
                    "csv_value": value,
                    "excel_text": str(value).zfill(width),
                }
            )
    return examples


def _sparse_issues(
    data_dir: Path,
    *,
    expected_dates: set[object] | None = None,
) -> dict[str, Any]:
    sparse_path = data_dir / "xsmb-sparse.csv"
    if not sparse_path.exists():
        return {"ok": False, "reason": "missing xsmb-sparse.csv"}

    df = pd.read_csv(sparse_path)
    if "date" not in df.columns:
        return {"ok": False, "reason": "missing date column"}

    expected_number_columns = [str(number) for number in range(100)]
    actual_number_columns = [column for column in df.columns if column != "date"]
    missing_columns = sorted(
        set(expected_number_columns) - set(actual_number_columns), key=int
    )
    extra_columns = sorted(set(actual_number_columns) - set(expected_number_columns))

    present_columns = [
        column for column in expected_number_columns if column in df.columns
    ]
    values = df[present_columns].apply(pd.to_numeric, errors="coerce")
    matrix = values.to_numpy(dtype=float)
    invalid_values = (
        ~np.isfinite(matrix)
        | (matrix < 0)
        | (matrix != np.trunc(matrix))
    )
    bad_value_rows = pd.Series(invalid_values.any(axis=1), index=df.index)

    complete_schema = not missing_columns and not extra_columns
    if complete_schema:
        sums = values.sum(axis=1, min_count=len(expected_number_columns))
        bad_sum_rows = sums.ne(27) | bad_value_rows
    else:
        bad_sum_rows = pd.Series(True, index=df.index)

    raw_dates = df["date"].astype(str)
    canonical_date_format = raw_dates.str.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
    parsed_dates = pd.to_datetime(raw_dates, errors="coerce").dt.date
    invalid_date_rows = parsed_dates.isna() | ~canonical_date_format
    duplicate_dates = (
        parsed_dates[~invalid_date_rows & parsed_dates.duplicated(keep=False)]
        .astype(str)
        .drop_duplicates()
        .tolist()
    )

    observed_dates = set(parsed_dates[~invalid_date_rows].tolist())
    missing_dates: list[str] = []
    extra_dates: list[str] = []
    if expected_dates is not None:
        missing_dates = sorted(str(value) for value in expected_dates - observed_dates)
        extra_dates = sorted(str(value) for value in observed_dates - expected_dates)

    bad_rows = bad_sum_rows | bad_value_rows | invalid_date_rows
    ok = (
        complete_schema
        and not bad_rows.any()
        and not duplicate_dates
        and not missing_dates
        and not extra_dates
    )
    return {
        "ok": bool(ok),
        "rows": int(len(df)),
        "missing_number_columns": missing_columns,
        "extra_number_columns": extra_columns,
        "invalid_value_row_count": int(bad_value_rows.sum()),
        "invalid_date_row_count": int(invalid_date_rows.sum()),
        "duplicate_dates": duplicate_dates[:50],
        "missing_dates": missing_dates[:50],
        "extra_dates": extra_dates[:50],
        "bad_row_count": int(bad_rows.sum()),
        "expected_sum_per_draw": 27,
        "bad_dates": df.loc[bad_rows, "date"].astype(str).head(50).tolist(),
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
        raise SystemExit(2)

    df = pd.read_csv(xsmb)
    if "date" not in df.columns or df.empty:
        out = {"ok": False, "reason": "empty_or_missing_date"}
        _write(args.out, out)
        print("[FAIL]", out["reason"])
        raise SystemExit(2)

    raw_dates = df["date"].astype(str)
    canonical_date_format = raw_dates.str.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
    parsed_dates = pd.to_datetime(raw_dates, errors="coerce")
    invalid_dates = parsed_dates.isna() | ~canonical_date_format
    if invalid_dates.any():
        out = {
            "ok": False,
            "reason": "invalid_or_noncanonical_date",
            "invalid_date_count": int(invalid_dates.sum()),
            "invalid_date_values": raw_dates[invalid_dates].head(50).tolist(),
        }
        _write(args.out, out)
        print("[FAIL]", out["reason"])
        raise SystemExit(2)

    df["date"] = parsed_dates.dt.date
    last = df["date"].max()
    first = df["date"].min()
    start = last - timedelta(days=int(args.lookback_days))

    missing = _missing_dates(df["date"], start=start, end=last)
    full_missing = _missing_dates(df["date"], start=first, end=last)
    duplicate_dates = df["date"][df["date"].duplicated()].astype(str).tolist()

    range_issues = _range_issues(df)
    sparse = _sparse_issues(data_dir, expected_dates=set(df["date"].tolist()))
    zero_examples = _leading_zero_examples(df)

    ok = (
        len(full_missing) == 0
        and not duplicate_dates
        and not range_issues
        and bool(sparse.get("ok", False))
    )
    out = {
        "ok": ok,
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
        "calendar_contiguous_required": True,
        "excel_note": "Use data/excel/*.xlsx for Excel consumption; lottery codes are written as text to preserve leading zeroes.",
    }
    _write(args.out, out)
    print("[OK]" if out["ok"] else "[FAIL]", "health written to", args.out)
    if not out["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
