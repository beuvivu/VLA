from __future__ import annotations

"""Ô tick "Tự động đánh dấu cặp trùng" phải THẬT SỰ đánh dấu được.

Lỗi người dùng báo: bật ô tick rồi bấm ô nào cũng chỉ sáng đúng ô đó. Đo trong
trình duyệt thật thì 14 trang bày ô tick nhưng chỉ 2 trang chạy.

Nguyên nhân: ``markPair()`` đọc cặp ra từ ``data-key``, mà chỉ hai hàm vẽ đặt
cặp vào khoá; số còn lại dùng khoá vị trí ``sp-grid:hàng:cột``. Regex không
khớp gì, ``markPair`` trả null, và chế độ cặp lặng lẽ rơi về chế độ thường —
không lỗi, không cảnh báo, chỉ là không làm gì.

Bảng do JS dựng lúc chạy nên HTML đã xuất bản CHƯA có ``data-key`` nào; phép
kiểm đọc HTML tĩnh không thấy được gì (bản đầu của chính tệp này sai đúng chỗ
đó và đỏ cả 12 trang). Nên ở đây ghim ba bất biến cấu trúc đọc được từ nguồn,
còn bất biến đầu-cuối thì đo bằng trình duyệt ở
``tests/test_pair_marking_browser.py``.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
JS = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")


def test_the_table_builder_reads_a_declared_pair_into_the_cell_key() -> None:
    """Không có bước này thì mọi khai báo ``pairOf`` của hàm vẽ đều rơi vào hư không."""
    body = re.search(r"const pair = opts\.pairOf[^\n]*\n[^\n]*\n?", JS)
    assert body, "table() không còn đọc opts.pairOf"
    assert re.search(r"const key = pair [^\n]*\|n\$\{pair\}", JS), (
        "table() đọc opts.pairOf nhưng không gắn cặp vào data-key, nên "
        "markPair() vẫn không đọc ra gì"
    )


def test_a_cell_lights_up_from_pair_marks_not_only_from_cell_marks() -> None:
    """Lúc VẼ LẠI, ô phải sáng theo cả hai kho.

    Chỉ tra ``MARKS`` thì dấu cặp biến mất mỗi lần đổi dải ngày hay đổi chiều
    bảng — vẽ lại là xoá sạch, và người dùng thấy đúng "bấm xong tự mất".
    """
    for scope in ("const on = (MARKS.has(key)", "const on = (MARKS.has(hKey)"):
        line = next((l for l in JS.split("\n") if l.strip().startswith(scope)), None)
        assert line, f"không tìm thấy nhánh tô sáng: {scope}"
        assert "PAIR_MARKS.has(pair)" in line or "PAIR_MARKS.has(hPair)" in line, (
            f"nhánh tô sáng chỉ tra MARKS, bỏ qua PAIR_MARKS: {line.strip()}"
        )


def test_pair_marks_are_stored_site_wide_but_cell_marks_stay_per_page() -> None:
    """Hai phạm vi lưu khác nhau, vì hai thứ được đánh dấu khác bản chất.

    Khoá ô (``sp-grid:12:3``) chỉ có nghĩa trong đúng bảng sinh ra nó. Còn "34"
    là 34 ở mọi trang. Nhốt dấu cặp theo từng trang thì trên năm trang mà mỗi
    con chỉ hiện một lần, chế độ cặp sáng đúng một ô — không khác gì chế độ
    thường, tức vẫn đúng lỗi người dùng báo.
    """
    mark = re.search(r"^const MARK_KEY = (.+)$", JS, re.M)
    pair = re.search(r"^const PAIR_KEY = (.+)$", JS, re.M)
    assert mark and pair, "thiếu một trong hai khoá lưu trữ"
    assert "location.pathname" in mark.group(1), "dấu Ô phải theo từng trang"
    assert "location.pathname" not in pair.group(1), (
        "dấu CẶP phải dùng chung cho toàn site; có location.pathname là đang "
        "nhốt nó lại theo trang"
    )


def test_pages_without_two_digit_numbers_do_not_offer_pair_mode() -> None:
    """Trang chỉ có chữ số đơn 0-9 thì KHÔNG được bày ô tick.

    Một nút bấm vào không thấy gì xảy ra tệ hơn là không có nút.
    """
    offered = {
        p.name for p in DOCS.glob("*.html")
        if 'id="sp-pair-mode"' in p.read_text(encoding="utf-8")
    }
    assert len(offered) >= 10, "quá ít trang có ô tick; phép kiểm mất đối tượng"
    for name in ("dau-duoi-loto.html", "giai-dac-biet-theo-tong.html"):
        assert (DOCS / name).exists(), f"thiếu {name}; phép kiểm mất đối tượng"
        assert name not in offered, (
            f"{name} chỉ có chữ số đơn 0-9 nên đánh dấu theo cặp hai chữ số là "
            "vô nghĩa ở đó, nhưng trang vẫn bày ô tick."
        )
