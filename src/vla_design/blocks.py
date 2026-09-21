from __future__ import annotations

"""Khối HTML dùng lại cho mọi trang: thẻ, KPI, bảng, trạng thái phản hồi.

Vì sao tập trung ở đây: mục XVIII.5 cấm cùng một loại thành phần mang luật
khác nhau giữa các trang. Nếu mỗi trình dựng tự viết thẻ của nó thì hai mươi
chín trang sẽ có hai mươi chín biến thể — đúng chuyện đã xảy ra với giao diện
cũ.

Mọi chuỗi đi vào đây đều được escape. Không có lối nào để dữ liệu từ ``data/``
trở thành thẻ HTML: đó vừa là bảo mật, vừa là lý do một ô chứa ``<`` hiện ra
đúng ``<`` thay vì nuốt mất phần còn lại của bảng.
"""

import html
from collections.abc import Iterable, Sequence
from typing import Any

from vla_design.data_access import Dataset
from vla_design.icons import icon


def esc(value: Any) -> str:
    """Escape mọi thứ thành chữ an toàn. ``None`` thành dấu gạch dài."""
    if value is None:
        return "—"
    return html.escape(str(value), quote=True)


def card(title: str, body: str, *, note: str = "", actions: str = "", wide_body: bool = False) -> str:
    """Một thẻ có đầu, thân, và ghi chú tuỳ chọn.

    ``wide_body`` bỏ đệm thân để bảng chạm sát mép thẻ — bảng đã có đệm ô
    riêng, cộng thêm đệm thẻ là phí hai mươi pixel mỗi bên trên một trang
    toàn bảng.
    """
    head = (
        f'<header class="vla-card-head"><h2 class="vla-card-title">{esc(title)}</h2>'
        f"{actions}</header>"
        if title or actions
        else ""
    )
    body_class = "vla-card-body vla-card-body--flush" if wide_body else "vla-card-body"
    footer = f'<p class="vla-card-note">{esc(note)}</p>' if note else ""
    return f'<section class="vla-card">{head}<div class="{body_class}">{body}{footer}</div></section>'


def kpi(label: str, value: str, *, note: str = "", tone: str = "neutral") -> str:
    """Một ô số liệu chính. ``value`` đã định dạng sẵn, không định dạng ở đây."""
    badge = f'<p class="vla-kpi-note"><span class="vla-badge vla-badge--{esc(tone)}">{esc(note)}</span></p>' if note else ""
    return (
        '<article class="vla-card vla-card--kpi">'
        f'<p class="vla-kpi-label">{esc(label)}</p>'
        f'<p class="vla-kpi-value vla-num">{esc(value)}</p>'
        f"{badge}</article>"
    )


def kpi_row(cells: Iterable[str]) -> str:
    return f'<div class="vla-kpi-grid">{"".join(cells)}</div>'


def empty_state(message: str, *, hint: str = "") -> str:
    """Trạng thái RỖNG: dữ liệu thật sự chưa có. Không phải lỗi."""
    extra = f'<p class="vla-state-text">{esc(hint)}</p>' if hint else ""
    return (
        '<div class="vla-state">'
        f'<span class="vla-state-icon">{icon("calendar", size=28)}</span>'
        f'<p class="vla-state-title">{esc(message)}</p>{extra}</div>'
    )


def error_state(message: str, *, reason: str = "", source: str = "") -> str:
    """Trạng thái LỖI: hệ thống hỏng, và phải nói ra.

    Nêu cả nguồn và lý do. Một thông báo lỗi không nói hỏng ở đâu thì người
    đọc chỉ biết là hỏng, không biết báo gì cho ai.
    """
    parts = [p for p in (reason, source) if p]
    detail = f'<p class="vla-state-text">{esc(" · ".join(parts))}</p>' if parts else ""
    return (
        '<div class="vla-state vla-state--error">'
        f'<span class="vla-state-icon">{icon("flask", size=28)}</span>'
        f'<p class="vla-state-title">{esc(message)}</p>{detail}</div>'
    )


def dataset_fallback(dataset: Dataset, *, empty_message: str) -> str | None:
    """Khối thay thế khi tập dữ liệu không dùng được, hoặc ``None`` nếu dùng được.

    Gộp ba trạng thái về một lời gọi, để chỗ gọi không phải nhớ phân biệt
    ``empty`` với ``error`` — quên phân biệt là biến một đường ống hỏng thành
    "hôm nay chưa có số liệu".
    """
    if dataset.state == "ok":
        return None
    if dataset.state == "empty":
        return empty_state(empty_message, hint=f"Nguồn: {dataset.source}")
    return error_state(
        "Không đọc được dữ liệu cho phần này",
        reason=dataset.reason,
        source=dataset.source,
    )


def table(
    columns: Sequence[tuple[str, str]],
    rows: Iterable[Sequence[Any]],
    *,
    caption: str = "",
    numeric: Sequence[int] = (),
    row_classes: Iterable[str] | None = None,
) -> str:
    """Bảng dữ liệu chuẩn.

    Args:
        columns: Cặp ``(khoá, nhãn)``. Khoá đi vào ``data-col`` để CSS và phép
            kiểm bám vào ngữ nghĩa thay vì bám vào thứ tự cột.
        rows: Các hàng, mỗi hàng là dãy ô THEO THỨ TỰ của ``columns``.
        caption: Tóm tắt cho trình đọc màn hình. Bắt buộc về mặt ngữ nghĩa nên
            nếu không truyền thì bảng không có ``<caption>`` — và một phép
            kiểm ở `tests/test_vla_pages.py` bắt trường hợp đó.
        numeric: Chỉ số các cột là số, sẽ canh phải và dùng chữ số thẳng cột.
        row_classes: Lớp cho từng hàng, cùng thứ tự với ``rows``.
    """
    numeric_set = set(numeric)
    num_attr = ' class="vla-num"'
    head = "".join(
        f'<th scope="col" data-col="{esc(key)}"'
        + (num_attr if i in numeric_set else "")
        + f">{esc(label)}</th>"
        for i, (key, label) in enumerate(columns)
    )
    classes = list(row_classes) if row_classes is not None else []
    body: list[str] = []
    for index, row in enumerate(rows):
        cls = f' class="{esc(classes[index])}"' if index < len(classes) and classes[index] else ""
        cells = "".join(
            f'<td data-col="{esc(columns[i][0])}"'
            + (num_attr if i in numeric_set else "")
            + f">{esc(cell)}</td>"
            for i, cell in enumerate(row)
        )
        body.append(f"<tr{cls}>{cells}</tr>")
    cap = f'<caption class="vla-visually-hidden">{esc(caption)}</caption>' if caption else ""
    return (
        '<div class="vla-table-scroll">'
        f'<table class="vla-table">{cap}<thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def source_note(*datasets: Dataset) -> str:
    """Dòng ghi nguồn dữ liệu của một trang.

    Mỗi con số trên trang phải truy được về tệp sinh ra nó. Không có dòng này
    thì người đọc không phân biệt được số đo thật với số minh hoạ.
    """
    names = sorted({d.source for d in datasets if d.source})
    if not names:
        return ""
    items = " · ".join(f"<code>{esc(name)}</code>" for name in names)
    return f'<p class="vla-source-note">Nguồn dữ liệu: {items}</p>'


def disclaimer(text: str) -> str:
    """Khối cảnh báo. Dùng cho mọi trang mang tính dự đoán hoặc mô phỏng."""
    return (
        '<aside class="vla-disclaimer" role="note">'
        f'<span class="vla-disclaimer-icon">{icon("flask", size=18)}</span>'
        f"<span>{esc(text)}</span></aside>"
    )
