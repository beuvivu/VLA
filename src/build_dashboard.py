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
            logger.warning("Không thể đọc ngày mới nhất từ %s: %s", cand, exp)
            continue
    return ""
