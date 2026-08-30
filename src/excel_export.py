from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

logger = logging.getLogger(__name__)

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

PRIZE_GROUPS: list[tuple[str, list[str]]] = [
    ("Đặc biệt", ["special"]),
    ("Giải nhất", ["prize1"]),
    ("Giải nhì", ["prize2_1", "prize2_2"]),
    ("Giải ba", ["prize3_1", "prize3_2", "prize3_3", "prize3_4", "prize3_5", "prize3_6"]),
    ("Giải tư", ["prize4_1", "prize4_2", "prize4_3", "prize4_4"]),
    ("Giải năm", ["prize5_1", "prize5_2", "prize5_3", "prize5_4", "prize5_5", "prize5_6"]),
    ("Giải sáu", ["prize6_1", "prize6_2", "prize6_3"]),
    ("Giải bảy", ["prize7_1", "prize7_2", "prize7_3", "prize7_4"]),
]


def _fmt_date(v: object) -> str:
    return pd.to_datetime(v).date().isoformat()


def _fmt_prize(value: object, field: str) -> str:
    width = FIELD_WIDTHS[field]
    return str(int(value)).zfill(width)


def _format_raw_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "date" in out.columns:
        out["date"] = out["date"].apply(_fmt_date)
    for col, width in FIELD_WIDTHS.items():
        if col in out.columns:
            out[col] = out[col].apply(lambda v, w=width: str(int(v)).zfill(w))
    return out


def _format_two_digit_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "date" in out.columns:
        out["date"] = out["date"].apply(_fmt_date)
    for col in [c for c in out.columns if c != "date"]:
        out[col] = out[col].apply(lambda v: str(int(v) % 100).zfill(2))
    return out


def _write_df(ws, df: pd.DataFrame, *, freeze_row: int = 1) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True)
    text_align = Alignment(horizontal="center", vertical="center")

    for col_idx, col in enumerate(df.columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=str(col))
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = text_align

    for row_idx, row in enumerate(df.itertuples(index=False), start=2):
        for col_idx, value in enumerate(row, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if isinstance(value, str):
                cell.number_format = "@"
            cell.alignment = text_align

    ws.freeze_panes = f"A{freeze_row + 1}"
    ws.auto_filter.ref = ws.dimensions
    for col_idx, col in enumerate(df.columns, start=1):
        max_len = max([len(str(col)), *[len(str(v)) for v in df.iloc[:500, col_idx - 1].tolist()]]) if not df.empty else len(str(col))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(10, max_len + 2), 22)


def _save_workbook(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    from openpyxl import Workbook

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    # Remove default sheet after adding first real sheet.
    default = wb.active
    wb.remove(default)

    for name, df in sheets.items():
        ws = wb.create_sheet(title=name[:31])
        _write_df(ws, df)

    wb.save(path)


def _daily_loto_table(row: pd.Series) -> pd.DataFrame:
    values = [int(row[field]) % 100 for field in FIELD_WIDTHS]
    rows: list[dict[str, str]] = []
    for head in range(10):
        tails = sorted(v % 10 for v in values if v // 10 == head)
        rows.append({"Đầu": str(head), "Đuôi": ", ".join(str(t) for t in tails)})
    return pd.DataFrame(rows)


def _daily_prize_table(row: pd.Series) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    for label, fields in PRIZE_GROUPS:
        rows.append({"Giải": label, "Kết quả": ", ".join(_fmt_prize(row[f], f) for f in fields)})
    return pd.DataFrame(rows)


def _export_daily_files(raw_df: pd.DataFrame, out_dir: Path, *, latest_only: bool) -> None:
    if raw_df.empty:
        return

    view = raw_df.sort_values("date")
    if latest_only:
        view = view.tail(1)

    daily_dir = out_dir / "daily"
    if latest_only and daily_dir.exists():
        for old_file in daily_dir.glob("xsmb_*.xlsx"):
            old_file.unlink(missing_ok=True)
    for _, row in view.iterrows():
        d = _fmt_date(row["date"])
        _save_workbook(
            daily_dir / f"xsmb_{d}.xlsx",
            {
                "Ket qua": _daily_prize_table(row),
                "Lo to dau duoi": _daily_loto_table(row),
            },
        )


def export_excel_outputs(
    *,
    raw_df: pd.DataFrame,
    two_digit_df: pd.DataFrame,
    sparse_df: pd.DataFrame,
    data_dir: Path,
    latest_daily_only: bool = False,
) -> None:
    """Export Excel-friendly workbooks while preserving leading zeroes.

    All lottery code columns are written as text, not numbers, so Excel does not
    strip leading zeroes such as 00, 0023, 07177 or 08936.
    """
    try:
        import openpyxl  # noqa: F401
    except Exception as exc:  # pragma: no cover
        logger.warning("openpyxl is not available; skip Excel export: %s", exc)
        return

    excel_dir = data_dir / "excel"
    _save_workbook(excel_dir / "xsmb.xlsx", {"Raw": _format_raw_df(raw_df)})
    _save_workbook(excel_dir / "xsmb-2-digits.xlsx", {"TwoDigits": _format_two_digit_df(two_digit_df)})

    if not sparse_df.empty:
        sparse = sparse_df.copy()
        if "date" in sparse.columns:
            sparse["date"] = sparse["date"].apply(_fmt_date)
        _save_workbook(excel_dir / "xsmb-sparse.xlsx", {"Sparse": sparse})

    _export_daily_files(raw_df, excel_dir, latest_only=latest_daily_only)
