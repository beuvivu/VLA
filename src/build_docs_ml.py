from __future__ import annotations

from pathlib import Path

import pandas as pd

from ui_locale import column_label
from ui_theme import tailwind_style_tag
from web_security import security_meta_tags


DOCS_DIR = Path("docs")
ML_DIR = Path("data/ml")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _df_to_html_table(df: pd.DataFrame, title: str) -> str:
    if df.empty:
        return f"<h2>{title}</h2><p><b>Chưa có dữ liệu.</b> Hãy chạy workflow (sync + ml_predict) trước.</p>"

    cols = [c for c in ["predict_for_date", "number", "prob_percent", "prob"] if c in df.columns]
    view = df[cols].copy()

    if "prob_percent" in view.columns:
        view["prob_percent"] = view["prob_percent"].astype(float).map(lambda x: f"{x:.3f}%")
    if "prob" in view.columns:
        view["prob"] = view["prob"].astype(float).map(lambda x: f"{x:.6f}")
    view = view.rename(columns=column_label)

    gen_date = ""
    if "predict_for_date" in df.columns and len(df):
        gen_date = str(df["predict_for_date"].iloc[0])

    return f"""
    <h2>{title}</h2>
    <div class="meta">Dự báo cho ngày: <code>{gen_date}</code></div>
    {view.to_html(index=False, escape=True, classes="tbl")}
    """


def _base_page(body: str, page_title: str) -> str:
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  {security_meta_tags()}
  {tailwind_style_tag()}
  <title>{page_title}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; color:#111; }}
    .topbar {{ display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:16px; }}
    .pill {{ display:inline-block; padding:8px 12px; border:1px solid #ddd; border-radius:999px; text-decoration:none; color:#111; }}
    .pill:hover {{ background:#f6f6f6; }}
    .tbl {{ border-collapse: collapse; width: 100%; }}
    .tbl th, .tbl td {{ border: 1px solid #e5e5e5; padding: 10px; text-align: left; font-size:14px; }}
    .tbl th {{ background: #fafafa; }}
    .meta {{ color:#555; font-size:13px; margin: 6px 0 12px; }}
    .tabs {{ display:flex; gap:8px; margin: 12px 0 16px; }}
    .tabbtn {{ padding:10px 12px; border:1px solid #ddd; border-radius:10px; cursor:pointer; background:#fff; }}
    .tabbtn.active {{ background:#111; color:#fff; border-color:#111; }}
    .panel {{ display:none; }}
    .panel.active {{ display:block; }}
    .hint {{ color:#666; font-size:13px; margin-top:10px; }}
  </style>
</head>
<body class="bg-slate-50 text-slate-800">
{body}
</body>
</html>"""


def build() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    loto_top = _read_csv(ML_DIR / "predict_next_loto_ml_top10.csv")
    de_top = _read_csv(ML_DIR / "predict_next_de_ml_top10.csv")

    loto_page = _base_page(
        body=f"""
        <div class="topbar">
          <a class="pill" href="index.html">Bảng điều khiển</a>
          <a class="pill" href="ml_top10_de.html">10 số Đặc Biệt đứng đầu</a>
          <a class="pill" href="soi-path-loto-active.html">Soi cầu lô tô (đang chạy)</a>
          <a class="pill" href="soi-path-de-active.html">Soi cầu Đặc Biệt (đang chạy)</a>
        </div>
        {_df_to_html_table(loto_top, "Dự báo ML — 10 số lô tô đứng đầu (00–99)")}
        <div class="hint">Sau 18:35 (giờ Việt Nam), quy trình sẽ cập nhật dự báo cho ngày hôm sau.</div>
        """,
        page_title="ML — 10 số lô tô đứng đầu",
    )
    (DOCS_DIR / "ml_top10_loto.html").write_text(loto_page, encoding="utf-8")

    de_page = _base_page(
        body=f"""
        <div class="topbar">
          <a class="pill" href="index.html">Bảng điều khiển</a>
          <a class="pill" href="ml_top10_loto.html">10 số lô tô đứng đầu</a>
          <a class="pill" href="soi-path-loto-active.html">Soi cầu lô tô (đang chạy)</a>
          <a class="pill" href="soi-path-de-active.html">Soi cầu Đặc Biệt (đang chạy)</a>
        </div>
        {_df_to_html_table(de_top, "Dự báo ML — 10 số Đặc Biệt đứng đầu (2 số cuối ĐB)")}
        <div class="hint italic text-slate-600">Đặc Biệt: mô hình chuẩn hóa xác suất thành phân phối 00–99 (tổng xấp xỉ 1).</div>
        """,
        page_title="ML — 10 số Đặc Biệt đứng đầu",
    )
    (DOCS_DIR / "ml_top10_de.html").write_text(de_page, encoding="utf-8")

    loto_html = _df_to_html_table(loto_top, "10 số lô tô đứng đầu")
    de_html = _df_to_html_table(de_top, "10 số Đặc Biệt đứng đầu")

    index_body = f"""
    <div class="topbar">
      <span class="pill" style="border:none; font-weight:700;">Bảng điều khiển phân tích xổ số</span>
      <a class="pill" href="ml_top10_loto.html">Trang 10 số lô tô</a>
      <a class="pill" href="ml_top10_de.html">Trang 10 số Đặc Biệt</a>
      <a class="pill" href="soi-path-loto-active.html">Cầu lô tô đang chạy</a>
      <a class="pill" href="soi-path-loto-stable.html">Cầu lô tô ổn định</a>
      <a class="pill" href="soi-path-de-active.html">Cầu Đặc Biệt đang chạy</a>
      <a class="pill" href="soi-path-de-stable.html">Cầu Đặc Biệt ổn định</a>
    </div>

    <div class="tabs">
      <button class="tabbtn active" data-tab="loto">LÔ (00–99)</button>
      <button class="tabbtn" data-tab="de">ĐẶC BIỆT (2 số cuối ĐB)</button>
    </div>

    <div id="panel-loto" class="panel active">{loto_html}</div>
    <div id="panel-de" class="panel">{de_html}</div>

    <script>
      const btns = document.querySelectorAll('.tabbtn');
      const pL = document.getElementById('panel-loto');
      const pD = document.getElementById('panel-de');
      btns.forEach(b => b.addEventListener('click', () => {{
        btns.forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        const tab = b.dataset.tab;
        if (tab === 'loto') {{ pL.classList.add('active'); pD.classList.remove('active'); }}
        else {{ pD.classList.add('active'); pL.classList.remove('active'); }}
      }}));
    </script>

    <div class="hint">
      Bảng điều khiển lấy dữ liệu từ <code>data/ml/predict_next_*_ml_top10.csv</code>.
      Nếu chưa thấy số mới: chạy GitHub Actions sau 18:35 (VN).
    </div>
    """

    (DOCS_DIR / "index.html").write_text(
        _base_page(index_body, "Bảng điều khiển xổ số"), encoding="utf-8"
    )


if __name__ == "__main__":
    build()
