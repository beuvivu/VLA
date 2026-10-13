"""Trang «Lô VIP nhiều nháy»: mọi con số và kết luận phải ĐI THEO phép đo.

Trang không được có câu "không hơn chọn bừa" viết sẵn: cùng một trình dựng, đưa số đo của một
lịch sử có cài tín hiệu thì phải nói "hơn", đưa số đo của lịch sử công bằng thì phải nói "không
hơn". Các phép kiểm dưới đây dựng cả hai phía bằng chính ``multi_hit_report.vip_section`` trên
lịch sử giả định, rồi ghim luật làm mới bản đệm của giao thức lượt hai.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest
from bs4 import BeautifulSoup

import build_multi_hit_page as page
import multi_hit_report as report
import multi_hit_vip as m

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "multi_hit"
PLANTED = (7, 38, 68)


def _vip_of(frame) -> dict:
    draws, labels = m.draws_from_frame(frame)
    return report.vip_section(draws, labels)


@pytest.fixture(scope="module")
def fair_vip() -> dict:
    return _vip_of(m.mock_history(100, seed=2026))


@pytest.fixture(scope="module")
def planted_vip() -> dict:
    return _vip_of(m.mock_history(120, seed=2026, planted=PLANTED))


@pytest.fixture(scope="module")
def bench() -> dict:
    """Số đo lượt hai đã xuất bản; dùng làm phần nền cho các kịch bản dựng trang."""
    return json.loads((DATA / "benchmark.json").read_text(encoding="utf-8"))


def _soup(vip: dict, bench: dict | None) -> BeautifulSoup:
    return BeautifulSoup(page.render(vip, bench), "html.parser")


def _verdict(soup: BeautifulSoup) -> str:
    return soup.select_one(".app-vip-verdict")["data-verdict"]


# --------------------------------------------------------------------------- số đo


def test_wilson_interval_matches_the_textbook_value() -> None:
    lo, hi = report.wilson(5, 10)
    assert (lo, hi) == pytest.approx((0.2366, 0.7634), abs=1e-4)
    # Không trúng lần nào: cận dưới đúng 0, cận trên vẫn dương (khoảng Wald thì sập về 0).
    lo, hi = report.wilson(0, 50)
    assert lo == pytest.approx(0.0, abs=1e-12) and hi == pytest.approx(0.0713, abs=1e-4)
    assert all(math.isnan(x) for x in report.wilson(0, 0))


def test_the_recent_rows_count_the_real_nhay_of_each_pick(fair_vip) -> None:
    draws, labels = m.draws_from_frame(m.mock_history(100, seed=2026))
    counts = m.counts_matrix(draws)
    assert len(fair_vip["recent"]) == report.RECENT_DRAWS
    assert fair_vip["recent"][0]["date"] == labels[-1]           # mới nhất trước
    for row in fair_vip["recent"]:
        t = labels.index(row["date"])
        assert len(row["picks"]) == fair_vip["config"]["top_k"]
        for pick in row["picks"]:
            assert pick["hits"] == counts[t, int(pick["number"])]
        assert row["multi"] == sum(p["hits"] >= 2 for p in row["picks"])


def test_the_backtest_block_is_the_model_s_own_numbers(planted_vip) -> None:
    bt = planted_vip["backtest"]
    assert bt["rate"] == pytest.approx(bt["hits"] / bt["picks"])
    assert bt["ci95"][0] < bt["rate"] < bt["ci95"][1]
    assert bt["lift"] == pytest.approx(bt["hits"] / bt["expected"])
    assert planted_vip["confidence"] == m.model_confidence(bt["p_value"], bt["lift"])


# --------------------------------------------------------------------------- bản đệm lượt hai


def _history(n: int = 100):
    draws, labels = m.draws_from_frame(m.mock_history(n, seed=9))
    return draws, list(labels)


def _cached(draws, labels, measured: int, **extra) -> dict:
    return {"version": report.MEASURE_VERSION, "draws": measured,
            "history_sha256": report.history_fingerprint(draws, labels, measured), **extra}


def test_a_missing_or_older_benchmark_is_remeasured() -> None:
    draws, labels = _history()
    assert report.benchmark_is_stale(None, draws, labels)
    old = _cached(draws, labels, 70, version=report.MEASURE_VERSION - 1)
    assert report.benchmark_is_stale(old, draws[:70], labels[:70])


@pytest.mark.parametrize(("added", "stale"), [
    (0, False),
    (report.BENCHMARK_REFRESH_DRAWS - 1, False),
    (report.BENCHMARK_REFRESH_DRAWS, True),
])
def test_the_benchmark_is_remeasured_after_enough_new_draws(added, stale) -> None:
    draws, labels = _history()
    cached = _cached(draws, labels, 60)
    now = 60 + added
    assert report.benchmark_is_stale(cached, draws[:now], labels[:now]) is stale


def test_correcting_an_old_draw_invalidates_the_benchmark() -> None:
    """Sửa một ô của kỳ cũ: số kỳ và ngày cuối không đổi, nhưng mọi số đo có thể đã đổi."""
    draws, labels = _history()
    cached = _cached(draws, labels, 80)
    fixed = draws.copy()
    fixed[10, 3] = (fixed[10, 3] + 1) % 100
    assert report.benchmark_is_stale(cached, fixed[:80], labels[:80])
    relabelled = labels[:80].copy()
    relabelled[5] = "2025-12-31"
    assert report.benchmark_is_stale(cached, draws[:80], relabelled)


def test_a_cut_history_invalidates_the_benchmark() -> None:
    draws, labels = _history()
    assert report.benchmark_is_stale(_cached(draws, labels, 80), draws[:79], labels[:79])


def test_new_draws_after_the_measured_ones_do_not_invalidate_it() -> None:
    draws, labels = _history()
    cached = _cached(draws, labels, 80)
    later = draws.copy()
    later[85, 0] = (later[85, 0] + 1) % 100        # sau đoạn đã đo
    assert not report.benchmark_is_stale(cached, later[:90], labels[:90])


def test_run_writes_the_filter_daily_and_the_benchmark_only_when_stale(tmp_path, monkeypatch) -> None:
    m.mock_history(80, seed=5).to_csv(tmp_path / "xsmb-2-digits.csv", index=False)
    calls = []

    def fake_benchmark(draws, labels):
        calls.append(len(draws))
        return {"version": report.MEASURE_VERSION, "draws": len(draws),
                "history_sha256": report.history_fingerprint(draws, labels)}

    monkeypatch.setattr(report, "benchmark_section", fake_benchmark)
    assert set(report.run(tmp_path)) == {"vip", "benchmark"}
    assert set(report.run(tmp_path)) == {"vip"}
    assert set(report.run(tmp_path, force_benchmark=True)) == {"vip", "benchmark"}
    assert calls == [80, 80]
    vip = json.loads((tmp_path / report.OUT_DIR / report.VIP_FILE).read_text(encoding="utf-8"))
    assert vip["draws"] == 80


# --------------------------------------------------------------------------- "ít nhất một con về"


def _scores_for(picks: list[int], n_rows: int) -> np.ndarray:
    """Điểm chọn đúng con ``picks[t]`` ở hàng t (mọi con khác thấp hơn rõ rệt)."""
    scores = np.zeros((n_rows, 100))
    for t, number in enumerate(picks):
        scores[t, number] = 1.0
    return scores


def test_the_any_hit_error_is_paired_on_the_same_draws() -> None:
    counts = np.zeros((6, 100))
    counts[:, 7] = [2, 2, 0, 2, 0, 2]          # con 7 về ≥ 2 nháy ở kỳ 0, 1, 3, 5
    counts[:, 9] = [2, 0, 0, 2, 2, 0]          # con 9 về ≥ 2 nháy ở kỳ 0, 3, 4
    rows = range(6)
    a, b = _scores_for([7] * 6, 6), _scores_for([9] * 6, 6)
    se = report.paired_any_hit_se(a, b, counts, rows, ks=(1,))["multi"]["1"]
    diff = np.array([0, 1, 0, 0, -1, 1], dtype=float)
    assert se == pytest.approx(diff.std(ddof=1) / math.sqrt(6))
    # Cùng một bộ chọn: hiệu từng kỳ bằng 0, nên sai số của hiệu bằng 0 — công thức hai mẫu độc
    # lập thì vẫn ra số dương.
    assert report.paired_any_hit_se(a, a, counts, rows, ks=(1,))["multi"]["1"] == 0.0


def test_the_any_hit_error_uses_the_same_top_k_as_the_rates() -> None:
    import multi_hit_benchmark as bm

    draws, _ = _history(120)
    counts = m.counts_matrix(draws)
    rng = np.random.default_rng(1)
    a, b = rng.random((121, 100)), rng.random((121, 100))
    rows = range(20, 120)
    rate_a = bm.any_hit_rates(a, counts, rows, ks=(5,))["single"][5]
    picks_a = bm.top_k(a[list(rows)], 5)
    hit_a = (np.take_along_axis(counts[list(rows)], picks_a, axis=1) >= 1).any(axis=1)
    assert hit_a.mean() == pytest.approx(rate_a)
    se = report.paired_any_hit_se(a, b, counts, rows, ks=(5,))["single"]["5"]
    assert 0 < se < 1


def test_the_page_prints_the_measured_paired_error(fair_vip, bench) -> None:
    changed = copy.deepcopy(bench)
    for k in changed["any_hit"]["paired_se"]["multi"]:
        changed["any_hit"]["paired_se"]["multi"][k] = 0.01234
    text = _soup(fair_vip, changed).select_one("#app-vip-any").get_text(" ", strip=True)
    assert "là 1,2 điểm %" in text


# --------------------------------------------------------------------------- kết luận


def test_a_fair_history_reads_not_better_than_random(fair_vip, bench) -> None:
    assert fair_vip["confidence"] == "Low"
    soup = _soup(fair_vip, bench)
    assert _verdict(soup) == "khong-hon"
    assert soup.select_one(".app-vip-verdict").get_text(strip=True).startswith("Không hơn chọn bừa")


def test_a_planted_history_reads_better_than_random(planted_vip, bench) -> None:
    assert planted_vip["confidence"] == "High"
    soup = _soup(planted_vip, bench)
    assert _verdict(soup) == "hon"
    assert "Có bằng chứng hơn chọn bừa" in soup.select_one(".app-vip-verdict").get_text()


def test_a_second_round_that_passes_turns_the_verdict(fair_vip, bench) -> None:
    passed = copy.deepcopy(bench)
    passed["candidate_passes"] = True
    assert page.verdict(fair_vip, passed)["state"] == "hon"
    assert "ĐẠT" in page.verdict_text(fair_vip, passed)[1]


def test_a_blind_protocol_cannot_conclude_not_better(fair_vip, bench) -> None:
    blind = copy.deepcopy(bench)
    blind["power_check"]["candidate_passes"] = False
    assert page.verdict(fair_vip, blind)["state"] == "chua-ket-luan"
    assert "chưa đủ căn cứ" in page.verdict_text(fair_vip, blind)[1]


def test_without_a_benchmark_the_page_still_builds_from_the_filter_alone(fair_vip) -> None:
    soup = _soup(fair_vip, None)
    assert _verdict(soup) == "khong-hon"
    assert "Chưa có số đo của lượt thử thứ hai" in soup.get_text()


def test_the_verdict_prints_the_measured_numbers(planted_vip, bench) -> None:
    text = page.verdict_text(planted_vip, bench)[1]
    bt = planted_vip["backtest"]
    assert f"{bt['hits']}/{bt['picks']}" in text.replace(".", "")
    assert page._pct(bt["rate"]) in text
    assert page._pct(bt["random_rate"]) in text
    assert page._pct(bench["candidate_test"]["rate"]) in text
    assert page.strategy_label(bench["candidate"]) in text


def test_the_confidence_rule_on_the_page_is_the_model_s_rule(fair_vip) -> None:
    text = _soup(fair_vip, None).get_text()
    for level, p in m.CONFIDENCE_P.items():
        assert f"p < {page._num(p, 2)}" in text, level


# --------------------------------------------------------------------------- bảng


def test_the_picks_table_lists_the_measured_top_k(planted_vip) -> None:
    rows = _soup(planted_vip, None).select("#app-vip-picks tbody tr")
    numbers = [r.select("td")[1].get_text(strip=True) for r in rows]
    assert numbers == [p["number"] for p in planted_vip["picks"]]
    assert {int(n) for n in PLANTED} <= {int(n) for n in numbers}


def test_every_strategy_of_the_benchmark_has_a_reader_facing_label(bench) -> None:
    names = [s["name"] for s in bench["strategies"]]
    assert len(names) >= 20                    # không quét tập rỗng
    missing = [n for n in names if n not in page.STRATEGY_LABELS]
    assert not missing, missing


def test_the_candidate_row_is_marked_and_only_that_row(bench, fair_vip) -> None:
    rows = _soup(fair_vip, bench).select("#app-vip-benchmark tbody tr")
    marked = [r.select_one("td").get_text(" ", strip=True) for r in rows if "ứng viên" in r.get_text()]
    assert marked == [f"{page.strategy_label(bench['candidate'])} ứng viên"]


def test_reasons_use_the_vietnamese_decimal_comma() -> None:
    raw = "Dị thường Poisson +3.44 (2 kỳ ≥2 nháy trong cửa sổ, z = +1.19, lift ×1.17)"
    assert page._vi_decimals(raw) == "Dị thường Poisson +3,44 (2 kỳ ≥2 nháy trong cửa sổ, z = +1,19, lift ×1,17)"
    assert page._vi_decimals("số 07 · kỳ 30.") == "số 07 · kỳ 30."


# --------------------------------------------------------------------------- trang đã xuất bản


def test_the_published_page_agrees_with_the_published_measurement() -> None:
    vip = json.loads((DATA / "vip.json").read_text(encoding="utf-8"))
    bench = json.loads((DATA / "benchmark.json").read_text(encoding="utf-8"))
    soup = BeautifulSoup((ROOT / "docs" / page.PAGE).read_text(encoding="utf-8"), "html.parser")
    assert _verdict(soup) == page.verdict(vip, bench)["state"]
    picks = [r.select("td")[1].get_text(strip=True) for r in soup.select("#app-vip-picks tbody tr")]
    assert picks == [p["number"] for p in vip["picks"]]
