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

from ui_theme import SITE_NAV

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


def _nhom_cua_trang(ten_tep: str) -> int:
    """Chỉ số nhóm chứa trang này; 0 nếu không nhóm nào chứa."""
    for i, (_, muc) in enumerate(SITE_NAV):
        for href, _, _ in muc:
            if href.split("#", 1)[0] == ten_tep:
                return i
    return 0


def rail_html(current: str) -> str:
    """Dải biểu tượng cấp một: một nút cho mỗi nhóm của ``SITE_NAV``."""
    hoat_dong = _nhom_cua_trang(current)
    phan = [
        f'<aside class="app-rail" id="app-rail" aria-label="Nhóm chức năng">',
        '<div class="app-rail-list" role="tablist" aria-orientation="vertical">',
    ]
    for i, (ten, muc) in enumerate(SITE_NAV):
        bieu_tuong = muc[0][2] if muc else "◆"
        chon = "true" if i == hoat_dong else "false"
        phan.append(
            f'<button class="app-rail-btn" role="tab" type="button"'
            f' id="app-tab-{i}" aria-controls="app-panel-{i}" aria-selected="{chon}"'
            f' data-app-group="{i}" title="{escape(ten, quote=True)}">'
            f'<span class="app-rail-ic" aria-hidden="true">{escape(bieu_tuong)}</span>'
            f'<span class="app-rail-lb">{escape(NHAN_NGAN.get(ten, ten))}</span>'
            f"</button>"
        )
    phan.append("</div></aside>")
    return "".join(phan)


def panel_html(current: str) -> str:
    """Dải chi tiết cấp hai: danh sách mục của nhóm đang chọn."""
    hoat_dong = _nhom_cua_trang(current)
    phan = [
        '<div class="app-panel" id="app-panel" aria-label="Chức năng trong nhóm">',
        '<div class="app-panel-head"><span class="app-panel-title" id="app-panel-title">'
        f"{escape(SITE_NAV[hoat_dong][0])}</span></div>",
        '<div class="app-panel-search">'
        '<input type="search" id="app-search" class="app-search-input"'
        ' placeholder="Tìm chức năng…" autocomplete="off"'
        ' aria-label="Tìm trang và chức năng">'
        '<p class="app-search-empty" id="app-search-empty" hidden>Không có chức năng nào khớp.</p>'
        "</div>",
    ]
    for i, (ten, muc) in enumerate(SITE_NAV):
        an = "" if i == hoat_dong else " hidden"
        phan.append(
            f'<nav class="app-panel-group" id="app-panel-{i}" role="tabpanel"'
            f' aria-labelledby="app-tab-{i}" data-app-group="{i}"{an}>'
        )
        for href, nhan, bieu_tuong in muc:
            la_trang_nay = href.split("#", 1)[0] == current
            danh_dau = ' aria-current="page"' if la_trang_nay else ""
            lop = " app-nav-item--active" if la_trang_nay else ""
            phan.append(
                f'<a class="app-nav-item{lop}" href="{escape(href, quote=True)}"{danh_dau}'
                f' data-app-label="{escape(nhan, quote=True)}">'
                f'<span class="app-nav-ic" aria-hidden="true">{escape(bieu_tuong)}</span>'
                f'<span class="app-nav-lb">{escape(nhan)}</span></a>'
            )
        phan.append("</nav>")
    phan.append("</div>")
    return "".join(phan)


def header_html(current: str) -> str:
    """Thanh trên: nút thu/mở, đường dẫn, và các điều khiển có việc thật."""
    hoat_dong = _nhom_cua_trang(current)
    nhom = escape(SITE_NAV[hoat_dong][0])
    trang = current
    for _, muc in SITE_NAV:
        for href, nhan, _ in muc:
            if href.split("#", 1)[0] == current:
                trang = nhan
                break
    return (
        '<header class="app-header" id="app-header">'
        '<a class="app-rail-brand" href="index.html" title="Vietnam Lottery Analysis">'
        '<span aria-hidden="true">V</span>'
        '<span class="app-sr">Vietnam Lottery Analysis</span></a>'
        '<button class="app-icon-btn app-toggle" id="app-toggle" type="button"'
        ' aria-expanded="false" aria-controls="app-panel"'
        ' title="Mở/đóng menu chi tiết"><span class="app-burger" aria-hidden="true"></span>'
        '<span class="app-sr">Mở hoặc đóng menu chi tiết</span></button>'
        '<nav class="app-crumbs" aria-label="Đường dẫn">'
        f'<span class="app-crumb">{nhom}</span>'
        '<span class="app-crumb-sep" aria-hidden="true">/</span>'
        f'<span class="app-crumb app-crumb--now">{escape(trang)}</span>'
        "</nav>"
        '<div class="app-header-actions">'
        '<button class="app-icon-btn" id="app-search-open" type="button"'
        ' title="Tìm chức năng"><span aria-hidden="true">⌕</span>'
        '<span class="app-sr">Tìm chức năng</span></button>'
        '<button class="app-icon-btn" id="app-theme" type="button"'
        ' title="Đổi chế độ màu"><span class="app-theme-ic" aria-hidden="true">◐</span>'
        '<span class="app-sr">Đổi chế độ màu</span></button>'
        "</div></header>"
    )


#: Dock cũ: thanh nổi ở chân trang. Khung mới thay hẳn vai trò của nó, nên gỡ
#: đi — để lại thì hai bộ điều hướng cùng tồn tại và cùng đòi cùng một chỗ.
_DOCK_CU = re.compile(r'<nav class="ui-dock".*?</nav>\s*(?:<script>.*?</script>)?', re.S)
_MO_BODY = re.compile(r"(<body\b[^>]*>)", re.I)
_DONG_BODY = re.compile(r"</body\s*>", re.I)


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
    if "app-rail" in html:
        return html
    mo = _MO_BODY.search(html)
    if not mo or not _DONG_BODY.search(html):
        return html
    html = _DOCK_CU.sub("", html)
    mo = _MO_BODY.search(html)
    if mo is None:
        return html
    dau = html[: mo.end()]
    cuoi_vt = _DONG_BODY.search(html)
    if cuoi_vt is None:
        return html
    than = html[mo.end() : cuoi_vt.start()]
    duoi = html[cuoi_vt.start() :]
    khung = (
        rail_html(current)
        + panel_html(current)
        + '<div class="app-scrim" id="app-scrim" hidden></div>'
        + header_html(current)
        + '<main class="app-main" id="app-main">'
        + than
        + "</main>"
        + '<script src="assets/app-shell.js" defer></script>'
    )
    return dau + khung + duoi
