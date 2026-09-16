from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from page_output import write_page
from ui_locale import column_label, localize_mapping_for_display
from ui_theme import (
    ALIGN_LEFT,
    ALIGN_RIGHT,
    app_shell_close,
    app_shell_open,
    card,
    dataframe_table,
    definition_table,
    page_header,
    raw_details,
    stylesheet_link,
    write_stylesheet,
)
from web_security import security_meta_tags

logger = logging.getLogger(__name__)

_COMMAND_CENTER_CSS = r"""
.ai-command-center{min-height:100vh;background:linear-gradient(135deg,#F4F5FF 0%,#EAEBFF 48%,#E8ECFF 100%)}
.ai-command-center .ui-shell{max-width:1280px}
.ai-command-center .ui-header{position:relative;overflow:hidden;padding:clamp(1.35rem,3vw,2.2rem);border:1px solid rgba(255,255,255,.96);border-radius:24px;background:rgba(255,255,255,.9);box-shadow:0 12px 36px rgba(15,23,42,.06);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}
.ai-command-center .ui-header::after{content:"AI";position:absolute;right:1rem;top:-1.5rem;font-size:7rem;font-weight:900;letter-spacing:-.08em;color:rgba(79,70,229,.07);pointer-events:none}
.ai-status-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.8rem;margin:1rem 0 1.25rem}
.ai-status-item{position:relative;overflow:hidden;min-width:0;padding:1rem 1.05rem;border:1px solid rgba(255,255,255,.96);border-radius:18px;background:rgba(255,255,255,.9);box-shadow:0 10px 30px rgba(15,23,42,.045);backdrop-filter:blur(14px)}
.ai-status-item::after{content:"";position:absolute;left:1rem;right:1rem;bottom:.65rem;height:3px;border-radius:999px;background:linear-gradient(90deg,#4f46e5 0 32%,#818cf8 32% 63%,#c7d2fe 63% 100%);opacity:.78}
.ai-status-item span{display:block;font-size:.66rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#64748b}.ai-status-item strong{display:block;margin-top:.25rem;padding-bottom:.55rem;font-size:.92rem;color:#0f172a}
.ai-signal-grid{align-items:start}.ai-signal-grid>.ui-card{border-color:rgba(255,255,255,.96);background:rgba(255,255,255,.92);box-shadow:0 10px 32px rgba(15,23,42,.05);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.ai-signal-grid>.ui-card:nth-child(-n+2){position:relative;overflow:hidden;border-color:#c7d2fe;box-shadow:0 16px 40px rgba(79,70,229,.09)}
.ai-signal-grid>.ui-card:nth-child(-n+2)::before{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:linear-gradient(180deg,#4f46e5,#818cf8)}
.ai-signal-grid>.ui-card .ui-card-head h2{letter-spacing:-.02em}.ai-command-center .ui-table{font-variant-numeric:tabular-nums}.ai-command-center .ui-table th{background:#f8fafc}
@media(max-width:760px){.ai-status-strip{grid-template-columns:1fr}.ai-command-center .ui-header::after{font-size:4.5rem}}
"""


def _read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _latest_date(data_dir: Path) -> str:
    """Return latest draw date from known repository data files."""
    for cand in [
        data_dir / "xsmb.parquet",
        data_dir / "xsmb.csv",
        data_dir / "rawdata.parquet",
        data_dir / "raw.parquet",
        data_dir / "results.parquet",
    ]:
        if not cand.exists():
            continue
        try:
            if cand.suffix == ".csv":
                df = pd.read_csv(cand, usecols=["date"])
            else:
                df = pd.read_parquet(cand, columns=["date"])
            if df.empty:
                continue
            return pd.to_datetime(df["date"]).max().date().isoformat()
        except Exception as exc:
            logger.warning("Không thể đọc ngày mới nhất từ %s: %s", cand, exc)
            continue
    return ""


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Dựng bảng điều khiển và trang chất lượng mô hình.")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args(argv)

    root = Path(".")
    data_dir = root / "data"
    docs_dir = Path(args.docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    write_stylesheet(docs_dir)

    latest = _latest_date(data_dir)
    gen = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    picks_loto = _read_json(data_dir / "predict" / "picks_loto.json")
    picks_de = _read_json(data_dir / "predict" / "picks_de.json")
    w_loto = _read_json(data_dir / "ensemble" / "weights_loto.json")
    w_de = _read_json(data_dir / "ensemble" / "weights_de.json")
    c_loto = _read_json(data_dir / "ensemble" / "calibration_loto.json")
    c_de = _read_json(data_dir / "ensemble" / "calibration_de.json")

    if not w_loto:
        w_loto = {"weights": {"w_ml": 0.4, "w_active": 0.3, "w_stable": 0.3}, "note": "Chưa học được trọng số vì chưa đủ ngày có nhãn"}
    if not w_de:
        w_de = {"weights": {"w_ml": 0.4, "w_active": 0.3, "w_stable": 0.3}, "note": "Chưa học được trọng số vì chưa đủ ngày có nhãn"}
    if not c_loto:
        c_loto = {"note": "Chưa học được phép hiệu chỉnh"}
    if not c_de:
        c_de = {"note": "Chưa học được phép hiệu chỉnh"}
    if not picks_loto:
        picks_loto = {"note": "Chưa tạo danh sách gợi ý; hãy chạy quy trình predict_nextday_2d.py"}
    if not picks_de:
        picks_de = {"note": "Chưa tạo danh sách gợi ý; hãy chạy quy trình predict_nextday_2d.py"}

    def load_pred(mode: str) -> pd.DataFrame:
        files = sorted((data_dir / "predict").glob(f"predict_next_{mode}_all_*.csv"))
        if not files:
            return pd.DataFrame()
        try:
            return pd.read_csv(files[-1]).sort_values("prob", ascending=False).head(20)
        except Exception:
            return pd.DataFrame()

    pred_loto = load_pred("loto")
    pred_de = load_pred("de")

    def df_to_html(df: pd.DataFrame) -> str:
        if df.empty:
            return '<p class="ui-table-empty">Chưa có dữ liệu. Tệp đầy đủ nằm trong <code>data/predict/</code>.</p>'
        cols = [c for c in df.columns if c in ("number", "prob")]
        if not cols:
            cols = df.columns.tolist()[:2]
        df2 = df[cols].copy()
        if "prob" in df2.columns:
            df2["prob"] = df2["prob"].astype(float).map(lambda x: f"{x:.6f}")
        df2 = df2.rename(columns=column_label)
        df2.insert(0, "#", range(1, len(df2) + 1))
        align = [ALIGN_RIGHT, ALIGN_LEFT] + [ALIGN_RIGHT] * (len(df2.columns) - 2)
        return dataframe_table(df2, align=align, key_column=1)

    def rendered(payload: dict) -> str:
        return definition_table(localize_mapping_for_display(payload)) + raw_details(payload)

    cards = "".join([
        card(df_to_html(pred_loto), title="Xác suất LOTO cao nhất", span=6, flush=True, lift=True),
        card(df_to_html(pred_de), title="Xác suất Đặc Biệt cao nhất", span=6, flush=True, lift=True),
        card(rendered(picks_loto), title="Danh sách gợi ý (LOTO)", span=6),
        card(rendered(picks_de), title="Danh sách gợi ý (Đặc Biệt)", span=6),
        card(rendered(w_loto) + '<h3 class="mt-4">Hiệu chỉnh (LOTO)</h3>' + rendered(c_loto), title="Trọng số (LOTO)", span=6),
        card(rendered(w_de) + '<h3 class="mt-4">Hiệu chỉnh (Đặc Biệt)</h3>' + rendered(c_de), title="Trọng số (Đặc Biệt)", span=6),
    ])

    status_strip = (
        '<section class="ai-status-strip" aria-label="Cấu trúc bảng điều khiển AI/ML">'
        '<div class="ai-status-item"><span>Không gian</span><strong>AI/ML Command Center</strong></div>'
        '<div class="ai-status-item"><span>Tín hiệu</span><strong>Xác suất · Gợi ý · Xếp hạng</strong></div>'
        '<div class="ai-status-item"><span>Kiểm soát</span><strong>Trọng số · Hiệu chỉnh · Chất lượng</strong></div>'
        '</section>'
    )

    dashboard_html = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {stylesheet_link()}
  <style id="ai-command-center-source">{_COMMAND_CENTER_CSS}</style>
  <title>Bảng điều khiển phân tích XSMB</title>
</head>
<body class="ai-command-center">
{app_shell_open("dashboard.html")}
{page_header("Bảng điều khiển phân tích XSMB", "Xác suất mô hình tổ hợp, trọng số đã học và danh sách gợi ý cho kỳ kế tiếp.", [f"Ngày dữ liệu mới nhất: {latest}", f"Tạo lúc: {gen}"])}
{status_strip}
<div class="ui-grid ai-signal-grid">{cards}</div>
{app_shell_close("dashboard.html")}
</body>
</html>
"""
    write_page(docs_dir / "dashboard.html", dashboard_html)
    print("Wrote:", docs_dir / "dashboard.html")


if __name__ == "__main__":
    main()
