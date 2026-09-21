from __future__ import annotations

"""Mô hình điều hướng — MỘT nguồn sự thật cho cả 29 trang.

Trước đây mỗi trình dựng tự khai danh sách liên kết của nó, nên thêm một mục
là phải sửa mười một chỗ và bốn trang soi-path đã nằm lệch khỏi phần còn lại.
Ở đây cấu trúc là dữ liệu, sidebar dựng từ nó, và một phép kiểm so danh sách
này với các tệp thật trong ``docs/``.

Quy tắc thuật ngữ của mục IX được áp ở ĐÂY và chỉ ở đây: nhãn hiển thị dùng
"Đặc Biệt", còn tên tệp giữ nguyên ``ml_top10_de.html``, ``soi-path-de-*`` —
tên tệp là URL, đổi nó là làm chết mọi liên kết đã lưu của người đọc.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class NavItem:
    """Một trang trong điều hướng.

    Attributes:
        key: Khoá ổn định, dùng để đánh dấu mục đang mở. KHÔNG dùng tên tệp
            làm khoá, để đổi tên tệp không kéo theo đổi mọi trang.
        href: Tên tệp trong ``docs/``, tức URL thật.
        label: Nhãn hiển thị, tiếng Việt có dấu, đã áp quy tắc "Đặc Biệt".
        summary: Một dòng giải thích, dùng cho ``title`` và trang chủ.
    """

    key: str
    href: str
    label: str
    summary: str


@dataclass(frozen=True)
class NavGroup:
    key: str
    label: str
    icon: str
    items: tuple[NavItem, ...]


NAV: Final[tuple[NavGroup, ...]] = (
    NavGroup(
        key="tong-quan",
        label="Tổng quan",
        icon="home",
        items=(
            NavItem("trang-chu", "index.html", "Trang chủ", "Điểm vào, số liệu nổi bật của kỳ mới nhất"),
            NavItem("bang-dieu-khien", "dashboard.html", "Bảng điều khiển", "Dự đoán kỳ tới, trọng số đang hiệu lực, hiệu chuẩn"),
            NavItem("thong-ke-tong-hop", "thong-ke-tong-hop.html", "Thống kê tổng hợp", "Tổng hợp mọi bảng thống kê trong một trang"),
            NavItem("thong-ke", "statistics.html", "Bảng thống kê", "Ma trận thống kê và tần suất theo nhiều cửa sổ"),
        ),
    ),
    NavGroup(
        key="ket-qua",
        label="Kết quả",
        icon="book",
        items=(
            NavItem("truc-tiep", "live.html", "Trực tiếp", "Kết quả đang về của kỳ hôm nay"),
            NavItem("so-truyen-thong", "so-ket-qua-truyen-thong.html", "Sổ kết quả truyền thống", "Bảng kết quả theo lối sổ giấy, kèm chục và đơn vị"),
        ),
    ),
    NavGroup(
        key="dac-biet",
        label="Đặc Biệt",
        icon="star",
        items=(
            NavItem("bang-dac-biet", "bang-dac-biet.html", "Bảng Đặc Biệt", "Giải Đặc Biệt theo ngày"),
            NavItem("bang-dac-biet-thang", "bang-dac-biet-thang.html", "Bảng Đặc Biệt theo tháng", "Giải Đặc Biệt gom theo tháng"),
            NavItem("bang-dac-biet-nam", "bang-dac-biet-nam.html", "Bảng Đặc Biệt theo năm", "Giải Đặc Biệt gom theo năm"),
            NavItem("cau-dac-biet", "cau-giai-dac-biet.html", "Cầu giải Đặc Biệt", "Quan hệ giữa các kỳ liền nhau của giải Đặc Biệt"),
            NavItem("cau-dac-biet-bo-so", "cau-dac-biet-theo-bo-so.html", "Cầu Đặc Biệt theo bộ số", "Cầu Đặc Biệt nhóm theo bộ số"),
            NavItem("chu-ky-dac-biet", "chu-ky-dac-biet.html", "Chu kỳ Đặc Biệt", "Khoảng cách giữa hai lần về của cùng một số"),
            NavItem("dac-biet-theo-tong", "giai-dac-biet-theo-tong.html", "Đặc Biệt theo tổng", "Giải Đặc Biệt nhóm theo tổng hai chữ số cuối"),
            NavItem("dac-biet-ngay-mai", "giai-db-ngay-mai.html", "Đặc Biệt kỳ tới", "Thống kê hướng tới kỳ chưa mở"),
        ),
    ),
    NavGroup(
        key="lo-to",
        label="Lô tô",
        icon="grid",
        items=(
            NavItem("tan-suat-loto", "tan-suat-loto.html", "Tần suất lô tô", "Số lần về của từng con trong nhiều cửa sổ"),
            NavItem("tan-suat-cap-loto", "tan-suat-cap-loto.html", "Tần suất cặp lô tô", "Số lần hai con cùng về trong một kỳ"),
            NavItem("cap-lon-loto", "cap-lon-loto.html", "Cặp lớn lô tô", "Các cặp có tần suất đồng hiện cao nhất"),
            NavItem("dau-duoi-loto", "dau-duoi-loto.html", "Đầu đuôi lô tô", "Phân bố theo chữ số đầu và chữ số cuối"),
            NavItem("lo-gan", "lo-gan.html", "Lô gan", "Số kỳ liên tiếp một con chưa về"),
        ),
    ),
    NavGroup(
        key="du-doan",
        label="Dự đoán & Mô hình",
        icon="brain",
        items=(
            NavItem("ml-loto", "ml_top10_loto.html", "Top 10 lô tô (ML)", "Mười con lô tô có xác suất mô hình cao nhất"),
            NavItem("ml-dac-biet", "ml_top10_de.html", "Top 10 Đặc Biệt (ML)", "Mười con Đặc Biệt có xác suất mô hình cao nhất"),
            NavItem("chat-luong-mo-hinh", "model-quality.html", "Chất lượng mô hình", "Hiệu chuẩn, độ nhọn, phân rã Murphy, kỹ năng so đường cơ sở"),
        ),
    ),
    NavGroup(
        key="soi-path",
        label="Soi path",
        icon="route",
        items=(
            NavItem("path-loto-on-dinh", "soi-path-loto-stable.html", "Path lô tô — ổn định", "Đường đi ổn định của lô tô qua các kỳ"),
            NavItem("path-loto-hoat-dong", "soi-path-loto-active.html", "Path lô tô — hoạt động", "Đường đi đang hoạt động của lô tô"),
            NavItem("path-dac-biet-on-dinh", "soi-path-de-stable.html", "Path Đặc Biệt — ổn định", "Đường đi ổn định của giải Đặc Biệt"),
            NavItem("path-dac-biet-hoat-dong", "soi-path-de-active.html", "Path Đặc Biệt — hoạt động", "Đường đi đang hoạt động của giải Đặc Biệt"),
        ),
    ),
    NavGroup(
        key="nghien-cuu",
        label="Nghiên cứu",
        icon="flask",
        items=(
            NavItem("phong-nghien-cuu", "research-lab.html", "Phòng nghiên cứu", "Quét cầu, kiểm định đa giả thuyết, cổng nghiên cứu"),
        ),
    ),
)

#: Hai biến thể của trang chủ, KHÔNG nằm trong sidebar.
#:
#: Chúng là bản riêng cho máy tính và cho điện thoại, tồn tại từ giao diện cũ.
#: Đưa chúng vào điều hướng sẽ là ba mục dẫn tới cùng một nội dung — mục 5.3
#: đòi mục đang mở phải nhận ra được, và ba mục trùng nội dung thì không nhận
#: ra được cái nào đang mở. Vẫn khai ở đây để phép kiểm đối chiếu 29 tệp không
#: báo thiếu, và để không ai quên chúng tồn tại.
UNLISTED_PAGES: Final[tuple[NavItem, ...]] = (
    NavItem("landing", "landing.html", "Trang giới thiệu", "Biến thể trang chủ"),
    NavItem("landing-desktop", "landing_desktop.html", "Trang giới thiệu (máy tính)", "Biến thể trang chủ cho màn hình lớn"),
)


def all_items() -> tuple[NavItem, ...]:
    """Mọi trang, kể cả các trang không nằm trong sidebar."""
    listed = tuple(item for group in NAV for item in group.items)
    return listed + UNLISTED_PAGES


def item_by_key(key: str) -> NavItem:
    """Tra một trang theo khoá.

    Raises:
        KeyError: Khi khoá không tồn tại. Ném lỗi thay vì trả ``None``, vì một
            khoá sai lặng lẽ cho ra trang không có mục nào được đánh dấu đang
            mở — đúng lỗi mục 5.3 cấm.
    """
    for item in all_items():
        if item.key == key:
            return item
    raise KeyError(f"không có trang với khoá {key!r}")


def group_of(key: str) -> NavGroup | None:
    """Nhóm chứa trang này, hoặc ``None`` nếu trang không nằm trong sidebar."""
    for group in NAV:
        if any(item.key == key for item in group.items):
            return group
    return None
