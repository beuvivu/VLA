"""Hai trang tần suất LOTO: đánh dấu bám ô, và ô không về đọc được.

Phần lỗi đánh dấu là lỗi CHUYỂN VỊ, nên phép kiểm phải nói về danh tính ô
chứ không về sự tồn tại của trình xử lý sự kiện. Trình xử lý vốn đã đúng và
vẫn chạy ở cả hai chiều; cái sai là KHOÁ mà nó tra.
"""

from __future__ import annotations

import re
from pathlib import Path

from theme_palette_helpers import theme_tokens, resolve_theme_colors

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
    """Ô không về đổi nền theo chủ đề và luôn tách khỏi cấp có về đầu tiên."""
    rule = _block(CSS_CODE, ".sp-table td.is-empty {")
    assert "var(--ui-empty-bg)" in rule
    dark = theme_tokens(True)["--ui-empty-bg"]
    red, green, blue = (int(dark[i:i + 2], 16) for i in (1, 3, 5))
    assert 0.2126 * red + 0.7152 * green + 0.0722 * blue < 40
    for is_dark in (False, True):
        values = theme_tokens(is_dark)
        assert values["--ui-empty-bg"] != values["--ui-n1-bg"]
    assert theme_tokens(False)["--ui-empty-bg"] != dark


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
    assert "var(--ui-pending-bg)" in rule, rule
    for dark in (False, True):
        values = theme_tokens(dark)
        assert values["--ui-pending-bg"] != values["--ui-empty-bg"]


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
    #
    # Soi DANH SÁCH, không soi chuỗi liền kề: thêm một ô điều khiển nữa vào
    # cùng mảng là chuỗi ghim cũ vỡ, dù hành vi không đổi chút nào.
    wiring = JS_CODE[JS_CODE.index("[from, to, $(\"sp-year\")"):]
    wiring = wiring[: wiring.index(".forEach")]
    for control in ("sp-weekday", "sp-sort", "sp-orient"):
        assert f'$("{control}")' in wiring, (control, wiring)


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


def test_the_number_is_clickable_in_both_orientations() -> None:
    """Bố cục hai chiều BẤT ĐỐI XỨNG, và đó là chỗ lỗi nằm.

    Cùng một con số:

        chiều ngang  -> nhãn HÀNG   -> <td class="cell">  bấm được
        chiều dọc    -> tiêu đề CỘT -> <th> trần          KHÔNG bấm được

    Trình xử lý khớp `closest("td.cell")` nên `<th>` không bao giờ trúng.
    Người dùng thấy đúng thế: bấm số ở chiều ngang thì đổi màu, ở chiều dọc
    thì không.

    Phép kiểm trước của tôi bấm vào Ô DỮ LIỆU chứ không bấm vào CON SỐ, nên
    nó xanh trong khi lỗi còn nguyên — một phép kiểm đo sai thứ thì tệ hơn
    không có, vì nó cấp giấy chứng nhận cho một bản vá chưa xong.
    """
    # Soi TRONG THÂN `table()`, không soi cả tệp. Chuỗi "opts.headKey" còn xuất
    # hiện ở các hàm dựng ma trận, nên một phép kiểm soi cả tệp vẫn xanh khi
    # `table()` bị đổi thành `const headKey = null` — tức lỗi gốc được khôi
    # phục nguyên vẹn mà bộ kiểm cấp giấy chứng nhận. Đột biến đã bắt đúng
    # chỗ ấy ở vòng đầu.
    builder = _block(JS_CODE, "function table(")
    assert "opts.headKey && opts.headKey(i)" in builder, builder[:400]
    # Ghim NGỮ NGHĨA, không ghim tên biến. Bản trước đòi đúng chuỗi
    # `data-key="${headKey}"`; khi `table()` được thêm bước gắn cặp, khoá phát
    # ra đổi tên biến thành `hKey` và phép kiểm đỏ oan trong khi tiêu đề cột
    # vẫn bấm được y nguyên (đo trong trình duyệt: 91 `th.cell[data-key]`, bấm
    # một cái thì số ô sáng 0 -> 1). Thứ đáng đòi là: tiêu đề CÓ mang khoá, và
    # khoá ấy suy ra từ `headKey`.
    #
    # Bảng nay dựng bằng `mk()` chứ không ghép chuỗi, nên khuôn cần khớp là
    # lời gọi `mk("th", ...)` chứ không còn là một mẩu HTML.
    assert re.search(
        r'mk\(\s*"th",\s*\{\s*class:\s*"cell"\s*\+\s*on,\s*"data-key":\s*h?[Kk]ey',
        builder,
    ), ("tiêu đề cột phải là ô bấm được và phải mang data-key", builder[:400])
    assert "if (!headKey) {" in builder and 'mk("th", null,' in builder, (
        "không có headKey thì phải dựng <th> trần; thiếu nhánh này nghĩa là "
        "khoá tiêu đề không còn bắt nguồn từ opts.headKey", builder[:400],
    )
    assert 'closest("td.cell, th.cell")' in JS_CODE, "trình xử lý phải nhận cả th"
    assert 'querySelectorAll("td.cell, th.cell")' in JS_CODE, "paintMarks phải quét cả th"
    for name in ("renderLotoMatrix", "renderPairMatrix"):
        block = _block(JS_CODE, f"function {name}")
        vertical, horizontal = block.split("} else {")
        for branch, side in ((vertical, "dọc"), (horizontal, "ngang")):
            assert "headKey" in branch, (name, side)


def test_a_number_keeps_one_identity_whichever_axis_it_sits_on() -> None:
    """Con số phải mang CÙNG khoá dù nó là nhãn hàng hay tiêu đề cột.

    Khác khoá thì đánh dấu ở chiều này sẽ không sáng ở chiều kia, và người
    dùng lại thấy "mất dấu khi đổi chiều".
    """
    loto = _block(JS_CODE, "function renderLotoMatrix")
    vertical, horizontal = loto.split("} else {")
    # Chiều dọc: số là TIÊU ĐỀ. Chiều ngang: số là NHÃN HÀNG. Cùng dạng `m|n..`.
    assert re.search(r"headKey = \(i\) => \(i === 0 \? null : `m\|n\$\{pad2\(nums\[i - 1\]\)\}`\)",
                     vertical), vertical
    assert re.search(r"i === 0\s*\n?\s*\?\s*`m\|n\$\{pad2\(nums\[y\]\)\}`", horizontal), horizontal
    pair = _block(JS_CODE, "function renderPairMatrix")
    vertical, horizontal = pair.split("} else {")
    assert "`p|c${label(CAP50[i - 1])}`" in vertical, vertical
    assert "`p|c${label(CAP50[y])}`" in horizontal, horizontal


def test_a_marked_header_actually_changes_colour() -> None:
    """Gắn được lớp `marked` mà không có quy tắc cho `th` thì vẫn không đổi màu.

    `th` có nền riêng (`var(--ui-surface-2)`), nên một quy tắc chỉ nhắm `td`
    sẽ bị nền ấy đè và người dùng vẫn thấy "bấm không lên màu".
    """
    css = _without_media(CSS_CODE)
    rule = _block(css, ".sp-table td.marked,")
    assert "th.marked" in rule, rule
    assert "!important" in rule, rule


# --- Thang màu nháy, khoảng gan, biểu đồ mini, popup -------------------------


def test_nhay_cells_and_legend_share_readable_pastel_colors() -> None:
    """Ô và chú giải cùng token; sáng pastel, tối dịu, cả hai đạt AA."""
    from ui_theme import contrast_ratio
    for dark in (False, True):
        css = resolve_theme_colors(_without_media(CSS_CODE), dark)
        colors = set()
        for tier in range(1, 6):
            rule = _block(css, f".sp-table td.sp-n{tier} {{")
            legend = _block(css, f".sp-nl i.sp-n{tier} {{")
            bg = re.search(r"background-color:\s*(#[0-9A-Fa-f]{6})", rule).group(1)
            fg = re.search(r"(?<!-)color:\s*(#[0-9A-Fa-f]{6})", rule).group(1)
            rgb = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
            assert max(rgb) < 100 if dark else min(rgb) >= 200
            assert contrast_ratio(fg, bg) >= 4.5
            assert bg in legend and fg in legend
            colors.add(bg)
        assert len(colors) == 5


def test_the_gan_run_reads_differently_from_an_ordinary_miss() -> None:
    """Ô trống giữa hai lần về, và cả dải trống tới hôm nay, là HAI thứ khác nhau.

    Một ô trống lẻ chỉ là kỳ trượt. Cả dải chạy từ lần về cuối tới hôm nay
    CHÍNH LÀ nhịp gan — thứ người soi cầu đi tìm. Cùng một màu thì phải tự
    đếm bằng mắt.
    """
    body = _block(JS_CODE, "function renderLotoMatrix")
    assert "const ganOf" in body, body[:300]
    assert "day < ganOf[num]" in body, "phải đánh dấu đúng dải tới lần về gần nhất"
    rule = _block(_without_media(CSS_CODE), ".sp-table td.sp-gan {")
    assert "background-color" in rule and "inset" in rule, rule


def test_the_hover_tooltip_states_the_gan_day_count() -> None:
    body = _block(JS_CODE, "function renderLotoMatrix")
    assert "số ngày chưa ra tính đến ngày hiện tại" in body, body[:400]
    assert "ganOf[num]" in body


def test_the_header_chart_is_one_element_per_number_not_an_svg() -> None:
    """100 tiêu đề × một biểu đồ, nên mỗi nút thừa nhân lên trăm lần."""
    body = _block(JS_CODE, "function miniBar")
    # Một `<i>` một thuộc tính, dựng bằng `mk` — không phải SVG, không canvas.
    assert re.search(r'mk\(\s*"i",\s*\{\s*class:\s*"sp-mini-bar"', body), body
    assert '"svg"' not in body and "canvas" not in body, body


def test_the_gan_popup_covers_both_loto_and_special_prize() -> None:
    body = _block(JS_CODE, "function ganCycles")
    # Hai chế độ đọc hai trường KHÁC NHAU của cùng một kỳ.
    assert 'mode === "de"' in body, body
    assert "String(r.s || \"\").slice(-2)" in body, body
    assert "(r.n || []).indexOf(pair)" in body, body
    assert "data-gmode" in JS_CODE, "popup phải có nút đổi chế độ"


def test_the_popup_is_reachable_on_both_pages() -> None:
    """Trang tần suất cặp không có lưới 00-99, nên chỉ gắn popup vào lưới ấy
    là để tính năng chỉ tồn tại ở một trong hai trang.

    Kiểm trên TRANG ĐÃ DỰNG chứ không đếm chỗ gọi trong mã builder. Bản trước
    ghim cứng "đúng hai chỗ gọi ``_gan_modal()``", nên khi trang thứ ba dùng
    lại cùng cái popup thì phép kiểm đỏ lên trong khi cả hai trang nó canh
    vẫn có đủ popup — nó đo số dòng mã, không đo thứ người dùng nhận được.
    """
    for name in ("tan-suat-loto.html", "tan-suat-cap-loto.html"):
        page = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert 'id="sp-gan-modal"' in page, f"{name}: thiếu khung popup chu kỳ gan"
        assert "sp-gan-pick" in page, f"{name}: thiếu ô chọn số để mở popup"


def test_the_popup_filter_button_only_shows_where_it_does_something() -> None:
    """Trang cặp lọc theo HỌ CẶP, nên nút "chỉ xem số 07" ở đó không đổi gì."""
    body = _block(JS_CODE, "function openGanPopup")
    assert '$("sp-picker")' in body, body[-500:]


def test_the_popup_can_redraw_the_matrix_it_filters() -> None:
    """`render` là THAM SỐ, không phải biến toàn cục.

    Gọi thẳng `render()` trong `bindGanPopup` ném "render is not defined", và
    lỗi ấy chỉ hiện trong console — nhìn từ giao diện thì y như nút hỏng vô cớ.
    """
    assert "function bindGanPopup(render)" in JS_CODE
    assert "bindGanPopup(render);" in JS_CODE
    body = _block(JS_CODE, "function bindGanPopup")
    assert "redraw()" in body and "render()" not in body.replace("bindGanPopup(render)", ""), body


def test_sorting_reorders_numbers_and_never_the_days() -> None:
    """Ngày luôn theo trục thời gian; đảo nó đi thì ma trận mất nghĩa."""
    body = _block(JS_CODE, "function renderLotoMatrix")
    assert "nums.sort(" in body, body[:400]
    assert "byDate.sort(" not in body, "không được sắp xếp lại trục ngày"
    # Hoà nhau thì giữ 00 -> 99 để bảng không nhảy giữa các lần dựng.
    assert "|| a - b" in body, body[:400]
    assert BUILDER.count("SORT_CHOICES") >= 1


def test_quick_ranges_count_back_from_the_newest_draw_not_from_today() -> None:
    """Lùi từ hôm nay sẽ hụt mấy kỳ mỗi khi kho chưa cập nhật tới hôm nay."""
    assert "sp-quick" in BUILDER
    body = JS_CODE[JS_CODE.index('const quick = $("sp-quick");'):]
    body = body[: body.index("\n  }") + 4]
    assert "DRAWS[DRAWS.length - 1].d" in body, body
    assert "new Date()" not in body, body


def test_marks_survive_a_reload_because_they_live_in_local_storage() -> None:
    assert "localStorage.getItem(MARK_KEY)" in JS_CODE
    assert "localStorage.setItem(MARK_KEY" in JS_CODE
    # Bọc try/catch: cửa sổ ẩn danh ném lỗi ngay ở lệnh đọc, và một trang
    # trắng thì tệ hơn hẳn việc mất dấu.
    body = JS_CODE[JS_CODE.index("let MARKS = new Set();"):]
    assert "catch" in body[:600], body[:600]


def test_both_matrices_get_the_chart_the_gan_run_and_the_tooltip() -> None:
    """Yêu cầu nói rõ áp cho CẢ HAI trang.

    Bản đầu tôi chỉ nối vào ma trận lô tô; trang tần suất cặp đo ra 0 cột
    mini — tức một nửa yêu cầu im lặng không được làm.
    """
    pair = _block(JS_CODE, "function renderPairMatrix")
    assert "miniBar(recentPair[" in pair, pair[:400]
    assert "gan: pairGan" in pair, pair[:400]
    assert "title: pairTip" in pair, pair[:400]
    # Trần biểu đồ phải khác: mỗi ô cặp cộng lần về của HAI con.
    assert "/ 2)" in pair, "giá trị cặp gấp đôi nên phải chia lại khi vẽ"
