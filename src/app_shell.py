"""Khung ứng dụng dùng chung: hai cấp điều hướng, thanh trên, vùng nội dung.

Dựng theo số đo THẬT của trang tham chiếu mà chủ dự án chọn, lấy bằng
``scripts/inspect_reference_shell.py`` chạy trên runner Actions (proxy môi
trường phát triển chặn trang đó). Các con số dưới đây là đo, không phải ước:

    dải biểu tượng      80px, bóng trong rgba(41,41,75,.05) 0 0 10px
    dải chi tiết        240px (220px ở <=1024), PHỦ LÊN nội dung
    thanh trên          80px, padding-left 80px, viền dưới 1px
    vùng nội dung       margin-left 80px, padding 10px 15px 30px
    mục nav hoạt động   47x46, bo 8px
    nền sáng            #fdfdff trang / #ffffff dải / viền #eeeef3
    nền tối             #282828 trang / #1e1e1e dải / viền rgba(255,255,255,.05)

Điều quan trọng nhất đo được: khi mở dải chi tiết, ``margin-left`` của vùng
nội dung KHÔNG đổi. Dải chi tiết phủ lên nội dung chứ không đẩy nó — nên mở
hay đóng cũng không có một dòng chữ nào phải xếp lại. Bản dựng này giữ đúng
hành vi ấy.

Điều hướng lấy nguyên từ :data:`ui_theme.SITE_NAV` — bảy nhóm, ba mươi hai
mục, tất cả trỏ tới trang có thật. Không nhóm rỗng, không liên kết chết, không
mục bịa.
"""

from __future__ import annotations

import re
from html import escape
from typing import Final

from app_icons import icon_svg
from nexlink_icons import nexlink_icon, navigation_icon
from ui_theme import LANDING_SECTIONS, SITE_NAV, SITE_SEARCH_EXTRAS

#: Bề rộng dải biểu tượng. Số đo của trang tham chiếu, dùng ở cả CSS lẫn JS.
RAIL_W: Final[int] = 80
#: Bề rộng dải chi tiết ở màn rộng và ở màn hẹp.
PANEL_W: Final[int] = 240
PANEL_W_SM: Final[int] = 220
#: Chiều cao thanh trên.
HEADER_H: Final[int] = 80
#: Dưới mốc này, cả hai dải ra ngoài màn và mở ra dưới dạng phủ.
BP_DESKTOP: Final[int] = 1200

#: Nhãn ngắn cho biểu tượng cấp một. ``SITE_NAV`` mang nhãn đầy đủ; dải rộng
#: 80px không chứa nổi "Bảng Đặc Biệt" nên rút gọn RIÊNG cho dải, còn nhãn đầy
#: đủ vẫn hiện ở dải chi tiết và ở thuộc tính title.
NHAN_NGAN: Final[dict[str, str]] = {
    "Trực tiếp": "Trực tiếp",
    "Thống kê": "Thống kê",
    "Cầu kèo": "Cầu kèo",
    "Phỏng đoán": "Dự đoán",
    "Bảng Đặc Biệt": "Đặc Biệt",
    "LOTO chi tiết": "LOTO",
    "Tool nâng cao": "Công cụ",
}


def _trang_chuan(ten_tep: str) -> str:
    """Ba địa chỉ của trang chủ dùng chung một mục điều hướng."""
    return "index.html" if ten_tep in {"landing.html", "landing_desktop.html"} else ten_tep


def _nhom_cua_trang(ten_tep: str) -> int:
    """Chỉ số nhóm chứa trang này; 0 nếu không nhóm nào chứa."""
    ten_tep = _trang_chuan(ten_tep)
    for i, (_, muc) in enumerate(SITE_NAV):
        for href, _, _ in muc:
            if href.split("#", 1)[0] == ten_tep:
                return i
    return 0


def rail_html(current: str) -> str:
    """All eleven reference rail icons, in the original groups and order."""
    active = _nhom_cua_trang(current)
    parts = [
        '<aside class="app-rail" id="app-rail" aria-label="Nhóm chức năng">',
        '<div class="app-rail-list" role="tablist" aria-orientation="vertical">',
    ]
    # Seven existing groups plus two useful direct links occupy the nine slots.
    for position, (group, icon) in enumerate([(0, 'home'), (1, 'crown'), (2, 'layers'),
                                            (3, 'circles'), (4, 'components'),
                                            (6, 'code'), (5, 'clipboard')]):
        if position in (3, 5):
            parts.append('<span class="app-rail-divider" role="presentation"></span>')
        label = SITE_NAV[group][0]
        selected = 'true' if group == active else 'false'
        parts.append(
            f'<button class="app-rail-btn" role="tab" type="button" id="app-tab-{group}"'
            f' aria-controls="app-panel-{group}" aria-selected="{selected}"'
            f' data-app-group="{group}" title="{escape(label, quote=True)}">'
            f'<span class="app-rail-ic">{nexlink_icon(icon)}</span>'
            f'<span class="app-rail-lb">{escape(label)}</span></button>'
        )
    for icon, href, label in [('chart', 'statistics.html', 'Ma trận thống kê'),
                              ('robot', 'dashboard.html', 'Bảng điều khiển AI/ML')]:
        parts.append(f'<a class="app-rail-link" href="{href}" title="{label}" aria-label="{label}">'
                     f'{nexlink_icon(icon)}' + ('<span class="app-status-dot" aria-hidden="true"></span>' if icon == 'robot' else '') + '</a>')
    parts.extend([
        '<span class="app-rail-divider" role="presentation"></span>',
        '<button class="app-rail-link app-rail-add" id="app-rail-add" type="button"'
        ' title="Mở chức năng" aria-label="Mở chức năng" aria-haspopup="dialog" aria-controls="app-global-search">'
        + nexlink_icon('plus') + '</button>',
        '<button class="app-rail-link app-rail-exit" id="app-rail-exit" type="button"'
        ' title="Đóng menu" aria-label="Đóng menu">' + nexlink_icon('exit') + '</button>',
        '</div></aside>',
    ])
    return ''.join(parts)


def panel_html(current: str) -> str:
    """Dải chi tiết cấp hai: danh sách mục của nhóm đang chọn."""
    hoat_dong = _nhom_cua_trang(current)
    phan = [
        '<div class="app-panel" id="app-panel" aria-label="Chức năng trong nhóm">',
        '<div class="app-panel-head"><span class="app-panel-title" id="app-panel-title">'
        f"{escape(SITE_NAV[hoat_dong][0])}</span></div>",
        '<div class="app-panel-search">'
        '<input type="search" id="app-sidebar-filter" class="app-search-input"'
        ' placeholder="Lọc trong nhóm…" autocomplete="off"'
        ' aria-label="Lọc chức năng trong nhóm đang chọn">'
        '<p class="app-search-empty" id="app-sidebar-filter-empty" role="status" hidden>'
        'Không có chức năng nào khớp trong nhóm.</p>'
        "</div>",
    ]
    for i, (_ten, muc) in enumerate(SITE_NAV):
        an = "" if i == hoat_dong else " hidden"
        phan.append(
            f'<nav class="app-panel-group" id="app-panel-{i}" role="tabpanel"'
            f' aria-labelledby="app-tab-{i}" data-app-group="{i}"{an}>'
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
    """Nexlink header layout, exact original vectors, real application actions."""
    group = escape(SITE_NAV[_nhom_cua_trang(current)][0])
    page = next((label for _, items in SITE_NAV for href, label, _ in items
                 if href == _trang_chuan(current)), 'Tổng quan')
    count = len({href for _, items in SITE_NAV for href, _, _ in items})
    return (
        '<header class="app-header" id="app-header">'
        '<a class="app-rail-brand" href="index.html" title="Vietnam Lottery Analysis" aria-label="Vietnam Lottery Analysis">'
        + nexlink_icon('brand', 'app-brand-icon') + '</a>'
        '<div class="app-header-inner">'
        '<button class="app-icon-btn app-toggle" id="app-toggle" type="button"'
        ' aria-expanded="false" aria-controls="app-panel" title="Mở/đóng menu chi tiết">'
        + nexlink_icon('chevrons') + '<span class="app-sr">Mở hoặc đóng menu chi tiết</span></button>'
        '<div class="app-header-start">'
        '<button class="app-search-trigger" id="app-search-open" type="button"'
        ' aria-haspopup="dialog" aria-controls="app-global-search" title="Tìm chức năng (Ctrl K)">'
        + nexlink_icon('search') + '<span>Tìm kiếm chức năng…</span></button>'
        f'<a class="app-header-badge" href="statistics.html">Chức năng phân tích<span>{count}</span></a>'
        '</div>'
        '<nav class="app-crumbs app-sr" aria-label="Đường dẫn">'
        f'<span class="app-crumb">{group}</span><span aria-hidden="true"> / </span>'
        f'<span class="app-crumb app-crumb--now">{escape(page)}</span></nav>'
        '<div class="app-header-end">'
        '<div class="app-theme-wrap"><button class="app-theme-switch" id="app-theme" type="button" title="Đổi chế độ màu">'
        '<span class="app-theme-ic" aria-hidden="true">'
        + nexlink_icon('sun', 'app-nexlink-ic app-theme-sun')
        + nexlink_icon('moon', 'app-nexlink-ic app-theme-moon') + '</span>'
        '<span class="app-sr">Đổi chế độ màu</span></button></div>'
        '<span class="app-header-divider" aria-hidden="true"></span>'
        '<div class="app-header-tools">'
        '<a class="app-icon-btn" href="live.html" title="Kết quả trực tiếp" aria-label="Kết quả trực tiếp">'
        + nexlink_icon('inbox') + '<span class="app-status-dot" aria-hidden="true"></span></a>'
        '<div class="app-dropdown">'
        '<button class="app-icon-btn" id="app-notifications-toggle" type="button"'
        ' aria-expanded="false" aria-controls="app-notifications-menu" title="Cập nhật" aria-label="Cập nhật">'
        + nexlink_icon('bell') + '</button>'
        '<div class="app-dropdown-menu app-notifications-menu" id="app-notifications-menu" hidden>'
        '<h2>Cập nhật</h2>'
        '<a href="index.html#ket-qua">' + nexlink_icon('inbox') + '<span>Kết quả mới nhất<small>Xem bảng kết quả theo giải</small></span></a>'
        '<a href="model-quality.html">' + nexlink_icon('clipboard') + '<span>Chất lượng mô hình<small>Kiểm tra dữ liệu và độ chính xác</small></span></a>'
        '<a href="index.html#backtest">' + nexlink_icon('chart') + '<span>Kiểm định AI/ML<small>Đối chiếu với kết quả lịch sử</small></span></a>'
        '</div></div>'
        '<a class="app-icon-btn app-calendar-link" href="so-ket-qua-truyen-thong.html" title="Sổ kết quả" aria-label="Sổ kết quả">'
        + nexlink_icon('calendar') + '</a></div>'
        '<span class="app-header-divider" aria-hidden="true"></span>'
        '<div class="app-dropdown app-profile">'
        '<button class="app-profile-toggle" id="app-profile-toggle" type="button"'
        ' aria-expanded="false" aria-controls="app-profile-menu" aria-label="Menu ứng dụng">'
        '<span class="app-profile-copy"><strong>Vietnam Lottery</strong><small>'
        + nexlink_icon('angle-down') + ' Analysis</small></span>'
        '<span class="app-avatar"><img src="assets/app-avatar.webp" alt="" width="40" height="40"></span></button>'
        '<div class="app-dropdown-menu app-profile-menu" id="app-profile-menu" hidden>'
        '<a href="index.html">' + nexlink_icon('house-blank') + 'Trang tổng quan</a>'
        '<a href="dashboard.html">' + nexlink_icon('circle-user') + 'Bảng điều khiển AI/ML</a>'
        '<a href="model-quality.html">' + nexlink_icon('review') + 'Chất lượng mô hình</a>'
        '<button id="app-fullscreen" type="button" title="Toàn màn hình" aria-label="Toàn màn hình">'
        + nexlink_icon('arrows') + '<span>Toàn màn hình</span></button>'
        '<a href="research-lab.html">' + nexlink_icon('sliders-h-square') + 'Công cụ nghiên cứu</a>'
        '</div></div></div></div></header>'
    )


def global_search_html() -> str:
    """Tìm kiếm toàn ứng dụng lấy đích thật, độc lập danh sách của sidebar."""
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


#: Dock cũ: thanh nổi ở chân trang. Khung mới thay hẳn vai trò của nó, nên gỡ
#: đi — để lại thì hai bộ điều hướng cùng tồn tại và cùng đòi cùng một chỗ.
_DOCK_CU = re.compile(
    r"<nav\b(?=[^>]*\bclass=[\"'][^\"']*\b(?:ui-dock|dock)\b)[^>]*>.*?</nav>\s*",
    re.S | re.I,
)
#: Kịch bản đi kèm dock — ``ui_theme.dock`` trả về ``<nav>`` rồi NGAY SAU là
#: thẻ này. Gỡ nav mà để lại nó thì ta có mã chết trên mọi trang, và trên
#: ``docs/live.html`` còn tệ hơn: thẻ mồ côi đứng SAU đuôi khung nên
#: :data:`_DUOI_KHUNG` (neo ở cuối phần thân) trượt, bước bóc bỏ cuộc, và mỗi
#: lượt pipeline bọc thêm một lớp — đo được 11 lớp sau một ngày.
#: Chỉ khớp chữ ký handler cũ của cả hai dock, không nuốt kịch bản nghiệp vụ
#: đứng ngay sau nav hoặc chỉ nhắc tên lớp dock.
_DOCK_KICH_BAN = re.compile(
    r"<script>\s*\(function\(\)\{var d=document\.querySelector\([\"']\.(?:ui-)?dock[\"']\);if\(!d\)return;"
    r".*?</script>\s*",
    re.S | re.I,
)
#: Nhận cả main và div: khung cũ đổi main lồng nhau thành div. Lượt chuẩn hoá
#: HTML còn đổi thứ tự thuộc tính và dấu nháy, nên không khớp chuỗi cố định.
_MO_MAIN = re.compile(
    r"<(?:main|div)\b(?=[^>]*\bid=[\"']app-main[\"'])(?=[^>]*\bclass=[\"'][^\"']*\bapp-main\b)[^>]*>",
    re.I,
)
#: Đuôi khung: đóng vùng nội dung rồi tới thẻ kịch bản, luôn ở CUỐI phần thân.
#:
#: KHÔNG khớp nguyên văn chuỗi mà :func:`wrap_page` sinh ra. Trang đã xuất bản
#: đi qua một lượt chuẩn hoá HTML sắp lại thuộc tính theo thứ tự chữ cái, nên
#: `<script src="…" defer>` quay lại thành `<script defer="" src="…">`. Bản
#: đầu của tôi khớp nguyên văn và vì thế trượt trên chính những tệp cần bóc:
#: index, landing, landing_desktop và live đều bị bọc thành HAI lớp. Đo được
#: bằng cách đếm `class="app-rail"` mỗi trang — phải đúng bằng 1.
#: Thẻ kịch bản là TUỲ CHỌN. Lớp khung phía trong của ``docs/live.html`` có
#: hai ``</main>`` nhưng chỉ một thẻ script — lượt chuẩn hoá gộp hai thẻ
#: ``src`` trùng nhau lại làm một. Bản đòi script bắt buộc vì thế bỏ cuộc ở
#: đúng tệp duy nhất cần bóc, rồi bọc thêm lớp nữa.
_DUOI_KHUNG: Final[re.Pattern[str]] = re.compile(
    r"</(?:main|div)>\s*(?:<script\b[^>]*\bsrc=\"assets/app-shell\.js\"[^>]*>\s*</script>\s*)?\Z"
)
_MO_BODY = re.compile(r"(<body\b[^>]*>)", re.I)
_DONG_BODY = re.compile(r"</body\s*>", re.I)


def _go_khung(than: str) -> str:
    """Bóc MỌI lớp khung đang có ra khỏi phần thân, trả lại nội dung gốc.

    Không có hàm này thì khung chỉ CỘNG THÊM. Đã xảy ra thật:
    ``docs/live.html`` là trang duy nhất viết tay và commit thẳng, nên mỗi
    lượt dựng đọc lại chính bản đã có khung rồi bọc tiếp — tệp kết thúc với
    hai ``.app-rail``, hai ``.app-header``, hai ``.app-main`` lồng nhau. Hệ
    quả nhìn thấy được, đo bằng ``elementFromPoint``: chữ thương hiệu của
    khung NGOÀI nằm đúng trên nút tab đầu của dải TRONG, nên mục điều hướng
    đầu tiên bấm không ăn.

    Chốt chặn cũ là ``if "app-rail" in html: return html``. Nó ngăn được lần
    bọc thứ hai nhưng KHÔNG sửa được tệp đã hỏng, và nó im lặng giữ nguyên
    một khung cũ đã lệch khỏi :data:`SITE_NAV`. Bóc rồi bọc lại thì cả hai
    vấn đề biến mất cùng lúc.

    Args:
        than: Nội dung giữa hai thẻ ``<body>``.

    Returns:
        Phần nội dung thật, đã bỏ hết lớp khung.
    """
    # Mỗi vòng cắt cả đầu và đuôi, nên chuỗi ngắn dần và không thể treo.
    # Không đặt trần khiến trang tích luỹ nhiều lớp vẫn còn khung lồng nhau.
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
    """Bọc một trang đã dựng vào khung dùng chung.

    Chỉ BỌC, không sửa gì bên trong: nội dung phân tích của từng trang đi
    nguyên vẹn vào ``<main class="app-main">``. Đây là điều kiện để khung mới
    không đụng tới bảng số, ma trận hay thứ tự khối nào.

    Args:
        html: Trang hoàn chỉnh đã dựng.
        current: Tên tệp của trang, để đánh dấu mục điều hướng đang mở.

    Returns:
        Trang đã bọc, hoặc nguyên trạng nếu nó không phải tài liệu đủ thẻ.
    """
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
    # Bóc trước, bọc sau. Gọi hàm này nhiều lần cho cùng một kết quả, và một
    # trang đã bị bọc chồng sẽ được SỬA chứ không chỉ được để yên.
    than = _go_khung(html[mo.end() : cuoi_vt.start()])
    # Mỗi tài liệu chỉ có một mốc main; giữ nguyên id/lớp và nội dung con.
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
