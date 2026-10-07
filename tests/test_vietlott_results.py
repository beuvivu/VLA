"""Trang Vietlott dựng từ engine ``vietlott/``: đủ 8 trang qua khung chung, không
lộ nguồn, không bịa giá trị khuyết, và đọc đúng dữ liệu đã commit của engine."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

import build_vietlott_results as b

SOURCE_MARKERS = ("nhanaz", "minhngoc", "vietlott.vn", "mirror", "SECRET-SOURCE")


def _matrix(draw_id: int, jackpot: int | None, *, numbers=(1, 2, 3, 4, 5, 6), bonus=None) -> dict:
    return {
        "draw_id": draw_id, "draw_date": f"2026-10-0{draw_id % 9 + 1}T00:00:00+07:00",
        "numbers": list(numbers), "bonus": bonus, "time_precision": "day",
        "source": "nhanaz:SECRET-SOURCE", "source_url": "https://SECRET-SOURCE.example/x",
        "official_url": "https://vietlott.vn/vi/645", "official_direct": False, "facts": {},
        "prize_source": "nhanaz:SECRET-SOURCE",
        "prizes": [
            {"label": "Jackpot", "condition": "6 số chính", "value_vnd": jackpot, "code": "jackpot1",
             "winners": None, "pool": True, "source": "nhanaz:SECRET-SOURCE"},
            {"label": "Giải Nhất", "condition": "5 số chính", "value_vnd": 10_000_000, "code": "first",
             "winners": 12, "pool": False, "source": "catalogue"},
        ],
    }


def _max_draw() -> dict:
    groups = [("Đặc biệt", ["038", "091"]), ("Nhất", ["232", "504", "975", "346"]),
              ("Nhì", ["989", "690", "066", "206", "904", "115"]),
              ("Ba", ["610", "570", "216", "577", "913", "985", "577", "286"])]
    return {"draw_id": 788, "draw_date": "2026-10-06T00:00:00+07:00",
            "numbers": [x for _, g in groups for x in g], "bonus": None, "source": "nhanaz",
            "official_url": "https://vietlott.vn/max", "facts": {},
            "prizes": [{"label": label, "numbers": g} for label, g in groups]}


def _dashboard() -> dict:
    latest = _matrix(1571, None)                       # jackpot kỳ mới CHƯA công bố
    older = _matrix(1570, 123_456_789_000)             # kỳ trước có jackpot
    forecast = {"target_id": 1572, "target_date": "2026-10-07", "made_at": "2026-10-04T21:23:33+07:00",
                "product": "mega645", "engine": "ml", "registered": True,
                "components": [{"name": "main", "kind": "set",
                                "top": [{"numbers": [4, 12, 31, 34, 38, 41], "p_model": 1.26e-07, "p_fair": 1.2e-07}]}]}
    compared = {"status": "matched", "product": "mega645", "target_id": 1571, "target_date": "2026-10-04",
                "registered": True, "result": latest,
                "tickets": [{"numbers": [14, 20, 21, 24, 27, 30], "matched_numbers": [20], "hits": 1}]}
    mismatched = {"status": "date_mismatch", "product": "mega645", "target_id": 1569,
                  "target_date": "2026-10-01", "registered": True, "tickets": []}
    lotto_draw = _matrix(930, None, numbers=(15, 22, 27, 28, 29), bonus=3)
    lotto_compared = {"status": "matched", "product": "lotto535", "target_id": 930, "target_date": "2026-10-06",
                      "registered": True, "result": lotto_draw,
                      "tickets": [{"numbers": [1, 2, 3, 4, 5], "special": 7, "matched_numbers": [], "hits": 0}]}
    reference = {**forecast, "registered": False, "status": "reference",
                 "note": "Dự báo tham khảo; chưa xác minh thời điểm từng kỳ."}
    products = [
        {"product": "mega645", "name": "Mega 6/45", "schedule": "18:00 Thứ 4, 6, CN",
         "official_url": "https://vietlott.vn/vi/645", "latest": latest, "draws": [latest, older],
         "prize_catalogue": [{"label": "Jackpot", "condition": "6 số chính", "value_vnd": None, "code": "jackpot1"}],
         "next_forecast": forecast, "comparisons": [compared, mismatched]},
        {"product": "lotto535", "name": "Lotto 5/35", "schedule": "13:00 và 21:00",
         "latest": lotto_draw, "draws": [lotto_draw], "prize_catalogue": [], "next_forecast": None,
         "comparisons": [lotto_compared]},
        {"product": "keno", "name": "Keno", "schedule": "~8 phút/kỳ",
         "latest": {**_matrix(298378, None, numbers=range(1, 21)), "prizes": [],
                    "facts": {"large": 11, "small": 9, "even": 12, "odd": 8}},
         "draws": [], "prize_catalogue": [], "next_forecast": reference, "comparisons": []},
        {"product": "bingo18", "name": "Bingo18", "schedule": "~6 phút/kỳ",
         "latest": {**_matrix(190110, None, numbers=(5, 1, 6)), "prizes": [],
                    "facts": {"sum": 12, "size": "Lớn"}},
         "draws": [], "prize_catalogue": [], "next_forecast": None, "comparisons": []},
        {"product": "max3dpro", "name": "Max 3D Pro", "schedule": "18:00 Thứ 3, 5, 7",
         "latest": _max_draw(), "draws": [_max_draw()], "prize_catalogue": [], "next_forecast": None,
         "comparisons": []},
    ]
    return {"schema_version": 1, "generated_at": "2026-10-07T23:16:50+07:00", "products": products,
            "warnings": ["result_conflict: mega645 #1570; nguồn nhanaz:SECRET-SOURCE / vietlott.vn"],
            "stats": {"products": 7, "results": 4, "registered_next": 1, "compared_draws": 1},
            "analysis": {"mega645": {"draws": 1571, "last_id": 1571, "last_date": "2026-10-04",
                                     "verdict": "Mô hình tự học CHƯA tìm thấy tín hiệu vượt ngẫu nhiên.",
                                     "evidence": {"found": False, "text": "Chưa có bằng chứng."},
                                     "board": {"recorded": 2, "scored": 1, "hits": 1.0, "expected": 0.8}}}}


@pytest.fixture
def built(tmp_path: Path) -> dict[str, str]:
    paths = b.build(tmp_path, dashboard=_dashboard())
    return {p.name: p.read_text(encoding="utf-8") for p in paths}


def test_all_eight_pages_are_built_through_the_shell(built) -> None:
    assert set(built) == {"vietlott.html", *(file for _, file, _ in b.PRODUCTS.values())}
    for name, page in built.items():
        assert "app-main" in page, name
        assert 'href="vietlott.html"' in page, name


def test_no_page_spells_out_a_data_source(built) -> None:
    """Dữ liệu engine mang tên nguồn, đường dẫn và cảnh báo nhắc nguồn; không chữ nào ra trang."""
    for name, page in built.items():
        for marker in SOURCE_MARKERS:
            assert marker not in page, (name, marker)


def test_an_unpublished_jackpot_is_a_dash_not_the_previous_draw(built) -> None:
    mega = built["vietlott-mega-645.html"]
    table = mega.split("Bảng giải kỳ #1571", 1)[1].split("</table>", 1)[0]
    jackpot_row = table.split('<th scope="row">Jackpot</th>', 1)[1].split("</tr>", 1)[0]
    cells = [c.split(">", 1)[1].split("</td>", 1)[0] for c in jackpot_row.split("<td")[1:]]
    assert cells == ["6 số chính", "—", "—"], cells
    assert "123.456.789.000" not in table, "jackpot kỳ trước bị mượn cho kỳ mới"
    assert "10.000.000 ₫" in table and ">12<" in table
    # Kỳ trước vẫn hiện jackpot của chính nó trong lịch sử.
    assert "123.456.789.000 ₫" in mega


def test_each_product_keeps_its_own_shape(built) -> None:
    pro = built["vietlott-max-3d-pro.html"]
    for label in ("Đặc biệt", "Nhất", "Nhì", "Ba"):
        assert f"<small>{label}</small>" in pro
    assert "038 · 091" in pro
    keno = built["vietlott-keno.html"]
    assert "Lớn 11 · Nhỏ 9 · Chẵn 12 · Lẻ 8" in keno
    bingo = built["vietlott-bingo18.html"]
    assert "Tổng <b>12</b> · Lớn" in bingo


def test_forecasts_say_whether_they_were_registered_before_the_draw(built) -> None:
    mega = built["vietlott-mega-645.html"]
    assert "Đã đăng ký trước kỳ" in mega and "04 12 31 34 38 41" in mega
    assert "Đã chấm" in mega and "Chưa hơn ngẫu nhiên" in mega
    keno = built["vietlott-keno.html"]
    assert "Tham khảo" in keno and "Đã đăng ký trước kỳ" not in keno
    assert "Chưa có kết quả đã xác thực" in built["vietlott-power-655.html"]


def test_a_date_mismatch_is_shown_as_such_not_as_pending(built) -> None:
    mega = built["vietlott-mega-645.html"]
    row = mega.split('<th scope="row">#1569</th>', 1)[1].split("</tr>", 1)[0]
    assert "Lệch ngày" in row and "Chờ kết quả" not in row


def test_comparisons_show_the_special_number_on_both_sides(built) -> None:
    lotto = built["vietlott-lotto-535.html"]
    row = lotto.split('<th scope="row">#930</th>', 1)[1].split("</tr>", 1)[0]
    assert "01 02 03 04 05 + 07" in row, row
    assert "15 22 27 28 29 + 03" in row, row


def test_a_cache_path_from_the_repo_root_is_resolved_before_entering_the_engine(tmp_path, monkeypatch) -> None:
    """Workflow truyền ``vietlott/data/forecast`` tính từ gốc kho; engine chạy sau chdir."""
    (tmp_path / "states").mkdir()
    monkeypatch.chdir(tmp_path)
    seen = []

    class Stop(Exception):
        pass

    def capture(work, cache_states):
        seen.append(cache_states)
        raise Stop

    monkeypatch.setattr(b, "_states_dir", capture)
    with pytest.raises(Stop):
        b.load(Path("states"), products=())
    assert seen == [(tmp_path / "states").resolve()]


def test_the_overview_names_each_latest_draw(built) -> None:
    overview = built["vietlott.html"]
    assert "Kỳ #1571" in overview and "Kỳ #788" in overview
    assert "Dự báo kỳ #1572: đã đăng ký trước kỳ" in overview


def test_the_overview_says_no_product_deviates_when_none_does(built) -> None:
    overview = built["vietlott.html"]
    assert "chưa thấy sản phẩm nào lệch khỏi máy quay công bằng" in overview
    assert "Kỳ quay đã kiểm là ngẫu nhiên" not in overview


def test_the_overview_names_a_product_whose_draws_deviate(tmp_path: Path) -> None:
    """Max 3D / Pro lệch thật ở hàng đơn vị; trang tổng quan không được viết cứng "ngẫu nhiên"."""
    dashboard = _dashboard()
    dashboard["analysis"]["max3dpro"] = {"draws": 786, "last_id": 786, "last_date": "2026-10-01", "verdict": "ĐÃ",
                                         "evidence": {"found": True, "text": "Có bằng chứng."}, "max_rtp": 0.6293}
    overview = {p.name: p.read_text(encoding="utf-8") for p in b.build(tmp_path, dashboard=dashboard)}["vietlott.html"]
    hero = overview.split('class="vl-hero"', 1)[1].split("</section>", 1)[0]
    assert "độ lệch nhỏ có ý nghĩa thống kê ở Max 3D Pro;" in hero
    assert "kỳ vọng âm: RTP cao nhất theo mô hình là 0,63 (dưới 1)" in hero
    assert "chưa thấy sản phẩm nào" not in hero and "không làm tăng xác suất trúng" not in hero
    dashboard["analysis"]["max3d"] = {**dashboard["analysis"]["max3dpro"], "max_rtp": 0.5918}
    two = b.randomness_summary(dashboard["analysis"], {c: v[0] for c, v in b.PRODUCTS.items()})
    assert "ở Max 3D / Max 3D+ và Max 3D Pro;" in two and "0,63" in two


def test_max_rtp_reads_every_bet_of_every_component() -> None:
    components = [{"digit": {"bets": [{"rtp_model": 0.59}, {"rtp_model": 0.63}]}, "set": None},
                  {"digit": None, "set": {"keno": [{"rtp_model": 0.71}], "bets": []}}]
    assert b._max_rtp(components) == 0.71
    assert b._max_rtp([{"digit": None, "set": {"ticket": [1]}}]) is None


def test_the_real_engine_data_loads(tmp_path: Path) -> None:
    """Đọc ĐÚNG dữ liệu đã commit của engine: 7 sản phẩm đều có kỳ mới nhất."""
    cwd = os.getcwd()
    dashboard = b.load(products=("mega645",))
    assert os.getcwd() == cwd, "engine phải trả lại thư mục làm việc"
    by_code = {p["product"]: p for p in dashboard["products"]}
    assert set(by_code) == set(b.PRODUCTS)
    assert all(p["latest"] for p in by_code.values())
    assert by_code["keno"]["latest"]["numbers"] and len(by_code["keno"]["latest"]["numbers"]) == 20
    assert dashboard["analysis"]["mega645"]["draws"] > 1500
    built = b.build(tmp_path, dashboard=copy.deepcopy(dashboard))
    for path in built:
        page = path.read_text(encoding="utf-8")
        for marker in SOURCE_MARKERS[:-1]:
            assert marker not in page, (path.name, marker)
