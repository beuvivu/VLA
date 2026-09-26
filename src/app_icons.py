"""Canonical Lucide SVG for page content and global search results.

The rail, expanded navigation and header use exact Nexlink assets through
nexlink_icons.py per the user's updated request on 2026-09-26.
Assets here retain their pinned upstream provenance and ISC/MIT notices.
"""

from __future__ import annotations

from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Final

CO_HOP: Final[int] = 20
LUOI: Final[str] = "0 0 24 24"
NET: Final[str] = "2"
_THU_MUC: Final[Path] = Path(__file__).resolve().parent / "assets" / "icons"

#: Ánh xạ ý nghĩa trong ứng dụng sang tên chính thức ở kho Lucide.
BIEU_TUONG: Final[dict[str, str]] = {
    "tim-kiem": "search",
    "che-do": "sun-moon",
    "toan-man-hinh": "maximize",
    "truc-tiep": "radio",
    "hom-nay": "calendar-check",
    "so-ket-qua": "book-open-text",
    "ma-tran": "grid-2x2",
    "tan-suat": "chart-column",
    "gan-nhip": "clock-3",
    "cap-lon": "arrow-up-down",
    "cau-chay": "trending-up",
    "cau-on-dinh": "activity",
    "cau-de-chay": "route",
    "cau-de-on-dinh": "chart-no-axes-combined",
    "vi-tri-cau": "locate-fixed",
    "ai-ml": "cpu",
    "top-loto": "list-ordered",
    "top-de": "award",
    "chat-luong": "shield-check",
    "theo-ngay": "calendar-days",
    "theo-thang": "calendar-range",
    "theo-nam": "calendar",
    "chu-ky": "repeat-2",
    "bo-so": "layers-2",
    "ngay-mai": "calendar-arrow-up",
    "cap-loto": "link",
    "cap-lon-loto": "repeat",
    "cau-giai-db": "crosshair",
    "theo-tong": "sigma",
    "dau-duoi": "columns-2",
    "lo-gan": "hourglass",
    "tong-hop": "layout-dashboard",
    "nghien-cuu": "flask-conical",
    "kiem-dinh": "clipboard-check",
    "menu": "menu",
    "close": "x",
    "sun": "sun",
    "moon": "moon",
    "settings": "settings",
    "dashboard": "layout-dashboard",
    "menu-toggle": "panel-left",
    "breadcrumb-separator": "chevron-right",
}


@lru_cache(maxsize=None)
def _noi_dung_svg(ten: str) -> str:
    """Đọc nguyên các phần tử hình học của asset đã ghim, chỉ một lần mỗi tên."""
    svg = (_THU_MUC / f"{ten}.svg").read_text(encoding="utf-8")
    return svg.split(">", 1)[1].rsplit("</svg>", 1)[0].strip()


def icon_svg(khoa: str, lop: str = "app-ic") -> str:
    """Dựng SVG 20px; khóa lạ dùng vòng tròn Lucide, không trở thành đường dẫn."""
    ten = BIEU_TUONG.get(khoa, "circle")
    ve = _noi_dung_svg(ten)
    return (
        f'<svg class="{escape(lop, quote=True)}" viewBox="{LUOI}"'
        f' width="{CO_HOP}" height="{CO_HOP}"'
        f' fill="none" stroke="currentColor" stroke-width="{NET}"'
        ' stroke-linecap="round" stroke-linejoin="round"'
        f' aria-hidden="true" focusable="false">{ve}</svg>'
    )
