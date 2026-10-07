from __future__ import annotations

from pathlib import Path
import html

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
from lab_ui import lab_card, lab_footer, lab_guide, lab_hero, lab_styles
from evidence_catalog import ml_row_evidence, ml_summary_evidence, tag_rows, values_block


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
  {lab_styles() if current.startswith("ml_top10_") else ""}
  <title>{page_title}</title>
</head>
<body>
{app_shell_open(current)}
{body}
{app_shell_close(current)}
</body>
</html>"""


def _prediction_overview(frame: pd.DataFrame, date: str, mode: str) -> str:
    """Đọc mức tin đã lưu, không suy từ xác suất và không mặc định thiếu thành 0."""
    trust = pd.to_numeric(frame.get("model_trust", pd.Series(dtype=float)), errors="coerce")
    complete = len(frame) > 0 and len(trust) == len(frame) and trust.between(0, 1).all()
    if not complete:
        value = "—"
        note = "Chưa có đủ mức tin thành phần ML trong báo cáo này. Không suy mức tin từ xác suất dự báo."
    else:
        low, high = float(trust.min()), float(trust.max())
        value = f"{low:.1%}" if low == high else f"{low:.1%}–{high:.1%}"
        value = value.replace(".", ",")
        if high == 0:
            note = ("Mức tin thành phần ML bằng 0: xác suất được co hoàn toàn về xác suất nền. "
                    "Thứ hạng có thể dùng xác suất thô để phá hòa; thứ hạng ấy không chứng minh lợi thế dự báo.")
        else:
            note = ("Mức tin thành phần ML điều khiển phép co xác suất thô về mức nền. "
                    "Đây là trọng số của thành phần ML, không phải xác suất trúng hay Confidence Score.")
    evidence_id = f"ml-{mode}-summary"
    return f"""<section class="app-lab-summary" aria-label="Tóm tắt bản dự báo ML">
<article class="app-lab-stat"><span>Kỳ dự báo</span><strong class="app-lab-forecast-date">{html.escape(date or "—")}</strong><small>Ngày đích ghi trong bản dự báo</small></article>
<article class="app-lab-stat"><span>Danh sách công bố</span><strong>{len(frame)}</strong><small>Số ứng viên hiện có trong bảng</small></article>
<article class="app-lab-stat"><span>Mức tin thành phần ML</span><strong data-ml-trust data-evidence="{evidence_id}">{value}</strong><small>Trọng số co về xác suất nền</small></article>
</section><p class="app-lab-trust-note">{note}</p>"""


def _forecast_body(frame: pd.DataFrame, table: str, date: str,
                   rows: list, mode: str) -> str:
    """Dải số giữ nguyên thứ tự công bố; bảng giữ toàn bộ độ chính xác cũ."""
    name = "LOTO" if mode == "loto" else "Đặc Biệt"
    current = f"ml_top10_{mode}.html"
    subtitle = (
        "Quan sát thứ hạng của thành phần học máy trên dải 00–99. Xác suất biểu diễn khả năng "
        "một số xuất hiện ít nhất một lần trong kỳ dự báo."
        if mode == "loto" else
        "Theo dõi hai chữ số cuối giải Đặc Biệt qua thành phần học máy. "
        "Phân phối xác suất trên toàn bộ dải 00–99 được chuẩn hóa về tổng xấp xỉ một."
    )
    numbers = []
    if "number" in frame:
        for index, number in enumerate(frame["number"]):
            evidence = f' data-evidence="{html.escape(rows[index][0])}"' if index < len(rows) else ""
            numbers.append(f'<li{evidence}><b>{html.escape(str(number).zfill(2))}</b></li>')
    strip = ('<ol class="app-lab-number-strip" aria-label="Các số theo thứ tự công bố">'
             + ''.join(numbers) + '</ol>') if numbers else ''
    hero = lab_hero(current, f"Dự báo ML · Top 10 {name}", subtitle,
                    eyebrow="PHÒNG PHÂN TÍCH DỰ BÁO", core="ML / LOTO" if mode == "loto" else "ML / ĐB",
                    meta="Bản dự báo theo kỳ · Đọc cùng mức tin và kết quả kiểm ngoài mẫu",
                    action=("#app-lab-ranking", "Xem bảng xếp hạng"))
    guide = lab_guide([
        ("Xác suất công bố", "Giá trị sau phép co về nền: mức tin × xác suất thô + (1 − mức tin) × xác suất nền. "
         + ("Đặc Biệt được chuẩn hóa sau co để xác suất của toàn bộ 100 số cộng lại 100%. " if mode == "de" else "")
         + "Nhấp vào giá trị trong bảng để xem bước tính."),
        ("Thứ hạng", "Danh sách giữ nguyên thứ tự từ bản dự báo. Nếu xác suất sau co bằng nhau, thứ hạng không biểu thị khác biệt về xác suất công bố."),
        ("Chu kỳ cập nhật", "Sau 18:35 giờ Việt Nam, quy trình cập nhật dự báo cho kỳ tiếp theo. Ngày đích ở trên cho biết bản dự báo đang được hiển thị."),
    ])
    ranking = lab_card(table, title=f"10 số {name} đứng đầu" + (" (00–99)" if mode == "loto" else " (2 số cuối Đặc Biệt)"),
                       aside=_date_badge(date), span=12, flush=True, ident="app-lab-ranking")
    return (f'<div class="app-lab app-lab-forecast" data-lab-layout="forecast">{hero}'
            + _prediction_overview(frame, date, mode) + strip + '<div class="ui-grid">' + ranking + '</div>'
            + values_block([(f"ml-{mode}-summary", ml_summary_evidence(mode))])
            + guide + lab_footer() + '</div>')


def build() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    loto_top = _read_csv(ML_DIR / "predict_next_loto_ml_top10.csv")
    de_top = _read_csv(ML_DIR / "predict_next_de_ml_top10.csv")

    loto_table, loto_date = _prediction_table(loto_top)
    de_table, de_date = _prediction_table(de_top)
    # Mỗi hàng mang bằng chứng tính toán riêng (xác suất thô, model_trust, phép
    # co về nền); app-evidence.js mở nó khi người xem nhấp vào số trong hàng.
    loto_rows = ml_row_evidence(loto_top, "loto")
    de_rows = ml_row_evidence(de_top, "de")
    # Cột 0 là hạng "#": bằng chứng xác suất của hàng không giải thích hạng.
    loto_table = tag_rows(loto_table, [ident for ident, _ in loto_rows], cols=(2, 3)) + values_block(loto_rows)
    de_table = tag_rows(de_table, [ident for ident, _ in de_rows], cols=(2, 3)) + values_block(de_rows)

    write_stylesheet(DOCS_DIR)
    for mode, frame, table, date, rows in (
        ("loto", loto_top, loto_table, loto_date, loto_rows),
        ("de", de_top, de_table, de_date, de_rows),
    ):
        current = f"ml_top10_{mode}.html"
        name = "LOTO" if mode == "loto" else "Đặc Biệt"
        body = _forecast_body(frame, table, date, rows, mode)
        write_page(DOCS_DIR / current, _base_page(body, f"ML — 10 số {name} đứng đầu", current))

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
