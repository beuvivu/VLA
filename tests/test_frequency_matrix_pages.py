"""Hai trang tần suất LOTO: đánh dấu bám ô, và ô không về đọc được.

Phần lỗi đánh dấu là lỗi CHUYỂN VỊ, nên phép kiểm phải nói về danh tính ô
chứ không về sự tồn tại của trình xử lý sự kiện. Trình xử lý vốn đã đúng và
vẫn chạy ở cả hai chiều; cái sai là KHOÁ mà nó tra.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
CSS = (ROOT / "src" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
JS_CODE = "\n".join(
    line for line in JS.splitlines() if not line.lstrip().startswith(("//", "*", "/*"))
)
CSS_CODE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def _block(source: str, start: str) -> str:
    body = source[source.index(start):]
    return body[: body.index("\n}") + 2]


def test_a_cell_keeps_its_key_when_the_matrix_is_transposed() -> None:
    """Khoá đánh dấu phải mang DANH TÍNH ô, không phải toạ độ của nó.

    Khoá cũ là `${el.id}:${y}:${i}` — thuần vị trí. Ma trận đổi chiều được,
    tức bị chuyển vị, nên cùng một khoá trỏ sang ô khác sau khi đổi chiều.
    Đã đo trong Chromium: một dấu đặt ở chiều dọc mang khoá
    `sp-matrix-grid:0:0`, sang chiều ngang thì khoá ấy rơi vào ô nhãn "00".

    Hệ quả người dùng thấy là "bấm không ăn ở chiều dọc": cú bấm rơi trúng
    một ô đang mang dấu lạc thì nó GỠ dấu thay vì thêm.
    """
    assert "opts.key ? opts.key(y, i)" in JS_CODE, "table() phải nhận khoá từ người gọi"
    for name in ("renderLotoMatrix", "renderPairMatrix"):
        block = _block(JS_CODE, f"function {name}")
        vertical, horizontal = block.split("} else {")
        for branch, side in ((vertical, "dọc"), (horizontal, "ngang")):
            # Tên thuộc tính phải ĐÚNG là `key`. Đổi nó thành `keyX` là mã rơi
            # thẳng về khoá vị trí — mà phép kiểm chỉ soi chuỗi khoá thì vẫn
            # xanh, vì chuỗi ấy còn nguyên dưới một cái tên vô dụng.
            assert re.search(r"(?:opts\.key\s*=|(?<![\w])key\s*:)\s*\(y, i\)", branch), (name, side)
            # Khoá phải dựng từ NGÀY — thứ không đổi khi chuyển vị.
            assert re.search(r"\|d\$\{[\w.\[\]\s+-]+\.d\}", branch), (name, side)


def test_both_orientations_build_the_same_identity_for_the_same_cell() -> None:
    """Hai nhánh chiều phải sinh CÙNG một khoá cho cùng một ô logic.

    Nếu hai nhánh dùng tiền tố khác nhau thì dấu vẫn lạc, chỉ lạc theo kiểu
    khác — nên phép kiểm soi tiền tố chứ không chỉ soi "có khoá".
    """
    loto = _block(JS_CODE, "function renderLotoMatrix")
    vertical, horizontal = loto.split("} else {")
    # Ô DỮ LIỆU của cả hai nhánh phải mang cùng dạng `m|n<số>|d<ngày>`.
    for branch, name in ((vertical, "dọc"), (horizontal, "ngang")):
        assert re.search(r"`m\|n\$\{pad2\(nums\[[^\]]+\]\)\}\|d\$\{byDate\[[^\]]+\]\.d\}`",
                         branch), (name, branch)
    pair = _block(JS_CODE, "function renderPairMatrix")
    vertical, horizontal = pair.split("} else {")
    for branch, name in ((vertical, "dọc"), (horizontal, "ngang")):
        assert re.search(r"`p\|c\$\{label\(CAP50\[[^\]]+\]\)\}\|d\$\{byDate\[[^\]]+\]\.d\}`",
                         branch), (name, branch)

    # Ô NHÃN cũng phải cùng tiền tố với ô dữ liệu của chính ma trận ấy. Thiếu
    # khẳng định này thì một tiền tố lệch ở nhánh nhãn lọt qua, và dấu đặt
    # trên nhãn hàng lại lạc chỗ đúng như lỗi vừa sửa.
    for source, prefix in ((loto, "m|"), (pair, "p|")):
        heads = re.findall(r"\?\s*`([a-z])\|", source)
        assert heads, source
        assert set(heads) == {prefix[0]}, (prefix, heads)


def test_old_positional_marks_are_dropped_rather_than_reinterpreted() -> None:
    """Dấu lưu theo lược đồ cũ là toạ độ; nạp lại vào lược đồ mới là rải bừa."""
    assert 'MARK_KEY = "sp.marks.v2.' in JS_CODE, JS_CODE[:0]
    assert '"vla.marks."' not in JS_CODE


def test_empty_cells_carry_no_stripe_pattern() -> None:
    for selector in (".sp-table td.is-empty", ".sp-nl i.sp-empty-key"):
        rule = _block(CSS_CODE, selector + " {")
        assert "background-image: none" in rule, rule
        assert "gradient" not in rule, rule
    assert "repeating-linear-gradient" not in CSS_CODE


def test_the_empty_cell_has_a_dark_tone_and_a_light_mode_counterpart() -> None:
    """Một giá trị cho chế độ tối là chưa đủ.

    Thang màu ô có về là màu SÁNG CỐ ĐỊNH, không đổi theo chế độ. Nếu chỉ đặt
    tông tối mà không cho chế độ sáng một giá trị riêng thì ô rỗng sáng 231,3
    còn ô có về 232,3 — chênh một đơn vị, mắt thường không tách được. Chính
    vạch chéo cũ đang gánh việc phân biệt ấy.
    """
    rule = _block(CSS_CODE, ".sp-table td.is-empty {")
    found = re.search(r"background-color:\s*(#[0-9A-Fa-f]{6})", rule)
    assert found, rule
    red, green, blue = (int(found.group(1)[i:i + 2], 16) for i in (1, 3, 5))
    assert 0.2126 * red + 0.7152 * green + 0.0722 * blue < 40, found.group(1)
    light = re.search(
        r"@media \(prefers-color-scheme: light\) \{\s*\.sp-table td\.is-empty \{"
        r"\s*background-color:\s*(#[0-9A-Fa-f]{6})", CSS_CODE)
    assert light, "chế độ sáng phải có giá trị riêng"
    red, green, blue = (int(light.group(1)[i:i + 2], 16) for i in (1, 3, 5))
    luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
    assert 150 < luminance < 225, (light.group(1), luminance)


def test_a_hit_cell_keeps_a_ring_that_an_empty_cell_does_not_have() -> None:
    """Dấu hiệu thứ hai, cho trường hợp độ sáng chênh ít.

    Trang cặp lô tô không dùng thang số nháy (cố ý: giá trị ô là tổng lần về
    của HAI con, không phải số nháy của một con), nên ở chế độ tối ô có về chỉ
    chênh ô rỗng 9,9 đơn vị sáng. Vòng viền trong là thứ gánh phần còn lại.
    """
    assert "box-shadow: none" in _block(CSS_CODE, ".sp-table td.is-empty {")
    hit = _block(CSS_CODE, ".sp-table td.sp-hit {")
    assert "inset" in hit, hit
