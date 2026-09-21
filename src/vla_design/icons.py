from __future__ import annotations

"""Bộ icon SVG nội tuyến của VLA — MỘT họ duy nhất, không thư viện ngoài.

Vì sao tự vẽ thay vì nạp một bộ icon: mục XVIII.8 của spec cấm tăng phụ thuộc
không kiểm soát, và mọi bộ icon qua CDN đều đụng CSP ``'self'`` mà bộ kiểm của
kho đang đòi. Mười bốn hình cho hai mươi chín trang là vừa đủ, và tự vẽ thì
nét, kích thước, canh dọc chắc chắn đồng nhất — đúng ba thứ mục 4.5 đòi.

Mọi hình dùng cùng một quy ước: khung nhìn 24×24, nét 1,75, đầu và góc nét
tròn, tô bằng ``currentColor`` nên icon tự đổi màu theo chữ quanh nó thay vì
phải khai màu riêng cho từng chủ đề.
"""

from typing import Final

ICON_VIEWBOX: Final[str] = "0 0 24 24"
ICON_STROKE_WIDTH: Final[str] = "1.75"

#: Đường nét của từng hình. Chỉ phần ``<path>``/``<circle>`` bên trong, vì
#: thuộc tính chung do ``icon()`` gắn — khai lặp lại ở từng hình là cách nhanh
#: nhất để nét của một hình lệch khỏi phần còn lại.
_PATHS: Final[dict[str, str]] = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5.25 9.75V20.25h13.5V9.75"/><path d="M9.75 20.25v-6h4.5v6"/>',
    "dashboard": '<path d="M3.75 3.75h6.75v6.75H3.75zM13.5 3.75h6.75v4.5H13.5zM13.5 11.25h6.75v9H13.5zM3.75 13.5h6.75v6.75H3.75z"/>',
    "chart": '<path d="M3.75 20.25h16.5"/><path d="M6.75 20.25V12M11.25 20.25V6.75M15.75 20.25v-6M20.25 20.25V9.75"/>',
    "live": '<circle cx="12" cy="12" r="2.25"/><path d="M7.4 7.4a6.5 6.5 0 0 0 0 9.2M16.6 16.6a6.5 6.5 0 0 0 0-9.2"/><path d="M4.6 4.6a10.4 10.4 0 0 0 0 14.8M19.4 19.4a10.4 10.4 0 0 0 0-14.8"/>',
    "book": '<path d="M4.5 4.5h6a2.25 2.25 0 0 1 2.25 2.25V21a1.5 1.5 0 0 0-1.5-1.5H4.5z"/><path d="M19.5 4.5h-6a2.25 2.25 0 0 0-2.25 2.25V21a1.5 1.5 0 0 1 1.5-1.5h6.75z"/>',
    "star": '<path d="m12 3.75 2.55 5.17 5.7.83-4.13 4.02.98 5.68L12 16.77l-5.1 2.68.98-5.68L3.75 9.75l5.7-.83z"/>',
    "grid": '<path d="M3.75 3.75h16.5v16.5H3.75z"/><path d="M9.25 3.75v16.5M14.75 3.75v16.5M3.75 9.25h16.5M3.75 14.75h16.5"/>',
    "calendar": '<path d="M4.5 6h15v13.5h-15z"/><path d="M4.5 10.5h15M8.25 3.75V6M15.75 3.75V6"/>',
    "cycle": '<path d="M20.25 12a8.25 8.25 0 1 1-2.42-5.83"/><path d="M20.25 3.75V7.5h-3.75"/>',
    "sigma": '<path d="M17.25 5.25H6.75L12 12l-5.25 6.75h10.5"/>',
    "brain": '<path d="M12 5.25a3 3 0 0 0-5.63 1.02A2.63 2.63 0 0 0 5.25 12a2.63 2.63 0 0 0 1.5 4.73A3 3 0 0 0 12 18.75z"/><path d="M12 5.25a3 3 0 0 1 5.63 1.02A2.63 2.63 0 0 1 18.75 12a2.63 2.63 0 0 1-1.5 4.73A3 3 0 0 1 12 18.75z"/><path d="M12 5.25v13.5"/>',
    "route": '<circle cx="6" cy="6" r="2.25"/><circle cx="18" cy="18" r="2.25"/><path d="M8.25 6h4.5a3 3 0 0 1 3 3v6"/>',
    "flask": '<path d="M9.75 3.75h4.5v4.19l4.13 8.26A2.25 2.25 0 0 1 16.37 19.5H7.63a2.25 2.25 0 0 1-2.01-3.3l4.13-8.26z"/><path d="M6.9 13.5h10.2"/>',
    "gauge": '<path d="M20.25 15a8.25 8.25 0 1 0-16.5 0"/><path d="M12 15l4.13-4.13"/><circle cx="12" cy="15" r="1.13"/>',
    "sun": '<circle cx="12" cy="12" r="4.13"/><path d="M12 2.25v2.25M12 19.5v2.25M2.25 12H4.5M19.5 12h2.25M5.11 5.11l1.59 1.59M17.3 17.3l1.59 1.59M18.89 5.11 17.3 6.7M6.7 17.3 5.11 18.89"/>',
    "moon": '<path d="M20.25 14.62A8.63 8.63 0 0 1 9.38 3.75a8.63 8.63 0 1 0 10.87 10.87z"/>',
    "monitor": '<path d="M3.75 5.25h16.5v10.5H3.75z"/><path d="M8.25 20.25h7.5M12 15.75v4.5"/>',
    "menu": '<path d="M4.5 7.5h15M4.5 12h15M4.5 16.5h15"/>',
    "close": '<path d="m6.75 6.75 10.5 10.5M17.25 6.75 6.75 17.25"/>',
    "chevron": '<path d="m9 6.75 5.25 5.25L9 17.25"/>',
    "search": '<circle cx="10.88" cy="10.88" r="6.38"/><path d="m15.75 15.75 3.75 3.75"/>',
}

ICON_NAMES: Final[tuple[str, ...]] = tuple(sorted(_PATHS))


def icon(name: str, *, size: int = 20, extra_class: str = "") -> str:
    """Một icon SVG nội tuyến, đã ẩn khỏi trình đọc màn hình.

    ``aria-hidden="true"`` và ``focusable="false"`` là bắt buộc, không phải
    trang trí: icon ở đây luôn đi kèm nhãn chữ, nên để trình đọc màn hình đọc
    nó nữa là đọc lặp. ``focusable="false"`` chặn riêng lỗi của IE/Edge cũ vốn
    cho SVG vào chuỗi Tab.

    Args:
        name: Tên hình, phải có trong ``ICON_NAMES``.
        size: Cạnh vuông, tính bằng pixel.
        extra_class: Lớp CSS thêm vào.

    Returns:
        Chuỗi ``<svg>`` đã đủ thuộc tính.

    Raises:
        KeyError: Khi tên hình không tồn tại. Ném lỗi thay vì trả ô trống, vì
            một icon thiếu lặng lẽ là thứ không ai phát hiện khi duyệt trang.
    """
    if name not in _PATHS:
        raise KeyError(f"không có icon {name!r}; có: {', '.join(ICON_NAMES)}")
    classes = f"vla-icon {extra_class}".strip()
    return (
        f'<svg class="{classes}" width="{size}" height="{size}" '
        f'viewBox="{ICON_VIEWBOX}" fill="none" stroke="currentColor" '
        f'stroke-width="{ICON_STROKE_WIDTH}" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true" focusable="false">'
        f"{_PATHS[name]}</svg>"
    )
