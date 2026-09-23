"""Bộ biểu tượng nét, vẽ tay, theo số đo của trang tham chiếu.

Vì sao có tệp này: bản trước dùng 27 KÝ TỰ UNICODE rời rạc làm biểu tượng —
``◉ ▤ ▦ ⟋ ⚗ 🎯 🔁 ① ② Σ``. Chúng đến từ nhiều khối Unicode khác nhau nên lệch
nhau về nét, cỡ và đường chân chữ, lại do PHÔNG HỆ THỐNG vẽ nên mỗi máy một
khác. Không có cách nào làm chúng nhất quán, vì chúng chưa bao giờ là một bộ.

Số đo lấy từ trang tham chiếu qua runner Actions
(``scripts/inspect_reference_icons.py``), đo trên trình duyệt thật:

    hộp             18x18, viewBox "0 0 20 20"
    nét             stroke-width 1px, fill none
    kiểu            bo tròn
    màu biểu tượng  rgb(105,105,129)
    màu chữ         rgb(12,36,60)
    mục menu        cao 38px, bo 8px, cách chữ 10px, chữ 14px/500

Trang tham chiếu dùng CẢ HAI lối: một phông biểu tượng thương mại
(``uicons-regular-rounded``) và SVG nội tuyến một đường vẽ. Ở đây dựng theo
lối SVG — đúng lối thứ hai của họ — vì CSP của kho đặt ``font-src 'self'``
nên không nạp được phông ngoài, và vì kho không bê tệp của họ về.

Đường vẽ dưới đây là VẼ TAY trên lưới 20x20, không chép từ bộ nào.
"""

from __future__ import annotations

from typing import Final

#: Cạnh hộp hiển thị, tính bằng pixel. Số đo của trang tham chiếu.
CO_HOP: Final[int] = 18
#: Lưới toạ độ của đường vẽ. Mọi đường dưới đây nằm trong ô 20x20.
LUOI: Final[str] = "0 0 20 20"
#: Độ dày nét. Số đo của trang tham chiếu.
NET: Final[str] = "1"

#: Đường vẽ cho từng ẩn dụ, trên lưới 20x20.
#:
#: Quy ước giữ cho cả bộ nhìn như một bộ: chỉ dùng nét, không tô; bám lưới
#: chẵn; chừa lề 2.5 quanh mép; góc bo bằng ``rx``/cung tròn thay vì góc nhọn.
DUONG_VE: Final[dict[str, tuple[str, ...]]] = {
    # --- Trực tiếp -----------------------------------------------------------
    "truc-tiep": (
        "M10 8.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3z",
        "M6.8 6.8a4.5 4.5 0 0 0 0 6.4M13.2 6.8a4.5 4.5 0 0 1 0 6.4",
        "M4.6 4.6a7.6 7.6 0 0 0 0 10.8M15.4 4.6a7.6 7.6 0 0 1 0 10.8",
    ),
    "hom-nay": (
        "M4 6.5a1.5 1.5 0 0 1 1.5-1.5h9A1.5 1.5 0 0 1 16 6.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 4 15.5z",
        "M4 8.8h12M7 3.2v3.2M13 3.2v3.2",
        "M10 12.4h.01",
    ),
    "so-ket-qua": (
        "M5 3.8h8.2A1.8 1.8 0 0 1 15 5.6v10.6a1.8 1.8 0 0 0-1.8-1.8H5z",
        "M5 3.8A1.2 1.2 0 0 0 3.8 5v11a1.2 1.2 0 0 0 1.2 1.2h8.2",
        "M7.2 7.4h5M7.2 10.2h5",
    ),
    # --- Thống kê ------------------------------------------------------------
    "ma-tran": (
        "M3.6 4.6a1 1 0 0 1 1-1h3.2a1 1 0 0 1 1 1v3.2a1 1 0 0 1-1 1H4.6a1 1 0 0 1-1-1z",
        "M11.2 4.6a1 1 0 0 1 1-1h3.2a1 1 0 0 1 1 1v3.2a1 1 0 0 1-1 1h-3.2a1 1 0 0 1-1-1z",
        "M3.6 12.2a1 1 0 0 1 1-1h3.2a1 1 0 0 1 1 1v3.2a1 1 0 0 1-1 1H4.6a1 1 0 0 1-1-1z",
        "M11.2 12.2a1 1 0 0 1 1-1h3.2a1 1 0 0 1 1 1v3.2a1 1 0 0 1-1 1h-3.2a1 1 0 0 1-1-1z",
    ),
    "tan-suat": (
        "M3.5 16.4h13",
        "M5.8 16.4v-4.2M9.2 16.4V7.6M12.6 16.4v-6.4M16 16.4V5.2",
    ),
    "gan-nhip": (
        "M10 3.6a6.4 6.4 0 1 0 0 12.8 6.4 6.4 0 0 0 0-12.8z",
        "M10 6.6V10l2.4 1.6",
    ),
    "cap-lon": (
        "M7.2 4.4v11.2M7.2 4.4 4.8 6.9M7.2 4.4l2.4 2.5",
        "M12.8 15.6V4.4M12.8 15.6l-2.4-2.5M12.8 15.6l2.4-2.5",
    ),
    # --- Cầu kèo -------------------------------------------------------------
    "cau-chay": (
        "M3.6 14.4 7.4 10l3 2.6 5.4-6",
        "M12.6 4.6h3.6v3.6",
        "M3.6 16.4h12.8",
    ),
    "cau-on-dinh": (
        "M3.6 10.4h3.2l1.8-3.2 2.4 6 1.8-2.8h3.6",
        "M3.6 16.4h12.8",
    ),
    "cau-de-chay": (
        "M3.6 6.4 7.4 10.8l3-2.6 5.4 6",
        "M12.6 15.4h3.6v-3.6",
        "M3.6 3.6h12.8",
    ),
    "cau-de-on-dinh": (
        "M3.6 9.6h12.8",
        "M6.2 6.4v6.4M10 5.2v9.6M13.8 6.4v6.4",
    ),
    "vi-tri-cau": (
        "M3.8 3.8h12.4v12.4H3.8z",
        "M3.8 8h12.4M3.8 12h12.4M8 3.8v12.4M12 3.8v12.4",
    ),
    # --- Phỏng đoán ----------------------------------------------------------
    "ai-ml": (
        "M6.4 6.4h7.2v7.2H6.4z",
        "M8.2 2.8v3.6M11.8 2.8v3.6M8.2 13.6v3.6M11.8 13.6v3.6",
        "M2.8 8.2h3.6M2.8 11.8h3.6M13.6 8.2h3.6M13.6 11.8h3.6",
    ),
    "top-loto": (
        "M3.6 5.4h8.4M3.6 10h8.4M3.6 14.6h5.4",
        "M14.6 12.6 16.4 14.4l-1.8 1.8",
        "M16.4 14.4h-3.6",
    ),
    "top-de": (
        "M3.6 5.4h8.4M3.6 10h8.4M3.6 14.6h5.4",
        "M14.8 4.2a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
        "M14.8 8.2v3.4",
    ),
    "chat-luong": (
        "M10 3.2 15.6 5.4v4.2c0 3.4-2.3 6-5.6 7.2-3.3-1.2-5.6-3.8-5.6-7.2V5.4z",
        "M7.6 9.8 9.4 11.6l3-3.2",
    ),
    # --- Bảng Đặc Biệt -------------------------------------------------------
    "theo-ngay": (
        "M4 6.5a1.5 1.5 0 0 1 1.5-1.5h9A1.5 1.5 0 0 1 16 6.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 4 15.5z",
        "M4 8.8h12M7 3.2v3.2M13 3.2v3.2",
        "M7.2 11.6h2v2h-2z",
    ),
    "theo-thang": (
        "M4 6.5a1.5 1.5 0 0 1 1.5-1.5h9A1.5 1.5 0 0 1 16 6.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 4 15.5z",
        "M4 8.8h12M7 3.2v3.2M13 3.2v3.2",
        "M6.6 11.4h2M11.4 11.4h2M6.6 14.2h2M11.4 14.2h2",
    ),
    "theo-nam": (
        "M4 6.5a1.5 1.5 0 0 1 1.5-1.5h9A1.5 1.5 0 0 1 16 6.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 4 15.5z",
        "M4 8.8h12M7 3.2v3.2M13 3.2v3.2",
        "M6.4 11.6h7.2M6.4 14h4.4",
    ),
    "chu-ky": (
        "M16.2 10a6.2 6.2 0 1 1-1.9-4.5",
        "M16.4 3.4v3.4h-3.4",
    ),
    "bo-so": (
        "M8 5.6a4.4 4.4 0 1 0 0 8.8 4.4 4.4 0 0 0 0-8.8z",
        "M12 5.6a4.4 4.4 0 1 1 0 8.8",
    ),
    "ngay-mai": (
        "M4 6.5a1.5 1.5 0 0 1 1.5-1.5h9A1.5 1.5 0 0 1 16 6.5v9a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 4 15.5z",
        "M4 8.8h12M7 3.2v3.2M13 3.2v3.2",
        "M7.6 13h4.8M10.4 11l2 2-2 2",
    ),
    # --- LOTO chi tiết -------------------------------------------------------
    "cap-loto": (
        "M7.2 6.4a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2z",
        "M12.8 6.4a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2z",
    ),
    "cap-lon-loto": (
        "M4 7.4h9.4a2.6 2.6 0 0 1 0 5.2H4",
        "M6.4 5 4 7.4l2.4 2.4",
        "M13.6 10.2 16 12.6l-2.4 2.4",
    ),
    "cau-giai-db": (
        "M10 3.8a6.2 6.2 0 1 0 0 12.4 6.2 6.2 0 0 0 0-12.4z",
        "M10 7.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6z",
        "M10 1.8v2.4M10 15.8v2.4M1.8 10h2.4M15.8 10h2.4",
    ),
    "theo-tong": (
        "M10 3.6a6.4 6.4 0 1 0 0 12.8 6.4 6.4 0 0 0 0-12.8z",
        "M10 6.8v6.4M6.8 10h6.4",
    ),
    "dau-duoi": (
        "M3.8 4.6h12.4v10.8H3.8z",
        "M10 4.6v10.8",
        "M6 9.2h1.6M12.4 11h1.6",
    ),
    "lo-gan": (
        "M6 3.6h8M6 16.4h8",
        "M6.8 3.6v2.6L10 10l-3.2 3.8v2.6M13.2 3.6v2.6L10 10l3.2 3.8v2.6",
    ),
    "tong-hop": (
        "M3.6 4.6a1 1 0 0 1 1-1h10.8a1 1 0 0 1 1 1v2.8a1 1 0 0 1-1 1H4.6a1 1 0 0 1-1-1z",
        "M3.6 11.6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3.8a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1z",
        "M11.4 11.6a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v3.8a1 1 0 0 1-1 1h-3a1 1 0 0 1-1-1z",
    ),
    # --- Tool nâng cao -------------------------------------------------------
    "nghien-cuu": (
        "M8.4 2.8v4.6L4.6 14a1.8 1.8 0 0 0 1.6 2.7h7.6a1.8 1.8 0 0 0 1.6-2.7l-3.8-6.6V2.8",
        "M7.4 2.8h5.2",
        "M6.4 11.6h7.2",
    ),
    "kiem-dinh": (
        "M16.2 10a6.2 6.2 0 1 1-1.9-4.5",
        "M16.4 3.4v3.4h-3.4",
        "M7.6 10.2 9.4 12l3.4-3.6",
    ),
}


def icon_svg(khoa: str, lop: str = "app-ic") -> str:
    """Dựng thẻ ``<svg>`` cho một ẩn dụ.

    Args:
        khoa: Khoá trong :data:`DUONG_VE`.
        lop: Lớp CSS gắn vào thẻ.

    Returns:
        Chuỗi SVG nội tuyến. Khoá lạ trả về hình tròn rỗng thay vì chuỗi
        rỗng: một ô trống nhìn y như lỗi tải, còn hình tròn nói rõ "chưa gán
        biểu tượng cho mục này".
    """
    duong = DUONG_VE.get(khoa) or ("M10 4.4a5.6 5.6 0 1 0 0 11.2 5.6 5.6 0 0 0 0-11.2z",)
    ve = "".join(f'<path d="{d}"/>' for d in duong)
    return (
        f'<svg class="{lop}" viewBox="{LUOI}" width="{CO_HOP}" height="{CO_HOP}"'
        f' fill="none" stroke="currentColor" stroke-width="{NET}"'
        f' stroke-linecap="round" stroke-linejoin="round"'
        f' aria-hidden="true" focusable="false">{ve}</svg>'
    )
