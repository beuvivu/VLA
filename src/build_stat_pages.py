"""Dựng các trang thống kê riêng biệt có bộ lọc thời gian tùy biến.

Vì sao tính ở trình duyệt chứ không dựng sẵn
--------------------------------------------
Người dùng cần chọn dải ngày/tháng/năm tùy ý. Dựng sẵn mọi tổ hợp là không
khả thi, còn gọi API thì cần server — mà kho này phát hành site tĩnh trên
GitHub Pages, không có tiến trình nào chạy.

Lối thoát nằm ở kích thước dữ liệu. Đo thực tế: **172 byte mỗi kỳ**, tức 66 KB
thô cho 393 kỳ và khoảng 410 KB cho 2442 kỳ; qua gzip còn 16 KB và 99 KB
(nén 4,1 lần). Nhúng thẳng vào trang rồi tính bằng JavaScript cho ra bộ lọc
tức thì, không server, không độ trễ mạng. Đây là cách duy nhất thoả cả hai
ràng buộc.

Ngưỡng cần theo dõi: nhúng dữ liệu bắt đầu bất tiện quanh mốc vài MB thô. Với
một kỳ mỗi ngày thì từ 2442 kỳ còn khoảng 25 năm nữa mới chạm mốc đó.

Cảnh báo đi kèm: mọi **mốc so sánh** hiển thị trên trang đều phải tính theo
số kỳ đang chọn, không phải theo hằng số. Trang có bộ lọc 30/60/90/180/365
kỳ, nên một con số đóng cứng sai ngay lần bấm đầu tiên — xem
:func:`pair_chance_grid`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

import pandas as pd

from number_reference import all_cap_loto_50, bo_family_id
from ui_theme import app_shell_close, app_shell_open, stylesheet_link
from xsmb_domain import (
    LOTO_BASELINE_RATE,
    PAIR_COOCCURRENCE_RATE,
    pair_chance_maximum,
)
from web_security import json_for_html_script, security_meta_tags

logger = logging.getLogger(__name__)

#: Hai mốc ngẫu nhiên lấy từ ``xsmb_domain`` chứ không tự tính lại: bản chép
#: riêng ở đây từng khiến mốc cực đại 39,8 (đo trên 393 kỳ) nằm lại trong khi
#: lịch sử đã dài ra.
LOTO_BASELINE = LOTO_BASELINE_RATE
PAIR_BASELINE = PAIR_COOCCURRENCE_RATE

#: Độ rộng chữ số của từng giải. CSV lưu kiểu số nguyên nên mất số 0 ở đầu;
#: đo được 10,3% số ô ngắn hơn độ rộng đúng. Thiếu bảng này thì mọi phép cắt
#: chữ số theo vị trí đều lệch.
PRIZE_WIDTH: dict[str, int] = {
    "special": 5, "prize1": 5, "prize2": 5, "prize3": 5,
    "prize4": 4, "prize5": 4, "prize6": 3, "prize7": 2,
}


@dataclass(frozen=True)
class StatPage:
    """Mô tả một trang thống kê.

    Attributes:
        slug: Tên tệp không kèm ``.html``.
        title: Tiêu đề trang.
        subtitle: Mô tả ngắn dưới tiêu đề.
        controls: HTML của thanh điều khiển bộ lọc.
        body: HTML phần thân (thường là khung rỗng cho JS đổ vào).
        render: Tên hàm JavaScript vẽ lại trang khi bộ lọc đổi.
    """

    slug: str
    title: str
    subtitle: str
    controls: str
    body: str
    render: str


def load_draws(repo_root: Path) -> list[dict[str, object]]:
    """Đọc lịch sử và trả về dạng gọn để nhúng vào trang.

    Args:
        repo_root: Thư mục gốc của kho.

    Returns:
        Danh sách kỳ quay, mỗi phần tử ``{"d": ngày, "s": ĐB 5 chữ số,
        "n": [27 số hai chữ số]}``, sắp xếp tăng dần theo ngày.

    Raises:
        FileNotFoundError: Nếu thiếu ``data/xsmb.csv``.
    """
    path = repo_root / "data" / "xsmb.csv"
    if not path.exists():
        raise FileNotFoundError(f"thiếu {path}")

    frame = pd.read_csv(path, dtype=str).fillna("")
    frame = frame.sort_values("date").reset_index(drop=True)

    prize_cols = [c for c in frame.columns if c != "date"]
    draws: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        two_digits: list[str] = []
        special = ""
        for col in prize_cols:
            base = col.split("_")[0]
            width = PRIZE_WIDTH[base]
            # zfill là bắt buộc: CSV lưu số nguyên nên "05225" thành "5225".
            digits = str(row[col]).strip().zfill(width)
            if len(digits) != width or not digits.isdigit():
                continue
            two_digits.append(digits[-2:])
            if col == "special":
                special = digits
        if len(two_digits) == 27:
            draws.append({"d": str(row["date"]), "s": special, "n": two_digits})
    return draws


def _range_controls(*, mode: str = "day") -> str:
    """Thanh chọn dải thời gian.

    Args:
        mode: ``day`` cho hai ô chọn ngày, ``preset`` cho các nút nhanh.

    Returns:
        Chuỗi HTML.
    """
    presets = "".join(
        f'<button class="sp-chip" data-days="{d}">{label}</button>'
        for d, label in (
            (30, "30 kỳ"), (60, "60 kỳ"), (90, "90 kỳ"),
            (180, "180 kỳ"), (365, "1 năm"), (0, "Tất cả"),
        )
    )
    if mode == "preset":
        # Thanh đánh dấu phải có ở MỌI trang, không chỉ trang dùng bộ chọn
        # ngày: ô vẫn bấm được nên thiếu nút xoá là người dùng đánh dấu xong
        # không gỡ ra được.
        return (
            '<div class="sp-controls"><div class="sp-chips">'
            f'{presets}</div><span class="sp-count" id="sp-count"></span>'
            f"{_mark_tools()}</div>"
        )
    return f"""
    <div class="sp-controls">
      <label>Từ ngày <input type="date" id="sp-from"></label>
      <label>Đến ngày <input type="date" id="sp-to"></label>
      <div class="sp-chips">{presets}</div>
      <span class="sp-count" id="sp-count"></span>
      {_mark_tools()}
    </div>
    """


def _mark_tools() -> str:
    """Thanh đánh dấu ô, dùng chung cho mọi trang.

    Bảng ở đây dài hàng chục hàng và người đọc thường dõi theo vài ô rời rạc —
    ví dụ cùng một ngày qua nhiều tháng. Không có cách đánh dấu thì chỉ cần
    cuộn một cái là mất dấu.

    Returns:
        Chuỗi HTML của thanh công cụ.
    """
    return (
        '<span class="sp-marktools">'
        '<span class="sp-hint">Bấm vào ô bất kỳ để đánh dấu so sánh</span>'
        '<span class="sp-mark-count" id="sp-mark-count"></span>'
        '<button type="button" class="sp-chip" id="sp-clear-marks">Xoá đánh dấu</button>'
        "</span>"
    )


#: Hộp bật/tắt sáu trường trong mỗi ô bảng đặc biệt. Trang tham chiếu có đúng
#: sáu ô đánh dấu này; nội dung do JavaScript dựng từ DE_FIELDS.
FIELD_TOGGLE = '<div class="sp-fields-toggle" id="sp-fields-toggle"></div>'

PAGES: tuple[StatPage, ...] = (
    StatPage(
        slug="bang-dac-biet",
        title="Bảng đặc biệt theo tuần",
        subtitle="Giải đặc biệt đủ 5 chữ số theo tuần: hàng là tuần, cột là thứ.",
        controls=_range_controls(),
        body=FIELD_TOGGLE
             + '<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderSpecialByWeek",
    ),
    StatPage(
        slug="bang-dac-biet-thang",
        title="Bảng đặc biệt theo tháng",
        subtitle="Cả năm theo ngày × tháng, kèm bảng cùng một tháng qua nhiều năm.",
        controls='<div class="sp-controls">'
                 '<label>Năm <select id="sp-year"></select></label>'
                 '<label>Tháng <select id="sp-month"></select></label>'
                 '<span class="sp-count" id="sp-count"></span>' + _mark_tools() + '</div>',
        body=FIELD_TOGGLE
             + '<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>'
             '<h3 class="sp-subhead">Cùng tháng đã chọn, qua tất cả các năm có dữ liệu</h3>'
             '<div class="sp-scroll"><table class="sp-table" id="sp-multiyear"></table></div>',
        render="renderSpecialByMonth",
    ),
    StatPage(
        slug="bang-dac-biet-nam",
        title="Bảng đặc biệt theo năm",
        subtitle="Cả năm, chọn Kiểu tháng (ngày × tháng) hoặc Kiểu tuần (tuần × thứ).",
        controls='<div class="sp-controls">'
                 '<label>Năm <select id="sp-year"></select></label>'
                 '<label>Kiểu <select id="sp-mode"></select></label>'
                 '<span class="sp-count" id="sp-count"></span>' + _mark_tools() + '</div>',
        body=FIELD_TOGGLE
             + '<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderSpecialByYear",
    ),
    StatPage(
        slug="tan-suat-loto",
        title="Tần suất lô tô",
        subtitle="Ma trận con lô × từng kỳ, đổi được chiều, chọn con để so sánh.",
        controls='<div class="sp-controls">'
                 '<label>Từ ngày <input type="date" id="sp-from"></label>'
                 '<label>Đến ngày <input type="date" id="sp-to"></label>'
                 '<label>Chiều <select id="sp-orient">'
                 '<option>Xem theo chiều ngang</option>'
                 '<option>Xem theo chiều dọc</option></select></label>'
                 '<span class="sp-count" id="sp-count"></span>' + _mark_tools() + '</div>',
        body='<div class="sp-picker" id="sp-picker"></div>'
             '<p class="sp-matrix-note" id="sp-matrix-note"></p>'
             '<div class="sp-scroll"><table class="sp-table sp-dense" id="sp-matrix-grid"></table></div>'
             '<h3 class="sp-subhead">Xếp hạng trên trọn dải đã chọn</h3>'
             '<div id="sp-matrix" class="sp-matrix"></div>'
             '<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderLotoFrequency",
    ),
    StatPage(
        slug="tan-suat-cap-loto",
        title="Tần suất cặp lô tô",
        subtitle="Ma trận 50 họ cặp × từng kỳ, đổi được chiều; kèm bảng đồng xuất hiện.",
        controls='<div class="sp-controls">'
                 '<label>Từ ngày <input type="date" id="sp-from"></label>'
                 '<label>Đến ngày <input type="date" id="sp-to"></label>'
                 '<label>Chiều <select id="sp-orient">'
                 '<option>Xem theo chiều ngang</option>'
                 '<option>Xem theo chiều dọc</option></select></label>'
                 '<span class="sp-count" id="sp-count"></span>' + _mark_tools() + '</div>',
        body='<p class="sp-matrix-note" id="sp-matrix-note"></p>'
             '<div class="sp-scroll"><table class="sp-table sp-dense" id="sp-matrix-grid"></table></div>'
             '<h3 class="sp-subhead">Cặp đồng xuất hiện nhiều nhất trên trọn dải</h3>'
             '<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderPairFrequency",
    ),
    StatPage(
        slug="giai-dac-biet-theo-tong",
        title="Giải đặc biệt theo tổng",
        subtitle="Tổng = (Đầu + Đuôi) mod 10. Gan theo tổng, chuyển tổng và chẵn lẻ hôm sau.",
        controls=_range_controls(),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>'
             '<h3 class="sp-subhead">Hôm trước tổng X thì hôm sau tổng Y</h3>'
             '<p class="sp-note">Mức ngẫu nhiên là <b>10 %</b> cho mỗi ô, vì tổng chỉ có '
             '10 giá trị. Cột "So mức ngẫu nhiên" là tỉ lệ chia cho 10 %; quanh 1,0× nghĩa '
             'là không phân biệt được với ngẫu nhiên. Bảng xếp theo <b>lệch chuẩn hoá</b> '
             'chứ không theo tỉ lệ: xếp theo tỉ lệ thì một ô 3/9 cho 33 % và đứng đầu bảng, '
             'dù ba lần chẳng nói lên điều gì. Lệch chuẩn hoá chia độ lệch cho sai số chuẩn, '
             'nên chỉ mẫu đủ lớn mới lên được. Quanh ±2 vẫn là mức thường gặp khi xét 100 ô. '
             'Đây là thống kê MÔ TẢ trên lịch sử, '
             'không phải xác suất đã hiệu chuẩn, và chỉ đếm các kỳ LIỀN KỀ thật — ranh giới '
             'ngày nghỉ quay bị bỏ qua thay vì nối lại thành một chuyển tiếp không tồn tại.</p>'
             '<div class="sp-scroll"><table class="sp-table" id="sp-trans"></table></div>'
             '<h3 class="sp-subhead">Chẵn lẻ của tổng hôm sau</h3>'
             '<div class="sp-scroll"><table class="sp-table" id="sp-parity"></table></div>',
        render="renderSpecialByTong",
    ),
    StatPage(
        slug="cau-giai-dac-biet",
        title="Cầu giải đặc biệt",
        subtitle="Tần suất hai số cuối giải ĐB theo Đầu, cặp lộn kèm số lần, ba kỳ gần nhất.",
        controls=_range_controls(),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>'
             '<h3 class="sp-subhead">Cặp lộn của giải đặc biệt</h3>'
             '<div class="sp-scroll"><table class="sp-table" id="sp-lon"></table></div>'
             '<h3 class="sp-subhead">Ba kỳ gần nhất</h3>'
             '<div id="sp-recent" class="sp-recent"></div>',
        render="renderSpecialBridge",
    ),
    StatPage(
        slug="cap-lon-loto",
        title="Cặp lộn lô tô",
        subtitle="45 cặp lộn thật (đảo hai chữ số), kèm 10 số kép liệt kê riêng.",
        controls=_range_controls(),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>'
             '<h3 class="sp-subhead">Số kép — đảo lại chính nó nên không có số lộn</h3>'
             '<div class="sp-scroll"><table class="sp-table" id="sp-kep"></table></div>',
        render="renderReversePairs",
    ),
    StatPage(
        slug="dau-duoi-loto",
        title="Đầu đuôi lô tô",
        subtitle="Phân bố chữ số đầu và chữ số đuôi của toàn bộ lô tô trong dải đã chọn.",
        controls=_range_controls(),
        body='<div class="sp-duo">'
             '<div><h3>Theo chữ số ĐẦU</h3><table class="sp-table" id="sp-head"></table></div>'
             '<div><h3>Theo chữ số ĐUÔI</h3><table class="sp-table" id="sp-tail"></table></div>'
             "</div>",
        render="renderHeadTail",
    ),
    StatPage(
        slug="chu-ky-dac-biet",
        title="Chu kỳ giải đặc biệt",
        subtitle="Số kỳ chưa về của từng con 00–99 ở giải đặc biệt, và chu kỳ dài nhất trong lịch sử.",
        controls=_range_controls(mode="preset"),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderSpecialCycle",
    ),
    StatPage(
        slug="cau-dac-biet-theo-bo-so",
        title="Cầu giải đặc biệt theo bộ số",
        subtitle="Điểm rơi của từng bộ số ở giải đặc biệt: lần về gần nhất, khoảng cách và số lần.",
        controls=_range_controls(mode="preset"),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderSpecialBySet",
    ),
    StatPage(
        slug="giai-db-ngay-mai",
        title="Giải đặc biệt ngày mai",
        subtitle="Xếp hạng tham khảo cho kỳ kế tiếp, dựng từ chu kỳ và tần suất lịch sử.",
        controls=_range_controls(mode="preset"),
        body='<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderTomorrow",
    ),
    StatPage(
        slug="thong-ke-tong-hop",
        title="Thống kê tổng hợp",
        subtitle="Bảng tổng hợp đa chiều: tần suất, chu kỳ gan, đầu đuôi và tổng trên cùng một dải.",
        controls=_range_controls(),
        body='<div id="sp-kpi" class="sp-kpi"></div>'
             '<div class="sp-scroll"><table class="sp-table" id="sp-grid"></table></div>',
        render="renderOverview",
    ),
)


#: Ghi chú mốc ngẫu nhiên cho từng trang. Trang xếp hạng nào cũng phải có,
#: nếu không bảng trông như quy luật trong khi đó là mức ngẫu nhiên thường
#: tạo ra. Cách suy ra ghi trong
#: documentation/architecture/soi-cau-ml-mapping.md.
#:
#: Các chuỗi này là **khuôn ``str.format``**: mốc nào co giãn theo độ dài lịch
#: sử thì để chỗ trống cho :func:`chance_note_context` điền, không đóng cứng.
#: Ghi chú không có chỗ trống vẫn đi qua ``format`` nguyên vẹn.
CHANCE_NOTES: dict[str, str] = {
    "tan-suat-loto": (
        "Kỳ vọng mỗi con là <b>1 − (0,99)²⁷ ≈ 23,77%</b> mỗi kỳ. Con dẫn đầu "
        "trong 100 con luôn cao hơn kỳ vọng kể cả khi dữ liệu hoàn toàn ngẫu "
        "nhiên — cột “So kỳ vọng” là để so, không phải để chọn."
    ),
    # ``sp-chance`` được JavaScript viết lại theo dải ngày đang chọn. Nội dung
    # dựng sẵn ở đây là bản dự phòng cho toàn bộ lịch sử, đúng khi chưa ai bấm
    # bộ lọc và khi JavaScript không chạy.
    "tan-suat-cap-loto": (
        "Có <b>4 950</b> cặp số. <span id=\"sp-chance\">Trên lịch sử ngẫu nhiên "
        "dài đúng {n_draws} kỳ, cực đại trung bình là {chance_max} lần (khoảng "
        "90%: {low}–{high}), trong khi kỳ vọng mỗi cặp chỉ {pair_expected}."
        "</span> Một cặp chỉ đáng chú ý khi vượt hẳn khoảng đó."
    ),
    "chu-ky-dac-biet": (
        "Giải đặc biệt có 100 kết quả hai số nên khoảng gan trung bình là 100 "
        "kỳ. Gan dài không làm con số “sắp về”: mỗi kỳ vẫn là 1/100 độc lập "
        "với lịch sử."
    ),
    "cau-dac-biet-theo-bo-so": (
        "Bảng này mô tả lịch sử điểm rơi, không phải dự báo. Khoảng cách giữa "
        "hai lần về của cùng một bộ số phân bố hình học quanh trung bình 100 kỳ."
    ),
    "giai-db-ngay-mai": (
        "⚠️ Đây là <b>xếp hạng mô tả</b> dựng từ chu kỳ lịch sử, "
        "<b>không phải xác suất đã hiệu chuẩn</b> và không bảo đảm kết quả. "
        "Đo trên chính kho này: không mô hình nào trong 12 họ đã thử vượt được "
        "tỉ lệ nền."
    ),
}


def _asset(name: str) -> str:
    """Đọc tệp tài nguyên đi kèm mô-đun.

    Args:
        name: Tên tệp trong ``src/templates``.

    Returns:
        Nội dung tệp.
    """
    return (Path(__file__).resolve().parent / "templates" / name).read_text(encoding="utf-8")


#: Các mốc số kỳ để dựng sẵn cực đại ngẫu nhiên cho trình duyệt tra.
#:
#: Trang cho phép lọc theo dải ngày, nên mốc phải đổi theo tập ĐANG CHỌN chứ
#: không theo toàn bộ lịch sử. Công thức đóng cần hàm phân phối nhị thức, quá
#: nặng để cài lại trong JavaScript; lưới này cho nội suy tuyến tính sai số
#: tối đa 0,67%, và dưới 0,15% với mọi N >= 30.
PAIR_CHANCE_GRID_POINTS: tuple[int, ...] = (
    10, 20, 30, 45, 60, 90, 120, 180, 270, 365, 550,
    730, 1100, 1460, 1825, 2200, 2600, 3000, 3700, 4400, 5500, 7300,
)


def cap_loto_50() -> list[list[int]]:
    """50 họ cặp lô tô, lấy từ ``number_reference.all_cap_loto_50``.

    Trang tham chiếu dùng đúng bộ này: 45 cặp lộn thật cộng 5 cặp ghép hai số
    kép qua bóng (``00-55``, ``11-66``, ``22-77``, ``33-88``, ``44-99``). Đọc
    được từ chính trang họ nên đây là bằng chứng chứ không phải suy đoán.

    Returns:
        50 cặp ``[nhỏ, lớn]``, sắp theo phần tử nhỏ.
    """
    pairs = [sorted(int(m) for m in family) for family in all_cap_loto_50()]
    pairs.sort()
    return pairs


def bo_lookup() -> list[str]:
    """Bảng tra họ **bộ số** cho 00-99, dựng sẵn cho trình duyệt.

    Bộ số gom một con với bóng-dương và số lộn của nó: 68 thuộc bộ 13 vì
    6 có bóng 1 và 8 có bóng 3. Có 15 họ, nhãn là phần tử nhỏ nhất.

    Trang tham chiếu hiển thị cột này trong mỗi ô bảng đặc biệt; đo trên 24 ô
    thật thì :func:`number_reference.bo_family_id` khớp 100%, nên dựng sẵn từ
    chính hàm đó thay vì cài lại công thức trong JavaScript — một bản chép
    thứ hai là một bản sẽ trôi.

    Returns:
        Danh sách 100 nhãn, chỉ số là con số 00-99.
    """
    return [bo_family_id(f"{n:02d}") for n in range(100)]


def pair_chance_grid() -> list[list[float]]:
    """Bảng tra ``[số kỳ, cực đại, cận dưới, cận trên]`` cho trình duyệt.

    Returns:
        Danh sách theo thứ tự số kỳ tăng dần, để nội suy tuyến tính.
    """
    grid: list[list[float]] = []
    for n in PAIR_CHANCE_GRID_POINTS:
        mean, (low, high) = pair_chance_maximum(n)
        grid.append([n, round(mean, 2), low, high])
    return grid


def chance_note_context(n_draws: int) -> dict[str, str]:
    """Các mốc ngẫu nhiên co giãn theo độ dài lịch sử, để điền vào ghi chú.

    Args:
        n_draws: Số kỳ trong lịch sử đang dựng.

    Returns:
        Từ điển thay thế cho ``str.format`` trên :data:`CHANCE_NOTES`.
    """
    chance_max, (low, high) = pair_chance_maximum(n_draws)
    return {
        "n_draws": f"{n_draws:,}".replace(",", " "),
        "chance_max": f"{chance_max:.1f}".replace(".", ","),
        "low": str(low),
        "high": str(high),
        "pair_expected": f"{PAIR_BASELINE * n_draws:.1f}".replace(".", ","),
    }


def render_page(page: StatPage, draws: list[dict[str, object]], *, generated: str) -> str:
    """Dựng HTML hoàn chỉnh cho một trang thống kê.

    Args:
        page: Mô tả trang.
        draws: Lịch sử đã nạp, sẽ được nhúng vào trang.
        generated: Dấu thời gian dựng, hiển thị ở chân trang.

    Returns:
        Chuỗi HTML đầy đủ.
    """
    note = CHANCE_NOTES.get(page.slug, "").format(**chance_note_context(len(draws)))
    note_html = f'<p class="sp-note">{note}</p>' if note else ""
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{security_meta_tags()}
{stylesheet_link()}
<title>{page.title} · VLA</title>
<style>
{_asset("stat_pages.css")}
</style></head><body>
{app_shell_open(f"{page.slug}.html", wide=True)}
<div style="margin-bottom:1rem"><a href="index.html">← Trang chính</a></div>
<h1>{page.title}</h1>
<p class="vla-muted" style="max-width:60rem;line-height:1.65">{page.subtitle}</p>
{page.controls}
{page.body}
{note_html}
<p class="vla-muted" style="margin-top:1.5rem;font-size:.75rem">
Dựng lúc {generated}. Toàn bộ tính toán chạy trong trình duyệt trên
{len(draws)} kỳ đã nhúng — không gọi mạng, không máy chủ.</p>
{app_shell_close(f"{page.slug}.html")}
<script>window.__VLA_DRAWS__={json_for_html_script(draws)};
window.__VLA_PAIR_CHANCE__={json_for_html_script(pair_chance_grid())};
window.__VLA_BO__={json_for_html_script(bo_lookup())};
window.__VLA_CAP50__={json_for_html_script(cap_loto_50())};</script>
<script>
{_asset("stat_pages.js")}
boot({json.dumps(page.render)});
</script>
</body></html>
"""


def build(repo_root: Path, docs_dir: Path) -> list[Path]:
    """Dựng toàn bộ trang thống kê.

    Args:
        repo_root: Thư mục gốc của kho.
        docs_dir: Thư mục đầu ra.

    Returns:
        Danh sách tệp đã ghi.
    """
    draws = load_draws(repo_root)
    if not draws:
        raise SystemExit("không nạp được kỳ nào từ data/xsmb.csv")

    docs_dir.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    written: list[Path] = []
    for page in PAGES:
        target = docs_dir / f"{page.slug}.html"
        target.write_text(render_page(page, draws, generated=generated), encoding="utf-8")
        written.append(target)
        logger.info("đã ghi %s", target.name)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    """Điểm vào dòng lệnh.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát 0.
    """
    parser = argparse.ArgumentParser(description="Dựng các trang thống kê riêng biệt.")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Path(__file__).resolve().parents[1]
    files = build(root, root / args.docs_dir)
    logger.info("Xong: %d trang", len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
