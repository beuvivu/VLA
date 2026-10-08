"""Thành phần trình bày của nhóm trang nghiên cứu; không tính lại mô hình."""

from __future__ import annotations

import html
from pathlib import Path

from ui_theme import card

TEMPLATES = Path(__file__).with_name("templates")
PAGES = (
    ("research-lab.html", "Research Lab"),
    ("dashboard.html", "Điều khiển AI/ML"),
    ("model-quality.html", "Chất lượng mô hình"),
    ("do-tin-cay.html", "Độ tin cậy"),
    ("ml_top10_loto.html", "Top 10 LOTO"),
    ("ml_top10_de.html", "Top 10 Đặc Biệt"),
)


def lab_styles() -> str:
    """Nhúng lớp phủ có phạm vi; dùng token sáng/tối của giao diện chung."""
    return '<style id="app-lab-style">' + (TEMPLATES / "ai_lab.css").read_text(encoding="utf-8") + '</style>'


def lab_hero(current: str, title: str, subtitle: str, *, eyebrow: str,
             core: str, meta: str, action: tuple[str, str]) -> str:
    """Minh họa quỹ đạo là đồ họa khái niệm, không biểu diễn số đo hay tiến độ."""
    h = html.escape
    diagram = (TEMPLATES / "ai_lab_orbit.html").read_text(encoding="utf-8")
    diagram = diagram.replace("__CORE__", h(core))
    links = "".join(
        f'<a href="{url}"' + (' aria-current="page"' if url == current else '') + f'>{h(label)}</a>'
        for url, label in PAGES
    )
    return f'''<div class="app-lab-masthead"><span>KHÔNG GIAN NGHIÊN CỨU</span>
<a href="research-lab.html">Hệ sinh thái AI / ML <span aria-hidden="true">↗</span></a></div>
<header class="app-lab-hero" id="app-lab-top">
<div class="app-lab-aurora" aria-hidden="true"></div><div class="app-lab-scan" aria-hidden="true"></div>
<div class="app-lab-hero-copy"><p class="app-lab-eyebrow"><i aria-hidden="true"></i>{h(eyebrow)}</p>
<h1>{h(title)}</h1><p class="app-lab-lead">{h(subtitle)}</p>
<div class="app-lab-hero-actions"><a class="app-lab-primary" href="{h(action[0])}">{h(action[1])}<span aria-hidden="true">↘</span></a>
<a class="app-lab-secondary" href="#app-lab-guide">Cách đọc báo cáo <span aria-hidden="true">↓</span></a></div>
<p class="app-lab-meta">{h(meta)}</p></div>
<figure class="app-lab-orbit">{diagram}<figcaption>Sơ đồ minh họa · dữ liệu → mô hình → kiểm chứng</figcaption></figure>
</header><nav class="app-lab-nav" aria-label="Các phòng nghiên cứu">{links}</nav>'''


def lab_jump(items: list[tuple[str, str]]) -> str:
    links = "".join(f'<a href="#{html.escape(ident)}">{html.escape(label)}</a>' for ident, label in items)
    return f'<nav class="app-lab-jump" aria-label="Mục lục báo cáo"><span>TRONG BÁO CÁO</span>{links}</nav>'


def lab_card(body: str, *, title: str = "", aside: str = "", span: int = 0,
             flush: bool = False, lift: bool = False, ident: str = "") -> str:
    """Giữ cấu trúc thẻ và tiêu đề để ngăn kéo bằng chứng nhận đúng khối."""
    content = card(body, title=title, aside=aside, span=span, flush=flush, lift=lift)
    if ident:
        content = content.replace('<section ', f'<section id="{html.escape(ident)}" ', 1)
    # Bảng vẫn là bảng thật; vùng cuộn có tên và dùng được bằng bàn phím.
    content = content.replace('<div class="ui-table-wrap">',
                              f'<div class="ui-table-wrap" tabindex="0" role="region" aria-label="{html.escape(title)}">')
    return content.replace('<th>', '<th scope="col">')


def lab_guide(entries: list[tuple[str, str]]) -> str:
    terms = ''.join(f'<div><dt>{html.escape(term)}</dt><dd>{html.escape(note)}</dd></div>'
                    for term, note in entries)
    return f'''<details class="app-lab-guide" id="app-lab-guide"><summary>Cách đọc báo cáo
<span>THUẬT NGỮ &amp; PHƯƠNG PHÁP</span></summary><dl>{terms}</dl></details>'''


def lab_footer() -> str:
    return '''<footer class="app-lab-footer"><span>NGHIÊN CỨU CÓ KIỂM CHỨNG · MINH BẠCH PHƯƠNG PHÁP</span>
<a href="#app-lab-top">Về đầu trang ↑</a></footer>'''
