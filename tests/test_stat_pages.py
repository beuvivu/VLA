"""Kiểm thử mười trang thống kê có bộ lọc thời gian tùy biến.

Các trang này tính toán bằng JavaScript trong trình duyệt vì kho phát hành
site tĩnh: không có server để gọi API, mà dựng sẵn mọi tổ hợp dải ngày là bất
khả thi. Bộ test vì thế kiểm cả cấu trúc trang lẫn tính đúng đắn của dữ liệu
được nhúng.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from build_stat_pages import (
    CHANCE_NOTES,
    LOTO_BASELINE,
    PAGES,
    PAIR_BASELINE,
    PRIZE_WIDTH,
    load_draws,
    render_page,
)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


@pytest.fixture(scope="module")
def draws():
    return load_draws(ROOT)


def _soup(slug: str) -> BeautifulSoup:
    return BeautifulSoup((DOCS / f"{slug}.html").read_text(encoding="utf-8"), "html.parser")


# --- Nạp dữ liệu -----------------------------------------------------------


def test_every_draw_has_exactly_27_numbers(draws) -> None:
    """27 ô giải là bất biến của XSMB; kỳ thiếu ô phải bị loại chứ không được
    đưa vào với dữ liệu khuyết."""
    assert draws, "không nạp được kỳ nào"
    for row in draws:
        assert len(row["n"]) == 27, f"kỳ {row['d']} có {len(row['n'])} ô"


def test_numbers_keep_their_leading_zero(draws) -> None:
    """CSV lưu kiểu số nguyên nên mất số 0 đầu — đo được 10,3% số ô. Không
    zfill thì mọi phép cắt chữ số theo vị trí đều lệch."""
    for row in draws:
        for value in row["n"]:
            assert len(value) == 2 and value.isdigit(), f"{row['d']}: {value!r}"


def test_special_is_five_digits(draws) -> None:
    for row in draws:
        assert len(row["s"]) == 5 and row["s"].isdigit(), f"{row['d']}: {row['s']!r}"


def test_draws_are_sorted_by_date(draws) -> None:
    """Bộ máy JS lấy DRAWS[len-1] làm kỳ mới nhất và cắt N kỳ cuối cho bộ lọc
    nhanh; thứ tự sai thì mọi dải đều sai."""
    dates = [row["d"] for row in draws]
    assert dates == sorted(dates)


def test_prize_widths_sum_to_the_107_digit_board() -> None:
    counts = {"special": 1, "prize1": 1, "prize2": 2, "prize3": 6,
              "prize4": 4, "prize5": 6, "prize6": 3, "prize7": 4}
    assert sum(counts.values()) == 27
    assert sum(PRIZE_WIDTH[k] * n for k, n in counts.items()) == 107


# --- Tỉ lệ nền -------------------------------------------------------------


def test_loto_baseline_is_the_known_constant() -> None:
    assert LOTO_BASELINE == pytest.approx(0.2377, abs=5e-4)


def test_pair_baseline_uses_inclusion_exclusion() -> None:
    """Hai số cùng rút từ 27 ô giải nên KHÔNG độc lập; dùng bình phương tỉ lệ
    đơn là sai."""
    assert PAIR_BASELINE == pytest.approx(0.0549, abs=5e-4)
    assert PAIR_BASELINE != pytest.approx(LOTO_BASELINE**2, abs=1e-6)


# --- Trang đã dựng ---------------------------------------------------------


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.slug)
def test_page_file_exists(page) -> None:
    assert (DOCS / f"{page.slug}.html").exists()


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.slug)
def test_page_has_its_title_and_controls(page) -> None:
    soup = _soup(page.slug)
    assert soup.find("h1") is not None
    assert page.title in soup.find("h1").get_text()
    assert soup.select(".sp-controls"), "thiếu thanh điều khiển bộ lọc"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.slug)
def test_page_embeds_the_history(page) -> None:
    text = (DOCS / f"{page.slug}.html").read_text(encoding="utf-8")
    assert "__VLA_DRAWS__" in text, "trang phải nhúng lịch sử để lọc phía trình duyệt"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.slug)
def test_render_function_is_declared_not_a_const(page) -> None:
    """boot() tra hàm qua window[renderName]. `const` ở cấp cao nhất của
    script cổ điển KHÔNG tạo thuộc tính trên window, nên hàm khai bằng const
    sẽ làm trang im lặng không vẽ gì — đã gặp đúng lỗi này với
    renderSpecialByMonth và renderSpecialByYear.
    """
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert re.search(rf"^function {re.escape(page.render)}\s*\(", js, re.M), (
        f"{page.render} phải khai bằng `function`, không phải `const`"
    )


def test_no_render_function_is_declared_with_const() -> None:
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert not re.search(r"^const render\w+\s*=", js, re.M)


def test_page_slugs_are_unique() -> None:
    slugs = [p.slug for p in PAGES]
    assert len(slugs) == len(set(slugs))


def test_all_ten_requested_pages_are_built() -> None:
    """Mười trang được yêu cầu, cộng trang cặp lộn tách ra riêng."""
    expected = {
        "bang-dac-biet", "bang-dac-biet-thang", "bang-dac-biet-nam",
        "tan-suat-loto", "tan-suat-cap-loto", "cap-lon-loto", "dau-duoi-loto",
        "cau-giai-dac-biet", "giai-dac-biet-theo-tong",
        "chu-ky-dac-biet", "cau-dac-biet-theo-bo-so", "giai-db-ngay-mai",
        "thong-ke-tong-hop",
    }
    assert {p.slug for p in PAGES} == expected


# --- Ghi chú mốc ngẫu nhiên ------------------------------------------------


def test_pair_chance_note_scales_with_the_embedded_history() -> None:
    """Ghi chú mốc ngẫu nhiên của trang tần suất cặp phải tính theo số kỳ thật.

    Bản cũ đóng cứng "39,8 lần" đo trên 393 kỳ. Mốc đó tăng tuyến tính theo
    độ dài lịch sử, nên sau khi bổ sung dữ liệu nó biến mọi cặp thành bất
    thường nếu không tính lại.
    """
    from build_stat_pages import chance_note_context

    short = chance_note_context(393)
    long = chance_note_context(2200)

    assert short["chance_max"] == "39,9"
    assert long["chance_max"] == "161,8"
    assert short["pair_expected"] == "21,6"
    assert long["pair_expected"] == "120,7"


def test_pair_chance_grid_matches_the_exact_formula() -> None:
    """Lưới tra là bảng dựng sẵn của chính công thức đóng, không phải số gõ tay."""
    from build_stat_pages import PAIR_CHANCE_GRID_POINTS, pair_chance_grid
    from xsmb_domain import pair_chance_maximum

    grid = pair_chance_grid()
    assert [row[0] for row in grid] == list(PAIR_CHANCE_GRID_POINTS)

    for n, mean, low, high in grid:
        exact_mean, (exact_low, exact_high) = pair_chance_maximum(int(n))
        assert mean == pytest.approx(exact_mean, abs=0.005)
        assert (low, high) == (exact_low, exact_high)

    counts = [row[0] for row in grid]
    means = [row[1] for row in grid]
    assert counts == sorted(counts), "lưới phải tăng dần để nội suy được"
    assert means == sorted(means), "cực đại phải tăng theo số kỳ"


def test_pair_chance_grid_interpolates_within_one_percent() -> None:
    """Trình duyệt nội suy tuyến tính trên lưới này. Lưới quá thưa thì mốc
    hiển thị sai, mà sai ở đây nghĩa là bảng tuyên bố "bất thường" nhầm."""
    from build_stat_pages import pair_chance_grid
    from xsmb_domain import pair_chance_maximum

    grid = pair_chance_grid()

    def interpolate(n: int) -> float:
        if n <= grid[0][0]:
            return grid[0][1]
        if n >= grid[-1][0]:
            return grid[-1][1]
        for (a_n, a_m, _, _), (b_n, b_m, _, _) in zip(grid, grid[1:]):
            if a_n <= n <= b_n:
                t = (n - a_n) / (b_n - a_n)
                return a_m + t * (b_m - a_m)
        raise AssertionError("ngoài lưới")

    worst = max(
        abs(interpolate(n) - pair_chance_maximum(n)[0]) / pair_chance_maximum(n)[0]
        for n in range(10, 7300, 37)
    )
    assert worst < 0.01, f"sai số nội suy {worst:.2%} vượt 1%"


def test_pair_page_recomputes_the_chance_note_for_the_filtered_range() -> None:
    """Trang có bộ lọc 30/60/90/180/365 kỳ. Ghi chú cố định một con số là sai
    ngay khi người dùng bấm lọc: ở "30 kỳ" mốc thật là 7,7 chứ không phải 39,8
    của toàn bộ lịch sử — lệch 5 lần, và bảng đọc thành tín hiệu."""
    html = (DOCS / "tan-suat-cap-loto.html").read_text(encoding="utf-8")
    assert "__VLA_PAIR_CHANCE__" in html, "trang phải nhúng lưới tra cho trình duyệt"

    note = _soup("tan-suat-cap-loto").select_one("#sp-chance")
    assert note is not None, "ghi chú thiếu chỗ để JavaScript viết lại"

    js = (
        Path(__file__).resolve().parents[1] / "src" / "templates" / "stat_pages.js"
    ).read_text(encoding="utf-8")
    body = js[js.index("function renderPairFrequency()") :]
    body = body[: body.index("\nfunction ", 1)]
    assert "updateChanceNote(" in body, (
        "renderPairFrequency phải cập nhật ghi chú, nếu không nó đứng yên khi lọc"
    )


def test_chance_notes_are_format_safe() -> None:
    """Ghi chú đi qua ``str.format``; một dấu ngoặc nhọn lạc sẽ làm hỏng trang
    lúc dựng chứ không phải lúc chạy test khác."""
    from build_stat_pages import chance_note_context

    context = chance_note_context(393)
    for slug, note in CHANCE_NOTES.items():
        note.format(**context)  # không được ném lỗi


def test_baselines_come_from_the_single_source_of_truth() -> None:
    """Hai mốc từng được chép lại trong từng trình dựng trang; chính bản chép
    đó khiến 39,8 nằm lại sau khi lịch sử dài ra."""
    from xsmb_domain import LOTO_BASELINE_RATE, PAIR_COOCCURRENCE_RATE

    assert LOTO_BASELINE is LOTO_BASELINE_RATE
    assert PAIR_BASELINE is PAIR_COOCCURRENCE_RATE


@pytest.mark.parametrize("slug", sorted(CHANCE_NOTES))
def test_ranking_pages_carry_a_chance_note(slug) -> None:
    """Bảng xếp hạng thiếu mốc ngẫu nhiên trông như quy luật trong khi đó là
    mức ngẫu nhiên thường tạo ra."""
    note = _soup(slug).select_one(".sp-note")
    assert note is not None, f"{slug} thiếu ghi chú mốc ngẫu nhiên"
    assert len(note.get_text(strip=True)) > 60


def test_prediction_page_states_it_is_not_calibrated() -> None:
    """Trang dự báo phải nói rõ đây là xếp hạng mô tả, không phải xác suất."""
    text = _soup("giai-db-ngay-mai").select_one(".sp-note").get_text(" ", strip=True)
    assert "không phải xác suất đã hiệu chuẩn" in text


# --- Dựng lại được ---------------------------------------------------------


def test_render_page_is_deterministic_apart_from_the_timestamp(draws) -> None:
    a = render_page(PAGES[0], draws, generated="2026-01-01T00:00:00Z")
    b = render_page(PAGES[0], draws, generated="2026-01-01T00:00:00Z")
    assert a == b


def test_embedded_payload_is_valid_json(draws) -> None:
    html = render_page(PAGES[0], draws[:5], generated="2026-01-01T00:00:00Z")
    match = re.search(r"__VLA_DRAWS__=(\[.*?\]);", html, re.S)
    assert match, "không tìm thấy khối dữ liệu nhúng"
    payload = json.loads(match.group(1).replace("\\u0026", "&"))
    assert len(payload) == 5
    assert set(payload[0]) == {"d", "s", "n"}


# --- Giải đặc biệt đủ 5 chữ số ---------------------------------------------


@pytest.mark.parametrize(
    "slug", ["bang-dac-biet", "bang-dac-biet-thang", "bang-dac-biet-nam"]
)
def test_special_tables_render_all_five_digits(slug) -> None:
    """Bảng đặc biệt phải liệt kê TRỌN giải, không cắt còn hai số cuối.

    Dữ liệu nhúng vốn giữ đủ 5 chữ số; bản trước cắt ngay lúc dựng bảng nên
    người đọc mất ba chữ số đầu và không đối chiếu được với kết quả gốc.
    """
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function specialFull(" in js

    body = js[js.index("function specialFull(") :]
    body = body[: body.index("\n}") + 2]
    assert "padStart(5" in body, "phải bù 0 cho giải mất số 0 đứng đầu"
    assert "slice(0, 3)" in body and "slice(3)" in body, (
        "phải hiện ba số đầu cùng hai số cuối, không chỉ hai số cuối"
    )
    page = (DOCS / f"{slug}.html").read_text(encoding="utf-8")
    assert "sp-de" in page, f"{slug} chưa dùng lớp hiển thị giải đủ 5 số"

    # Hàm tồn tại là chưa đủ — phải được GỌI trong đúng hàm dựng của trang này.
    # Theo CHUỖI GỌI, không ghim một tên hàm: bảng đặc biệt dựng ô qua
    # specialCell(), và specialCell() dựng phần số qua specialFull(). Ghim tên
    # cụ thể thì test đỏ mỗi lần tách hàm dù hành vi không đổi.
    render = {
        "bang-dac-biet": "renderSpecialByWeek",
        "bang-dac-biet-thang": "renderSpecialByMonth",
        "bang-dac-biet-nam": "renderSpecialByYear",
    }[slug]

    def body_of(name: str) -> str:
        chunk = js[js.index(f"function {name}(") :]
        return chunk[: chunk.index("\nfunction ", 1)]

    reached = set()
    frontier = [render]
    while frontier:
        name = frontier.pop()
        if name in reached:
            continue
        reached.add(name)
        body = body_of(name)
        assert ".slice(-2)" not in body, f"{name} còn cắt hai số cuối khi hiển thị"
        for helper in ("specialCell", "specialFull", "weekGrid", "monthGrid"):
            if f"{helper}(" in body:
                frontier.append(helper)

    assert "specialFull" in reached, (
        f"{render} không dẫn tới specialFull qua bất kỳ đường nào; giải bị cắt"
    )


def test_counting_uses_last_two_digits_but_display_does_not() -> None:
    """Đếm theo hai số cuối là ĐÚNG (lô tô là hai chữ số); cắt khi HIỂN THỊ mới
    là sai. Hai việc khác nhau nên phải có hai hàm khác nhau."""
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function lastTwo(" in js
    assert "r.s.slice(-2)" not in js, (
        "còn chỗ cắt thẳng chuỗi giải; dùng lastTwo() để đếm hoặc "
        "specialFull() để hiện"
    )


# --- Cặp lộn ----------------------------------------------------------------


def test_reverse_pairs_are_true_reversals_not_kep_bong() -> None:
    """"Lộn" là đảo hai chữ số: 01 <-> 10. Chỉ có 45 cặp, vì 10 số kép đảo lại
    chính nó.

    Kho từng gộp 10 số kép thành 5 họ "kép bóng" (00-55, 11-66, ...) cho tròn
    50 cặp. BÓNG (0<->5, 1<->6) là khái niệm khác hẳn LỘN, nên bảng cũ trộn hai
    thứ rồi gọi chung là cặp lộn.
    """
    pairs = []
    for a in range(100):
        b = (a % 10) * 10 + a // 10
        if a < b:
            pairs.append((a, b))

    assert len(pairs) == 45
    assert not any(a % 11 == 0 or b % 11 == 0 for a, b in pairs), (
        "số kép không được xuất hiện trong cặp lộn"
    )

    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function reversePairs(" in js
    assert "function doubleNumbers(" in js
    assert "sp-kep" in js, "số kép phải liệt kê riêng, không trộn vào cặp lộn"


def test_reverse_pair_page_exists_separately() -> None:
    """Trang riêng cho tiện theo dõi, không nhét thêm vào trang tần suất cặp."""
    assert "cap-lon-loto" in {p.slug for p in PAGES}
    from ui_theme import SITE_NAV

    links = [item[0] for group in SITE_NAV for item in group[1]]
    assert "cap-lon-loto.html" in links, "trang mới phải vào được từ điều hướng"


# --- Đánh dấu ô để so sánh --------------------------------------------------


def test_cells_can_be_marked_for_comparison() -> None:
    """Bảng dài hàng chục hàng; không có cách đánh dấu thì chỉ cần cuộn một cái
    là mất dấu những ô đang muốn so."""
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function bindMarking(" in js
    assert 'data-key=' in js, "ô phải có khoá ổn định để nhớ được"
    assert "localStorage" in js

    assert "try {" in js and "catch" in js, (
        "cửa sổ ẩn danh ném lỗi ngay ở lệnh đọc localStorage; không bọc thì "
        "trang trắng"
    )
    css = (ROOT / "src" / "templates" / "stat_pages.css").read_text(encoding="utf-8")
    assert "td.marked" in css


@pytest.mark.parametrize("slug", sorted(p.slug for p in PAGES))
def test_every_page_can_clear_its_marks(slug) -> None:
    """Ô bấm được thì phải gỡ được.

    Ba trang dùng bộ chọn dạng nút nhanh từng thiếu thanh công cụ này: ô vẫn
    nhận click và vẫn lưu vào localStorage, nhưng không có nút xoá nên người
    dùng đánh dấu xong thì mắc kẹt.
    """
    page = (DOCS / f"{slug}.html").read_text(encoding="utf-8")
    assert 'id="sp-clear-marks"' in page, f"{slug} thiếu nút xoá đánh dấu"
    assert 'id="sp-mark-count"' in page, f"{slug} thiếu số đếm ô đã đánh dấu"


# --- Ô bảng đặc biệt sáu trường ---------------------------------------------


def test_bo_lookup_comes_from_the_domain_helper() -> None:
    """Cột "Bộ" của trang tham chiếu chính là ``bo_family_id``.

    Đo trên 24 ô thật lấy từ hainhay.net, hàm sẵn có của kho khớp 100%. Bảng
    tra phải dựng SẴN từ hàm đó chứ không cài lại công thức trong JavaScript:
    một bản chép thứ hai là một bản sẽ trôi khỏi bản gốc.
    """
    from build_stat_pages import bo_lookup
    from number_reference import bo_family_id

    table = bo_lookup()
    assert len(table) == 100
    for n in range(100):
        assert table[n] == bo_family_id(f"{n:02d}")

    # Mẫu thật quan sát được trên trang tham chiếu.
    for two, expected in (("68", "13"), ("48", "34"), ("21", "12"), ("77", "22")):
        assert table[int(two)] == expected

    assert len(set(table)) == 15, "bộ số có đúng 15 họ"


def test_special_cell_carries_all_six_reference_fields() -> None:
    """Ô của trang tham chiếu là sáu trường, không phải một con số:
    ``570 68 4 6 8 C 13`` = giải, Tổng, Đầu, Đuôi, Chẵn/Lẻ, Bộ."""
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function specialCell(" in js

    body = js[js.index("function specialCell(") :]
    body = body[: body.index("\n}") + 2]

    assert "(dau + duoi) % 10" in body, "Tổng = (Đầu + Đuôi) mod 10"
    assert 'duoi % 2 === 0 ? "C" : "L"' in body, "Chẵn/Lẻ xét theo Đuôi, không phải Đầu"
    assert "BO_LOOKUP[" in body, "Bộ phải tra bảng dựng sẵn"

    fields = js[js.index("const DE_FIELDS") :]
    fields = fields[: fields.index("];") + 2]
    for key in ("ngay", "tong", "dau", "duoi", "chanle", "bo"):
        assert f'key: "{key}"' in fields, f"thiếu trường {key}"


@pytest.mark.parametrize(
    "slug", ["bang-dac-biet", "bang-dac-biet-thang", "bang-dac-biet-nam"]
)
def test_special_pages_can_toggle_each_field(slug) -> None:
    """Trang tham chiếu có đúng sáu ô đánh dấu bật/tắt từng trường."""
    page = (DOCS / f"{slug}.html").read_text(encoding="utf-8")
    assert 'id="sp-fields-toggle"' in page, f"{slug} thiếu hộp bật/tắt trường"

    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "function bindFieldToggles(" in js
    assert "__VLA_BO__" in page, f"{slug} chưa nhúng bảng tra bộ số"


def test_matrix_note_does_not_shadow_the_chance_note() -> None:
    """Ghi chú kích thước ma trận phải có lớp RIÊNG.

    Bản đầu dùng chung lớp ``.sp-note``, và vì nó rỗng trong HTML tĩnh lại
    đứng trước, ``select_one('.sp-note')`` bắt phải nó thay vì ghi chú mốc
    ngẫu nhiên — đúng thứ mà mọi bảng xếp hạng trong kho này dựa vào để không
    chế ra tín hiệu.
    """
    for slug in ("tan-suat-loto", "tan-suat-cap-loto"):
        page = (DOCS / f"{slug}.html").read_text(encoding="utf-8")
        assert 'class="sp-matrix-note"' in page
        assert 'class="sp-note" id="sp-matrix-note"' not in page

        note = _soup(slug).select_one(".sp-note")
        assert note is not None and len(note.get_text(strip=True)) > 60, (
            f"{slug}: ghi chú mốc ngẫu nhiên bị che"
        )


def test_matrix_caps_its_column_count() -> None:
    """Chọn "Tất cả" trên kho 2392 kỳ cho 239 000 ô và trình duyệt nghẹn.
    Phải có trần, và phải nói ra trên trang thay vì để người dùng ngồi nhìn
    trang treo."""
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    assert "MATRIX_MAX_DAYS" in js
    cap = int(re.search(r"MATRIX_MAX_DAYS = (\d+)", js).group(1))
    assert 30 <= cap <= 400, f"trần {cap} kỳ không hợp lý"
    assert "sp-matrix-note" in js, "phải báo cho người đọc biết đã cắt bớt"


# --- Giải đặc biệt theo tổng ------------------------------------------------


def test_parity_field_covers_both_digits() -> None:
    """Chẵn/Lẻ là HAI ký tự: của Đầu rồi của Đuôi.

    Hai trang tham chiếu khác nhau ở chỗ này — hainhay ghi một ký tự theo
    Đuôi, thongkemienbac ghi cả hai. Kiểm trên 15 ô thật của thongkemienbac:
    49 cho "CL" (Đầu 4 chẵn, Đuôi 9 lẻ). Bản một ký tự mất một nửa thông tin.
    """
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    body = js[js.index("function specialCell(") :]
    body = body[: body.index("\n}") + 2]
    assert 'dau % 2 === 0 ? "C" : "L"' in body, "thiếu chẵn/lẻ của Đầu"
    assert 'duoi % 2 === 0 ? "C" : "L"' in body, "thiếu chẵn/lẻ của Đuôi"


def test_transition_table_ranks_by_standardised_deviation() -> None:
    """Xếp bảng chuyển tổng theo TỈ LỆ là cách chắc chắn đẩy nhiễu lên đầu.

    Đo trên trang vừa dựng: ô dẫn đầu là 3 lần trên 9 kỳ, cho 33 %. Ba lần
    chẳng nói lên điều gì, nhưng nếu xếp theo tỉ lệ thì nó đứng trên mọi ô có
    mẫu lớn. Chia cho sai số chuẩn thì mẫu nhỏ tự lùi xuống.
    """
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    body = js[js.index("function renderSpecialByTong(") :]

    assert "Math.sqrt(P0 * (1 - P0) / n)" in body, "thiếu sai số chuẩn"
    assert "Math.abs(y[5]) - Math.abs(x[5])" in body, (
        "phải xếp theo độ lệch chuẩn hoá, không theo tỉ lệ thô"
    )
    assert "Trên tổng số kỳ" in body, "phải hiện mẫu nền, nếu không tỉ lệ vô nghĩa"


def test_transition_table_skips_non_consecutive_draws() -> None:
    """Nối hai kỳ cách nhau nhiều ngày thành "hôm sau" là bịa ra một chuyển
    tiếp không tồn tại. XSMB có ngày nghỉ quay, nên ranh giới đó phải bỏ."""
    js = (ROOT / "src" / "templates" / "stat_pages.js").read_text(encoding="utf-8")
    body = js[js.index("function renderSpecialByTong(") :]
    assert "gap !== 1" in body, "phải bỏ qua ranh giới ngày nghỉ quay"


def test_tong_page_states_the_chance_level() -> None:
    """Tổng có 10 giá trị nên mức ngẫu nhiên là 10 % mỗi ô. Thiếu con số đó
    thì bảng đọc thành tín hiệu."""
    text = _soup("giai-dac-biet-theo-tong").select_one(".sp-note").get_text(" ", strip=True)
    assert "10 %" in text
    assert "lệch chuẩn hoá" in text.lower()
    assert "không phải xác suất đã hiệu chuẩn" in text
