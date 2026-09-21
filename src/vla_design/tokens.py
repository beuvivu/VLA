from __future__ import annotations

"""Token nền tảng của VLA Design System — NGUỒN SỰ THẬT DUY NHẤT.

Mọi màu, thang chữ, thang khoảng cách, bán kính, shadow và thời lượng chuyển
động đều khai ở đây. CSS được SINH RA từ đây, không viết tay song song, để
không lặp lại chuyện cũ: trước đây mỗi trang tự khai màu nên cùng một khái
niệm mang ba giá trị khác nhau.

Điểm quan trọng nhất của tệp này là ``CONTRAST_CONTRACT``: hợp đồng tương phản
là DỮ LIỆU, không phải lời hứa trong tài liệu. Phép kiểm đọc nó và tính lại
từng cặp, nên một màu thêm sau này mà không đạt WCAG là bộ kiểm đỏ ngay, chứ
không chờ ai đó nhớ ra phải đo.
"""

from typing import Final

#: Bảng màu Light Mode.
#:
#: Xuất phát từ bảng chủ dự án cung cấp (mục 4.1 của spec), rồi TINH CHỈNH theo
#: phép đo tương phản thật — spec nói rõ đó là điểm xuất phát, không phải ràng
#: buộc bất biến. Đo trên bảng gốc: 6 trong 15 cặp không đạt WCAG AA.
#:
#: Ba nhóm sửa, và lý do từng nhóm khác nhau:
#:
#: 1. ``text-muted`` gốc ``#94A3B8`` chỉ đạt 2,56:1 trên nền trắng và 2,44:1
#:    trên ``surface-secondary``. Không đạt cho chữ ở mọi kích thước. Làm đậm
#:    tới ``#607491`` (4,77:1 / 4,53:1), giữ nguyên hue và saturation bằng phép
#:    giảm độ sáng trong không gian HLS.
#: 2. ``success``/``warning``/``info``/``accent`` không đạt khi dùng LÀM CHỮ,
#:    nhưng vẫn hợp lệ khi dùng LÀM NỀN. Nên mỗi màu ngữ nghĩa tách thành ba
#:    token: ``-fill`` (màu nguyên bản, dùng làm nền), ``-ink`` (bản đậm đạt
#:    4,5:1, dùng khi chính màu là chữ), ``-soft`` (nền nhạt cho badge).
#:    Đây là câu trả lời đúng của một design system, không phải làm đậm bừa
#:    một giá trị rồi mất luôn màu nền.
#: 3. ``border`` ``#E2E8F0`` chỉ đạt 1,23:1 — nhưng NGƯỠNG 3:1 mà tôi áp lúc
#:    đầu là SAI cho trường hợp này. WCAG 1.4.11 đòi 3:1 cho "thông tin thị
#:    giác cần để nhận dạng thành phần điều khiển và trạng thái của nó", tức
#:    viền ô nhập hay vòng focus — KHÔNG đòi cho một đường kẻ ngăn trang trí.
#:    Nên ``border`` giữ nguyên cho đường kẻ, và thêm ``border-strong``
#:    ``#8794A8`` (3,07:1) cho viền điều khiển.
#:
#: Phép đo "không màu chữ nào đạt": dùng ``info`` hoặc ``accent`` nguyên bản
#: làm nền thì cả chữ trắng (4,10:1 / 4,47:1) lẫn chữ đậm (3,97:1 / 3,64:1)
#: đều thiếu. Nên badge hai màu ấy PHẢI theo mẫu nền nhạt + chữ ink.
#:
#: Lượt giải ``-ink`` đầu tiên của tôi SAI vì chọn sai nền đối chiếu: tôi giải
#: theo ``surface-secondary`` rồi bốn cặp badge vẫn đỏ (4,19-4,33:1), bởi nền
#: ``-soft`` có nhuộm màu nên tối hơn ``surface-secondary``. Giá trị hiện tại
#: giải theo nền CHẶT NHẤT trong cả ba nền mà màu ấy thực sự nằm trên, và
#: giải tới 4,65:1 chứ không phải 4,50:1. Lý do: lượt giải đúng-nhưng-sát cho
#: biên an toàn thấp nhất đúng bằng 1,000x, tức một lần đổi nền badge sau này
#: là hợp đồng đỏ.
#:
#: ``text-secondary`` gốc ``#64748B`` phải làm đậm thành ``#5C6A80``, và nó là
#: ví dụ đắt giá nhất trong tệp này về việc một hợp đồng THIẾU CẶP thì vô
#: dụng. Lượt đo đầu chỉ canh nó trên ``surface`` (4,76:1) và
#: ``surface-secondary`` (4,53:1), nên tôi kết luận "đạt, giữ nguyên giá trị
#: chủ dự án chỉ định". Kết luận ấy SAI: khi hợp đồng được siết để canh mọi
#: token chữ trên MỌI mặt nó nằm lên, cặp ``text-secondary``/``background``
#: hiện ra ở **4,39:1 — không đạt AA**. Chữ phụ trên nền trang là một trong
#: những cặp xuất hiện nhiều nhất của cả sản phẩm, và nó suýt lọt.
#:
#: Giá trị hiện tại giải theo cả bốn mặt (``surface`` 5,49:1,
#: ``surface-secondary`` 5,22:1, ``background`` 5,05:1,
#: ``background-secondary`` 4,67:1).
LIGHT: Final[dict[str, str]] = {
    "primary": "#5941C8",
    "primary-hover": "#4933AF",
    "primary-soft": "#EEEAFE",
    "on-primary": "#FFFFFF",
    "secondary": "#7C3AED",
    "accent-fill": "#6366F1",
    "accent-ink": "#5356F0",
    "accent-soft": "#EEF0FE",
    "background": "#F4F5FF",
    "background-secondary": "#EAECFA",
    "surface": "#FFFFFF",
    "surface-secondary": "#F8F9FE",
    "surface-glass": "rgba(255, 255, 255, 0.72)",
    "text-primary": "#172033",
    "text-secondary": "#5C6A80",
    "text-muted": "#5C708B",
    "border": "#E2E8F0",
    "border-strong": "#8794A8",
    "success-fill": "#16A34A",
    "success-ink": "#117E39",
    "success-soft": "#E7F7ED",
    "warning-fill": "#D97706",
    "warning-ink": "#A55B05",
    "warning-soft": "#FDF3E4",
    "danger-fill": "#DC2626",
    "danger-ink": "#CE2121",
    "danger-soft": "#FCEAEA",
    "info-fill": "#0284C7",
    "info-ink": "#0271AB",
    "info-soft": "#E5F3FB",
    "matrix-miss": "#E2E8F0",
    "matrix-hatch": "rgba(100, 116, 139, 0.16)",
    "focus-ring": "#5941C8",
}

#: Bảng màu Dark Mode.
#:
#: KHÔNG phải phép đảo ngược Light Mode — spec cấm điều đó, và đảo ngược cho ra
#: nền đen tuyệt đối với màu nhấn quá chói trên đó. Ở đây nền là xanh navy sâu
#: (``#0A0D18``) với các mặt nổi dần lên, hướng "premium dark" mà spec gán cho
#: Tapotik AI.
#:
#: Chiều tương phản ĐẢO so với Light Mode, và đó là điều dễ làm sai nhất: trên
#: nền tối, chữ trên một mảng màu nhấn phải là màu NỀN TỐI chứ không phải màu
#: trắng. Đo được: chữ trắng trên ``primary`` ``#9585EE`` chỉ đạt 3,06:1, còn
#: chữ ``#0A0D18`` trên cùng mảng ấy đạt 6,34:1. Cả sáu màu nhấn đều theo
#: chiều này, nên ``on-primary`` của Dark Mode là màu tối.
#:
#: ``border-strong`` ``#5A688B`` chọn bằng cách dò: ``#4A5675`` chỉ đạt 2,37:1
#: trên ``surface``, thiếu ngưỡng 3:1 của viền điều khiển.
DARK: Final[dict[str, str]] = {
    "primary": "#9585EE",
    "primary-hover": "#A797F5",
    "primary-soft": "#221C42",
    "on-primary": "#0A0D18",
    "secondary": "#A97BF5",
    "accent-fill": "#8B8DF7",
    "accent-ink": "#8B8DF7",
    "accent-soft": "#1E2047",
    "background": "#0A0D18",
    "background-secondary": "#111527",
    "surface": "#151A2C",
    "surface-secondary": "#1B2238",
    "surface-glass": "rgba(21, 26, 44, 0.72)",
    "text-primary": "#E9ECF6",
    "text-secondary": "#A6B1C8",
    "text-muted": "#808EA9",
    "border": "#272F47",
    "border-strong": "#5A688B",
    "success-fill": "#4ADE80",
    "success-ink": "#4ADE80",
    "success-soft": "#0F2D1C",
    "warning-fill": "#FBBF24",
    "warning-ink": "#FBBF24",
    "warning-soft": "#33260A",
    "danger-fill": "#F87171",
    "danger-ink": "#F87171",
    "danger-soft": "#341618",
    "info-fill": "#38BDF8",
    "info-ink": "#38BDF8",
    "info-soft": "#0B2A3B",
    "matrix-miss": "#232B41",
    "matrix-hatch": "rgba(166, 177, 200, 0.18)",
    "focus-ring": "#A797F5",
}

#: Hợp đồng tương phản: ``(chữ, nền, tỉ lệ tối thiểu, vì sao)``.
#:
#: Ngưỡng khác nhau theo MỤC ĐÍCH, không đặt một ngưỡng cho tất cả:
#:
#: * 4,5:1 — WCAG 2.2 SC 1.4.3, chữ thường.
#: * 3,0:1 — SC 1.4.11, thành phần phi văn bản: viền điều khiển, vòng focus.
#:
#: Đường kẻ trang trí (``border``) KHÔNG có trong hợp đồng, vì WCAG không đặt
#: ngưỡng cho nó. Đưa nó vào với ngưỡng 3:1 là tự tạo một lỗi không tồn tại —
#: chính sai sót tôi đã mắc ở lần đo đầu.
CONTRAST_CONTRACT: Final[tuple[tuple[str, str, float, str], ...]] = (
    ("text-primary", "surface", 4.5, "chữ chính trên thẻ"),
    ("text-primary", "background", 4.5, "chữ chính trên nền trang"),
    ("text-primary", "surface-secondary", 4.5, "chữ chính trên mặt phụ"),
    ("text-secondary", "surface", 4.5, "chữ phụ trên thẻ"),
    ("text-secondary", "surface-secondary", 4.5, "chữ phụ trên mặt phụ"),
    ("text-secondary", "background", 4.5, "chữ phụ trên nền trang"),
    ("text-muted", "background", 4.5, "chữ mờ trên nền trang"),
    ("text-muted", "surface", 4.5, "chữ mờ trên thẻ"),
    ("text-muted", "surface-secondary", 4.5, "chữ mờ trên mặt phụ"),
    ("primary", "surface", 4.5, "liên kết và nhãn màu chính"),
    ("primary", "background", 4.5, "màu chính trên nền trang"),
    ("primary", "primary-soft", 4.5, "chữ màu chính trên nền nhạt của nó"),
    ("on-primary", "primary", 4.5, "chữ trên nút màu chính"),
    ("on-primary", "primary-hover", 4.5, "chữ trên nút khi hover"),
    ("accent-ink", "surface", 4.5, "màu nhấn dùng làm chữ"),
    ("accent-ink", "accent-soft", 4.5, "chữ nhấn trên nền nhấn nhạt"),
    ("success-ink", "surface", 4.5, "trạng thái tốt dùng làm chữ"),
    ("success-ink", "success-soft", 4.5, "badge trạng thái tốt"),
    ("warning-ink", "surface", 4.5, "cảnh báo dùng làm chữ"),
    ("warning-ink", "warning-soft", 4.5, "badge cảnh báo"),
    ("danger-ink", "surface", 4.5, "lỗi dùng làm chữ"),
    ("danger-ink", "danger-soft", 4.5, "badge lỗi"),
    ("info-ink", "surface", 4.5, "thông tin dùng làm chữ"),
    ("info-ink", "info-soft", 4.5, "badge thông tin"),
    ("border-strong", "surface", 3.0, "viền ô điều khiển — SC 1.4.11"),
    ("focus-ring", "surface", 3.0, "vòng focus — SC 1.4.11"),
    ("focus-ring", "background", 3.0, "vòng focus trên nền trang"),
)

#: Thang chữ. VLA dày dữ liệu nên chữ KHÔNG được to: mỗi pixel chiều cao dòng
#: là một hàng số bị đẩy ra khỏi màn hình. Các mức nằm trong khoảng spec cho.
TYPE_SCALE: Final[dict[str, tuple[str, str, str]]] = {
    "page-title": ("1.75rem", "2.125rem", "650"),
    "section-title": ("1.25rem", "1.75rem", "620"),
    "card-title": ("1rem", "1.5rem", "600"),
    "kpi": ("2rem", "2.375rem", "680"),
    "kpi-sm": ("1.5rem", "1.875rem", "660"),
    "body": ("0.9375rem", "1.4375rem", "400"),
    "body-sm": ("0.875rem", "1.375rem", "400"),
    "table": ("0.8125rem", "1.25rem", "400"),
    "support": ("0.75rem", "1.125rem", "400"),
    "label": ("0.75rem", "1rem", "600"),
}

#: Thang khoảng cách, bội số của bốn. Không có giá trị tuỳ ý.
SPACING: Final[tuple[int, ...]] = (4, 8, 12, 16, 20, 24, 32, 40, 48)

RADII: Final[dict[str, str]] = {
    "sm": "8px",
    "md": "12px",
    "lg": "16px",
    "xl": "20px",
    "pill": "999px",
}

#: Shadow theo TẦNG ĐỘ CAO, không theo trang. Mỗi tầng một mục đích.
SHADOWS: Final[dict[str, dict[str, str]]] = {
    "light": {
        "xs": "0 1px 2px rgba(23, 32, 51, 0.05)",
        "sm": "0 1px 3px rgba(23, 32, 51, 0.07), 0 1px 2px rgba(23, 32, 51, 0.04)",
        "md": "0 4px 12px rgba(23, 32, 51, 0.07), 0 1px 3px rgba(23, 32, 51, 0.04)",
        "lg": "0 12px 28px rgba(23, 32, 51, 0.10), 0 2px 6px rgba(23, 32, 51, 0.05)",
        "focus": "0 0 0 3px rgba(89, 65, 200, 0.28)",
    },
    "dark": {
        "xs": "0 1px 2px rgba(0, 0, 0, 0.32)",
        "sm": "0 1px 3px rgba(0, 0, 0, 0.42), 0 1px 2px rgba(0, 0, 0, 0.28)",
        "md": "0 4px 14px rgba(0, 0, 0, 0.46), 0 1px 3px rgba(0, 0, 0, 0.30)",
        "lg": "0 14px 32px rgba(0, 0, 0, 0.55), 0 2px 8px rgba(0, 0, 0, 0.34)",
        "focus": "0 0 0 3px rgba(167, 151, 245, 0.34)",
    },
}

#: Chuyển động. Ngắn, và mọi thứ ở đây phải bị `prefers-reduced-motion` tắt
#: được. Không có mục nào dài hơn 240ms: trên một trang phân tích, chuyển động
#: dài là chờ đợi chứ không phải phản hồi.
MOTION: Final[dict[str, str]] = {
    "fast": "120ms",
    "base": "180ms",
    "slow": "240ms",
    "ease": "cubic-bezier(0.4, 0, 0.2, 1)",
    "ease-out": "cubic-bezier(0.16, 1, 0.3, 1)",
}


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    """Độ chói tương đối theo WCAG 2.2, từ mã hex ``#RRGGBB``.

    Args:
        color: Mã màu hex, có hoặc không có ``#``.

    Returns:
        Độ chói trong khoảng [0, 1].

    Raises:
        ValueError: Khi màu không phải hex 6 chữ số — ``rgba()`` không tính
            được độ chói mà không biết nền phía dưới, nên nó bị từ chối thẳng
            thay vì trả một con số vô nghĩa.
    """
    text = color.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"cần hex 6 chữ số, nhận {color!r}")
    try:
        r, g, b = (int(text[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError as exc:
        raise ValueError(f"cần hex 6 chữ số, nhận {color!r}") from exc
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(foreground: str, background: str) -> float:
    """Tỉ lệ tương phản WCAG 2.2 giữa hai màu, trong khoảng [1, 21]."""
    a, b = relative_luminance(foreground), relative_luminance(background)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)
