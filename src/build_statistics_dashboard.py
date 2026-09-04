from __future__ import annotations

"""Build a modern, self-contained statistical matrix dashboard.

The dashboard intentionally renders matrices, charts, and tables directly in
HTML/CSS so the report still works when docs/statistics.html is opened as a
standalone file outside the repository. It does not depend on external images,
CDNs, or JavaScript frameworks.
"""

import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from ui_locale import (
    COLUMN_LABELS,
    GROUP_LABELS,
    PERIOD_LABELS,
    mode_label,
    value_label,
)
from web_security import json_for_html_script, security_meta_tags

WEEKDAY_COLS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
PERIOD_TITLES = {
    "day": "Ngày hiện tại",
    "week": "Tuần hiện tại",
    "month": "Tháng hiện tại",
    "year": "Năm hiện tại",
}


def _read_csv(path: Path, *, dtype: dict[str, object] | str | None = None, nrows: int | None = None) -> pd.DataFrame:
    """Read a CSV defensively and return an empty DataFrame on bad/missing files."""
    try:
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame()
        return pd.read_csv(path, dtype=dtype, nrows=nrows, keep_default_na=False)
    except Exception:
        return pd.DataFrame()


def _read_json(path: Path) -> dict:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_columns(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """Return available columns in requested order; keep rendering if some are absent."""
    if df.empty:
        return df
    available = [c for c in columns if c in df.columns]
    return df.loc[:, available].copy() if available else df.copy()


def _num_series(df: pd.DataFrame, col: str) -> pd.Series:
    if df.empty or col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)


def _number_to_int(value: object) -> int | None:
    if pd.isna(value):
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        n = int(float(s))
    except Exception:
        return None
    return n if 0 <= n <= 99 else None


def _fmt2(value: object) -> str:
    n = _number_to_int(value)
    if n is None:
        return "" if pd.isna(value) else str(value)
    return f"{n:02d}"


def _fmt_value(value: object, *, decimals: int = 0, percent: bool = False) -> str:
    if pd.isna(value):
        return ""
    try:
        x = float(value)
    except Exception:
        return html.escape(str(value))
    if percent:
        return f"{x * 100:.1f}%"
    if decimals <= 0:
        if np.isfinite(x) and abs(x - round(x)) < 1e-9:
            return f"{int(round(x)):,}".replace(",", ".")
        return f"{x:,.0f}".replace(",", ".")
    return f"{x:.{decimals}f}".rstrip("0").rstrip(".")


def _pretty_col(col: str) -> str:
    return COLUMN_LABELS.get(col, col)


def _display_cell(value: object, col: str) -> str:
    if value == "" or pd.isna(value):
        return ""
    if col in {"number", "number_str", "prev_special_2d", "prev_loto", "next_loto", "a", "b"}:
        return html.escape(_fmt2(value))
    if col == "pair":
        pieces = str(value).split("-")
        if len(pieces) == 2:
            return f"{html.escape(_fmt2(pieces[0]))}-{html.escape(_fmt2(pieces[1]))}"
        return html.escape(str(value))
    if col == "period_kind":
        return PERIOD_LABELS.get(str(value), str(value))
    if col == "group_type":
        return GROUP_LABELS.get(str(value), str(value))
    if col == "mode":
        return html.escape(mode_label(value))
    if col == "score_band":
        return html.escape(str(value_label(value)))
    if col in {"hit_rate", "rate", "conditional_rate", "ml_prob"}:
        return html.escape(_fmt_value(value, decimals=3, percent=False))
    if col in {"ai_ml_signal_score", "z_score", "z_score_current_year", "rhythm_pressure", "mean_gap", "avg_per_draw", "expected_freq"}:
        return html.escape(_fmt_value(value, decimals=2))
    if col.startswith("T") or (len(col) == 2 and col.isdigit()):
        return html.escape(_fmt2(value))
    return html.escape(str(value))


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, float(t)))
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b, strict=True))


def _color_from_value(value: float, lo: float, hi: float, *, scheme: str) -> tuple[str, str]:
    if not np.isfinite(value):
        value = 0.0
    if not np.isfinite(lo):
        lo = 0.0
    if not np.isfinite(hi):
        hi = lo + 1.0
    if abs(hi - lo) < 1e-9:
        t = 0.0
    else:
        t = (value - lo) / (hi - lo)
    t = max(0.0, min(1.0, float(t)))

    palettes = {
        "freq": [(248, 250, 252), (191, 219, 254), (37, 99, 235), (30, 64, 175)],
        "hot": [(255, 251, 235), (253, 186, 116), (249, 115, 22), (220, 38, 38)],
        "gap": [(240, 253, 250), (153, 246, 228), (20, 184, 166), (15, 118, 110)],
        "ai": [(245, 243, 255), (196, 181, 253), (124, 58, 237), (76, 29, 149)],
        "de": [(255, 247, 237), (254, 215, 170), (234, 88, 12), (154, 52, 18)],
    }
    stops = palettes.get(scheme, palettes["freq"])
    if t <= 0.35:
        c = _mix(stops[0], stops[1], t / 0.35)
    elif t <= 0.72:
        c = _mix(stops[1], stops[2], (t - 0.35) / 0.37)
    else:
        c = _mix(stops[2], stops[3], (t - 0.72) / 0.28)
    r, g, b = c
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    text = "#f8fafc" if luminance < 0.52 else "#0f172a"
    return f"rgb({r},{g},{b})", text


def _empty_state(title: str = "Chưa có dữ liệu", hint: str = "Hãy chạy lại pipeline thống kê để sinh file CSV cần thiết.") -> str:
    return f"""
    <div class="empty-state">
      <strong>{html.escape(title)}</strong>
      <span>{html.escape(hint)}</span>
    </div>
    """


def _number_map(df: pd.DataFrame, value_col: str) -> dict[int, float]:
    values: dict[int, float] = {}
    if df.empty or value_col not in df.columns:
        return values

    number_col = "number"
    if number_col not in df.columns and "number_str" in df.columns:
        number_col = "number_str"
    if number_col not in df.columns:
        return values

    for _, row in df.iterrows():
        number = _number_to_int(row.get(number_col))
        if number is None:
            continue
        try:
            values[number] = float(row.get(value_col, 0) or 0)
        except Exception:
            values[number] = 0.0
    return values




def _clickable_number(number: object, *, mode: str | None, source_title: str, source_value: str = "") -> str:
    """Render a number pill that opens the evidence drawer when mode is known."""
    ns = _fmt2(number)
    if not ns:
        return html.escape(str(number))
    if not mode:
        return f"<span class='num-pill'>{html.escape(ns)}</span>"
    return (
        "<button type='button' class='num-pill num-click' "
        f"data-number='{html.escape(ns)}' "
        f"data-mode='{html.escape(mode)}' "
        f"data-source-title='{html.escape(source_title)}' "
        f"data-source-value='{html.escape(source_value)}' "
        "onclick='showNumberEvidence(this)' "
        "onkeydown='handleEvidenceKey(event,this)'>"
        f"{html.escape(ns)}</button>"
    )


def _json_for_script(payload: object) -> str:
    return json_for_html_script(payload)


def _row_dict_for_ui(row: pd.Series, columns: Sequence[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for col in columns:
        if col in row.index:
            value = row.get(col, "")
            out[col] = "" if pd.isna(value) else str(value)
    return out


def _evidence_payload(
    *,
    cau_loto: pd.DataFrame,
    cau_de: pd.DataFrame,
    explain_loto: pd.DataFrame,
    explain_de: pd.DataFrame,
    positions_loto: pd.DataFrame,
    positions_de: pd.DataFrame,
) -> dict[str, dict[str, dict[str, object]]]:
    """Build compact JSON used by click-to-explain number panels."""
    def build_mode(mode: str, cau: pd.DataFrame, explain: pd.DataFrame, positions: pd.DataFrame) -> dict[str, dict[str, object]]:
        summary_lookup: dict[str, pd.Series] = {}
        if not explain.empty and "number_str" in explain.columns:
            for _, row in explain.iterrows():
                summary_lookup[_fmt2(row.get("number_str", ""))] = row
        elif not cau.empty and "number_str" in cau.columns:
            for _, row in cau.iterrows():
                summary_lookup[_fmt2(row.get("number_str", ""))] = row

        pos_groups: dict[str, list[dict[str, str]]] = {}
        pos_cols = [
            "rule_kind",
            "lag_days",
            "base_date",
            "pos_i_label",
            "digit_i",
            "pos_j_label",
            "digit_j",
            "path_line",
            "p_mean",
            "hits",
            "trials",
            "current_streak",
            "max_streak",
            "rule_score",
            "reason",
        ]
        if not positions.empty and "number_str" in positions.columns:
            tmp = positions.copy()
            if "rule_score" in tmp.columns:
                tmp["_sort_score"] = pd.to_numeric(tmp["rule_score"], errors="coerce").fillna(0.0)
                tmp = tmp.sort_values(["number_str", "_sort_score"], ascending=[True, False])
            for ns, group in tmp.groupby(tmp["number_str"].map(_fmt2), sort=True):
                pos_groups[str(ns)] = [_row_dict_for_ui(row, pos_cols) for _, row in group.head(8).iterrows()]

        payload: dict[str, dict[str, object]] = {}
        summary_cols = [
            "number_str",
            "ai_cau_score",
            "ai_prob_percent",
            "cau_score",
            "prob_percent",
            "primary_reason",
            "ai_evidence",
            "evidence",
            "path_lines_count",
            "active_path_count",
            "stable_path_count",
            "top_path_score",
            "max_path_p_mean",
            "max_current_streak",
            "max_streak",
            "top_position_1",
            "top_position_2",
            "top_position_3",
            "explain_text",
        ]
        for n in range(100):
            ns = f"{n:02d}"
            row = summary_lookup.get(ns)
            summary = _row_dict_for_ui(row, summary_cols) if row is not None else {"number_str": ns}
            # Normalize names so JS can consume either legacy or summary columns.
            if "ai_cau_score" not in summary and "cau_score" in summary:
                summary["ai_cau_score"] = summary.get("cau_score", "")
            if "ai_prob_percent" not in summary and "prob_percent" in summary:
                summary["ai_prob_percent"] = summary.get("prob_percent", "")
            if "ai_evidence" not in summary and "evidence" in summary:
                summary["ai_evidence"] = summary.get("evidence", "")
            payload[ns] = {"mode": mode, "summary": summary, "positions": pos_groups.get(ns, [])}
        return payload

    return {
        "loto": build_mode("loto", cau_loto, explain_loto, positions_loto),
        "de": build_mode("de", cau_de, explain_de, positions_de),
    }


def _matrix(
    df: pd.DataFrame,
    *,
    title: str,
    subtitle: str,
    value_col: str,
    scheme: str = "freq",
    decimals: int = 0,
    suffix: str = "",
    min_zero: bool = True,
    evidence_mode: str | None = None,
) -> str:
    values = _number_map(df, value_col)
    if not values:
        return f"""
        <article class="viz-card matrix-card">
          <div class="card-head"><span class="type-badge matrix">Ma trận</span><h3>{html.escape(title)}</h3></div>
          <p>{html.escape(subtitle)}</p>
          {_empty_state()}
        </article>
        """
    ordered = [values.get(n, 0.0) for n in range(100)]
    lo = 0.0 if min_zero else float(np.nanmin(ordered))
    hi = float(np.nanmax(ordered)) if ordered else 1.0
    if abs(hi - lo) < 1e-9:
        hi = lo + 1.0

    parts = [
        f"""
        <article class="viz-card matrix-card">
          <div class="card-head"><span class="type-badge matrix">Ma trận</span><h3>{html.escape(title)}</h3></div>
          <p>{html.escape(subtitle)}</p>
          <div class="matrix-scroll">
            <div class="num-matrix" role="grid" aria-label="{html.escape(title)}">
              <div class="axis corner">×</div>
        """
    ]
    for unit in range(10):
        parts.append(f"<div class='axis'>đuôi {unit}</div>")
    for head in range(10):
        parts.append(f"<div class='axis row-axis'>đầu {head}</div>")
        for unit in range(10):
            n = head * 10 + unit
            val = float(values.get(n, 0.0))
            bg, fg = _color_from_value(val, lo, hi, scheme=scheme)
            val_text = _fmt_value(val, decimals=decimals)
            cell_class = "matrix-cell is-clickable" if evidence_mode else "matrix-cell"
            attrs = ""
            if evidence_mode:
                attrs = (
                    f" data-number='{n:02d}'"
                    f" data-mode='{html.escape(evidence_mode)}'"
                    f" data-source-title='{html.escape(title)}'"
                    f" data-source-value='{html.escape(val_text + suffix)}'"
                    " role='button' tabindex='0'"
                    " onclick='showNumberEvidence(this)'"
                    " onkeydown='handleEvidenceKey(event,this)'"
                )
            parts.append(
                f"<div class='{cell_class}' "
                f"style='background:{bg};color:{fg}' "
                f"title='{n:02d}: {html.escape(val_text + suffix)}'{attrs}>"
                f"<b>{n:02d}</b><span>{html.escape(val_text)}{html.escape(suffix)}</span>"
                "</div>"
            )
    parts.append(
        f"""
            </div>
          </div>
          <div class="legend">
            <span>Ít</span><i style="background:linear-gradient(90deg, {_color_from_value(lo, lo, hi, scheme=scheme)[0]}, {_color_from_value((lo+hi)/2, lo, hi, scheme=scheme)[0]}, {_color_from_value(hi, lo, hi, scheme=scheme)[0]});"></i><span>Nhiều</span>
          </div>
        </article>
        """
    )
    return "".join(parts)


def _bar_chart(
    df: pd.DataFrame,
    *,
    title: str,
    subtitle: str,
    label_col: str,
    value_col: str,
    top_n: int = 12,
    scheme: str = "freq",
    decimals: int = 0,
    suffix: str = "",
    filter_expr: tuple[str, str] | None = None,
    ascending: bool = False,
    evidence_mode: str | None = None,
) -> str:
    view = df.copy()
    if filter_expr and not view.empty:
        col, expected = filter_expr
        if col in view.columns:
            view = view[view[col].astype(str) == expected]
    if view.empty or label_col not in view.columns or value_col not in view.columns:
        return f"""
        <article class="viz-card">
          <div class="card-head"><span class="type-badge chart">Biểu đồ</span><h3>{html.escape(title)}</h3></div>
          <p>{html.escape(subtitle)}</p>
          {_empty_state()}
        </article>
        """
    view["_value_numeric"] = pd.to_numeric(view[value_col], errors="coerce").fillna(0.0)
    view = view.sort_values("_value_numeric", ascending=ascending).head(top_n).copy()
    max_v = float(view["_value_numeric"].max()) if not view.empty else 0.0
    min_v = 0.0 if not ascending else float(view["_value_numeric"].min())
    if max_v <= 0:
        max_v = 1.0

    rows = []
    for _, row in view.iterrows():
        label = _display_cell(row.get(label_col, ""), label_col)
        val = float(row["_value_numeric"])
        value_text = f"{_fmt_value(val, decimals=decimals)}{suffix}"
        if evidence_mode and label_col in {"number", "number_str", "a", "b", "prev_loto", "next_loto", "prev_special_2d"}:
            label_html = _clickable_number(row.get(label_col, ""), mode=evidence_mode, source_title=title, source_value=value_text)
        else:
            label_html = f"<span class='num-pill'>{label}</span>"
        width = max(4.0, min(100.0, val / max_v * 100.0)) if max_v > 0 else 0.0
        color, _ = _color_from_value(val, min_v, max_v, scheme=scheme)
        rows.append(
            "<div class='bar-row'>"
            f"{label_html}"
            f"<div class='bar-track'><i style='width:{width:.1f}%;background:{color}'></i></div>"
            f"<b>{html.escape(_fmt_value(val, decimals=decimals))}{html.escape(suffix)}</b>"
            "</div>"
        )
    return f"""
    <article class="viz-card">
      <div class="card-head"><span class="type-badge chart">Biểu đồ</span><h3>{html.escape(title)}</h3></div>
      <p>{html.escape(subtitle)}</p>
      <div class="bar-list">{''.join(rows)}</div>
    </article>
    """


def _table(
    df: pd.DataFrame,
    *,
    title: str,
    subtitle: str = "",
    columns: Sequence[str] | None = None,
    max_rows: int = 40,
    highlight_col: str | None = None,
    zfill_cols: Iterable[str] = (),
    compact: bool = False,
    evidence_mode: str | None = None,
) -> str:
    view = _safe_columns(df, columns) if columns else df.copy()
    if view.empty:
        return f"""
        <article class="viz-card table-card">
          <div class="card-head"><span class="type-badge table">Bảng</span><h3>{html.escape(title)}</h3></div>
          <p>{html.escape(subtitle)}</p>
          {_empty_state()}
        </article>
        """
    if highlight_col and highlight_col in view.columns:
        view = view.copy()
        view["_highlight"] = pd.to_numeric(view[highlight_col], errors="coerce").fillna(0.0)
        view = view.sort_values("_highlight", ascending=False)
    view = view.head(max_rows).copy()
    zfill = set(zfill_cols)

    max_highlight = float(view["_highlight"].max()) if "_highlight" in view.columns and not view.empty else 0.0

    header = "".join(f"<th>{html.escape(_pretty_col(c))}</th>" for c in view.columns if c != "_highlight")
    rows: list[str] = []
    for _, row in view.iterrows():
        cells: list[str] = []
        for c in view.columns:
            if c == "_highlight":
                continue
            raw = row.get(c, "")
            val = _fmt2(raw) if c in zfill else _display_cell(raw, c)
            cell_class = ""
            if c in {"number", "number_str", "prev_special_2d", "prev_loto", "next_loto"}:
                val = _clickable_number(raw, mode=evidence_mode, source_title=title)
            elif c == "pair":
                val = f"<span class='num-pill'>{val}</span>"
            elif c == "score_band":
                key = html.escape(str(raw)).replace("_", "-")
                val = f"<span class='band band-{key}'>{html.escape(str(raw))}</span>"
            elif c == highlight_col and max_highlight > 0:
                x = pd.to_numeric(pd.Series([raw]), errors="coerce").fillna(0.0).iloc[0]
                width = max(4.0, min(100.0, float(x) / max_highlight * 100.0))
                val_text = _display_cell(raw, c)
                val = f"<div class='mini-bar'><i style='width:{width:.1f}%'></i><b>{val_text}</b></div>"
            cells.append(f"<td class='{cell_class}'>{val}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")

    compact_class = " compact" if compact else ""
    return f"""
    <article class="viz-card table-card{compact_class}">
      <div class="card-head"><span class="type-badge table">Bảng</span><h3>{html.escape(title)}</h3></div>
      <p>{html.escape(subtitle)}</p>
      <div class="table-tools">
        <input type="search" placeholder="Lọc nhanh trong bảng..." aria-label="Lọc bảng" oninput="filterTable(this)" />
        <small>Hiển thị tối đa {max_rows} dòng đầu sau khi sắp xếp.</small>
      </div>
      <div class="table-wrap"><table><thead><tr>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    </article>
    """


def _metric_card(label: str, value: object, hint: str, icon: str) -> str:
    return f"""
    <article class="metric-card">
      <span class="metric-icon">{html.escape(icon)}</span>
      <div>
        <p>{html.escape(label)}</p>
        <strong>{html.escape(str(value))}</strong>
        <small>{html.escape(hint)}</small>
      </div>
    </article>
    """


def _period_snapshot(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    if df.empty or "period_kind" not in df.columns:
        return pd.DataFrame()
    return df[df["period_kind"].astype(str) == kind].copy()


def _period_text(df: pd.DataFrame) -> str:
    if df.empty or "period_key" not in df.columns:
        return ""
    values = [str(v) for v in df["period_key"].dropna().unique().tolist() if str(v)]
    return values[0] if values else ""


def _latest_by_period(df: pd.DataFrame, period_kind: str, period_key: str | None = None) -> pd.DataFrame:
    view = df.copy()
    if view.empty:
        return view
    if "period_kind" in view.columns:
        view = view[view["period_kind"].astype(str) == period_kind]
    if period_key and "period_key" in view.columns:
        view = view[view["period_key"].astype(str) == period_key]
    if view.empty or "period_key" not in view.columns:
        return view
    latest = sorted([str(x) for x in view["period_key"].unique()])[-1]
    return view[view["period_key"].astype(str) == latest].copy()


def _board_week_table(df: pd.DataFrame) -> str:
    return _table(
        df.tail(14),
        title="Bảng đặc biệt theo tuần",
        subtitle="Dùng bảng vì cần đối chiếu nhanh thứ trong tuần; ô trống là ngày chưa có dữ liệu trong mẫu.",
        columns=["week_key", *WEEKDAY_COLS],
        max_rows=14,
        zfill_cols=WEEKDAY_COLS,
        compact=True,
    )


def _board_month_table(df: pd.DataFrame) -> str:
    day_cols = [f"{i:02d}" for i in range(1, 32)]
    return _table(
        df.tail(8),
        title="Bảng đặc biệt theo tháng",
        subtitle="Dùng bảng rộng dạng lịch để soi chuỗi ngày trong tháng; cuộn ngang an toàn trên màn hình nhỏ.",
        columns=["month_key", *day_cols],
        max_rows=8,
        zfill_cols=day_cols,
        compact=True,
    )


def _section(title: str, intro: str, body: str, anchor: str) -> str:
    return f"""
    <section class="section" id="{html.escape(anchor)}">
      <div class="section-head">
        <div>
          <span class="eyebrow">{html.escape(anchor.replace('-', ' / '))}</span>
          <h2>{html.escape(title)}</h2>
          <p>{html.escape(intro)}</p>
        </div>
      </div>
      {body}
    </section>
    """


def main() -> None:
    root = Path(".")
    data_dir = root / "data"
    adv = data_dir / "advanced"
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)

    manifest = _read_json(adv / "statistics_manifest.json")
    generated = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    as_of = manifest.get("as_of_date", "")

    signal_loto = _read_csv(adv / "ai_ml_signal_loto.csv", dtype=str)
    signal_de = _read_csv(adv / "ai_ml_signal_de.csv", dtype=str)
    cau_loto = _read_csv(data_dir / "ai_ml" / "cau_keo_loto_all.csv", dtype=str)
    cau_de = _read_csv(data_dir / "ai_ml" / "cau_keo_de_all.csv", dtype=str)
    cau_report_loto = _read_csv(data_dir / "ai_ml" / "cau_keo_report_loto.csv", dtype=str)
    cau_report_de = _read_csv(data_dir / "ai_ml" / "cau_keo_report_de.csv", dtype=str)
    cau_positions_loto = _read_csv(data_dir / "ai_ml" / "cau_position_evidence_loto.csv", dtype=str)
    cau_positions_de = _read_csv(data_dir / "ai_ml" / "cau_position_evidence_de.csv", dtype=str)
    cau_explain_loto = _read_csv(data_dir / "ai_ml" / "cau_number_explain_loto.csv", dtype=str)
    cau_explain_de = _read_csv(data_dir / "ai_ml" / "cau_number_explain_de.csv", dtype=str)
    snap_loto = _read_csv(adv / "period_snapshot_loto_current.csv", dtype=str)
    snap_de = _read_csv(adv / "period_snapshot_de_current.csv", dtype=str)
    rhythm_loto = _read_csv(adv / "loto_rhythm.csv", dtype=str)
    rhythm_de = _read_csv(adv / "de_rhythm.csv", dtype=str)
    pair_current = _read_csv(adv / "reverse_pair_frequency_current.csv", dtype=str)
    hht_current = _read_csv(adv / "head_tail_total_loto_current.csv", dtype=str)
    sg_current = _read_csv(adv / "special_group_frequency_current.csv", dtype=str)
    special_week = _read_csv(adv / "special_week_board.csv", dtype=str)
    special_month = _read_csv(adv / "special_month_board.csv", dtype=str)
    first_overdue = _read_csv(adv / "first_prize_overdue.csv", dtype=str)
    cond_de_loto = _read_csv(adv / "conditional_loto_after_special_top500.csv", dtype=str, nrows=80)
    cond_loto_loto = _read_csv(adv / "conditional_loto_after_loto_top500.csv", dtype=str, nrows=80)

    loto_day = _period_snapshot(snap_loto, "day")
    loto_week = _period_snapshot(snap_loto, "week")
    loto_month = _period_snapshot(snap_loto, "month")
    loto_year = _period_snapshot(snap_loto, "year")
    de_day = _period_snapshot(snap_de, "day")
    de_week = _period_snapshot(snap_de, "week")
    de_month = _period_snapshot(snap_de, "month")
    de_year = _period_snapshot(snap_de, "year")

    latest_month_pair = _latest_by_period(pair_current, "month")
    latest_year_pair = _latest_by_period(pair_current, "year")
    hht_month = _latest_by_period(hht_current, "month")
    hht_year = _latest_by_period(hht_current, "year")
    sg_month = _latest_by_period(sg_current, "month")
    sg_year = _latest_by_period(sg_current, "year")

    files_count = len(manifest.get("files", []))
    evidence_json = _json_for_script(
        _evidence_payload(
            cau_loto=cau_loto,
            cau_de=cau_de,
            explain_loto=cau_explain_loto,
            explain_de=cau_explain_de,
            positions_loto=cau_positions_loto,
            positions_de=cau_positions_de,
        )
    )

    metrics = [
        _metric_card("Ngày dữ liệu mới nhất", as_of or "N/A", "Theo manifest thống kê", "📅"),
        _metric_card("Bảng/ma trận đã sinh", files_count or "N/A", "CSV/JSON trong data/advanced", "🧩"),
        _metric_card("Số bộ được phủ", "00–99", "Bấm vào số để xem căn cứ cầu", "🔢"),
        _metric_card(
            "AI/ML",
            "cầu-kèo + xếp hạng",
            "Có xác suất, điểm, lý do, kiểm định và vị trí cầu",
            "🤖",
        ),
    ]

    matrix_body = """
    <div class="layout-grid four">
    """ + "".join(
        [
            _matrix(loto_day, title=f"Loto {PERIOD_TITLES['day']}", subtitle=f"Tần suất loto trong {_period_text(loto_day) or 'ngày mới nhất'}.", value_col="freq", scheme="freq", evidence_mode="loto"),
            _matrix(loto_week, title=f"Loto {PERIOD_TITLES['week']}", subtitle=f"So sánh 00–99 trong {_period_text(loto_week) or 'tuần hiện tại'}.", value_col="freq", scheme="freq", evidence_mode="loto"),
            _matrix(loto_month, title=f"Loto {PERIOD_TITLES['month']}", subtitle=f"Đậm màu = về nhiều trong {_period_text(loto_month) or 'tháng hiện tại'}.", value_col="freq", scheme="hot", evidence_mode="loto"),
            _matrix(loto_year, title=f"Loto {PERIOD_TITLES['year']}", subtitle=f"Tổng hợp từ đầu {_period_text(loto_year) or 'năm'} đến ngày dữ liệu mới nhất.", value_col="freq", scheme="hot", evidence_mode="loto"),
        ]
    ) + "</div>"

    de_body = """
    <div class="layout-grid four">
    """ + "".join(
        [
            _matrix(de_day, title=f"ĐB {PERIOD_TITLES['day']}", subtitle=f"2 số cuối giải đặc biệt trong {_period_text(de_day) or 'ngày mới nhất'}.", value_col="freq", scheme="de", evidence_mode="de"),
            _matrix(de_week, title=f"ĐB {PERIOD_TITLES['week']}", subtitle=f"Phân bố ĐB theo {_period_text(de_week) or 'tuần hiện tại'}.", value_col="freq", scheme="de", evidence_mode="de"),
            _matrix(de_month, title=f"ĐB {PERIOD_TITLES['month']}", subtitle=f"Tần suất ĐB trong {_period_text(de_month) or 'tháng hiện tại'}.", value_col="freq", scheme="de", evidence_mode="de"),
            _matrix(de_year, title=f"ĐB {PERIOD_TITLES['year']}", subtitle=f"Tần suất ĐB từ đầu {_period_text(de_year) or 'năm'}.", value_col="freq", scheme="de", evidence_mode="de"),
        ]
    ) + "</div>"

    ai_body = f"""
    <div class="decision-grid">
      <article><b>Cầu-kèo ML</b><span>Mô hình học từ tần suất, gan, cầu dữ liệu gốc, quan hệ ĐB→số, lô tô→số, chạm/tổng/bóng và cùng thứ trong tuần.</span></article>
      <article><b>AI giải thích</b><span>Mỗi bộ số có lý do chính và bằng chứng định lượng để người xem hiểu vì sao điểm cao/thấp.</span></article>
      <article><b>Kiểm định lại</b><span>Luôn kèm tỷ lệ nhóm K trên tập kiểm định; không trình bày như kết quả chắc chắn.</span></article>
    </div>
    <div class="layout-grid two">
      {_matrix(cau_loto, title="Cầu-kèo AI/ML lô tô", subtitle="Ma trận điểm 00–99 từ mô hình học cầu lô, cầu dữ liệu gốc và thống kê tần suất.", value_col="cau_score", scheme="ai", decimals=1, min_zero=False, evidence_mode="loto")}
      {_matrix(cau_de, title="Cầu-kèo AI/ML ĐB", subtitle="Ma trận điểm ĐB 2 số; màu đậm = tín hiệu tổng hợp cao hơn trong lịch sử.", value_col="cau_score", scheme="ai", decimals=1, min_zero=False, evidence_mode="de")}
    </div>
    <div class="layout-grid two">
      {_bar_chart(cau_loto, title="Cầu-kèo lô tô đứng đầu", subtitle="Dùng biểu đồ để so sánh các điểm cao nhất và tránh đọc bảng dài.", label_col="number_str", value_col="cau_score", top_n=12, scheme="ai", decimals=1, evidence_mode="loto")}
      {_bar_chart(cau_de, title="Cầu-kèo ĐB đứng đầu", subtitle="Các số ĐB đứng đầu theo điểm tổng hợp; xem kèm cột lý do ở bảng bên dưới.", label_col="number_str", value_col="cau_score", top_n=12, scheme="ai", decimals=1, evidence_mode="de")}
    </div>
    <div class="layout-grid two">
      {_table(cau_loto, title="AI nhận định cầu-kèo lô tô", subtitle="Bảng giải thích: lý do chính, bằng chứng và các chỉ báo học từ lịch sử.", columns=["number_str", "cau_score", "prob_percent", "primary_reason", "evidence", "score_band"], max_rows=30, highlight_col="cau_score", zfill_cols={"number_str"}, evidence_mode="loto")}
      {_table(cau_de, title="AI nhận định cầu-kèo ĐB", subtitle="Dữ liệu ĐB rất thưa nên phải xem cùng kiểm định, không dùng điểm như cam kết.", columns=["number_str", "cau_score", "prob_percent", "primary_reason", "evidence", "score_band"], max_rows=30, highlight_col="cau_score", zfill_cols={"number_str"}, evidence_mode="de")}
    </div>
    <div class="layout-grid two">
      {_table(cau_report_loto, title="Kiểm định cầu-kèo lô tô", subtitle="Tỷ lệ nhóm K trên tập kiểm định gần nhất; dùng để kiểm tra mô hình có học được tín hiệu hay không.", columns=["top_k", "validation_days", "hit_any_days", "hit_any_rate", "avg_hits_per_day", "val_brier", "val_logloss", "val_start"], max_rows=10, highlight_col="hit_any_rate")}
      {_table(cau_report_de, title="Kiểm định cầu-kèo ĐB", subtitle="ĐB là bài toán 1/100 mỗi ngày nên tỷ lệ nhóm K thấp là bình thường; bảng này giúp kiểm soát ảo giác mô hình.", columns=["top_k", "validation_days", "hit_any_days", "hit_any_rate", "avg_hits_per_day", "val_brier", "val_logloss", "val_start"], max_rows=10, highlight_col="hit_any_rate")}
    </div>
    <div class="layout-grid two">
      {_matrix(signal_loto, title="Điểm AI/ML lô tô tổng hợp", subtitle="Lớp tín hiệu cũ vẫn được giữ để nhìn toàn cảnh 00–99 theo xác suất ML, tần suất và nhịp.", value_col="ai_ml_signal_score", scheme="ai", decimals=1, min_zero=False, evidence_mode="loto")}
      {_matrix(signal_de, title="Điểm AI/ML ĐB tổng hợp", subtitle="Điểm xếp hạng tương đối từ xác suất ML, chu kỳ, tần suất gần và độ lệch năm.", value_col="ai_ml_signal_score", scheme="ai", decimals=1, min_zero=False, evidence_mode="de")}
    </div>
    <div class="layout-grid two">
      {_bar_chart(signal_loto, title="AI/ML lô tô tổng hợp đứng đầu", subtitle="Dùng biểu đồ thanh để so sánh nhanh các điểm cao nhất.", label_col="number_str", value_col="ai_ml_signal_score", top_n=12, scheme="ai", decimals=1, evidence_mode="loto")}
      {_bar_chart(signal_de, title="AI/ML ĐB tổng hợp đứng đầu", subtitle="Các bộ có điểm thống kê tương đối cao nhất.", label_col="number_str", value_col="ai_ml_signal_score", top_n=12, scheme="ai", decimals=1, evidence_mode="de")}
    </div>
    <div class="layout-grid two">
      {_table(signal_loto, title="Bảng AI/ML lô tô chi tiết", subtitle="Có lọc nhanh; ưu tiên các trường dễ đọc thay vì toàn bộ cột kỹ thuật.", columns=["number_str", "ai_ml_signal_score", "ml_prob", "freq_7d", "freq_30d", "freq_current_year", "current_gap", "rhythm_pressure", "score_band"], max_rows=30, highlight_col="ai_ml_signal_score", zfill_cols={"number_str"}, evidence_mode="loto")}
      {_table(signal_de, title="Bảng AI/ML ĐB chi tiết", subtitle="Điểm chỉ là tín hiệu thống kê; không phải khuyến nghị chắc chắn.", columns=["number_str", "ai_ml_signal_score", "ml_prob", "freq_30d", "freq_current_year", "current_gap", "rhythm_pressure", "score_band"], max_rows=30, highlight_col="ai_ml_signal_score", zfill_cols={"number_str"}, evidence_mode="de")}
    </div>
    """

    rhythm_body = f"""
    <div class="layout-grid two">
      {_matrix(rhythm_loto, title="Ma trận lô gan lô tô", subtitle="Dùng ma trận để nhận biết cụm số có khoảng gan hiện tại cao/thấp.", value_col="current_gap", scheme="gap", evidence_mode="loto")}
      {_matrix(rhythm_de, title="Ma trận gan ĐB", subtitle="Màu càng đậm nghĩa là số càng lâu chưa xuất hiện trong ĐB.", value_col="current_gap", scheme="gap", evidence_mode="de")}
    </div>
    <div class="layout-grid three">
      {_bar_chart(rhythm_loto, title="Lô gan lô tô đứng đầu", subtitle="Biểu đồ thanh phù hợp để xếp hạng gan hiện tại.", label_col="number_str", value_col="current_gap", top_n=15, scheme="gap", evidence_mode="loto")}
      {_bar_chart(rhythm_de, title="Gan ĐB đứng đầu", subtitle="So sánh những bộ có khoảng cách hiện tại cao nhất.", label_col="number_str", value_col="current_gap", top_n=15, scheme="gap", evidence_mode="de")}
      {_bar_chart(first_overdue, title="Gan giải nhất đứng đầu", subtitle="Riêng 2 số cuối giải nhất.", label_col="number_str", value_col="current_gap", top_n=15, scheme="gap", evidence_mode="loto")}
    </div>
    <div class="layout-grid two">
      {_table(rhythm_loto, title="Lô gan lô tô chi tiết", subtitle="Bảng dùng khi cần xem cả số lần về, gan trung bình và lần cuối.", columns=["number_str", "current_gap", "hit_count", "mean_gap", "max_gap", "last_seen"], max_rows=35, highlight_col="current_gap", zfill_cols={"number_str"}, evidence_mode="loto")}
      {_table(rhythm_de, title="Gan ĐB chi tiết", subtitle="Sắp theo khoảng gan hiện tại giảm dần để dễ đối chiếu.", columns=["number_str", "current_gap", "hit_count", "mean_gap", "max_gap", "last_seen"], max_rows=35, highlight_col="current_gap", zfill_cols={"number_str"}, evidence_mode="de")}
    </div>
    """

    group_body = f"""
    <div class="layout-grid two">
      {_bar_chart(hht_month[hht_month.get("group_type", pd.Series(dtype=str)).astype(str) == "head"] if not hht_month.empty else hht_month, title="Đầu lô tô trong tháng", subtitle="10 đầu số nên dùng biểu đồ thanh để so sánh trực tiếp.", label_col="group_value", value_col="freq", top_n=10, scheme="hot")}
      {_bar_chart(hht_month[hht_month.get("group_type", pd.Series(dtype=str)).astype(str) == "tail"] if not hht_month.empty else hht_month, title="Đuôi lô tô trong tháng", subtitle="Đuôi nào tập trung nhiều trong tháng hiện tại.", label_col="group_value", value_col="freq", top_n=10, scheme="freq")}
    </div>
    <div class="layout-grid two">
      {_bar_chart(hht_month[hht_month.get("group_type", pd.Series(dtype=str)).astype(str) == "total"] if not hht_month.empty else hht_month, title="Tổng lô tô trong tháng", subtitle="Tổng 0–18, dùng thanh ngang để dễ so sánh.", label_col="group_value", value_col="freq", top_n=19, scheme="de")}
      {_bar_chart(sg_month, title="Nhóm ĐB trong tháng", subtitle="Chạm/đầu/đuôi/tổng ĐB xếp theo tần suất tháng.", label_col="group_value", value_col="freq", top_n=16, scheme="de")}
    </div>
    <div class="layout-grid two">
      {_table(hht_year, title="Đầu/đuôi/tổng lô tô năm", subtitle="Bảng chi tiết để đối chiếu nhóm và thứ hạng trong năm.", columns=["period_kind", "period_key", "group_type", "group_value", "freq", "rank_in_period_group"], max_rows=45, highlight_col="freq")}
      {_table(sg_year, title="Nhóm ĐB năm", subtitle="Tổng hợp nhóm đặc biệt: chạm, đầu, đuôi, tổng.", columns=["period_kind", "period_key", "group_type", "group_value", "freq", "rate", "rank_in_period_group"], max_rows=45, highlight_col="freq")}
    </div>
    """

    pair_body = f"""
    <div class="layout-grid two">
      {_bar_chart(latest_month_pair, title="Cặp lộn nổi bật trong tháng", subtitle="Gồm 45 cặp đảo chiều và 5 cặp kép-bóng; biểu đồ xếp hạng theo tần suất.", label_col="pair", value_col="freq", top_n=18, scheme="freq")}
      {_bar_chart(latest_year_pair, title="Cặp lộn nổi bật trong năm", subtitle="So sánh cặp nổi bật trên mẫu năm hiện tại.", label_col="pair", value_col="freq", top_n=18, scheme="hot")}
    </div>
    <div class="layout-grid two">
      {_table(latest_month_pair, title="Cặp lộn tháng chi tiết", subtitle="Có số ngày cùng về để nhìn mức đồng xuất hiện.", columns=["period_kind", "period_key", "pair", "freq", "days_hit", "cooccur_days", "avg_per_draw", "rank_in_period"], max_rows=45, highlight_col="freq")}
      {_table(latest_year_pair, title="Cặp lộn năm chi tiết", subtitle="Dùng bảng khi cần xem sâu hơn nhóm đứng đầu trên biểu đồ.", columns=["period_kind", "period_key", "pair", "freq", "days_hit", "cooccur_days", "avg_per_draw", "rank_in_period"], max_rows=45, highlight_col="freq")}
    </div>
    """

    board_body = f"""
    <div class="layout-grid one">
      {_board_week_table(special_week)}
      {_board_month_table(special_month)}
    </div>
    <div class="layout-grid two">
      {_table(first_overdue, title="Giải nhất gan", subtitle="2 số cuối giải nhất được tách riêng vì hành vi khác lô tô/ĐB.", columns=["number_str", "current_gap", "hit_count", "mean_gap", "max_gap", "last_seen"], max_rows=35, highlight_col="current_gap", zfill_cols={"number_str"}, evidence_mode="loto")}
      {_table(sg_current, title="Nhóm ĐB hiện tại", subtitle="Nhóm trong kỳ hiện tại; phù hợp bảng do số nhóm ít.", columns=["period_kind", "period_key", "group_type", "group_value", "freq", "rate", "rank_in_period_group"], max_rows=45, highlight_col="freq")}
    </div>
    """

    conditional_body = f"""
    <div class="layout-grid two">
      {_table(cond_de_loto, title="Lô tô sau ĐB", subtitle="Quan hệ điều kiện lịch sử: ĐB hôm trước → lô tô hôm sau.", columns=["prev_special_2d", "next_loto", "count", "base_count", "conditional_rate"], max_rows=45, highlight_col="conditional_rate", zfill_cols={"prev_special_2d", "next_loto"})}
      {_table(cond_loto_loto, title="Lô tô sau lô tô", subtitle="Quan hệ điều kiện lịch sử: lô tô hôm trước → lô tô hôm sau.", columns=["prev_loto", "next_loto", "count", "base_count", "conditional_rate"], max_rows=45, highlight_col="conditional_rate", zfill_cols={"prev_loto", "next_loto"})}
    </div>
    """

    position_body = f"""
    <div class="decision-grid">
      <article><b>Bấm để xem căn cứ</b><span>Bấm bất kỳ số 00–99 ở ma trận, biểu đồ hoặc bảng để mở khung căn cứ: điểm AI, xác suất, lý do và vị trí cầu.</span></article>
      <article><b>Vị trí đường cầu</b><span>Mỗi dòng ghi rõ ngày gốc, độ trễ, vị trí chữ số A/B, số ghép ra và hiệu suất lịch sử của đường cầu đó.</span></article>
      <article><b>Ưu tiên xem</b><span>Đường đang chạy thể hiện nhịp hiện tại; đường ổn định thể hiện cầu từng bền trong lịch sử. Luôn xem cùng kết quả kiểm định.</span></article>
    </div>
    <div class="layout-grid two">
      {_bar_chart(cau_explain_loto, title="Lô tô: số có nhiều căn cứ vị trí", subtitle="So sánh số lượng đường cầu đang được gắn vào từng bộ lô tô.", label_col="number_str", value_col="path_lines_count", top_n=15, scheme="freq", evidence_mode="loto")}
      {_bar_chart(cau_explain_de, title="ĐB: số có căn cứ vị trí", subtitle="ĐB ít mẫu hơn nên nhiều số có thể chưa đủ đường cầu vị trí đạt ngưỡng.", label_col="number_str", value_col="path_lines_count", top_n=15, scheme="de", evidence_mode="de")}
    </div>
    <div class="layout-grid two">
      {_table(cau_explain_loto, title="Bảng căn cứ tổng hợp lô tô", subtitle="Một dòng mỗi số: điểm AI, xác suất, số đường cầu, đường mạnh nhất và giải thích tự động.", columns=["number_str", "ai_cau_score", "ai_prob_percent", "path_lines_count", "active_path_count", "stable_path_count", "top_path_score", "max_path_p_mean", "max_current_streak", "top_position_1", "explain_text"], max_rows=45, highlight_col="ai_cau_score", zfill_cols={"number_str"}, evidence_mode="loto")}
      {_table(cau_explain_de, title="Bảng căn cứ tổng hợp ĐB", subtitle="Một dòng mỗi số ĐB; các số chưa có đường cầu đủ ngưỡng vẫn giữ bằng chứng AI/thống kê.", columns=["number_str", "ai_cau_score", "ai_prob_percent", "path_lines_count", "active_path_count", "stable_path_count", "top_path_score", "max_path_p_mean", "max_current_streak", "top_position_1", "explain_text"], max_rows=45, highlight_col="ai_cau_score", zfill_cols={"number_str"}, evidence_mode="de")}
    </div>
    <div class="layout-grid two">
      {_table(cau_positions_loto, title="Vị trí đường cầu lô tô", subtitle="Chi tiết đường cầu dữ liệu gốc: vị trí A/B, số ghép, độ trễ, ngày gốc và hiệu suất lịch sử.", columns=["number_str", "rule_kind", "lag_days", "base_date", "pos_i_label", "digit_i", "pos_j_label", "digit_j", "p_mean", "hits", "trials", "current_streak", "max_streak", "rule_score", "reason"], max_rows=90, highlight_col="rule_score", zfill_cols={"number_str"}, evidence_mode="loto")}
      {_table(cau_positions_de, title="Vị trí đường cầu ĐB", subtitle="ĐB có mẫu ít hơn; bảng này cho thấy những đường đủ ngưỡng hiện có.", columns=["number_str", "rule_kind", "lag_days", "base_date", "pos_i_label", "digit_i", "pos_j_label", "digit_j", "p_mean", "hits", "trials", "current_streak", "max_streak", "rule_score", "reason"], max_rows=90, highlight_col="rule_score", zfill_cols={"number_str"}, evidence_mode="de")}
    </div>
    """

    qa_body = f"""
    <div class="decision-grid">
      <article><b>Ma trận</b><span>Dùng cho 00–99: tần suất, gan, điểm AI/ML. Nhìn được toàn bộ mặt phẳng số và cụm bất thường.</span></article>
      <article><b>Biểu đồ thanh</b><span>Dùng cho xếp hạng: AI, lô gan, đầu–đuôi–tổng, cặp lộn. So sánh lớn/nhỏ rất nhanh.</span></article>
      <article><b>Bảng</b><span>Dùng cho dữ liệu cần đối chiếu chi tiết: bảng ĐB tuần/tháng, điều kiện lịch sử, các trường giải thích.</span></article>
    </div>
    <div class="layout-grid two">
      {_table(snap_loto, title="Ảnh chụp lô tô hiện tại", subtitle="Bảng kỹ thuật đầy đủ cho ngày/tuần/tháng/năm.", columns=["period_kind", "period_key", "number_str", "freq", "days_hit", "hit_rate", "avg_per_draw", "z_score", "rank_in_period"], max_rows=60, highlight_col="freq", zfill_cols={"number_str"}, evidence_mode="loto")}
      {_table(snap_de, title="Ảnh chụp ĐB hiện tại", subtitle="Bảng kỹ thuật đầy đủ cho ĐB ngày/tuần/tháng/năm.", columns=["period_kind", "period_key", "number_str", "freq", "days_hit", "hit_rate", "z_score", "rank_in_period"], max_rows=60, highlight_col="freq", zfill_cols={"number_str"}, evidence_mode="de")}
    </div>
    """

    sections = [
        _section("Tần suất loto ngày / tuần / tháng / năm", "Các thống kê phủ 00–99 nên hiển thị bằng ma trận 10x10 để so sánh bằng màu thay vì đọc bảng dài.", matrix_body, "ma-tran-loto"),
        _section("Tần suất ĐB ngày / tuần / tháng / năm", "ĐB có mật độ thấp hơn loto; ma trận vẫn giúp phát hiện vùng số nổi bật trong tháng/năm.", de_body, "ma-tran-db"),
        _section("Cầu-kèo AI/ML và tín hiệu xếp hạng", "Phần AI/ML được trình bày bằng ma trận, biểu đồ xếp hạng, bảng giải thích và kết quả kiểm định để dễ so sánh lẫn kiểm chứng.", ai_body, "ai-ml"),
        _section("Bảng vị trí đường cầu và căn cứ khi bấm số", "Mỗi số có bảng căn cứ riêng: vị trí chữ số, ngày gốc, độ trễ, hiệu suất lịch sử và nhận định AI/ML.", position_body, "can-cu-cau"),
        _section("Gan, nhịp và chu kỳ", "Khoảng cách xuất hiện hiện tại nên hiển thị bằng ma trận nhiệt và biểu đồ xếp hạng để nhận biết số lâu chưa về.", rhythm_body, "gan-nhip"),
        _section("Đầu, đuôi, tổng và nhóm ĐB", "Nhóm ít giá trị nên dùng biểu đồ thanh; bảng chỉ giữ phần chi tiết cần đối chiếu.", group_body, "dau-duoi-tong"),
        _section("Cặp lộn và kép-bóng", "Cặp lộn gồm 45 cặp đảo chiều; năm cặp kép dùng quan hệ bóng (00-55, 11-66, 22-77, 33-88, 44-99).", pair_body, "cap-lon"),
        _section("Bảng đặc biệt và giải nhất", "Bảng tuần/tháng giữ bố cục lịch để người dùng quen cách xem; giải nhất dùng biểu đồ/bảng gan riêng.", board_body, "bang-db"),
        _section("Điều kiện lịch sử", "Các bảng này có nhiều dòng và nhiều điều kiện, vì vậy giữ dạng bảng có lọc nhanh thay vì ép thành ma trận.", conditional_body, "dieu-kien"),
        _section("Quy tắc chọn loại hiển thị", "Mục này ghi rõ logic UI/UX để đội phát triển mở rộng thêm thống kê mà không làm rối giao diện.", qa_body, "ui-ux"),
    ]

    html_doc = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  <title>Bảng điều khiển thống kê XSMB</title>
  <style>
    :root {{
      --bg: #0b1020;
      --surface: rgba(255,255,255,0.92);
      --surface-strong: #ffffff;
      --text: #111827;
      --muted: #64748b;
      --line: rgba(15,23,42,0.10);
      --blue: #2563eb;
      --violet: #7c3aed;
      --orange: #f97316;
      --rose: #e11d48;
      --green: #0f766e;
      --shadow: 0 28px 70px rgba(2,6,23,0.28);
      --radius-xl: 30px;
      --radius-lg: 22px;
      --radius-md: 16px;
    }}

    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 8% -8%, rgba(37,99,235,0.55), transparent 30%),
        radial-gradient(circle at 90% 6%, rgba(124,58,237,0.42), transparent 28%),
        radial-gradient(circle at 55% 16%, rgba(249,115,22,0.20), transparent 30%),
        linear-gradient(135deg, #020617 0%, #0b1020 52%, #111827 100%);
      min-height: 100vh;
    }}

    a {{ color: inherit; }}
    .hero {{
      position: relative;
      padding: 40px clamp(18px, 5vw, 72px) 18px;
      color: white;
      overflow: hidden;
    }}
    .hero-inner {{
      max-width: 1280px;
      margin: 0 auto;
    }}
    .hero-kicker {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 8px 12px;
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 999px;
      background: rgba(255,255,255,0.10);
      backdrop-filter: blur(14px);
      color: #dbeafe;
      font-size: 13px;
      font-weight: 700;
    }}
    .hero h1 {{
      margin: 16px 0 12px;
      max-width: 980px;
      font-size: clamp(34px, 6vw, 78px);
      line-height: 0.95;
      letter-spacing: -0.07em;
    }}
    .hero p {{
      max-width: 980px;
      margin: 0;
      color: #dbeafe;
      line-height: 1.7;
      font-size: clamp(15px, 1.5vw, 18px);
    }}
    .hero-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .hero-actions a {{
      text-decoration: none;
      padding: 10px 14px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.22);
      background: rgba(255,255,255,0.10);
      color: white;
      font-weight: 750;
      transition: transform .15s ease, background .15s ease;
    }}
    .hero-actions a:hover {{ transform: translateY(-1px); background: rgba(255,255,255,0.18); }}

    main {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 0 clamp(16px, 5vw, 72px) 56px;
    }}

    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin: 18px 0 22px;
    }}
    .metric-card {{
      display: flex;
      gap: 14px;
      align-items: center;
      padding: 16px;
      border-radius: 24px;
      color: white;
      background: linear-gradient(145deg, rgba(255,255,255,0.16), rgba(255,255,255,0.07));
      border: 1px solid rgba(255,255,255,0.16);
      backdrop-filter: blur(16px);
      box-shadow: 0 18px 48px rgba(2,6,23,0.18);
    }}
    .metric-icon {{
      display: grid;
      place-items: center;
      width: 46px;
      height: 46px;
      border-radius: 16px;
      background: rgba(255,255,255,0.16);
      font-size: 22px;
      flex: 0 0 auto;
    }}
    .metric-card p {{ margin: 0; color: #bfdbfe; font-weight: 750; font-size: 13px; }}
    .metric-card strong {{ display: block; margin: 4px 0 2px; font-size: 23px; letter-spacing: -0.02em; }}
    .metric-card small {{ color: #e0e7ff; line-height: 1.4; }}

    .sticky-nav {{
      position: sticky;
      top: 0;
      z-index: 50;
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding: 12px 0 14px;
      margin-bottom: 8px;
      backdrop-filter: blur(16px);
      scrollbar-width: thin;
    }}
    .sticky-nav a {{
      white-space: nowrap;
      text-decoration: none;
      color: #e0e7ff;
      border: 1px solid rgba(255,255,255,0.16);
      background: rgba(15,23,42,0.52);
      padding: 9px 12px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 760;
    }}

    .section {{
      margin: 18px 0 24px;
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      background: var(--surface);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .section-head {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 24px 24px 8px;
    }}
    .eyebrow {{
      color: var(--blue);
      text-transform: uppercase;
      font-size: 12px;
      letter-spacing: .12em;
      font-weight: 900;
    }}
    .section h2 {{
      margin: 6px 0 8px;
      font-size: clamp(24px, 3.2vw, 40px);
      line-height: 1.05;
      letter-spacing: -0.05em;
    }}
    .section-head p {{
      margin: 0;
      max-width: 960px;
      color: var(--muted);
      line-height: 1.65;
    }}

    .layout-grid {{
      display: grid;
      gap: 16px;
      padding: 16px 20px 22px;
    }}
    .layout-grid.one {{ grid-template-columns: 1fr; }}
    .layout-grid.two {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
    .layout-grid.three {{ grid-template-columns: repeat(3, minmax(0,1fr)); }}
    .layout-grid.four {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}

    .viz-card {{
      min-width: 0;
      padding: 16px;
      border-radius: var(--radius-lg);
      background: var(--surface-strong);
      border: 1px solid rgba(15,23,42,0.08);
      box-shadow: 0 14px 36px rgba(15,23,42,0.06);
    }}
    .card-head {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
    }}
    .viz-card h3 {{
      margin: 0;
      font-size: 18px;
      letter-spacing: -0.025em;
    }}
    .viz-card p {{
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }}
    .type-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 72px;
      padding: 5px 9px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: .08em;
    }}
    .type-badge.matrix {{ background: #dbeafe; color: #1d4ed8; }}
    .type-badge.chart {{ background: #fef3c7; color: #b45309; }}
    .type-badge.table {{ background: #ede9fe; color: #6d28d9; }}

    .matrix-scroll {{
      overflow-x: auto;
      padding: 4px 2px 8px;
      scrollbar-width: thin;
    }}
    .num-matrix {{
      display: grid;
      grid-template-columns: 54px repeat(10, minmax(50px, 1fr));
      gap: 5px;
      min-width: 660px;
    }}
    .axis {{
      display: grid;
      place-items: center;
      min-height: 32px;
      border-radius: 12px;
      background: #f1f5f9;
      color: #475569;
      font-size: 11px;
      font-weight: 850;
      text-transform: uppercase;
    }}
    .row-axis {{ writing-mode: horizontal-tb; }}
    .corner {{ background: #e2e8f0; color: #334155; }}
    .matrix-cell {{
      min-height: 52px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      gap: 2px;
      border-radius: 14px;
      border: 1px solid rgba(15,23,42,0.08);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.25);
    }}
    .matrix-cell b {{
      font-size: 14px;
      letter-spacing: .04em;
    }}
    .matrix-cell span {{
      font-size: 12px;
      font-weight: 850;
      opacity: .96;
    }}

    .matrix-cell.is-clickable {{
      cursor: pointer;
      outline: none;
      transition: transform .14s ease, box-shadow .14s ease, filter .14s ease;
    }}
    .matrix-cell.is-clickable:hover,
    .matrix-cell.is-clickable:focus {{
      transform: translateY(-2px);
      filter: saturate(1.12);
      box-shadow: 0 12px 28px rgba(15,23,42,0.20), inset 0 1px 0 rgba(255,255,255,0.28);
    }}
    .num-click {{
      border: 0;
      cursor: pointer;
      font: inherit;
    }}
    .num-click:hover,
    .num-click:focus {{
      transform: translateY(-1px);
      box-shadow: 0 10px 22px rgba(37,99,235,0.18);
    }}
    .legend {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
    }}
    .legend i {{
      display: block;
      flex: 1;
      max-width: 260px;
      height: 10px;
      border-radius: 999px;
      border: 1px solid rgba(15,23,42,0.08);
    }}

    .bar-list {{
      display: grid;
      gap: 9px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(58px, auto) 1fr minmax(60px, auto);
      align-items: center;
      gap: 10px;
    }}
    .bar-track {{
      position: relative;
      height: 26px;
      border-radius: 999px;
      background: #eef2ff;
      overflow: hidden;
      border: 1px solid rgba(15,23,42,0.06);
    }}
    .bar-track i {{
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      border-radius: 999px;
    }}
    .bar-row > b {{
      text-align: right;
      color: #334155;
      font-variant-numeric: tabular-nums;
      font-size: 13px;
    }}

    .num-pill {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 42px;
      padding: 4px 9px;
      border-radius: 999px;
      background: #e0f2fe;
      color: #075985;
      border: 1px solid #bae6fd;
      font-weight: 900;
      letter-spacing: .04em;
      font-variant-numeric: tabular-nums;
    }}
    .band {{
      padding: 4px 9px;
      border-radius: 999px;
      font-weight: 900;
      font-size: 12px;
      text-transform: uppercase;
    }}
    .band-low {{ background: #e2e8f0; color: #334155; }}
    .band-medium {{ background: #dcfce7; color: #166534; }}
    .band-high {{ background: #fef3c7; color: #92400e; }}
    .band-very-high {{ background: #fee2e2; color: #991b1b; }}

    .table-tools {{
      display: flex;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      margin: 0 0 10px;
    }}
    .table-tools input {{
      width: min(320px, 100%);
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px solid #cbd5e1;
      outline: none;
      font: inherit;
      background: #f8fafc;
    }}
    .table-tools input:focus {{
      border-color: #60a5fa;
      box-shadow: 0 0 0 3px rgba(96,165,250,0.25);
      background: white;
    }}
    .table-tools small {{ color: var(--muted); }}

    .table-wrap {{
      overflow: auto;
      max-height: 560px;
      border: 1px solid #e2e8f0;
      border-radius: 16px;
      background: white;
      scrollbar-width: thin;
    }}
    table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      font-size: 13px;
    }}
    th, td {{
      padding: 9px 10px;
      border-bottom: 1px solid #eef2f7;
      white-space: nowrap;
      text-align: left;
      vertical-align: middle;
    }}
    th {{
      position: sticky;
      top: 0;
      z-index: 2;
      background: #f8fafc;
      color: #334155;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    tr:hover td {{ background: #f8fafc; }}
    .compact table {{ font-size: 12px; }}
    .compact th, .compact td {{ padding: 8px 9px; text-align: center; }}
    .compact th:first-child, .compact td:first-child {{
      text-align: left;
      position: sticky;
      left: 0;
      background: inherit;
      z-index: 1;
      font-weight: 850;
      color: #334155;
    }}
    .compact th:first-child {{ z-index: 3; background: #f8fafc; }}

    .mini-bar {{
      position: relative;
      min-width: 94px;
      height: 25px;
      border-radius: 999px;
      background: #eff6ff;
      overflow: hidden;
      border: 1px solid rgba(37,99,235,0.10);
    }}
    .mini-bar i {{
      position: absolute;
      inset: 0 auto 0 0;
      background: linear-gradient(90deg, #93c5fd, #2563eb);
      border-radius: 999px;
    }}
    .mini-bar b {{
      position: relative;
      z-index: 1;
      display: block;
      line-height: 23px;
      padding-left: 8px;
      color: #0f172a;
      font-size: 12px;
    }}

    .empty-state {{
      display: grid;
      gap: 6px;
      padding: 18px;
      border-radius: 18px;
      background: repeating-linear-gradient(135deg, #f8fafc, #f8fafc 12px, #f1f5f9 12px, #f1f5f9 24px);
      border: 1px dashed #cbd5e1;
      color: #475569;
    }}
    .empty-state strong {{ color: #0f172a; }}
    .empty-state span {{ font-size: 13px; line-height: 1.5; }}

    .decision-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      padding: 16px 20px 0;
    }}
    .decision-grid article {{
      padding: 16px;
      border-radius: 22px;
      border: 1px solid rgba(15,23,42,0.08);
      background: white;
    }}
    .decision-grid b {{
      display: block;
      font-size: 18px;
      margin-bottom: 6px;
      letter-spacing: -0.02em;
    }}
    .decision-grid span {{
      color: var(--muted);
      line-height: 1.55;
      font-size: 13px;
    }}


    .evidence-backdrop {{
      position: fixed;
      inset: 0;
      z-index: 110;
      display: none;
      background: rgba(2,6,23,0.52);
      backdrop-filter: blur(6px);
    }}
    .evidence-backdrop.open {{ display: block; }}
    .evidence-drawer {{
      position: fixed;
      z-index: 120;
      top: 0;
      right: 0;
      width: min(620px, 100vw);
      height: 100vh;
      display: flex;
      flex-direction: column;
      background: #f8fafc;
      box-shadow: -36px 0 90px rgba(2,6,23,0.35);
      transform: translateX(104%);
      transition: transform .22s ease;
      border-left: 1px solid rgba(15,23,42,0.12);
    }}
    .evidence-drawer.open {{ transform: translateX(0); }}
    .evidence-head {{
      padding: 20px 22px 14px;
      color: white;
      background:
        radial-gradient(circle at 10% 0%, rgba(255,255,255,0.25), transparent 34%),
        linear-gradient(135deg, #1d4ed8, #7c3aed 58%, #c026d3);
    }}
    .evidence-head-row {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
    }}
    .evidence-number {{
      display: inline-grid;
      place-items: center;
      width: 74px;
      height: 74px;
      border-radius: 24px;
      background: rgba(255,255,255,0.18);
      border: 1px solid rgba(255,255,255,0.24);
      font-size: 30px;
      font-weight: 950;
      letter-spacing: .04em;
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.26);
    }}
    .evidence-head h2 {{
      margin: 10px 0 6px;
      font-size: 24px;
      letter-spacing: -0.035em;
    }}
    .evidence-head p {{
      margin: 0;
      color: #e0e7ff;
      line-height: 1.55;
      font-size: 13px;
    }}
    .evidence-close {{
      border: 1px solid rgba(255,255,255,0.24);
      background: rgba(255,255,255,0.12);
      color: white;
      width: 38px;
      height: 38px;
      border-radius: 999px;
      cursor: pointer;
      font-size: 22px;
      line-height: 1;
    }}
    .evidence-body {{
      overflow: auto;
      padding: 18px 20px 26px;
      display: grid;
      gap: 14px;
    }}
    .evidence-card {{
      background: white;
      border: 1px solid #e2e8f0;
      border-radius: 20px;
      padding: 15px;
      box-shadow: 0 14px 36px rgba(15,23,42,0.06);
    }}
    .evidence-card h3 {{
      margin: 0 0 10px;
      font-size: 16px;
      letter-spacing: -0.02em;
    }}
    .evidence-metrics {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .evidence-metric {{
      padding: 11px;
      border-radius: 15px;
      background: #f1f5f9;
      border: 1px solid #e2e8f0;
    }}
    .evidence-metric span {{
      display: block;
      color: #64748b;
      font-size: 11px;
      font-weight: 850;
      text-transform: uppercase;
      letter-spacing: .05em;
    }}
    .evidence-metric b {{
      display: block;
      margin-top: 3px;
      font-size: 16px;
      color: #0f172a;
    }}
    .evidence-list {{
      margin: 0;
      padding-left: 18px;
      color: #334155;
      line-height: 1.55;
      font-size: 13px;
    }}
    .evidence-table-wrap {{
      overflow: auto;
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      max-height: 360px;
    }}
    .evidence-table {{
      min-width: 720px;
      font-size: 12px;
    }}
    .evidence-table th,
    .evidence-table td {{
      padding: 8px 9px;
    }}
    .evidence-empty {{
      padding: 14px;
      border-radius: 14px;
      background: #fff7ed;
      color: #9a3412;
      border: 1px solid #fed7aa;
      font-size: 13px;
      line-height: 1.55;
    }}

    .footer-note {{
      color: #cbd5e1;
      padding: 10px 0 0;
      font-size: 13px;
      line-height: 1.6;
    }}
    .footer-note code {{
      color: #e0f2fe;
      background: rgba(255,255,255,0.10);
      padding: 2px 6px;
      border-radius: 8px;
    }}

    @media (max-width: 1180px) {{
      .metric-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .layout-grid.two, .layout-grid.three, .layout-grid.four, .decision-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 680px) {{
      .hero h1 {{ letter-spacing: -0.045em; }}
      .metric-grid {{ grid-template-columns: 1fr; }}
      .section-head {{ padding: 20px 16px 6px; }}
      .layout-grid, .decision-grid {{ padding-left: 14px; padding-right: 14px; }}
      .viz-card {{ padding: 14px; border-radius: 20px; }}
      .table-tools {{ align-items: stretch; flex-direction: column; }}
      .bar-row {{ grid-template-columns: 52px 1fr 52px; gap: 7px; }}
      .num-pill {{ min-width: 36px; padding: 4px 7px; }}
      .evidence-metrics {{ grid-template-columns: 1fr; }}
      .evidence-head {{ padding: 18px 16px 12px; }}
      .evidence-body {{ padding: 14px 14px 22px; }}
    }}
  </style>
</head>
<body>
  <header class="hero">
    <div class="hero-inner">
      <span class="hero-kicker">📊 XSMB · Ma trận thống kê · Cầu-kèo AI/ML</span>
      <h1>Bảng điều khiển thống kê xổ số dễ nhìn, hiện đại và tự chứa dữ liệu.</h1>
      <p>
        Giao diện này ưu tiên khả năng so sánh: dữ liệu 00–99 được đưa vào ma trận nhiệt,
        dữ liệu xếp hạng được đưa vào biểu đồ thanh, còn bảng chỉ dùng cho thông tin cần đối chiếu chi tiết.
        Các tín hiệu AI/ML là thống kê xác suất từ lịch sử, không phải cam kết kết quả tương lai.
      </p>
      <nav class="hero-actions">
        <a href="#ma-tran-loto">Ma trận loto</a>
        <a href="#ma-tran-db">Ma trận ĐB</a>
        <a href="#ai-ml">Cầu-kèo AI/ML</a>
        <a href="#can-cu-cau">Căn cứ cầu</a>
        <a href="#gan-nhip">Gan / nhịp</a>
        <a href="#cap-lon">Cặp lộn</a>
        <a href="#bang-db">Bảng ĐB</a>
      </nav>
    </div>
  </header>

  <main>
    <div class="metric-grid">{''.join(metrics)}</div>
    <nav class="sticky-nav" aria-label="Điều hướng nhanh">
      <a href="#ma-tran-loto">Loto ngày/tuần/tháng/năm</a>
      <a href="#ma-tran-db">ĐB ngày/tuần/tháng/năm</a>
      <a href="#ai-ml">Cầu-kèo AI/ML</a>
      <a href="#can-cu-cau">Căn cứ cầu</a>
      <a href="#gan-nhip">Gan & nhịp</a>
      <a href="#dau-duoi-tong">Đầu đuôi tổng</a>
      <a href="#cap-lon">Cặp lộn</a>
      <a href="#bang-db">Bảng ĐB</a>
      <a href="#dieu-kien">Điều kiện</a>
      <a href="#ui-ux">Quy tắc UI</a>
    </nav>

    {''.join(sections)}

    <p class="footer-note">
      Tạo lúc: {html.escape(generated)} · Dữ liệu đến: {html.escape(str(as_of or 'Không có'))}
      · Manifest: <code>data/advanced/statistics_manifest.json</code>.
      Bảng điều khiển này không dùng ảnh ngoài/CDN nên có thể mở trực tiếp tệp HTML mà không bị mất ma trận.
    </p>
  </main>

  <div id="evidenceBackdrop" class="evidence-backdrop" onclick="closeEvidence()" aria-hidden="true"></div>
  <aside id="evidenceDrawer" class="evidence-drawer" aria-hidden="true" aria-label="Căn cứ đường cầu">
    <header class="evidence-head">
      <div class="evidence-head-row">
        <div>
          <span id="evidenceNumber" class="evidence-number">--</span>
          <h2 id="evidenceTitle">Căn cứ số</h2>
          <p id="evidenceSubtitle">Bấm vào số trong ma trận/bảng để xem giải thích.</p>
        </div>
        <button type="button" class="evidence-close" onclick="closeEvidence()" aria-label="Đóng">×</button>
      </div>
    </header>
    <div id="evidenceContent" class="evidence-body"></div>
  </aside>

  <script id="cauEvidenceData" type="application/json">{evidence_json}</script>
  <script>
    function filterTable(input) {{
      const card = input.closest('.table-card');
      if (!card) return;
      const query = input.value.trim().toLowerCase();
      const rows = card.querySelectorAll('tbody tr');
      rows.forEach(row => {{
        const text = row.innerText.toLowerCase();
        row.style.display = text.includes(query) ? '' : 'none';
      }});
    }}

    const CAU_EVIDENCE = JSON.parse(document.getElementById('cauEvidenceData')?.textContent || '{{}}');

    function handleEvidenceKey(event, element) {{
      if (event.key === 'Enter' || event.key === ' ') {{
        event.preventDefault();
        showNumberEvidence(element);
      }}
    }}

    function valueOrDash(value) {{
      if (value === undefined || value === null || value === '' || value === 'nan' || value === 'NaN') return '—';
      return String(value);
    }}

    function modeLabel(mode) {{
      return mode === 'de' ? 'ĐB' : 'loto';
    }}

    function createEvidenceElement(tag, className, text) {{
      const node = document.createElement(tag);
      if (className) node.className = className;
      if (text !== undefined) node.textContent = text;
      return node;
    }}

    function metric(label, value) {{
      const node = createEvidenceElement('div', 'evidence-metric');
      node.append(
        createEvidenceElement('span', '', label),
        createEvidenceElement('b', '', valueOrDash(value))
      );
      return node;
    }}

    function renderPositionRows(positions) {{
      if (!positions || !positions.length) {{
        return createEvidenceElement(
          'div',
          'evidence-empty',
          'Chưa có đường cầu vị trí đạt ngưỡng cho số này. Hãy xem thêm điểm AI, tần suất, gan/nhịp và kết quả kiểm định trước khi đánh giá.'
        );
      }}
      const headers = ['Loại', 'Trễ', 'Ngày gốc', 'Vị trí A', 'Số A', 'Vị trí B', 'Số B', 'Tỷ lệ', 'Trúng/Mẫu', 'Chuỗi', 'Điểm', 'Căn cứ'];
      const wrap = createEvidenceElement('div', 'evidence-table-wrap');
      const table = createEvidenceElement('table', 'evidence-table');
      const thead = document.createElement('thead');
      const headerRow = document.createElement('tr');
      headers.forEach(function(header) {{
        headerRow.appendChild(createEvidenceElement('th', '', header));
      }});
      thead.appendChild(headerRow);
      const tbody = document.createElement('tbody');
      positions.forEach(function(p) {{
        const cells = [
          p.rule_kind,
          p.lag_days,
          p.base_date,
          p.pos_i_label,
          p.digit_i,
          p.pos_j_label,
          p.digit_j,
          p.p_mean,
          valueOrDash(p.hits) + '/' + valueOrDash(p.trials),
          valueOrDash(p.current_streak) + ' / ' + valueOrDash(p.max_streak),
          p.rule_score,
          p.reason
        ];
        const row = document.createElement('tr');
        cells.forEach(function(cell) {{
          row.appendChild(createEvidenceElement('td', '', valueOrDash(cell)));
        }});
        tbody.appendChild(row);
      }});
      table.append(thead, tbody);
      wrap.appendChild(table);
      return wrap;
    }}

    function renderTopLines(summary) {{
      const lines = [summary.top_position_1, summary.top_position_2, summary.top_position_3].filter(function(x) {{
        return x && String(x).trim() && String(x) !== 'nan' && String(x) !== 'NaN';
      }});
      if (!lines.length) {{
        return createEvidenceElement(
          'div',
          'evidence-empty',
          'Chưa có vị trí nổi bật đủ ngưỡng; khung này vẫn hiển thị bằng chứng AI/thống kê để đối chiếu.'
        );
      }}
      const list = createEvidenceElement('ol', 'evidence-list');
      lines.forEach(function(line) {{
        list.appendChild(createEvidenceElement('li', '', line));
      }});
      return list;
    }}

    function evidenceSection(title, content) {{
      const section = createEvidenceElement('section', 'evidence-card');
      section.append(createEvidenceElement('h3', '', title), content);
      return section;
    }}

    function evidenceParagraph(label, value) {{
      const paragraph = document.createElement('p');
      paragraph.style.cssText = 'margin:6px 0 0;color:#475569;line-height:1.6;font-size:13px;';
      paragraph.append(
        createEvidenceElement('b', '', label + ': '),
        document.createTextNode(valueOrDash(value))
      );
      return paragraph;
    }}

    function showNumberEvidence(element) {{
      const number = element.dataset.number || '--';
      const mode = element.dataset.mode || 'loto';
      const sourceTitle = element.dataset.sourceTitle || 'Bảng thống kê';
      const sourceValue = element.dataset.sourceValue || '';
      const item = ((CAU_EVIDENCE[mode] || {{}})[number]) || {{}};
      const summary = item.summary || {{}};
      const positions = item.positions || [];

      document.getElementById('evidenceNumber').textContent = number;
      document.getElementById('evidenceTitle').textContent = 'Căn cứ số ' + number + ' · ' + modeLabel(mode);
      document.getElementById('evidenceSubtitle').textContent = sourceTitle + (sourceValue ? ' · Giá trị đang xem: ' + sourceValue : '');

      const score = summary.ai_cau_score || summary.cau_score;
      const prob = summary.ai_prob_percent || summary.prob_percent;
      const evidence = summary.ai_evidence || summary.evidence || '';
      const metrics = createEvidenceElement('div', 'evidence-metrics');
      metrics.append(
        metric('Điểm AI', score),
        metric('Xác suất hiển thị', prob ? prob + '%' : ''),
        metric('Số đường cầu', summary.path_lines_count),
        metric('Đang chạy', summary.active_path_count),
        metric('Cầu bền', summary.stable_path_count),
        metric('Chuỗi dài nhất', summary.max_streak)
      );
      const aiContent = document.createDocumentFragment();
      aiContent.append(
        metrics,
        evidenceParagraph('Lý do', summary.primary_reason),
        evidenceParagraph('Bằng chứng', evidence)
      );
      const explanation = createEvidenceElement('p', '', valueOrDash(summary.explain_text));
      explanation.style.cssText = 'margin:0;color:#334155;line-height:1.65;font-size:13px;';

      document.getElementById('evidenceContent').replaceChildren(
        evidenceSection('AI/ML nhận định', aiContent),
        evidenceSection('Vị trí tạo số nổi bật', renderTopLines(summary)),
        evidenceSection('Bảng vị trí đường cầu', renderPositionRows(positions)),
        evidenceSection('Diễn giải ngắn', explanation)
      );
      document.getElementById('evidenceBackdrop').classList.add('open');
      const drawer = document.getElementById('evidenceDrawer');
      drawer.classList.add('open');
      drawer.setAttribute('aria-hidden', 'false');
    }}

    function closeEvidence() {{
      document.getElementById('evidenceBackdrop').classList.remove('open');
      const drawer = document.getElementById('evidenceDrawer');
      drawer.classList.remove('open');
      drawer.setAttribute('aria-hidden', 'true');
    }}

    document.addEventListener('keydown', function(event) {{
      if (event.key === 'Escape') closeEvidence();
    }});
  </script>
</body>
</html>
"""
    html_doc = "\n".join(line.rstrip() for line in html_doc.splitlines()) + "\n"
    (docs / "statistics.html").write_text(html_doc, encoding="utf-8")
    print("Wrote:", docs / "statistics.html")


if __name__ == "__main__":
    main()
