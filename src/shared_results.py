"""Bảng Sổ KQ dùng chung cho trang chủ, trang đích và sổ lịch sử."""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path
from typing import Mapping, Any

from web_security import json_for_html_script

#: Thứ tự giải, nhãn và độ rộng. Bên JS giữ một bản y hệt; chúng phải khớp
#: nhau và ``tests/test_traditional_results_page.py`` kiểm điều đó.
PRIZE_SPEC: tuple[tuple[str, str, int, int], ...] = (
    # mã, nhãn, số lượng, độ rộng
    ("special", "Đặc Biệt", 1, 5),
    ("prize1", "Giải Nhất", 1, 5),
    ("prize2", "Giải Nhì", 2, 5),
    ("prize3", "Giải Ba", 6, 5),
    ("prize4", "Giải Tư", 4, 4),
    ("prize5", "Giải Năm", 6, 4),
    ("prize6", "Giải Sáu", 3, 3),
    ("prize7", "Giải Bảy", 4, 2),
)
PRIZE_ORDER = tuple(code for code, _, _, _ in PRIZE_SPEC)
PRIZE_WIDTHS = {code: width for code, _, _, width in PRIZE_SPEC}
PRIZE_LABELS = {code: label for code, label, _, _ in PRIZE_SPEC}
PRIZE_COUNTS = {code: count for code, _, count, _ in PRIZE_SPEC}
PRIZE_FIELDS = {
    "special": ("special",),
    "prize1": ("prize1",),
    "prize2": ("prize2_1", "prize2_2"),
    "prize3": tuple(f"prize3_{i}" for i in range(1, 7)),
    "prize4": tuple(f"prize4_{i}" for i in range(1, 5)),
    "prize5": tuple(f"prize5_{i}" for i in range(1, 7)),
    "prize6": tuple(f"prize6_{i}" for i in range(1, 4)),
    "prize7": tuple(f"prize7_{i}" for i in range(1, 5)),
}

#: Độ dài một dòng nén: 10 ký tự ngày + 107 chữ số giải.
DATE_WIDTH = 10
PRIZE_DIGITS = sum(PRIZE_COUNTS[code] * PRIZE_WIDTHS[code] for code in PRIZE_ORDER)
ROW_WIDTH = DATE_WIDTH + PRIZE_DIGITS


def encode_row(row: dict[str, str]) -> str | None:
    """Một kỳ thành một chuỗi ``YYYY-MM-DD`` + 107 chữ số, hoặc ``None``.

    Trả ``None`` cho mọi kỳ thiếu dữ liệu. KHÔNG bịa số 0 thay cho ô trống:
    một kỳ thiếu phải biến mất khỏi sổ, chứ không được hiện ra như thể giải
    ấy về 0000.
    """
    draw_date = str(row.get("date", ""))[:DATE_WIDTH]
    try:
        date.fromisoformat(draw_date)
    except ValueError:
        return None
    digits: list[str] = []
    for code in PRIZE_ORDER:
        width = PRIZE_WIDTHS[code]
        for field in PRIZE_FIELDS[code]:
            raw = row.get(field)
            if raw is None or not str(raw).strip():
                return None
            value = str(raw).strip().zfill(width)
            if len(value) != width or not (value.isascii() and value.isdigit()):
                return None
            digits.append(value)
    encoded = draw_date + "".join(digits)
    return encoded if len(encoded) == ROW_WIDTH else None


def decode_row(row: str, *, metadata: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """Giải mã kỳ đầy đủ; chỉ gắn ký hiệu thuộc chính ngày đang dựng."""
    if not isinstance(row, str) or len(row) != ROW_WIDTH:
        return None
    draw_date = row[:DATE_WIDTH]
    try:
        date.fromisoformat(draw_date)
    except ValueError:
        return None
    digits = row[DATE_WIDTH:]
    if not (digits.isascii() and digits.isdigit()):
        return None
    prizes = []
    cursor = 0
    for code, name, count, width in PRIZE_SPEC:
        values = [digits[cursor + i * width:cursor + (i + 1) * width] for i in range(count)]
        cursor += count * width
        prizes.append({"code": code, "name": name, "width": width, "values": values})
    details = metadata or {}
    if details.get("date") and details["date"] != draw_date:
        details = {}
    station = details.get("station", "")
    codes = details.get("special_codes", [])
    return {
        "date": draw_date,
        "prizes": prizes,
        "station": station if isinstance(station, str) else "",
        "special_codes": [code for code in codes if isinstance(code, str) and code.strip()]
        if isinstance(codes, list) else [],
    }


def draw_from_row(row: Mapping[str, Any], metadata: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """Chuyển dòng CSV sang hợp đồng bảng dùng chung, giữ nguyên số 0 đầu."""
    encoded = encode_row(dict(row))
    return decode_row(encoded, metadata=metadata) if encoded else None


def shared_results_css() -> str:
    """Mọi nơi nạp chính stylesheet Sổ KQ, không sao chép hay xấp xỉ CSS."""
    return (Path(__file__).parent / "templates" / "traditional_results.css").read_text(encoding="utf-8")


def shared_results_script() -> str:
    """Bộ dựng DOM và đánh dấu duy nhất được nhúng vào từng trang tự chứa."""
    return (Path(__file__).parent / "templates" / "shared_results.js").read_text(encoding="utf-8")


def _number_attrs(draw_date: str, code: str, index: int, pair: str) -> str:
    return (
        f' data-cell="{escape(draw_date)}|{escape(code)}|{index}" tabindex="0"'
        f' role="button" aria-pressed="false" aria-label="Đánh dấu số {escape(pair)}"'
    )


def render_draw(draw: Mapping[str, Any], *, include_loto: bool = True, extra: str = "") -> str:
    """Bản HTML dự phòng chung, đủ dữ liệu trước lúc bộ dựng DOM khởi chạy.

    ``extra`` là một khối đã dựng sẵn (vd. ô cầu vị trí ở trang chủ), đặt thành
    cột thứ ba của lưới, cạnh bảng LOTO. Bộ dựng DOM chuyển nguyên khối ấy sang
    bảng mới thay vì dựng lại.
    """
    draw_date = str(draw["date"])
    parsed = date.fromisoformat(draw_date)
    weekday = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")[parsed.weekday()]
    station = f' ({escape(str(draw["station"]))})' if draw.get("station") else ""
    codes = '<span class="tr-code-label">Ký hiệu Đặc Biệt:</span>'
    if draw.get("special_codes"):
        codes += "".join(f'<span class="tr-special-code">{escape(str(code))}</span>' for code in draw["special_codes"])
    else:
        codes += '<span class="tr-code-missing">Chưa có dữ liệu ký hiệu cho kỳ này</span>'
    header = (
        '<header class="tr-day-head"><div class="tr-day-title">'
        f'<h2>Xổ số Miền Bắc{station}</h2><time datetime="{escape(draw_date)}">'
        f'{weekday}, {parsed:%d/%m/%Y}</time><div class="tr-special-codes">{codes}</div></div>'
        '<span class="tr-badge">Đã đối chiếu</span></header>'
    )
    rows = []
    heads: list[list[str]] = [[] for _ in range(10)]
    all_pairs = []
    for prize in draw["prizes"]:
        code = str(prize["code"])
        numbers = []
        for index, raw_value in enumerate(prize["values"]):
            value = str(raw_value)
            pair = value[-2:]
            heads[int(pair[0])].append(pair[1])
            all_pairs.append(pair)
            content = escape(value)
            if code == "special":
                content = f'{escape(value[:-2])}<span class="tr-special-tail">{escape(pair)}</span>'
            numbers.append(f'<div class="tr-number"{_number_attrs(draw_date, code, index, pair)}>{content}</div>')
        rows.append(
            f'<div class="tr-prize-row" data-prize="{escape(code)}">'
            f'<div class="tr-prize-label">{escape(str(prize["name"]))}</div>'
            f'<div class="tr-number-grid" style="--count: {len(prize["values"])};">'
            + "".join(numbers) + '</div></div>'
        )
    head_rows = []
    for digit, tails in enumerate(heads):
        minis = "".join(
            f'<span class="tr-mini" data-value="{digit}{tail}"'
            f'{_number_attrs(draw_date, f"d{digit}", index, f"{digit}{tail}")}>{digit}{tail}</span>'
            for index, tail in enumerate(sorted(tails))
        ) or '<span class="tr-dash">—</span>'
        head_rows.append(
            f'<tr><td class="tr-digit">{digit}</td><td class="tr-tails">'
            f'<div class="tr-digit-list">{minis}</div></td></tr>'
        )
    side = (
        '<section class="tr-head-tail"><h3>Bảng LOTO theo đầu</h3>'
        '<div class="tr-head-tail-scroll"><table><thead><tr><th>Đầu</th><th>LOTO</th></tr></thead><tbody>'
        + "".join(head_rows) + '</tbody></table></div></section>'
    )
    if include_loto:
        side += '<section class="tr-loto"><h3>Dãy LOTO (27 số)</h3><div class="tr-loto-list">'
        side += "".join(f'<span class="tr-loto-item">{escape(pair)}</span>' for pair in sorted(all_pairs))
        side += '</div></section>'
    extra_block = f'<div class="tr-day-extra">{extra}</div>' if extra else ""
    return (
        f'<article class="tr-day">{header}<div class="tr-day-grid"><section class="tr-prizes">'
        + "".join(rows) + f'</section><div class="tr-day-side">{side}</div>{extra_block}</div></article>'
    )


def render_result_board(draw: Mapping[str, Any] | None, *, board_id: str = "app-daily-results",
                        include_loto: bool = False, extra: str = "") -> str:
    """Nhúng một bảng hoàn chỉnh với dữ liệu thật và đánh dấu chuột/bàn phím."""
    if not draw:
        return '<p class="tr-empty">Chưa có kết quả đầy đủ cho kỳ này.</p>'
    payload_id = f"{board_id}-data"
    options = {"includeLoto": include_loto}
    return (
        f'<section id="{escape(board_id)}" class="tr-results" data-layout="1"'
        f' data-headtail="on" data-loto="{"on" if include_loto else "off"}" data-tail="on"'
        f' data-extra="{"on" if extra else "off"}" aria-label="Kết quả xổ số Miền Bắc">'
        f'{render_draw(draw, include_loto=include_loto, extra=extra)}</section>'
        f'<script id="{escape(payload_id)}" type="application/json">{json_for_html_script(dict(draw))}</script>'
        f'<script>{shared_results_script()}</script><script>'
        'window.TraditionalResults.mount('
        f'document.getElementById({json_for_html_script(board_id)}),'
        f'JSON.parse(document.getElementById({json_for_html_script(payload_id)}).textContent),'
        f'{json_for_html_script(options)});</script>'
    )
