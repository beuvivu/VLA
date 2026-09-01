from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ADV = DATA / "advanced"
OUT = ROOT / "DASHBOARD.md"

PRIZE_GROUPS: list[tuple[str, list[str], int]] = [
    ("Đặc biệt", ["special"], 5),
    ("Giải nhất", ["prize1"], 5),
    ("Giải nhì", ["prize2_1", "prize2_2"], 5),
    ("Giải ba", [f"prize3_{i}" for i in range(1, 7)], 5),
    ("Giải tư", [f"prize4_{i}" for i in range(1, 5)], 4),
    ("Giải năm", [f"prize5_{i}" for i in range(1, 7)], 4),
    ("Giải sáu", [f"prize6_{i}" for i in range(1, 4)], 3),
    ("Giải bảy", [f"prize7_{i}" for i in range(1, 5)], 2),
]

HEAT = ["⬜", "🟦", "🟩", "🟨", "🟧", "🟥", "🟪"]


def _read_csv(path: Path, *, dtype: Any = None) -> pd.DataFrame:
    try:
        if not path.exists() or path.stat().st_size == 0:
            return pd.DataFrame()
        return pd.read_csv(path, dtype=dtype, keep_default_na=False)
    except Exception:
        return pd.DataFrame()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {"data": obj}
    except Exception:
        return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _fmt2(value: Any) -> str:
    try:
        return f"{int(float(value)):02d}"
    except Exception:
        return str(value or "").zfill(2)


def _fmt_code(value: Any, width: int) -> str:
    try:
        return f"{int(float(value)):0{width}d}"
    except Exception:
        text = str(value or "").strip()
        return text.zfill(width) if text else "—"


def _fmt_num(value: Any, digits: int = 2) -> str:
    x = _safe_float(value, float("nan"))
    if not math.isfinite(x):
        return "—"
    if abs(x - round(x)) < 1e-10 and digits == 0:
        return f"{int(round(x)):,}".replace(",", ".")
    return f"{x:.{digits}f}"


def _fmt_pct(value: Any, digits: int = 2, *, already_percent: bool = False) -> str:
    x = _safe_float(value, float("nan"))
    if not math.isfinite(x):
        return "—"
    if not already_percent:
        x *= 100.0
    return f"{x:.{digits}f}%"


def _cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _md_table(headers: Sequence[Any], rows: Iterable[Sequence[Any]]) -> str:
    rows = list(rows)
    if not rows:
        return "_Chưa có dữ liệu._"
    head = "| " + " | ".join(_cell(x) for x in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_cell(x) for x in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def _bar(value: float, max_value: float, width: int = 10) -> str:
    if max_value <= 0:
        return "▱" * width
    n = max(0, min(width, int(round(value / max_value * width))))
    return "▰" * n + "▱" * (width - n)


def _heat(value: float, lo: float, hi: float) -> str:
    if not math.isfinite(value):
        return HEAT[0]
    if hi <= lo:
        return HEAT[3]
    t = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    idx = min(len(HEAT) - 1, int(round(t * (len(HEAT) - 1))))
    return HEAT[idx]


def _number_col(df: pd.DataFrame) -> str | None:
    for c in ("number_str", "number"):
        if c in df.columns:
            return c
    return None


def _number_matrix(
    df: pd.DataFrame,
    value_col: str,
    *,
    percent: bool = False,
    decimals: int = 1,
    title: str = "",
) -> str:
    ncol = _number_col(df)
    if df.empty or not ncol or value_col not in df.columns:
        return f"_Chưa đủ dữ liệu cho {title or value_col}._"
    values: dict[int, float] = {}
    for _, row in df.iterrows():
        try:
            n = int(float(row[ncol]))
        except Exception:
            continue
        if 0 <= n <= 99:
            values[n] = _safe_float(row[value_col])
    ordered = np.array([values.get(i, 0.0) for i in range(100)], dtype=float)
    lo = float(np.nanmin(ordered)) if len(ordered) else 0.0
    hi = float(np.nanmax(ordered)) if len(ordered) else 1.0
    rows: list[list[str]] = []
    for head in range(10):
        line = [f"**{head}x**"]
        for tail in range(10):
            n = head * 10 + tail
            v = values.get(n, 0.0)
            txt = _fmt_pct(v, decimals) if percent else _fmt_num(v, decimals)
            line.append(f"{_heat(v, lo, hi)}<br>`{n:02d}`<br>**{txt}**")
        rows.append(line)
    return _md_table(["Đầu\\Đuôi", *[str(i) for i in range(10)]], rows)


def _rank_table(
    df: pd.DataFrame,
    *,
    value_col: str,
    columns: Sequence[str],
    top_n: int = 15,
    ascending: bool = False,
    percent_cols: Sequence[str] = (),
    number_cols: Sequence[str] = ("number", "number_str"),
) -> str:
    if df.empty or value_col not in df.columns:
        return "_Chưa có dữ liệu._"
    view = df.copy()
    view["__score"] = pd.to_numeric(view[value_col], errors="coerce")
    view = view.sort_values("__score", ascending=ascending).head(top_n)
    max_v = float(view["__score"].abs().max()) if not view.empty else 0.0
    rows: list[list[Any]] = []
    for rank, (_, row) in enumerate(view.iterrows(), 1):
        out: list[Any] = [rank]
        for c in columns:
            raw = row.get(c, "")
            if c in number_cols:
                out.append(f"**{_fmt2(raw)}**")
            elif c in percent_cols:
                out.append(_fmt_pct(raw, 2))
            elif isinstance(raw, (float, np.floating)):
                out.append(_fmt_num(raw, 4))
            else:
                out.append(raw)
        out.append(_bar(abs(_safe_float(row.get(value_col))), max_v, 8))
        rows.append(out)
    return _md_table(["#", *columns, "Visual"], rows)


def _wide_top_pairs(path: Path, *, top_n: int = 20, descending: bool = True) -> str:
    df = _read_csv(path)
    if df.empty or len(df.columns) < 3:
        return "_Chưa có dữ liệu._"
    source_col = df.columns[0]
    pairs: list[tuple[str, str, float]] = []
    for _, row in df.iterrows():
        src = _fmt2(row[source_col])
        for col in df.columns[1:]:
            val = _safe_float(row[col], float("nan"))
            if math.isfinite(val):
                pairs.append((src, _fmt2(col), val))
    pairs.sort(key=lambda x: x[2], reverse=descending)
    chosen = pairs[:top_n]
    max_v = max((abs(v) for _, _, v in chosen), default=1.0)
    return _md_table(
        ["#", "Nguồn", "→", "Đích", "Giá trị", "Visual"],
        [[i, f"`{a}`", "→", f"**`{b}`**", f"{v:.4f}", _bar(abs(v), max_v, 8)] for i, (a, b, v) in enumerate(chosen, 1)],
    )


def _fun_board(payload: dict[str, Any]) -> str:
    groups = payload.get("groups", []) if isinstance(payload.get("groups"), list) else []
    rows: list[list[Any]] = []
    for group in groups:
        vals = group.get("values", []) if isinstance(group, dict) else []
        numbers = " · ".join(str(v.get("value", "")) for v in vals if isinstance(v, dict))
        suffixes = " · ".join(
            f"`{v.get('suffix','')}` {_fmt_pct(v.get('model_prob', 0), 2)}" for v in vals if isinstance(v, dict)
        )
        rows.append([group.get("label", ""), numbers, suffixes])
    return _md_table(["Giải", "Dự đoán vui", "2 số cuối · model probability"], rows)


def _daily_board(df: pd.DataFrame) -> tuple[str, str]:
    if df.empty:
        return "—", "_Chưa có dữ liệu._"
    row = df.iloc[-1]
    date = str(row.get("date", ""))
    rows = []
    for label, cols, width in PRIZE_GROUPS:
        values = " · ".join(_fmt_code(row.get(c, ""), width) for c in cols)
        rows.append([label, f"**{values}**" if label == "Đặc biệt" else values])
    return date, _md_table(["Giải", "Kết quả thực"], rows)


def _recent_results(df: pd.DataFrame, n: int = 10) -> str:
    if df.empty:
        return "_Chưa có dữ liệu._"
    rows = []
    for _, row in df.tail(n).iloc[::-1].iterrows():
        rows.append(
            [
                row.get("date", ""),
                f"**{_fmt_code(row.get('special'), 5)}**",
                _fmt_code(row.get("prize1"), 5),
                " · ".join(_fmt_code(row.get(f"prize2_{i}"), 5) for i in (1, 2)),
                " · ".join(_fmt_code(row.get(f"prize7_{i}"), 2) for i in range(1, 5)),
            ]
        )
    return _md_table(["Ngày", "ĐB", "G1", "G2", "G7"], rows)


def _prediction(mode: str, target: str) -> tuple[pd.DataFrame, Path | None]:
    preferred = DATA / "predict" / f"predict_next_{mode}_all_{target}.csv"
    if preferred.exists():
        return _read_csv(preferred), preferred
    files = sorted((DATA / "predict").glob(f"predict_next_{mode}_all_*.csv"))
    if not files:
        return pd.DataFrame(), None
    return _read_csv(files[-1]), files[-1]


def _period(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    if df.empty or "period_kind" not in df.columns:
        return pd.DataFrame()
    return df[df["period_kind"].astype(str) == kind].copy()


def _latest_period(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    view = _period(df, kind)
    if view.empty or "period_key" not in view.columns:
        return view
    key = sorted(view["period_key"].astype(str).unique())[-1]
    return view[view["period_key"].astype(str) == key].copy()


def _group_rank(df: pd.DataFrame, kind: str, group: str, top_n: int = 20) -> str:
    view = _latest_period(df, kind)
    if not view.empty and "group_type" in view.columns:
        view = view[view["group_type"].astype(str) == group].copy()
    if view.empty:
        return "_Chưa có dữ liệu._"
    view["freq_num"] = pd.to_numeric(view.get("freq"), errors="coerce").fillna(0.0)
    view = view.sort_values("freq_num", ascending=False).head(top_n)
    max_v = float(view["freq_num"].max()) if not view.empty else 1.0
    rows = []
    for i, (_, row) in enumerate(view.iterrows(), 1):
        rows.append([i, row.get("group_value", ""), int(row["freq_num"]), _bar(float(row["freq_num"]), max_v, 10)])
    return _md_table(["#", "Nhóm", "Tần suất", "Phân bố"], rows)


def _special_group_table(df: pd.DataFrame, kind: str = "month") -> str:
    view = _latest_period(df, kind)
    if view.empty:
        return "_Chưa có dữ liệu._"
    rows = []
    for group in ("db_head", "db_tail", "db_cham", "db_total"):
        g = view[view["group_type"].astype(str) == group].copy()
        if g.empty:
            continue
        g["freq_num"] = pd.to_numeric(g["freq"], errors="coerce").fillna(0)
        g = g.sort_values("freq_num", ascending=False).head(6)
        label = {"db_head": "Đầu ĐB", "db_tail": "Đuôi ĐB", "db_cham": "Chạm ĐB", "db_total": "Tổng ĐB"}[group]
        rows.append([label, " · ".join(f"**{r['group_value']}** ({int(r['freq_num'])})" for _, r in g.iterrows())])
    return _md_table(["Nhóm", "Top phân bố"], rows)


def _board_table(path: Path, *, tail: int) -> str:
    df = _read_csv(path, dtype=str)
    if df.empty:
        return "_Chưa có dữ liệu._"
    view = df.tail(tail).iloc[::-1]
    return _md_table(list(view.columns), [[row.get(c, "") for c in view.columns] for _, row in view.iterrows()])


def _conditional_table(path: Path, *, top_n: int = 15) -> str:
    df = _read_csv(path)
    if df.empty:
        return "_Chưa có dữ liệu._"
    score = "conditional_rate" if "conditional_rate" in df.columns else "rate" if "rate" in df.columns else "count"
    df["__score"] = pd.to_numeric(df[score], errors="coerce").fillna(0)
    df = df.sort_values("__score", ascending=False).head(top_n)
    preferred = [c for c in ("prev_special_2d", "prev_loto", "next_loto", "count", "base_count", "conditional_rate", "lift") if c in df.columns]
    rows = []
    max_v = float(df["__score"].max()) if not df.empty else 1.0
    for i, (_, row) in enumerate(df.iterrows(), 1):
        vals = []
        for c in preferred:
            raw = row.get(c, "")
            if c in {"prev_special_2d", "prev_loto", "next_loto"}:
                vals.append(f"`{_fmt2(raw)}`")
            elif c == "conditional_rate":
                vals.append(_fmt_pct(raw, 2))
            else:
                vals.append(_fmt_num(raw, 3) if isinstance(raw, (float, np.floating)) else raw)
        rows.append([i, *vals, _bar(float(row["__score"]), max_v, 8)])
    return _md_table(["#", *preferred, "Visual"], rows)


def _significance(path: Path, top_n: int = 15) -> str:
    df = _read_csv(path)
    if df.empty:
        return "_Chưa có dữ liệu._"
    score = "evidence_score" if "evidence_score" in df.columns else "z_score"
    df["__score"] = pd.to_numeric(df[score], errors="coerce").abs().fillna(0)
    df = df.sort_values("__score", ascending=False).head(top_n)
    rows = []
    for i, (_, r) in enumerate(df.iterrows(), 1):
        rows.append(
            [
                i,
                f"**{_fmt2(r.get('number_str', r.get('number')))}**",
                _fmt_num(r.get("observed_rate"), 3),
                _fmt_num(r.get("baseline_rate"), 3),
                _fmt_num(r.get("lift"), 3),
                _fmt_num(r.get("z_score"), 3),
                _fmt_num(r.get("p_value"), 4),
                _fmt_num(r.get("q_value_fdr"), 4),
                _fmt_num(r.get("posterior_mean"), 3),
                "✅" if str(r.get("fdr_05", "")).lower() == "true" else "—",
            ]
        )
    return _md_table(["#", "Số", "Observed", "Baseline", "Lift", "Z", "p", "q(FDR)", "Posterior", "FDR<.05"], rows)


def _strategy_lab(path: Path, top_n: int = 15) -> str:
    df = _read_csv(path)
    if df.empty:
        return "_Chưa có dữ liệu._"
    df["__score"] = pd.to_numeric(df.get("holdout_lift"), errors="coerce").fillna(0)
    df = df.sort_values("__score", ascending=False).head(top_n)
    rows = []
    for i, (_, r) in enumerate(df.iterrows(), 1):
        rows.append(
            [
                i,
                r.get("strategy", ""),
                r.get("category", ""),
                _fmt_num(r.get("holdout_lift"), 3),
                _fmt_num(r.get("holdout_effect"), 4),
                _fmt_pct(r.get("holdout_precision"), 2),
                _fmt_num(r.get("holdout_q_value_fdr"), 4),
                "✅" if str(r.get("research_gate_pass", "")).lower() == "true" else "—",
            ]
        )
    return _md_table(["#", "Strategy", "Nhóm", "OOS lift", "Effect", "OOS precision", "q(FDR)", "Gate"], rows)


def _model_report(mode: str) -> dict[str, Any]:
    return _read_json(DATA / "ml" / f"meta_report_{mode}.json") or _read_json(DATA / "predict" / f"meta_report_{mode}.json")


def _weights(mode: str) -> dict[str, Any]:
    return _read_json(DATA / "ensemble" / f"weights_{mode}.json")


def _weight_table(loto: dict[str, Any], de: dict[str, Any]) -> str:
    wl = loto.get("weights", loto) if isinstance(loto, dict) else {}
    wd = de.get("weights", de) if isinstance(de, dict) else {}
    keys = ["w_ml", "w_cau", "w_stat", "w_active", "w_stable"]
    names = {"w_ml": "Base ML", "w_cau": "Cầu/Kèo ML", "w_stat": "Statistical", "w_active": "Active paths", "w_stable": "Stable paths"}
    return _md_table(
        ["Component", "Lô tô", "Đề", "Lô tô visual", "Đề visual"],
        [[names[k], _fmt_pct(wl.get(k, 0), 1), _fmt_pct(wd.get(k, 0), 1), _bar(_safe_float(wl.get(k)), 1, 8), _bar(_safe_float(wd.get(k)), 1, 8)] for k in keys],
    )


def _diagnostic_cards() -> str:
    health = _read_json(DATA / "health.json")
    dyn_l = _read_json(DATA / "number_dynamics" / "diagnostics_loto.json")
    dyn_d = _read_json(DATA / "number_dynamics" / "diagnostics_de.json")
    sig = _read_json(DATA / "significance" / "global_diagnostics.json")
    research = _read_json(DATA / "research" / "research_firewall_report.json")
    scientific = _read_json(DATA / "research" / "scientific_diagnostics.json")
    rows = [
        ["Data health", "✅ OK" if health.get("ok") else "⚠️ CHECK", f"rows={health.get('row_count','—')} · missing={health.get('missing_count','—')}"],
        ["Dynamics Loto", _fmt_num(dyn_l.get("global_dynamics_reliability"), 3), f"JS drift={_fmt_num(dyn_l.get('js_divergence_30_vs_180'),4)}"],
        ["Dynamics Đề", _fmt_num(dyn_d.get("global_dynamics_reliability"), 3), f"JS drift={_fmt_num(dyn_d.get('js_divergence_30_vs_180'),4)}"],
        ["Significance", sig.get("as_of_date", "—"), json.dumps(sig, ensure_ascii=False)[:120] + "…" if sig else "—"],
        ["Research firewall", research.get("as_of_date", research.get("generated_at", "—")), f"gate summary: {research.get('summary', research.get('research_gate_pass','—'))}"],
        ["Scientific diagnostics", scientific.get("as_of_date", scientific.get("generated_at", "—")), f"tests={len(scientific)} top-level fields"],
    ]
    return _md_table(["Layer", "Status / score", "Diagnostic"], rows)


def main() -> None:
    health = _read_json(DATA / "health.json")
    xsmb = _read_csv(DATA / "xsmb.csv")
    fun = _read_json(DATA / "predict" / "fun_draw_next.json")
    picks_loto = _read_json(DATA / "predict" / "picks_loto.json")
    picks_de = _read_json(DATA / "predict" / "picks_de.json")

    latest_date, daily = _daily_board(xsmb)
    target = str(picks_loto.get("target_date") or picks_de.get("target_date") or fun.get("target_date") or "—")
    pred_loto, pred_loto_path = _prediction("loto", target)
    pred_de, pred_de_path = _prediction("de", target)

    snap_loto = _read_csv(ADV / "period_snapshot_loto_current.csv")
    snap_de = _read_csv(ADV / "period_snapshot_de_current.csv")
    rhythm_loto = _read_csv(ADV / "loto_rhythm.csv")
    rhythm_de = _read_csv(ADV / "de_rhythm.csv")
    first_overdue = _read_csv(ADV / "first_prize_overdue.csv")
    hht = _read_csv(ADV / "head_tail_total_loto_current.csv")
    special_groups = _read_csv(ADV / "special_group_frequency_current.csv")
    reverse_pairs = _read_csv(ADV / "reverse_pair_frequency_current.csv")
    cau_loto = _read_csv(DATA / "ai_ml" / "cau_keo_loto_all.csv")
    cau_de = _read_csv(DATA / "ai_ml" / "cau_keo_de_all.csv")
    signal_loto = _read_csv(ADV / "ai_ml_signal_loto.csv")
    signal_de = _read_csv(ADV / "ai_ml_signal_de.csv")
    dynamics_loto = _read_csv(DATA / "number_dynamics" / "current_dynamics_loto.csv")
    dynamics_de = _read_csv(DATA / "number_dynamics" / "current_dynamics_de.csv")
    markov = _read_csv(DATA / "markov" / "markov_loto.csv")
    hazard_loto = _read_csv(DATA / "hazard" / "hazard_loto.csv")
    hazard_de = _read_csv(DATA / "hazard" / "hazard_de.csv")

    generated = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    loto_meta = picks_loto.get("meta", {}) if isinstance(picks_loto.get("meta"), dict) else {}
    de_meta = picks_de.get("meta", {}) if isinstance(picks_de.get("meta"), dict) else {}

    # Prediction tables.
    def forecast_table(df: pd.DataFrame, top_n: int = 15) -> str:
        if df.empty:
            return "_Chưa có prediction._"
        view = df.head(top_n)
        rows = []
        max_p = float(pd.to_numeric(view["prob"], errors="coerce").fillna(0).max()) if "prob" in view else 1.0
        for i, (_, r) in enumerate(view.iterrows(), 1):
            n = _fmt2(r.get("number_str", r.get("number", "")))
            p = _safe_float(r.get("prob"))
            rows.append([
                i,
                f"**{n}**" if i <= 4 else n,
                _fmt_pct(p, 3),
                _fmt_pct(r.get("linear_prob"), 3),
                _fmt_pct(r.get("meta_prob"), 3),
                _fmt_pct(r.get("meta_edge"), 3),
                r.get("agreement_tier", "—"),
                _fmt_num(r.get("component_disagreement"), 4),
                _bar(p, max_p, 10),
            ])
        return _md_table(["#", "Số", "Final P", "Linear", "Meta", "Meta edge", "Agreement", "Dispersion", "Probability"], rows)

    # Rhythm/hazard tables.
    gap_cols = ["number_str", "current_gap", "hit_count", "mean_gap", "max_gap", "last_seen", "rhythm_pressure"]
    def gap_table(df: pd.DataFrame, top_n: int = 15) -> str:
        if df.empty:
            return "_Chưa có dữ liệu._"
        view = df.copy()
        view["__gap"] = pd.to_numeric(view.get("current_gap"), errors="coerce").fillna(0)
        view = view.sort_values("__gap", ascending=False).head(top_n)
        max_g = float(view["__gap"].max()) if not view.empty else 1
        return _md_table(
            ["#", "Số", "Gan", "Số lần về", "Gan TB", "Gan max", "Lần cuối", "Pressure", "Visual"],
            [[i, f"**{_fmt2(r.get('number_str', r.get('number')))}**", int(r["__gap"]), r.get("hit_count", ""), _fmt_num(r.get("mean_gap"),2), r.get("max_gap", ""), r.get("last_seen", ""), _fmt_num(r.get("rhythm_pressure"),2), _bar(float(r["__gap"]), max_g, 8)] for i, (_, r) in enumerate(view.iterrows(),1)],
        )

    def hazard_table(df: pd.DataFrame, max_gap: int = 25) -> str:
        if df.empty:
            return "_Chưa có dữ liệu._"
        view = df[pd.to_numeric(df.get("gap"), errors="coerce").fillna(0) <= max_gap].copy()
        max_h = float(pd.to_numeric(view.get("hazard"), errors="coerce").fillna(0).max()) if not view.empty else 1.0
        return _md_table(
            ["Gap", "Exposure", "Hits", "Hazard", "Curve"],
            [[int(_safe_float(r.get("gap"))), int(_safe_float(r.get("denom"))), int(_safe_float(r.get("hits"))), _fmt_pct(r.get("hazard"),2), _bar(_safe_float(r.get("hazard")), max_h, 12)] for _, r in view.iterrows()],
        )

    # Dynamics decomposition.
    def dynamics_table(df: pd.DataFrame, top_n: int = 15) -> str:
        if df.empty:
            return "_Chưa có dữ liệu._"
        view = df.copy()
        view["__p"] = pd.to_numeric(view.get("prob"), errors="coerce").fillna(0)
        view = view.sort_values("__p", ascending=False).head(top_n)
        rows = []
        for i, (_, r) in enumerate(view.iterrows(), 1):
            rows.append([
                i, f"**{_fmt2(r.get('number_str',r.get('number')))}**",
                _fmt_pct(r.get("prob"),2), _fmt_pct(r.get("baseline_prob"),2), _fmt_pct(r.get("markov2_prob"),2),
                r.get("markov2_state",""), _fmt_pct(r.get("hazard_prob"),2), r.get("next_gap",""),
                _fmt_pct(r.get("transition_prob"),2), _fmt_pct(r.get("lag_kernel_prob"),2), _fmt_pct(r.get("regime_prob"),2),
                _fmt_num(r.get("regime_log_ratio"),3), _fmt_num(r.get("dynamics_reliability"),3)
            ])
        return _md_table(["#","Số","Dynamics P","Baseline","Markov-2","State","Hazard","Next gap","Transition","Lag kernel","Regime","Regime log-ratio","Reliability"], rows)

    # Markov table.
    markov_table = "_Chưa có dữ liệu._"
    if not markov.empty:
        m = markov.copy()
        m["lift_num"] = pd.to_numeric(m.get("lift"), errors="coerce").fillna(0)
        m = m.sort_values("lift_num", ascending=False).head(20)
        markov_table = _md_table(
            ["#","Số","P(hit|hit)","P(hit|miss)","Lift","Hit→hit samples","Miss→hit samples"],
            [[i,f"**{_fmt2(r.get('number'))}**",_fmt_pct(r.get("p_hit_given_hit"),2),_fmt_pct(r.get("p_hit_given_miss"),2),_fmt_num(r.get("lift"),3),f"{r.get('prev1_curr1','')}/{r.get('prev1_total','')}",f"{r.get('prev0_curr1','')}/{r.get('prev0_total','')}"] for i,(_,r) in enumerate(m.iterrows(),1)],
        )

    # Reverse pair month.
    pair_view = _latest_period(reverse_pairs, "month")
    if not pair_view.empty:
        pair_view["freq_num"] = pd.to_numeric(pair_view.get("freq"), errors="coerce").fillna(0)
        pair_view = pair_view.sort_values(["freq_num", "cooccur_days"], ascending=False).head(20)
    pair_table = _md_table(
        ["#","Cặp lộn","Tần suất","Ngày có mặt","Cùng về","TB/ngày"],
        [[i,f"**{r.get('pair','')}**",int(_safe_float(r.get("freq"))),r.get("days_hit",""),r.get("cooccur_days",""),_fmt_num(r.get("avg_per_draw"),2)] for i,(_,r) in enumerate(pair_view.iterrows(),1)] if not pair_view.empty else [],
    )

    # Weight/quality.
    w_loto, w_de = _weights("loto"), _weights("de")

    dashboard = f"""<div align="center">

# ✨ VLA · XSMB ANALYTICAL COCKPIT

**Daily · Next Draw · Probability · Statistical Matrices · AI/ML · Dynamics · Research**

![Data](https://img.shields.io/badge/DATA-{'HEALTHY' if health.get('ok') else 'CHECK'}-34d399?style=for-the-badge)
![Latest](https://img.shields.io/badge/LATEST-{latest_date.replace('-', '--')}-60a5fa?style=for-the-badge)
![Forecast](https://img.shields.io/badge/FORECAST-{target.replace('-', '--')}-a78bfa?style=for-the-badge)
![Loto Meta](https://img.shields.io/badge/LOTO_META-{'ACTIVE' if loto_meta.get('active') else 'BASELINE'}-22c55e?style=for-the-badge)
![De Meta](https://img.shields.io/badge/DE_META-{'ACTIVE' if de_meta.get('active') else 'GATED'}-fb7185?style=for-the-badge)

<sub>Auto-generated `{generated}` · mọi bảng dưới đây là số liệu trực tiếp từ pipeline VLA.</sub>

</div>

> [!IMPORTANT]
> Dashboard này tối ưu cho **quan sát dữ liệu và kiểm định mô hình**. “Dự đoán vui” là mô phỏng giải trí; probability là output thống kê/ML, không phải cam kết kết quả.

## 🧭 Quick Navigation

**[🎟 Daily](#-daily--next-draw)** · **[🔮 Probability](#-probability-arena)** · **[🔥 Frequency](#-frequency-heatmaps-0099)** · **[⏳ Gap](#-gap--rhythm)** · **[🤖 AI/ML](#-aiml--number-dynamics)** · **[🧬 Markov](#-markov--transition--dependency)** · **[🧩 Structure](#-head--tail--total--pairs)** · **[📆 Boards](#-special-boards--conditional-next-day)** · **[🧪 Significance](#-significance--research-firewall)**

---

## 💎 Executive Pulse

| 🟢 Canonical | 🟣 Forecast | 🔵 Dataset | 🟠 Quality |
| --- | --- | --- | --- |
| **{latest_date}** | **{target}** | **{health.get('row_count', len(xsmb))} kỳ** | missing **{health.get('missing_count','—')}** |
| Loto Meta: **{'ACTIVE' if loto_meta.get('active') else 'OFF'}** | trust **{_fmt_num(loto_meta.get('trust'),2)}** | skill **{_fmt_pct(loto_meta.get('logloss_skill'),2)}** | gate **{loto_meta.get('quality_pass','—')}** |
| Đề Meta: **{'ACTIVE' if de_meta.get('active') else 'OFF'}** | trust **{_fmt_num(de_meta.get('trust'),2)}** | skill **{_fmt_pct(de_meta.get('logloss_skill'),2)}** | gate **{de_meta.get('quality_pass','—')}** |

---

## 🎟️ Daily & Next Draw

### 🏆 Kết quả thực · {latest_date}

{daily}

### 🎲 Dự đoán vui · {fun.get('target_date', target)}

{_fun_board(fun)}

> 🧠 **Logic:** 2 số cuối ĐB dùng distribution Đề; 26 giải còn lại dùng distribution Loto. Prefix chỉ là deterministic simulation.

### 📅 10 kỳ gần nhất

{_recent_results(xsmb, 10)}

---

## 🔮 Probability Arena

### 🟣 Lô tô · Top probability

{forecast_table(pred_loto)}

### 🟢 Lô tô · Ma trận probability 00–99

> Heat legend: ⬜ thấp → 🟦 → 🟩 → 🟨 → 🟧 → 🟥 → 🟪 cao.

{_number_matrix(pred_loto, 'prob', percent=True, decimals=1, title='Loto probability')}

### 🌸 Đặc biệt · Top probability

{forecast_table(pred_de)}

### 🟠 Đặc biệt · Ma trận probability 00–99

{_number_matrix(pred_de, 'prob', percent=True, decimals=2, title='Đề probability')}

### ⚖️ Ensemble component weights

{_weight_table(w_loto, w_de)}

---

## 🔥 Frequency Heatmaps 00–99

### 🟦 Loto · tháng hiện tại

{_number_matrix(_period(snap_loto,'month'), 'freq', decimals=0, title='Loto month frequency')}

### 🟨 Loto · năm hiện tại

{_number_matrix(_period(snap_loto,'year'), 'freq', decimals=0, title='Loto year frequency')}

### 🟧 ĐB · tháng hiện tại

{_number_matrix(_period(snap_de,'month'), 'freq', decimals=0, title='ĐB month frequency')}

### 🟥 ĐB · năm hiện tại

{_number_matrix(_period(snap_de,'year'), 'freq', decimals=0, title='ĐB year frequency')}

<details>
<summary><strong>🧊 Mở ma trận ngày + tuần</strong></summary>

#### Loto · ngày
{_number_matrix(_period(snap_loto,'day'), 'freq', decimals=0)}

#### Loto · tuần
{_number_matrix(_period(snap_loto,'week'), 'freq', decimals=0)}

#### ĐB · ngày
{_number_matrix(_period(snap_de,'day'), 'freq', decimals=0)}

#### ĐB · tuần
{_number_matrix(_period(snap_de,'week'), 'freq', decimals=0)}

</details>

---

## ⏳ Gap & Rhythm

### 🟩 Ma trận lô gan Loto

{_number_matrix(rhythm_loto, 'current_gap', decimals=0, title='Loto gap')}

### Top Loto gan

{gap_table(rhythm_loto)}

### 🟠 Ma trận gan ĐB

{_number_matrix(rhythm_de, 'current_gap', decimals=0, title='DE gap')}

### Top ĐB gan

{gap_table(rhythm_de)}

### 🎯 Gan giải nhất

{gap_table(first_overdue, 12)}

<details>
<summary><strong>📈 Hazard curves · xác suất xuất hiện có điều kiện theo gap</strong></summary>

#### Loto hazard
{hazard_table(hazard_loto)}

#### ĐB hazard
{hazard_table(hazard_de)}

</details>

---

## 🤖 AI/ML & Number Dynamics

### 🟪 Cầu-kèo ML · Loto score matrix

{_number_matrix(cau_loto, 'cau_score', decimals=1, title='Cau Loto')}

### 🟣 Cầu-kèo ML · ĐB score matrix

{_number_matrix(cau_de, 'cau_score', decimals=1, title='Cau DE')}

### Top Cầu-kèo Loto

{_rank_table(cau_loto, value_col='cau_score', columns=['number_str','cau_score','prob_percent','primary_reason','score_band'], top_n=15, number_cols=('number_str',))}

### Top Cầu-kèo ĐB

{_rank_table(cau_de, value_col='cau_score', columns=['number_str','cau_score','prob_percent','primary_reason','score_band'], top_n=15, number_cols=('number_str',))}

### 🧠 AI/ML tổng hợp · Loto

{_number_matrix(signal_loto, 'ai_ml_signal_score', decimals=1, title='AI/ML signal Loto')}

### 🧠 AI/ML tổng hợp · ĐB

{_number_matrix(signal_de, 'ai_ml_signal_score', decimals=1, title='AI/ML signal DE')}

### 🌐 Higher-order dynamics · Loto probability

{_number_matrix(dynamics_loto, 'prob', percent=True, decimals=1, title='Dynamics Loto')}

{dynamics_table(dynamics_loto)}

### 🌐 Higher-order dynamics · ĐB probability

{_number_matrix(dynamics_de, 'prob', percent=True, decimals=2, title='Dynamics DE')}

{dynamics_table(dynamics_de)}

---

## 🧬 Markov · Transition · Dependency

### Markov-1 Loto · top lift

{markov_table}

### 🔁 100×100 transition lift · Top 25 quan hệ mạnh nhất Loto

{_wide_top_pairs(DATA / 'number_dynamics' / 'transition_lift_lag1_loto.csv', top_n=25)}

### 🔁 100×100 transition lift · Top 25 quan hệ mạnh nhất ĐB

{_wide_top_pairs(DATA / 'number_dynamics' / 'transition_lift_lag1_de.csv', top_n=25)}

### 🔗 Co-occurrence Phi · Top 25 Loto

{_wide_top_pairs(DATA / 'number_dynamics' / 'cooccurrence_phi_loto.csv', top_n=25)}

### 🔗 Co-occurrence Phi · Top 25 ĐB

{_wide_top_pairs(DATA / 'number_dynamics' / 'cooccurrence_phi_de.csv', top_n=25)}

<details>
<summary><strong>⏱️ Multi-lag dependency</strong></summary>

#### Loto
{_rank_table(_read_csv(DATA / 'number_dynamics' / 'lag_dependency_loto.csv'), value_col='lift', columns=['number_str','state','lag','lift','reliability'], top_n=25, number_cols=('number_str',))}

#### ĐB
{_rank_table(_read_csv(DATA / 'number_dynamics' / 'lag_dependency_de.csv'), value_col='lift', columns=['number_str','state','lag','lift','reliability'], top_n=25, number_cols=('number_str',))}

</details>

---

## 🧩 Head · Tail · Total · Pairs

### 🔵 Đầu Loto · tháng

{_group_rank(hht, 'month', 'head', 10)}

### 🟣 Đuôi Loto · tháng

{_group_rank(hht, 'month', 'tail', 10)}

### 🟠 Tổng Loto · tháng

{_group_rank(hht, 'month', 'total', 19)}

### 🌸 Cấu trúc ĐB · tháng

{_special_group_table(special_groups, 'month')}

### 🔄 Top cặp lộn · tháng

{pair_table}

---

## 📆 Special Boards & Conditional Next-day

### 📅 ĐB theo tuần · 12 tuần gần nhất

{_board_table(ADV / 'special_week_board.csv', tail=12)}

### 🗓️ ĐB theo tháng · 6 tháng gần nhất

{_board_table(ADV / 'special_month_board.csv', tail=6)}

### ĐB hôm trước → Loto hôm sau

{_conditional_table(ADV / 'conditional_loto_after_special_top500.csv', top_n=20)}

### Loto hôm trước → Loto hôm sau

{_conditional_table(ADV / 'conditional_loto_after_loto_top500.csv', top_n=20)}

### ĐB hôm trước → ĐB hôm sau

{_conditional_table(ADV / 'conditional_special_after_special_top500.csv', top_n=20)}

---

## 🧪 Significance & Research Firewall

### Loto · significance 30 ngày

{_significance(DATA / 'significance' / 'number_significance_loto_30d.csv')}

### Loto · significance 90 ngày

{_significance(DATA / 'significance' / 'number_significance_loto_90d.csv')}

### ĐB · significance 30 ngày

{_significance(DATA / 'significance' / 'number_significance_de_30d.csv')}

### ĐB · significance 90 ngày

{_significance(DATA / 'significance' / 'number_significance_de_90d.csv')}

### 🧫 Strategy Lab · Loto OOS

{_strategy_lab(DATA / 'research' / 'strategy_lab_loto.csv')}

### 🧫 Strategy Lab · ĐB OOS

{_strategy_lab(DATA / 'research' / 'strategy_lab_de.csv')}

### 🛡️ System / statistical diagnostics

{_diagnostic_cards()}

---

## 🗂️ Deep-dive data panels

<details>
<summary><strong>📚 Toàn bộ 10 kỳ gần nhất + nguồn audit</strong></summary>

{_recent_results(xsmb, 30)}

Canonical: [`data/xsmb.csv`](data/xsmb.csv) · Source consensus: [`data/source_audit.json`](data/source_audit.json)

</details>

<details>
<summary><strong>🧭 Deep links tới dashboard HTML tương tác</strong></summary>

- [Landing / Daily](docs/index.html)
- [Statistical matrices](docs/statistics.html)
- [AI/ML dashboard](docs/dashboard.html)
- [Model quality](docs/model-quality.html)
- [Research Lab](docs/research-lab.html)
- [Near-live](docs/live.html)

</details>

---

<div align="center">

### ✨ VLA Analytics

**GitHub-native · zero-touch daily refresh · canonical + statistical + ML + research evidence**

<sub>Generated from committed production outputs. Không dùng số liệu mock.</sub>

</div>
"""

    OUT.write_text(dashboard, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
