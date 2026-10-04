"""Soi cầu vị trí: đếm đúng như trang đối chiếu, số bóng chỉ để hiển thị, phép
kiểm lịch sử phát hiện được tín hiệu khi có, và ô trang chủ không lệch kỳ.

Các con số "đối chiếu" dưới đây đọc từ trang soi cầu công khai cho kỳ
29-09-2026 (qua workflow ``inspect-reference-bridge.yml``), dữ liệu đến 28-09.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from bs4 import BeautifulSoup

import build_position_bridges as page
import position_bridges as pb

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATE = "2026-09-28"


@pytest.fixture(scope="module")
def draws():
    raw = pd.read_csv(ROOT / "data" / "xsmb.csv", dtype={"date": str})
    raw = raw[raw["date"] <= SOURCE_DATE]
    dates, digits, values = pb.load_draws(raw)
    assert dates[-1] == SOURCE_DATE
    return digits, values


def _scan(draws, **params):
    digits, values = draws
    bridges = pb.find_bridges(digits, values, **params)
    return bridges, pb.summarize(bridges, params["limit"])


def test_loto_bridges_match_the_reference_page(draws) -> None:
    bridges, summary = _scan(draws, nhay=1, db=False, lon=True, limit=5)
    assert (summary["count"], summary["longer"], summary["pairs"], summary["pairs_longer"]) == (43, 18, 27, 16)
    assert [b["numbers"][0] for b in bridges][:37] == (
        "03 05 06 08 15 15 17 19 20 22 27 29 37 38 38 38 39 43 44 44 44 44 47 52 52 53 55 55 59 "
        "65 69 70 72 72 73 78 83").split()
    assert [(r["pair"], r["bridges"]) for r in summary["repeats"][:16]] == [
        ("38,83", 4), ("44", 4), ("27,72", 3), ("15,51", 2), ("29,92", 2), ("37,73", 2), ("39,93", 2),
        ("25,52", 2), ("55", 2), ("48,84", 2), ("79,97", 2), ("03,30", 1), ("05,50", 1), ("06,60", 1),
        ("08,80", 1), ("17,71", 1)]


def test_two_hit_bridges_pool_both_directions_like_the_reference(draws) -> None:
    bridges, summary = _scan(draws, nhay=2, db=False, lon=True, limit=3)
    assert [b["vt"] for b in bridges] == [
        "38x84", "38x76", "38x89", "2x41", "76x81", "32x67", "6x84", "6x76", "45x76", "6x89", "6x22",
        "0x61", "22x81", "22x45"]
    assert " ".join(b["numbers"][0] for b in bridges) == "00 03 07 17 30 33 60 63 63 67 68 79 80 86"
    assert (summary["count"], summary["longer"], summary["pairs"], summary["pairs_longer"]) == (14, 1, 11, 1)
    assert [r["pair"] for r in summary["repeats"]] == [
        "03,30", "36,63", "68,86", "00", "07,70", "17,71", "33", "06,60", "67,76", "79,97", "08,80"]
    by_vt = {b["vt"]: b for b in bridges}
    assert by_vt["6x22"]["numbers"] == ["68", "86"] and by_vt["6x22"]["streak"] == 3
    assert by_vt["32x67"]["numbers"] == ["33"] and by_vt["32x67"]["shadow"] == "88"


def test_special_prize_bridges_match_the_reference(draws) -> None:
    bridges, summary = _scan(draws, nhay=1, db=True, lon=True, limit=1)
    assert (summary["count"], summary["longer"], summary["pairs"], summary["pairs_longer"]) == (132, 1, 29, 1)
    assert summary["repeats"][0] == {"pair": "47,74", "bridges": 18}
    longest = [b for b in bridges if b["streak"] > 1]
    assert [(b["vt"], b["numbers"], b["shadow"]) for b in longest] == [("18x36", ["44"], "99")]


def test_exact_length_keeps_only_that_length(draws) -> None:
    at_least, _ = _scan(draws, nhay=1, db=False, lon=True, limit=5)
    exact, summary = _scan(draws, nhay=1, db=False, lon=True, limit=6, exact=True)
    assert [b["vt"] for b in exact] == [b["vt"] for b in at_least if b["streak"] == 6]
    assert exact and summary["count"] < sum(b["streak"] >= 6 for b in at_least)


def test_without_lon_the_order_of_positions_matters(draws) -> None:
    bridges, summary = _scan(draws, nhay=1, db=False, lon=False, limit=5)
    assert [b["vt"] for b in bridges] == ["95x74", "63x31", "32x22", "33x70", "44x104", "59x43", "78x6"]
    assert [b["numbers"] for b in bridges] == [["22"], ["29"], ["38"], ["43"], ["65"], ["95"], ["96"]]
    assert (summary["count"], summary["longer"], summary["pairs"], summary["pairs_longer"]) == (7, 4, 7, 4)


def _one_draw(values: dict[int, int]) -> np.ndarray:
    """27 giá trị: giải ĐB = 99999 và mọi giải khác = 0, trừ các chỉ số được đặt."""
    row = np.zeros(27, dtype=np.int64)
    row[0] = 99999
    for index, value in values.items():
        row[index] = value
    return row


def _digits(values: np.ndarray) -> np.ndarray:
    frame = pd.DataFrame(values, columns=pb.COLUMNS)
    frame.insert(0, "date", [f"2026-01-{i + 1:02d}" for i in range(len(values))])
    return pb.load_draws(frame)[1]


def test_the_shadow_number_is_shown_but_never_counted_as_a_hit() -> None:
    """Kép 44 kèm bóng 99 để HIỂN THỊ. Tính 99 là trúng thì ngày 28-09 ra 64 cầu
    LOTO thay vì 43 của trang đối chiếu."""
    assert pb.shadow(["44"]) == "99" and pb.shadow(["00"]) == "55" and pb.shadow(["27"]) is None
    assert pb.shadow(["45", "54"]) is None
    # Kỳ 1: G1 = 44000 nên vị trí 5x6 báo 44. Kỳ 2 chỉ có 99 (giải Bảy).
    values = np.stack([_one_draw({1: 44000}), _one_draw({23: 99})])
    hits, pa, pb_ = pb.hit_matrix(_digits(values), values, nhay=1, db=False, lon=True)
    p = int(np.flatnonzero((pa == 5) & (pb_ == 6))[0])
    assert not hits[0, p]


def test_lon_pools_both_directions_toward_the_hit_count() -> None:
    """45 về một lần và 54 về một lần là 2 nháy khi lộn; không lộn thì 1 nháy."""
    values = np.stack([_one_draw({1: 45000}), _one_draw({23: 45, 24: 54})])
    digits = _digits(values)
    for lon, expected in ((True, True), (False, False)):
        hits, pa, pb_ = pb.hit_matrix(digits, values, nhay=2, db=False, lon=lon)
        p = int(np.flatnonzero((pa == 5) & (pb_ == 6))[0])
        assert bool(hits[0, p]) is expected, lon


def test_the_special_prize_mode_reads_only_the_last_two_digits_of_the_special() -> None:
    values = np.stack([_one_draw({1: 45000}), _one_draw({0: 12354, 23: 45})])
    hits, pa, pb_ = pb.hit_matrix(_digits(values), values, nhay=1, db=True, lon=True)
    assert bool(hits[0, int(np.flatnonzero((pa == 5) & (pb_ == 6))[0])])
    values[1, 0] = 12345
    values[1, 23] = 54
    hits, pa, pb_ = pb.hit_matrix(_digits(values), values, nhay=1, db=True, lon=True)
    assert bool(hits[0, int(np.flatnonzero((pa == 5) & (pb_ == 6))[0])])
    values[1, 0] = 12346
    hits, _, _ = pb.hit_matrix(_digits(values), values, nhay=1, db=True, lon=True)
    assert not bool(hits[0, int(np.flatnonzero((pa == 5) & (pb_ == 6))[0])]), "giải Bảy 54 không phải ĐB"


def test_best_keeps_one_bridge_per_pair_ranked_by_streak_then_agreement() -> None:
    bridges = [
        {"vt": "1x2", "a": 1, "b": 2, "streak": 5, "numbers": ["12", "21"]},
        {"vt": "3x4", "a": 3, "b": 4, "streak": 7, "numbers": ["34", "43"]},
        {"vt": "5x6", "a": 5, "b": 6, "streak": 5, "numbers": ["56", "65"]},
        {"vt": "7x8", "a": 7, "b": 8, "streak": 5, "numbers": ["65", "56"]},
        {"vt": "0x9", "a": 0, "b": 9, "streak": 6, "numbers": ["34", "43"]},
    ]
    chosen = pb.best(bridges)
    assert [b["vt"] for b in chosen] == ["3x4", "5x6", "1x2"]
    assert [b["same_pair"] for b in chosen] == [2, 2, 1]


def _random_draws(days: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    values = np.column_stack([rng.integers(0, 10 ** w, size=days) for w in pb.WIDTHS])
    return _digits(values), values


def test_the_backtest_finds_a_signal_when_one_is_planted() -> None:
    """Phép kiểm phải đỏ được: cho mỗi kỳ có 50% chép y nguyên kỳ trước, cầu vừa
    trúng dễ trúng tiếp hơn thật, nên tỉ lệ ở k ≥ 3 phải vượt kỳ vọng rõ rệt."""
    digits, values = _random_draws(300, seed=3)
    copy = np.random.default_rng(4).random(300) < 0.5
    for t in range(1, 300):
        if copy[t]:
            digits[t], values[t] = digits[t - 1], values[t - 1]
    rows = pb.streak_backtest(pb.history(digits, values, nhay=1, db=False, lon=True))["rows"]
    assert rows[3]["rate"] > rows[3]["expected"] + 0.05
    assert rows[3]["z"] > 4


def test_random_draws_show_no_streak_effect_and_rows_partition_every_event() -> None:
    digits, values = _random_draws(400, seed=11)
    past = pb.history(digits, values, nhay=1, db=False, lon=True)
    report = pb.streak_backtest(past)
    prev, nxt, kep, _ = past
    assert sum(r["n"] for r in report["rows"]) == prev.size
    assert sum(r["hits"] for r in report["rows"]) == int(nxt.sum())
    assert report["rate_kep"] < report["rate_pair"], "số kép là một số nên dễ trượt hơn"
    # Kỳ vọng của từng hàng theo đúng tỉ lệ số kép trong hàng, không theo nền chung.
    mask = prev == 1
    mix = np.where(kep[mask], report["rate_kep"], report["rate_pair"]).mean()
    assert report["rows"][1]["expected"] == pytest.approx(mix, rel=1e-9)
    for row in report["rows"]:
        if row["n"] >= 5_000:
            assert abs(row["rate"] - row["expected"]) < 0.02
            assert abs(row["z"]) < 4


def test_agreement_counts_each_number_pair_once_per_draw() -> None:
    """m cầu cùng báo một cặp là MỘT lần trúng/trượt — đếm theo cầu sẽ thổi phồng mẫu."""
    digits, values = _random_draws(60, seed=5)
    past = pb.history(digits, values, nhay=1, db=False, lon=True)
    prev, _, _, key = past
    expected = sum(len(np.unique(key[s][prev[s] >= 2])) for s in range(prev.shape[0]))
    rows = pb.consensus_backtest(past, 2)["rows"]
    assert sum(r["n"] for r in rows) == expected
    assert expected < int((prev >= 2).sum())


def _report() -> dict:
    return {
        "source_date": SOURCE_DATE, "target_date": "2026-09-29", "window": 60,
        "draws": [{"date": SOURCE_DATE, "values": ["77115"] * 27}],
        "modes": {
            key: {**cfg, "summary": {"count": 3, "longer": 1, "pairs": 2, "pairs_longer": 1, "repeats": []},
                  "best": [{"vt": "60x83", "a": 60, "b": 83, "streak": 6, "numbers": ["44"], "shadow": "99",
                            "same_pair": 4}],
                  "streaks": {"base_rate": 0.4, "rate_kep": 0.24, "rate_pair": 0.42, "draws": 4217,
                              "rows": [{"k": k, "plus": k == 10, "n": 1000, "hits": 400, "rate": 0.4,
                                        "expected": 0.4, "z": 0.1, "days": 10} for k in range(11)]},
                  "consensus": {"limit": cfg["limit"],
                                "rows": [{"from": 1, "to": 1, "n": 300, "hits": 120, "rate": 0.4,
                                          "expected": 0.4, "z": -0.2, "days": 10}]}}
            for key, cfg in pb.MODES.items()
        },
    }


def test_the_home_panel_links_each_bridge_with_the_reference_parameters() -> None:
    soup = BeautifulSoup(page.best_panel(_report(), SOURCE_DATE), "html.parser")
    links = [a["href"] for a in soup.select(".app-bridge-list a")]
    assert links == [
        "soi-cau-vi-tri.html?vt=60x83&limit=5&exactlimit=0&lon=1&nhay=1&db=0",
        "soi-cau-vi-tri.html?vt=60x83&limit=3&exactlimit=0&lon=1&nhay=2&db=0",
        "soi-cau-vi-tri.html?vt=60x83&limit=1&exactlimit=0&lon=1&nhay=1&db=1",
    ]
    chip = soup.select_one(".app-bridge-list a")
    assert chip.select_one("b").get_text() == "44,99"
    assert chip.select_one(".app-bridge-shadow").get_text() == ",99", "số bóng phải phân biệt được với số cầu"
    assert chip.select_one(".app-bridge-streak").get_text() == "6"
    # Mỗi số một phần tử: "44,99" viết liền bị đọc thành số thập phân 44,99.
    assert [s.get_text() for s in chip.select(".app-bridge-num")] == ["44", "99"]


def test_the_home_panel_refuses_a_report_from_another_draw() -> None:
    """Ô cầu của hôm qua đặt cạnh kết quả hôm nay là sai lặng lẽ."""
    soup = BeautifulSoup(page.best_panel(_report(), "2026-09-29"), "html.parser")
    assert not soup.select(".app-bridge-list a")
    assert "đang được tính lại" in soup.get_text()
    assert not BeautifulSoup(page.best_panel(None, SOURCE_DATE), "html.parser").select("a[href*='vt=']")


def test_the_verdict_is_read_from_the_numbers() -> None:
    report = _report()
    assert "Không hàng nào" in page.backtest_card(report)
    report["modes"]["lo"]["streaks"]["rows"][7]["z"] = 3.4
    card = page.backtest_card(report)
    assert "1 trên 12 hàng đủ mẫu trúng nhiều hơn kỳ vọng" in card
    report["modes"]["lo"]["streaks"]["rows"][7]["n"] = 150
    assert "Không hàng nào trong 11 hàng" in page.backtest_card(report), "mẫu nhỏ không được tính"


def test_the_page_embeds_the_window_and_hides_the_path_until_asked(tmp_path: Path) -> None:
    html = page.render(_report())
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one("#app-bridge-path").find_parent("section").has_attr("hidden")
    assert soup.select_one("#app-bridge-form")["action"] == page.PAGE
    assert soup.select_one("#kiem-chung")
    assert "vla" not in html.lower()


def test_the_result_board_carries_the_extra_column_only_when_given() -> None:
    from shared_results import decode_row, render_result_board

    row = "2026-09-26" + "00001" + "00000" + "0000200003" + "00004" * 6 + "0005" * 4 + "0006" * 6 + "007" * 3 + "08" * 4
    draw = decode_row(row)
    plain = BeautifulSoup(render_result_board(draw), "html.parser")
    assert plain.select_one(".tr-results")["data-extra"] == "off"
    assert plain.select_one(".tr-day-extra") is None
    board = BeautifulSoup(render_result_board(draw, extra='<aside class="x">cầu</aside>'), "html.parser")
    assert board.select_one(".tr-results")["data-extra"] == "on"
    assert board.select_one(".tr-day-grid > .tr-day-extra > aside.x")
