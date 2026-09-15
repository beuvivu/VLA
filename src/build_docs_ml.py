from __future__ import annotations

from pathlib import Path

import pandas as pd

from ui_locale import column_label
from ui_theme import (
    ALIGN_LEFT,
    ALIGN_RIGHT,
    card,
    dataframe_table,
    app_shell_close,
    app_shell_open,
    nav_links,
    page_header,
    stylesheet_link,
    write_stylesheet,
)
from web_security import security_meta_tags
from page_output import write_page


DOCS_DIR = Path("docs")
ML_DIR = Path("data/ml")

NAV: tuple[tuple[str, str], ...] = (
    ("index.html", "Bảng điều khiển"),
    ("ml_top10_loto.html", "10 số LOTO"),
    ("ml_top10_de.html", "10 số Đặc Biệt"),
    ("soi-path-loto-active.html", "Cầu LOTO đang chạy"),
    ("soi-path-de-active.html", "Cầu Đặc Biệt đang chạy"),
    ("live.html", "Kết quả trực tiếp"),
)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _prediction_table(df: pd.DataFrame) -> tuple[str, str]:
    """Trả về (bảng đã canh cột, ngày dự báo)."""

    if df.empty:
        return (
            '<p class="ui-table-empty">Chưa có dữ liệu. '
            "Hãy chạy workflow (sync + ml_predict) trước.</p>",
            "",
        )

    cols = [c for c in ["predict_for_date", "number", "prob_percent", "prob"] if c in df.columns]
    view = df[cols].copy()

    if "prob_percent" in view.columns:
        view["prob_percent"] = view["prob_percent"].astype(float).map(lambda x: f"{x:.3f}%")
    if "prob" in view.columns:
        view["prob"] = view["prob"].astype(float).map(lambda x: f"{x:.6f}")

    gen_date = ""
    if "predict_for_date" in df.columns and len(df):
        gen_date = str(df["predict_for_date"].iloc[0])
        # Ngày lặp lại trên mọi dòng nên đưa lên tiêu đề thay vì chiếm một cột.
        view = view.drop(columns=["predict_for_date"])

    view = view.rename(columns=column_label)
    # Thêm thứ hạng để bảng hai/ba cột lấp đầy bề ngang thay vì dồn ra hai mép.
    view.insert(0, "#", range(1, len(view) + 1))
    align = [ALIGN_RIGHT, ALIGN_LEFT] + [ALIGN_RIGHT] * (len(view.columns) - 2)
    return dataframe_table(view, align=align, key_column=1), gen_date


def _date_badge(gen_date: str) -> str:
    if not gen_date:
        return ""
    return f'<span class="ui-badge ui-badge-brand">Dự báo cho {gen_date}</span>'


def _base_page(body: str, page_title: str, current: str = "") -> str:
    """Khung trang ML, dùng chung khung ứng dụng có dock như mọi trang khác.

    Trước đây hai trang ML mở bằng :func:`shell_open` trần, nên chúng là đích
    ĐẾN của dock mà bản thân lại không có dock: vào rồi thì lối ra duy nhất là
    nút Back hoặc dải ``nav_links`` ba mục ở đầu trang.

    Args:
        body: Phần thân trang.
        page_title: Tiêu đề cho thẻ ``<title>``.
        current: Tên tệp trang hiện tại, để dock đánh dấu mục đang xem.
    """
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  {security_meta_tags()}
  {stylesheet_link()}
  <title>{page_title}</title>
</head>
<body>
{app_shell_open(current)}
{body}
{app_shell_close(current)}
</body>
</html>"""


def build() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    loto_top = _read_csv(ML_DIR / "predict_next_loto_ml_top10.csv")
    de_top = _read_csv(ML_DIR / "predict_next_de_ml_top10.csv")

    loto_table, loto_date = _prediction_table(loto_top)
    de_table, de_date = _prediction_table(de_top)

    loto_page = _base_page(
        body=f"""
{
            page_header(
                "Dự báo ML — 10 số LOTO đứng đầu",
                "Xác suất mô hình học máy cho dải 00–99. Sau 18:35 (giờ Việt Nam) quy "
                "trình sẽ cập nhật dự báo cho ngày hôm sau.",
            )
        }
{nav_links(NAV, current="ml_top10_loto.html")}
<div class="ui-grid">
{
            card(
                loto_table,
                title="10 số LOTO đứng đầu (00–99)",
                aside=_date_badge(loto_date),
                span=12,
                flush=True,
                lift=True,
            )
        }
</div>
""",
        page_title="ML — 10 số LOTO đứng đầu",
        current="ml_top10_loto.html",
    )
    write_stylesheet(DOCS_DIR)
    write_page((DOCS_DIR / "ml_top10_loto.html"), loto_page)

    de_page = _base_page(
        body=f"""
{
            page_header(
                "Dự báo ML — 10 số Đặc Biệt đứng đầu",
                "Hai số cuối giải Đặc Biệt. Mô hình chuẩn hóa xác suất thành phân phối "
                "00–99 (tổng xấp xỉ 1).",
            )
        }
{nav_links(NAV, current="ml_top10_de.html")}
<div class="ui-grid">
{
            card(
                de_table,
                title="10 số Đặc Biệt đứng đầu (2 số cuối Đặc Biệt)",
                aside=_date_badge(de_date),
                span=12,
                flush=True,
                lift=True,
            )
        }
</div>
""",
        page_title="ML — 10 số Đặc Biệt đứng đầu",
        current="ml_top10_de.html",
    )
    write_page((DOCS_DIR / "ml_top10_de.html"), de_page)

    index_body = f"""
{
        page_header(
            "Bảng điều khiển phân tích xổ số",
            "Dữ liệu lấy từ data/ml/predict_next_*_ml_top10.csv. Nếu chưa thấy số "
            "mới, hãy chạy GitHub Actions sau 18:35 (giờ Việt Nam).",
        )
    }
{nav_links(NAV, current="index.html")}
<div class="ui-tabs">
  <button class="tabbtn active" data-tab="loto" type="button">LÔ (00–99)</button>
  <button class="tabbtn" data-tab="de" type="button">ĐẶC BIỆT (2 số cuối Đặc Biệt)</button>
</div>
<div id="panel-loto" class="panel active">
  <div class="ui-grid">
  {
        card(
            loto_table,
            title="10 số LOTO đứng đầu",
            aside=_date_badge(loto_date),
            span=12,
            flush=True,
        )
    }
  </div>
</div>
<div id="panel-de" class="panel">
  <div class="ui-grid">
  {
        card(
            de_table,
            title="10 số Đặc Biệt đứng đầu",
            aside=_date_badge(de_date),
            span=12,
            flush=True,
        )
    }
  </div>
</div>

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
"""

    write_page(DOCS_DIR / "index.html", _base_page(index_body, "Bảng điều khiển xổ số", "index.html"))


if __name__ == "__main__":
    build()
