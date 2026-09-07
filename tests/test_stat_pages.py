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
    """Mười trang tương ứng danh sách được yêu cầu."""
    expected = {
        "bang-dac-biet", "bang-dac-biet-thang", "bang-dac-biet-nam",
        "tan-suat-loto", "tan-suat-cap-loto", "dau-duoi-loto",
        "chu-ky-dac-biet", "cau-dac-biet-theo-bo-so", "giai-db-ngay-mai",
        "thong-ke-tong-hop",
    }
    assert {p.slug for p in PAGES} == expected


# --- Ghi chú mốc ngẫu nhiên ------------------------------------------------


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
