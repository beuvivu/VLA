from __future__ import annotations

import json
import logging
import math
from calendar import monthrange
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from ui_locale import strategy_label, value_label

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ADV = DATA / "advanced"
OUT = ROOT / "DASHBOARD.md"
logger = logging.getLogger(__name__)

HEAT = ["⬜", "🟦", "🟩", "🟨", "🟧", "🟥", "🟪"]
HEAT_MEANING = [
    "Rất thấp so với các số khác trong cùng ma trận",
    "Thấp",
    "Dưới vùng trung tâm",
    "Trung tính / vùng giữa",
    "Trên vùng trung tâm",
    "Cao",
    "Rất cao so với các số khác trong cùng ma trận",
]
BAR_WIDTH = 10

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
    if digits == 0:
        return f"{int(round(x)):,}".replace(",", ".")
    return f"{x:.{digits}f}"


def _fmt_pct(value: Any, digits: int = 2, *, already_percent: bool = False) -> str:
    x = _safe_float(value, float("nan"))
    if not math.isfinite(x):
        return "—"
    if not already_percent:
        x *= 100.0
    return f"{x:.{digits}f}%"


def _short(value: Any, limit: int = 46) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


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


def _bar(value: float, max_value: float, width: int = BAR_WIDTH) -> str:
    if max_value <= 0:
        return "▱" * width
    n = max(0, min(width, int(round(abs(value) / max_value * width))))
    return "▰" * n + "▱" * (width - n)


def _bar_legend() -> str:
    return _md_table(
        ["Ký hiệu", "Mức", "Ý nghĩa"],
        [
            ["▰▰▱▱▱▱▱▱▱▱", "Thấp", "Giá trị nhỏ tương đối trong chính bảng đang xem"],
            ["▰▰▰▰▰▱▱▱▱▱", "Trung bình", "Nằm quanh vùng giữa của nhóm so sánh"],
            ["▰▰▰▰▰▰▰▰▰▰", "Cao", "Thuộc nhóm giá trị lớn nhất trong bảng"],
        ],
    )


def _number_col(df: pd.DataFrame) -> str | None:
    for c in ("number_str", "number"):
        if c in df.columns:
            return c
    return None


def _heat_idx(value: float, lo: float, hi: float) -> int:
    if not math.isfinite(value):
        return 0
    if hi <= lo:
        return 3
    t = max(0.0, min(1.0, (value - lo) / (hi - lo)))
    return min(6, int(t * 7.0))


def _heat_legend(lo: float, hi: float, *, percent: bool, decimals: int, metric: str) -> str:
    rows: list[list[str]] = []
    span = max(0.0, hi - lo)
    for i, color in enumerate(HEAT):
        a = lo + span * i / 7.0
        b = hi if i == 6 else lo + span * (i + 1) / 7.0
        fa = _fmt_pct(a, decimals) if percent else _fmt_num(a, decimals)
        fb = _fmt_pct(b, decimals) if percent else _fmt_num(b, decimals)
        rows.append([color, f"{fa} → {fb}", HEAT_MEANING[i]])
    return (
        f"> **Cách đọc màu – {metric}:** màu chỉ biểu thị **mức tương đối trong chính ma trận này**, "
        "không tự động đồng nghĩa với khả năng chắc chắn.\n\n"
        + _md_table(["Màu", "Khoảng giá trị", "Ý nghĩa"], rows)
    )


def _number_matrix(
    df: pd.DataFrame,
    value_col: str,
    *,
    percent: bool = False,
    decimals: int = 1,
    metric: str,
) -> str:
    ncol = _number_col(df)
    if df.empty or not ncol or value_col not in df.columns:
        return f"_Chưa đủ dữ liệu cho {metric}._"
    values: dict[int, float] = {}
    for _, row in df.iterrows():
        try:
            n = int(float(row[ncol]))
        except (TypeError, ValueError) as exc:
            logger.debug("Bỏ qua mã số không hợp lệ %r: %s", row[ncol], exc)
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
            idx = _heat_idx(v, lo, hi)
            txt = _fmt_pct(v, decimals) if percent else _fmt_num(v, decimals)
            line.append(f"{HEAT[idx]}<br>`{n:02d}`<br>**{txt}**")
        rows.append(line)
    return _heat_legend(lo, hi, percent=percent, decimals=decimals, metric=metric) + "\n\n" + _md_table(
        ["Đầu\\Đuôi", *[str(i) for i in range(10)]], rows
    )


def _balanced_rank(
    df: pd.DataFrame,
    *,
    score_col: str,
    label_col: str,
    compare_col: str | None = None,
    top_n: int = 15,
    percent_score: bool = False,
    score_already_percent: bool = False,
    meaning_fn: Any = None,
    descending: bool = True,
) -> str:
    if df.empty or score_col not in df.columns:
        return "_Chưa có dữ liệu._"
    view = df.copy()
    view["__score"] = pd.to_numeric(view[score_col], errors="coerce")
    view = view.sort_values("__score", ascending=not descending).head(top_n)
    max_v = float(view["__score"].abs().max()) if not view.empty else 1.0
    rows = []
    for i, (_, r) in enumerate(view.iterrows(), 1):
        score = _safe_float(r.get(score_col))
        if percent_score:
            score_txt = _fmt_pct(score, 2, already_percent=score_already_percent)
        else:
            score_txt = _fmt_num(score, 3)
        compare = _short(r.get(compare_col, "—"), 34) if compare_col else "—"
        meaning = meaning_fn(r) if meaning_fn else "Xếp hạng tương đối trong cùng bảng"
        rows.append(
            [i, f"**{_fmt2(r.get(label_col))}**" if label_col in {"number", "number_str"} else _short(r.get(label_col), 28), score_txt, compare, _short(meaning, 52), _bar(score, max_v)]
        )
    return _md_table(
        ["#", "Đối tượng", "Giá trị", "So sánh / căn cứ", "Ý nghĩa", "Thanh so sánh"],
        rows,
    )


def _daily_board(df: pd.DataFrame) -> tuple[str, str]:
    if df.empty:
        return "—", "_Chưa có dữ liệu._"
    row = df.iloc[-1]
    day = str(row.get("date", ""))
    rows = []
    for label, cols, width in PRIZE_GROUPS:
        vals = " · ".join(_fmt_code(row.get(c), width) for c in cols)
        suffix = " · ".join(_fmt2(str(_fmt_code(row.get(c), width))[-2:]) for c in cols)
        rows.append([label, f"**{vals}**" if label == "Đặc biệt" else vals, suffix, "Kết quả chuẩn đã xác minh"])
    return day, _md_table(["Giải", "Kết quả", "2 số cuối", "Ý nghĩa"], rows)


def _fun_board(payload: dict[str, Any]) -> str:
    rows = []
    for group in payload.get("groups", []) if isinstance(payload.get("groups"), list) else []:
        vals = group.get("values", []) if isinstance(group, dict) else []
        numbers = " · ".join(str(v.get("value", "")) for v in vals if isinstance(v, dict))
        suffix = " · ".join(f"`{v.get('suffix','')}` {_fmt_pct(v.get('model_prob',0),2)}" for v in vals if isinstance(v, dict))
        rows.append(
            [
                group.get("label", ""),
                numbers,
                suffix,
                "Mô phỏng tất định; xác suất chỉ áp dụng cho 2 số cuối",
            ]
        )
    return _md_table(["Giải", "Mô phỏng", "Hai số cuối · xác suất", "Ý nghĩa"], rows)


def _recent_results(df: pd.DataFrame, n: int = 10) -> str:
    if df.empty:
        return "_Chưa có dữ liệu._"
    rows = []
    for _, r in df.tail(n).iloc[::-1].iterrows():
        rows.append([r.get("date", ""), f"**{_fmt_code(r.get('special'),5)}**", _fmt_code(r.get("prize1"),5), " · ".join(_fmt_code(r.get(f"prize7_{i}"),2) for i in range(1,5)), "Đối chiếu xu hướng gần nhất"])
    return _md_table(["Ngày", "ĐB", "G1", "G7", "Ý nghĩa"], rows)


def _prediction(mode: str, target: str) -> pd.DataFrame:
    preferred = DATA / "predict" / f"predict_next_{mode}_all_{target}.csv"
    if preferred.exists():
        return _read_csv(preferred)
    files = sorted((DATA / "predict").glob(f"predict_next_{mode}_all_*.csv"))
    return _read_csv(files[-1]) if files else pd.DataFrame()


def _forecast_table(df: pd.DataFrame, mode: str, top_n: int = 15) -> str:
    if df.empty or "prob" not in df.columns:
        return "_Chưa có dự báo._"
    view = df.copy()
    view["__p"] = pd.to_numeric(view["prob"], errors="coerce").fillna(0)
    view = view.sort_values("__p", ascending=False).head(top_n)
    max_p = float(view["__p"].max()) if not view.empty else 1.0
    rows = []
    for i, (_, r) in enumerate(view.iterrows(), 1):
        p = _safe_float(r.get("prob"))
        agree = str(value_label(str(r.get("agreement_tier", "—"))))
        dispersion = _safe_float(r.get("component_disagreement"))
        meaning = "Ưu tiên tương đối cao" if i <= 4 else "Theo dõi trong nhóm xếp hạng"
        if agree == "low":
            meaning += "; độ đồng thuận mô hình thấp"
        rows.append([i, f"**{_fmt2(r.get('number_str',r.get('number')))}**", _fmt_pct(p,3), f"{agree} · disp {_fmt_num(dispersion,3)}", meaning, _bar(p,max_p)])
    return _md_table(
        ["#", "Số", "Xác suất cuối", "Đồng thuận", "Ý nghĩa", "Thanh so sánh"],
        rows,
    )


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


def _gap_table(df: pd.DataFrame, top_n: int = 15) -> str:
    if df.empty or "current_gap" not in df.columns:
        return "_Chưa có dữ liệu._"
    view = df.copy()
    view["__gap"] = pd.to_numeric(view["current_gap"], errors="coerce").fillna(0)
    view = view.sort_values("__gap", ascending=False).head(top_n)
    max_g = float(view["__gap"].max()) if not view.empty else 1.0
    rows = []
    for i, (_, r) in enumerate(view.iterrows(), 1):
        gap = _safe_float(r.get("current_gap"))
        mean_gap = _safe_float(r.get("mean_gap"))
        ratio = gap / mean_gap if mean_gap > 0 else 0
        meaning = "Gan hiện tại vượt gan trung bình" if ratio > 1.25 else "Gan trong vùng lịch sử thường gặp"
        rows.append([i, f"**{_fmt2(r.get('number_str',r.get('number')))}**", _fmt_num(gap,0), f"TB {_fmt_num(mean_gap,2)} · lớn nhất {_fmt_num(r.get('max_gap'),0)}", meaning, _bar(gap,max_g)])
    return _md_table(["#", "Số", "Gan hiện tại", "So sánh lịch sử", "Ý nghĩa", "Thanh so sánh"], rows)


def _hazard_table(df: pd.DataFrame, max_gap: int = 25) -> str:
    if df.empty or "hazard" not in df.columns:
        return "_Chưa có dữ liệu._"
    view = df[pd.to_numeric(df.get("gap"), errors="coerce").fillna(0) <= max_gap].copy()
    max_h = float(pd.to_numeric(view["hazard"], errors="coerce").fillna(0).max()) if not view.empty else 1.0
    rows = []
    for _, r in view.iterrows():
        h = _safe_float(r.get("hazard"))
        rows.append([int(_safe_float(r.get("gap"))), _fmt_pct(h,2), f"{int(_safe_float(r.get('hits')))} / {int(_safe_float(r.get('denom')))}", "Xác suất thực nghiệm có điều kiện tại mức gan này", _bar(h,max_h)])
    return _md_table(
        ["Mức gan", "Tỷ suất xuất hiện", "Trúng / số lần quan sát", "Ý nghĩa", "Thanh so sánh"],
        rows,
    )


def _group_table(df: pd.DataFrame, kind: str, group: str, top_n: int) -> str:
    view = _latest_period(df, kind)
    if not view.empty and "group_type" in view.columns:
        view = view[view["group_type"].astype(str) == group].copy()
    if view.empty:
        return "_Chưa có dữ liệu._"
    view["__f"] = pd.to_numeric(view.get("freq"), errors="coerce").fillna(0)
    view = view.sort_values("__f", ascending=False).head(top_n)
    max_f = float(view["__f"].max()) if not view.empty else 1.0
    rows = []
    for i, (_, r) in enumerate(view.iterrows(),1):
        f = _safe_float(r.get("freq"))
        rows.append([i, str(r.get("group_value","")), _fmt_num(f,0), f"hạng {r.get('rank_in_period_group','—')}", "Tần suất tương đối trong kỳ", _bar(f,max_f)])
    return _md_table(["#", "Nhóm", "Tần suất", "Xếp hạng", "Ý nghĩa", "Thanh so sánh"], rows)


def _special_group_table(df: pd.DataFrame, kind: str = "month") -> str:
    view = _latest_period(df, kind)
    if view.empty:
        return "_Chưa có dữ liệu._"
    rows = []
    labels = {"db_head":"Đầu ĐB","db_tail":"Đuôi ĐB","db_cham":"Chạm ĐB","db_total":"Tổng ĐB"}
    for group, label in labels.items():
        g = view[view["group_type"].astype(str) == group].copy()
        if g.empty:
            continue
        g["__f"] = pd.to_numeric(g["freq"], errors="coerce").fillna(0)
        g = g.sort_values("__f", ascending=False).head(5)
        top = " · ".join(f"**{r['group_value']}** ({int(r['__f'])})" for _,r in g.iterrows())
        rows.append([label, top, "5 nhóm đầu", "Nhìn cấu trúc phân bố thay vì một số đơn lẻ"])
    return _md_table(["Nhóm", "Phân bố nổi bật", "Phạm vi", "Ý nghĩa"], rows)


def _reverse_pairs(df: pd.DataFrame, top_n: int = 15) -> str:
    view = _latest_period(df,"month")
    if view.empty:
        return "_Chưa có dữ liệu._"
    view["__f"] = pd.to_numeric(view.get("freq"), errors="coerce").fillna(0)
    view = view.sort_values(["__f","cooccur_days"],ascending=False).head(top_n)
    max_f = float(view["__f"].max()) if not view.empty else 1.0
    rows=[]
    for i,(_,r) in enumerate(view.iterrows(),1):
        f=_safe_float(r.get("freq"))
        rows.append([i,f"**{r.get('pair','')}**",_fmt_num(f,0),f"cùng về {r.get('cooccur_days','—')} ngày","Cặp đảo có tần suất cao trong tháng",_bar(f,max_f)])
    return _md_table(["#","Cặp lộn","Tần suất","So sánh","Ý nghĩa","Thanh so sánh"],rows)


def _wide_top_pairs(path: Path, *, top_n: int = 20, metric_name: str) -> str:
    df = _read_csv(path)
    if df.empty or len(df.columns) < 3:
        return "_Chưa có dữ liệu._"
    source_col = df.columns[0]
    pairs: list[tuple[str,str,float]]=[]
    for _,r in df.iterrows():
        src=_fmt2(r[source_col])
        for c in df.columns[1:]:
            dst=_fmt2(c)
            if src == dst:
                continue
            v=_safe_float(r[c],float("nan"))
            if math.isfinite(v):
                pairs.append((src,dst,v))
    pairs.sort(key=lambda x:x[2],reverse=True)
    chosen=pairs[:top_n]
    max_v=max((abs(v) for _,_,v in chosen),default=1.0)
    rows=[]
    for i,(src,dst,v) in enumerate(chosen,1):
        metric_kind = path.name.lower()
        meaning = "Quan hệ dương mạnh" if v>1 and "lift" in metric_kind else "Quan hệ nổi bật tương đối"
        if "phi" in metric_kind:
            meaning = "Đồng xuất hiện dương mạnh hơn các cặp khác" if v>0 else "Đồng xuất hiện âm"
        rows.append([i,f"`{src}` → **`{dst}`**",_fmt_num(v,4),metric_name,meaning,_bar(v,max_v)])
    return _md_table(["#","Quan hệ","Giá trị","Chỉ số","Ý nghĩa","Thanh so sánh"],rows)


def _lag_dependency(path: Path, top_n: int=20) -> str:
    df=_read_csv(path)
    if df.empty or "lift_vs_baseline" not in df.columns:
        return "_Chưa có dữ liệu._"
    df["__lift"]=pd.to_numeric(df["lift_vs_baseline"],errors="coerce").fillna(0)
    df=df.sort_values("__lift",ascending=False).head(top_n)
    max_v=float(df["__lift"].abs().max()) if not df.empty else 1.0
    rows=[]
    for i,(_,r) in enumerate(df.iterrows(),1):
        lift=_safe_float(r.get("lift_vs_baseline"))
        state="trúng" if str(r.get("state"))=="1" else "trượt"
        meaning="Tín hiệu tăng so với nền" if lift>1 else "Không cao hơn nền"
        rows.append([i,f"**{_fmt2(r.get('number'))}**",_fmt_num(lift,3),f"trễ {r.get('lag')} · trước={state} · mẫu={_fmt_num(r.get('trials'),0)}",meaning,_bar(lift,max_v)])
    return _md_table(["#","Số","Độ nâng so với nền","Điều kiện","Ý nghĩa","Thanh so sánh"],rows)


def _month_calendar(path: Path, months: int=4) -> str:
    df=_read_csv(path,dtype=str)
    if df.empty or "month_key" not in df.columns:
        return "_Chưa có dữ liệu._"
    blocks=[]
    weekdays=["T2","T3","T4","T5","T6","T7","CN"]
    for _,r in df.tail(months).iloc[::-1].iterrows():
        key=str(r.get("month_key",""))
        try:
            y,m=[int(x) for x in key.split("-")[:2]]
        except (TypeError, ValueError) as exc:
            logger.debug("Bỏ qua khóa tháng không hợp lệ %r: %s", key, exc)
            continue
        first=date(y,m,1).weekday()
        days=monthrange(y,m)[1]
        cells=[""]*first
        for d in range(1,days+1):
            val=str(r.get(f"{d:02d}","")).strip()
            cells.append(f"**{d:02d}**<br>`{val}`" if val else f"{d:02d}<br>—")
        while len(cells)%7:
            cells.append("")
        rows=[cells[i:i+7] for i in range(0,len(cells),7)]
        blocks.append(f"#### {key}\n\n"+_md_table(weekdays,rows))
    return "\n\n".join(blocks)


def _week_board(path: Path, tail: int=10) -> str:
    df=_read_csv(path,dtype=str)
    if df.empty:
        return "_Chưa có dữ liệu._"
    view=df.tail(tail).iloc[::-1]
    return _md_table(["Tuần","T2","T3","T4","T5","T6","T7","CN"],[[r.get("week_key",""),*[r.get(c,"") for c in ["T2","T3","T4","T5","T6","T7","CN"]]] for _,r in view.iterrows()])


def _conditional(path: Path, top_n: int=15) -> str:
    df=_read_csv(path)
    if df.empty:
        return "_Chưa có dữ liệu._"
    score="conditional_rate" if "conditional_rate" in df.columns else "rate" if "rate" in df.columns else "count"
    df["__s"]=pd.to_numeric(df[score],errors="coerce").fillna(0)
    df=df.sort_values("__s",ascending=False).head(top_n)
    prev=next((c for c in ["prev_special_2d","prev_loto","prev_special"] if c in df.columns),None)
    nxt=next((c for c in ["next_loto","next_special_2d","next_special"] if c in df.columns),None)
    max_v=float(df["__s"].max()) if not df.empty else 1.0
    rows=[]
    for i,(_,r) in enumerate(df.iterrows(),1):
        s=_safe_float(r.get(score))
        sample=_safe_float(r.get("base_count",r.get("count",0)))
        meaning="Mẫu nhỏ – chỉ tham khảo" if sample<10 else "Có mẫu lịch sử tương đối tốt hơn"
        score_txt=_fmt_pct(s,2) if "rate" in score else _fmt_num(s,3)
        rows.append([i,f"`{_fmt2(r.get(prev))}` → **`{_fmt2(r.get(nxt))}`**" if prev and nxt else "—",score_txt,f"n={_fmt_num(sample,0)}",meaning,_bar(s,max_v)])
    return _md_table(["#","Điều kiện → kết quả","Tỷ lệ","Mẫu","Ý nghĩa","Thanh so sánh"],rows)


def _significance(path: Path, top_n: int=15) -> str:
    df=_read_csv(path)
    if df.empty:
        return "_Chưa có dữ liệu._"
    df["__e"]=pd.to_numeric(df.get("evidence_score",df.get("z_score")),errors="coerce").abs().fillna(0)
    df=df.sort_values("__e",ascending=False).head(top_n)
    max_v=float(df["__e"].max()) if not df.empty else 1.0
    rows=[]
    for i,(_,r) in enumerate(df.iterrows(),1):
        lift=_safe_float(r.get("lift"))
        q=_safe_float(r.get("q_value_fdr"),1.0)
        sig=str(r.get("fdr_05","")).lower()=="true"
        meaning="Qua FDR 5%" if sig else "Chưa đủ bằng chứng sau hiệu chỉnh đa kiểm định"
        rows.append([i,f"**{_fmt2(r.get('number_str',r.get('number')))}**",_fmt_num(lift,3),f"p {_fmt_num(r.get('p_value'),4)} · q {_fmt_num(q,4)}",meaning,_bar(_safe_float(r.get("__e")),max_v)])
    return _md_table(["#","Số","Độ nâng","p / q (FDR)","Ý nghĩa","Thanh so sánh"],rows)


def _strategy(path: Path, top_n: int=15) -> str:
    df=_read_csv(path)
    if df.empty or "holdout_lift" not in df.columns:
        return "_Chưa có dữ liệu._"
    df["__l"]=pd.to_numeric(df["holdout_lift"],errors="coerce").fillna(0)
    df=df.sort_values("__l",ascending=False).head(top_n)
    max_v=float(df["__l"].max()) if not df.empty else 1.0
    rows=[]
    for i,(_,r) in enumerate(df.iterrows(),1):
        lift=_safe_float(r.get("holdout_lift"))
        q=_safe_float(r.get("holdout_q_value_fdr"),1.0)
        gate=str(r.get("research_gate_pass","")).lower()=="true"
        meaning="Qua cổng nghiên cứu" if gate else "Chỉ nghiên cứu; chưa qua FDR/cổng"
        rows.append([i,_short(strategy_label(r.get("strategy")),28),_fmt_num(lift,3),f"độ chính xác {_fmt_pct(r.get('holdout_precision'),2)} · q {_fmt_num(q,3)}",meaning,_bar(lift,max_v)])
    return _md_table(["#","Chiến lược","Độ nâng ngoài mẫu","Tập giữ lại","Ý nghĩa","Thanh so sánh"],rows)


def _dynamics(df: pd.DataFrame, top_n: int=15) -> str:
    if df.empty or "prob" not in df.columns:
        return "_Chưa có dữ liệu._"
    df=df.copy(); df["__p"]=pd.to_numeric(df["prob"],errors="coerce").fillna(0); df=df.sort_values("__p",ascending=False).head(top_n)
    max_v=float(df["__p"].max()) if not df.empty else 1.0
    rows=[]
    for i,(_,r) in enumerate(df.iterrows(),1):
        p=_safe_float(r.get("prob")); base=_safe_float(r.get("baseline_prob")); delta=p-base
        meaning="Động lực cao hơn nền" if delta>0 else "Động lực không cao hơn nền"
        rows.append([i,f"**{_fmt2(r.get('number_str',r.get('number')))}**",_fmt_pct(p,2),f"nền {_fmt_pct(base,2)} · Δ {_fmt_pct(delta,2)}",meaning,_bar(p,max_v)])
    return _md_table(["#","Số","Xác suất động lực","So với nền","Ý nghĩa","Thanh so sánh"],rows)


def _markov(df: pd.DataFrame, top_n: int=15) -> str:
    if df.empty or "lift" not in df.columns:
        return "_Chưa có dữ liệu._"
    df=df.copy(); df["__l"]=pd.to_numeric(df["lift"],errors="coerce").fillna(0); df=df.sort_values("__l",ascending=False).head(top_n)
    max_v=float(df["__l"].max()) if not df.empty else 1.0
    rows=[]
    for i,(_,r) in enumerate(df.iterrows(),1):
        lift=_safe_float(r.get("lift")); meaning="Có tính duy trì dương" if lift>1 else "Không có tính duy trì dương"
        rows.append([i,f"**{_fmt2(r.get('number'))}**",_fmt_num(lift,3),f"P1 {_fmt_pct(r.get('p_hit_given_hit'),2)} · P0 {_fmt_pct(r.get('p_hit_given_miss'),2)}",meaning,_bar(lift,max_v)])
    return _md_table(["#","Số","Độ nâng","P(trúng|trúng) / P(trúng|trượt)","Ý nghĩa","Thanh so sánh"],rows)


def _diagnostics() -> str:
    health=_read_json(DATA/"health.json")
    dl=_read_json(DATA/"number_dynamics"/"diagnostics_loto.json")
    dd=_read_json(DATA/"number_dynamics"/"diagnostics_de.json")
    return _md_table(["Lớp","Giá trị","So sánh","Ý nghĩa"],[
        ["Sức khỏe dữ liệu","✅ ĐẠT" if health.get("ok") else "⚠️ CẦN KIỂM TRA",f"số dòng {health.get('row_count','—')} · thiếu {health.get('missing_count','—')}","Tính toàn vẹn dữ liệu chuẩn"],
        ["Động lực lô tô",_fmt_num(dl.get("global_dynamics_reliability"),3),f"JS 30/180 {_fmt_num(dl.get('regime_js_divergence_30_vs_180'),4)}","Độ tin cậy + dịch chuyển chế độ"],
        ["Động lực ĐB",_fmt_num(dd.get("global_dynamics_reliability"),3),f"JS 30/180 {_fmt_num(dd.get('regime_js_divergence_30_vs_180'),4)}","Độ tin cậy + dịch chuyển chế độ"],
    ])


def main() -> None:
    health=_read_json(DATA/"health.json")
    xsmb=_read_csv(DATA/"xsmb.csv")
    fun=_read_json(DATA/"predict"/"fun_draw_next.json")
    picks_l=_read_json(DATA/"predict"/"picks_loto.json")
    picks_d=_read_json(DATA/"predict"/"picks_de.json")
    latest,daily=_daily_board(xsmb)
    target=str(picks_l.get("target_date") or picks_d.get("target_date") or fun.get("target_date") or "—")
    pred_l=_prediction("loto",target); pred_d=_prediction("de",target)
    snap_l=_read_csv(ADV/"period_snapshot_loto_current.csv"); snap_d=_read_csv(ADV/"period_snapshot_de_current.csv")
    rhythm_l=_read_csv(ADV/"loto_rhythm.csv"); rhythm_d=_read_csv(ADV/"de_rhythm.csv")
    first=_read_csv(ADV/"first_prize_overdue.csv")
    hht=_read_csv(ADV/"head_tail_total_loto_current.csv"); sg=_read_csv(ADV/"special_group_frequency_current.csv"); pairs=_read_csv(ADV/"reverse_pair_frequency_current.csv")
    cau_l=_read_csv(DATA/"ai_ml"/"cau_keo_loto_all.csv"); cau_d=_read_csv(DATA/"ai_ml"/"cau_keo_de_all.csv")
    sig_l=_read_csv(ADV/"ai_ml_signal_loto.csv"); sig_d=_read_csv(ADV/"ai_ml_signal_de.csv")
    dyn_l=_read_csv(DATA/"number_dynamics"/"current_dynamics_loto.csv"); dyn_d=_read_csv(DATA/"number_dynamics"/"current_dynamics_de.csv")
    markov=_read_csv(DATA/"markov"/"markov_loto.csv")
    hazard_l=_read_csv(DATA/"hazard"/"hazard_loto.csv"); hazard_d=_read_csv(DATA/"hazard"/"hazard_de.csv")
    meta_l=picks_l.get("meta",{}) if isinstance(picks_l.get("meta"),dict) else {}; meta_d=picks_d.get("meta",{}) if isinstance(picks_d.get("meta"),dict) else {}
    generated=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00","Z")

    cau_mean=lambda r: f"{_short(r.get('primary_reason','Tín hiệu tổng hợp'),38)}"

    md=f'''<div align="center">

# ✨ VLA · TRUNG TÂM PHÂN TÍCH XSMB

**Giao diện cân đối · chú giải rõ ràng · bảng phân tích dễ so sánh**

![Dữ liệu](https://img.shields.io/badge/DU_LIEU-{'TOT' if health.get('ok') else 'KIEM_TRA'}-34d399?style=for-the-badge)
![Mới nhất](https://img.shields.io/badge/MOI_NHAT-{latest.replace('-', '--')}-60a5fa?style=for-the-badge)
![Dự báo](https://img.shields.io/badge/DU_BAO-{target.replace('-', '--')}-a78bfa?style=for-the-badge)
![Meta lô tô](https://img.shields.io/badge/META_LO_TO-{'DANG_BAT' if meta_l.get('active') else 'NEN'}-22c55e?style=for-the-badge)
![Meta Đặc Biệt](https://img.shields.io/badge/META_DAC_BIET-{'DANG_BAT' if meta_d.get('active') else 'DA_CHAN'}-fb7185?style=for-the-badge)

<sub>Tạo lúc {generated} · dữ liệu chuẩn + thống kê + ML + bằng chứng nghiên cứu.</sub>

</div>

> [!IMPORTANT]
> **Quy ước giao diện:** mọi ma trận nhiệt đều có bảng `Màu | Khoảng giá trị | Ý nghĩa` ngay phía trên; mọi thanh `▰▱` đều là xếp hạng **tương đối trong chính bảng**, không phải xác suất chắc chắn. Các bảng phân tích được chuẩn hóa 6 cột để hạn chế chênh lệch bề ngang.

## 🧭 Điều hướng

**[Kết quả ngày](#daily--next-draw)** · **[Xác suất](#probability-arena)** · **[Tần suất](#frequency-heatmaps-0099)** · **[Gan](#gap--rhythm)** · **[AI/ML](#aiml--dynamics)** · **[Markov](#markov--transition--dependency)** · **[Cấu trúc](#structure--pairs)** · **[Bảng lịch](#special-boards--conditional)** · **[Nghiên cứu](#significance--research)**

---

## 💎 Tóm tắt điều hành

| Ngày dữ liệu chuẩn | Ngày dự báo | Bộ dữ liệu | Trạng thái mô hình |
| --- | --- | --- | --- |
| **{latest}** | **{target}** | **{health.get('row_count',len(xsmb))} kỳ · thiếu {health.get('missing_count','—')}** | Meta lô tô **{'ĐANG BẬT' if meta_l.get('active') else 'TẮT'}** · Đặc Biệt **{'ĐANG BẬT' if meta_d.get('active') else 'ĐÃ CHẶN'}** |

---

<a id="daily--next-draw"></a>
## 🎟️ Kết quả ngày và kỳ tiếp theo

### Kết quả chuẩn · {latest}

{daily}

### Dự đoán vui · {fun.get('target_date',target)}

{_fun_board(fun)}

### 10 kỳ gần nhất

{_recent_results(xsmb,10)}

---

<a id="probability-arena"></a>
## 🔮 Khu vực xác suất

### Lô tô · Xác suất cao nhất

{_bar_legend()}

{_forecast_table(pred_l,'loto')}

### Lô tô · Ma trận nhiệt xác suất 00–99

{_number_matrix(pred_l,'prob',percent=True,decimals=2,metric='Xác suất cuối lô tô')}

### ĐB · Xác suất cao nhất

{_forecast_table(pred_d,'de')}

### ĐB · Ma trận nhiệt xác suất 00–99

{_number_matrix(pred_d,'prob',percent=True,decimals=3,metric='Xác suất cuối ĐB')}

---

<a id="frequency-heatmaps-0099"></a>
## 🔥 Ma trận nhiệt tần suất 00–99

### Lô tô · tháng
{_number_matrix(_period(snap_l,'month'),'freq',decimals=0,metric='Tần suất lô tô tháng')}

### ĐB · tháng
{_number_matrix(_period(snap_d,'month'),'freq',decimals=0,metric='Tần suất ĐB tháng')}

### Lô tô · năm
{_number_matrix(_period(snap_l,'year'),'freq',decimals=0,metric='Tần suất lô tô năm')}

### ĐB · năm
{_number_matrix(_period(snap_d,'year'),'freq',decimals=0,metric='Tần suất ĐB năm')}

### Lô tô · tuần
{_number_matrix(_period(snap_l,'week'),'freq',decimals=0,metric='Tần suất lô tô tuần')}

### ĐB · tuần
{_number_matrix(_period(snap_d,'week'),'freq',decimals=0,metric='Tần suất ĐB tuần')}

---

<a id="gap--rhythm"></a>
## ⏳ Gan và nhịp

### Ma trận nhiệt gan lô tô
{_number_matrix(rhythm_l,'current_gap',decimals=0,metric='Gan hiện tại của lô tô')}

### Gan lô tô đứng đầu
{_bar_legend()}

{_gap_table(rhythm_l)}

### Ma trận nhiệt gan ĐB
{_number_matrix(rhythm_d,'current_gap',decimals=0,metric='Gan hiện tại của ĐB')}

### Gan ĐB đứng đầu
{_gap_table(rhythm_d)}

### Gan giải nhất
{_gap_table(first,12)}

### Tỷ suất xuất hiện theo gan lô tô
{_hazard_table(hazard_l)}

### Tỷ suất xuất hiện theo gan ĐB
{_hazard_table(hazard_d)}

---

<a id="aiml--dynamics"></a>
## 🤖 AI/ML và động lực

### Cầu-kèo lô tô · ma trận nhiệt điểm
{_number_matrix(cau_l,'cau_score',decimals=1,metric='Điểm cầu-kèo ML lô tô')}

### Cầu-kèo lô tô đứng đầu
{_balanced_rank(cau_l,score_col='cau_score',label_col='number_str',compare_col='primary_reason',meaning_fn=cau_mean)}

### Cầu-kèo ĐB · ma trận nhiệt điểm
{_number_matrix(cau_d,'cau_score',decimals=1,metric='Điểm cầu-kèo ML ĐB')}

### Cầu-kèo ĐB đứng đầu
{_balanced_rank(cau_d,score_col='cau_score',label_col='number_str',compare_col='primary_reason',meaning_fn=cau_mean)}

### AI/ML tổng hợp · Lô tô
{_number_matrix(sig_l,'ai_ml_signal_score',decimals=1,metric='AI/ML tổng hợp lô tô')}

### AI/ML tổng hợp · ĐB
{_number_matrix(sig_d,'ai_ml_signal_score',decimals=1,metric='AI/ML tổng hợp ĐB')}

### Động lực bậc cao · Lô tô
{_number_matrix(dyn_l,'prob',percent=True,decimals=2,metric='Xác suất động lực lô tô')}

{_dynamics(dyn_l)}

### Động lực bậc cao · ĐB
{_number_matrix(dyn_d,'prob',percent=True,decimals=3,metric='Xác suất động lực ĐB')}

{_dynamics(dyn_d)}

---

<a id="markov--transition--dependency"></a>
## 🧬 Markov · chuyển tiếp · phụ thuộc

### Markov bậc 1 · Lô tô
{_bar_legend()}

{_markov(markov)}

### Độ nâng chuyển tiếp lô tô · bỏ cặp tự thân
{_wide_top_pairs(DATA/'number_dynamics'/'transition_lift_lag1_loto.csv',top_n=20,metric_name='Độ nâng chuyển tiếp')}

### Độ nâng chuyển tiếp ĐB · bỏ cặp tự thân
{_wide_top_pairs(DATA/'number_dynamics'/'transition_lift_lag1_de.csv',top_n=20,metric_name='Độ nâng chuyển tiếp')}

### Đồng xuất hiện Phi lô tô · bỏ đường chéo tự thân
{_wide_top_pairs(DATA/'number_dynamics'/'cooccurrence_phi_loto.csv',top_n=20,metric_name='Đồng xuất hiện Phi')}

### Đồng xuất hiện Phi ĐB · bỏ đường chéo tự thân
{_wide_top_pairs(DATA/'number_dynamics'/'cooccurrence_phi_de.csv',top_n=20,metric_name='Đồng xuất hiện Phi')}

### Phụ thuộc đa độ trễ lô tô
{_lag_dependency(DATA/'number_dynamics'/'lag_dependency_loto.csv')}

### Phụ thuộc đa độ trễ ĐB
{_lag_dependency(DATA/'number_dynamics'/'lag_dependency_de.csv')}

---

<a id="structure--pairs"></a>
## 🧩 Cấu trúc và cặp số

### Đầu lô tô · tháng
{_group_table(hht,'month','head',10)}

### Đuôi lô tô · tháng
{_group_table(hht,'month','tail',10)}

### Tổng lô tô · tháng
{_group_table(hht,'month','total',19)}

### Cấu trúc ĐB · tháng
{_special_group_table(sg,'month')}

### Cặp lộn · tháng
{_reverse_pairs(pairs)}

---

<a id="special-boards--conditional"></a>
## 📆 Bảng đặc biệt và quan hệ có điều kiện

### ĐB theo tuần
{_week_board(ADV/'special_week_board.csv',10)}

### ĐB theo tháng · lịch 7 cột

> Thay cho bảng 31 cột trước đây. Mỗi ô là `ngày / 2 số cuối ĐB`, nhờ đó bề ngang ổn định và không làm vỡ phần cuối trang.

{_month_calendar(ADV/'special_month_board.csv',4)}

### ĐB hôm trước → lô tô hôm sau
{_conditional(ADV/'conditional_loto_after_special_top500.csv')}

### Lô tô hôm trước → lô tô hôm sau
{_conditional(ADV/'conditional_loto_after_loto_top500.csv')}

### ĐB hôm trước → ĐB hôm sau
{_conditional(ADV/'conditional_special_after_special_top500.csv')}

---

<a id="significance--research"></a>
## 🧪 Mức ý nghĩa và nghiên cứu

### Lô tô · mức ý nghĩa 30 ngày
{_significance(DATA/'significance'/'number_significance_loto_30d.csv')}

### Lô tô · mức ý nghĩa 90 ngày
{_significance(DATA/'significance'/'number_significance_loto_90d.csv')}

### ĐB · mức ý nghĩa 30 ngày
{_significance(DATA/'significance'/'number_significance_de_30d.csv')}

### ĐB · mức ý nghĩa 90 ngày
{_significance(DATA/'significance'/'number_significance_de_90d.csv')}

### Phòng chiến lược · Lô tô ngoài mẫu
{_strategy(DATA/'research'/'strategy_lab_loto.csv')}

### Phòng chiến lược · ĐB ngoài mẫu
{_strategy(DATA/'research'/'strategy_lab_de.csv')}

### Chẩn đoán
{_diagnostics()}

---

## 🔎 Kiểm toán và liên kết chi tiết

| Tài nguyên | Mục đích | Ý nghĩa |
| --- | --- | --- |
| [`data/xsmb.csv`](data/xsmb.csv) | Dữ liệu chuẩn | Dữ liệu kết quả chuẩn |
| [`data/source_audit.json`](data/source_audit.json) | Đồng thuận nguồn | Kiểm tra nguồn xác minh |
| [Thống kê HTML](docs/statistics.html) | Tương tác | Bảng điều khiển thống kê có tương tác |
| [AI/ML HTML](docs/dashboard.html) | Tương tác | Bảng điều khiển AI/ML |
| [Phòng nghiên cứu](docs/research-lab.html) | Nghiên cứu | Bác bỏ giả thuyết / ngoài mẫu / FDR |
| [Kết quả gần thời gian thực](docs/live.html) | Trực tiếp | Trạng thái kết quả trực tiếp |

---

<div align="center">

### ✨ Phân tích VLA

**Một trang · số liệu trực tiếp · màu có giải thích · bảng cân đối · tự động làm mới**

<sub>Không dùng dữ liệu giả. Màu nhiệt và thanh trực quan chỉ biểu diễn tương đối trong từng bảng.</sub>

</div>
'''
    OUT.write_text(md,encoding="utf-8")
    print(f"Đã ghi {OUT} ({OUT.stat().st_size:,} byte)")


if __name__ == "__main__":
    main()
