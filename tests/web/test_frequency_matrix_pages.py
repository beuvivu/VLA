from __future__ import annotations

import re
from pathlib import Path

from theme_palette_helpers import theme_tokens, resolve_theme_colors

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "src" / "web" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
CSS = (ROOT / "src" / "web" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
JS_CODE = "\n".join(
    line for line in JS.splitlines() if not line.lstrip().startswith(("//", "*", "/*"))
)
CSS_CODE = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def _block(source: str, start: str) -> str:
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
    assert "opts.key ? opts.key(y, i)" in JS_CODE, "table() phải nhận khoá từ người gọi"
    for name in ("renderLotoMatrix", "renderPairMatrix"):
        block = _block(JS_CODE, f"function {name}")
        vertical, horizontal = block.split("} else {")
        for branch, side in ((vertical, "dọc"), (horizontal, "ngang")):
            assert re.search(r"(?:opts\.key\s*=|(?<![\w])key\s*:)\s*\(y, i\)", branch), (name, side)
            assert re.search(r"\|d\$\{[\w.\[\]\s+-]+\.d\}", branch), (name, side)


def test_both_orientations_build_the_same_identity_for_the_same_cell() -> None:
    loto = _block(JS_CODE, "function renderLotoMatrix")
    vertical, horizontal = loto.split("} else {")
    for branch, name in ((vertical, "dọc"), (horizontal, "ngang")):
        assert re.search(r"`m\|n\$\{pad2\(nums\[[^\]]+\]\)\}\|d\$\{byDate\[[^\]]+\]\.d\}`",
                         branch), (name, branch)
    pair = _block(JS_CODE, "function renderPairMatrix")
    vertical, horizontal = pair.split("} else {")
    for branch, name in ((vertical, "dọc"), (horizontal, "ngang")):
        assert re.search(r"`p\|c\$\{label\(CAP50\[[^\]]+\]\)\}\|d\$\{byDate\[[^\]]+\]\.d\}`",
                         branch), (name, branch)

    for source, prefix in ((loto, "m|"), (pair, "p|")):
        heads = re.findall(r"\?\s*`([a-z])\|", source)
        assert heads, source
        assert set(heads) == {prefix[0]}, (prefix, heads)


def test_old_positional_marks_are_dropped_rather_than_reinterpreted() -> None:
    assert 'MARK_KEY = "sp.marks.v2.' in JS_CODE, JS_CODE[:0]
    assert '"vla.marks."' not in JS_CODE


def test_empty_cells_carry_no_stripe_pattern() -> None:
    base = _without_media(CSS_CODE)
    for selector in (".sp-table td.is-empty", ".sp-nl i.sp-empty-key"):
        rule = _block(base, selector + " {")
        assert "background-image: none" in rule, rule
        assert "gradient" not in rule, rule
    assert "repeating-linear-gradient" not in CSS_CODE


def test_the_empty_cell_has_a_dark_tone_and_a_light_mode_counterpart() -> None:
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
    assert "box-shadow: none" in _block(CSS_CODE, ".sp-table td.is-empty {")
    hit = _block(CSS_CODE, ".sp-table td.sp-hit {")
    assert "inset" in hit, hit


def _without_media(css: str) -> str:
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


BUILDER = (ROOT / "src" / "pages" / "build_stat_pages.py").read_text(encoding="utf-8")


def test_the_pending_draw_is_shown_as_waiting_not_as_a_miss() -> None:
    assert "function pendingDay" in JS_CODE
    assert "pending: true" in JS_CODE
    rule = _block(_without_media(CSS_CODE), ".sp-table td.sp-pending,")
    assert "dashed" in rule, rule
    assert "var(--ui-pending-bg)" in rule, rule
    for dark in (False, True):
        values = theme_tokens(dark)
        assert values["--ui-pending-bg"] != values["--ui-empty-bg"]


def test_today_is_read_in_vietnam_time_not_the_viewer_clock() -> None:
    body = _block(JS_CODE, "function todayInVietnam")
    assert "Asia/Ho_Chi_Minh" in body, body
    assert "en-CA" in body, "định dạng phải cho ra YYYY-MM-DD"


def test_the_pending_column_obeys_the_weekday_filter() -> None:
    body = _block(JS_CODE, "function pendingDay")
    assert 'sp-weekday' in body, body
    assert "weekdayOf(today)" in body, body


def test_the_weekday_filter_exists_and_is_wired_to_rerender() -> None:
    assert "sp-weekday" in BUILDER, "thiếu ô chọn thứ trong HTML"
    assert BUILDER.count('("0", "Chủ nhật")') == 1
    body = _block(JS_CODE, "function selected")
    assert "weekdayOf(r.d) === want" in body, body
    wiring = JS_CODE[JS_CODE.index("[from, to, $(\"sp-year\")"):]
    wiring = wiring[: wiring.index(".forEach")]
    for control in ("sp-weekday", "sp-sort", "sp-orient"):
        assert f'$("{control}")' in wiring, (control, wiring)


def test_weekday_is_computed_without_the_viewer_timezone() -> None:
    body = _block(JS_CODE, "function weekdayOf")
    assert "Date.UTC(" in body and "getUTCDay()" in body, body
    assert "getDay(" not in body.replace("getUTCDay(", ""), body


def test_pair_mode_is_opt_in_and_keeps_two_separate_stores() -> None:
    assert 'id="sp-pair-mode"' in BUILDER
    assert "let PAIR_MARKS = new Set();" in JS_CODE
    body = _block(JS_CODE, "function toggleMark")
    assert body.index("PAIR_MARKS.delete") < body.index("PAIR_MARKS.add"), body
    assert body.index("MARKS.delete") < body.index("MARKS.add"), body
    assert 'id="sp-pair-mode">' in BUILDER and 'id="sp-pair-mode" checked' not in BUILDER


def test_the_pair_is_read_from_the_key_not_from_the_cell_text() -> None:
    body = _block(JS_CODE, "function markPair")
    assert "dataset.key" in body, body
    assert "textContent" not in body, body


def test_switching_pair_mode_off_does_not_erase_existing_marks() -> None:
    body = _block(JS_CODE, "function bindMarking")
    assert 'pairBox.addEventListener("change", paintMarks)' in body, body
    assert "PAIR_MARKS.clear()" not in body.split('addEventListener("change"')[1].split("\n")[0]


def test_requested_short_and_yearly_ranges_are_available() -> None:
    from pages.build_stat_pages import QUICK_RANGES

    assert {"10", "30", "100", "365"}.issubset(dict(QUICK_RANGES))


def test_the_matrix_does_not_touch_the_frame_it_sits_in() -> None:
    rule = _block(_without_media(CSS_CODE), ".sp-scroll{")
    assert "padding-bottom" in rule, rule
    assert "padding-left" not in rule and "padding:" not in rule, rule


def test_the_number_is_clickable_in_both_orientations() -> None:
    builder = _block(JS_CODE, "function table(")
    assert "opts.headKey && opts.headKey(i)" in builder, builder[:400]
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
    loto = _block(JS_CODE, "function renderLotoMatrix")
    vertical, horizontal = loto.split("} else {")
    assert re.search(r"headKey = \(i\) => \(i === 0 \? null : `m\|n\$\{pad2\(nums\[i - 1\]\)\}`\)",
                     vertical), vertical
    assert re.search(r"i === 0\s*\n?\s*\?\s*`m\|n\$\{pad2\(nums\[y\]\)\}`", horizontal), horizontal
    pair = _block(JS_CODE, "function renderPairMatrix")
    vertical, horizontal = pair.split("} else {")
    assert "`p|c${label(CAP50[i - 1])}`" in vertical, vertical
    assert "`p|c${label(CAP50[y])}`" in horizontal, horizontal


def test_a_marked_header_actually_changes_colour() -> None:
    css = _without_media(CSS_CODE)
    rule = _block(css, ".sp-table td.marked,")
    assert "th.marked" in rule, rule
    assert "!important" in rule, rule


def test_nhay_cells_and_legend_share_readable_pastel_colors() -> None:
    from web.ui_theme import contrast_ratio
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
    body = _block(JS_CODE, "function miniBar")
    assert re.search(r'mk\(\s*"i",\s*\{\s*class:\s*"sp-mini-bar"', body), body
    assert '"svg"' not in body and "canvas" not in body, body


def test_the_gan_popup_covers_both_loto_and_special_prize() -> None:
    body = _block(JS_CODE, "function ganCycles")
    assert 'mode === "de"' in body, body
    assert "String(r.s || \"\").slice(-2)" in body, body
    assert "(r.n || []).indexOf(pair)" in body, body
    assert "data-gmode" in JS_CODE, "popup phải có nút đổi chế độ"


def test_the_popup_is_reachable_on_both_pages() -> None:
    for name in ("tan-suat-loto.html", "tan-suat-cap-loto.html"):
        page = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert 'id="sp-gan-modal"' in page, f"{name}: thiếu khung popup chu kỳ gan"
        assert "sp-gan-pick" in page, f"{name}: thiếu ô chọn số để mở popup"


def test_the_popup_filter_button_only_shows_where_it_does_something() -> None:
    body = _block(JS_CODE, "function openGanPopup")
    assert '$("sp-picker")' in body, body[-500:]


def test_the_popup_can_redraw_the_matrix_it_filters() -> None:
    assert "function bindGanPopup(render)" in JS_CODE
    assert "bindGanPopup(render);" in JS_CODE
    body = _block(JS_CODE, "function bindGanPopup")
    assert "redraw()" in body and "render()" not in body.replace("bindGanPopup(render)", ""), body


def test_sorting_reorders_numbers_and_never_the_days() -> None:
    body = _block(JS_CODE, "function renderLotoMatrix")
    assert "nums.sort(" in body, body[:400]
    assert "byDate.sort(" not in body, "không được sắp xếp lại trục ngày"
    assert "|| a - b" in body, body[:400]
    assert BUILDER.count("SORT_CHOICES") >= 1


def test_quick_ranges_count_back_from_the_newest_draw_not_from_today() -> None:
    assert "sp-quick" in BUILDER
    body = JS_CODE[JS_CODE.index('const quick = $("sp-quick");'):]
    body = body[: body.index("\n  }") + 4]
    assert "DRAWS[DRAWS.length - 1].d" in body, body
    assert "new Date()" not in body, body


def test_marks_survive_a_reload_because_they_live_in_local_storage() -> None:
    assert "localStorage.getItem(MARK_KEY)" in JS_CODE
    assert "localStorage.setItem(MARK_KEY" in JS_CODE
    body = JS_CODE[JS_CODE.index("let MARKS = new Set();"):]
    assert "catch" in body[:600], body[:600]


def test_both_matrices_get_the_chart_the_gan_run_and_the_tooltip() -> None:
    pair = _block(JS_CODE, "function renderPairMatrix")
    assert "miniBar(recentPair[" in pair, pair[:400]
    assert "gan: pairGan" in pair, pair[:400]
    assert "title: pairTip" in pair, pair[:400]
    assert "/ 2)" in pair, "giá trị cặp gấp đôi nên phải chia lại khi vẽ"
