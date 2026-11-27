from __future__ import annotations

import re
from html import escape
from typing import Final

from web.app_icons import icon_svg
from web.nexlink_icons import nexlink_icon, navigation_icon
from web.ui_theme import LANDING_SECTIONS, SITE_NAV, SITE_NAV_SECTIONS, SITE_SEARCH_EXTRAS

RAIL_W: Final[int] = 80
PANEL_W: Final[int] = 240
PANEL_W_SM: Final[int] = 220
HEADER_H: Final[int] = 80
BP_DESKTOP: Final[int] = 1200

NHAN_NGAN: Final[dict[str, str]] = {
    "Kết quả": "Kết quả",
    "Vietlott": "Vietlott",
    "Thống kê": "Thống kê",
    "Thống kê LOTO": "LOTO",
    "Thống kê Đặc Biệt": "Đặc Biệt",
    "Soi cầu": "Soi cầu",
    "Dự báo": "Dự báo",
    "Nghiên cứu & công cụ": "Công cụ",
}
BIEU_TUONG_NHOM: Final[dict[str, str]] = {
    "Kết quả": "home",
    "Vietlott": "tags",
    "Thống kê": "chart",
    "Thống kê LOTO": "clipboard",
    "Thống kê Đặc Biệt": "crown",
    "Soi cầu": "layers",
    "Dự báo": "robot",
    "Nghiên cứu & công cụ": "code",
}


def _trang_chuan(ten_tep: str) -> str:
    return "index.html" if ten_tep in {"landing.html", "landing_desktop.html"} else ten_tep


def _nhom_cua_trang(ten_tep: str) -> int:
    ten_tep = _trang_chuan(ten_tep)
    for i, (_, muc) in enumerate(SITE_NAV):
        for href, _, _ in muc:
            if href.split("#", 1)[0] == ten_tep:
                return i
    return 0


def rail_html(current: str) -> str:
    active = _nhom_cua_trang(current)
    parts = [
        '<aside class="app-rail" id="app-rail" aria-label="Nhóm chức năng">',
        '<div class="app-rail-list" role="tablist" aria-orientation="vertical">',
    ]
    for group, (label, _) in enumerate(SITE_NAV):
        if label in ("Thống kê", "Soi cầu", "Nghiên cứu & công cụ"):
            parts.append('<span class="app-rail-divider" role="presentation"></span>')
        selected = 'true' if group == active else 'false'
        tab_index = '0' if group == active else '-1'
        parts.append(
            f'<button class="app-rail-btn" role="tab" type="button" id="app-tab-{group}"'
            f' aria-controls="app-panel-{group}" aria-selected="{selected}"'
            f' tabindex="{tab_index}"'
            f' data-app-group="{group}" data-app-module="{"vietlott" if label == "Vietlott" else "standard"}"'
            f' aria-label="{escape(label, quote=True)}">'
            f'<span class="app-rail-ic">{nexlink_icon(BIEU_TUONG_NHOM[label])}</span>'
            f'<span class="app-rail-lb" aria-hidden="true">{escape(NHAN_NGAN[label])}</span></button>'
        )
    parts.extend([
        '</div><div class="app-rail-actions" role="group" aria-label="Thao tác menu">',
        '<button class="app-rail-link app-rail-add" id="app-rail-add" type="button"'
        ' aria-label="Mở chức năng" aria-haspopup="dialog" aria-controls="app-global-search">'
        + nexlink_icon('plus') + '</button>',
        '<button class="app-rail-link app-rail-exit" id="app-rail-exit" type="button"'
        ' aria-label="Đóng menu">' + nexlink_icon('exit') + '</button>',
        '</div></aside>',
    ])
    return ''.join(parts)


def panel_html(current: str) -> str:
    hoat_dong = _nhom_cua_trang(current)
    phan = [
        '<div class="app-panel" id="app-panel" aria-label="Chức năng trong nhóm">',
        '<div class="app-panel-head"><span class="app-panel-title" id="app-panel-title">'
        f"{escape(SITE_NAV[hoat_dong][0])}</span></div>",
    ]
    for i, (_ten, cum) in enumerate(SITE_NAV_SECTIONS):
        an = "" if i == hoat_dong else " hidden"
        phan.append(
            f'<nav class="app-panel-group" id="app-panel-{i}" role="tabpanel"'
            f' data-app-module="{"vietlott" if _ten == "Vietlott" else "standard"}"'
            f' aria-labelledby="app-tab-{i}" data-app-group="{i}"{an}>'
        )
        for j, (tieu_de, muc) in enumerate(cum):
            heading_id = f"app-nav-heading-{i}-{j}"
            phan.append(
                f'<section class="app-nav-section" aria-labelledby="{heading_id}">'
                f'<h3 class="app-nav-heading" id="{heading_id}">{escape(tieu_de)}</h3>'
            )
            for href, nhan, bieu_tuong in muc:
                la_trang_nay = href == _trang_chuan(current)
                danh_dau = ' aria-current="page"' if la_trang_nay else ""
                lop = " app-nav-item--active" if la_trang_nay else ""
                phan.append(
                    f'<a class="app-nav-item{lop}" href="{escape(href, quote=True)}"{danh_dau}'
                    f' data-app-label="{escape(nhan, quote=True)}">'
                    f'<span class="app-nav-ic">{navigation_icon(bieu_tuong)}</span>'
                    f'<span class="app-nav-lb">{escape(nhan)}</span></a>'
                )
            phan.append("</section>")
        phan.append("</nav>")
    if _trang_chuan(current) == "index.html":
        phan.append('<details class="app-page-sections"><summary>Trên trang này</summary>'
                    '<nav aria-label="Các phần trong trang">')
        for section_id, label, _ in LANDING_SECTIONS:
            phan.append(f'<a class="app-section-link" href="#{escape(section_id)}">{escape(label)}</a>')
        phan.append('</nav></details>')
    phan.append("</div>")
    return "".join(phan)


def header_html(current: str) -> str:
    group = escape(SITE_NAV[_nhom_cua_trang(current)][0])
    page = next((label for _, items in SITE_NAV for href, label, _ in items
                 if href == _trang_chuan(current)), 'Tổng quan')
    return (
        '<header class="app-header" id="app-header">'
        '<a class="app-rail-brand" href="index.html" aria-label="Vietnam Lottery Analysis">'
        '<img class="app-brand-icon" src="assets/lottery-drum.webp" alt="" width="48" height="48"></a>'
        '<div class="app-header-inner">'
        '<button class="app-icon-btn app-toggle" id="app-toggle" type="button"'
        ' aria-expanded="false" aria-controls="app-panel">'
        + nexlink_icon('chevrons') + '<span class="app-sr">Mở hoặc đóng menu chi tiết</span></button>'
        '<div class="app-header-start">'
        '<button class="app-search-trigger" id="app-search-open" type="button"'
        ' aria-haspopup="dialog" aria-controls="app-global-search" aria-description="Tìm chức năng (Ctrl K)">'
        + nexlink_icon('search') + '<span>Tìm kiếm chức năng…</span></button>'
        '</div>'
        '<nav class="app-crumbs app-sr" aria-label="Đường dẫn">'
        f'<span class="app-crumb">{group}</span><span aria-hidden="true"> / </span>'
        f'<span class="app-crumb app-crumb--now">{escape(page)}</span></nav>'
        '<div class="app-header-end">'
        '<div class="app-theme-wrap"><button class="app-theme-switch" id="app-theme" type="button">'
        '<span class="app-theme-ic" aria-hidden="true">'
        + nexlink_icon('sun', 'app-nexlink-ic app-theme-sun')
        + nexlink_icon('moon', 'app-nexlink-ic app-theme-moon') + '</span>'
        '<span class="app-sr">Đổi chế độ màu</span></button></div>'
        '<span class="app-header-divider" aria-hidden="true"></span>'
        '<div class="app-header-tools">'
        '<a class="app-icon-btn" href="live.html" aria-label="Kết quả trực tiếp">'
        + nexlink_icon('inbox') + '<span class="app-status-dot" aria-hidden="true"></span></a>'
        '<div class="app-dropdown">'
        '<button class="app-icon-btn" id="app-notifications-toggle" type="button"'
        ' aria-expanded="false" aria-controls="app-notifications-menu" aria-label="Cập nhật">'
        + nexlink_icon('bell') + '</button>'
        '<div class="app-dropdown-menu app-notifications-menu" id="app-notifications-menu" hidden>'
        '<h2>Cập nhật</h2>'
        '<a href="index.html#ket-qua">' + nexlink_icon('inbox') + '<span>Kết quả mới nhất<small>Xem bảng kết quả theo giải</small></span></a>'
        '<a href="model-quality.html">' + nexlink_icon('clipboard') + '<span>Chất lượng mô hình<small>Kiểm tra dữ liệu và độ chính xác</small></span></a>'
        '<a href="index.html#backtest">' + nexlink_icon('chart') + '<span>Kiểm định AI/ML<small>Đối chiếu với kết quả lịch sử</small></span></a>'
        '</div></div>'
        '<a class="app-icon-btn app-calendar-link" href="index.html#db-tuan-thang" aria-label="Lịch vạn niên">'
        + nexlink_icon('calendar') + '</a></div>'
        '<span class="app-header-divider" aria-hidden="true"></span>'
        '<div class="app-dropdown app-profile">'
        '<button class="app-profile-toggle" id="app-profile-toggle" type="button"'
        ' aria-expanded="false" aria-controls="app-profile-menu" aria-label="Menu ứng dụng">'
        '<span class="app-profile-copy"><strong>Vietnam Lottery</strong><small>'
        + nexlink_icon('angle-down') + ' Analysis</small></span>'
        '<span class="app-avatar"><img src="assets/lottery-drum.webp" alt="" width="40" height="40"></span></button>'
        '<div class="app-dropdown-menu app-profile-menu" id="app-profile-menu" hidden>'
        '<a href="index.html">' + nexlink_icon('house-blank') + 'Trang tổng quan</a>'
        '<a href="dashboard.html">' + nexlink_icon('circle-user') + 'Bảng điều khiển AI/ML</a>'
        '<a href="model-quality.html">' + nexlink_icon('review') + 'Chất lượng mô hình</a>'
        '<button id="app-fullscreen" type="button" aria-label="Toàn màn hình">'
        + nexlink_icon('arrows') + '<span>Toàn màn hình</span></button>'
        '<a href="research-lab.html">' + nexlink_icon('sliders-h-square') + 'Công cụ nghiên cứu</a>'
        '</div></div></div></div></header>'
    )


def global_search_html() -> str:
    muc = [(href, nhan, nhom, icon) for nhom, nhom_muc in SITE_NAV
           for href, nhan, icon in nhom_muc]
    muc.extend((f"index.html#{key}", label, "Trên trang chủ", "hom-nay")
               for key, label, _ in LANDING_SECTIONS)
    muc.extend((href, label, "Giao diện", icon) for href, label, icon in SITE_SEARCH_EXTRAS)
    da_co: set[str] = set()
    lien_ket: list[str] = []
    for href, nhan, nhom, icon in muc:
        if href in da_co:
            continue
        da_co.add(href)
        lien_ket.append(
            f'<a class="app-global-result" id="app-global-result-{len(lien_ket)}"'
            f' href="{escape(href, quote=True)}" role="option" tabindex="-1" aria-selected="false"'
            f' data-app-search="{escape(nhan + " " + nhom, quote=True)}">'
            f'{icon_svg(icon)}<span class="app-global-result-copy">'
            f'<span>{escape(nhan)}</span><small>{escape(nhom)}</small></span></a>'
        )
    return (
        '<dialog class="app-global-search" id="app-global-search" aria-modal="true"'
        ' aria-labelledby="app-global-search-title" aria-describedby="app-global-search-hint">'
        '<div class="app-global-search-surface">'
        '<div class="app-global-search-heading"><h2 id="app-global-search-title">Tìm chức năng</h2>'
        '<button class="app-icon-btn" id="app-global-search-close" type="button" aria-label="Đóng tìm kiếm">'
        f'{icon_svg("close")}</button></div>'
        '<label class="app-sr" for="app-global-search-input">Tìm trên toàn ứng dụng</label>'
        '<input class="app-search-input app-global-search-input" id="app-global-search-input"'
        ' type="search" placeholder="Tìm trang, thống kê hoặc chức năng…" autocomplete="off"'
        ' role="combobox" aria-autocomplete="list" aria-expanded="false"'
        ' aria-controls="app-global-search-results">'
        f'<p class="app-global-search-status" id="app-global-search-status" role="status" aria-live="polite">{len(lien_ket)} chức năng</p>'
        '<div class="app-global-search-results" id="app-global-search-results" role="listbox" aria-label="Kết quả tìm kiếm">'
        + "".join(lien_ket)
        + '</div><p class="app-global-search-empty" id="app-global-search-empty" role="status" aria-live="polite" hidden>Không có chức năng nào khớp.</p>'
        '<p class="app-global-search-hint" id="app-global-search-hint">↑ ↓ để chọn · Enter để mở · Esc để đóng</p>'
        '</div></dialog>'
    )


_DOCK_CU = re.compile(
    r"<nav\b(?=[^>]*\bclass=[\"'][^\"']*\b(?:ui-dock|dock)\b)[^>]*>.*?</nav>\s*",
    re.S | re.I,
)
_DOCK_KICH_BAN = re.compile(
    r"<script>\s*\(function\(\)\{var d=document\.querySelector\([\"']\.(?:ui-)?dock[\"']\);if\(!d\)return;"
    r".*?</script>\s*",
    re.S | re.I,
)
_MO_MAIN = re.compile(
    r"<(?:main|div)\b(?=[^>]*\bid=[\"']app-main[\"'])(?=[^>]*\bclass=[\"'][^\"']*\bapp-main\b)[^>]*>",
    re.I,
)
_DUOI_KHUNG: Final[re.Pattern[str]] = re.compile(
    r"</(?:main|div)>\s*(?:<script\b[^>]*\bsrc\s*=\s*([\"'])"
    r"assets/app-shell\.js(?:[?#][^\"']*)?\1[^>]*>\s*</script>\s*)?\Z"
)
_MO_BODY = re.compile(r"(<body\b[^>]*>)", re.I)
_DONG_BODY = re.compile(r"</body\s*>", re.I)


def _go_khung(than: str) -> str:
    while True:
        if "app-rail" not in than:
            return than
        dau = _MO_MAIN.search(than)
        if dau is None:
            return than
        con = than[dau.end() :]
        duoi = _DUOI_KHUNG.search(con)
        if duoi is None:
            return than
        than = con[: duoi.start()]


def wrap_page(html: str, current: str) -> str:
    mo = _MO_BODY.search(html)
    if not mo or not _DONG_BODY.search(html):
        return html
    html = _DOCK_KICH_BAN.sub("", _DOCK_CU.sub("", html))
    mo = _MO_BODY.search(html)
    if mo is None:
        return html
    dau = html[: mo.end()]
    cuoi_vt = _DONG_BODY.search(html)
    if cuoi_vt is None:
        return html
    than = _go_khung(html[mo.end() : cuoi_vt.start()])
    than = re.sub(r"<(/?)main\b", r"<\1div", than, flags=re.I)
    duoi = html[cuoi_vt.start() :]
    khung = (
        rail_html(current)
        + panel_html(current)
        + '<div class="app-scrim" id="app-scrim" hidden></div>'
        + header_html(current)
        + global_search_html()
        + '<main class="app-main" id="app-main">'
        + than
        + "</main>"
        + '<script src="assets/app-shell.js" defer></script>'
    )
    return dau + khung + duoi
