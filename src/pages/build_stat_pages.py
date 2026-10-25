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
import html
import json
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

import pandas as pd

from core.number_reference import all_cap_loto_50, bo_family_id
from web.ui_theme import app_shell_close, app_shell_open, stylesheet_link
from core.xsmb_domain import (
    LOTO_BASELINE_RATE,
    PAIR_COOCCURRENCE_RATE,
    pair_chance_maximum,
)
from web.web_security import json_for_html_script, security_meta_tags
from web.page_output import write_page
from core.paths import REPO_ROOT, TEMPLATES

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


def _range_controls(*, mode: str = "day", pairs: bool = True, weekday: bool = False) -> str:
    """Thanh chọn dải thời gian.

    Args:
        mode: ``day`` cho hai ô chọn ngày, ``preset`` cho các nút nhanh.
        pairs: Có ô tick "Tự động đánh dấu cặp trùng" hay không. Đặt ``False``
            cho trang mà không ô nào mang số hai chữ số.
        weekday: Thêm bộ lọc thứ trong dải ngày cho trang tổng hợp.

    Returns:
        Chuỗi HTML.
    """
    # Nút nào đang thật sự có hiệu lực phụ thuộc vào kiểu thanh điều khiển.
    # Trang kiểu ``day`` có hai ô ngày, và stat_pages.js đặt sẵn chúng ở
    # ``DRAWS.length - 90``. Trang kiểu ``preset`` đọc mốc từ nút đang chọn,
    # mặc định là toàn bộ lịch sử.
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
            f'{presets}</div><span class="sp-count" id="sp-count" data-evidence-split></span>'
            f"{_mark_tools(pairs=pairs)}</div>"
            '<p class="sp-note">Thống kê trong dải kỳ đang chọn. Nếu một số '
            'chưa xuất hiện trong dải, số kỳ chưa về thực tế có thể dài hơn dải này. '
            'Bảng ghi “từ trước đến nay” dùng toàn bộ lịch sử.</p>'
        )
    return f"""
    <div class="sp-controls">
      <label>Từ ngày <input type="date" id="sp-from"></label>
      <label>Đến ngày <input type="date" id="sp-to"></label>
      {_weekday_filter() if weekday else ""}
      <div class="sp-chips">{presets}</div>
      <span class="sp-count" id="sp-count" data-evidence-split></span>
      {_mark_tools(pairs=pairs)}
    </div>
    """


def _mark_tools(*, pairs: bool = True) -> str:
    """Thanh đánh dấu ô, dùng chung cho mọi trang.

    Bảng ở đây dài hàng chục hàng và người đọc thường dõi theo vài ô rời rạc —
    ví dụ cùng một ngày qua nhiều tháng. Không có cách đánh dấu thì chỉ cần
    cuộn một cái là mất dấu.

    Args:
        pairs: Có ô tick "Tự động đánh dấu cặp trùng" hay không.

            Ô tick ấy đánh dấu MỌI ô mang cùng số hai chữ số. Trang Đầu/Đuôi
            và trang theo Tổng chỉ có chữ số đơn 0-9, nên ở đó nó không thể
            làm gì — và một nút bấm vào không thấy gì xảy ra thì tệ hơn là
            không có nút. Bày ra ở đó chính là lỗi người dùng đã báo.

    Returns:
        Chuỗi HTML của thanh công cụ.
    """
    pair_box = (
        '<label class="sp-chip sp-chip-check">'
        '<input type="checkbox" id="sp-pair-mode">'
        '<span>Tự động đánh dấu cặp trùng</span></label>'
    ) if pairs else ""
    return (
        '<span class="sp-marktools">'
        '<span class="sp-hint">Bấm vào ô bất kỳ để đánh dấu so sánh</span>'
        f'{pair_box}'
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


#: Mốc ngày nhanh, gồm dải ngắn và trọn năm cho bảng co giãn.
QUICK_RANGES: tuple[tuple[str, str], ...] = (
    ("10", "10 ngày"), ("30", "30 ngày"), ("60", "60 ngày"), ("90", "90 ngày"),
    ("100", "100 ngày"), ("200", "200 ngày"), ("300", "300 ngày"),
    ("365", "365 ngày"),
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
        '<dialog class="sp-gan-modal" id="sp-gan-modal" aria-labelledby="sp-gan-title" hidden>'
        '<div class="sp-modal-card">'
        '<div class="sp-modal-head"><b class="sp-modal-title" id="sp-gan-title"></b>'
        '<button type="button" class="sp-btn" data-close>Đóng</button></div>'
        '<div class="sp-modal-body"></div></div></dialog>'
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

def _tomorrow_controls() -> str:
    """Chọn đúng hai số cuối và phạm vi các ngày từng xuất hiện."""
    options = "".join(f'<option value="{n:02d}">{n:02d}</option>' for n in range(100))
    ranges = _range_controls(mode="preset").split('<p class="sp-note">', 1)[0]
    return ('<section class="app-tomorrow-controls" aria-label="Tra cứu Đặc Biệt hôm sau">'
            '<div class="app-tomorrow-pick"><label for="sp-tomorrow-number">Đặc Biệt đã về số</label>'
            f'<select id="sp-tomorrow-number">{options}</select>'
            '<button type="button" id="sp-tomorrow-latest" class="sp-btn">Số kỳ mới nhất</button>'
            '<span>Tra theo hai số cuối · 00–99</span></div>' + ranges + '</section>')


SPECIAL_STAT_PAGES = (
    ("cau-giai-dac-biet", "Tần suất"),
    ("giai-dac-biet-theo-tong", "Theo tổng"),
    ("cau-dac-biet-theo-bo-so", "Theo từng số"),
    ("chu-ky-dac-biet", "Chu kỳ"),
)


LOTO_STAT_PAGES = (
    ("dau-duoi-loto", "Đầu đuôi"),
    ("cap-lon-loto", "Cặp lộn"),
    ("lo-gan", "Lô gan"),
)


def _loto_table(ident: str, label: str) -> str:
    """Tên vùng cuộn giữ ngữ cảnh của bảng khi dùng bàn phím."""
    return (f'<div class="sp-scroll" tabindex="0" role="region" aria-label="{html.escape(label)}">'
            f'<table class="sp-table sp-grid-lines sp-crosshair" id="{ident}" '
            f'aria-label="{html.escape(label)}"></table></div>')


def _loto_panel(ident: str, title: str, description: str, body: str, *, extra_class: str = "") -> str:
    """Đặt định nghĩa và phạm vi ngay trước những con số cần đọc."""
    return (f'<section class="app-lotostats-panel{(" " + extra_class) if extra_class else ""}" '
            f'aria-labelledby="{ident}"><header><h2 id="{ident}">{title}</h2>'
            f'<p>{description}</p></header>{body}</section>')


def _loto_stat_layout(page: StatPage) -> str:
    """Ba lối đọc LOTO dùng cùng đường đi từ bộ lọc đến bảng dữ liệu."""
    nav = ''.join(
        f'<a href="{slug}.html"' + (' aria-current="page"' if slug == page.slug else '')
        + f'>{label}</a>' for slug, label in LOTO_STAT_PAGES
    )
    controls, _, range_note = page.controls.partition('<p class="sp-note">')
    range_note = '<p class="sp-note">' + range_note if range_note else ''
    method = {
        "dau-duoi-loto": '<p>Mỗi kỳ có 27 số LOTO. Đầu là chữ số hàng chục, Đuôi là hàng đơn vị; '
                         'Tổng là (Đầu + Đuôi) chia lấy dư 10. Tỉ lệ lấy số lượt chia cho tổng lượt trong dải. '
                         'Ba bảng theo kỳ giữ tối đa 20 kỳ mới nhất thuộc bộ lọc.</p>',
        "cap-lon-loto": '<p>Mỗi lượt xuất hiện đều được cộng, kể cả một số về nhiều lần trong cùng kỳ. '
                        'Tổng lượt bằng Lượt thuận + Lượt lộn; Chênh lệch bằng Lượt thuận − Lượt lộn. '
                        '45 cặp được xếp theo Tổng lượt giảm dần. Số kép được xếp theo số lần về.</p>',
        "lo-gan": '<p>Gan đếm theo <b>kỳ quay</b>, không theo ngày lịch: các ngày nghỉ không được cộng thêm. '
                  'Gan hiện tại là số kỳ kể từ lần xuất hiện gần nhất. Gan cực đại là khoảng cách giữa '
                  'hai lần xuất hiện đã ghi nhận; dấu — nghĩa là chưa đủ hai lần. '
                  'Một số về nhiều nháy vẫn chỉ được tính một lần có mặt trong kỳ.</p>',
    }[page.slug]
    return (f'<div class="app-lotostats-shell" data-app-workspace-guide data-stat-view="{page.slug}">'
            '<header class="app-lotostats-header"><p>Thống kê LOTO</p>'
            f'<h1>{page.title}</h1><p>{page.subtitle}</p></header>'
            f'<nav class="app-lotostats-nav" aria-label="Thống kê LOTO">{nav}</nav>'
            '<section class="app-lotostats-filters" aria-label="Chọn phạm vi thống kê">'
            '<h2>Chọn phạm vi</h2>' + controls + '</section>' + page.body
            + '<details class="app-lotostats-method"><summary>Cách đọc và phạm vi thống kê</summary>'
            + method + range_note + '<p>Đây là thống kê lịch sử. Số lượt nhiều hoặc khoảng chưa về dài '
            'không phải xác suất dự báo cho kỳ tới.</p></details></div>')


def _special_table(ident: str, label: str, *, matrix: bool = False) -> str:
    """Bảng thật có vùng cuộn mang tên và nhận được tiêu điểm bàn phím."""
    return (f'<div class="sp-scroll{" app-special-matrix" if matrix else ""}" tabindex="0" '
            f'role="region" aria-label="{html.escape(label)}">'
            f'<table class="sp-table sp-grid-lines sp-crosshair" id="{ident}" '
            f'aria-label="{html.escape(label)}"></table></div>')


def _special_panel(ident: str, title: str, description: str, body: str) -> str:
    """Tiêu đề và đơn vị luôn đứng cùng bảng mà chúng giải thích."""
    return (f'<section class="app-specialstats-panel" aria-labelledby="{ident}">'
            f'<header><h2 id="{ident}">{title}</h2><p>{description}</p></header>{body}</section>')


def _special_stat_layout(page: StatPage, note_html: str) -> str:
    """Bốn lối xem cùng một miền dữ liệu; hướng dẫn chi tiết đứng sau bảng."""
    nav = ''.join(
        f'<a href="{slug}.html"' + (' aria-current="page"' if slug == page.slug else '')
        + f'>{label}</a>' for slug, label in SPECIAL_STAT_PAGES
    )
    controls, _, range_note = page.controls.partition('<p class="sp-note">')
    range_note = '<p class="sp-note">' + range_note if range_note else ''
    cycle_note = (
        '<p class="sp-note">Đếm theo <b>kỳ quay trong dải đã chọn</b>, không theo ngày lịch; '
        'những ngày nghỉ quay không được tính thêm vào chu kỳ. '
        'Chu kỳ dài nhất là khoảng cách giữa hai lần về đã ghi nhận; dấu — nghĩa là chưa đủ hai lần.</p>'
        if page.slug in {"chu-ky-dac-biet", "cau-dac-biet-theo-bo-so"} else ''
    )
    method = '' if page.slug == "giai-dac-biet-theo-tong" else (
        '<details class="app-specialstats-method"><summary>Cách đọc và phạm vi thống kê</summary>'
        + cycle_note + range_note + note_html
        + '<p>Đây là thống kê lịch sử trong phạm vi được ghi ở từng bảng. '
        'Số lượt nhiều hoặc khoảng chưa về dài không phải xác suất dự báo cho kỳ tới.</p></details>'
    )
    return (f'<div class="app-specialstats-shell" data-app-workspace-guide data-stat-view="{page.slug}">'
            '<header class="app-specialstats-header"><p>Thống kê Đặc Biệt</p>'
            f'<h1>{page.title}</h1><p>{page.subtitle}</p></header>'
            f'<nav class="app-specialstats-nav" aria-label="Thống kê Đặc Biệt">{nav}</nav>'
            '<section class="app-specialstats-filters" aria-label="Chọn phạm vi thống kê">'
            '<h2>Chọn phạm vi</h2>' + controls + '</section>'
            + page.body + method + '</div>')


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
                 '<span class="sp-count" id="sp-count" data-evidence-split></span>' + _mark_tools() + '</div>',
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
                 '<span class="sp-count" id="sp-count" data-evidence-split></span>' + _mark_tools() + '</div>',
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
                 '<label>Hiển thị <select id="sp-orient">'
                 '<option value="Xem theo chiều ngang">Số theo hàng</option>'
                 '<option value="Xem theo chiều dọc">Ngày theo hàng</option></select></label>'
                 + _weekday_filter() + _quick_ranges() + _sort_menu() + _gan_picker() +
                 '<span class="sp-count" id="sp-count" data-evidence-split></span>' + _mark_tools() + '</div>',
        body=_gan_modal() +
             '<div class="sp-picker" id="sp-picker"></div>'
             '<p class="sp-matrix-note" id="sp-matrix-note" data-evidence-split></p>'
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
                 '<label>Hiển thị <select id="sp-orient">'
                 '<option value="Xem theo chiều ngang">Cặp theo hàng</option>'
                 '<option value="Xem theo chiều dọc">Ngày theo hàng</option></select></label>'
                 + _weekday_filter() + _quick_ranges() + _sort_menu() + _gan_picker() +
                 '<span class="sp-count" id="sp-count" data-evidence-split></span>' + _mark_tools() + '</div>',
        body=_gan_modal() +
             '<p class="sp-matrix-note" id="sp-matrix-note" data-evidence-split></p>'
             '<div class="sp-scroll"><table class="sp-table sp-dense sp-grid-lines sp-crosshair" id="sp-matrix-grid"></table></div>'
             '<h3 class="sp-subhead">Cặp đồng xuất hiện nhiều nhất trên trọn dải</h3>'
             '<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid"></table></div>',
        render="renderPairFrequency",
    ),
    StatPage(
        slug="giai-dac-biet-theo-tong",
        title="Giải Đặc Biệt theo tổng",
        subtitle="Tổng là chữ số cuối của đầu + đuôi. Ví dụ: 78 có tổng 5.",
        controls=_range_controls(pairs=False),
        body='<div class="app-specialstats-pair">'
             + _special_panel("app-total-gap-title", "Khoảng cách của 10 tổng",
                              "Sắp theo số kỳ chưa về, từ dài đến ngắn. Màu cam đậm hơn = khoảng chưa về dài hơn.",
                              '<div class="app-specialstats-legend" id="app-special-gap-legend"></div>'
                              '<div class="app-specialstats-legend" id="app-special-total-frequency-legend"></div>'
                              + _special_table("sp-grid", "Khoảng cách và số lần xuất hiện theo tổng"))
             + _special_panel("app-total-parity-title", "Chẵn lẻ của tổng hôm sau",
                              "Tỷ lệ lịch sử, chỉ đếm hai ngày liền nhau đã có kết quả.",
                              '<div class="app-specialstats-legend"><span class="app-stat-parity-even">Chẵn: 0, 2, 4, 6, 8</span>'
                              '<span class="app-stat-parity-odd">Lẻ: 1, 3, 5, 7, 9</span></div>'
                              + _special_table("sp-parity", "Tỷ lệ tổng chẵn và lẻ của ngày hôm sau"))
             + '</div>'
             + _special_panel("app-total-transition-title", "Tổng hôm trước → tổng hôm sau",
                              "40 chuyển tiếp lệch nhiều nhất so với mốc 10 %, xếp theo độ lệch chuẩn hoá. Đây là thống kê lịch sử.",
                              '<div class="app-specialstats-legend" id="app-special-transition-legend"></div>'
                              + _special_table("sp-trans", "Số lượt chuyển tổng giữa hai ngày liền nhau"))
             + '<details class="app-specialstats-method"><summary>Cách đọc bảng tổng và chuyển tiếp</summary>'
             '<p class="sp-note">Mức ngẫu nhiên là <b>10 %</b> cho mỗi ô, vì tổng chỉ có '
             '10 giá trị. Cột <b>Tỉ lệ</b> quanh 10 % nghĩa là không phân biệt được với '
             'ngẫu nhiên. Bảng xếp theo <b>lệch chuẩn hoá</b> '
             'chứ không theo tỉ lệ: xếp theo tỉ lệ thì một ô 3/9 cho 33 % và đứng đầu bảng, '
             'dù ba lần chẳng nói lên điều gì. Lệch chuẩn hoá chia độ lệch cho sai số chuẩn, '
             'nên chỉ mẫu đủ lớn mới lên được. Quanh ±2 vẫn là mức thường gặp khi xét 100 ô. '
             'Đây là thống kê MÔ TẢ trên lịch sử, '
             'không phải xác suất đã hiệu chuẩn, và chỉ đếm các kỳ LIỀN KỀ thật — ranh giới '
             'ngày nghỉ quay bị bỏ qua thay vì nối lại thành một chuyển tiếp không tồn tại.</p></details>',
        render="renderSpecialByTong",
    ),
    StatPage(
        slug="cau-giai-dac-biet",
        title="Tần suất hai số cuối Đặc Biệt",
        subtitle="Xem mỗi số 00–99 đã xuất hiện bao nhiêu lần trong dải kỳ đã chọn.",
        controls=_range_controls(),
        body=_special_panel("app-special-frequency-title", "100 số theo đầu và đuôi",
                            "Hàng là chữ số đầu, cột là chữ số đuôi. Mỗi ô ghi số và lượt xuất hiện; màu đỏ đậm hơn = nhiều lượt hơn.",
                            '<div class="app-specialstats-legend" id="app-special-frequency-legend"></div>'
                            + _special_table("sp-grid", "Tần suất 100 số Đặc Biệt theo đầu và đuôi", matrix=True))
             + _special_panel("app-special-reverse-title", "Cặp số đảo nhau",
                              "Cộng lượt của hai số trong cặp, xếp từ nhiều đến ít. Số kép không thuộc danh sách này.",
                              '<div class="app-specialstats-legend" id="app-special-reverse-legend"></div>'
                              + _special_table("sp-lon", "Cặp lộn Đặc Biệt theo tổng lượt xuất hiện"))
             + '<details class="app-specialstats-recent"><summary>Ba kỳ gần nhất · toàn bộ lịch sử</summary>'
             '<p>Phần đối chiếu này giữ ba kỳ mới nhất, không thay đổi theo bộ lọc ở trên.</p>'
             '<div id="sp-recent" class="sp-recent"></div></details>',
        render="renderSpecialBridge",
    ),
    StatPage(
        slug="cap-lon-loto",
        title="Cặp lộn LOTO",
        subtitle="45 cặp lộn thật (đảo hai chữ số), kèm 10 số kép liệt kê riêng.",
        controls=_range_controls(),
        body='<div class="app-lotostats-legend" id="app-loto-reverse-frequency-legend" '
             'aria-label="Thang màu số lượt của cặp lộn và số kép"></div>'
             '<div class="app-lotostats-reverse app-reverse-layout">'
             + _loto_panel("app-reverse-title", "45 cặp lộn",
                           "Trong dải đã chọn · Lượt thuận / lộn ứng với số bên trái / bên phải. Xếp theo Tổng lượt.",
                           _loto_table("sp-grid", "45 cặp lộn theo tổng lượt trong dải đã chọn"),
                           extra_class="app-reverse-card")
             + _loto_panel("app-double-title", "10 số kép",
                           "Trong dải đã chọn · Đảo hai chữ số vẫn giữ nguyên. Xếp theo số lần về.",
                           _loto_table("sp-kep", "10 số kép theo số lần về trong dải đã chọn"),
                           extra_class="app-reverse-card") + '</div>',
        render="renderReversePairs",
    ),
    StatPage(
        slug="dau-duoi-loto",
        title="Đầu đuôi LOTO",
        subtitle="Phân bố chữ số đầu và chữ số đuôi của toàn bộ LOTO trong dải đã chọn.",
        controls=_range_controls(pairs=False),
        body='<section class="app-lotostats-summary" aria-labelledby="app-loto-summary-title">'
             '<header><h2 id="app-loto-summary-title">Phân bố trong dải đã chọn</h2>'
             '<p>Tổng lượt của 27 số mỗi kỳ · Đầu và Đuôi cùng thang màu để đối chiếu.</p></header>'
             '<div id="app-head-tail-legend" class="app-head-tail-legend" aria-label="Thang màu tổng lượt Đầu và Đuôi"></div>'
             '<div class="app-lotostats-duo">'
             + _loto_panel("app-loto-head-title", "Theo chữ số Đầu", "Chữ số hàng chục của từng số LOTO.",
                           _loto_table("sp-head", "Phân bố chữ số đầu trong dải đã chọn"))
             + _loto_panel("app-loto-tail-title", "Theo chữ số Đuôi", "Chữ số hàng đơn vị của từng số LOTO.",
                           _loto_table("sp-tail", "Phân bố chữ số đuôi trong dải đã chọn"))
             + '</div></section>'
             '<section class="app-lotostats-daily" aria-labelledby="app-loto-daily-title">'
             '<header><h2 id="app-loto-daily-title">20 kỳ gần nhất trong dải</h2>'
             '<p>Mỗi hàng là một kỳ, mỗi ô là số lần chữ số xuất hiện. Kỳ mới nhất đứng trước.</p></header>'
             '<div id="app-head-tail-day-legend" class="app-head-tail-legend" aria-label="Thang màu số nháy từng kỳ"></div>'
             + _loto_panel("app-loto-day-head-title", "Theo chữ số Đầu", "Dùng chung thang màu với bảng Đuôi theo kỳ.",
                           _loto_table("sp-day-head", "20 kỳ gần nhất theo chữ số đầu"))
             + _loto_panel("app-loto-day-tail-title", "Theo chữ số Đuôi", "Dùng chung thang màu với bảng Đầu theo kỳ.",
                           _loto_table("sp-day-tail", "20 kỳ gần nhất theo chữ số đuôi"))
             + _loto_panel("app-loto-day-sum-title", "Theo Tổng", "Tổng = (Đầu + Đuôi) chia lấy dư 10. Đọc số lượt trực tiếp trong từng ô.",
                           _loto_table("sp-day-sum", "20 kỳ gần nhất theo tổng chữ số")) + '</section>',
        render="renderHeadTail",
    ),
    StatPage(
        slug="lo-gan",
        title="Lô gan miền Bắc",
        subtitle="Số kỳ chưa về của từng con LOTO, gan cực đại trong lịch sử, và cặp lô gan.",
        controls=_range_controls(mode="preset"),
        body=_loto_panel("app-loto-current-title", "Lô gan hiện tại",
                         "Trong dải đã chọn · Xếp theo số kỳ chưa về. Gan cực đại cũng tính trong dải này. Đơn vị: kỳ quay.",
                         '<div class="app-lotostats-legend" id="app-loto-current-gap-legend"></div>'
                         '<div class="app-lotostats-legend" id="app-loto-current-cycle-legend"></div>'
                         '<div class="app-lotostats-legend" id="app-loto-current-frequency-legend"></div>'
                         + _loto_table("sp-grid", "Gan hiện tại của 100 số LOTO trong dải đã chọn"))
             + '<section class="app-lotostats-history" aria-labelledby="app-loto-history-title">'
             '<header><h2 id="app-loto-history-title">Gan cực đại từ trước đến nay</h2>'
             '<p>Toàn bộ lịch sử · Hai nửa 00–49 và 50–99 dùng chung thang màu. '
             'Giữ nguyên khi đổi phạm vi lọc. Dấu —: chưa đủ hai lần xuất hiện.</p></header>'
             '<div class="app-lotostats-legend" id="app-loto-history-cycle-legend"></div>'
             '<div class="app-lotostats-duo">'
             + _loto_panel("app-loto-max-lo-title", "Bộ số 00–49", "Chu kỳ dài nhất đã ghi nhận · đơn vị kỳ quay.",
                           _loto_table("sp-max-lo", "Gan cực đại toàn bộ lịch sử của bộ số 00 đến 49"))
             + _loto_panel("app-loto-max-hi-title", "Bộ số 50–99", "Chu kỳ dài nhất đã ghi nhận · đơn vị kỳ quay.",
                           _loto_table("sp-max-hi", "Gan cực đại toàn bộ lịch sử của bộ số 50 đến 99"))
             + '</div></section>'
             + _loto_panel("app-loto-pair-gan-title", "Cặp lô gan",
                           "Trong dải đã chọn · Cặp về khi một trong hai con có mặt trong kỳ. Xếp theo số kỳ chưa về.",
                           '<div class="app-lotostats-legend" id="app-loto-pair-gap-legend"></div>'
                           '<div class="app-lotostats-legend" id="app-loto-pair-cycle-legend"></div>'
                           '<div class="app-lotostats-legend" id="app-loto-pair-frequency-legend"></div>'
                           + _loto_table("sp-pair-gan", "Gan hiện tại của 50 họ cặp trong dải đã chọn")),
        render="renderLoGan",
    ),
    StatPage(
        slug="chu-ky-dac-biet",
        title="Chu kỳ giải Đặc Biệt",
        subtitle="So sánh số kỳ chưa về với chu kỳ dài nhất của từng số 00–99.",
        controls=_range_controls(mode="preset"),
        body=_special_panel("app-special-cycle-title", "Xếp hạng theo số kỳ chưa về",
                            "Cả 100 số, sắp từ khoảng chưa về dài đến ngắn. Đơn vị: kỳ quay trong dải đang chọn.",
                            '<div class="app-specialstats-legend" id="app-special-gap-legend"></div>'
                            + _special_table("sp-grid", "Chu kỳ và số kỳ chưa về của 100 số Đặc Biệt")),
        render="renderSpecialCycle",
    ),
    StatPage(
        slug="cau-dac-biet-theo-bo-so",
        title="Đặc Biệt theo từng số",
        subtitle="Mỗi hàng là một số 00–99: lần về gần nhất, khoảng chưa về và tổng lượt xuất hiện.",
        controls=_range_controls(mode="preset"),
        body=_special_panel("app-special-number-title", "Lịch sử của từng số",
                            "Sắp theo số kỳ chưa về, từ dài đến ngắn. “Chưa về trong dải” chỉ nói về phạm vi đang chọn.",
                            '<div class="app-specialstats-legend" id="app-special-gap-legend"></div>'
                            + _special_table("sp-grid", "Lần xuất hiện và khoảng chưa về của từng số Đặc Biệt")),
        render="renderSpecialBySet",
    ),
    StatPage(
        slug="giai-db-ngay-mai",
        title="Giải Đặc Biệt ngày mai",
        subtitle="Đối chiếu Đặc Biệt đủ 5 chữ số và LOTO cùng ngày, kèm kết quả ngày lịch hôm sau.",
        controls=_tomorrow_controls(),
        body='<p id="sp-tomorrow-summary" class="app-tomorrow-summary" role="status" aria-live="polite"></p>'
             '<div class="app-tomorrow-workspace"><section class="app-tomorrow-card app-tomorrow-history">'
             '<header><h2 id="sp-tomorrow-heading">Lịch sử cùng số</h2><span>Mới nhất → cũ nhất</span></header>'
             '<div class="sp-scroll" tabindex="0" role="region" aria-label="Lịch sử Đặc Biệt và LOTO, cuộn để xem thêm">'
             '<table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid" '
             'aria-label="Đặc Biệt và LOTO cùng ngày, đối chiếu ngày lịch hôm sau"></table></div></section>'
             '<aside class="app-tomorrow-card app-tomorrow-stat"><header><h2>Hôm sau thường gặp</h2></header>'
             '<p id="sp-tomorrow-frequency-note"></p>'
             '<div id="sp-tomorrow-frequencies" class="app-tomorrow-frequencies"></div>'
             '<p class="app-tomorrow-caption">Đếm theo các ngày hôm sau đã có kết quả. '
             'Ngày chưa có dữ liệu không được tính.</p></aside></div>',
        render="renderTomorrow",
    ),
    StatPage(
        slug="thong-ke-tong-hop",
        title="Thống kê tổng hợp",
        subtitle="Tần suất LOTO, phân bố đầu – đuôi – tổng và chu kỳ Đặc Biệt từ lịch sử XSMB.",
        controls=_range_controls(weekday=True),
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
        "Bảng đối chiếu những lần cùng hai số cuối xuất hiện với kết quả của đúng "
        "<b>ngày lịch kế tiếp</b>. Không lấy một ngày khác để lấp ngày thiếu dữ liệu. "
        "Tần suất là thống kê lịch sử, <b>không phải xác suất đã hiệu chuẩn</b> cho kỳ tới."
    ),
}


def _asset(name: str) -> str:
    """Đọc tệp tài nguyên đi kèm mô-đun.

    Args:
        name: Tên tệp trong ``src/web/templates``.

    Returns:
        Nội dung tệp.
    """
    return (TEMPLATES / name).read_text(encoding="utf-8")


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



def _statistics_tabs(active: str) -> str:
    """Ba trang thống kê cùng một lối đi, giữ rõ trang đang xem."""
    links = (
        ("thong-ke-tong-hop", "Tổng hợp", "Đa chiều"),
        ("tan-suat-loto", "Tần suất LOTO", "00–99"),
        ("tan-suat-cap-loto", "Tần suất cặp", "50 họ cặp"),
    )
    current = ' aria-current="page"'
    return '<nav class="bf-tabs" aria-label="Loại thống kê">' + "".join(
        f'<a href="{slug}.html"'
        f'{current if slug == active else ""}>'
        f'{label}<span>{hint}</span></a>'
        for slug, label, hint in links
    ) + '</nav>'


def overview_layout(page: StatPage) -> str:
    """Tổng hợp theo luồng đọc: dải dữ liệu, phân bố, rồi chi tiết từng số."""
    distribution = "".join(
        f'<section class="bf-card bf-distribution" aria-labelledby="bf-{key}-title">'
        '<header class="bf-card-heading"><div>'
        f'<h2 id="bf-{key}-title">{title}</h2></div></header>'
        f'<p class="bf-section-copy">{hint}</p>'
        f'<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair"'
        f' id="sp-overview-{key}" aria-label="{title}"></table></div></section>'
        for key, title, hint in (
            ("head", "Theo chữ số đầu", "Hàng chục của từng số LOTO."),
            ("tail", "Theo chữ số đuôi", "Hàng đơn vị của từng số LOTO."),
            ("sum", "Theo tổng hai chữ số", "Cộng đầu và đuôi, lấy chữ số cuối."),
        )
    )
    return f"""
<div class="bf-topline"><a href="statistics.html">← Thống kê</a><span class="bf-live">Lịch sử XSMB · Miền Bắc</span></div>
<header class="bf-hero">
  <div><p class="bf-eyebrow">THỐNG KÊ / MIỀN BẮC</p><h1>{page.title}</h1>
  <p>{page.subtitle}</p></div>
  <a class="bf-demo-link" href="tan-suat-loto.html">Xem từng kỳ quay ↗</a>
</header>
{_statistics_tabs(page.slug)}
<section class="bf-card bf-filters" aria-labelledby="bf-filter-title">
  <header class="bf-card-heading"><div><span class="bf-step">01</span><h2 id="bf-filter-title">Chọn dải dữ liệu</h2></div><span>Áp dụng cho tần suất và phân bố LOTO</span></header>
  {page.controls}
</section>
<section id="sp-kpi" class="sp-kpi bf-kpis" aria-label="Tóm tắt dữ liệu"></section>
<section class="bf-card bf-totals" aria-labelledby="bf-overview-matrix-title">
  <header class="bf-card-heading"><div><span class="bf-step">02</span><h2 id="bf-overview-matrix-title">Tần suất LOTO 00–99</h2></div><span id="sp-overview-total" data-evidence-split></span></header>
  <p class="bf-section-copy">Mỗi ô là tổng số nháy của một số trong dải đã chọn. Xếp từ 00 đến 99 để đối chiếu nhanh.</p>
  <div id="sp-overview-matrix" class="sp-matrix"></div>
</section>
<div class="bf-distributions">{distribution}</div>
<section class="bf-card bf-ranking" aria-labelledby="bf-overview-ranking-title">
  <header class="bf-card-heading"><div><span class="bf-step">03</span><h2 id="bf-overview-ranking-title">40 số LOTO về nhiều nhất</h2></div><span>Đối chiếu với chu kỳ Đặc Biệt</span></header>
  <p class="bf-section-copy">Tần suất LOTO theo bộ lọc phía trên. Gan và chu kỳ Đặc Biệt tính trên toàn bộ lịch sử, đến kỳ mới nhất đã có kết quả.</p>
  <div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid" aria-label="Tần suất LOTO và chu kỳ Đặc Biệt"></table></div>
</section>
<section class="bf-card bf-guide" aria-labelledby="bf-guide-title">
  <header class="bf-card-heading"><div><h2 id="bf-guide-title">Hiểu đúng các chỉ số</h2></div><span>Thống kê mô tả từ lịch sử</span></header>
  <div class="bf-guide-grid">
    <div><h3>Số nháy LOTO</h3><p>Một số xuất hiện nhiều lần trong cùng kỳ được cộng đủ từng lần. Mỗi kỳ XSMB có 27 kết quả LOTO.</p></div>
    <div><h3>So với kỳ vọng</h3><p id="sp-overview-expected" data-evidence-split></p><p>Số dẫn đầu trong 100 số có thể cao hơn mức này ngay cả khi kết quả ngẫu nhiên.</p></div>
    <div><h3>Gan và chu kỳ Đặc Biệt</h3><p>Gan là số kỳ chưa xuất hiện ở giải Đặc Biệt. Chu kỳ dài nhất là khoảng cách giữa hai lần xuất hiện đã ghi nhận. Gan dài không có nghĩa là sắp về.</p></div>
  </div>
</section>
<script type="application/json" id="sp-stat-evidence" data-app-evidence-values>{{}}</script>
"""


def frequency_bento_layout(page: StatPage, note_html: str) -> str:
    """Hai trang tần suất theo luồng dọc, giữ các định danh điều khiển sẵn có."""
    pairs = page.slug == "tan-suat-cap-loto"
    label = "cặp số" if pairs else "số lô tô"
    picker = (
        '<div id="bf-pair-picker"></div>' if pairs
        else '<div class="sp-picker" id="sp-picker"></div>'
    )
    matrix = "Tổng số nháy theo 50 họ cặp" if pairs else "Tổng số nháy 00–99"
    total_id = "bf-pair-totals" if pairs else "sp-matrix"
    guide = (
        '<div><h3>Đọc ma trận cặp số</h3><p>Mỗi ô cộng số nháy của hai thành viên '
        'trong cùng kỳ. Ví dụ 12 về 2 nháy và 21 về 1 nháy: ô 12–21 hiển thị '
        '<b>3</b>.</p></div>'
        '<div><h3>50 họ cặp</h3><p>Gồm 45 cặp đảo hai chữ số và 5 cặp kép bóng. '
        'Tổng nháy theo họ cặp cộng đủ các lần xuất hiện, kể cả khi chỉ một '
        'thành viên về.</p></div>'
        '<div><h3>Đồng xuất hiện</h3><p>Bảng xếp hạng xét toàn bộ 4.950 cặp số khác '
        'nhau. Mỗi kỳ chỉ tính một lần nếu <b>cả hai số cùng về</b>; phép đếm '
        'này khác tổng nháy của họ cặp.</p></div>'
        if pairs else
        '<div><h3>Đọc ma trận theo kỳ</h3><p>Số trong ô là số nháy của một con LOTO '
        'ở kỳ đó. Đổi chiều để xem theo ngày hoặc theo số; thứ tự ngày luôn '
        'mới nhất trước.</p></div>'
        '<div><h3>Đọc tổng 00–99</h3><p>Tổng nháy và xếp hạng dùng toàn bộ 100 số '
        'trên dải đã chọn. Lựa chọn số phía trên chỉ thu gọn ma trận theo kỳ '
        'để dễ so sánh.</p></div>'
        '<div><h3>Chu kỳ gan</h3><p>Chọn một số trong bộ chọn để xem chu kỳ gan. '
        'Gan đếm theo kỳ quay; số gan cao không bảo đảm kết quả kỳ tiếp theo.</p></div>'
    )
    return f"""
<div class="bf-topline"><a href="statistics.html">← Thống kê</a><span class="bf-live" id="bf-source">Lịch sử XSMB · Miền Bắc</span></div>
<header class="bf-hero">
  <div><p class="bf-eyebrow">THỐNG KÊ / MIỀN BẮC</p><h1>{page.title}</h1>
  <p>{page.subtitle}</p></div>
  <a class="bf-demo-link" id="bf-demo-link" href="?demo=1">Xem dữ liệu minh họa ↗</a>
</header>
{_statistics_tabs(page.slug)}
<div id="bf-demo-banner" class="bf-demo-banner" hidden>DỮ LIỆU MINH HỌA · 45 kỳ giả lập, tách riêng dữ liệu và đánh dấu của bạn.</div>
<section id="app-frequency-onboarding" class="app-frequency-onboarding" aria-labelledby="app-frequency-demo-title" hidden>
  <h2 id="app-frequency-demo-title">Thử đọc tần suất trong 3 bước</h2>
  <ol><li><b>Chọn dải</b><span>Bấm 30 kỳ hoặc đổi ngày; mọi tổng lượt và biểu đồ cập nhật cùng lúc.</span></li><li><b>Đọc xu hướng</b><span>Ngang: số theo hàng. Dọc: ngày theo hàng. Biểu đồ đi từ kỳ cũ đến kỳ mới.</span></li><li><b>Đối chiếu</b><span>Bấm ô của số và ngày cần theo dõi để đánh dấu. Xem bảng xếp hạng và mốc ngẫu nhiên phía dưới.</span></li></ol>
  <p>Màu xanh: mức lượt/kỳ nửa sau bằng hoặc cao hơn nửa đầu. Màu đỏ: thấp hơn. Đây là mô tả lịch sử, không dự báo.</p>
</section>
<section class="bf-card bf-filters" aria-labelledby="bf-filter-title">
  <header class="bf-card-heading"><div><span class="bf-step">01</span><h2 id="bf-filter-title">Bộ lọc &amp; lựa chọn</h2></div><span>Cập nhật ngay khi thay đổi</span></header>
  {page.controls}
  <details class="bf-selection"><summary>Chọn {label} để so sánh <span id="bf-selection-count"></span></summary>{picker}</details>
</section>
<section class="bf-kpis" aria-label="Tổng quan dải đã chọn" id="bf-kpis"></section>
<section class="bf-card bf-matrix-card" aria-labelledby="bf-matrix-title">
  <header class="bf-card-heading"><div><span class="bf-step">02</span><h2 id="bf-matrix-title">Ma trận tần suất</h2></div><span id="sp-matrix-note" class="sp-matrix-note" data-evidence-split></span></header>
  <div class="app-frequency-toolbar"><div class="app-frequency-orientation" role="group" aria-label="Chiều xem tần suất"><button type="button" data-app-orientation="horizontal" aria-pressed="true">Ngang</button><button type="button" data-app-orientation="vertical" aria-pressed="false">Dọc</button></div><p id="app-frequency-view-help">Ngang: số theo hàng, ngày theo cột. Dọc: ngày theo hàng, số theo cột.</p></div>
  <p class="app-frequency-chart-help">Xu hướng theo dải đã chọn · cùng thang lượt/kỳ · cũ → mới. Xanh: nửa sau ≥ nửa đầu; đỏ: giảm. Tổng lượt gồm cả các lần về lặp trong cùng kỳ.</p>
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
<section class="bf-card bf-totals" aria-labelledby="bf-totals-title">
  <header class="bf-card-heading"><div><span class="bf-step">03</span><h2 id="bf-totals-title">{matrix}</h2></div><span>Trọn dải đã chọn</span></header>
  <p class="bf-section-copy">Tổng nháy cộng gộp qua các kỳ, không phụ thuộc lựa chọn {label} trên ma trận.</p>
  <div id="{total_id}" class="sp-matrix {'bf-pair-totals' if pairs else ''}"></div>
</section>
<section class="bf-card bf-ranking" aria-labelledby="bf-ranking-title">
  <header class="bf-card-heading"><div><span class="bf-step">04</span><h2 id="bf-ranking-title">{'Xếp hạng đồng xuất hiện' if pairs else 'Xếp hạng tần suất'}</h2></div><span>{'50 cặp dẫn đầu trong 4.950 cặp' if pairs else 'Đủ 100 số trên trọn dải'}</span></header>
  <div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-grid" aria-label="{'Xếp hạng cặp đồng xuất hiện' if pairs else 'Xếp hạng tần suất LOTO'}"></table></div>
</section>
<section class="bf-card bf-guide" aria-labelledby="bf-guide-title">
  <header class="bf-card-heading"><div><h2 id="bf-guide-title">Cách đọc và đối chiếu</h2></div><span>Thống kê mô tả từ lịch sử</span></header>
  <div class="bf-guide-grid">{guide}</div>
  <details class="bf-method" open><summary>Mốc ngẫu nhiên để so sánh</summary>{note_html}</details>
  <p class="bf-tip">★ Ô có hai số cuối giải Đặc Biệt được ưu tiên màu đỏ. Giá trị trong ô vẫn là số nháy.</p>
</section>
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
    overview = page.slug == "thong-ke-tong-hop"
    statistical = bento or overview
    calendar = page.slug in {"bang-dac-biet", "bang-dac-biet-thang", "bang-dac-biet-nam"}
    tomorrow = page.slug == "giai-db-ngay-mai"
    special_stats = page.slug in {slug for slug, _ in SPECIAL_STAT_PAGES}
    loto_stats = page.slug in {slug for slug, _ in LOTO_STAT_PAGES}
    responsive = statistical or calendar
    body = page.body.replace('class="sp-table ', 'class="sp-table sp-calendar-table ') if calendar else page.body
    content = _loto_stat_layout(page) if loto_stats else _special_stat_layout(page, note_html) if special_stats else (f'<div class="app-tomorrow-shell" data-app-workspace-guide><header class="app-tomorrow-header">'
               '<a href="statistics.html">← Thống kê Đặc Biệt</a>'
               f'<h1>{page.title}</h1><p>{page.subtitle}</p></header>'
               f'{page.controls}{body}{note_html}</div>') if tomorrow else frequency_bento_layout(page, note_html) if bento else overview_layout(page) if overview else f"""
<div style="margin-bottom:1rem"><a href="index.html">← Trang chính</a></div>
<h1>{page.title}</h1>
<p class="ui-muted" style="max-width:60rem;line-height:1.65">{page.subtitle}</p>
{page.controls}
{body}
{note_html}"""
    footer = (
        f'Dữ liệu đến {str(draws[-1]["d"])} · Dựng lúc {generated}.'
        if (statistical or tomorrow or special_stats or loto_stats) and draws else
        f'Dựng lúc {generated}. Toàn bộ tính toán chạy trong trình duyệt trên '
        f'{len(draws)} kỳ đã nhúng — không gọi mạng, không máy chủ.'
    )
    if (special_stats or loto_stats) and not draws:
        footer = f'Chưa có dữ liệu. Dựng lúc {generated}.'
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{security_meta_tags()}
{stylesheet_link()}
<title>{page.title}</title>
<style>
{_asset("stat_pages.css")}
{_asset("tomorrow_history.css") if tomorrow else ""}
{_asset("frequency_bento.css") if statistical else ""}
{_asset("stat_table_layout.css") if responsive else ""}
</style>
{'<style id="app-specialstats-style">' + _asset("special_stat_pages.css") + '</style>' if special_stats else ''}
{'<style id="app-lotostats-style">' + _asset("loto_stat_pages.css") + '</style>' if loto_stats else ''}
</head><body class="{'app-lotostats-page' if loto_stats else 'app-specialstats-page' if special_stats else 'app-tomorrow-page' if tomorrow else 'bf-page sp-overview-page' if overview else 'bf-page' if bento else ''}">
{app_shell_open(f"{page.slug}.html", wide=True)}
{content}
<p class="ui-muted{' app-lotostats-footer' if loto_stats else ' app-specialstats-footer' if special_stats else ''}" style="margin-top:1.5rem;font-size:.75rem">
{footer}</p>
{app_shell_close(f"{page.slug}.html")}
<script>window.__D_DRAWS__={json_for_html_script(draws)};
window.__D_PAIR_CHANCE__={json_for_html_script(pair_chance_grid())};
window.__D_BO__={json_for_html_script(bo_lookup())};
window.__D_CAP50__={json_for_html_script(cap_loto_50())};</script>
<script>
{_asset("frequency_demo.js") if bento else ""}
{_asset("stat_pages.js")}
{_asset("frequency_window.js") if bento else ""}
{_asset("frequency_bento.js") if bento else ""}
{f'installFrequencyBento({json.dumps(page.render)});' if bento else ""}
{_asset("stat_table_layout.js") if responsive else ""}
{'installStatTableLayout();' if responsive else ''}
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
    root = REPO_ROOT
    files = build(root, root / args.docs_dir)
    logger.info("Xong: %d trang", len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
