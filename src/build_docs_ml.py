from __future__ import annotations

from pathlib import Path

import pandas as pd


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

    gen_date = ""
    if "predict_for_date" in df.columns and len(df):
        gen_date = str(df["predict_for_date"].iloc[0])

    return f"""
    <h2>{title}</h2>
    <div class="meta">Predict for: <code>{gen_date}</code></div>
    {view.to_html(index=False, escape=True, classes="tbl")}
    """


def _base_page(body: str, page_title: str) -> str:
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
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
<body>
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
          <a class="pill" href="index.html">Dashboard</a>
          <a class="pill" href="ml_top10_de.html">Đề Top10</a>
          <a class="pill" href="soi-path-loto-active.html">Soi Path Lô (Active)</a>
          <a class="pill" href="soi-path-de-active.html">Soi Path Đề (Active)</a>
        </div>
        {_df_to_html_table(loto_top, "ML Prediction — LÔ Top 10 (00–99)")}
        <div class="hint">Sau 18:35 (VN), workflow sẽ cập nhật dự báo cho ngày hôm sau.</div>
        """,
        page_title="ML — Lô Top 10",
    )
    (DOCS_DIR / "ml_top10_loto.html").write_text(loto_page, encoding="utf-8")

    de_page = _base_page(
        body=f"""
        <div class="topbar">
          <a class="pill" href="index.html">Dashboard</a>
          <a class="pill" href="ml_top10_loto.html">Lô Top10</a>
          <a class="pill" href="soi-path-loto-active.html">Soi Path Lô (Active)</a>
          <a class="pill" href="soi-path-de-active.html">Soi Path Đề (Active)</a>
        </div>
        {_df_to_html_table(de_top, "ML Prediction — ĐỀ Top 10 (2 số cuối ĐB)")}
        <div class="hint">Đề: model chuẩn hoá xác suất về phân phối 00–99 (sum≈1).</div>
        """,
        page_title="ML — Đề Top 10",
    )
    (DOCS_DIR / "ml_top10_de.html").write_text(de_page, encoding="utf-8")

    loto_html = _df_to_html_table(loto_top, "LÔ Top 10")
    de_html = _df_to_html_table(de_top, "ĐỀ Top 10")

    index_body = f"""
    <div class="topbar">
      <span class="pill" style="border:none; font-weight:700;">Lottery Insights Dashboard</span>
      <a class="pill" href="ml_top10_loto.html">Lô Top10 (page)</a>
      <a class="pill" href="ml_top10_de.html">Đề Top10 (page)</a>
      <a class="pill" href="soi-path-loto-active.html">Soi Path Lô (Active)</a>
      <a class="pill" href="soi-path-loto-stable.html">Soi Path Lô (Stable)</a>
      <a class="pill" href="soi-path-de-active.html">Soi Path Đề (Active)</a>
      <a class="pill" href="soi-path-de-stable.html">Soi Path Đề (Stable)</a>
    </div>

    <div class="tabs">
      <button class="tabbtn active" data-tab="loto">LÔ (00–99)</button>
      <button class="tabbtn" data-tab="de">ĐỀ (2 số cuối ĐB)</button>
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
      Dashboard lấy dữ liệu từ <code>data/ml/predict_next_*_ml_top10.csv</code>.
      Nếu chưa thấy số mới: chạy GitHub Actions sau 18:35 (VN).
    </div>
    """

    (DOCS_DIR / "index.html").write_text(_base_page(index_body, "Lottery Dashboard"), encoding="utf-8")


if __name__ == "__main__":
    build()
