from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ensemble_utils import DEFAULT_ENSEMBLE_WEIGHTS, load_ensemble_weights

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
    write_stylesheet,
)
from css_links import stylesheet_link
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
        except Exception as exp:
            logger.warning("Khong the doc ngay moi nhat tu %s: %s", cand, exp)
            continue
    return ""


def _effective_weights(data_dir: Path, mode: str) -> dict:
    """Trọng số đang có hiệu lực, kèm lý do vì sao nó là nó.

    Ba xuất xứ, không phải hai. Bản trước suy xuất xứ bằng cách so với mặc
    định, nên kể từ khi bộ học có cổng đề bạt thì nó nói SAI: một tệp hợp lệ,
    lược đồ 7, mang đúng trọng số mặc định vì cổng đã TỪ CHỐI đề bạt lại bị
    báo là "tệp trọng số thiếu hoặc sai lược đồ". Xuất xứ phải đọc từ khối
    ``promotion`` chứ không suy từ giá trị.
    """
    effective = load_ensemble_weights(data_dir, mode)
    stored = _read_json(data_dir / "ensemble" / f"weights_{mode}.json")
    promotion = stored.get("promotion") if isinstance(stored, dict) else None
    payload: dict = {"mode": mode, "weights": effective.as_dict()}

    if not isinstance(promotion, dict):
        learned = effective.as_dict() != DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
        payload["nguon"] = "da hoc (chua co cong de bat)" if learned else "mac dinh dat tay"
        if not learned:
            payload["ly_do"] = (
                "tep trong so thieu hoac sai luoc do" if stored else "chua co tep trong so"
            )
            return payload
    elif promotion.get("promoted"):
        payload["nguon"] = "da hoc va vuot cong ngoai mau"
    else:
        payload["nguon"] = "mac dinh, cong tu choi de bat"
        payload["ly_do"] = str(promotion.get("reason", ""))

    for key in ("learned_at_utc", "window_days", "half_life_days", "metric"):
        if key in stored:
            payload[key] = stored[key]
    payload["days_used"] = len(stored.get("days_used", []))
    if isinstance(promotion, dict):
        payload["tham_dinh"] = {
            "so_ky_khop": promotion.get("train_days"),
            "so_ky_tham_dinh": promotion.get("validation_days"),
            "logloss_ngoai_mau": promotion.get("validation_logloss"),
            "loi_tuong_doi": promotion.get("relative_gain"),
        }
    return payload


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Dung bang dieu khien va trang chat luong mo hinh.")
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
    w_loto = _effective_weights(data_dir, "loto")
    w_de = _effective_weights(data_dir, "de")
    c_loto = _read_json(data_dir / "ensemble" / "calibration_loto.json")
    c_de = _read_json(data_dir / "ensemble" / "calibration_de.json")

    if not c_loto:
        c_loto = {"note": "Chua hoc duoc phep hieu chinh"}
    if not c_de:
        c_de = {"note": "Chua hoc duoc phep hieu chinh"}
    if not picks_loto:
        picks_loto = {"note": "Chua tao danh sach goi y"}
    if not picks_de:
        picks_de = {"note": "Chua tao danh sach goi y"}

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
            return '<p class="ui-table-empty">Chua co du lieu.</p>'
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
        card(df_to_html(pred_loto), title="Xac suat LOTO cao nhat", span=6, flush=True, lift=True),
        card(df_to_html(pred_de), title="Xac suat Dac Biet cao nhat", span=6, flush=True, lift=True),
        card(rendered(picks_loto), title="Danh sach goi y (LOTO)", span=6),
        card(rendered(picks_de), title="Danh sach goi y (Dac Biet)", span=6),
        card(rendered(w_loto) + '<h3 class="mt-4">Hieu chinh (LOTO)</h3>' + rendered(c_loto), title="Trong so (LOTO)", span=6),
        card(rendered(w_de) + '<h3 class="mt-4">Hieu chinh (Dac Biet)</h3>' + rendered(c_de), title="Trong so (Dac Biet)", span=6),
    ])

    status_strip = (
        '<section class="ai-status-strip" aria-label="AI/ML">'
        '<div class="ai-status-item"><span>Space</span><strong>AI/ML Command Center</strong></div>'
        '<div class="ai-status-item"><span>Signals</span><strong>Prob · Picks · Rank</strong></div>'
        '<div class="ai-status-item"><span>Control</span><strong>Weights · Calibration</strong></div>'
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
  <title>Bang dieu khien phan tich XSMB</title>
</head>
<body class="ai-command-center">
{app_shell_open("dashboard.html")}
{page_header("Bang dieu khien phan tich XSMB", "Xac suat mo hinh to hop, trong so da hoc va danh sach goi y.", [f"Ngay du lieu moi nhat: {latest}", f"Tao luc: {gen}"])}
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
