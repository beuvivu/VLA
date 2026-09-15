from __future__ import annotations

import argparse

import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ui_locale import column_label, localize_mapping_for_display, mode_label
from ui_theme import (
    ALIGN_CENTER,
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
from page_output import write_page

logger = logging.getLogger(__name__)


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
    """Điểm vào dòng lệnh.

    Args:
        argv: Tham số dòng lệnh.

    ``--docs-dir`` để test dựng được vào thư mục tạm thay vì ghi đè docs/ của
    kho thật. Cùng tên tham số với build_stat_pages.py.
    """
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
        w_loto = {
            "weights": {"w_ml": 0.4, "w_active": 0.3, "w_stable": 0.3},
            "note": "Chưa học được trọng số vì chưa đủ ngày có nhãn",
        }
    if not w_de:
        w_de = {
            "weights": {"w_ml": 0.4, "w_active": 0.3, "w_stable": 0.3},
            "note": "Chưa học được trọng số vì chưa đủ ngày có nhãn",
        }
    if not c_loto:
        c_loto = {"note": "Chưa học được phép hiệu chỉnh"}
    if not c_de:
        c_de = {"note": "Chưa học được phép hiệu chỉnh"}
    if not picks_loto:
        picks_loto = {"note": "Chưa tạo danh sách gợi ý; hãy chạy quy trình predict_nextday_2d.py"}
    if not picks_de:
        picks_de = {"note": "Chưa tạo danh sách gợi ý; hãy chạy quy trình predict_nextday_2d.py"}

    def load_pred(mode: str) -> pd.DataFrame:
        pred_dir = data_dir / "predict"
        files = sorted(pred_dir.glob(f"predict_next_{mode}_all_*.csv"))
        if not files:
            return pd.DataFrame()
        try:
            df = pd.read_csv(files[-1])
            return df.sort_values("prob", ascending=False).head(20)
        except Exception:
            return pd.DataFrame()

    pred_loto = load_pred("loto")
    pred_de = load_pred("de")

    def df_to_html(df: pd.DataFrame) -> str:
        if df.empty:
            return (
                '<p class="ui-table-empty">Chưa có dữ liệu. '
                "Tệp đầy đủ nằm trong <code>data/predict/</code>.</p>"
            )
        cols = [c for c in df.columns if c in ("number", "prob")]
        if not cols:
            cols = df.columns.tolist()[:2]
        df2 = df[cols].copy()
        if "prob" in df2.columns:
            df2["prob"] = df2["prob"].astype(float).map(lambda x: f"{x:.6f}")
        df2 = df2.rename(columns=column_label)
        # Cột thứ hạng giúp bảng ba cột lấp đầy bề ngang thay vì để số và xác
        # suất dính hai mép; hạng canh phải, số là khóa, xác suất canh phải.
        df2.insert(0, "#", range(1, len(df2) + 1))
        align = [ALIGN_RIGHT, ALIGN_LEFT] + [ALIGN_RIGHT] * (len(df2.columns) - 2)
        return dataframe_table(df2, align=align, key_column=1)

    def rendered(payload: dict) -> str:
        """Bảng nhãn–giá trị, kèm JSON gốc gập lại phía dưới.

        Trước đây bốn card này đổ thẳng JSON ra thẻ <pre>. Khối đó đọc được với
        người viết ra nó và gần như vô nghĩa với người dùng trang — lại còn để
        lộ tên khóa chưa dịch (w_cau, effective_weights) nằm cạnh nhãn đã dịch.
        """
        return definition_table(localize_mapping_for_display(payload)) + raw_details(payload)

    # Mỗi hàng ghép đúng một cặp LOTO | Đặc Biệt (6/12 mỗi card). Hai card cùng
    # hàng luôn cùng dạng nội dung nên cao bằng nhau, không sinh khoảng trống
    # dưới đáy card thấp hơn như khi xếp lẫn bảng với khối JSON.
    cards = "".join(
        [
            card(
                df_to_html(pred_loto),
                title="Xác suất LOTO cao nhất",
                span=6,
                flush=True,
                lift=True,
            ),
            card(
                df_to_html(pred_de),
                title="Xác suất Đặc Biệt cao nhất",
                span=6,
                flush=True,
                lift=True,
            ),
            card(
                rendered(picks_loto),
                title="Danh sách gợi ý (LOTO)",
                span=6,
            ),
            card(
                rendered(picks_de),
                title="Danh sách gợi ý (Đặc Biệt / Đặc Biệt)",
                span=6,
            ),
            card(
                rendered(w_loto) + '<h3 class="mt-4">Hiệu chỉnh (LOTO)</h3>' + rendered(c_loto),
                title="Trọng số (LOTO)",
                span=6,
            ),
            card(
                rendered(w_de) + '<h3 class="mt-4">Hiệu chỉnh (Đặc Biệt)</h3>' + rendered(c_de),
                title="Trọng số (Đặc Biệt)",
                span=6,
            ),
        ]
    )

    dashboard_html = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {stylesheet_link()}
  <title>Bảng điều khiển phân tích XSMB</title>
</head>
<body>
{app_shell_open("dashboard.html")}
{
        page_header(
            "Bảng điều khiển phân tích XSMB",
            "Xác suất mô hình tổ hợp, trọng số đã học và danh sách gợi ý cho kỳ kế tiếp.",
            [f"Ngày dữ liệu mới nhất: {latest}", f"Tạo lúc: {gen}"],
        )
    }
<div class="ui-grid">{cards}</div>
{app_shell_close("dashboard.html")}
</body>
</html>
"""
    write_page((docs_dir / "dashboard.html"), dashboard_html)
    print("Wrote:", docs_dir / "dashboard.html")

    # Trang Chất lượng mô hình đã chuyển sang `build_model_quality.py`. Nó không
    # còn là hai bảng đọc thẳng từ một CSV nữa mà là báo cáo chẩn đoán dựng từ
    # `model_quality.report`, nên để lại đây sẽ thành hai nguồn sự thật cùng ghi
    # một tệp, và tệp cuối cùng phụ thuộc vào thứ tự chạy builder.


if __name__ == "__main__":
    main()
