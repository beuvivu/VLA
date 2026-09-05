from __future__ import annotations

import html
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ui_locale import column_label, localize_mapping_for_display, mode_label
from ui_theme import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    card,
    dataframe_table,
    nav_links,
    page_header,
    shell_close,
    shell_open,
    tailwind_style_tag,
)
from web_security import security_meta_tags

logger = logging.getLogger(__name__)

# Liên kết điều hướng dùng chung cho hai trang do builder này sinh ra.
NAV: tuple[tuple[str, str], ...] = (
    ("index.html", "Trang chính"),
    ("dashboard.html", "Bảng điều khiển AI/ML"),
    ("statistics.html", "Ma trận thống kê"),
    ("model-quality.html", "Chất lượng mô hình"),
    ("live.html", "Kết quả trực tiếp"),
)


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


def main() -> None:
    root = Path(".")
    data_dir = root / "data"
    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

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
        picks_loto = {
            "note": "Chưa tạo danh sách gợi ý; hãy chạy quy trình predict_nextday_2d.py"
        }
    if not picks_de:
        picks_de = {
            "note": "Chưa tạo danh sách gợi ý; hãy chạy quy trình predict_nextday_2d.py"
        }

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
                '<p class="vla-table-empty">Chưa có dữ liệu. '
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

    def display_json(payload: dict) -> str:
        localized = localize_mapping_for_display(payload)
        return html.escape(json.dumps(localized, ensure_ascii=False, indent=2))

    # Mỗi hàng ghép đúng một cặp lô tô | Đặc Biệt (6/12 mỗi card). Hai card cùng
    # hàng luôn cùng dạng nội dung nên cao bằng nhau, không sinh khoảng trống
    # dưới đáy card thấp hơn như khi xếp lẫn bảng với khối JSON.
    cards = "".join(
        [
            card(
                df_to_html(pred_loto),
                title="Xác suất lô tô cao nhất",
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
                f'<pre class="vla-pre">{display_json(picks_loto)}</pre>',
                title="Danh sách gợi ý (lô tô)",
                span=6,
            ),
            card(
                f'<pre class="vla-pre">{display_json(picks_de)}</pre>',
                title="Danh sách gợi ý (Đặc Biệt / ĐB)",
                span=6,
            ),
            card(
                f'<pre class="vla-pre">{display_json(w_loto)}</pre>'
                '<h3 class="mt-4">Hiệu chỉnh (lô tô)</h3>'
                f'<pre class="vla-pre">{display_json(c_loto)}</pre>',
                title="Trọng số (lô tô)",
                span=6,
            ),
            card(
                f'<pre class="vla-pre">{display_json(w_de)}</pre>'
                '<h3 class="mt-4">Hiệu chỉnh (Đặc Biệt)</h3>'
                f'<pre class="vla-pre">{display_json(c_de)}</pre>',
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
  {tailwind_style_tag()}
  <title>Bảng điều khiển phân tích XSMB</title>
</head>
<body>
{shell_open()}
{page_header(
    "Bảng điều khiển phân tích XSMB",
    "Xác suất mô hình tổ hợp, trọng số đã học và danh sách gợi ý cho kỳ kế tiếp.",
    [f"Ngày dữ liệu mới nhất: {latest}", f"Tạo lúc: {gen}"],
)}
{nav_links(NAV, current="dashboard.html")}
<div class="vla-grid">{cards}</div>
{shell_close()}
</body>
</html>
"""
    (docs_dir / "dashboard.html").write_text(dashboard_html, encoding="utf-8")
    print("Wrote:", docs_dir / "dashboard.html")

    # GitHub Pages publishes only docs/. Keep model-quality data self-contained
    # instead of fetching ../data at runtime (which is unavailable with /docs
    # branch publishing).
    quality_path = data_dir / "prob_eval" / "ensemble_history.csv"
    try:
        quality = pd.read_csv(quality_path) if quality_path.exists() else pd.DataFrame()
    except Exception:
        quality = pd.DataFrame()

    # Loại canh trái, ngày canh giữa, hai chỉ số lỗi canh phải.
    quality_align = [ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT, ALIGN_RIGHT]

    if quality.empty:
        quality_body = (
            '<p class="vla-table-empty">Chưa có đủ lịch sử đánh giá mô hình.</p>'
        )
        latest_quality = ""
    else:
        q = quality.copy()
        q["target_date"] = q["target_date"].astype(str)
        q["logloss"] = pd.to_numeric(q["logloss"], errors="coerce")
        q["brier"] = pd.to_numeric(q["brier"], errors="coerce")
        q = q.sort_values(["mode", "target_date"])
        latest_rows = q.groupby("mode", as_index=False).tail(1).copy()
        latest_rows["logloss"] = latest_rows["logloss"].map(lambda x: f"{x:.6f}" if pd.notna(x) else "")
        latest_rows["brier"] = latest_rows["brier"].map(lambda x: f"{x:.6f}" if pd.notna(x) else "")
        latest_rows["mode"] = latest_rows["mode"].map(mode_label)
        latest_quality = dataframe_table(
            latest_rows[["mode", "target_date", "logloss", "brier"]].rename(
                columns=column_label
            ),
            align=quality_align,
            key_column=0,
        )

        recent = q.groupby("mode", group_keys=False).tail(30).copy()
        recent["logloss"] = recent["logloss"].map(lambda x: f"{x:.6f}" if pd.notna(x) else "")
        recent["brier"] = recent["brier"].map(lambda x: f"{x:.6f}" if pd.notna(x) else "")
        recent["mode"] = recent["mode"].map(mode_label)
        quality_body = dataframe_table(
            recent[["mode", "target_date", "logloss", "brier"]].rename(
                columns=column_label
            ),
            align=quality_align,
            key_column=0,
        )

    quality_html = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {tailwind_style_tag()}
  <title>Chất lượng mô hình — Phân tích XSMB</title>
</head>
<body>
{shell_open()}
{page_header(
    "Chất lượng mô hình",
    "Đánh giá cuốn chiếu ngoài mẫu của mô hình tổ hợp. LogLoss/Brier càng thấp "
    "càng tốt; đây là thước đo xác suất, không phải cam kết kết quả.",
)}
{nav_links(NAV, current="model-quality.html")}
<div class="vla-grid">
{card(
    latest_quality or '<p class="vla-table-empty">Chưa có dữ liệu.</p>',
    title="Mới nhất",
    span=12,
    flush=True,
)}
{card(
    quality_body,
    title="30 đánh giá gần nhất theo loại",
    span=12,
    flush=True,
    lift=True,
)}
</div>
{shell_close()}
</body>
</html>
"""
    (docs_dir / "model-quality.html").write_text(quality_html, encoding="utf-8")
    print("Wrote:", docs_dir / "model-quality.html")


if __name__ == "__main__":
    main()
