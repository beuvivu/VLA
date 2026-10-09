from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo
import html
from pathlib import Path

from ensemble_utils import DEFAULT_ENSEMBLE_WEIGHTS, weights_provenance

import pandas as pd

from safe_io import read_csv_or_empty, read_json_or_empty

from page_output import write_page
from lab_ui import lab_footer, lab_guide, lab_hero, lab_jump, lab_styles
from dashboard_tables import (
    calibration_card, dashboard_group, dashboard_styles, forecast_card, picks_card, weights_card,
)
from ui_theme import (
    app_shell_close,
    app_shell_open,
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
    """Ánh xạ provenance chuẩn sang nhãn UI tương thích; không tự đọc hồ sơ."""
    payload = weights_provenance(data_dir, mode)
    if payload['xuat_xu'] == 'khong_co_ho_so':
        learned = payload['weights'] != DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
        payload["xuat_xu"] = "da_hoc_chua_co_cong" if learned else "mac_dinh_dat_tay"
        payload["nguon"] = "đã học (chưa có cổng đề bạt)" if learned else "mặc định đặt tay"
        if learned:
            payload.pop('ly_do', None)
        else:
            payload['ly_do'] = {'tep trong so thieu hoac sai luoc do':'tệp trọng số thiếu hoặc sai lược đồ',
                               'chua co tep trong so':'chưa có tệp trọng số'}.get(payload['ly_do'], payload['ly_do'])
    elif payload['xuat_xu'] == 'da_hoc':
        payload["nguon"] = "đã học và vượt cổng ngoài mẫu"
    else:
        payload["nguon"] = "mặc định, cổng từ chối đề bạt"
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

    cards = "".join([
        dashboard_group(1, "Bảng xếp hạng xác suất", "Hai kênh có ý nghĩa xác suất khác nhau; giữ nguyên thứ tự và độ chính xác công bố.",
                        forecast_card(pred_loto, "loto") + forecast_card(pred_de, "de")),
        dashboard_group(2, "Danh sách số theo kỳ", "Đọc trọn bộ Top 4, Top 8 và Top 10; dữ liệu kiểm chứng nằm trong hồ sơ mở rộng.",
                        picks_card(picks_loto, "loto") + picks_card(picks_de, "de")),
        dashboard_group(3, "Cấu trúc tổ hợp", "Đối chiếu trọng số có hiệu lực và xuất xứ của từng kênh.",
                        weights_card(w_loto, "loto") + weights_card(w_de, "de")),
        dashboard_group(4, "Hiệu chỉnh xác suất", "Tham số và cách lựa chọn được lưu cùng báo cáo; ô thiếu dữ liệu hiển thị dấu gạch ngang.",
                        calibration_card(c_loto, "loto") + calibration_card(c_de, "de")),
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
  {dashboard_styles()}
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
           ("app-lab-picks", "Danh sách gợi ý"), ("app-lab-weights", "Trọng số"),
           ("app-dash-calibration-loto", "Hiệu chỉnh")])}
{cards}
{lab_footer()}</div>
{app_shell_close("dashboard.html")}
</body>
</html>
"""
    write_page(docs_dir / "dashboard.html", dashboard_html)
    print("Wrote:", docs_dir / "dashboard.html")


if __name__ == "__main__":
    main()
