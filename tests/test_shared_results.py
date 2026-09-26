"""Cùng một bảng giải phải giữ đủ dữ liệu kể cả trước khi JavaScript chạy."""

from bs4 import BeautifulSoup

from build_traditional_results import embedded_payload, render_page


ENCODED = "2026-09-26" + "00001" + "00000" + "0000200003" + "00004" * 6 + "0005" * 4 + "0006" * 6 + "007" * 3 + "08" * 4


def test_the_traditional_page_has_all_27_prizes_before_javascript() -> None:
    """Bỏ fallback hoặc ép số về integer sẽ làm mất ô hay mất số 0 đầu."""
    page = render_page(embedded_payload([ENCODED], generated="x"))
    soup = BeautifulSoup(page, "html.parser")
    values = [node.get_text() for node in soup.select("#tr-results .tr-number")]
    assert len(values) == 27
    assert values[:4] == ["00001", "00000", "00002", "00003"]
    assert values[-7:] == ["007", "007", "007", "08", "08", "08", "08"]


def test_the_home_board_has_complete_prizes_and_no_extra_loto_strip() -> None:
    from shared_results import decode_row, render_result_board

    draw = decode_row(ENCODED, metadata={"station": "Nam Định", "special_codes": ["1AB", "2CD"]})
    soup = BeautifulSoup(render_result_board(draw), "html.parser")
    assert len(soup.select(".tr-number")) == 27
    assert len(soup.select(".tr-mini")) == 27
    assert soup.select_one(".tr-loto") is None
    assert soup.select_one(".tr-day-title h2").get_text() == "Xổ số Miền Bắc (Nam Định)"
    assert [node.get_text() for node in soup.select(".tr-special-code")] == ["1AB", "2CD"]
    assert all(node.get("aria-pressed") == "false" for node in soup.select(".tr-number, .tr-mini"))


def test_metadata_never_leaks_between_draw_dates_or_becomes_markup() -> None:
    from shared_results import decode_row, render_result_board

    draw = decode_row(ENCODED, metadata={"date": "2026-09-25", "station": "Hà Nội", "special_codes": ["1AB"]})
    soup = BeautifulSoup(render_result_board(draw), "html.parser")
    assert "Hà Nội" not in soup.select_one(".tr-day-head").get_text()
    assert soup.select_one(".tr-special-code") is None
    assert "Chưa có dữ liệu ký hiệu" in soup.select_one(".tr-special-codes").get_text()

    draw = decode_row(ENCODED, metadata={"station": "<img src=x>", "special_codes": ["<script>x</script>"]})
    soup = BeautifulSoup(render_result_board(draw), "html.parser")
    assert soup.select_one(".tr-day img") is None
    assert soup.select_one(".tr-day script") is None
    assert "<img src=x>" in soup.select_one(".tr-day-title h2").get_text()
