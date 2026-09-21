from __future__ import annotations

"""Dựng khung trang VLA — MỘT hàm cho cả 29 trang.

Trước đây mười một trình dựng mỗi cái tự viết thẻ ``<head>``, tự khai điều
hướng, tự khai CSS. Hệ quả đo được ở giao diện cũ: bốn trang soi-path nằm lệch
khỏi phần còn lại vì không trình dựng nào chạy lại chúng, và cùng một khái
niệm màu mang ba giá trị. Ở đây trang chỉ cung cấp NỘI DUNG; khung, điều
hướng, CSP, chủ đề đều từ một chỗ.

Chính sách CSP là ``default-src 'none'`` rồi mở từng thứ cần. Mặc định đóng
chứ không mặc định mở: một chỉ thị bị quên sẽ làm tài nguyên bị chặn — thấy
ngay — thay vì lặng lẽ cho phép thứ không nên cho.
"""

import html
from dataclasses import dataclass, field
from typing import Final

from vla_design.icons import icon
from vla_design.navigation import NAV, all_items, group_of

#: Chính sách CSP mặc định. ``script-src 'self'`` là lý do mọi JavaScript của
#: VLA nằm ở tệp riêng chứ không nội tuyến, và ``style-src 'self'`` là lý do
#: CSS cũng vậy. Trang nào cần gọi mạng (ví dụ trang trực tiếp) truyền thêm
#: ``connect_src`` thay vì nới chính sách cho mọi trang.
#:
#: KHÔNG có ``frame-ancestors`` ở đây, và đó là một giới hạn thật chứ không
#: phải bỏ quên. Chỉ thị ấy bị BỎ QUA khi giao qua ``<meta>`` — Chromium ghi
#: thẳng vào console: "The Content Security Policy directive 'frame-ancestors'
#: is ignored when delivered via a <meta> element". Nó chỉ hoạt động qua
#: HTTP header, mà GitHub Pages không cho đặt header. Hệ quả: VLA KHÔNG được
#: bảo vệ khỏi bị nhúng trong iframe của trang khác. Muốn có thì phải đưa
#: trang qua một CDN cho phép đặt header, ví dụ Cloudflare — đó là quyết định
#: hạ tầng, không phải quyết định của tầng giao diện.
DEFAULT_CSP: Final[dict[str, str]] = {
    "default-src": "'none'",
    "base-uri": "'none'",
    "form-action": "'none'",
    "img-src": "'self' data:",
    "style-src": "'self'",
    "script-src": "'self'",
    "font-src": "'self'",
    "connect-src": "'self'",
}


def csp_value(*, connect_src: str = "") -> str:
    """Chuỗi ``Content-Security-Policy``, có thể nới riêng ``connect-src``."""
    policy = dict(DEFAULT_CSP)
    if connect_src:
        policy["connect-src"] = f"{policy['connect-src']} {connect_src}".strip()
    return "; ".join(f"{key} {value}" for key, value in policy.items())


@dataclass(frozen=True)
class Crumb:
    label: str
    href: str = ""


@dataclass(frozen=True)
class Page:
    """Mọi thứ một trang cần khai, ngoài phần nội dung của nó.

    Attributes:
        nav_key: Khoá trong ``navigation``. Quyết định mục nào được đánh dấu
            đang mở, nên khoá sai là trang không có mục nào sáng.
        title: Tiêu đề hiển thị ở đầu trang và trong thẻ ``<title>``.
        subtitle: Một đoạn ngắn nói trang này trả lời câu hỏi gì.
        crumbs: Đường dẫn phía trên tiêu đề. Mục "Trang chủ" được thêm sẵn.
        wide: Dùng khung rộng 1920px cho ma trận và bảng lớn — mục 5.1 cấm ép
            bảng thống kê vào khung hẹp.
        actions: HTML của các nút ở góc phải đầu trang.
        connect_src: Nới ``connect-src`` của CSP cho riêng trang này.
    """

    nav_key: str
    title: str
    subtitle: str = ""
    crumbs: tuple[Crumb, ...] = ()
    wide: bool = False
    actions: str = ""
    connect_src: str = ""
    extra_head: str = ""
    body_end: str = ""
    css_files: tuple[str, ...] = field(default_factory=lambda: ("assets/vla.css",))
    js_files: tuple[str, ...] = field(default_factory=lambda: ("assets/vla-shell.js",))


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def _nav_html(active_key: str) -> str:
    active_group = group_of(active_key)
    parts: list[str] = []
    for group in NAV:
        # Nhóm chứa trang đang mở thì mở sẵn. Bắt người đọc tự bấm mở nhóm để
        # tìm ra mình đang ở đâu là đánh mất chính thông tin mà mục 5.3 đòi.
        is_open = active_group is not None and active_group.key == group.key
        parts.append(
            f'<details class="vla-nav-group"{" open" if is_open else ""}>'
            f'<summary>{icon(group.icon, size=18)}'
            f'<span class="vla-nav-group-label">{_esc(group.label)}</span>'
            f'{icon("chevron", size=16, extra_class="vla-nav-caret")}'
            f"</summary>"
            f'<ul class="vla-nav-list">'
        )
        for item in group.items:
            current = ' aria-current="page"' if item.key == active_key else ""
            parts.append(
                f'<li><a class="vla-nav-link" href="{_esc(item.href)}"'
                f'{current} title="{_esc(item.summary)}">{_esc(item.label)}</a></li>'
            )
        parts.append("</ul></details>")
    return "".join(parts)


def _crumbs_html(page: Page) -> str:
    crumbs = (Crumb("Trang chủ", "index.html"), *page.crumbs)
    group = group_of(page.nav_key)
    if group is not None and not page.crumbs:
        crumbs = (*crumbs, Crumb(group.label))
    items: list[str] = []
    for index, crumb in enumerate(crumbs):
        if index:
            items.append('<li class="vla-breadcrumb-sep" aria-hidden="true">/</li>')
        if crumb.href:
            items.append(f'<li><a href="{_esc(crumb.href)}">{_esc(crumb.label)}</a></li>')
        else:
            items.append(f"<li>{_esc(crumb.label)}</li>")
    items.append('<li class="vla-breadcrumb-sep" aria-hidden="true">/</li>')
    items.append(f'<li aria-current="page">{_esc(page.title)}</li>')
    return (
        '<nav class="vla-breadcrumb" aria-label="Đường dẫn">'
        f'<ol class="vla-breadcrumb-list">{"".join(items)}</ol></nav>'
    )


def _topbar_context(page: Page) -> str:
    """Chữ trên đầu trang dính: TÊN NHÓM, không phải tên trang.

    Đo trên ảnh chụp thật: lặp tiêu đề ở cả topbar và ``<h1>`` làm hai dòng
    giống nhau cách nhau 40px, và trên màn 375px nó ăn 64px chiều cao để nhắc
    lại đúng thứ ngay bên dưới. Tên nhóm thì KHÔNG lặp — trên điện thoại
    sidebar đóng nên đây là chỗ duy nhất nói người đọc đang ở nhánh nào.
    """
    group = group_of(page.nav_key)
    return group.label if group is not None else "VLA"


def _theme_button() -> str:
    """Nút xoay ba trạng thái chủ đề, với cả ba nhãn nằm sẵn trong DOM.

    Ba nhãn có sẵn và CSS chọn nhãn nào hiện, nên JavaScript không phải viết
    thẻ vào DOM lúc chạy — tránh đúng lớp thao tác mà bộ kiểm bảo mật của kho
    cấm. Một vùng ``aria-live`` riêng thông báo thay đổi cho trình đọc màn
    hình, vì đổi màu là thay đổi mà người không thấy màu không nhận ra được.
    """
    return (
        '<button type="button" class="vla-btn vla-btn--icon" data-vla-theme-toggle'
        ' aria-describedby="vla-theme-live">'
        f'<span class="vla-theme-label vla-theme-label--system">{icon("monitor")}</span>'
        f'<span class="vla-theme-label vla-theme-label--light">{icon("sun")}</span>'
        f'<span class="vla-theme-label vla-theme-label--dark">{icon("moon")}</span>'
        '<span class="vla-visually-hidden">Đổi chủ đề: theo hệ thống, sáng, tối</span>'
        "</button>"
        '<span id="vla-theme-live" class="vla-visually-hidden" role="status" aria-live="polite"></span>'
    )


def render_page(page: Page, content: str) -> str:
    """Một tài liệu HTML hoàn chỉnh: khung, điều hướng, chủ đề, nội dung.

    Args:
        page: Khai báo của trang.
        content: HTML phần nội dung, đã tự escape.

    Returns:
        Chuỗi HTML đầy đủ, đã có CSP và ``lang="vi"``.

    Raises:
        KeyError: Khi ``nav_key`` không có trong mô hình điều hướng.
    """
    known = {item.key for item in all_items()}
    if page.nav_key not in known:
        raise KeyError(f"nav_key {page.nav_key!r} không có trong mô hình điều hướng")

    container = "vla-container vla-container--wide" if page.wide else "vla-container"
    css = "".join(
        f'<link rel="stylesheet" href="{_esc(href)}">' for href in page.css_files
    )
    # Script nạp CHẶN trong <head>, không `defer`: nó đặt `data-theme` trước
    # khi trang được vẽ. Dùng `defer` thì trang hiện ra ở chủ đề sáng rồi nhảy
    # sang tối — nháy chủ đề, và mục XI cấm layout shift khi tải.
    js = "".join(f'<script src="{_esc(href)}"></script>' for href in page.js_files)
    subtitle = (
        f'<p class="vla-page-sub">{_esc(page.subtitle)}</p>' if page.subtitle else ""
    )
    actions = (
        f'<div class="vla-page-actions">{page.actions}</div>' if page.actions else ""
    )

    return f"""<!DOCTYPE html>
<html lang="vi" data-theme-state="system">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{_esc(csp_value(connect_src=page.connect_src))}">
<meta name="color-scheme" content="light dark">
<meta name="description" content="{_esc(page.subtitle or page.title)}">
<title>{_esc(page.title)} · VLA</title>
{css}{js}{page.extra_head}
</head>
<body>
<a class="vla-skip-link" href="#vla-content">Bỏ qua điều hướng, tới nội dung</a>
<div class="vla-app">
<aside id="vla-sidebar" class="vla-sidebar" data-open="false">
  <div class="vla-sidebar-brand">
    <span class="vla-brand-mark" aria-hidden="true">VLA</span>
    <span class="vla-brand-text">
      <span class="vla-brand-name">Phân tích XSMB</span>
      <span class="vla-brand-sub">Thống kê &amp; xác suất</span>
    </span>
    <button type="button" class="vla-btn vla-btn--icon vla-menu-button" data-vla-nav-close>
      {icon("close")}<span class="vla-visually-hidden">Đóng điều hướng</span>
    </button>
  </div>
  <nav class="vla-sidebar-scroll" aria-label="Điều hướng chính">
    {_nav_html(page.nav_key)}
  </nav>
  <div class="vla-sidebar-foot">
    Mọi số liệu là THỐNG KÊ MÔ TẢ, không phải dự đoán có giá trị kỳ vọng dương.
  </div>
</aside>
<div id="vla-backdrop" class="vla-backdrop" data-open="false"></div>
<div id="vla-main" class="vla-main">
  <header class="vla-topbar">
    <button type="button" class="vla-btn vla-btn--icon vla-menu-button" data-vla-nav-toggle
            aria-expanded="false" aria-controls="vla-sidebar">
      {icon("menu")}<span class="vla-visually-hidden">Mở điều hướng</span>
    </button>
    <div class="vla-topbar-title">
      <span class="vla-topbar-context">{_esc(_topbar_context(page))}</span>
    </div>
    <div class="vla-topbar-actions">{_theme_button()}</div>
  </header>
  <main id="vla-content" class="vla-content" tabindex="-1">
    <div class="{container}">
      {_crumbs_html(page)}
      <div class="vla-page-head">
        <div class="vla-page-head-text">
          <h1 class="vla-page-title">{_esc(page.title)}</h1>
          {subtitle}
        </div>
        {actions}
      </div>
      {content}
    </div>
  </main>
</div>
</div>
{page.body_end}
</body>
</html>
"""
