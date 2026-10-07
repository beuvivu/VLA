from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo
import html
from pathlib import Path

from ensemble_utils import DEFAULT_ENSEMBLE_WEIGHTS, load_ensemble_weights

import pandas as pd

from safe_io import read_csv_or_empty, read_json_or_empty
from lottery_codes import lottery_code

from page_output import write_page
from lab_ui import lab_card as card, lab_footer, lab_guide, lab_hero, lab_jump, lab_styles
from ui_locale import column_label, localize_mapping_for_display
from ui_theme import (
    ALIGN_LEFT,
    ALIGN_RIGHT,
    app_shell_close,
    app_shell_open,
    dataframe_table,
    definition_table,
    raw_details,
    write_stylesheet,
)
from css_links import stylesheet_link
from web_security import security_meta_tags

logger = logging.getLogger(__name__)

def _read_json(p: Path) -> dict:
    return read_json_or_empty(p)


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
            logger.warning("Không thể đọc ngày mới nhất từ %s: %s", cand, exp)
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

    # ``xuat_xu`` là MÃ, ``nguon`` là câu chữ cho người đọc. Hai thứ tách nhau
    # vì câu chữ là chuyện trình bày: đổi cách viết — kể cả chỉ thêm lại dấu
    # tiếng Việt — không được làm sai một phép kiểm nào. Dò chuỗi trong
    # ``nguon`` chính là ghim mặt chữ, và nó đã từng đỏ đúng vì lý do đó.
    if not isinstance(promotion, dict):
        learned = effective.as_dict() != DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
        payload["xuat_xu"] = "da_hoc_chua_co_cong" if learned else "mac_dinh_dat_tay"
        payload["nguon"] = "đã học (chưa có cổng đề bạt)" if learned else "mặc định đặt tay"
        if not learned:
            payload["ly_do"] = (
                "tệp trọng số thiếu hoặc sai lược đồ" if stored else "chưa có tệp trọng số"
            )
            return payload
    elif promotion.get("promoted"):
        payload["xuat_xu"] = "da_hoc"
        payload["nguon"] = "đã học và vượt cổng ngoài mẫu"
    else:
        payload["xuat_xu"] = "bi_tu_choi"
        payload["nguon"] = "mặc định, cổng từ chối đề bạt"
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
    parser = argparse.ArgumentParser(description="Dựng bảng điều khiển và trang chất lượng mô hình.")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args(argv)

    root = Path(".")
    data_dir = root / "data"
    docs_dir = Path(args.docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    write_stylesheet(docs_dir)

    latest = _latest_date(data_dir)
    gen = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%d/%m/%Y %H:%M UTC+7")

    picks_loto = _read_json(data_dir / "predict" / "picks_loto.json")
    picks_de = _read_json(data_dir / "predict" / "picks_de.json")
    w_loto = _effective_weights(data_dir, "loto")
    w_de = _effective_weights(data_dir, "de")
    c_loto = _read_json(data_dir / "ensemble" / "calibration_loto.json")
    c_de = _read_json(data_dir / "ensemble" / "calibration_de.json")

    if not c_loto:
        c_loto = {"note": "Chưa học được phép hiệu chỉnh"}
    if not c_de:
        c_de = {"note": "Chưa học được phép hiệu chỉnh"}
    if not picks_loto:
        picks_loto = {"note": "Chưa tạo danh sách gợi ý"}
    if not picks_de:
        picks_de = {"note": "Chưa tạo danh sách gợi ý"}

    def load_pred(mode: str) -> pd.DataFrame:
        files = sorted((data_dir / "predict").glob(f"predict_next_{mode}_all_*.csv"))
        if not files:
            return pd.DataFrame()
        frame = read_csv_or_empty(files[-1])
        if "prob" not in frame.columns:
            return pd.DataFrame()
        return frame.sort_values("prob", ascending=False).head(20)

    pred_loto = load_pred("loto")
    pred_de = load_pred("de")

    def df_to_html(df: pd.DataFrame) -> str:
        if df.empty:
            return '<p class="ui-table-empty">Chưa có dữ liệu.</p>'
        cols = [c for c in df.columns if c in ("number", "prob")]
        if not cols:
            cols = df.columns.tolist()[:2]
        df2 = df[cols].copy()
        if "number" in df2:
            df2["number"] = df2["number"].map(lottery_code)
        if "prob" in df2.columns:
            df2["prob"] = df2["prob"].astype(float).map(lambda x: f"{x:.6f}")
        df2 = df2.rename(columns=column_label)
        df2.insert(0, "#", range(1, len(df2) + 1))
        align = [ALIGN_RIGHT, ALIGN_LEFT] + [ALIGN_RIGHT] * (len(df2.columns) - 2)
        return dataframe_table(df2, align=align, key_column=1)

    def rendered(payload: dict) -> str:
        return definition_table(localize_mapping_for_display(payload)) + raw_details(payload)

    cards = "".join([
        card(df_to_html(pred_loto), title="Xác suất LOTO cao nhất", span=6, flush=True, lift=True, ident="app-lab-loto"),
        card(df_to_html(pred_de), title="Xác suất Đặc Biệt cao nhất", span=6, flush=True, lift=True, ident="app-lab-de"),
        card(rendered(picks_loto), title="Danh sách gợi ý (LOTO)", span=6, ident="app-lab-picks"),
        card(rendered(picks_de), title="Danh sách gợi ý (Đặc Biệt)", span=6),
        card(rendered(w_loto) + '<h3 class="mt-4">Hiệu chỉnh (LOTO)</h3>' + rendered(c_loto), title="Trọng số (LOTO)", span=6, ident="app-lab-weights"),
        card(rendered(w_de) + '<h3 class="mt-4">Hiệu chỉnh (Đặc Biệt)</h3>' + rendered(c_de), title="Trọng số (Đặc Biệt)", span=6),
    ])

    status_strip = f"""<section class="ai-status-strip" aria-label="Phạm vi bảng điều khiển">
<article class="app-lab-stat"><span>Dữ liệu kết quả</span><strong class="app-lab-status-value">{html.escape(latest or "Chưa có dữ liệu")}</strong><small>Mốc mới nhất trong lịch sử</small></article>
<article class="app-lab-stat"><span>Kênh LOTO</span><strong class="app-lab-status-value">{html.escape(w_loto['nguon'])}</strong><small>Xuất xứ trọng số tổ hợp</small></article>
<article class="app-lab-stat"><span>Kênh Đặc Biệt</span><strong class="app-lab-status-value">{html.escape(w_de['nguon'])}</strong><small>Xuất xứ trọng số tổ hợp</small></article>
</section>"""

    dashboard_html = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {stylesheet_link()}
  {lab_styles()}
  <title>Bảng điều khiển phân tích XSMB</title>
</head>
<body class="ai-command-center">
{app_shell_open("dashboard.html")}
<div class="app-lab app-lab-dashboard" data-lab-layout="dashboard">
{lab_hero("dashboard.html", "Trung tâm điều khiển AI/ML",
    "Theo dõi hai kênh dự báo trong cùng một không gian: xác suất tổ hợp, danh sách gợi ý, "
    "trọng số có hiệu lực và các bước hiệu chỉnh.",
    eyebrow="TRUNG TÂM PHÂN TÍCH MÔ HÌNH", core="TỔ HỢP", meta=f"Bản dựng: {gen}",
    action=("#app-lab-loto", "Mở bảng xác suất"))}
{status_strip}
{lab_guide([
    ("Hai kênh dự báo", "LOTO là xác suất một số xuất hiện ít nhất một lần. Đặc Biệt là phân phối hai chữ số cuối; hai kênh có mức nền khác nhau."),
    ("Trọng số có hiệu lực", "Trọng số đã học chỉ được áp dụng khi vượt cổng thẩm định. Đọc xuất xứ và lý do của từng kênh trong hồ sơ bên dưới."),
    ("Kiểm chứng từng giá trị", "Chọn một con số để xem nguồn và bước tính. Các khối dữ liệu gốc vẫn có thể mở để đối chiếu chi tiết."),
])}
{lab_jump([("app-lab-loto", "Xác suất LOTO"), ("app-lab-de", "Xác suất Đặc Biệt"),
           ("app-lab-picks", "Danh sách gợi ý"), ("app-lab-weights", "Trọng số & hiệu chỉnh")])}
<div class="ui-grid ai-signal-grid">{cards}</div>
{lab_footer()}</div>
{app_shell_close("dashboard.html")}
</body>
</html>
"""
    write_page(docs_dir / "dashboard.html", dashboard_html)
    print("Wrote:", docs_dir / "dashboard.html")


if __name__ == "__main__":
    main()
