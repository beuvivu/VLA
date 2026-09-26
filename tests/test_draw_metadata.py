"""Chú thích kỳ quay phải bám đúng ngày và đúng kết quả đã xác thực."""

import json
from datetime import date

import pytest

from draw_metadata import load_draw_metadata, parse_draw_metadata, refresh_draw_metadata, station_for_date


def page_for(day="26092026", special="18132", codes="3GX 4GX 5GX 11GX 12GX 15GX"):
    return (f'<div id="kqngay_{day}_kq"><table><tr><td id="mb_prizeCode">'
            + " ".join(f"<span>{code}</span>" for code in codes.split())
            + f'</td></tr><tr><td><span id="mb_prizeDB_item0">{special}</span></td></tr></table></div>')


def test_station_follows_draw_date_for_all_seven_weekdays():
    assert [station_for_date(f"2026-09-{day}") for day in range(21, 28)] == [
        "Hà Nội", "Quảng Ninh", "Bắc Ninh", "Hà Nội", "Hải Phòng", "Nam Định", "Thái Bình"]
    assert station_for_date("not-a-date") == ""


def test_codes_are_read_only_from_the_matching_date_and_special():
    page = page_for("25092026", "34465", "7GV 9GV") + page_for()
    result = parse_draw_metadata(page, date(2026, 9, 26), "18132")
    assert result == {"station": "Nam Định", "special_codes": ["3GX", "4GX", "5GX", "11GX", "12GX", "15GX"], "special": "18132"}
    assert parse_draw_metadata(page, date(2026, 9, 27), "18132") is None
    assert parse_draw_metadata(page, date(2026, 9, 26), "00000") is None


def test_reference_result_block_keeps_all_six_codes():
    from pathlib import Path

    source = Path(__file__).parent / "fixtures/draw_metadata_2026_09_26.html"
    parsed = parse_draw_metadata(source.read_text(encoding="utf-8"), date(2026, 9, 26), "18132")
    assert parsed["special_codes"] == ["3GX", "4GX", "5GX", "11GX", "12GX", "15GX"]


@pytest.mark.parametrize("codes", ["3GX xss", "3GX 3GX", "0GX", "３GX", "3GX <script>"])
def test_malformed_or_duplicate_codes_fail_closed(codes):
    assert parse_draw_metadata(page_for(codes=codes), date(2026, 9, 26), "18132") is None


def test_refresh_retains_old_dates_and_never_borrows_codes_for_missing_day(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "xsmb.csv").write_text("date,special\n2026-09-25,34465\n2026-09-26,18132\n", encoding="utf-8")

    class Response:
        status_code = 200
        text = page_for()

    class Session:
        def get(self, url, timeout):
            assert "26-09-2026" in url and timeout <= 10
            return Response()

    assert refresh_draw_metadata(tmp_path, http=Session()) is True
    assert load_draw_metadata(tmp_path)["2026-09-26"]["special_codes"] == ["3GX", "4GX", "5GX", "11GX", "12GX", "15GX"]
    (data / "xsmb.csv").write_text("date,special\n2026-09-26,18132\n2026-09-27,12345\n", encoding="utf-8")

    class Unavailable:
        def get(self, url, timeout):
            raise OSError("network unavailable")

    assert refresh_draw_metadata(tmp_path, http=Unavailable()) is False
    cached = load_draw_metadata(tmp_path)
    assert "2026-09-26" in cached and "2026-09-27" not in cached
    (data / "xsmb.csv").write_text("date,special\n2026-09-26,00000\n", encoding="utf-8")
    assert load_draw_metadata(tmp_path) == {}


def test_corrupt_cache_cannot_render_codes(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/draw_metadata.json").write_text(json.dumps({"draws": {"2026-09-26": {"special_codes": ["<script>"]}}}))
    assert load_draw_metadata(tmp_path) == {}
