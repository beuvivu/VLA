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
    """Trọn một khối từ ``start`` tới dấu ngoặc đóng khớp với nó.

    Bản đầu tìm ``"\n}"``, tức giả định khối luôn đóng ngoặc trên dòng riêng.
    CSS của trang này viết nén, nhiều quy tắc đóng ngay cuối dòng
    (``box-shadow:var(--ui-sh-sm)}``), nên phép tìm ấy chạy tuột sang các quy
    tắc phía sau và nuốt vào cả những khai báo không thuộc khối — phép kiểm
    khi ấy nói về một khối khác với khối nó tưởng.
    """
    begin = source.index(start)
    brace = source.index("{", begin)
    depth, i = 1, brace + 1
    while i < len(source) and depth:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1
    return source[begin:i]


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
    # Lấy quy tắc NỀN, không phải bản đè trong `@media`. Bản đè chỉ đặt lại
    # màu, nên soi nhầm nó thì phép kiểm đòi `background-image: none` ở một
    # chỗ vốn không có lý do khai nó — báo đỏ oan trên mã đang đúng.
    #
    # Cắt tại `@media` ĐẦU TIÊN là không đủ: tệp có nhiều khối `@media` và
    # khối đầu nằm TRƯỚC quy tắc cần soi, nên lát cắt ấy rỗng. Phải bỏ trọn
    # từng khối bằng cách đếm ngoặc.
    base = _without_media(CSS_CODE)
    for selector in (".sp-table td.is-empty", ".sp-nl i.sp-empty-key"):
        rule = _block(base, selector + " {")
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
    # Ở chế độ sáng, ô không về nay là TRẮNG — đúng lối trang mẫu, và làm được
    # vì cấp 1 nháy đã chuyển sang vàng nên không còn chiếm màu trắng.
    #
    # Trắng và vàng chênh rất ít về ĐỘ SÁNG (tỉ số 1,07) dù khác hẳn về sắc,
    # nên phép kiểm KHÔNG được dựa vào độ sáng ở đây. Điều phải canh là ô có
    # về còn vòng viền trong mà ô không về không có — xem phép kiểm bên dưới.
    assert light.group(1).upper() == "#FFFFFF", light.group(1)
    tier_one = re.search(r"\.sp-table td\.sp-n1 \{[^}]*background-color:\s*(#[0-9A-Fa-f]{6})",
                         CSS_CODE)
    assert tier_one and tier_one.group(1).upper() != "#FFFFFF", (
        "cấp 1 nháy không được trùng màu ô không về")


def test_a_hit_cell_keeps_a_ring_that_an_empty_cell_does_not_have() -> None:
    """Dấu hiệu thứ hai, cho trường hợp độ sáng chênh ít.

    Trang cặp lô tô không dùng thang số nháy (cố ý: giá trị ô là tổng lần về
    của HAI con, không phải số nháy của một con), nên ở chế độ tối ô có về chỉ
    chênh ô rỗng 9,9 đơn vị sáng. Vòng viền trong là thứ gánh phần còn lại.
    """
    assert "box-shadow: none" in _block(CSS_CODE, ".sp-table td.is-empty {")
    hit = _block(CSS_CODE, ".sp-table td.sp-hit {")
    assert "inset" in hit, hit


def _without_media(css: str) -> str:
    """Bỏ trọn mọi khối ``@media``, giữ lại phần quy tắc nền."""
    out: list[str] = []
    i = 0
    while i < len(css):
        at = css.find("@media", i)
        if at == -1:
            out.append(css[i:])
            break
        out.append(css[i:at])
        brace = css.find("{", at)
        if brace == -1:
            break
        depth, j = 1, brace + 1
        while j < len(css) and depth:
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        i = j
    return "".join(out)


# --- Kỳ chưa quay, lọc thứ, chế độ cặp --------------------------------------

BUILDER = (ROOT / "src" / "build_stat_pages.py").read_text(encoding="utf-8")


def test_the_pending_draw_is_shown_as_waiting_not_as_a_miss() -> None:
    """Kỳ hôm nay chưa quay phải HIỆN RA, và hiện khác hẳn ô "không về".

    Bỏ nó đi thì bảng trông như hôm nay không tồn tại. Để nó trắng như ô
    "không về" thì tệ hơn: đó là một lời khẳng định SAI — chưa quay không
    phải là không về.
    """
    assert "function pendingDay" in JS_CODE
    assert "pending: true" in JS_CODE
    rule = _block(_without_media(CSS_CODE), ".sp-table td.sp-pending,")
    assert "dashed" in rule, rule
    assert "#E0E0E0" in rule, rule


def test_today_is_read_in_vietnam_time_not_the_viewer_clock() -> None:
    """Người xem ở bờ Tây nước Mỹ lúc 19h ngày 14 đang là 09h ngày 15 ở VN."""
    body = _block(JS_CODE, "function todayInVietnam")
    assert "Asia/Ho_Chi_Minh" in body, body
    assert "en-CA" in body, "định dạng phải cho ra YYYY-MM-DD"


def test_the_pending_column_obeys_the_weekday_filter() -> None:
    """Cột chờ được chèn SAU khi lọc, nên nếu không tự kiểm thì nó lách qua.

    Đã đo: lọc "Thứ hai" và lọc "Chủ nhật" đều hiện cột 15-09, trong khi
    15-09-2026 là thứ Ba.
    """
    body = _block(JS_CODE, "function pendingDay")
    assert 'sp-weekday' in body, body
    assert "weekdayOf(today)" in body, body


def test_the_weekday_filter_exists_and_is_wired_to_rerender() -> None:
    assert "sp-weekday" in BUILDER, "thiếu ô chọn thứ trong HTML"
    assert BUILDER.count('("0", "Chủ nhật")') == 1
    body = _block(JS_CODE, "function selected")
    assert "weekdayOf(r.d) === want" in body, body
    # Đổi ô chọn phải dựng lại bảng; thiếu dòng này thì ô có mà bấm không ăn.
    assert '$("sp-weekday")].forEach' in JS_CODE


def test_weekday_is_computed_without_the_viewer_timezone() -> None:
    """`getDay()` đọc theo múi giờ máy người xem nên sai ngoài Việt Nam."""
    body = _block(JS_CODE, "function weekdayOf")
    assert "Date.UTC(" in body and "getUTCDay()" in body, body
    assert "getDay(" not in body.replace("getUTCDay(", ""), body


def test_pair_mode_is_opt_in_and_keeps_two_separate_stores() -> None:
    """Hai kho, không phải một.

    Một ô có thể đang sáng vì chính nó được bấm, HOẶC vì cặp số của nó đang
    được đánh dấu. Gộp vào một kho thì không phân biệt được, và cú bấm tiếp
    theo xử lý sai.
    """
    assert 'id="sp-pair-mode"' in BUILDER
    assert "let PAIR_MARKS = new Set();" in JS_CODE
    body = _block(JS_CODE, "function toggleMark")
    # Hai nhánh TẮT phải đứng trước hai nhánh BẬT.
    assert body.index("PAIR_MARKS.delete") < body.index("PAIR_MARKS.add"), body
    assert body.index("MARKS.delete") < body.index("MARKS.add"), body
    # Bật chế độ cặp là tuỳ chọn: mặc định không tích.
    assert 'id="sp-pair-mode">' in BUILDER and 'id="sp-pair-mode" checked' not in BUILDER


def test_the_pair_is_read_from_the_key_not_from_the_cell_text() -> None:
    """Chữ trong ô là SỐ NHÁY ("1", "2"), không phải con lô.

    Lấy nhầm nó thì bấm ô "2" sẽ làm sáng mọi ô có 2 nháy — một tập hợp
    chẳng có nghĩa gì với người soi cầu.
    """
    body = _block(JS_CODE, "function markPair")
    assert "dataset.key" in body, body
    assert "textContent" not in body, body


def test_switching_pair_mode_off_does_not_erase_existing_marks() -> None:
    """Người xem không hề bỏ chọn gì khi họ chỉ tắt một tuỳ chọn."""
    body = _block(JS_CODE, "function bindMarking")
    assert 'pairBox.addEventListener("change", paintMarks)' in body, body
    assert "PAIR_MARKS.clear()" not in body.split('addEventListener("change"')[1].split("\n")[0]


def test_the_day_cap_reaches_the_longest_preset_people_ask_for() -> None:
    """Trần 120 cũ âm thầm cắt mốc 300 ngày xuống còn 120.

    Chi phí dựng đã đo lại trong Chromium: 300 ngày cho 30 300 ô trong 894 ms,
    còn 500 ngày mới là chỗ gãy (4 113 ms).
    """
    found = re.search(r"const MATRIX_MAX_DAYS = (\d+);", JS_CODE)
    assert found and int(found.group(1)) >= 300, found


def test_the_matrix_does_not_touch_the_frame_it_sits_in() -> None:
    """Đo trước khi sửa: hàng cuối cách chân khung đúng 1px, tức dính viền."""
    rule = _block(_without_media(CSS_CODE), ".sp-scroll{")
    assert "padding-bottom" in rule, rule
    # Đệm NGANG sẽ đẩy mốc `sticky` lệch khỏi cạnh khung.
    assert "padding-left" not in rule and "padding:" not in rule, rule
