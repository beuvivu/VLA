"""Hiển thị không gian phân tích tại ranh giới xuất trang, giữ nguyên dữ liệu."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from pathlib import Path

from core.paths import TEMPLATES

_STYLE_ID = 'app-analysis-workspace-style'
_CSS = TEMPLATES.joinpath('analysis_workspace.css')
_DETAIL = {
    'dau-duoi-loto.html': ('Phân bố LOTO', 'Đối chiếu đầu và đuôi trước, rồi đọc ba bảng 20 kỳ gần nhất để xem phân bố thay đổi theo thời gian.'),
    'cap-lon-loto.html': ('Cặp số & đối chiếu', 'So sánh từng cặp đảo và số kép trong cùng dải ngày. Số kép được tách riêng vì đảo lại vẫn là chính nó.'),
    'lo-gan.html': ('Khoảng cách xuất hiện', 'Đọc gan hiện tại cùng gan cực đại và cặp lô gan. Khoảng vắng dài chỉ mô tả lịch sử, không cho biết kỳ kế tiếp.'),
    'cau-giai-dac-biet.html': ('Tần suất Đặc Biệt', 'Đọc số lần xuất hiện, đối chiếu cặp lộn rồi xem lại ba kỳ gần nhất.'),
    'giai-dac-biet-theo-tong.html': ('Phân bố theo tổng', 'Bắt đầu từ tổng hai chữ số, sau đó đối chiếu chuyển tiếp giữa hai kỳ và chẵn lẻ.'),
    'cau-dac-biet-theo-bo-so.html': ('Nhóm số Đặc Biệt', 'So sánh các bộ số trên cùng lịch sử. Đánh dấu ô để giữ mốc khi đối chiếu nhiều hàng.'),
    'chu-ky-dac-biet.html': ('Chu kỳ Đặc Biệt', 'Đối chiếu khoảng cách hiện tại với các chu kỳ đã ghi nhận; đọc đơn vị kỳ ngay trong bảng.'),
    'giai-db-ngay-mai.html': ('Đối chiếu lịch sử', 'Chọn hai số cuối, xem các lần từng về từ mới đến cũ và giải Đặc Biệt của đúng ngày hôm sau.'),
    'thong-ke-tong-hop.html': ('Toàn cảnh dữ liệu', 'Từ 100 số LOTO đến phân bố đầu, đuôi và tổng; đối chiếu nhóm xuất hiện nhiều với gan Đặc Biệt.'),
}


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str | None]
    start: int
    opened: int
    end: int = 0
    closed: int = 0
    parent: '_Node | None' = None
    children: list['_Node'] = field(default_factory=list)

    def has(self, name: str) -> bool:
        return name in (self.attrs.get('class') or '').split()


class _Layout(HTMLParser):
    """Chỉ lập chỉ mục vị trí; không tuần tự hóa lại HTML hay mã chạy sẵn."""
    def __init__(self, source: str):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0]
        self.lines.extend(m.end() for m in re.finditer('\n', source))
        self.nodes: list[_Node] = []
        self.stack: list[_Node] = []
        self.feed(source)

    def position(self) -> int:
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        start = self.position()
        node = _Node(tag, dict(attrs), start, start + len(self.get_starttag_text()))
        if self.stack:
            node.parent = self.stack[-1]
            node.parent.children.append(node)
        self.nodes.append(node)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append(node)
        else:
            node.end = node.opened

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                node = self.stack[index]
                node.closed = self.position()
                node.end = self.source.find('>', node.closed) + 1
                del self.stack[index:]
                break


def workspace_pages() -> set[str]:
    """Suy ra phạm vi từ điều hướng thật để trang bổ sung không bị bỏ sót."""
    from web.ui_theme import SITE_NAV_SECTIONS
    pages = set(_DETAIL)
    for group, sections in SITE_NAV_SECTIONS:
        if group in {'Soi cầu', 'Dự báo', 'Nghiên cứu & công cụ'}:
            pages.update(href.split('#')[0] for _, links in sections for href, _, _ in links)
    return pages - {'index.html', 'landing.html', 'landing_desktop.html'}


def _brief(filename: str) -> tuple[str, str]:
    if filename in _DETAIL:
        return _DETAIL[filename]
    if filename == 'tao-phoi-tuan.html':
        return 'Công cụ in & lưu', 'Chọn số lượng và kiểu chữ, xem trước phôi tuần rồi dùng các nút in hoặc tải ảnh ngay bên dưới.'
    if filename.startswith(('soi-cau-', 'soi-path-')):
        return 'Soi cầu · đối chiếu vị trí', 'Chọn mốc dữ liệu và điều kiện, đọc phân bố rồi mở từng số để đối chiếu đường cầu với kết quả gốc.'
    if filename == 'research-lab.html':
        return 'Nghiên cứu & kiểm định', 'Theo dõi giả thuyết qua kiểm định, tập giữ lại và cổng vận hành; mở phương pháp để đọc căn cứ của từng chỉ số.'
    return 'Dự báo & kiểm chứng', 'Đọc xếp hạng cùng mức nền, cỡ mẫu và kết quả kiểm ngoài mẫu. Mở từng chỉ số để xem căn cứ trước khi so sánh.'


def _guide(filename: str) -> str:
    label, description = _brief(filename)
    links = [('thong-ke-tong-hop.html', 'Tổng quan dữ liệu'), ('soi-cau-vi-tri.html', 'Đối chiếu vị trí'), ('model-quality.html', 'Kiểm chứng mô hình')]
    if filename == 'tao-phoi-tuan.html':
        links = [('bang-dac-biet.html', 'Xem kết quả theo tuần'), ('thong-ke-tong-hop.html', 'Đối chiếu thống kê')]
    anchors = ''.join(f'<a href="{href}">{text}<span aria-hidden="true"> ↗</span></a>' for href, text in links if href != filename)
    return (f'<aside class="app-workspace-guide" data-app-workspace-guide aria-label="Hướng dẫn phân tích">'
            f'<div><span class="app-workspace-eyebrow">{escape(label)}</span><p>{escape(description)}</p></div>'
            f'<nav aria-label="Trang phân tích liên quan">{anchors}</nav></aside>')


def refine_workspace(path: Path | str, page: str) -> str:
    """Bổ sung phân cấp, đường đọc và khối điều khiển, lũy đẳng từng byte."""
    filename = Path(path).name
    if filename not in workspace_pages():
        return page
    css = f'<style id="{_STYLE_ID}">{_CSS.read_text(encoding="utf-8")}</style>'
    page = re.sub(r'<style\b[^>]*id=["\']' + _STYLE_ID + r'["\'][^>]*>.*?</style>\s*', '', page, flags=re.S)
    page = page.replace('</head>', css + '\n</head>', 1)
    if 'data-app-workspace-guide' in page:
        return page
    layout = _Layout(page)
    edits: list[tuple[int, int, str]] = []

    def annotate(node: _Node, classes: str, attrs: str = '') -> None:
        opening = page[node.start:node.opened]
        found = re.search(r'\bclass=(["\'])(.*?)\1', opening, re.S)
        if found:
            opening = opening[:found.start(2)] + found[2] + ' ' + classes + opening[found.end(2):]
        else:
            opening = opening[:-1] + f' class="{classes}">'
        if attrs:
            opening = opening[:-1] + ' ' + attrs + '>'
        edits.append((node.start, node.opened, opening))

    body = next((n for n in layout.nodes if n.tag == 'body'), None)
    if body:
        annotate(body, 'app-workspace' + (' app-workspace-detail' if filename in _DETAIL else '') + (' app-workspace-overview' if filename == 'thong-ke-tong-hop.html' else ''), f'data-app-workspace-page="{escape(Path(filename).stem)}"')
    heading = next((n for n in layout.nodes if n.tag == 'h1'), None)
    if heading:
        hero = heading.parent
        while hero and not (hero.tag == 'header' or any(hero.has(c) for c in ('path-hero', 'rl-hero', 'sp-detail-hero'))):
            hero = hero.parent
        if hero and hero.end:
            annotate(hero, 'app-workspace-hero')
            edits.append((hero.end, hero.end, _guide(filename)))
        else:
            # Các trang chi tiết cũ chỉ có h1 + mô tả; giữ nguyên hai nút này.
            end = heading.end
            if heading.parent:
                siblings = heading.parent.children
                index = siblings.index(heading)
                if index + 1 < len(siblings) and siblings[index + 1].tag == 'p':
                    end = siblings[index + 1].end
            edits.append((heading.start, heading.start, '<header class="app-workspace-hero"><p class="app-workspace-eyebrow">' + escape(_brief(filename)[0]) + '</p>'))
            edits.append((end, end, '</header>' + _guide(filename)))
    else:
        # Mẫu nhỏ dùng trong kiểm thử vẫn có thể đọc đúng khối điều khiển.
        target = next((n for n in layout.nodes if n.has('ui-shell') or n.has('path-shell')), body)
        if target:
            edits.append((target.opened, target.opened, _guide(filename)))
    for node in layout.nodes:
        if node.has('sp-controls'):
            annotate(node, 'app-workspace-controls')
            if filename != 'thong-ke-tong-hop.html':
                edits.append((node.start, node.start, '<section class="app-workspace-filter" aria-label="Điều kiện phân tích"><header><span class="app-workspace-step">01</span><div><h2>Chọn dữ liệu cần xem</h2><p>Đổi điều kiện để cập nhật các bảng bên dưới.</p></div></header>'))
                edits.append((node.end, node.end, '</section>'))
        if node.has('sp-scroll'):
            attrs = '' if node.attrs.get('tabindex') is not None else 'tabindex="0"'
            if not node.attrs.get('role'):
                attrs += ' role="region" aria-label="Bảng phân tích có thể cuộn"'
            annotate(node, 'app-workspace-table', attrs.strip())
        if node.tag == 'h3' and node.has('sp-subhead'):
            annotate(node, 'app-workspace-section-title')
    # Áp dụng từ cuối về đầu giữ toàn bộ vị trí và byte của script nghiệp vụ.
    for start, end, replacement in sorted(edits, key=lambda edit: (edit[0], edit[1]), reverse=True):
        page = page[:start] + replacement + page[end:]
    return page
