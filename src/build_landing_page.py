from __future__ import annotations

"""Build the modern Vietnamese lottery landing page.

The landing page is intentionally self-contained: it embeds the latest draw,
statistical matrices, AI/ML ranking, and cầu-position evidence into one HTML
file so docs/index.html still works when opened directly from disk.
"""

import argparse
import html
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from ui_locale import COLUMN_LABELS, GROUP_LABELS, mode_label, value_label


NAV_ITEMS: list[tuple[str, str, str]] = [
    ("tong-quan", "Tổng quan", "Cập nhật, tín hiệu nóng và đường dẫn nhanh"),
    ("ket-qua", "Kết quả ngày", "Bảng kết quả đầy đủ theo giải"),
    ("chuc-don-vi", "Chục × đơn vị", "Ma trận đầu/chục và đuôi/đơn vị"),
    ("ai-ml", "AI/ML cầu-kèo", "Xếp hạng xác suất và lý do thống kê"),
    ("tan-suat-loto", "Tần suất loto", "Ma trận ngày, tuần, tháng, năm"),
    ("tan-suat-de", "Tần suất ĐB", "Ma trận đặc biệt theo kỳ"),
    ("gan-nhip", "Gan / nhịp", "Số lâu chưa về và áp lực nhịp"),
    ("cap-lon", "Cặp lộn", "Cặp đảo chiều cùng tần suất"),
    ("dau-duoi-tong", "Đầu · đuôi · tổng", "Phân bổ nhóm số dễ so sánh"),
    ("db-tuan-thang", "ĐB tuần/tháng", "Bảng đặc biệt theo lịch"),
    ("duong-cau", "Vị trí đường cầu", "Căn cứ khi bấm vào từng số"),
    ("backtest", "Kiểm định AI/ML", "Kiểm định lại tín hiệu trên lịch sử"),
]

PRIZE_GROUPS: list[tuple[str, str, list[str], str]] = [
    ("special", "Đặc biệt", ["special"], "special"),
    ("prize1", "Giải nhất", ["prize1"], "normal"),
    ("prize2", "Giải nhì", ["prize2_1", "prize2_2"], "normal"),
    (
        "prize3",
        "Giải ba",
        ["prize3_1", "prize3_2", "prize3_3", "prize3_4", "prize3_5", "prize3_6"],
        "normal",
    ),
    ("prize4", "Giải tư", ["prize4_1", "prize4_2", "prize4_3", "prize4_4"], "compact"),
    (
        "prize5",
        "Giải năm",
        ["prize5_1", "prize5_2", "prize5_3", "prize5_4", "prize5_5", "prize5_6"],
        "compact",
    ),
    ("prize6", "Giải sáu", ["prize6_1", "prize6_2", "prize6_3"], "compact"),
    ("prize7", "Giải bảy", ["prize7_1", "prize7_2", "prize7_3", "prize7_4"], "mini"),
]

PRETTY_COLS = COLUMN_LABELS

PALETTES = {
    "blue": ("#eff6ff", "#2563eb"),
    "sky": ("#ecfeff", "#0891b2"),
    "purple": ("#f5f3ff", "#7c3aed"),
    "orange": ("#fff7ed", "#ea580c"),
    "rose": ("#fff1f2", "#e11d48"),
    "green": ("#ecfdf5", "#059669"),
    "slate": ("#f8fafc", "#334155"),
}


def _read_csv(
    path: Path,
    *,
    dtype: str | Mapping[str, object] | None = None,
    nrows: int | None = None,
) -> pd.DataFrame:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame()
        return pd.read_csv(path, dtype=dtype, nrows=nrows, keep_default_na=False)
    except Exception:
        return pd.DataFrame()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        x = float(value)
        if np.isfinite(x):
            return x
    except Exception:
        pass
    return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _fmt2(value: Any) -> str:
    try:
        return f"{int(float(value)):02d}"
    except Exception:
        s = str(value).strip()
        if not s:
            return ""
        digits = re.sub(r"\D+", "", s)
        return digits[-2:].zfill(2) if digits else s


def _fmt_num(value: Any, *, decimals: int = 0, percent: bool = False) -> str:
    if value is None or value == "":
        return ""
    x = _to_float(value, default=np.nan)
    if not np.isfinite(x):
        return html.escape(str(value))
    if percent:
        return f"{x * 100:.1f}%"
    if decimals <= 0:
        return f"{int(round(x)):,}".replace(",", ".")
    return f"{x:.{decimals}f}".rstrip("0").rstrip(".")


def _pct(value: Any) -> str:
    x = _to_float(value, default=0.0)
    if x <= 1:
        x *= 100
    return f"{x:.1f}%"


def _pretty_col(col: str) -> str:
    return PRETTY_COLS.get(col, col.replace("_", " "))


def _prize_width(col: str) -> int:
    if col == "special" or col == "prize1" or col.startswith("prize2") or col.startswith("prize3"):
        return 5
    if col.startswith("prize4") or col.startswith("prize5"):
        return 4
    if col.startswith("prize6"):
        return 3
    if col.startswith("prize7"):
        return 2
    return 2


def _fmt_prize(col: str, value: Any) -> str:
    s = str(value).strip()
    if not s:
        return ""
    digits = re.sub(r"\D+", "", s)
    if not digits:
        return html.escape(s)
    return digits.zfill(_prize_width(col))


def _last2_from_prize(col: str, value: Any) -> str:
    s = _fmt_prize(col, value)
    digits = re.sub(r"\D+", "", s)
    return digits[-2:].zfill(2) if digits else ""


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    color = hex_color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hex(rgb: Iterable[int]) -> str:
    return "#" + "".join(f"{max(0, min(255, int(v))):02x}" for v in rgb)


def _mix(low: str, high: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    a = _hex_to_rgb(low)
    b = _hex_to_rgb(high)
    return _rgb_to_hex(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _luminance(hex_color: str) -> float:
    rgb = [v / 255 for v in _hex_to_rgb(hex_color)]

    def linear(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = [linear(c) for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _style_for_value(value: float, min_value: float, max_value: float, palette: str) -> tuple[str, str]:
    low, high = PALETTES.get(palette, PALETTES["blue"])
    span = max(max_value - min_value, 1e-9)
    t = (value - min_value) / span
    bg = _mix(low, high, t)
    fg = "#ffffff" if _luminance(bg) < 0.42 else "#0f172a"
    return bg, fg


def _df_to_rows(df: pd.DataFrame, columns: Sequence[str], limit: int = 12) -> list[dict[str, Any]]:
    if df.empty:
        return []
    cols = [c for c in columns if c in df.columns]
    if not cols:
        cols = list(df.columns[: min(6, len(df.columns))])
    out = df.loc[:, cols].head(limit).copy()
    return out.to_dict(orient="records")


def _latest_draw(repo_root: Path) -> dict[str, Any]:
    df = _read_csv(repo_root / "data" / "xsmb.csv", dtype=str)
    if df.empty:
        return {"date": "", "groups": [], "numbers": [], "counts": {}}
    df = df.sort_values("date")
    row = df.iloc[-1].to_dict()
    groups = []
    numbers: list[str] = []
    for key, label, cols, kind in PRIZE_GROUPS:
        values = [_fmt_prize(c, row.get(c, "")) for c in cols if str(row.get(c, "")).strip()]
        groups.append({"key": key, "label": label, "values": values, "kind": kind})
        for c in cols:
            n = _last2_from_prize(c, row.get(c, ""))
            if n:
                numbers.append(n)
    counts = dict(Counter(numbers))
    heads: dict[str, list[str]] = {str(i): [] for i in range(10)}
    tails: dict[str, list[str]] = {str(i): [] for i in range(10)}
    for number, count in sorted(counts.items()):
        label = number if count == 1 else f"{number}×{count}"
        heads[number[0]].append(label)
        tails[number[1]].append(label)
    return {
        "date": row.get("date", ""),
        "special": _fmt_prize("special", row.get("special", "")),
        "special_2d": _last2_from_prize("special", row.get("special", "")),
        "groups": groups,
        "numbers": numbers,
        "counts": counts,
        "heads": heads,
        "tails": tails,
    }


def _matrix_from_df(df: pd.DataFrame, value_col: str) -> dict[str, float]:
    values = {f"{i:02d}": 0.0 for i in range(100)}
    if df.empty or value_col not in df.columns:
        return values
    for _, row in df.iterrows():
        if "number_str" in df.columns:
            n = _fmt2(row["number_str"])
        elif "number" in df.columns:
            n = _fmt2(row["number"])
        else:
            continue
        values[n] = _to_float(row.get(value_col, 0))
    return values


def _current_period_matrix(repo_root: Path, mode: str, period: str, value_col: str = "freq") -> dict[str, float]:
    df = _read_csv(repo_root / "data" / "advanced" / f"period_snapshot_{mode}_current.csv", dtype=str)
    if not df.empty and "period_kind" in df.columns:
        df = df[df["period_kind"] == period]
    return _matrix_from_df(df, value_col)


def _rhythm_matrix(repo_root: Path, mode: str) -> dict[str, float]:
    df = _read_csv(repo_root / "data" / "advanced" / f"{mode}_rhythm.csv", dtype=str)
    return _matrix_from_df(df, "current_gap")


def _ai_matrix(repo_root: Path, mode: str) -> dict[str, float]:
    explain = _read_csv(repo_root / "data" / "ai_ml" / f"cau_number_explain_{mode}.csv", dtype=str)
    if not explain.empty and "ai_cau_score" in explain.columns:
        return _matrix_from_df(explain, "ai_cau_score")
    top = _read_csv(repo_root / "data" / "ai_ml" / f"cau_keo_{mode}_top20.csv", dtype=str)
    if not top.empty and "cau_score" in top.columns:
        return _matrix_from_df(top, "cau_score")
    fallback = _read_csv(repo_root / "data" / "advanced" / f"ai_ml_signal_{mode}.csv", dtype=str)
    return _matrix_from_df(fallback, "prob")


def _sort_top(df: pd.DataFrame, col: str, limit: int = 12, ascending: bool = False) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    out["_sort_value"] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    out = out.sort_values("_sort_value", ascending=ascending).drop(columns=["_sort_value"])
    return out.head(limit)


def _load_explain_map(repo_root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {"loto": {}, "de": {}}
    for mode in ["loto", "de"]:
        explain = _read_csv(repo_root / "data" / "ai_ml" / f"cau_number_explain_{mode}.csv", dtype=str)
        if not explain.empty:
            for _, row in explain.iterrows():
                number = _fmt2(row.get("number_str", row.get("number", "")))
                result[mode][number] = {
                    "number": number,
                    "score": _to_float(row.get("ai_cau_score", 0)),
                    "prob": _to_float(row.get("ai_prob_percent", 0)),
                    "reason": str(row.get("primary_reason", "")),
                    "evidence": str(row.get("ai_evidence", "")),
                    "summary": str(row.get("explain_text", "")),
                    "positions": [
                        str(row.get("top_position_1", "")),
                        str(row.get("top_position_2", "")),
                        str(row.get("top_position_3", "")),
                    ],
                    "lines": [],
                }
        evidence = _read_csv(repo_root / "data" / "ai_ml" / f"cau_position_evidence_{mode}.csv", dtype=str)
        if not evidence.empty:
            sort_cols = [c for c in ["number_str", "rule_score"] if c in evidence.columns]
            if sort_cols:
                evidence["_score"] = pd.to_numeric(evidence.get("rule_score", 0), errors="coerce").fillna(0)
                evidence = evidence.sort_values(["number_str", "_score"], ascending=[True, False]).drop(columns=["_score"])
            for number, group in evidence.groupby(evidence["number_str"].map(_fmt2)):
                if number not in result[mode]:
                    result[mode][number] = {
                        "number": number,
                        "score": 0,
                        "prob": 0,
                        "reason": "",
                        "evidence": "",
                        "summary": "",
                        "positions": [],
                        "lines": [],
                    }
                lines: list[dict[str, str]] = []
                for _, row in group.head(6).iterrows():
                    lines.append(
                        {
                            "kind": str(row.get("rule_kind", "")),
                            "lag": str(row.get("lag_days", "")),
                            "base_date": str(row.get("base_date", "")),
                            "path_line": str(row.get("path_line", "")),
                            "p_mean": _fmt_num(row.get("p_mean", ""), decimals=3),
                            "hits": str(row.get("hits", "")),
                            "trials": str(row.get("trials", "")),
                            "streak": str(row.get("current_streak", "")),
                            "score": _fmt_num(row.get("rule_score", ""), decimals=1),
                            "reason": str(row.get("reason", "")),
                        }
                    )
                result[mode][number]["lines"] = lines
    return result


def _render_result_table(latest: Mapping[str, Any]) -> str:
    if not latest.get("groups"):
        return "<div class='empty'>Chưa có dữ liệu kết quả ngày.</div>"
    rows = []
    for group in latest["groups"]:
        prizes = " ".join(
            f"<span class='prize-number {html.escape(str(group['key']))}' data-mode='loto' data-number='{html.escape(v[-2:])}'>{html.escape(v)}</span>"
            for v in group["values"]
        )
        rows.append(
            f"<tr><th>{html.escape(str(group['label']))}</th>"
            f"<td><div class='prize-list {html.escape(str(group['kind']))}'>{prizes}</div></td></tr>"
        )
    return "<table class='result-table'><tbody>" + "".join(rows) + "</tbody></table>"


def _render_daily_matrix(latest: Mapping[str, Any]) -> str:
    counts = {f"{i:02d}": int(latest.get("counts", {}).get(f"{i:02d}", 0)) for i in range(100)}
    max_count = max(counts.values()) if counts else 0
    cells = []
    for head in range(10):
        row_cells = [f"<div class='matrix-head'>{head}</div>"]
        for tail in range(10):
            n = f"{head}{tail}"
            value = counts[n]
            bg, fg = _style_for_value(value, 0, max(max_count, 1), "orange")
            active = " is-hit" if value else ""
            label = f"{value} lần" if value else "0"
            row_cells.append(
                f"<button class='tiny-matrix-cell{active}' data-mode='loto' data-number='{n}' "
                f"style='background:{bg};color:{fg}' title='{n}: {label}'>"
                f"<b>{n}</b><span>{label}</span></button>"
            )
        cells.append("".join(row_cells))
    header = "<div></div>" + "".join(f"<div class='matrix-head'>{i}</div>" for i in range(10))
    return f"<div class='tiny-matrix'>{header}{''.join(cells)}</div>"


def _render_head_tail_lists(latest: Mapping[str, Any]) -> str:
    def block(title: str, data: Mapping[str, Sequence[str]]) -> str:
        rows = []
        for digit in range(10):
            values = data.get(str(digit), [])
            badges = "".join(f"<span class='mini-badge'>{html.escape(v)}</span>" for v in values) or "<span class='muted'>—</span>"
            rows.append(f"<div class='head-tail-row'><b>{digit}</b><div>{badges}</div></div>")
        return f"<div class='head-tail-card'><h4>{html.escape(title)}</h4>{''.join(rows)}</div>"

    return (
        "<div class='head-tail-grid'>"
        + block("Theo hàng chục / đầu", latest.get("heads", {}))
        + block("Theo hàng đơn vị / đuôi", latest.get("tails", {}))
        + "</div>"
    )


def _render_matrix_card(
    *,
    title: str,
    subtitle: str,
    values: Mapping[str, float],
    palette: str,
    mode: str,
    value_suffix: str = "",
    decimals: int = 0,
) -> str:
    numbers = [f"{i:02d}" for i in range(100)]
    vals = [float(values.get(n, 0.0)) for n in numbers]
    max_value = max(vals) if vals else 0.0
    min_value = min(vals) if vals else 0.0
    cells = []
    for head in range(10):
        row = [f"<div class='matrix-axis'>{head}</div>"]
        for tail in range(10):
            n = f"{head}{tail}"
            value = float(values.get(n, 0.0))
            bg, fg = _style_for_value(value, min_value, max_value, palette)
            val_label = _fmt_num(value, decimals=decimals)
            if value_suffix:
                val_label = f"{val_label}{value_suffix}"
            row.append(
                f"<button class='matrix-cell' data-mode='{mode}' data-number='{n}' "
                f"style='background:{bg};color:{fg}' title='{html.escape(title)} · {n}: {html.escape(val_label)}'>"
                f"<span class='cell-number'>{n}</span><span class='cell-value'>{html.escape(val_label)}</span></button>"
            )
        cells.append("".join(row))
    header = "<div></div>" + "".join(f"<div class='matrix-axis'>{i}</div>" for i in range(10))
    legend_low, legend_high = PALETTES.get(palette, PALETTES["blue"])
    return f"""
    <article class="card matrix-card">
      <div class="card-head">
        <div>
          <p class="eyebrow">Ma trận 00–99</p>
          <h3>{html.escape(title)}</h3>
          <p>{html.escape(subtitle)}</p>
        </div>
      </div>
      <div class="matrix-wrap">
        <div class="matrix-grid">{header}{''.join(cells)}</div>
      </div>
      <div class="legend"><span style="background:{legend_low}"></span> Thấp <i></i> Cao <span style="background:{legend_high}"></span></div>
    </article>
    """


def _render_bar_card(
    *,
    title: str,
    subtitle: str,
    df: pd.DataFrame,
    label_col: str,
    value_col: str,
    palette: str,
    mode: str | None = None,
    number_col: str | None = None,
    limit: int = 12,
    value_decimals: int = 1,
    percent: bool = False,
) -> str:
    if df.empty or label_col not in df.columns or value_col not in df.columns:
        body = "<div class='empty'>Chưa có dữ liệu.</div>"
    else:
        rows = df.head(limit).copy()
        values = pd.to_numeric(rows[value_col], errors="coerce").fillna(0.0)
        max_value = max(float(values.max()), 1e-9)
        _, high = PALETTES.get(palette, PALETTES["blue"])
        items = []
        for _, row in rows.iterrows():
            value = _to_float(row.get(value_col, 0))
            width = max(3, min(100, value / max_value * 100))
            label = str(row.get(label_col, ""))
            number_attr = ""
            if mode and number_col and number_col in row:
                number_attr = f" data-mode='{mode}' data-number='{_fmt2(row.get(number_col))}'"
            elif mode and re.fullmatch(r"\d{1,2}", label):
                number_attr = f" data-mode='{mode}' data-number='{_fmt2(label)}'"
            value_text = _pct(value) if percent else _fmt_num(value, decimals=value_decimals)
            items.append(
                f"<button class='bar-row'{number_attr}>"
                f"<span class='bar-label'>{html.escape(label)}</span>"
                f"<span class='bar-track'><span class='bar-fill' style='width:{width:.1f}%;background:{high}'></span></span>"
                f"<span class='bar-value'>{html.escape(value_text)}</span>"
                f"</button>"
            )
        body = "<div class='bar-list'>" + "".join(items) + "</div>"
    return f"""
    <article class="card">
      <div class="card-head">
        <div>
          <p class="eyebrow">Biểu đồ thanh</p>
          <h3>{html.escape(title)}</h3>
          <p>{html.escape(subtitle)}</p>
        </div>
      </div>
      {body}
    </article>
    """


def _render_table(
    *,
    title: str,
    subtitle: str,
    df: pd.DataFrame,
    columns: Sequence[str],
    limit: int = 12,
    dense: bool = False,
    searchable: bool = False,
    number_mode: str = "loto",
) -> str:
    rows = _df_to_rows(df, columns, limit=limit)
    if not rows:
        body = "<div class='empty'>Chưa có dữ liệu.</div>"
    else:
        table_cols = list(rows[0].keys())
        thead = "".join(f"<th>{html.escape(_pretty_col(c))}</th>" for c in table_cols)
        trs = []
        for row in rows:
            cells = []
            for c in table_cols:
                value = row.get(c, "")
                s = str(value)
                if c.endswith("rate") or c in {"hit_any_rate", "prob"}:
                    s = _pct(value)
                elif c in {"number", "number_str", "next_loto", "prev_loto", "prev_special_2d"}:
                    s = _fmt2(value)
                    s = f"<button class='num-link' data-mode='{number_mode}' data-number='{s}'>{s}</button>"
                    cells.append(f"<td>{s}</td>")
                    continue
                elif c == "mode":
                    s = mode_label(value)
                elif c in {"score_band", "period_kind", "stage", "status"}:
                    s = str(value_label(value))
                cells.append(f"<td>{html.escape(s)}</td>")
            trs.append("<tr>" + "".join(cells) + "</tr>")
        search = (
            "<input class='table-filter' type='search' placeholder='Lọc nhanh trong bảng...' aria-label='Lọc bảng'/>"
            if searchable
            else ""
        )
        body = f"{search}<div class='table-wrap'><table class='stat-table {'dense' if dense else ''}'><thead><tr>{thead}</tr></thead><tbody>{''.join(trs)}</tbody></table></div>"
    return f"""
    <article class="card table-card">
      <div class="card-head">
        <div>
          <p class="eyebrow">Bảng dữ liệu</p>
          <h3>{html.escape(title)}</h3>
          <p>{html.escape(subtitle)}</p>
        </div>
      </div>
      {body}
    </article>
    """


def _render_special_board(repo_root: Path, kind: str) -> str:
    if kind == "week":
        df = _read_csv(repo_root / "data" / "advanced" / "special_week_board.csv", dtype=str).tail(8)
        title = "Bảng ĐB theo tuần"
        subtitle = "8 tuần gần nhất, chia theo thứ trong tuần."
        cols = ["week_key", "T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    else:
        df = _read_csv(repo_root / "data" / "advanced" / "special_month_board.csv", dtype=str).tail(4)
        title = "Bảng ĐB theo tháng"
        subtitle = "4 tháng gần nhất, giữ đủ cột ngày 01–31."
        cols = ["month_key"] + [f"{i:02d}" for i in range(1, 32)]
    return _render_table(title=title, subtitle=subtitle, df=df, columns=cols, limit=10, dense=True, searchable=False)


def _render_group_bars(repo_root: Path, period: str) -> str:
    df = _read_csv(repo_root / "data" / "advanced" / "head_tail_total_loto_current.csv", dtype=str)
    if df.empty:
        return "<div class='empty'>Chưa có dữ liệu đầu/đuôi/tổng.</div>"
    if "period_kind" in df.columns:
        df = df[df["period_kind"] == period]
    cards = []
    for group, palette in [("head", "blue"), ("tail", "green"), ("total", "orange")]:
        part = df[df.get("group_type", "") == group].copy()
        if not part.empty:
            part["label"] = part["group_value"].map(lambda x: f"{GROUP_LABELS.get(group, group)} {x}")
        cards.append(
            _render_bar_card(
                title=GROUP_LABELS.get(group, group),
                subtitle=f"Phân bổ {GROUP_LABELS.get(group, group).lower()} trong kỳ {period}.",
                df=_sort_top(part, "freq", 10),
                label_col="label",
                value_col="freq",
                palette=palette,
                limit=10,
                value_decimals=0,
            )
        )
    return "<div class='three-col'>" + "".join(cards) + "</div>"


def _render_html(repo_root: Path, *, desktop_view: bool = False) -> str:
    latest = _latest_draw(repo_root)
    explain_map = _load_explain_map(repo_root)
    generated_at = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    loto_snapshot = _read_csv(repo_root / "data" / "advanced" / "period_snapshot_loto_current.csv", dtype=str)
    de_snapshot = _read_csv(repo_root / "data" / "advanced" / "period_snapshot_de_current.csv", dtype=str)

    ai_loto = _sort_top(_read_csv(repo_root / "data" / "ai_ml" / "cau_keo_loto_top20.csv", dtype=str), "cau_score", 10)
    ai_de = _sort_top(_read_csv(repo_root / "data" / "ai_ml" / "cau_keo_de_top20.csv", dtype=str), "cau_score", 10)
    loto_rhythm = _sort_top(_read_csv(repo_root / "data" / "advanced" / "loto_rhythm.csv", dtype=str), "current_gap", 12)
    de_rhythm = _sort_top(_read_csv(repo_root / "data" / "advanced" / "de_rhythm.csv", dtype=str), "current_gap", 12)
    reverse_pairs = _read_csv(repo_root / "data" / "advanced" / "reverse_pair_frequency_current.csv", dtype=str)
    if not reverse_pairs.empty and "period_kind" in reverse_pairs.columns:
        reverse_pairs = reverse_pairs[reverse_pairs["period_kind"] == "month"]
    reverse_pairs = _sort_top(reverse_pairs, "freq", 12)

    conditional_special = _read_csv(repo_root / "data" / "advanced" / "conditional_loto_after_special_top500.csv", dtype=str)
    conditional_loto = _read_csv(repo_root / "data" / "advanced" / "conditional_loto_after_loto_top500.csv", dtype=str)
    first_prize = _sort_top(_read_csv(repo_root / "data" / "advanced" / "first_prize_overdue.csv", dtype=str), "current_gap", 10)
    report_loto = _read_csv(repo_root / "data" / "ai_ml" / "cau_keo_report_loto.csv", dtype=str)
    report_de = _read_csv(repo_root / "data" / "ai_ml" / "cau_keo_report_de.csv", dtype=str)
    evidence_loto = _sort_top(_read_csv(repo_root / "data" / "ai_ml" / "cau_position_evidence_loto.csv", dtype=str), "rule_score", 10)
    evidence_de = _sort_top(_read_csv(repo_root / "data" / "ai_ml" / "cau_position_evidence_de.csv", dtype=str), "rule_score", 10)

    stat_cards_top = [
        (
            "Ngày dữ liệu",
            str(latest.get("date") or "—"),
            "Ngày kết quả mới nhất trong data/xsmb.csv",
            "blue",
        ),
        (
            "Đặc biệt",
            str(latest.get("special") or "—"),
            f"2 số cuối: {latest.get('special_2d') or '—'}",
            "orange",
        ),
        (
            "Loto về hôm nay",
            str(sum(_to_int(v) for v in latest.get("counts", {}).values())),
            "Tổng lượt 2 số từ toàn bộ giải",
            "green",
        ),
        (
            "Số khác nhau",
            str(len(latest.get("counts", {}))),
            "Số bộ 00–99 xuất hiện trong ngày",
            "purple",
        ),
    ]

    nav = "\n".join(
        f"<a href='#{sid}'><span>{idx:02d}</span><b>{html.escape(label)}</b><small>{html.escape(desc)}</small></a>"
        for idx, (sid, label, desc) in enumerate(NAV_ITEMS, start=1)
    )

    stat_tiles = "\n".join(
        f"<div class='metric-tile {palette}'><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong><em>{html.escape(desc)}</em></div>"
        for label, value, desc, palette in stat_cards_top
    )

    hero_actions = """
      <div class="hero-actions">
        <a class="primary-action" href="#ket-qua">Xem kết quả ngày</a>
        <a class="ghost-action" href="landing_desktop.html">Mở giao diện máy tính</a>
        <a class="ghost-action" href="statistics.html">Mở bảng điều khiển thống kê đầy đủ</a>
        <a class="ghost-action" href="soi-path-loto-active.html">Soi cầu vị trí</a>
      </div>
    """

    ai_summary_rows = ai_loto.head(3).to_dict("records") if not ai_loto.empty else []
    ai_pills = "".join(
        f"<button class='signal-pill' data-mode='loto' data-number='{_fmt2(row.get('number_str', row.get('number', '')))}'>"
        f"<b>{_fmt2(row.get('number_str', row.get('number', '')))}</b>"
        f"<span>{html.escape(str(row.get('primary_reason', 'Tín hiệu AI/ML')))}</span>"
        f"</button>"
        for row in ai_summary_rows
    ) or "<span class='muted'>Chưa có dữ liệu AI/ML.</span>"

    data_json = json.dumps({"explain": explain_map, "generated_at": generated_at}, ensure_ascii=False).replace("</", "<\\/")
    body_class = ' class="desktop-view"' if desktop_view else ''

    html_doc = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Trung tâm phân tích xổ số</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --panel-soft: #f8fafc;
      --ink: #0f172a;
      --muted: #64748b;
      --line: #e2e8f0;
      --blue: #2563eb;
      --sky: #0891b2;
      --green: #059669;
      --orange: #ea580c;
      --purple: #7c3aed;
      --rose: #e11d48;
      --shadow: 0 22px 70px rgba(15, 23, 42, .10);
      --radius: 24px;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(37,99,235,.18), transparent 34rem),
        radial-gradient(circle at 75% 10%, rgba(124,58,237,.14), transparent 32rem),
        var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    }}
    a {{ color: inherit; text-decoration: none; }}
    button {{ font: inherit; }}
    .app {{
      display: grid;
      grid-template-columns: 292px minmax(0, 1fr);
      min-height: 100vh;
    }}
    .sidebar {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      padding: 22px;
      color: #e5e7eb;
      background:
        linear-gradient(180deg, rgba(15,23,42,.96), rgba(15,23,42,.91)),
        radial-gradient(circle at 30% 0%, rgba(37,99,235,.55), transparent 16rem);
      border-right: 1px solid rgba(255,255,255,.08);
    }}
    .brand {{
      display: flex;
      gap: 12px;
      align-items: center;
      padding: 12px;
      border: 1px solid rgba(255,255,255,.10);
      border-radius: 18px;
      background: rgba(255,255,255,.06);
      margin-bottom: 18px;
    }}
    .brand-logo {{
      width: 42px;
      height: 42px;
      display: grid;
      place-items: center;
      border-radius: 14px;
      background: linear-gradient(135deg, #60a5fa, #a78bfa);
      color: #fff;
      font-weight: 900;
    }}
    .brand strong {{ display: block; font-size: 14px; }}
    .brand small {{ display: block; color: #94a3b8; margin-top: 2px; }}
    .nav-title {{
      margin: 20px 10px 8px;
      font-size: 11px;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: .14em;
      font-weight: 800;
    }}
    .side-nav {{ display: grid; gap: 8px; }}
    .side-nav a {{
      display: grid;
      grid-template-columns: 28px 1fr;
      gap: 10px;
      padding: 11px 12px;
      border: 1px solid transparent;
      border-radius: 16px;
      color: #cbd5e1;
      transition: .18s ease;
    }}
    .side-nav a span {{
      width: 28px;
      height: 28px;
      border-radius: 10px;
      display: grid;
      place-items: center;
      background: rgba(148,163,184,.12);
      color: #93c5fd;
      font-size: 11px;
      font-weight: 900;
    }}
    .side-nav a b {{ font-size: 13px; }}
    .side-nav a small {{ grid-column: 2; color: #94a3b8; line-height: 1.35; margin-top: 2px; }}
    .side-nav a:hover,
    .side-nav a.active {{
      background: rgba(255,255,255,.08);
      border-color: rgba(255,255,255,.12);
      color: #fff;
      transform: translateX(2px);
    }}
    .main {{
      min-width: 0;
      padding: 28px;
    }}
    .hero {{
      position: relative;
      overflow: hidden;
      border-radius: 32px;
      padding: 30px;
      margin-bottom: 20px;
      color: #fff;
      background:
        linear-gradient(135deg, rgba(15,23,42,.98), rgba(30,41,59,.92)),
        radial-gradient(circle at 10% 10%, rgba(37,99,235,.8), transparent 22rem),
        radial-gradient(circle at 80% 20%, rgba(124,58,237,.75), transparent 20rem);
      box-shadow: var(--shadow);
    }}
    .hero::after {{
      content: "";
      position: absolute;
      right: -12rem;
      top: -12rem;
      width: 32rem;
      height: 32rem;
      background: radial-gradient(circle, rgba(96,165,250,.32), transparent 70%);
      pointer-events: none;
    }}
    .hero-content {{ position: relative; z-index: 1; display: grid; gap: 18px; }}
    .hero h1 {{
      max-width: 900px;
      margin: 0;
      font-size: clamp(30px, 5vw, 58px);
      line-height: .98;
      letter-spacing: -.045em;
    }}
    .hero p {{ max-width: 820px; margin: 0; color: #cbd5e1; font-size: 16px; line-height: 1.65; }}
    .hero-actions {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    .primary-action, .ghost-action {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      padding: 10px 15px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 800;
    }}
    .primary-action {{ background: #fff; color: #0f172a; }}
    .ghost-action {{ border: 1px solid rgba(255,255,255,.18); color: #e5e7eb; background: rgba(255,255,255,.07); }}
    .metric-row {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }}
    .metric-tile {{
      padding: 18px;
      border-radius: 22px;
      background: var(--panel);
      border: 1px solid rgba(226,232,240,.8);
      box-shadow: 0 14px 34px rgba(15,23,42,.06);
      min-height: 124px;
      display: grid;
      gap: 8px;
      align-content: start;
      position: relative;
      overflow: hidden;
    }}
    .metric-tile::before {{
      content: "";
      position: absolute;
      inset: auto 16px 14px auto;
      width: 70px;
      height: 70px;
      border-radius: 999px;
      opacity: .12;
      background: currentColor;
    }}
    .metric-tile span {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .09em; font-weight: 900; }}
    .metric-tile strong {{ font-size: clamp(26px, 4vw, 42px); line-height: 1; letter-spacing: -.04em; }}
    .metric-tile em {{ font-style: normal; color: var(--muted); font-size: 13px; line-height: 1.4; }}
    .metric-tile.blue {{ color: var(--blue); }}
    .metric-tile.orange {{ color: var(--orange); }}
    .metric-tile.green {{ color: var(--green); }}
    .metric-tile.purple {{ color: var(--purple); }}
    .layout-top {{
      display: grid;
      grid-template-columns: minmax(0, 1.4fr) minmax(330px, .72fr);
      gap: 18px;
      align-items: start;
    }}
    .right-rail {{ display: grid; gap: 18px; }}
    .section {{
      scroll-margin-top: 20px;
      margin-top: 18px;
    }}
    .section-title {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 16px;
      margin: 30px 0 14px;
    }}
    .section-title h2 {{
      margin: 0;
      font-size: clamp(22px, 3vw, 34px);
      letter-spacing: -.035em;
    }}
    .section-title p {{
      margin: 6px 0 0;
      color: var(--muted);
      max-width: 780px;
      line-height: 1.55;
    }}
    .section-title .section-kicker {{
      font-size: 11px;
      color: var(--blue);
      text-transform: uppercase;
      letter-spacing: .15em;
      font-weight: 900;
    }}
    .card {{
      background: rgba(255,255,255,.88);
      backdrop-filter: blur(18px);
      border: 1px solid rgba(226,232,240,.85);
      border-radius: var(--radius);
      box-shadow: 0 16px 42px rgba(15,23,42,.07);
      padding: 18px;
      min-width: 0;
    }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 14px;
    }}
    .eyebrow {{
      margin: 0 0 5px;
      color: var(--blue);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .14em;
      font-weight: 900;
    }}
    .card h3 {{
      margin: 0;
      font-size: 18px;
      letter-spacing: -.02em;
    }}
    .card-head p:not(.eyebrow), .card > p {{
      color: var(--muted);
      margin: 5px 0 0;
      line-height: 1.45;
      font-size: 13px;
    }}
    .result-combo {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(260px, .45fr);
      gap: 16px;
      align-items: start;
    }}
    .result-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 18px;
    }}
    .result-table th {{
      width: 118px;
      text-align: left;
      vertical-align: middle;
      padding: 14px;
      color: #334155;
      background: #f8fafc;
      border-bottom: 1px solid var(--line);
      font-size: 13px;
    }}
    .result-table td {{
      padding: 12px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }}
    .result-table tr:last-child th, .result-table tr:last-child td {{ border-bottom: 0; }}
    .prize-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .prize-number {{
      border: 0;
      cursor: pointer;
      display: inline-grid;
      place-items: center;
      min-width: 68px;
      min-height: 38px;
      padding: 6px 10px;
      border-radius: 13px;
      background: #f1f5f9;
      color: #0f172a;
      font-weight: 900;
      letter-spacing: .03em;
      box-shadow: inset 0 -1px 0 rgba(15,23,42,.08);
    }}
    .prize-number.special {{
      min-width: 116px;
      min-height: 52px;
      background: linear-gradient(135deg, #fee2e2, #ffedd5);
      color: #b91c1c;
      font-size: 28px;
      letter-spacing: .06em;
    }}
    .prize-list.mini .prize-number {{ min-width: 48px; color: #b91c1c; background: #fff1f2; }}
    .chuc-card {{
      position: sticky;
      top: 18px;
    }}
    .tiny-matrix, .matrix-grid {{
      display: grid;
      grid-template-columns: 26px repeat(10, minmax(38px, 1fr));
      gap: 6px;
      align-items: stretch;
    }}
    .tiny-matrix {{
      grid-template-columns: 22px repeat(10, minmax(27px, 1fr));
      gap: 4px;
    }}
    .matrix-axis, .matrix-head {{
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
    }}
    .tiny-matrix-cell, .matrix-cell {{
      border: 1px solid rgba(15,23,42,.06);
      border-radius: 12px;
      cursor: pointer;
      min-width: 0;
      transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
    }}
    .matrix-cell {{
      min-height: 52px;
      padding: 7px 4px;
      display: grid;
      place-items: center;
      gap: 2px;
    }}
    .tiny-matrix-cell {{
      min-height: 42px;
      padding: 4px 2px;
      display: grid;
      place-items: center;
      gap: 1px;
    }}
    .tiny-matrix-cell b, .cell-number {{
      font-weight: 950;
      letter-spacing: -.02em;
    }}
    .tiny-matrix-cell span, .cell-value {{
      font-size: 10px;
      opacity: .88;
      font-weight: 750;
    }}
    .matrix-cell:hover, .tiny-matrix-cell:hover, .bar-row:hover, .num-link:hover, .signal-pill:hover {{
      transform: translateY(-1px);
      box-shadow: 0 12px 22px rgba(15,23,42,.12);
      border-color: rgba(37,99,235,.35);
    }}
    .matrix-wrap {{ overflow: auto; padding-bottom: 4px; }}
    .legend {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
    }}
    .legend span {{ width: 32px; height: 10px; border-radius: 99px; border: 1px solid rgba(15,23,42,.08); }}
    .legend i {{ width: 50px; height: 1px; background: var(--line); }}
    .head-tail-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .head-tail-card {{
      border-radius: 18px;
      background: #f8fafc;
      border: 1px solid var(--line);
      padding: 12px;
    }}
    .head-tail-card h4 {{ margin: 0 0 8px; font-size: 13px; }}
    .head-tail-row {{
      display: grid;
      grid-template-columns: 26px minmax(0, 1fr);
      gap: 8px;
      align-items: start;
      padding: 5px 0;
      border-top: 1px solid rgba(226,232,240,.75);
    }}
    .head-tail-row:first-of-type {{ border-top: 0; }}
    .mini-badge {{
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 3px 7px;
      margin: 1px;
      border-radius: 999px;
      background: #e0f2fe;
      color: #075985;
      font-size: 12px;
      font-weight: 850;
    }}
    .matrix-two, .two-col {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }}
    .matrix-three, .three-col {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
    }}
    .bar-list {{ display: grid; gap: 9px; }}
    .bar-row {{
      display: grid;
      grid-template-columns: 86px minmax(0, 1fr) 74px;
      align-items: center;
      gap: 10px;
      width: 100%;
      padding: 8px;
      border: 1px solid transparent;
      border-radius: 14px;
      background: transparent;
      text-align: left;
      cursor: pointer;
    }}
    .bar-label {{
      font-weight: 900;
      color: #0f172a;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .bar-track {{
      height: 13px;
      border-radius: 999px;
      background: #e2e8f0;
      overflow: hidden;
    }}
    .bar-fill {{
      display: block;
      height: 100%;
      border-radius: inherit;
    }}
    .bar-value {{
      color: var(--muted);
      text-align: right;
      font-size: 12px;
      font-weight: 850;
    }}
    .signal-pills {{ display: grid; gap: 8px; }}
    .signal-pill {{
      display: grid;
      grid-template-columns: 46px 1fr;
      gap: 10px;
      align-items: center;
      padding: 9px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: #fff;
      text-align: left;
      cursor: pointer;
    }}
    .signal-pill b {{
      display: grid;
      place-items: center;
      width: 42px;
      height: 42px;
      border-radius: 14px;
      background: #f5f3ff;
      color: var(--purple);
      font-size: 18px;
    }}
    .signal-pill span {{
      color: #334155;
      font-size: 13px;
      line-height: 1.35;
      font-weight: 700;
    }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 18px;
      max-height: 520px;
    }}
    .stat-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      min-width: 640px;
      background: #fff;
    }}
    .stat-table th {{
      position: sticky;
      top: 0;
      z-index: 1;
      padding: 10px 11px;
      text-align: left;
      background: #f8fafc;
      border-bottom: 1px solid var(--line);
      color: #334155;
      font-size: 12px;
      white-space: nowrap;
    }}
    .stat-table td {{
      padding: 10px 11px;
      border-bottom: 1px solid #f1f5f9;
      color: #0f172a;
      font-size: 13px;
      vertical-align: top;
    }}
    .stat-table.dense th, .stat-table.dense td {{
      padding: 7px 8px;
      font-size: 12px;
      text-align: center;
      white-space: nowrap;
    }}
    .table-filter {{
      width: 100%;
      margin: 0 0 10px;
      min-height: 42px;
      padding: 0 14px;
      border: 1px solid var(--line);
      border-radius: 14px;
      outline: none;
      background: #fff;
    }}
    .num-link {{
      border: 0;
      border-radius: 10px;
      background: #eff6ff;
      color: #1d4ed8;
      font-weight: 900;
      padding: 5px 8px;
      cursor: pointer;
    }}
    .inspector {{
      display: grid;
      grid-template-columns: minmax(0, .7fr) minmax(0, 1.3fr);
      gap: 18px;
      align-items: start;
    }}
    .inspect-panel {{
      background:
        radial-gradient(circle at 20% 0%, rgba(124,58,237,.16), transparent 18rem),
        #fff;
      border-radius: var(--radius);
      border: 1px solid rgba(226,232,240,.9);
      padding: 18px;
      box-shadow: 0 16px 42px rgba(15,23,42,.07);
    }}
    .inspect-number {{
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .inspect-number b {{
      display: grid;
      place-items: center;
      width: 64px;
      height: 64px;
      border-radius: 20px;
      background: linear-gradient(135deg, #ede9fe, #dbeafe);
      color: #5b21b6;
      font-size: 28px;
      letter-spacing: -.05em;
    }}
    .inspect-number span {{ color: var(--muted); font-size: 13px; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; }}
    .inspect-panel h3 {{ margin: 0 0 8px; font-size: 22px; }}
    .inspect-panel p {{ color: #475569; line-height: 1.55; margin: 8px 0; }}
    .inspect-meta {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin: 14px 0;
    }}
    .inspect-meta div {{
      padding: 10px;
      border-radius: 14px;
      background: #f8fafc;
      border: 1px solid var(--line);
    }}
    .inspect-meta span {{
      display: block;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: .08em;
      font-weight: 900;
    }}
    .inspect-meta strong {{ display: block; margin-top: 3px; font-size: 18px; }}
    .position-list {{ display: grid; gap: 8px; margin-top: 10px; }}
    .position-list li {{
      list-style: none;
      padding: 10px;
      border-radius: 14px;
      background: #f8fafc;
      border: 1px solid var(--line);
      color: #334155;
      font-size: 13px;
      line-height: 1.45;
    }}
    .empty, .muted {{ color: var(--muted); }}
    .empty {{
      padding: 22px;
      border-radius: 18px;
      background: #f8fafc;
      border: 1px dashed #cbd5e1;
      text-align: center;
    }}
    .footer {{
      margin: 32px 0 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
      text-align: center;
    }}
    @media (min-width: 1181px) {{
      .main {{
        max-width: min(100%, 1780px);
        padding: 32px clamp(28px, 3vw, 48px);
      }}
      .layout-top {{
        grid-template-columns: minmax(760px, 1fr) minmax(360px, 440px);
      }}
      .right-rail {{
        position: sticky;
        top: 22px;
        max-height: calc(100vh - 44px);
        overflow: auto;
        padding-right: 2px;
      }}
      .result-combo {{
        grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
      }}
      .hero-content {{
        grid-template-columns: minmax(0, 1fr) minmax(300px, 380px);
        align-items: end;
      }}
      .hero-content > div:first-child,
      .hero-content > p,
      .hero-actions {{
        grid-column: 1;
      }}
      .hero .signal-pills {{
        grid-column: 2;
        grid-row: 1 / span 3;
        align-self: stretch;
        align-content: end;
        padding: 12px;
        border: 1px solid rgba(255,255,255,.16);
        border-radius: 22px;
        background: rgba(255,255,255,.08);
        backdrop-filter: blur(18px);
      }}
      .section-title {{
        padding-right: min(10vw, 180px);
      }}
    }}
    @media (min-width: 1440px) {{
      .matrix-two {{
        grid-template-columns: repeat(2, minmax(520px, 1fr));
      }}
      .two-col {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .three-col {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 1180px) {{
      .app {{ grid-template-columns: 1fr; }}
      .sidebar {{
        position: relative;
        height: auto;
        border-right: 0;
        border-bottom: 1px solid rgba(255,255,255,.08);
      }}
      .side-nav {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .main {{ padding: 18px; }}
      .layout-top {{ grid-template-columns: 1fr; }}
      .right-rail {{ position: static; max-height: none; overflow: visible; }}
      .chuc-card {{ position: static; }}
      .metric-row {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 860px) {{
      .result-combo, .matrix-two, .matrix-three, .two-col, .three-col, .inspector {{
        grid-template-columns: 1fr;
      }}
      .side-nav {{ grid-template-columns: 1fr; }}
      .metric-row {{ grid-template-columns: 1fr; }}
      .hero {{ padding: 22px; border-radius: 24px; }}
      .result-table th {{ width: 92px; }}
      .prize-number.special {{ font-size: 22px; min-width: 96px; }}
      .tiny-matrix, .matrix-grid {{
        grid-template-columns: 22px repeat(10, 38px);
      }}
      .matrix-cell {{ min-height: 48px; }}
      .bar-row {{ grid-template-columns: 62px minmax(0, 1fr) 58px; }}
      .head-tail-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 640px) {{
      body {{
        background:
          radial-gradient(circle at top, rgba(37,99,235,.16), transparent 24rem),
          var(--bg);
      }}
      .sidebar {{
        position: sticky;
        top: 0;
        z-index: 30;
        padding: 10px;
        border-bottom: 1px solid rgba(255,255,255,.10);
      }}
      .brand {{
        margin-bottom: 8px;
        padding: 9px;
      }}
      .brand-logo {{ width: 34px; height: 34px; border-radius: 12px; }}
      .brand small {{ display: none; }}
      .nav-title {{ display: none; }}
      .side-nav {{
        display: flex;
        gap: 8px;
        overflow-x: auto;
        padding-bottom: 4px;
        scroll-snap-type: x mandatory;
        -webkit-overflow-scrolling: touch;
      }}
      .side-nav a {{
        min-width: 164px;
        grid-template-columns: 24px 1fr;
        gap: 8px;
        padding: 8px;
        scroll-snap-align: start;
      }}
      .side-nav a span {{
        width: 24px;
        height: 24px;
        border-radius: 8px;
        font-size: 10px;
      }}
      .side-nav a b {{ font-size: 12px; }}
      .side-nav a small {{ display: none; }}
      .main {{ padding: 12px; }}
      .hero {{
        padding: 18px;
        margin-bottom: 12px;
        border-radius: 22px;
      }}
      .hero h1 {{
        font-size: clamp(26px, 8vw, 34px);
        line-height: 1.05;
      }}
      .hero p {{
        font-size: 14px;
        line-height: 1.55;
      }}
      .hero-actions a {{
        width: 100%;
      }}
      .card {{
        padding: 14px;
        border-radius: 20px;
      }}
      .section-title {{
        display: block;
        margin: 24px 0 12px;
      }}
      .section-title h2 {{
        font-size: 24px;
      }}
      .card-head {{
        display: block;
      }}
      .result-combo > div:first-child,
      .matrix-wrap,
      .table-wrap {{
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
      }}
      .result-table {{
        min-width: 520px;
      }}
      .tiny-matrix, .matrix-grid {{
        min-width: 430px;
        grid-template-columns: 24px repeat(10, 36px);
      }}
      .matrix-cell {{
        min-height: 46px;
        border-radius: 11px;
      }}
      .tiny-matrix-cell {{
        min-height: 38px;
        border-radius: 10px;
      }}
      .inspect-meta {{
        grid-template-columns: 1fr;
      }}
      .stat-table {{
        min-width: 620px;
      }}
      .footer {{
        margin-bottom: 70px;
      }}
    }}
    body.desktop-view {{
      min-width: 1320px;
    }}
    body.desktop-view .app {{
      grid-template-columns: 304px minmax(980px, 1fr) !important;
    }}
    body.desktop-view .sidebar {{
      position: sticky !important;
      top: 0 !important;
      height: 100vh !important;
      border-right: 1px solid rgba(255,255,255,.08) !important;
      border-bottom: 0 !important;
    }}
    body.desktop-view .side-nav {{
      display: grid !important;
      grid-template-columns: 1fr !important;
      overflow: visible !important;
    }}
    body.desktop-view .side-nav a {{
      min-width: 0 !important;
    }}
    body.desktop-view .side-nav a small {{
      display: block !important;
    }}
    body.desktop-view .main {{
      max-width: min(100%, 1780px) !important;
      padding: 32px clamp(28px, 3vw, 48px) !important;
    }}
    body.desktop-view .layout-top {{
      grid-template-columns: minmax(760px, 1fr) minmax(360px, 440px) !important;
    }}
    body.desktop-view .right-rail {{
      position: sticky !important;
      top: 22px !important;
      max-height: calc(100vh - 44px) !important;
      overflow: auto !important;
    }}
    body.desktop-view .result-combo {{
      grid-template-columns: minmax(0, 1fr) minmax(280px, 340px) !important;
    }}
    body.desktop-view .matrix-two,
    body.desktop-view .two-col {{
      grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }}
    body.desktop-view .matrix-three,
    body.desktop-view .three-col {{
      grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    }}
    body.desktop-view .inspector {{
      grid-template-columns: minmax(320px, .7fr) minmax(0, 1.3fr) !important;
    }}
    @media print {{
      .sidebar, .hero-actions {{ display: none; }}
      .app {{ display: block; }}
      body {{ background: #fff; }}
      .card, .metric-tile, .hero {{ box-shadow: none; }}
    }}
  </style>
</head>
<body{body_class}>
  <div class="app">
    <aside class="sidebar" aria-label="Menu thống kê">
      <div class="brand">
        <div class="brand-logo">AI</div>
        <div>
          <strong>Trung tâm phân tích xổ số</strong>
          <small>Trang tổng hợp thống kê XSMB</small>
        </div>
      </div>
      <div class="nav-title">Trình đơn thống kê</div>
      <nav class="side-nav" id="side-nav">
        {nav}
      </nav>
    </aside>

    <main class="main">
      <section id="tong-quan" class="hero section">
        <div class="hero-content">
          <div>
            <p class="eyebrow" style="color:#93c5fd">Bảng điều khiển tổng hợp</p>
            <h1>Trung tâm thống kê xổ số: kết quả ngày, ma trận, cầu vị trí và tín hiệu AI/ML.</h1>
          </div>
          <p>
            Trang này gom các bảng quan trọng vào một trang tổng hợp hiện đại: bấm trình đơn để cuộn tới đúng thống kê,
            bảng kết quả đặt trung tâm, chục–đơn vị đặt cạnh bên, còn AI/ML và các bảng phân tích nằm ở phải và bên dưới
            để so sánh nhanh mà không bị rối giao diện.
          </p>
          {hero_actions}
          <div class="signal-pills">
            {ai_pills}
          </div>
        </div>
      </section>

      <div class="metric-row">
        {stat_tiles}
      </div>

      <div class="layout-top">
        <section id="ket-qua" class="section card">
          <div class="card-head">
            <div>
              <p class="eyebrow">Kết quả hàng ngày</p>
              <h3>XSMB ngày {html.escape(str(latest.get('date') or '—'))}</h3>
              <p>Bảng kết quả giữ đủ số 0 đầu theo chuẩn từng giải; bấm vào số để xem căn cứ AI/ML và đường cầu.</p>
            </div>
          </div>
          <div class="result-combo">
            <div>
              {_render_result_table(latest)}
            </div>
            <aside id="chuc-don-vi" class="chuc-card">
              <div class="card-head">
                <div>
                  <p class="eyebrow">Chục × đơn vị</p>
                  <h3>Ma trận lô tô ngày</h3>
                  <p>Hàng ngang là đơn vị, hàng dọc là hàng chục/đầu. Màu đậm hơn nghĩa là số xuất hiện nhiều lần hơn.</p>
                </div>
              </div>
              {_render_daily_matrix(latest)}
            </aside>
          </div>
          {_render_head_tail_lists(latest)}
        </section>

        <aside class="right-rail">
          <section id="ai-ml" class="section">
            {_render_bar_card(title='AI/ML lô tô đứng đầu', subtitle='Các số có điểm cầu-kèo cao nhất từ mô hình và thống kê lịch sử.', df=ai_loto, label_col='number_str', value_col='cau_score', palette='purple', mode='loto', number_col='number_str', limit=10, value_decimals=1)}
          </section>
          {_render_bar_card(title='AI/ML ĐB đứng đầu', subtitle='Tín hiệu ĐB theo AI/ML, dùng để tham khảo xác suất tương đối.', df=ai_de, label_col='number_str', value_col='cau_score', palette='orange', mode='de', number_col='number_str', limit=10, value_decimals=1)}
        </aside>
      </div>

      <section id="tan-suat-loto" class="section">
        <div class="section-title">
          <div>
            <div class="section-kicker">Ma trận tần suất</div>
            <h2>Tần suất lô tô theo ngày / tuần / tháng / năm</h2>
            <p>Những phần có đủ 00–99 được thể hiện bằng ma trận để mắt nhận ra vùng nóng/lạnh nhanh hơn bảng dài.</p>
          </div>
        </div>
        <div class="matrix-two">
          {_render_matrix_card(title='Lô tô ngày hiện tại', subtitle='Tần suất 00–99 trong ngày kết quả mới nhất.', values=_current_period_matrix(repo_root, 'loto', 'day'), palette='blue', mode='loto')}
          {_render_matrix_card(title='Lô tô tuần hiện tại', subtitle='Cộng dồn lô tô trong tuần hiện tại.', values=_current_period_matrix(repo_root, 'loto', 'week'), palette='green', mode='loto')}
          {_render_matrix_card(title='Lô tô tháng hiện tại', subtitle='Cộng dồn lô tô trong tháng hiện tại.', values=_current_period_matrix(repo_root, 'loto', 'month'), palette='orange', mode='loto')}
          {_render_matrix_card(title='Lô tô năm hiện tại', subtitle='Cộng dồn lô tô trong năm hiện tại.', values=_current_period_matrix(repo_root, 'loto', 'year'), palette='purple', mode='loto')}
        </div>
      </section>

      <section id="tan-suat-de" class="section">
        <div class="section-title">
          <div>
            <div class="section-kicker">Số đặc biệt</div>
            <h2>Tần suất ĐB theo kỳ</h2>
            <p>ĐB là một kết quả/ngày nên xem bằng ma trận tháng/năm sẽ dễ nhận biết phân bổ hơn bảng xếp hạng đơn thuần.</p>
          </div>
        </div>
        <div class="matrix-two">
          {_render_matrix_card(title='ĐB tháng hiện tại', subtitle='Tần suất 2 số cuối giải đặc biệt trong tháng.', values=_current_period_matrix(repo_root, 'de', 'month'), palette='orange', mode='de')}
          {_render_matrix_card(title='ĐB năm hiện tại', subtitle='Tần suất 2 số cuối giải đặc biệt trong năm.', values=_current_period_matrix(repo_root, 'de', 'year'), palette='rose', mode='de')}
          {_render_matrix_card(title='Điểm AI lô tô', subtitle='Điểm AI/ML kết hợp tần suất, nhịp, điều kiện và cầu vị trí.', values=_ai_matrix(repo_root, 'loto'), palette='purple', mode='loto', decimals=1)}
          {_render_matrix_card(title='Điểm AI ĐB', subtitle='Điểm AI/ML dành riêng cho 2 số cuối giải đặc biệt.', values=_ai_matrix(repo_root, 'de'), palette='rose', mode='de', decimals=1)}
        </div>
      </section>

      <section id="gan-nhip" class="section">
        <div class="section-title">
          <div>
            <div class="section-kicker">Nhịp xuất hiện</div>
            <h2>Gan / nhịp và áp lực quay lại</h2>
            <p>Gan cao không đồng nghĩa chắc chắn về; phần này giúp phát hiện số lâu chưa xuất hiện và so sánh với nhịp lịch sử.</p>
          </div>
        </div>
        <div class="matrix-two">
          {_render_matrix_card(title='Gan lô tô hiện tại', subtitle='Số ngày chưa về của từng bộ lô tô.', values=_rhythm_matrix(repo_root, 'loto'), palette='green', mode='loto')}
          {_render_matrix_card(title='Gan ĐB hiện tại', subtitle='Số ngày chưa về của từng bộ ĐB.', values=_rhythm_matrix(repo_root, 'de'), palette='rose', mode='de')}
          {_render_bar_card(title='Gan lô tô đứng đầu', subtitle='Các bộ lô tô có khoảng gan hiện tại cao nhất.', df=loto_rhythm, label_col='number_str', value_col='current_gap', palette='green', mode='loto', number_col='number_str', limit=12, value_decimals=0)}
          {_render_bar_card(title='Gan ĐB đứng đầu', subtitle='Các bộ ĐB có khoảng gan hiện tại cao nhất.', df=de_rhythm, label_col='number_str', value_col='current_gap', palette='rose', mode='de', number_col='number_str', limit=12, value_decimals=0)}
        </div>
      </section>

      <section id="cap-lon" class="section">
        <div class="section-title">
          <div>
            <div class="section-kicker">Cặp đảo chiều</div>
            <h2>Cặp lộn / cặp đảo chiều</h2>
            <p>Biểu đồ thanh phù hợp hơn ma trận vì cần so sánh xếp hạng từng cặp như 36–63, 69–96.</p>
          </div>
        </div>
        <div class="two-col">
          {_render_bar_card(title='Cặp lộn nổi bật trong tháng', subtitle='Cặp đảo chiều có tổng tần suất cao trong tháng hiện tại.', df=reverse_pairs, label_col='pair', value_col='freq', palette='sky', limit=12, value_decimals=0)}
          {_render_table(title='Chi tiết cặp lộn', subtitle='Có thêm số ngày về và số ngày cùng về để tránh nhìn nhầm chỉ theo tần suất.', df=reverse_pairs, columns=['pair', 'freq', 'days_hit', 'cooccur_days', 'avg_per_draw', 'rank_in_period'], limit=12, dense=False)}
        </div>
      </section>

      <section id="dau-duoi-tong" class="section">
        <div class="section-title">
          <div>
            <div class="section-kicker">Nhóm số</div>
            <h2>Đầu · đuôi · tổng</h2>
            <p>Các nhóm 0–9 nên hiển thị bằng biểu đồ thanh để so sánh trực tiếp giữa các nhóm.</p>
          </div>
        </div>
        {_render_group_bars(repo_root, 'month')}
      </section>

      <section id="db-tuan-thang" class="section">
        <div class="section-title">
          <div>
            <div class="section-kicker">Bảng theo lịch</div>
            <h2>Bảng ĐB tuần và tháng</h2>
            <p>Nhóm lịch được giữ dạng bảng vì mục tiêu là đối chiếu theo ngày/thứ, không phải chỉ nhìn nhóm đứng đầu.</p>
          </div>
        </div>
        <div class="two-col">
          {_render_special_board(repo_root, 'week')}
          {_render_special_board(repo_root, 'month')}
        </div>
      </section>

      <section id="duong-cau" class="section">
        <div class="section-title">
          <div>
            <div class="section-kicker">Bấm để xem căn cứ</div>
            <h2>Vị trí đường cầu và căn cứ tạo số liệu</h2>
            <p>Bấm vào bất kỳ số nào trên ma trận, bảng kết quả hoặc bảng xếp hạng AI/ML để cập nhật khung bên trái với lý do, điểm, xác suất và các đường cầu vị trí.</p>
          </div>
        </div>
        <div class="inspector">
          <aside class="inspect-panel" id="number-inspector">
            <div class="inspect-number">
              <b id="inspect-num">--</b>
              <div><span id="inspect-mode">Chưa chọn</span><h3 id="inspect-title">Chọn một số trên trang</h3></div>
            </div>
            <p id="inspect-summary">Khi chọn số, hệ thống hiển thị điểm AI, xác suất, bằng chứng và các đường cầu vị trí tốt nhất.</p>
            <div class="inspect-meta">
              <div><span>Điểm AI</span><strong id="inspect-score">—</strong></div>
              <div><span>Xác suất</span><strong id="inspect-prob">—</strong></div>
            </div>
            <p><b>Lý do chính:</b> <span id="inspect-reason">—</span></p>
            <p><b>Bằng chứng:</b> <span id="inspect-evidence">—</span></p>
            <h4>Đường cầu vị trí nổi bật</h4>
            <ul class="position-list" id="inspect-lines">
              <li>Bấm vào số để xem chi tiết.</li>
            </ul>
          </aside>
          <div class="two-col">
            {_render_table(title='Vị trí cầu lô tô nổi bật', subtitle='Các đường cầu lô tô có điểm quy tắc cao nhất hiện tại.', df=evidence_loto, columns=['number_str', 'rule_kind', 'lag_days', 'path_line', 'p_mean', 'hits', 'trials', 'current_streak', 'rule_score', 'reason'], limit=10, dense=False, searchable=True)}
            {_render_table(title='Vị trí cầu ĐB nổi bật', subtitle='Các đường cầu ĐB có điểm quy tắc cao nhất hiện tại.', df=evidence_de, columns=['number_str', 'rule_kind', 'lag_days', 'path_line', 'p_mean', 'hits', 'trials', 'current_streak', 'rule_score', 'reason'], limit=10, dense=False, searchable=True, number_mode='de')}
          </div>
        </div>
      </section>

      <section id="backtest" class="section">
        <div class="section-title">
          <div>
            <div class="section-kicker">Kiểm định mô hình</div>
            <h2>Kiểm định lại AI/ML và thống kê điều kiện</h2>
            <p>Dùng kiểm định lại để đánh giá chất lượng xếp hạng trên lịch sử; không dùng để cam kết kết quả tương lai.</p>
          </div>
        </div>
        <div class="two-col">
          {_render_table(title='Báo cáo kiểm định lô tô', subtitle='Tỷ lệ trúng theo nhóm K và chỉ số hiệu chỉnh của mô hình lô tô.', df=report_loto, columns=['mode', 'top_k', 'validation_days', 'hit_any_days', 'hit_any_rate', 'avg_hits_per_day', 'val_brier', 'val_logloss'], limit=8, dense=False)}
          {_render_table(title='Báo cáo kiểm định ĐB', subtitle='Tỷ lệ trúng theo nhóm K và chỉ số hiệu chỉnh của mô hình ĐB.', df=report_de, columns=['mode', 'top_k', 'validation_days', 'hit_any_days', 'hit_any_rate', 'avg_hits_per_day', 'val_brier', 'val_logloss'], limit=8, dense=False)}
          {_render_table(title='Điều kiện ĐB hôm trước → lô tô hôm sau', subtitle='Các cặp điều kiện thường gặp, lọc theo số lần và tỷ lệ có điều kiện.', df=conditional_special, columns=['prev_special_2d', 'next_loto', 'count', 'base_count', 'conditional_rate'], limit=12, dense=False, searchable=True)}
          {_render_table(title='Điều kiện lô tô hôm trước → lô tô hôm sau', subtitle='Quan hệ chuyển tiếp giữa lô tô hôm trước và lô tô ngày sau.', df=conditional_loto, columns=['prev_loto', 'next_loto', 'count', 'base_count', 'conditional_rate'], limit=12, dense=False, searchable=True)}
          {_render_table(title='Giải nhất lâu chưa về', subtitle='Một bảng phụ để đối chiếu giải nhất với nhịp chung.', df=first_prize, columns=['number_str', 'last_seen', 'current_gap', 'hit_count', 'mean_gap', 'max_gap'], limit=10, dense=False)}
          {_render_table(title='Tần suất lô tô nổi bật tháng hiện tại', subtitle='Bảng hỗ trợ đọc số liệu bên cạnh ma trận.', df=_sort_top(loto_snapshot[loto_snapshot['period_kind'] == 'month'] if not loto_snapshot.empty and 'period_kind' in loto_snapshot.columns else loto_snapshot, 'freq', 10), columns=['number_str', 'freq', 'days_hit', 'hit_rate', 'avg_per_draw', 'z_score', 'rank_in_period'], limit=10, dense=False)}
        </div>
      </section>

      <div class="footer">
        Sinh lúc {html.escape(generated_at)}. AI/ML và cầu-kèo là tín hiệu thống kê từ lịch sử, không phải bảo đảm kết quả xổ số tương lai.
      </div>
    </main>
  </div>

  <script type="application/json" id="landing-data">{data_json}</script>
  <script>
    const APP_DATA = JSON.parse(document.getElementById('landing-data').textContent);

    function fmtPercent(value) {{
      const n = Number(value || 0);
      if (!Number.isFinite(n)) return '—';
      return (n > 1 ? n : n * 100).toFixed(1) + '%';
    }}

    function showNumber(mode, number) {{
      const n = String(number || '').padStart(2, '0').slice(-2);
      const m = mode || 'loto';
      const data = (APP_DATA.explain && APP_DATA.explain[m] && APP_DATA.explain[m][n]) || null;
      document.getElementById('inspect-num').textContent = n;
      document.getElementById('inspect-mode').textContent = m === 'de' ? 'Đặc biệt' : 'Loto';
      document.getElementById('inspect-title').textContent = data ? 'Căn cứ thống kê cho số ' + n : 'Chưa có căn cứ cho số ' + n;
      document.getElementById('inspect-score').textContent = data && data.score ? Number(data.score).toFixed(1) : '—';
      document.getElementById('inspect-prob').textContent = data && data.prob ? fmtPercent(data.prob) : '—';
      document.getElementById('inspect-reason').textContent = data && data.reason ? data.reason : 'Chưa có lý do AI/ML nổi bật.';
      document.getElementById('inspect-evidence').textContent = data && data.evidence ? data.evidence : 'Chưa có bằng chứng định lượng.';
      document.getElementById('inspect-summary').textContent = data && data.summary ? data.summary : 'Số này chưa nằm trong nhóm giải thích AI/ML hoặc chưa có đường cầu vị trí đủ mạnh.';
      const list = document.getElementById('inspect-lines');
      list.innerHTML = '';
      const lines = data && Array.isArray(data.lines) ? data.lines : [];
      if (!lines.length) {{
        const li = document.createElement('li');
        li.textContent = 'Chưa có đường cầu vị trí đủ điều kiện hiển thị.';
        list.appendChild(li);
      }} else {{
        lines.forEach(line => {{
          const li = document.createElement('li');
          li.innerHTML = '<b>' + (line.path_line || 'Đường cầu') + '</b><br>' +
            '<span>Loại: ' + (line.kind || '—') +
            ' · Lag: ' + (line.lag || '—') +
            ' · P: ' + (line.p_mean || '—') +
            ' · Trúng/Mẫu: ' + (line.hits || '—') + '/' + (line.trials || '—') +
            ' · Nhịp: ' + (line.streak || '—') +
            ' · Điểm: ' + (line.score || '—') + '</span><br>' +
            '<span>' + (line.reason || '') + '</span>';
          list.appendChild(li);
        }});
      }}
    }}

    document.querySelectorAll('[data-number]').forEach(el => {{
      el.addEventListener('click', () => {{
        showNumber(el.dataset.mode || 'loto', el.dataset.number);
      }});
    }});

    const navLinks = [...document.querySelectorAll('.side-nav a')];
    const sections = navLinks
      .map(a => document.querySelector(a.getAttribute('href')))
      .filter(Boolean);
    const observer = new IntersectionObserver(entries => {{
      entries.forEach(entry => {{
        if (entry.isIntersecting) {{
          navLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + entry.target.id));
        }}
      }});
    }}, {{ rootMargin: '-30% 0px -60% 0px', threshold: 0 }});
    sections.forEach(section => observer.observe(section));

    document.querySelectorAll('.table-filter').forEach(input => {{
      input.addEventListener('input', () => {{
        const q = input.value.trim().toLowerCase();
        const table = input.parentElement.querySelector('table');
        if (!table) return;
        table.querySelectorAll('tbody tr').forEach(tr => {{
          tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none';
        }});
      }});
    }});

    const firstSignal = document.querySelector('[data-number]');
    if (firstSignal) showNumber(firstSignal.dataset.mode || 'loto', firstSignal.dataset.number);
  </script>
</body>
</html>
"""
    return html_doc


def build_landing_page(*, repo_root: Path) -> list[Path]:
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    html_doc = "\n".join(
        line.rstrip() for line in _render_html(repo_root).splitlines()
    ) + "\n"
    desktop_doc = "\n".join(
        line.rstrip()
        for line in _render_html(repo_root, desktop_view=True).splitlines()
    ) + "\n"
    out_index = docs_dir / "index.html"
    out_landing = docs_dir / "landing.html"
    out_desktop = docs_dir / "landing_desktop.html"
    out_index.write_text(html_doc, encoding="utf-8")
    out_landing.write_text(html_doc, encoding="utf-8")
    out_desktop.write_text(desktop_doc, encoding="utf-8")
    return [out_index, out_landing, out_desktop]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dựng trang tổng hợp thống kê hiện đại."
    )
    parser.add_argument("--repo-root", default=".", help="Thư mục gốc kho mã")
    args = parser.parse_args()
    outputs = build_landing_page(repo_root=Path(args.repo_root).resolve())
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
