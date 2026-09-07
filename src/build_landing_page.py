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
from ui_theme import SITE_NAV, readable_ink, stylesheet_link, write_stylesheet
from web_security import json_for_html_script, security_meta_tags


NAV_ITEMS: list[tuple[str, str, str]] = [
    ("tong-quan", "Tổng quan", "Cập nhật, tín hiệu nóng và đường dẫn nhanh"),
    ("ket-qua", "Kết quả ngày", "Bảng kết quả đầy đủ theo giải"),
    ("chuc-don-vi", "Chục × đơn vị", "Ma trận đầu/chục và đuôi/đơn vị"),
    ("ai-ml", "AI/ML cầu-kèo", "Xếp hạng xác suất và lý do thống kê"),
    ("tan-suat-loto", "Tần suất loto", "Ma trận ngày, tuần, tháng, năm"),
    ("tan-suat-de", "Tần suất ĐB", "Ma trận đặc biệt theo kỳ"),
    ("gan-nhip", "Gan / nhịp", "Số lâu chưa về và áp lực nhịp"),
    ("cap-lon", "Cặp lộn", "45 cặp đảo chiều và 5 cặp kép-bóng"),
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


#: Nhãn cột rút gọn cho hai bảng đường cầu. Tiêu đề dài như "Độ trễ (ngày)"
#: hay "Chuỗi hiện tại" đặt sàn bề rộng cho cột chỉ chứa MỘT chữ số — đo được
#: 99px và 102px cho ô hiện "13" và "3". Rút gọn ở đây thay vì sửa
#: COLUMN_LABELS dùng chung, vì bảng thống kê bên trang khác còn chỗ rộng.
PATH_TABLE_LABELS = {
    "lag_days": "Độ trễ",
    "current_streak": "Chuỗi",
    "hit_ratio": "Trúng/Mẫu",
    "p_mean": "Tỷ lệ",
    "rule_score": "Điểm",
}

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
    except (TypeError, ValueError):
        return default
    return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _fmt2(value: Any) -> str:
    token = str(value).strip()
    if re.fullmatch(r"[0-9]{1,2}(?:\.0+)?", token) is None:
        return ""
    number = int(float(token))
    return f"{number:02d}" if 0 <= number <= 99 else ""


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


def _style_for_value(
    value: float, min_value: float, max_value: float, palette: str
) -> tuple[str, str]:
    low, high = PALETTES.get(palette, PALETTES["blue"])
    span = max(max_value - min_value, 1e-9)
    t = (value - min_value) / span
    bg = _mix(low, high, t)
    # Chọn màu chữ theo tỉ lệ tương phản thực tế thay vì ngưỡng độ sáng cố
    # định. Ngưỡng cũ (luminance < 0.42) để lọt cả một dải nền tầm trung: đo
    # trên trang thật, chữ trắng trên nền #8aacf5 chỉ đạt 2,26:1.
    return bg, readable_ink(bg)


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


def _current_period_matrix(
    repo_root: Path, mode: str, period: str, value_col: str = "freq"
) -> dict[str, float]:
    df = _read_csv(
        repo_root / "data" / "advanced" / f"period_snapshot_{mode}_current.csv", dtype=str
    )
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
        explain = _read_csv(
            repo_root / "data" / "ai_ml" / f"cau_number_explain_{mode}.csv", dtype=str
        )
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
        evidence = _read_csv(
            repo_root / "data" / "ai_ml" / f"cau_position_evidence_{mode}.csv", dtype=str
        )
        if not evidence.empty:
            sort_cols = [c for c in ["number_str", "rule_score"] if c in evidence.columns]
            if sort_cols:
                evidence["_score"] = pd.to_numeric(
                    evidence.get("rule_score", 0), errors="coerce"
                ).fillna(0)
                evidence = evidence.sort_values(
                    ["number_str", "_score"], ascending=[True, False]
                ).drop(columns=["_score"])
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


def _render_live_block(latest: Mapping[str, Any]) -> str:
    """Khối quay trực tiếp, đặt ở vị trí ưu tiên hàng đầu.

    Trang này là HTML tĩnh sinh sẵn, nên không thể tự biết lúc người dùng mở
    trang là mấy giờ. Việc chuyển giữa "đang quay" và "đã có kết quả" do
    JavaScript quyết định theo giờ Việt Nam ngay trên máy người xem — nếu để
    phía dựng trang quyết định, mọi người mở trang sau đó sẽ thấy một trạng thái
    đã cũ.
    """
    date_text = html.escape(str(latest.get("date") or "—"))
    return f"""
      <section id="live" class="section card" data-live-block>
        <div class="card-head">
          <div>
            <p class="eyebrow">Quay thưởng</p>
            <h3 id="live-title">Kết quả ngày {date_text}</h3>
            <p id="live-note">Kỳ quay diễn ra lúc 18:30 giờ Việt Nam hằng ngày.</p>
          </div>
          <a class="btn secondary" href="live.html">Mở trang quay trực tiếp</a>
        </div>
        <div id="live-status" class="live-status" role="status" aria-live="polite">
          <span class="live-dot" aria-hidden="true"></span>
          <span id="live-status-text">Đang xác định trạng thái kỳ quay…</span>
        </div>
      </section>
    """


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
    return (
        "<div class='result-scroll'><table class='result-table'><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


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
    # Trên màn hẹp ma trận có min-width 430px; phải bọc trong .matrix-wrap để
    # phần dư cuộn ngang trong khung thay vì đẩy cả trang tràn ra ngoài.
    return f"<div class='matrix-wrap'><div class='tiny-matrix'>{header}{''.join(cells)}</div></div>"


def _render_head_tail_lists(latest: Mapping[str, Any]) -> str:
    def block(title: str, data: Mapping[str, Sequence[str]]) -> str:
        rows = []
        for digit in range(10):
            values = data.get(str(digit), [])
            badges = (
                "".join(f"<span class='mini-badge'>{html.escape(v)}</span>" for v in values)
                or "<span class='muted'>—</span>"
            )
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
        <div class="matrix-grid">{header}{"".join(cells)}</div>
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


def _hit_ratio_column(df: pd.DataFrame) -> pd.DataFrame:
    """Gộp ``hits`` và ``trials`` thành một cột ``hit_ratio`` dạng ``9/391``.

    Hai cột riêng tốn 158px để hiện "3" và "379" — bề rộng do TIÊU ĐỀ "Số lần
    trúng" đặt sàn chứ không phải do dữ liệu. Gộp lại còn ~90px mà không mất
    thông tin nào, và "trúng/mẫu" đúng là cách khung căn cứ bên trái đã dùng.

    Args:
        df: Bảng có hai cột ``hits`` và ``trials``.

    Returns:
        Bản sao có thêm cột ``hit_ratio``; trả nguyên bản nếu thiếu cột nguồn.
    """
    if df.empty or not {"hits", "trials"} <= set(df.columns):
        return df
    out = df.copy()
    out["hit_ratio"] = [
        f"{h}/{t}" for h, t in zip(out["hits"], out["trials"], strict=True)
    ]
    return out


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
    labels: Mapping[str, str] | None = None,
) -> str:
    rows = _df_to_rows(df, columns, limit=limit)
    if not rows:
        body = "<div class='empty'>Chưa có dữ liệu.</div>"
    else:
        table_cols = list(rows[0].keys())
        # Lớp theo tên cột để CSS chỉnh bề rộng từng cột. Cách thay thế là
        # nth-child, nhưng chỉ số cột đổi theo mỗi lần gọi _render_table nên
        # quy tắc sẽ trượt sang cột khác lúc nào không hay.
        overrides = dict(labels or {})
        thead = "".join(
            f'<th class="col-{html.escape(c)}">'
            f"{html.escape(overrides.get(c) or _pretty_col(c))}</th>"
            for c in table_cols
        )
        trs = []
        for row in rows:
            cells = []
            for c in table_cols:
                value = row.get(c, "")
                s = str(value)
                cls = f' class="col-{html.escape(c)}"'
                if c.endswith("rate") or c in {"hit_any_rate", "prob", "p_mean"}:
                    # p_mean từng in nguyên 8 chữ số thập phân ("0.02544529"):
                    # vừa rộng vô ích vừa không ai đọc tới số thứ tám.
                    s = _pct(value)
                elif c in {"number", "number_str", "next_loto", "prev_loto", "prev_special_2d"}:
                    s = _fmt2(value)
                    s = f"<button class='num-link' data-mode='{number_mode}' data-number='{s}'>{s}</button>"
                    cells.append(f"<td{cls}>{s}</td>")
                    continue
                elif c == "rule_score":
                    s = _fmt_num(value, decimals=1)
                elif c == "mode":
                    s = mode_label(value)
                elif c in {"score_band", "period_kind", "stage", "status"}:
                    s = str(value_label(value))
                cells.append(f"<td{cls}>{html.escape(s)}</td>")
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
        df = _read_csv(repo_root / "data" / "advanced" / "special_week_board.csv", dtype=str).tail(
            8
        )
        title = "Bảng ĐB theo tuần"
        subtitle = "8 tuần gần nhất, chia theo thứ trong tuần."
        cols = ["week_key", "T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    else:
        df = _read_csv(repo_root / "data" / "advanced" / "special_month_board.csv", dtype=str).tail(
            4
        )
        title = "Bảng ĐB theo tháng"
        subtitle = "4 tháng gần nhất, giữ đủ cột ngày 01–31."
        cols = ["month_key"] + [f"{i:02d}" for i in range(1, 32)]
    return _render_table(
        title=title, subtitle=subtitle, df=df, columns=cols, limit=10, dense=True, searchable=False
    )


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
            group_label = GROUP_LABELS.get(group, group)
            part["label"] = part["group_value"].map(lambda x, label=group_label: f"{label} {x}")
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

    loto_snapshot = _read_csv(
        repo_root / "data" / "advanced" / "period_snapshot_loto_current.csv", dtype=str
    )
    de_snapshot = _read_csv(
        repo_root / "data" / "advanced" / "period_snapshot_de_current.csv", dtype=str
    )

    ai_loto = _sort_top(
        _read_csv(repo_root / "data" / "ai_ml" / "cau_keo_loto_top20.csv", dtype=str),
        "cau_score",
        10,
    )
    ai_de = _sort_top(
        _read_csv(repo_root / "data" / "ai_ml" / "cau_keo_de_top20.csv", dtype=str), "cau_score", 10
    )
    loto_rhythm = _sort_top(
        _read_csv(repo_root / "data" / "advanced" / "loto_rhythm.csv", dtype=str), "current_gap", 12
    )
    de_rhythm = _sort_top(
        _read_csv(repo_root / "data" / "advanced" / "de_rhythm.csv", dtype=str), "current_gap", 12
    )
    reverse_pairs = _read_csv(
        repo_root / "data" / "advanced" / "reverse_pair_frequency_current.csv", dtype=str
    )
    if not reverse_pairs.empty and "period_kind" in reverse_pairs.columns:
        reverse_pairs = reverse_pairs[reverse_pairs["period_kind"] == "month"]
    reverse_pairs = _sort_top(reverse_pairs, "freq", 12)

    conditional_special = _read_csv(
        repo_root / "data" / "advanced" / "conditional_loto_after_special_top500.csv", dtype=str
    )
    conditional_loto = _read_csv(
        repo_root / "data" / "advanced" / "conditional_loto_after_loto_top500.csv", dtype=str
    )
    first_prize = _sort_top(
        _read_csv(repo_root / "data" / "advanced" / "first_prize_overdue.csv", dtype=str),
        "current_gap",
        10,
    )
    report_loto = _read_csv(repo_root / "data" / "ai_ml" / "cau_keo_report_loto.csv", dtype=str)
    report_de = _read_csv(repo_root / "data" / "ai_ml" / "cau_keo_report_de.csv", dtype=str)
    evidence_loto = _sort_top(
        _read_csv(repo_root / "data" / "ai_ml" / "cau_position_evidence_loto.csv", dtype=str),
        "rule_score",
        10,
    )
    evidence_de = _sort_top(
        _read_csv(repo_root / "data" / "ai_ml" / "cau_position_evidence_de.csv", dtype=str),
        "rule_score",
        10,
    )

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
        (
            "Chuỗi ngày",
            str(_history_days(repo_root)),
            "Số kỳ liên tục trong data/xsmb.csv",
            "blue",
        ),
        (
            "Chất lượng mô hình",
            _model_grade(repo_root),
            "Hạng theo kỹ năng log-loss so với nền",
            "green",
        ),
    ]

    dock_html = _render_dock()
    nav_fallback = _render_nav_fallback()

    live_block = _render_live_block(latest)

    stat_tiles = "\n".join(
        f"<div class='metric-tile {palette}' data-long='{str(len(value) >= 9).lower()}'>"
        f"<span>{html.escape(label)}</span><strong>{html.escape(value)}</strong>"
        f"<em>{html.escape(desc)}</em></div>"
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
    ai_pills = (
        "".join(
            f"<button class='signal-pill' data-mode='loto' data-number='{_fmt2(row.get('number_str', row.get('number', '')))}'>"
            f"<b>{_fmt2(row.get('number_str', row.get('number', '')))}</b>"
            f"<span>{html.escape(str(row.get('primary_reason', 'Tín hiệu AI/ML')))}</span>"
            f"</button>"
            for row in ai_summary_rows
        )
        or "<span class='muted'>Chưa có dữ liệu AI/ML.</span>"
    )

    data_json = json_for_html_script({"explain": explain_map, "generated_at": generated_at})
    body_class = ' class="desktop-view"' if desktop_view else ""

    html_doc = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  {security_meta_tags()}
  {stylesheet_link()}
  <title>Trung tâm phân tích xổ số</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --panel-soft: #f8fafc;
      --ink: #0f172a;
      --muted: #55606f;
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
      font-family: var(--vla-font);
    }}
    a {{ color: inherit; text-decoration: none; }}
    button {{ font: inherit; }}
    /* Trang này CỐ Ý giữ một bảng màu sáng duy nhất, không theo chế độ tối của
       hệ điều hành. Lý do: các ma trận nhiệt ở đây tô màu bằng hàm trộn hex
       trong Python (_style_for_value), không đi qua biến CSS — nên đảo token
       chỉ lật được phần khung mà không lật được phần dữ liệu, tạo ra bảng màu
       lai. Bản thử trước đó đúng là như vậy: ghi đè 6 token, bỏ sót --muted và
       --panel-soft, làm chữ #e8eef6 nằm trên nền #f8fafc — đo được 1,12:1.
       Một chế độ tối nửa vời tệ hơn hẳn một chế độ sáng nhất quán. */
    /* Không còn cột sidebar. Sidebar cũ rộng 292px trên màn 1680px — 17,4%
       chiều ngang dành cho 17 liên kết mà phần lớn thời gian không ai bấm.
       Điều hướng chuyển sang dock nổi ở chân trang; toàn bộ phần đó trả về
       cho nội dung. */
    .app {{
      min-height: 100vh;
      padding-bottom: calc(76px + 32px);   /* chừa chỗ cho dock */
    }}
    .app > * {{ min-width: 0; }}
    /* Nhãn chỉ dành cho trình đọc màn hình: dock dùng biểu tượng, và một nút
       chỉ có icon sẽ được đọc thành "nút" trống nếu thiếu nhãn này. */
    .sr-only {{
      position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
      overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
    }}

    /* Điều hướng dự phòng cuối trang. */
    /* Dàn đều hết chiều ngang container thay vì dồn về trái. Năm hàng trước
       đây đều rộng 1684px nhưng nội dung dồn cả sang mép trái.
       Cách làm là lưới cột — mỗi nhóm SITE_NAV một cột bằng nhau — chứ không
       phải space-between trên từng <ul>: nhóm chỉ có 2-4 mục thì
       space-between đẩy chúng dính hai mép và chừa khoảng trống lớn ở giữa. */
    .nav-fallback {{
      margin-top: 48px; padding-top: 24px;
      border-top: 1px solid var(--line); font-size: 13px;
      display: grid; gap: 24px 32px;
      grid-template-columns: repeat(auto-fit, minmax(min(180px, 100%), 1fr));
    }}
    .nav-fallback > section {{ min-width: 0; }}
    .nav-fallback h2 {{
      font-size: 12px; letter-spacing: .06em; text-transform: uppercase;
      color: var(--muted); margin: 0 0 8px; font-weight: 600;
    }}
    .nav-fallback ul {{
      list-style: none; padding: 0; margin: 0;
      display: flex; flex-direction: column; gap: 8px;
    }}

    /* ── Dock điều hướng nổi ──────────────────────────────────────────────
       17 đích là quá nhiều cho một dock kiểu macOS: icon sẽ nhỏ hơn 32px và
       tooltip chồng nhau. SITE_NAV vốn đã chia 5 nhóm, nên dock hiện 5 icon
       nhóm và mở popover khi hover HOẶC focus — chỉ hover thôi thì người dùng
       bàn phím không bao giờ tới được các mục con. */
    .dock {{
      position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%);
      z-index: 60; max-width: calc(100vw - 32px);
    }}
    /* Kính mờ 30%. Nền 84% trước đây gần như đục hẳn nên không còn là
       glassmorphism; ở mức 30% phải tăng độ tương phản viền và bóng đổ để
       thanh vẫn tách khỏi nội dung phía sau. */
    .dock-inner {{
      display: flex; align-items: center; gap: 4px;
      padding: 6px 10px; border-radius: 999px;
      background: rgba(15, 23, 42, .30);
      border: 1px solid rgba(255,255,255,.18);
      box-shadow: 0 10px 36px rgba(15,23,42,.34), inset 0 1px 0 rgba(255,255,255,.10);
      backdrop-filter: blur(12px) saturate(1.8);
      -webkit-backdrop-filter: blur(12px) saturate(1.8);
    }}
    /* Không có backdrop-filter thì thấy nền đặc — mất hiệu ứng kính nhưng
       vẫn đọc được, đó là điều quan trọng. */
    @supports not (backdrop-filter: blur(1px)) {{
      .dock-inner {{ background: #0f172a; }}
    }}
    .dock-group {{ position: relative; }}
    /* Nhãn chuyển thành tooltip thay vì chữ dưới icon: hai dòng làm thanh cao
       114px, quá thô so với mức 48–56px cần đạt. */
    .dock-btn {{
      display: grid; place-items: center;
      padding: 0; background: none; border: 0; cursor: pointer;
      border-radius: 12px; color: #e5e7eb;
    }}
    .dock-ic {{
      display: grid; place-items: center; width: 40px; height: 40px; font-size: 18px;
      border-radius: 11px; background: rgba(255,255,255,.08);
      border: 1px solid rgba(255,255,255,.12);
      transition: transform .24s ease-in-out, background .2s ease-in-out;
    }}
    .dock-btn:hover .dock-ic, .dock-btn:focus-visible .dock-ic {{
      transform: scale(1.18);
      background: rgba(124,58,237,.42);
    }}
    .dock-btn:focus-visible {{ outline: 2px solid #93c5fd; outline-offset: 2px; }}

    /* Tooltip thay cho nhãn cố định. */
    .dock-name {{
      position: absolute; bottom: calc(100% + 8px); left: 50%;
      transform: translateX(-50%) translateY(4px);
      padding: 4px 9px; border-radius: 7px; white-space: nowrap;
      font-size: 11px; font-weight: 600; letter-spacing: .02em;
      background: #0f172a; color: #f1f5f9;
      border: 1px solid rgba(255,255,255,.12);
      opacity: 0; pointer-events: none;
      transition: opacity .18s ease-in-out, transform .18s ease-in-out;
    }}
    .dock-btn:hover .dock-name, .dock-btn:focus-visible .dock-name {{
      opacity: 1; transform: translateX(-50%) translateY(0);
    }}
    /* Khi popover đang mở thì ẩn tooltip — hai lớp nổi chồng nhau gây rối. */
    .dock-group:hover .dock-name, .dock-group:focus-within .dock-name {{ opacity: 0; }}
    .dock-pop {{
      position: absolute; bottom: calc(100% + 14px); left: 50%;
      transform: translateX(-50%) translateY(6px);
      min-width: 232px; padding: 8px;
      background: rgba(255,255,255,.97); border: 1px solid var(--line);
      border-radius: 16px; box-shadow: 0 18px 44px rgba(15,23,42,.26);
      backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
      opacity: 0; visibility: hidden; pointer-events: none;
      /* Độ trễ khi ĐÓNG (0.22s) nhưng không trễ khi MỞ. Rê chuột ra ngoài
         trong chớp mắt sẽ không làm menu tắt ngay, nên người dùng có thời gian
         quay lại — đây là nửa thứ hai của cơ chế chống tắt đột ngột. */
      transition: opacity .18s ease-in-out .22s,
                  transform .18s ease-in-out .22s,
                  visibility 0s linear .40s;
    }}
    /* CẦU NỐI HOVER. Giữa nút và popover có khe hở 14px; con trỏ đi qua khe đó
       rời khỏi cả hai phần tử nên :hover tắt và menu biến mất giữa chừng —
       đúng lỗi người dùng gặp. Phần tử giả này phủ kín khe, trong suốt, và
       thuộc về .dock-pop nên hover trên nó vẫn tính là hover trong nhóm. */
    .dock-pop::after {{
      content: ""; position: absolute; left: 0; right: 0;
      top: 100%; height: 18px;
    }}
    /* Mở rộng vùng bắt của cả nhóm xuống dưới nút, phòng khi con trỏ đi vòng. */
    .dock-group::after {{
      content: ""; position: absolute; left: -6px; right: -6px;
      top: -18px; bottom: -6px; z-index: -1;
    }}
    .dock-group:hover .dock-pop, .dock-group:focus-within .dock-pop {{
      opacity: 1; visibility: visible; pointer-events: auto;
      transform: translateX(-50%) translateY(0);
      /* Mở ngay, không trễ. Trễ khi mở làm menu có cảm giác chậm chạp. */
      transition: opacity .18s ease-in-out, transform .18s ease-in-out, visibility 0s;
    }}
    .dock-pop a {{
      display: flex; align-items: center; gap: 8px; padding: 8px 16px;
      border-radius: 12px; color: #1e293b; font-size: 13px;
      white-space: nowrap; text-decoration: none;
    }}
    .dock-pop a:hover {{ background: #f1f5f9; }}
    @media (max-width: 640px) {{
      .dock {{ left: 16px; right: 16px; transform: none; max-width: none; }}
      .dock-inner {{ overflow-x: auto; justify-content: flex-start; border-radius: 16px; }}
      .dock-btn {{ min-width: 52px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .dock-ic, .dock-pop {{ transition: none; }}
      .dock-btn:hover .dock-ic, .dock-btn:focus-visible .dock-ic {{ transform: none; }}
    }}

    /* Căn giữa container tổng. Trước đây .main không có margin:0 auto và chỉ
       bị giới hạn bằng max-width ở lớp desktop-view, nên ở màn 1920px nó dính
       sát mép trái và chừa 140px bên phải — lệch hẳn một phía. */
    .main {{
      min-width: 0;
      width: 100%;
      max-width: 1600px;
      margin: 0 auto;
      padding: 32px clamp(16px, 2.5vw, 40px);
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
    /* auto-fit + minmax cho 6 thẻ tự xuống 3 rồi 2 rồi 1 mà không cần một
       media query riêng cho từng mốc. */
    .metric-row {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
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
    .metric-tile strong {{
      font-size: clamp(26px, 4vw, 42px); line-height: 1; letter-spacing: -.04em;
      font-variant-numeric: tabular-nums;
    }}
    /* Giá trị dài (ngày "2026-09-06" là 10 ký tự) không vừa một dòng ở cỡ 42px
       trong thẻ 213px, và một ngày bị ngắt thành "2026-09-" / "06" thì vô
       nghĩa. Hạ cỡ chữ theo độ dài thay vì cho xuống dòng. */
    .metric-tile[data-long="true"] strong {{ font-size: clamp(20px, 2.1vw, 27px); }}
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
    /* Bảng kết quả có bề rộng tối thiểu do số giải quy định; ở 360px nó rộng
       520px và trước đây đẩy cả trang tràn ngang 187px. Cho phần dư cuộn
       trong khung riêng thay vì đẩy body. */
    .result-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; max-width: 100%; }}
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
    /* Grid item mặc định min-width:auto nên phình theo min-content của ma trận
       (430px) và tràn khỏi khung cha; min-width:0 cho phép nó co lại và để
       .matrix-wrap cuộn ngang phần dư. */
    .chuc-card {{
      position: sticky;
      top: 18px;
      min-width: 0;
    }}
    .result-combo > * {{ min-width: 0; }}
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
    /* Sau khi xếp dọc, thẻ biểu đồ chiếm trọn 1504px. Kéo một thanh dài
       ~1400px không cho biết thêm gì so với 560px, mà nhãn và trị số bị đẩy ra
       hai mép xa nhau tới mức phải đưa mắt qua cả màn hình mới ghép được cặp.

       Đổi thành nhiều CỘT thay vì giới hạn bề rộng rồi bỏ trống nửa thẻ: 10
       mục thành 2 cột × 5 hàng, vừa lấp hết chiều ngang vừa giảm nửa chiều
       cao. minmax(min(100%, 560px), 1fr) tự rơi về một cột khi hẹp mà không
       cần media query cho từng mốc. */
    .bar-list {{
      display: grid;
      gap: 9px 28px;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 560px), 1fr));
      grid-auto-flow: row;
    }}
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
    /* Hai khối nằm ngang, tự co giãn theo bề rộng còn lại và luôn bằng chiều
       cao nhau. minmax(0,1fr) là phần chống vỡ khung: thiếu nó, một bảng rộng
       bên trong sẽ đẩy cột phình ra và làm cả trang tràn ngang. */
    .live-status {{
      display: flex; align-items: center; gap: 10px;
      padding: 10px 14px; border-radius: 12px;
      background: var(--panel-2); border: 1px solid var(--line);
      font-size: 13px; color: var(--ink-soft);
    }}
    .live-dot {{
      width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto;
      background: #94a3b8;
    }}
    .live-status[data-state="live"] {{ border-color: #ef4444; color: #b91c1c; }}
    .live-status[data-state="live"] .live-dot {{
      background: #ef4444; animation: live-pulse 1.6s ease-in-out infinite;
    }}
    .live-status[data-state="done"] .live-dot {{ background: #22c55e; }}
    @keyframes live-pulse {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50% {{ opacity: .45; transform: scale(1.35); }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .live-status[data-state="live"] .live-dot {{ animation: none; }}
    }}

    .pair-row {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
      align-items: stretch;
      margin-bottom: 18px;
    }}
    .pair-row > * {{ min-width: 0; margin: 0; }}
    @media (max-width: 900px) {{ .pair-row {{ grid-template-columns: 1fr; }} }}

    /* Khu căn cứ: khung chọn số độc lập bên trái, hai bảng đường cầu gộp
       thành một khối bên phải. Bản ba cột trước đây cho mỗi bảng 445px — cột
       "Tỷ lệ" bị cắt mất và ~45% chiều cao mỗi cột bỏ trống. */
    .inspector {{
      display: grid;
      grid-template-columns: minmax(0, 34fr) minmax(0, 66fr);
      gap: 24px;
      /* stretch để hai ô cùng cao; chiều cao hàng do CỘT TRÁI quyết định nhờ
         thủ thuật ở .basis-cell ngay dưới. */
      align-items: stretch;
    }}
    .inspector > * {{ min-width: 0; }}

    /* Cân bằng hai cột bằng cách GIỮ khung trái trong tầm mắt, không phải bằng
       cách nhồi khối phải vào chiều cao của nó.

       Bản trước khoá chiều cao khối phải bằng đúng khung trái (absolute
       inset:0). Nó chữa được độ lệch 497px nhưng đẻ ra lỗi nặng hơn: hai bảng
       dữ liệu cần 874px và 1082px bị ép vào 511px mỗi bảng, và vì .table-wrap
       vốn đã có max-height + overflow riêng nên sinh ra HAI thanh cuộn lồng
       nhau trên cùng một trục — cuộn một cái không biết cái nào chạy. Tệ hơn,
       .table-wrap cao 520px nằm trong section cao 511px, tức con cao hơn cha
       nên hàng cuối bị cắt ngang.

       Cách đúng: khung trái là bảng chú giải cho khối phải, nên cho nó dính
       theo màn hình (đúng khuôn mẫu .right-rail đã dùng trong trang này). Khối
       phải chảy tự nhiên, không thanh cuộn trong, không cắt xén, và mắt vẫn
       thấy cả hai cùng lúc. sticky đòi ô lưới KHÔNG bị kéo giãn, nên phải có
       align-self:start — align-items:stretch của .inspector sẽ vô hiệu hoá
       sticky nếu thiếu dòng này. */
    .basis-cell {{ min-width: 0; }}
    .inspector > .inspect-panel {{
      align-self: start;
      position: sticky;
      top: 22px;
      max-height: calc(100vh - 44px);
      overflow: auto;
      scrollbar-width: thin;
    }}
    @media (max-width: 1100px) {{
      .inspector {{ grid-template-columns: minmax(0, 1fr); }}
      /* Xếp dọc thì không còn gì để dính theo; trả về luồng bình thường. */
      .inspector > .inspect-panel {{
        position: static; max-height: none; overflow: visible;
      }}
    }}

    /* Khối hợp nhất: đường phân cách chỉ nằm GIỮA hai phần, không nằm trên
       phần đầu — dùng bộ chọn anh em liền kề thay vì border-top cho mọi con. */
    .basis-merged {{
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: #fff;
      overflow: hidden;
    }}
    /* MỘT thanh cuộn cho mỗi bảng, không phải hai. Phần section chỉ là hộp
       chứa: nó không cuộn. Bảng chỉ hiện tối đa 10 hàng nên để nó cao tự
       nhiên là đọc được trọn vẹn, không cắt hàng nào. */
    .basis-merged > section {{ padding: 20px 24px; }}
    .basis-merged > section + section {{ border-top: 1px solid var(--line); }}
    .basis-merged > section > * {{ margin: 0; border: 0; box-shadow: none; padding: 0; }}
    /* Bỏ trần chiều cao của .table-wrap RIÊNG trong khối này: 10 hàng là giới
       hạn cứng ở nơi dựng bảng, nên không có nguy cơ bảng dài vô hạn. */
    .basis-merged .table-wrap {{ max-height: none; }}

    /* Bề rộng cột cho hai bảng đường cầu.

       Bảng có 10 cột trong ~925px. Để trình duyệt tự chia thì "Đường cầu" và
       "Căn cứ" — hai cột chữ dài nhất — bị bóp xuống ~90px và xuống 3-4 dòng,
       kéo hàng cao 83px ở bảng trên và 104px ở bảng dưới. Hai bảng cạnh nhau
       cao lệch nhau trông như lỗi dựng.

       Chữa bằng cách nói rõ cột nào ưu tiên bề rộng, thay vì để thuật toán
       chia đều cho cả cột chỉ chứa một con số. */
    .basis-merged .col-path_line {{ min-width: 190px; width: 26%; }}
    .basis-merged .col-reason {{ min-width: 170px; width: 22%; }}
    .basis-merged .col-rule_kind {{ width: 1%; }}
    /* Cột số: canh phải để so sánh theo cột dọc — mắt bắt được chênh lệch độ
       lớn ngay mà không phải đọc từng chữ số.

       nowrap chỉ áp cho ô DỮ LIỆU, không áp cho tiêu đề. Áp cả hai thì những
       tiêu đề dài như "Độ trễ (ngày)" hay "Chuỗi hiện tại" tự đặt sàn bề rộng
       cho cột, đẩy bảng lên 1051px trong khung 927px và sinh cuộn ngang. Tiêu
       đề xuống hai dòng là chuyện bình thường ở bảng dày; số bị ngắt dòng mới
       là lỗi. */
    .basis-merged th.col-lag_days,
    .basis-merged th.col-p_mean,
    .basis-merged th.col-hit_ratio,
    .basis-merged th.col-current_streak,
    .basis-merged th.col-rule_score {{ text-align: right; width: 1%; }}
    .basis-merged td.col-lag_days,
    .basis-merged td.col-p_mean,
    .basis-merged td.col-hit_ratio,
    .basis-merged td.col-current_streak,
    .basis-merged td.col-rule_score {{
      white-space: nowrap; text-align: right; width: 1%;
      font-variant-numeric: tabular-nums;
    }}
    .basis-merged .col-number_str {{ width: 1%; }}

    /* Tầng 1 của ma trận dữ liệu: 58/42. minmax(0,…) là bắt buộc — 1fr mặc
       định là minmax(auto,1fr) và bảng kết quả sẽ đẩy cột phình ra. */
    .matrix-top {{
      display: grid;
      grid-template-columns: minmax(0, 58fr) minmax(0, 42fr);
      gap: 24px;
      align-items: stretch;
      margin-bottom: 24px;
    }}
    .matrix-top > * {{ min-width: 0; margin: 0; }}
    @media (max-width: 1100px) {{ .matrix-top {{ grid-template-columns: minmax(0, 1fr); }} }}

    .matrix-full {{ width: 100%; margin-bottom: 24px; }}

    /* Ba bảng dự đoán ngày mai XẾP DỌC.

       Bản ba cột trước đây cho mỗi thẻ 485px ở màn 1920px và 435px ở 1440px.
       Bảng mô phỏng bên trong cần tối thiểu 520px cho khung giải, nên nó bị
       ép còn 131px và 81px — đo được tràn 389px và 439px, đúng cái thanh cuộn
       ngang nhìn thấy dưới bảng. Đồng thời hai biểu đồ bị kéo cao 1255px cho
       bằng thẻ mô phỏng, để lại một khoảng trắng lớn phía trên mỗi biểu đồ.

       Xếp dọc giải quyết cả hai: mỗi thẻ có trọn chiều ngang, và không thẻ
       nào phải cao theo thẻ khác. */
    .next-day {{
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 24px;
    }}
    .next-day > * {{ min-width: 0; margin: 0; }}
    /* Bảng mô phỏng do build_fun_prediction.py chèn vào SAU khi trang được
       dựng. Nếu bước đó không chạy thì section rỗng vẫn chiếm một hàng và để
       lại khoảng trống; ẩn hẳn đi. */
    .next-day > section:empty {{ display: none; }}
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
      /* Chỉ nới padding ở màn rộng. max-width giữ nguyên 1600px của lớp cơ sở:
         trước đây khối này ghi đè thành 1780px nên ba nơi khai báo .main lệch
         nhau và màn 1920px chạy rộng hơn khung thiết kế 1440-1600px. */
      .main {{
        padding: 32px clamp(28px, 3vw, 48px);
      }}
      /* Bề rộng khả dụng của .main đã trừ .side-nav (~247px) nên ở màn 1440px
         chỉ còn ~1062px. Ngưỡng cũ 760+18+360=1138px lớn hơn mức đó khiến
         cả lưới tràn ra ngoài viewport. */
      .layout-top {{
        grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
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
        /* align-content:end dồn ba viên xuống đáy, để lại 140px trống ở đầu
           panel — 39% chiều cao khối. Căn giữa thì khoảng trống chia đều hai
           đầu và khối cân về mặt thị giác. */
        align-content: center;
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
      /* Cột cố định 38px làm ma trận rộng 402px, vượt bề ngang khả dụng của
         màn hình nhỏ (~354px ở 390px) và đẩy cả trang tràn ngang. Cho cột co
         lại theo khung để ma trận luôn vừa màn hình. */
      .tiny-matrix, .matrix-grid {{
        grid-template-columns: 22px repeat(10, minmax(0, 1fr));
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
    body.desktop-view .side-nav a {{
      min-width: 0 !important;
    }}
    body.desktop-view .side-nav a small {{
      display: block !important;
    }}
    body.desktop-view .main {{
      max-width: min(100%, 1600px) !important;
      margin-inline: auto !important;
      padding: 32px clamp(28px, 3vw, 48px) !important;
    }}
    /* Cùng lý do như .layout-top ở trên: sau khi bỏ sidebar, .main dùng trọn
       chiều ngang nên ngưỡng cột phải nới theo. */
    body.desktop-view .layout-top {{
      grid-template-columns: minmax(0, 1fr) minmax(320px, 420px) !important;
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
      .dock, .hero-actions {{ display: none; }}
      .app {{ padding-bottom: 0; }}
      body {{ background: #fff; }}
      .card, .metric-tile, .hero {{ box-shadow: none; }}
    }}
  </style>
</head>
<body{body_class}>
  <div class="app">
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

      {live_block}

      <div class="metric-row">
        {stat_tiles}
      </div>

      <!-- Tầng 1: kết quả ngày (58%) cạnh phân bổ chục×đơn vị (42%), cân
           bằng chiều cao. Trước đây bảng kết quả chiếm trọn chiều ngang rồi
           đẩy hai bảng nhỏ xuống dưới, nên mắt phải cuộn giữa hai thứ vốn
           được đọc cùng nhau. -->
      <div class="matrix-top">
        <section id="ket-qua" class="section card">
          <div class="card-head">
            <div>
              <p class="eyebrow">Kết quả hàng ngày</p>
              <h3>XSMB ngày {html.escape(str(latest.get("date") or "—"))}</h3>
              <p>Bảng kết quả giữ đủ số 0 đầu theo chuẩn từng giải; bấm vào số để xem căn cứ AI/ML và đường cầu.</p>
            </div>
          </div>
          {_render_result_table(latest)}
        </section>
        <section id="chuc-don-vi" class="section card">
          <div class="card-head">
            <div>
              <p class="eyebrow">Phân bổ chữ số</p>
              <h3>Chục × đơn vị</h3>
              <p>Các số đã về hôm nay gom theo hàng chục/đầu và hàng đơn vị/đuôi.</p>
            </div>
          </div>
          {_render_head_tail_lists(latest)}
        </section>
      </div>

      <!-- Tầng 2: ma trận trải hết chiều ngang. Ma trận 10×10 trong cột 637px
           phải nén mỗi ô xuống dưới 60px; ở 1680px mỗi ô rộng gấp đôi. -->
      <section id="ma-tran-ngay" class="section card matrix-full">
        <div class="card-head">
          <div>
            <p class="eyebrow">Chục × đơn vị</p>
            <h3>Ma trận lô tô ngày</h3>
            <p>Hàng ngang là đơn vị, hàng dọc là hàng chục/đầu. Màu đậm hơn nghĩa là số xuất hiện nhiều lần hơn.</p>
          </div>
        </div>
        {_render_daily_matrix(latest)}
      </section>

      <!-- Ba bảng dự đoán trên MỘT hàng. Khối mô phỏng trước đây là một
           section rời phía trên, còn ĐB và lô tô nằm trong section khác, nên
           ba thứ cùng nói về ngày mai bị tách làm hai vùng cuộn. -->
      <section id="ai-ml" class="section">
        <div class="section-title">
          <div>
            <div class="section-kicker">Dự đoán vui</div>
            <h2>Ngày mai</h2>
            <p>Ba bảng dưới đây là điểm xếp hạng của mô hình, không phải xác suất đã hiệu chuẩn và không phải lời khuyên đặt cược.</p>
          </div>
        </div>
        <div class="next-day">
          <section id="mo-phong" class="section"></section>
          {_render_bar_card(title="Đặc biệt ngày mai", subtitle="Tín hiệu ĐB theo AI/ML, dùng để tham khảo xác suất tương đối.", df=ai_de, label_col="number_str", value_col="cau_score", palette="orange", mode="de", number_col="number_str", limit=10, value_decimals=1)}
          {_render_bar_card(title="Lô tô ngày mai", subtitle="Các số có điểm cầu-kèo cao nhất từ mô hình và thống kê lịch sử.", df=ai_loto, label_col="number_str", value_col="cau_score", palette="purple", mode="loto", number_col="number_str", limit=10, value_decimals=1)}
        </div>
      </section>

      <section id="tan-suat-loto" class="section">
        <div class="section-title">
          <div>
            <div class="section-kicker">Ma trận tần suất</div>
            <h2>Tần suất lô tô theo ngày / tuần / tháng / năm</h2>
            <p>Những phần có đủ 00–99 được thể hiện bằng ma trận để mắt nhận ra vùng nóng/lạnh nhanh hơn bảng dài.</p>
          </div>
        </div>
        <div class="matrix-two">
          {_render_matrix_card(title="Lô tô ngày hiện tại", subtitle="Tần suất 00–99 trong ngày kết quả mới nhất.", values=_current_period_matrix(repo_root, "loto", "day"), palette="blue", mode="loto")}
          {_render_matrix_card(title="Lô tô tuần hiện tại", subtitle="Cộng dồn lô tô trong tuần hiện tại.", values=_current_period_matrix(repo_root, "loto", "week"), palette="green", mode="loto")}
          {_render_matrix_card(title="Lô tô tháng hiện tại", subtitle="Cộng dồn lô tô trong tháng hiện tại.", values=_current_period_matrix(repo_root, "loto", "month"), palette="orange", mode="loto")}
          {_render_matrix_card(title="Lô tô năm hiện tại", subtitle="Cộng dồn lô tô trong năm hiện tại.", values=_current_period_matrix(repo_root, "loto", "year"), palette="purple", mode="loto")}
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
          {_render_matrix_card(title="ĐB tháng hiện tại", subtitle="Tần suất 2 số cuối giải đặc biệt trong tháng.", values=_current_period_matrix(repo_root, "de", "month"), palette="orange", mode="de")}
          {_render_matrix_card(title="ĐB năm hiện tại", subtitle="Tần suất 2 số cuối giải đặc biệt trong năm.", values=_current_period_matrix(repo_root, "de", "year"), palette="rose", mode="de")}
          {_render_matrix_card(title="Điểm AI lô tô", subtitle="Điểm AI/ML kết hợp tần suất, nhịp, điều kiện và cầu vị trí.", values=_ai_matrix(repo_root, "loto"), palette="purple", mode="loto", decimals=1)}
          {_render_matrix_card(title="Điểm AI ĐB", subtitle="Điểm AI/ML dành riêng cho 2 số cuối giải đặc biệt.", values=_ai_matrix(repo_root, "de"), palette="rose", mode="de", decimals=1)}
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
          {_render_matrix_card(title="Gan lô tô hiện tại", subtitle="Số ngày chưa về của từng bộ lô tô.", values=_rhythm_matrix(repo_root, "loto"), palette="green", mode="loto")}
          {_render_matrix_card(title="Gan ĐB hiện tại", subtitle="Số ngày chưa về của từng bộ ĐB.", values=_rhythm_matrix(repo_root, "de"), palette="rose", mode="de")}
          {_render_bar_card(title="Gan lô tô đứng đầu", subtitle="Các bộ lô tô có khoảng gan hiện tại cao nhất.", df=loto_rhythm, label_col="number_str", value_col="current_gap", palette="green", mode="loto", number_col="number_str", limit=12, value_decimals=0)}
          {_render_bar_card(title="Gan ĐB đứng đầu", subtitle="Các bộ ĐB có khoảng gan hiện tại cao nhất.", df=de_rhythm, label_col="number_str", value_col="current_gap", palette="rose", mode="de", number_col="number_str", limit=12, value_decimals=0)}
        </div>
      </section>

      <section id="cap-lon" class="section">
        <div class="section-title">
          <div>
            <div class="section-kicker">Cặp lộn / kép-bóng</div>
            <h2>Cặp lộn và cặp kép-bóng</h2>
            <p>Biểu đồ thanh phù hợp hơn ma trận vì cần so sánh xếp hạng từng cặp như 36–63, 69–96.</p>
          </div>
        </div>
        <div class="two-col">
          {_render_bar_card(title="Cặp lộn nổi bật trong tháng", subtitle="45 cặp đảo chiều và 5 cặp kép-bóng có tổng tần suất cao trong tháng hiện tại.", df=reverse_pairs, label_col="pair", value_col="freq", palette="sky", limit=12, value_decimals=0)}
          {_render_table(title="Chi tiết cặp lộn", subtitle="Có thêm số ngày về và số ngày cùng về để tránh nhìn nhầm chỉ theo tần suất.", df=reverse_pairs, columns=["pair", "freq", "days_hit", "cooccur_days", "avg_per_draw", "rank_in_period"], limit=12, dense=False)}
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
        {_render_group_bars(repo_root, "month")}
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
          {_render_special_board(repo_root, "week")}
          {_render_special_board(repo_root, "month")}
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
          <!-- Hai bảng gộp thành một khối, ĐB trên và lô tô dưới, ngăn bằng
               một đường mảnh. Trước đây chúng là hai cột hẹp 445px: cột "Tỷ lệ"
               bị cắt mất, ô nội dung xuống 5 dòng, và ~45% chiều cao mỗi cột
               bỏ trống. Gộp lại cho mỗi bảng gần 1090px và chia nhau chiều cao. -->
          <div class="basis-cell">
            <div class="basis-merged">
            <section>
              {_render_table(title="Vị trí cầu ĐB nổi bật", subtitle="Các đường cầu ĐB có điểm quy tắc cao nhất hiện tại.", df=_hit_ratio_column(evidence_de), columns=["number_str", "rule_kind", "lag_days", "path_line", "p_mean", "hit_ratio", "current_streak", "rule_score", "reason"], limit=10, dense=False, searchable=True, number_mode="de", labels=PATH_TABLE_LABELS)}
            </section>
            <section>
              {_render_table(title="Vị trí cầu lô tô nổi bật", subtitle="Các đường cầu lô tô có điểm quy tắc cao nhất hiện tại.", df=_hit_ratio_column(evidence_loto), columns=["number_str", "rule_kind", "lag_days", "path_line", "p_mean", "hit_ratio", "current_streak", "rule_score", "reason"], limit=10, dense=False, searchable=True, labels=PATH_TABLE_LABELS)}
            </section>
            </div>
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
          {_render_table(title="Báo cáo kiểm định lô tô", subtitle="Tỷ lệ trúng theo nhóm K và chỉ số hiệu chỉnh của mô hình lô tô.", df=report_loto, columns=["mode", "top_k", "validation_days", "hit_any_days", "hit_any_rate", "avg_hits_per_day", "val_brier", "val_logloss"], limit=8, dense=False)}
          {_render_table(title="Báo cáo kiểm định ĐB", subtitle="Tỷ lệ trúng theo nhóm K và chỉ số hiệu chỉnh của mô hình ĐB.", df=report_de, columns=["mode", "top_k", "validation_days", "hit_any_days", "hit_any_rate", "avg_hits_per_day", "val_brier", "val_logloss"], limit=8, dense=False)}
          {_render_table(title="Điều kiện ĐB hôm trước → lô tô hôm sau", subtitle="Các cặp điều kiện thường gặp, lọc theo số lần và tỷ lệ có điều kiện.", df=conditional_special, columns=["prev_special_2d", "next_loto", "count", "base_count", "conditional_rate"], limit=12, dense=False, searchable=True)}
          {_render_table(title="Điều kiện lô tô hôm trước → lô tô hôm sau", subtitle="Quan hệ chuyển tiếp giữa lô tô hôm trước và lô tô ngày sau.", df=conditional_loto, columns=["prev_loto", "next_loto", "count", "base_count", "conditional_rate"], limit=12, dense=False, searchable=True)}
          {_render_table(title="Giải nhất lâu chưa về", subtitle="Một bảng phụ để đối chiếu giải nhất với nhịp chung.", df=first_prize, columns=["number_str", "last_seen", "current_gap", "hit_count", "mean_gap", "max_gap"], limit=10, dense=False)}
          {_render_table(title="Tần suất lô tô nổi bật tháng hiện tại", subtitle="Bảng hỗ trợ đọc số liệu bên cạnh ma trận.", df=_sort_top(loto_snapshot[loto_snapshot["period_kind"] == "month"] if not loto_snapshot.empty and "period_kind" in loto_snapshot.columns else loto_snapshot, "freq", 10), columns=["number_str", "freq", "days_hit", "hit_rate", "avg_per_draw", "z_score", "rank_in_period"], limit=10, dense=False)}
        </div>
      </section>

      <div class="footer">
        Sinh lúc {html.escape(generated_at)}. AI/ML và cầu-kèo là tín hiệu thống kê từ lịch sử, không phải bảo đảm kết quả xổ số tương lai.
      </div>
      {nav_fallback}
    </main>
    {dock_html}
  </div>

  <script type="application/json" id="landing-data">{data_json}</script>
  <script>
    const APP_DATA = JSON.parse(document.getElementById('landing-data').textContent);

    /* Sidebar thu gọn. Trạng thái lưu trong localStorage nên giữ nguyên khi
       chuyển trang; mọi truy cập đều bọc try/catch vì trình duyệt ở chế độ
       riêng tư có thể ném lỗi ngay khi đọc. */
    /* Trạng thái kỳ quay tính theo giờ Việt Nam trên máy người xem, không phải
       theo giờ lúc dựng trang: trang tĩnh dựng một lần rồi phục vụ suốt ngày,
       nên một trạng thái ghi cứng sẽ sai với gần như mọi lượt xem. */
    (function () {{
      const box = document.getElementById('live-status');
      const text = document.getElementById('live-status-text');
      const note = document.getElementById('live-note');
      if (!box || !text) return;

      const DRAW_START = 18 * 60 + 10;   // 18:10 — bắt đầu quay các giải phụ
      const DRAW_END = 18 * 60 + 40;     // 18:40 — thường đã xong giải ĐB

      function vietnamMinutes() {{
        const parts = new Intl.DateTimeFormat('en-GB', {{
          timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', hour12: false
        }}).formatToParts(new Date());
        const get = (k) => Number(parts.find((p) => p.type === k).value);
        return get('hour') * 60 + get('minute');
      }}

      function refresh() {{
        const m = vietnamMinutes();
        if (m >= DRAW_START && m <= DRAW_END) {{
          box.setAttribute('data-state', 'live');
          text.textContent = 'Đang quay thưởng — mở trang trực tiếp để xem từng giải hiện dần.';
          if (note) note.textContent = 'Kết quả bên dưới là của kỳ trước cho tới khi kỳ hôm nay hoàn tất.';
        }} else {{
          box.setAttribute('data-state', 'done');
          text.textContent = 'Kỳ quay đã kết thúc. Bảng kết quả đầy đủ hiển thị bên dưới.';
          if (note) note.textContent = 'Kỳ quay diễn ra lúc 18:30 giờ Việt Nam hằng ngày.';
        }}
      }}

      refresh();
      window.setInterval(refresh, 30000);
    }})();


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
      list.replaceChildren();
      const lines = data && Array.isArray(data.lines) ? data.lines : [];
      if (!lines.length) {{
        const li = document.createElement('li');
        li.textContent = 'Chưa có đường cầu vị trí đủ điều kiện hiển thị.';
        list.appendChild(li);
      }} else {{
        lines.forEach(line => {{
          const li = document.createElement('li');
          const title = document.createElement('b');
          title.textContent = line.path_line || 'Đường cầu';
          const metrics = document.createElement('span');
          metrics.textContent = 'Loại: ' + (line.kind || '—') +
            ' · Lag: ' + (line.lag || '—') +
            ' · P: ' + (line.p_mean || '—') +
            ' · Trúng/Mẫu: ' + (line.hits || '—') + '/' + (line.trials || '—') +
            ' · Nhịp: ' + (line.streak || '—') +
            ' · Điểm: ' + (line.score || '—');
          const reason = document.createElement('span');
          reason.textContent = line.reason || '';
          li.append(title, document.createElement('br'), metrics, document.createElement('br'), reason);
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


def _render_dock() -> str:
    """Dựng dock điều hướng nổi từ :data:`SITE_NAV`.

    Sidebar cũ rộng 292px trên màn 1680px — 17,4% chiều ngang cho 17 liên kết
    mà phần lớn thời gian không ai bấm. Dock trả toàn bộ phần đó cho nội dung.

    17 đích là quá nhiều cho một dock kiểu macOS: icon sẽ nhỏ hơn 32px và
    tooltip chồng nhau. ``SITE_NAV`` vốn đã chia 5 nhóm, nên dock hiện 5 icon
    nhóm, mỗi icon mở một popover chứa các mục con.

    Returns:
        Chuỗi HTML của dock.
    """
    # Nhóm đầu tiên là các neo TRONG trang. Bỏ sidebar cũng bỏ luôn khả năng
    # nhảy tới từng mục, mà trang này cao khoảng 12 000px — cuộn tay từ đầu tới
    # phần kiểm định là hơn mười màn hình. SITE_NAV chỉ phủ 4 trong 12 neo đó.
    groups: list[tuple[str, tuple[tuple[str, str, str], ...]]] = [
        (
            "Trên trang",
            tuple((f"#{sid}", label, f"{index:02d}") for index, (sid, label, _) in enumerate(NAV_ITEMS, 1)),
        ),
        *SITE_NAV,
    ]
    parts = ['<nav class="dock" aria-label="Điều hướng chính"><div class="dock-inner">']
    for group, items in groups:
        group_id = "dock-" + re.sub(r"[^a-z0-9]+", "-", group.lower()).strip("-")
        icon = "☰" if group == "Trên trang" else (items[0][2] if items else "•")
        parts.append('<div class="dock-group">')
        parts.append(
            f'<button class="dock-btn" type="button" aria-haspopup="true"'
            f' aria-controls="{group_id}">'
            f'<span class="dock-ic" aria-hidden="true">{icon}</span>'
            f'<span class="dock-name">{html.escape(group)}</span></button>'
        )
        parts.append(f'<div class="dock-pop" id="{group_id}" role="menu">')
        for href, label, item_icon in items:
            parts.append(
                f'<a href="{href}" role="menuitem">'
                f'<span aria-hidden="true">{item_icon}</span>'
                f"<span>{html.escape(label)}</span></a>"
            )
        parts.append("</div></div>")
    parts.append("</div></nav>")
    return "".join(parts)


def _render_nav_fallback() -> str:
    """Điều hướng phẳng cuối trang, phòng khi CSS không tải được.

    Popover của dock ẩn bằng ``visibility:hidden``. Nếu CSS không tải được vì
    bất kỳ lý do gì thì trạng thái hiển thị rơi về mặc định của trình duyệt, và
    không nên phụ thuộc vào điều đó cho việc điều hướng. Một danh sách phẳng
    tốn vài trăm byte và loại bỏ hẳn rủi ro; nó cũng giữ nguyên khả năng dò của
    trình thu thập, vốn là lý do sidebar cũ tồn tại.

    Returns:
        Chuỗi HTML của khối điều hướng dự phòng.
    """
    parts = ['<nav class="nav-fallback" aria-label="Điều hướng đầy đủ">']
    for group, items in SITE_NAV:
        parts.append(f"<section><h2>{html.escape(group)}</h2><ul>")
        for href, label, _ in items:
            parts.append(f'<li><a href="{href}">{html.escape(label)}</a></li>')
        parts.append("</ul></section>")
    parts.append("</nav>")
    return "".join(parts)


def _history_days(repo_root: Path) -> int:
    """Số kỳ quay liên tục có trong tệp kết quả.

    Args:
        repo_root: Thư mục gốc của kho.

    Returns:
        Số dòng dữ liệu, hoặc 0 nếu chưa đọc được tệp.
    """
    try:
        return int(len(pd.read_csv(repo_root / "data" / "xsmb.csv")))
    except Exception:  # pragma: no cover - phụ thuộc trạng thái tệp
        return 0


def _model_grade(repo_root: Path) -> str:
    """Hạng chất lượng mô hình, quy từ kỹ năng log-loss đã đo.

    Thẻ này cố ý KHÔNG hiện một con số phần trăm. Kỹ năng đo được nằm ở mức
    một phần vạn, nên in ra "0,07%" sẽ gợi ý một độ chính xác mà phép đo không
    có. Một chữ cái nói đúng điều cần nói: mô hình có vượt nền hay không.

    Args:
        repo_root: Thư mục gốc của kho.

    Returns:
        Một trong ``"A"``, ``"B"``, ``"C"`` hoặc ``"—"`` khi chưa có số liệu.
    """
    try:
        scores = json.loads(
            (repo_root / "data" / "research" / "model_scores.json").read_text(encoding="utf-8")
        )
        modes = scores.get("modes", {})
        beats = sum(1 for entry in modes.values() if entry.get("beats_baseline"))
        if not modes:
            return "—"
        if beats == len(modes):
            return "A"
        return "B" if beats else "C"
    except Exception:  # pragma: no cover - phụ thuộc trạng thái tệp
        return "—"


def build_landing_page(*, repo_root: Path) -> list[Path]:
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    write_stylesheet(docs_dir)
    html_doc = "\n".join(line.rstrip() for line in _render_html(repo_root).splitlines()) + "\n"
    desktop_doc = (
        "\n".join(line.rstrip() for line in _render_html(repo_root, desktop_view=True).splitlines())
        + "\n"
    )
    out_index = docs_dir / "index.html"
    out_landing = docs_dir / "landing.html"
    out_desktop = docs_dir / "landing_desktop.html"
    out_index.write_text(html_doc, encoding="utf-8")
    out_landing.write_text(html_doc, encoding="utf-8")
    out_desktop.write_text(desktop_doc, encoding="utf-8")
    return [out_index, out_landing, out_desktop]


def main() -> None:
    parser = argparse.ArgumentParser(description="Dựng trang tổng hợp thống kê hiện đại.")
    parser.add_argument("--repo-root", default=".", help="Thư mục gốc kho mã")
    args = parser.parse_args()
    outputs = build_landing_page(repo_root=Path(args.repo_root).resolve())
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
