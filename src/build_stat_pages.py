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
from page_output import write_page

logger = logging.getLogger(__name__)

#: Hai mốc ngẫu nhiên lấy từ ``xsmb_domain`` chứ không tự tính lại: bản chép
#: riêng ở đây từng khiến mốc cực đại 39,8 (đo trên 393 kỳ) nằm lại trong khi
#: lịch sử đã dài ra.
LOTO_BASELINE = LOTO_BASELINE_RATE
PAIR_BASELINE = PAIR_COOCCURRENCE_RATE

#: Dải mặc định khi mở trang, tính theo SỐ KỲ. Giá trị thật nằm trong
#: ``stat_pages.js`` (``DRAWS.length - 90``); ở đây chỉ để tô sáng đúng nút.
#: ``test_default_range_chip_matches_the_javascript_default`` giữ hai bên khớp
#: nhau, vì lệch thì thanh điều khiển nói một đằng còn ô ngày một nẻo — đúng
#: trạng thái trước đây, khi không nút nào sáng cả.
DEFAULT_RANGE_DRAWS = 90

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
        Danh sách kỳ quay, mỗi phần tử ``{"d": ngày, "s": Đặc Biệt 5 chữ số,
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
    # Nút nào đang thật sự có hiệu lực phụ thuộc vào kiểu thanh điều khiển.
    # Trang kiểu ``day`` có hai ô ngày, và stat_pages.js đặt sẵn chúng ở
    # ``DRAWS.length - 90``. Trang kiểu ``preset`` KHÔNG có ô ngày nào, nên
    # nhánh đó trong JS không chạy và dải mặc định là toàn bộ lịch sử.
    # Tô sáng 90 kỳ ở cả hai kiểu thì trang preset sẽ khoe "90 kỳ" trong khi
    # đang hiển thị 2 396 kỳ.
    active = DEFAULT_RANGE_DRAWS if mode == "day" else 0
    presets = "".join(
        f'<button class="sp-chip{" on" if d == active else ""}"'
        f' data-days="{d}">{label}</button>'
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
        '<label class="sp-chip sp-chip-check">'
        '<input type="checkbox" id="sp-pair-mode">'
        '<span>Tự động đánh dấu cặp trùng</span></label>'
        '<span class="sp-mark-count" id="sp-mark-count"></span>'
        '<button type="button" class="sp-btn" id="sp-clear-marks">Xoá đánh dấu</button>'
        "</span>"
    )


#: Lọc theo thứ trong tuần. Giá trị là chỉ số thứ chuẩn JavaScript
#: (Chủ nhật = 0); thứ tự hiển thị bắt đầu từ Thứ hai vì tuần của người Việt
#: bắt đầu từ đó — hai chuyện ấy không cần trùng nhau.
WEEKDAY_CHOICES: tuple[tuple[str, str], ...] = (
    ("all", "Tất cả các thứ"),
    ("1", "Thứ hai"), ("2", "Thứ ba"), ("3", "Thứ tư"), ("4", "Thứ năm"),
    ("5", "Thứ sáu"), ("6", "Thứ bảy"), ("0", "Chủ nhật"),
)


#: Mốc ngày nhanh. Trần 300 là ràng buộc đo được: 300 kỳ dựng trong 894 ms,
#: còn 500 kỳ mất 4 113 ms nên không đưa vào danh sách.
QUICK_RANGES: tuple[tuple[str, str], ...] = (
    ("30", "30 ngày"), ("60", "60 ngày"), ("90", "90 ngày"),
    ("100", "100 ngày"), ("200", "200 ngày"), ("300", "300 ngày"),
)

#: Thứ tự sắp xếp con số trên ma trận.
SORT_CHOICES: tuple[tuple[str, str], ...] = (
    ("num", "00 → 99"),
    ("hit-desc", "Về nhiều nhất"),
    ("hit-asc", "Về ít nhất"),
    ("gan-desc", "Gan nhiều nhất"),
    ("gan-asc", "Gan ít nhất"),
)


def _gan_picker() -> str:
    """Ô chọn số để mở popup chu kỳ gan.

    Trang tần suất cặp không có lưới 00-99, nên nếu chỉ gắn popup vào lưới ấy
    thì tính năng chỉ tồn tại ở một trong hai trang.
    """
    options = "".join(f'<option value="{n:02d}">{n:02d}</option>' for n in range(100))
    return ('<label>Chu kỳ gan <select id="sp-gan-pick">'
            f'<option value="">Chọn số…</option>{options}</select></label>')


def _gan_modal() -> str:
    """Khung popup chu kỳ gan. MỘT hàm cho mọi trang, không chép hai bản."""
    return (
        '<div class="sp-gan-modal" id="sp-gan-modal" hidden>'
        '<div class="sp-modal-card" role="dialog" aria-modal="true">'
        '<div class="sp-modal-head"><b class="sp-modal-title"></b>'
        '<button type="button" class="sp-btn" data-close>Đóng</button></div>'
        '<div class="sp-modal-body"></div></div></div>'
    )


def _quick_ranges() -> str:
    buttons = "".join(
        f'<button type="button" class="sp-btn" data-days="{value}">{label}</button>'
        for value, label in QUICK_RANGES
    )
    return f'<span class="sp-quick" id="sp-quick">{buttons}</span>'


def _sort_menu() -> str:
    options = "".join(
        f'<option value="{value}"{" selected" if value == "num" else ""}>{label}</option>'
        for value, label in SORT_CHOICES
    )
    return f'<label>Sắp xếp <select id="sp-sort">{options}</select></label>'


def _weekday_filter() -> str:
    options = "".join(
        f'<option value="{value}"{" selected" if value == "all" else ""}>{label}</option>'
        for value, label in WEEKDAY_CHOICES
    )
    return f'<label>Thứ <select id="sp-weekday">{options}</select></label>'


#: Chú giải ô + hộp bật/tắt sáu trường trong mỗi ô bảng Đặc Biệt.
#:
#: Trang tham chiếu có đúng sáu ô đánh dấu này nhưng không giải thích trường
#: nào đứng ở đâu. Người đọc phải hỏi mới biết chữ nhỏ dưới mỗi giải là gì, nên
#: ở đây đặt thêm hàng chú giải phía trên. Cả hai khối đều rỗng trong HTML:
#: JavaScript dựng chúng từ DE_FIELDS, một nguồn duy nhất cho cả ô lẫn chú
#: giải — chép nhãn sang Python là tạo bản thứ hai sẽ trôi khỏi bản gốc.
FIELD_TOGGLE = (
    '<div class="sp-legend" id="sp-legend"></div>'
    '<div class="sp-fields-toggle" id="sp-fields-toggle"></div>'
)

PAGES: tuple[StatPage, ...] = (
    StatPage(
        slug="bang-dac-biet",
        title="Bảng Đặc Biệt theo tuần",
        subtitle="Giải Đặc Biệt đủ 5 chữ số theo tuần: hàng là tuần, cột là thứ.",
        controls=_range_controls(),
        body=FIELD_TOGGLE
             + '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>',
        render="renderSpecialByWeek",
    ),
    # HAI TRANG NÀY TỪNG HIỆN ĐÚNG CÙNG MỘT BẢNG.
    #
    # Cả hai gọi `table($("sp-grid"), MONTH_HEAD, monthGrid(year))` — cùng lưới
    # ngày × tháng, cùng năm, cùng từng ô. Người dùng mở hai đường dẫn khác
    # nhau và thấy hai trang y hệt. Trang "theo năm" còn có bộ chọn Kiểu mà
    # nhánh "Kiểu tuần" của nó lại dựng đúng cùng một lệnh với trang "theo
    # tuần", nên nó là hai trang kia mặc áo khác.
    #
    # Nay mỗi trang mang tên đúng TRỤC mà bảng trải ra:
    #
    #     theo tuần   hàng = tuần   cột = thứ trong tuần   (dải ngày tuỳ chọn)
    #     theo tháng  hàng = ngày   cột = THÁNG 1-12       (chọn năm)
    #     theo năm    hàng = NĂM    cột = ngày 1-31        (chọn tháng)
    #
    # Ba trục, ba trang, không chồng lấn.
    StatPage(
        slug="bang-dac-biet-thang",
        title="Bảng Đặc Biệt theo tháng",
        subtitle="Trọn một năm: hàng là ngày trong tháng, cột là tháng.",
        controls='<div class="sp-controls">'
                 '<label>Năm <select id="sp-year"></select></label>'
                 '<span class="sp-count" id="sp-count"></span>' + _mark_tools() + '</div>',
        body=FIELD_TOGGLE
             + '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>',
        render="renderSpecialDayByMonth",
    ),
    StatPage(
        slug="bang-dac-biet-nam",
        title="Bảng Đặc Biệt theo năm",
        subtitle="Một tháng soi qua mọi năm: hàng là năm, cột là ngày trong tháng.",
        controls='<div class="sp-controls">'
                 '<label>Tháng <select id="sp-month"></select></label>'
                 '<span class="sp-count" id="sp-count"></span>' + _mark_tools() + '</div>',
        body=FIELD_TOGGLE
             + '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>',
        render="renderSpecialYearByDay",
    ),
    StatPage(
        slug="tan-suat-loto",
        title="Tần suất LOTO",
        subtitle="Ma trận con lô × từng kỳ, đổi được chiều, chọn con để so sánh.",
        controls='<div class="sp-controls">'
                 '<label>Từ ngày <input type="date" id="sp-from"></label>'
                 '<label>Đến ngày <input type="date" id="sp-to"></label>'
                 '<label>Chiều <select id="sp-orient">'
                 '<option>Xem theo chiều ngang</option>'
                 '<option>Xem theo chiều dọc</option></select></label>'
                 + _weekday_filter() + _quick_ranges() + _sort_menu() + _gan_picker() +
                 '<span class="sp-count" id="sp-count"></span>' + _mark_tools() + '</div>',
        body=_gan_modal() +
             '<div class="sp-picker" id="sp-picker"></div>'
             '<p class="sp-matrix-note" id="sp-matrix-note"></p>'
             '<div class="sp-scroll"><table class="sp-table sp-dense sp-grid-lines sp-crosshair" id="sp-matrix-grid"></table></div>'
             '<h3 class="sp-subhead">Xếp hạng trên trọn dải đã chọn</h3>'
             '<div id="sp-matrix" class="sp-matrix"></div>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>',
        render="renderLotoFrequency",
    ),
    StatPage(
        slug="tan-suat-cap-loto",
        title="Tần suất cặp LOTO",
        subtitle="Ma trận 50 họ cặp × từng kỳ, đổi được chiều; kèm bảng đồng xuất hiện.",
        controls='<div class="sp-controls">'
                 '<label>Từ ngày <input type="date" id="sp-from"></label>'
                 '<label>Đến ngày <input type="date" id="sp-to"></label>'
                 '<label>Chiều <select id="sp-orient">'
                 '<option>Xem theo chiều ngang</option>'
                 '<option>Xem theo chiều dọc</option></select></label>'
                 + _weekday_filter() + _quick_ranges() + _sort_menu() + _gan_picker() +
                 '<span class="sp-count" id="sp-count"></span>' + _mark_tools() + '</div>',
        body=_gan_modal() +
             '<p class="sp-matrix-note" id="sp-matrix-note"></p>'
             '<div class="sp-scroll"><table class="sp-table sp-dense sp-grid-lines sp-crosshair" id="sp-matrix-grid"></table></div>'
             '<h3 class="sp-subhead">Cặp đồng xuất hiện nhiều nhất trên trọn dải</h3>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>',
        render="renderPairFrequency",
    ),
    StatPage(
        slug="giai-dac-biet-theo-tong",
        title="Giải Đặc Biệt theo tổng",
        subtitle="Tổng = (Đầu + Đuôi) mod 10. Gan theo tổng, chuyển tổng và chẵn lẻ hôm sau.",
        controls=_range_controls(),
        body='<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>'
             '<h3 class="sp-subhead">Hôm trước tổng X thì hôm sau tổng Y</h3>'
             '<p class="sp-note">Mức ngẫu nhiên là <b>10 %</b> cho mỗi ô, vì tổng chỉ có '
             '10 giá trị. Cột <b>Tỉ lệ</b> quanh 10 % nghĩa là không phân biệt được với '
             'ngẫu nhiên. Bảng xếp theo <b>lệch chuẩn hoá</b> '
             'chứ không theo tỉ lệ: xếp theo tỉ lệ thì một ô 3/9 cho 33 % và đứng đầu bảng, '
             'dù ba lần chẳng nói lên điều gì. Lệch chuẩn hoá chia độ lệch cho sai số chuẩn, '
             'nên chỉ mẫu đủ lớn mới lên được. Quanh ±2 vẫn là mức thường gặp khi xét 100 ô. '
             'Đây là thống kê MÔ TẢ trên lịch sử, '
             'không phải xác suất đã hiệu chuẩn, và chỉ đếm các kỳ LIỀN KỀ thật — ranh giới '
             'ngày nghỉ quay bị bỏ qua thay vì nối lại thành một chuyển tiếp không tồn tại.</p>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-trans"></table></div>'
             '<h3 class="sp-subhead">Chẵn lẻ của tổng hôm sau</h3>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-parity"></table></div>',
        render="renderSpecialByTong",
    ),
    StatPage(
        slug="cau-giai-dac-biet",
        title="Cầu giải Đặc Biệt",
        subtitle="Tần suất hai số cuối giải Đặc Biệt theo Đầu, cặp lộn kèm số lần, ba kỳ gần nhất.",
        controls=_range_controls(),
        body='<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>'
             '<h3 class="sp-subhead">Cặp lộn của giải Đặc Biệt</h3>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-lon"></table></div>'
             '<h3 class="sp-subhead">Ba kỳ gần nhất</h3>'
             '<div id="sp-recent" class="sp-recent"></div>',
        render="renderSpecialBridge",
    ),
    StatPage(
        slug="cap-lon-loto",
        title="Cặp lộn LOTO",
        subtitle="45 cặp lộn thật (đảo hai chữ số), kèm 10 số kép liệt kê riêng.",
        controls=_range_controls(),
        body='<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>'
             '<h3 class="sp-subhead">Số kép — đảo lại chính nó nên không có số lộn</h3>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-kep"></table></div>',
        render="renderReversePairs",
    ),
    StatPage(
        slug="dau-duoi-loto",
        title="Đầu đuôi LOTO",
        subtitle="Phân bố chữ số đầu và chữ số đuôi của toàn bộ LOTO trong dải đã chọn.",
        controls=_range_controls(),
        body='<div class="sp-duo">'
             '<div><h3>Theo chữ số ĐẦU</h3><table class="sp-table sp-grid-lines sp-crosshair" id="sp-head"></table></div>'
             '<div><h3>Theo chữ số ĐUÔI</h3><table class="sp-table sp-grid-lines sp-crosshair" id="sp-tail"></table></div>'
             '</div>'
             '<h3 class="sp-subhead">20 kỳ gần nhất theo chữ số ĐẦU</h3>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-head"></table></div>'
             '<h3 class="sp-subhead">20 kỳ gần nhất theo chữ số ĐUÔI (đít)</h3>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-tail"></table></div>'
             '<h3 class="sp-subhead">20 kỳ gần nhất theo TỔNG</h3>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-sum"></table></div>',
        render="renderHeadTail",
    ),
    StatPage(
        slug="lo-gan",
        title="Lô gan miền Bắc",
        subtitle="Số kỳ chưa về của từng con LOTO, gan cực đại trong lịch sử, và cặp lô gan.",
        controls=_range_controls(mode="preset"),
        body='<p class="sp-note">Gan đếm theo <b>kỳ quay</b>, không theo ngày lịch: '
             'XSMB nghỉ Tết và nghỉ 01–22/04/2020, đếm theo ngày lịch sẽ thổi phồng '
             'gan của mọi con ngay sau mỗi đợt nghỉ. Cột <b>Gan cực đại</b> chỉ tính '
             'trong kho lịch sử của trang này, nên có thể lệch với trang khác có '
             'lịch sử dài ngắn khác.</p>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>'
             '<h3 class="sp-subhead">Gan cực đại từ trước đến nay, cả 00–99</h3>'
             '<div class="sp-duo">'
             '<div><table class="sp-table sp-grid-lines sp-crosshair" id="sp-max-lo"></table></div>'
             '<div><table class="sp-table sp-grid-lines sp-crosshair" id="sp-max-hi"></table></div>'
             '</div>'
             '<h3 class="sp-subhead">Cặp lô gan — cặp về khi một trong hai con có mặt trong kỳ</h3>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-pair-gan"></table></div>',
        render="renderLoGan",
    ),
    StatPage(
        slug="chu-ky-dac-biet",
        title="Chu kỳ giải Đặc Biệt",
        subtitle="Số kỳ chưa về của từng con 00–99 ở giải Đặc Biệt, và chu kỳ dài nhất trong lịch sử.",
        controls=_range_controls(mode="preset"),
        body='<p class="sp-note">Đếm theo <b>kỳ quay</b>, không theo ngày lịch, nên số ở '
             'đây nhỏ hơn trang nào đếm theo ngày. Ví dụ đối chiếu được: con 98 ra lần cuối '
             '17-02-2025, tới 09-09-2026 là 569 ngày lịch, trừ 4 ngày Tết 2026 không quay '
             'còn <b>565 kỳ</b> — đúng con số cột "Chưa về".</p>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>',
        render="renderSpecialCycle",
    ),
    StatPage(
        slug="cau-dac-biet-theo-bo-so",
        title="Cầu giải Đặc Biệt theo bộ số",
        subtitle="Điểm rơi của từng bộ số ở giải Đặc Biệt: lần về gần nhất, khoảng cách và số lần.",
        controls=_range_controls(mode="preset"),
        body='<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>',
        render="renderSpecialBySet",
    ),
    StatPage(
        slug="giai-db-ngay-mai",
        title="Giải Đặc Biệt ngày mai",
        subtitle="Xếp hạng tham khảo cho kỳ kế tiếp, dựng từ chu kỳ và tần suất lịch sử.",
        controls=_range_controls(mode="preset"),
        body='<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>',
        render="renderTomorrow",
    ),
    StatPage(
        slug="thong-ke-tong-hop",
        title="Thống kê tổng hợp",
        subtitle="Bảng tổng hợp đa chiều: tần suất, chu kỳ gan, đầu đuôi và tổng trên cùng một dải.",
        controls=_range_controls(),
        body='<div id="sp-kpi" class="sp-kpi"></div>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>',
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
        "Kỳ vọng tổng số nháy mỗi con là <b>27/100 = 0,27 nháy/kỳ</b>. "
        "Xác suất về ít nhất một lần là 1 − (0,99)²⁷ ≈ 23,77% mỗi kỳ. Con dẫn đầu "
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
        "Giải Đặc Biệt có 100 kết quả hai số nên khoảng gan trung bình là 100 "
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
    """50 họ cặp LOTO, lấy từ ``number_reference.all_cap_loto_50``.

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

    Trang tham chiếu hiển thị cột này trong mỗi ô bảng Đặc Biệt; đo trên 24 ô
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



def frequency_bento_layout(page: StatPage, note_html: str) -> str:
    """Bento layout for the two frequency pages; controls keep existing IDs."""
    pairs = page.slug == "tan-suat-cap-loto"
    label = "cặp số" if pairs else "số lô tô"
    picker = (
        '<div id="bf-pair-picker"></div>' if pairs
        else '<div class="sp-picker" id="sp-picker"></div>'
    )
    matrix = "Tổng quan 00–99" if not pairs else "Đọc ma trận cặp số"
    overview = (
        '<div id="sp-matrix" class="sp-matrix"></div>' if not pairs
        else '<p>Mỗi ô cộng số lần xuất hiện của hai thành viên trong cùng kỳ. '
             'Ví dụ 12 về 2 lần và 21 về 1 lần: ô 12–21 hiển thị <b>3</b>.</p>'
             '<p>Ngôi sao đỏ cho biết một thành viên là hai số cuối Giải Đặc Biệt. '
             '50 họ gồm 45 cặp đảo và 5 cặp kép bóng.</p>'
             '<p>Bảng đồng xuất hiện tính số kỳ <b>cả hai số cùng về</b>, '
             'trên toàn bộ 4.950 cặp khác nhau.</p>'
    )
    return f"""
<div class="bf-topline"><a href="index.html">← Trang chính</a><span class="bf-live" id="bf-source">Dữ liệu XSMB · Miền Bắc</span></div>
<header class="bf-hero">
  <div><p class="bf-eyebrow">THỐNG KÊ / MIỀN BẮC</p><h1>{page.title}</h1>
  <p>Nhìn rõ từng nhịp số. So sánh tần suất theo ngày trong một không gian gọn gàng.</p></div>
  <a class="bf-demo-link" id="bf-demo-link" href="?demo=1">Xem dữ liệu minh họa ↗</a>
</header>
<nav class="bf-tabs" aria-label="Loại thống kê">
  <a href="tan-suat-loto.html" {'aria-current="page"' if not pairs else ''}>Tần suất lô tô <span>00–99</span></a>
  <a href="tan-suat-cap-loto.html" {'aria-current="page"' if pairs else ''}>Tần suất cặp <span>50 họ cặp</span></a>
</nav>
<div id="bf-demo-banner" class="bf-demo-banner" hidden>DỮ LIỆU MINH HỌA · Các kỳ và kết quả được giả lập để kiểm tra giao diện.</div>
<section class="bf-kpis" aria-label="Tổng quan dải đã chọn" id="bf-kpis"></section>
<section class="bf-card bf-filters" aria-labelledby="bf-filter-title">
  <div class="bf-card-heading"><div><span class="bf-step">01</span><h2 id="bf-filter-title">Bộ lọc &amp; lựa chọn</h2></div><span>Cập nhật ngay khi thay đổi</span></div>
  {page.controls}
  <details class="bf-selection"><summary>Chọn {label} để so sánh <span id="bf-selection-count"></span></summary>{picker}</details>
</section>
<section class="bf-card bf-matrix-card" aria-labelledby="bf-matrix-title">
  <div class="bf-card-heading"><div><span class="bf-step">02</span><h2 id="bf-matrix-title">Ma trận tần suất</h2></div><span id="sp-matrix-note" class="sp-matrix-note"></span></div>
  <div class="bf-legend" aria-label="Chú thích số nháy">
    <span><i class="bf-swatch is-empty"></i>Không về</span>
    <span><i class="bf-swatch sp-n1">1</i>1 nháy</span>
    <span><i class="bf-swatch sp-n2">2</i>2 nháy</span>
    <span><i class="bf-swatch sp-n3">3</i>3 nháy</span>
    <span><i class="bf-swatch sp-n4">4</i>4 nháy</span>
    <span><i class="bf-swatch sp-n5">5+</i>≥ 5 nháy</span>
    <span><i class="bf-swatch sp-de-hit">★</i>Đặc Biệt · ưu tiên</span>
    <span><i class="bf-swatch bf-wait">…</i>Chờ kết quả</span>
  </div>
  <div class="sp-scroll bf-matrix-scroll" role="region" aria-label="Ma trận cuộn ngang và dọc" tabindex="0">
    <table class="sp-table sp-dense sp-grid-lines sp-crosshair" id="sp-matrix-grid" aria-label="Ma trận tần suất theo ngày"></table>
  </div>
  <div class="bf-matrix-footer"><span id="bf-cell-status" role="status" aria-live="polite">Rê chuột hoặc chạm vào ô để dóng hàng và cột.</span><span>↔ Cuộn để xem thêm · Phím mũi tên để di chuyển</span></div>
</section>
<div class="bf-bottom">
  <section class="bf-card bf-ranking"><div class="bf-card-heading"><div><span class="bf-step">03</span><h2>{'Xếp hạng đồng xuất hiện' if pairs else 'Xếp hạng tần suất'}</h2></div><span>Trọn dải đã chọn</span></div>
    <div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>
  </section>
  <aside class="bf-card bf-summary"><div class="bf-card-heading"><h2>{matrix}</h2></div>{overview}
    <details class="bf-method"><summary>Cách đọc &amp; mốc so sánh</summary>{note_html}</details>
    <p class="bf-tip">★ Màu Đặc Biệt luôn ưu tiên, kể cả khi số về nhiều nháy. Số trong ô vẫn là tổng số nháy.</p>
  </aside>
</div>
{_gan_modal()}
"""

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
    bento = page.slug in {"tan-suat-loto", "tan-suat-cap-loto"}
    content = frequency_bento_layout(page, note_html) if bento else f"""
<div style="margin-bottom:1rem"><a href="index.html">← Trang chính</a></div>
<h1>{page.title}</h1>
<p class="ui-muted" style="max-width:60rem;line-height:1.65">{page.subtitle}</p>
{page.controls}
{page.body}
{note_html}"""
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{security_meta_tags()}
{stylesheet_link()}
<title>{page.title}</title>
<style>
{_asset("stat_pages.css")}
{_asset("frequency_bento.css") if bento else ""}
</style></head><body class="{'bf-page' if bento else ''}">
{app_shell_open(f"{page.slug}.html", wide=True)}
{content}
<p class="ui-muted" style="margin-top:1.5rem;font-size:.75rem">
Dựng lúc {generated}. Toàn bộ tính toán chạy trong trình duyệt trên
{len(draws)} kỳ đã nhúng — không gọi mạng, không máy chủ.</p>
{app_shell_close(f"{page.slug}.html")}
<script>window.__D_DRAWS__={json_for_html_script(draws)};
window.__D_PAIR_CHANCE__={json_for_html_script(pair_chance_grid())};
window.__D_BO__={json_for_html_script(bo_lookup())};
window.__D_CAP50__={json_for_html_script(cap_loto_50())};</script>
<script>
{_asset("frequency_demo.js") if bento else ""}
{_asset("stat_pages.js")}
{_asset("frequency_bento.js") if bento else ""}
{f'installFrequencyBento({json.dumps(page.render)});' if bento else ""}
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
        write_page(target, render_page(page, draws, generated=generated))
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
