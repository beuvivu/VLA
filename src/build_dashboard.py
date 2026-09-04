from __future__ import annotations

import html
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ui_locale import column_label, localize_mapping_for_display, mode_label
from ui_theme import tailwind_style_tag
from web_security import security_meta_tags

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
                "<p><em>Chưa có dữ liệu.</em></p>"
                "<p class='muted'>Tệp đầy đủ nằm trong <code>data/predict/</code>.</p>"
            )
        cols = [c for c in df.columns if c in ("number", "prob")]
        if not cols:
            cols = df.columns.tolist()[:2]
        df2 = df[cols].copy()
        if "prob" in df2.columns:
            df2["prob"] = df2["prob"].astype(float).map(lambda x: f"{x:.6f}")
        df2 = df2.rename(columns=column_label)
        return df2.to_html(index=False, escape=True)

    def display_json(payload: dict) -> str:
        localized = localize_mapping_for_display(payload)
        return html.escape(json.dumps(localized, ensure_ascii=False, indent=2))

    dashboard_html = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {tailwind_style_tag()}
  <title>Bảng điều khiển phân tích XSMB</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }}
    h1,h2,h3 {{ margin: 0.6em 0 0.4em; }}
    .meta {{ color: #555; margin-bottom: 18px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .card {{ border: 1px solid #ddd; border-radius: 12px; padding: 14px 16px; }}
    pre {{ background: #f7f7f7; padding: 10px; border-radius: 10px; overflow:auto; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #eee; padding: 6px 8px; text-align: left; font-size: 13px; }}
    .muted {{ color: #666; font-size: 13px; }}
    a {{ color: #0b57d0; text-decoration: none; }}
  </style>
</head>
<body class="bg-slate-50 text-slate-800">
  <h1>Bảng điều khiển phân tích XSMB</h1>
  <div class="meta">Ngày dữ liệu mới nhất: <b>{latest}</b> &nbsp;|&nbsp; Tạo lúc: {gen}</div>

  <div class="grid">
    <div class="card">
      <h2>Danh sách gợi ý (lô tô)</h2>
      <pre>{display_json(picks_loto)}</pre>
    </div>
    <div class="card bg-white border border-slate-200/60 rounded-xl shadow-sm transition-all duration-200 ease-in-out hover:shadow-lg hover:-translate-y-0.5">
      <h2>Danh sách gợi ý (Đặc Biệt / ĐB)</h2>
      <pre>{display_json(picks_de)}</pre>
    </div>

    <div class="card">
      <h2>Trọng số (lô tô)</h2>
      <pre>{display_json(w_loto)}</pre>
      <h3>Hiệu chỉnh (lô tô)</h3>
      <pre>{display_json(c_loto)}</pre>
    </div>
    <div class="card bg-white border border-slate-200/60 rounded-xl shadow-sm transition-all duration-200 ease-in-out hover:shadow-lg hover:-translate-y-0.5">
      <h2>Trọng số (Đặc Biệt)</h2>
      <pre>{display_json(w_de)}</pre>
      <h3>Hiệu chỉnh (Đặc Biệt)</h3>
      <pre>{display_json(c_de)}</pre>
    </div>

    <div class="card">
      <h2>Các xác suất lô tô cao nhất — xem trước</h2>
      {df_to_html(pred_loto)}
    </div>
    <div class="card bg-white border border-slate-200/60 rounded-xl shadow-sm transition-all duration-200 ease-in-out hover:shadow-lg hover:-translate-y-0.5">
      <h2>Các xác suất Đặc Biệt cao nhất — xem trước</h2>
      {df_to_html(pred_de)}
    </div>
  </div>

  <p class="muted" style="margin-top:16px;">
    Trang: <a href="index.html">Mục lục tài liệu</a> · <a href="statistics.html">Ma trận thống kê</a> · <a href="model-quality.html">Chất lượng mô hình</a>
  </p>
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

    if quality.empty:
        quality_body = "<p><em>Chưa có đủ lịch sử đánh giá mô hình.</em></p>"
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
        latest_quality = latest_rows[["mode", "target_date", "logloss", "brier"]].rename(
            columns=column_label
        ).to_html(index=False, escape=True)

        recent = q.groupby("mode", group_keys=False).tail(30).copy()
        recent["logloss"] = recent["logloss"].map(lambda x: f"{x:.6f}" if pd.notna(x) else "")
        recent["brier"] = recent["brier"].map(lambda x: f"{x:.6f}" if pd.notna(x) else "")
        recent["mode"] = recent["mode"].map(mode_label)
        quality_body = recent[["mode", "target_date", "logloss", "brier"]].rename(
            columns=column_label
        ).to_html(index=False, escape=True)

    quality_html = f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  {security_meta_tags()}
  {tailwind_style_tag()}
  <title>Chất lượng mô hình — Phân tích XSMB</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin:24px; color:#111; }}
    .card {{ border:1px solid #ddd; border-radius:12px; padding:16px; margin:14px 0; }}
    table {{ border-collapse:collapse; width:100%; }}
    th,td {{ border-bottom:1px solid #eee; padding:8px; text-align:left; font-size:13px; }}
    th {{ background:#fafafa; }}
    .muted {{ color:#666; font-size:13px; }}
    a {{ color:#0b57d0; text-decoration:none; }}
  </style>
</head>
<body>
  <h1>Chất lượng mô hình</h1>
  <p class="muted">Đánh giá cuốn chiếu ngoài mẫu của mô hình tổ hợp. LogLoss/Brier càng thấp càng tốt; đây là thước đo xác suất, không phải cam kết kết quả.</p>
  <p><a href="index.html">Trang chính</a> · <a href="dashboard.html">Bảng điều khiển AI/ML</a> · <a href="statistics.html">Thống kê</a></p>
  <div class="card"><h2>Mới nhất</h2>{latest_quality or '<p>Chưa có dữ liệu.</p>'}</div>
  <div class="card"><h2>30 đánh giá gần nhất theo loại</h2>{quality_body}</div>
</body>
</html>
"""
    (docs_dir / "model-quality.html").write_text(quality_html, encoding="utf-8")
    print("Wrote:", docs_dir / "model-quality.html")


if __name__ == "__main__":
    main()
