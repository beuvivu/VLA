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
import multi_hit_pairs as pairs
import multi_hit_report as report
import multi_hit_vip as m

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "multi_hit"
PLANTED = (7, 38, 68)


#: Lịch sử giả định bắt đầu 01-01-2026: chốt bộ lọc TRƯỚC đó để mọi kỳ là tiến cứu.
BEFORE_MOCK = "2025-12-31"


def _vip_of(frame, after: str = BEFORE_MOCK) -> dict:
    draws, labels = m.draws_from_frame(frame)
    return report.vip_section(draws, labels, prospective_after=after)


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


def test_the_interval_is_wilson_on_the_kish_effective_sample() -> None:
    """deff = phương sai số trúng từng kỳ / (k·p·(1 − p)); Wilson trên số lượt chọn / deff."""
    k, n = 5, 400
    hits = np.zeros(n)
    hits[:60] = 1
    (lo, hi), deff = report.draw_level_interval(hits, k)
    p = 60 / (n * k)
    expected_deff = hits.var(ddof=1) / (k * p * (1 - p))
    assert deff == pytest.approx(expected_deff)
    n_eff = n * k / deff
    assert (lo, hi) == pytest.approx(report.wilson(p * n_eff, n_eff))


def test_picks_that_hit_together_widen_the_interval() -> None:
    """Năm con cùng kỳ trúng hay trượt cùng nhau: thông tin chỉ bằng một phép thử mỗi kỳ."""
    k, n = 5, 400
    clustered = np.zeros(n)
    clustered[:12] = k                       # 60 lượt trúng dồn trong 12 kỳ
    spread = np.zeros(n)
    spread[:60] = 1                          # cùng 60 lượt trải trên 60 kỳ
    (c_lo, c_hi), c_deff = report.draw_level_interval(clustered, k)
    (s_lo, s_hi), s_deff = report.draw_level_interval(spread, k)
    assert c_deff > 4 > s_deff
    assert c_hi - c_lo > 1.8 * (s_hi - s_lo)
    naive = report.wilson(60, n * k)
    assert c_hi - c_lo > naive[1] - naive[0]


def test_the_published_interval_is_the_draw_level_one(planted_vip) -> None:
    draws, labels = m.draws_from_frame(m.mock_history(120, seed=2026, planted=PLANTED))
    bt = m.VIPMultiHitModel(draws, labels, m.VIPConfig()).predict_next().backtest
    (lo, hi), deff = report.draw_level_interval(bt.per_draw["trung"], bt.top_k)
    assert planted_vip["backtest"]["ci95"] == pytest.approx([lo, hi])
    assert planted_vip["backtest"]["design_effect"] == pytest.approx(deff)


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
        # Mốc chọn bừa của TỪNG kỳ: k con trong 100, m con về ≥ 2 nháy → k·m/100.
        m_t = int((counts[t] >= 2).sum())
        assert row["numbers_multi"] == m_t
        assert row["expected"] == pytest.approx(fair_vip["config"]["top_k"] * m_t / 100)


def test_the_backtest_block_is_the_model_s_own_numbers(planted_vip) -> None:
    bt = planted_vip["backtest"]
    assert bt["rate"] == pytest.approx(bt["hits"] / bt["picks"])
    assert bt["ci95"][0] < bt["rate"] < bt["ci95"][1]
    assert bt["lift"] == pytest.approx(bt["hits"] / bt["expected"])
    pro = planted_vip["prospective"]
    assert pro["lift"] == pytest.approx(pro["hits"] / pro["expected"])
    assert planted_vip["confidence"] == m.model_confidence(pro["p_anytime"], pro["lift"])
    for pick in planted_vip["picks"]:
        assert pick["confidence"] == m.number_confidence(planted_vip["confidence"], pick["probability"],
                                                         planted_vip["base_theory"])


# --------------------------------------------------------------------------- p luôn hợp lệ


def test_anytime_p_on_a_hand_computed_path() -> None:
    # Cược λ = 1: vốn 1 → 1,5 (trúng 1, kỳ vọng 0,5) → 0,75 (trượt). Đỉnh 1,5 → p = 1/1,5.
    p, e_max = report.anytime_p([1, 0], [0.5, 0.5], grid=(1.0,))
    assert e_max == pytest.approx(1.5) and p == pytest.approx(1 / 1.5)
    # Không bao giờ hơn kỳ vọng: vốn không lên khỏi 1, p = 1.
    assert report.anytime_p([0, 0, 0], [0.2, 0.3, 0.1]) == (1.0, 1.0)
    with pytest.raises(ValueError):
        report.anytime_p([0], [0.5], grid=(3.0,))         # cược làm vốn âm


def _null_paths(n_hist: int, n_draws: int, seed: int = 1):
    """Lịch sử KHÔNG có kỹ năng: mỗi kỳ m con về ≥ 2 nháy, top-5 trúng theo siêu bội."""
    rng = np.random.default_rng(seed)
    for _ in range(n_hist):
        m_t = rng.binomial(100, 0.0297, size=n_draws)
        yield rng.hypergeometric(m_t, 100 - m_t, 5), 5 * m_t / 100, m_t


def test_looking_every_day_needs_the_anytime_p() -> None:
    """Xem lại sau mỗi kỳ với cùng ngưỡng 0,05: p một lần xem vượt ngưỡng ở quá nhiều lịch sử
    không kỹ năng; p luôn hợp lệ giữ đúng mức đã hứa."""
    from scipy.stats import norm

    naive = anytime = 0
    n_hist = 400
    for hits, mu, m_t in _null_paths(n_hist, 1500):
        var = 5 * (m_t / 100) * (1 - m_t / 100) * 95 / 99
        z = np.cumsum(hits - mu)[200:] / np.sqrt(np.cumsum(var)[200:])
        naive += bool((norm.sf(z) < 0.05).any())
        anytime += report.anytime_p(hits, mu)[0] < 0.05
    assert naive / n_hist > 0.15              # vấn đề có thật trong chính thiết lập này
    assert anytime / n_hist <= 0.05


def test_every_confidence_on_the_page_follows_the_anytime_p(monkeypatch) -> None:
    """Mô hình tự báo High trên lịch sử cài tín hiệu; nếu p luôn hợp lệ không đạt thì không con nào được tin."""
    monkeypatch.setattr(report, "anytime_p", lambda hits, expected: (1.0, 1.0))
    vip = _vip_of(m.mock_history(120, seed=2026, planted=PLANTED))
    assert vip["confidence"] == "Low"
    assert {p["confidence"] for p in vip["picks"]} == {"Low"}


def test_anytime_p_still_finds_a_real_edge(planted_vip, fair_vip) -> None:
    assert planted_vip["prospective"]["p_anytime"] < 1e-6 and planted_vip["confidence"] == "High"
    assert fair_vip["prospective"]["p_anytime"] > 0.05 and fair_vip["confidence"] == "Low"


def test_a_retrospective_edge_alone_cannot_raise_the_confidence() -> None:
    """Bộ lọc thiết kế sau khi xem lịch sử: lợi thế trên chính lịch sử ấy không được tính là bằng chứng."""
    vip = _vip_of(m.mock_history(120, seed=2026, planted=PLANTED), after="2026-12-31")
    assert vip["backtest"]["p_value"] < 1e-6                     # hồi cứu thì "rất có ý nghĩa"
    assert vip["prospective"]["draws"] == 0 and vip["prospective"]["lift"] is None
    json.dumps(vip, allow_nan=False)                             # tệp đo là JSON hợp chuẩn
    assert vip["confidence"] == "Low"
    assert {p["confidence"] for p in vip["picks"]} == {"Low"}
    assert page.verdict(vip, None)["state"] != "hon"


def test_only_draws_after_the_freeze_enter_the_e_process() -> None:
    frame = m.mock_history(120, seed=2026, planted=PLANTED)
    draws, labels = m.draws_from_frame(frame)
    vip = _vip_of(frame, after=labels[89])
    model = m.VIPMultiHitModel(draws, labels, m.VIPConfig())
    per_draw = model.predict_next().backtest.per_draw
    later = per_draw[per_draw["ky"] > labels[89]]
    assert vip["prospective"]["draws"] == len(later) == 30
    assert vip["prospective"]["hits"] == int(later["trung"].sum())


# --------------------------------------------------------------------------- bản đệm lượt hai


def _history(n: int = 100):
    draws, labels = m.draws_from_frame(m.mock_history(n, seed=9))
    return draws, list(labels)


def _cached(draws, labels, measured: int, **extra) -> dict:
    return {"version": report.BENCHMARK_VERSION, "draws": measured,
            "history_sha256": report.history_fingerprint(draws, labels, measured), **extra}


@pytest.fixture
def register_at(monkeypatch):
    """Dời ngày đăng ký của lượt hai về kỳ thứ n của một lịch sử giả định (mặc định: 12-10-2026)."""
    def _register(labels, n: int) -> None:
        monkeypatch.setattr(report, "SECOND_ROUND_UNTIL", labels[n - 1])
    return _register


def test_a_missing_or_older_benchmark_is_remeasured(register_at) -> None:
    draws, labels = _history()
    register_at(labels, 70)
    assert report.benchmark_is_stale(None, draws, labels)
    old = _cached(draws, labels, 70, version=report.BENCHMARK_VERSION - 1)
    assert report.benchmark_is_stale(old, draws, labels)
    assert not report.benchmark_is_stale(_cached(draws, labels, 70), draws, labels)


def test_a_new_daily_measurement_format_does_not_reopen_the_one_time_test(register_at, monkeypatch) -> None:
    """vip.json đổi khuôn (thêm cặp xiên 2) không được buộc phép kiểm một lần đã đóng băng chạy lại."""
    draws, labels = _history()
    register_at(labels, 70)
    cached = _cached(draws, labels, 70)
    monkeypatch.setattr(report, "MEASURE_VERSION", report.MEASURE_VERSION + 1)
    assert not report.benchmark_is_stale(cached, draws, labels)
    monkeypatch.setattr(report, "BENCHMARK_VERSION", report.BENCHMARK_VERSION + 1)
    assert report.benchmark_is_stale(cached, draws, labels)


@pytest.mark.parametrize("added", [0, 30, 240])
def test_new_draws_never_reopen_the_one_time_test(register_at, added) -> None:
    """Lượt hai là phép kiểm MỘT lần: kỳ mới sau ngày đăng ký không bao giờ làm nó cần đo lại."""
    draws, labels = _history(300)
    register_at(labels, 60)
    cached = _cached(draws, labels, 60)
    now = 60 + added
    assert not report.benchmark_is_stale(cached, draws[:now], labels[:now])


def test_correcting_an_old_draw_invalidates_the_benchmark(register_at) -> None:
    """Sửa một ô của kỳ cũ: số kỳ và ngày cuối không đổi, nhưng mọi số đo có thể đã đổi."""
    draws, labels = _history()
    register_at(labels, 80)
    cached = _cached(draws, labels, 80)
    fixed = draws.copy()
    fixed[10, 3] = (fixed[10, 3] + 1) % 100
    assert report.benchmark_is_stale(cached, fixed, labels)
    relabelled = labels.copy()
    relabelled[5] = "2025-12-31"
    assert report.benchmark_is_stale(cached, draws, relabelled)


def test_a_cut_history_invalidates_the_benchmark(register_at) -> None:
    draws, labels = _history()
    register_at(labels, 80)
    assert report.benchmark_is_stale(_cached(draws, labels, 80), draws[:79], labels[:79])


def test_a_benchmark_measured_past_the_registered_date_is_rejected(register_at) -> None:
    draws, labels = _history()
    register_at(labels, 80)
    assert report.benchmark_is_stale(_cached(draws, labels, 90), draws, labels)


def test_new_draws_after_the_registered_date_do_not_invalidate_it(register_at) -> None:
    draws, labels = _history()
    register_at(labels, 80)
    later = draws.copy()
    later[85, 0] = (later[85, 0] + 1) % 100        # sau ngày đăng ký
    assert not report.benchmark_is_stale(_cached(draws, labels, 80), later, labels)


def test_the_benchmark_reads_only_the_registered_draws(register_at, monkeypatch) -> None:
    import multi_hit_benchmark as bm

    class Seen(Exception):
        pass

    def spy(draws, weekdays, **_):
        raise Seen(len(draws))

    draws, labels = _history()
    register_at(labels, 80)
    monkeypatch.setattr(bm, "strategy_scores", spy)
    with pytest.raises(Seen) as seen:
        report.benchmark_section(draws, labels)
    assert seen.value.args == (80,)


def test_run_writes_the_filter_daily_and_the_benchmark_only_when_stale(tmp_path, monkeypatch,
                                                                       register_at) -> None:
    frame = m.mock_history(120, seed=5)
    _, labels = m.draws_from_frame(frame)
    register_at(list(labels), 80)
    frame.iloc[:80].to_csv(tmp_path / "xsmb-2-digits.csv", index=False)
    calls = []

    def fake_benchmark(draws, labels):
        n = report.registered_draws(labels)
        calls.append(n)
        return {"version": report.BENCHMARK_VERSION, "draws": n,
                "history_sha256": report.history_fingerprint(draws, labels, n)}

    monkeypatch.setattr(report, "benchmark_section", fake_benchmark)
    assert set(report.run(tmp_path)) == {"vip", "benchmark"}
    assert set(report.run(tmp_path)) == {"vip"}
    frame.to_csv(tmp_path / "xsmb-2-digits.csv", index=False)       # 40 kỳ mới sau ngày đăng ký
    assert set(report.run(tmp_path)) == {"vip"}
    assert set(report.run(tmp_path, force_benchmark=True)) == {"vip", "benchmark"}
    assert calls == [80, 80]
    vip = json.loads((tmp_path / report.OUT_DIR / report.VIP_FILE).read_text(encoding="utf-8"))
    assert vip["draws"] == 120


def test_the_recent_baseline_sums_each_displayed_draw(fair_vip) -> None:
    changed = copy.deepcopy(fair_vip)
    for i, row in enumerate(changed["recent"]):
        row["expected"] = 0.1 * (i + 1)          # tổng 5,5 — khác hẳn mọi trung bình toàn lịch sử
    text = _soup(changed, None).select_one("#app-vip-recent").get_text(" ", strip=True)
    assert "chọn bừa kỳ vọng 5,50" in text


def _data_dir(tmp_path, frame) -> Path:
    frame.to_csv(tmp_path / "xsmb-2-digits.csv", index=False)
    draws, labels = m.draws_from_frame(frame)
    out = tmp_path / report.OUT_DIR
    out.mkdir()
    (out / report.VIP_FILE).write_text(json.dumps(report.vip_section(draws, labels)), encoding="utf-8")
    bench = {"version": report.BENCHMARK_VERSION, "draws": len(draws),
             "history_sha256": report.history_fingerprint(draws, labels)}
    (out / report.BENCHMARK_FILE).write_text(json.dumps(bench), encoding="utf-8")
    return tmp_path


def _write_vip(data: Path, frame) -> None:
    draws, labels = m.draws_from_frame(frame)
    path = data / report.OUT_DIR / report.VIP_FILE
    path.write_text(json.dumps(report.vip_section(draws, labels)), encoding="utf-8")


def _corrected(frame):
    fixed = frame.copy()
    column = [c for c in fixed.columns if c != "date"][0]
    fixed.loc[3, column] = (int(fixed.loc[3, column]) + 1) % 100
    return fixed


def test_the_builder_prints_measurements_that_match_the_history(tmp_path) -> None:
    got = page.load(_data_dir(tmp_path, m.mock_history(80, seed=5)))
    assert got.vip is not None and got.bench is not None
    assert (got.vip_state, got.behind_by) == ("current", 0)


def test_the_builder_drops_a_benchmark_of_a_history_that_no_longer_exists(tmp_path) -> None:
    """Một kỳ cũ được sửa; bộ lọc đã đo lại nhưng lượt hai thì chưa (bước đo hỏng giữa chừng)."""
    frame = m.mock_history(80, seed=5)
    data = _data_dir(tmp_path, frame)
    fixed = _corrected(frame)
    fixed.to_csv(data / "xsmb-2-digits.csv", index=False)
    _write_vip(data, fixed)
    got = page.load(data)
    assert got.vip_state == "current" and got.bench is None


def test_the_builder_keeps_the_frozen_benchmark_as_new_draws_arrive(tmp_path, register_at) -> None:
    """Bộ lọc đo lại mỗi ngày; lượt hai đóng băng ở ngày đăng ký vẫn được in, kỳ mới không làm nó cũ."""
    frame = m.mock_history(120, seed=5)
    register_at(list(m.draws_from_frame(frame)[1]), 80)
    data = _data_dir(tmp_path, frame.iloc[:80].reset_index(drop=True))
    frame.to_csv(data / "xsmb-2-digits.csv", index=False)
    _write_vip(data, frame)
    got = page.load(data)
    assert got.vip_state == "current" and got.bench is not None


def test_a_filter_measurement_behind_the_history_prints_no_picks(tmp_path) -> None:
    """Sổ có thêm kỳ mà bước đo hỏng: con và cặp của lần đo cũ là cho một kỳ ĐÃ quay."""
    frame = m.mock_history(126, seed=5)
    data = _data_dir(tmp_path, frame.iloc[:120].reset_index(drop=True))
    frame.to_csv(data / "xsmb-2-digits.csv", index=False)
    got = page.load(data)
    assert (got.vip_state, got.behind_by) == ("behind", 6)
    assert got.vip["pairs"]["picks"]                             # có cặp đã đo, nhưng không được in
    soup = BeautifulSoup(page.render(got.vip, None, last_date=got.last_date,
                                     behind_by=got.behind_by), "html.parser")
    assert soup.select_one("#app-vip-picks [data-vip-behind]")["data-vip-behind"] == "6"
    assert not soup.select("#app-vip-picks .app-vip-strip li")
    assert not soup.select("#app-vip-pairs .app-vip-strip li")
    assert soup.select_one(".app-vip-verdict") is not None      # kiểm chứng của đoạn đã đo vẫn in
    assert soup.select_one(".app-vip-pair-verdict") is not None


def test_a_filter_measurement_of_a_corrected_history_prints_nothing(tmp_path) -> None:
    frame = m.mock_history(80, seed=5)
    data = _data_dir(tmp_path, frame)
    _corrected(frame).to_csv(data / "xsmb-2-digits.csv", index=False)
    got = page.load(data)
    assert got.vip_state == "invalid" and got.vip is None and got.bench is None
    docs = tmp_path / "docs"
    docs.mkdir()
    out = page.build(data, docs)
    soup = BeautifulSoup(out.read_text(encoding="utf-8"), "html.parser")
    assert soup.select_one("[data-vip-unavailable]") is not None
    assert soup.select_one(".app-vip-verdict") is None
    assert not soup.select("#app-vip-picks")


def test_a_missing_filter_measurement_replaces_the_old_page(tmp_path) -> None:
    """Thiếu vip.json thì trang cũ (với top-k và kết luận cũ) phải bị ghi đè, không được để nguyên."""
    frame = m.mock_history(80, seed=5)
    data = _data_dir(tmp_path, frame)
    (data / report.OUT_DIR / report.VIP_FILE).unlink()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / page.PAGE).write_text('<p class="app-vip-verdict" data-verdict="hon">cũ</p>', encoding="utf-8")
    out = page.build(data, docs)
    soup = BeautifulSoup(out.read_text(encoding="utf-8"), "html.parser")
    assert soup.select_one("[data-vip-unavailable]") is not None
    assert soup.select_one(".app-vip-verdict") is None


@pytest.mark.parametrize("garbage", ['{"version": 5, "draws"', "[1, 2, 3]", "\x00\x01"])
def test_unreadable_measurements_replace_the_old_page(tmp_path, garbage) -> None:
    """Tệp đo cụt hay hỏng: không làm trình dựng chết (trang cũ còn nguyên), mà coi như không hợp lệ."""
    data = _data_dir(tmp_path, m.mock_history(80, seed=5))
    for name in (report.VIP_FILE, report.BENCHMARK_FILE):
        (data / report.OUT_DIR / name).write_text(garbage, encoding="utf-8")
    got = page.load(data)
    assert (got.vip_state, got.vip, got.bench) == ("invalid", None, None)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / page.PAGE).write_text('<p class="app-vip-verdict" data-verdict="hon">cũ</p>', encoding="utf-8")
    soup = BeautifulSoup(page.build(data, docs).read_text(encoding="utf-8"), "html.parser")
    assert soup.select_one("[data-vip-unavailable]") is not None


def test_the_filter_status_follows_the_history_prefix() -> None:
    draws, labels = _history(90)
    vip = {"version": report.MEASURE_VERSION, "draws": 80,
           "history_sha256": report.history_fingerprint(draws, labels, 80)}
    assert report.vip_status(vip, draws[:80], labels[:80]) == "current"
    assert report.vip_status(vip, draws, labels) == "behind"
    fixed = draws.copy()
    fixed[2, 0] = (fixed[2, 0] + 1) % 100
    assert report.vip_status(vip, fixed, labels) == "invalid"
    assert report.vip_status(vip, draws[:79], labels[:79]) == "invalid"
    assert report.vip_status({**vip, "version": report.MEASURE_VERSION - 1}, draws[:80], labels[:80]) == "invalid"
    assert report.vip_status(None, draws, labels) == "invalid"


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
    headline = soup.select_one(".app-vip-verdict").get_text(strip=True)
    # Không bác bỏ được "không kỹ năng" không phải chứng minh không có lợi thế.
    assert headline.startswith("Không có bằng chứng hơn chọn bừa")
    assert "không loại trừ được một lợi thế nhỏ hơn" in soup.select_one("#app-lab-conclusion").get_text()


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
    blind["power"]["sensitive"] = False
    assert page.verdict(fair_vip, blind)["state"] == "chua-ket-luan"
    assert "chưa đủ căn cứ" in page.verdict_text(fair_vip, blind)[1]


def test_sensitivity_is_the_power_over_many_histories_not_one_lucky_run(fair_vip, bench) -> None:
    """Một lượt cài tín hiệu đạt hay trượt do may không được quyết định kết luận; tỉ lệ đạt mới quyết định."""
    lucky = copy.deepcopy(bench)
    lucky["power_check"]["candidate_passes"] = True
    lucky["power"].update(passes=5, rate=0.5, sensitive=False)
    assert page.verdict(fair_vip, lucky)["state"] == "chua-ket-luan"
    unlucky = copy.deepcopy(bench)
    unlucky["power_check"]["candidate_passes"] = False
    unlucky["power"].update(passes=19, rate=0.95, sensitive=True)
    assert page.verdict(fair_vip, unlucky)["state"] == "khong-hon"


@pytest.mark.parametrize(("passing", "sensitive"), [(8, True), (7, False)])
def test_power_is_the_share_of_planted_histories_that_pass(passing, sensitive) -> None:
    seeds = tuple(range(10))
    fake = lambda job: {"candidate_passes": job[1] < passing}  # noqa: E731
    runs, power = report.power_estimate(1000, seeds=seeds, run=fake, workers=1)
    assert len(runs) == 10 and power["passes"] == passing
    assert power["rate"] == pytest.approx(passing / 10)
    assert power["required"] == report.POWER_REQUIRED == 0.8
    assert power["sensitive"] is sensitive
    assert power["ci95"][0] < power["rate"] < power["ci95"][1]


def test_the_power_check_uses_many_independent_histories() -> None:
    assert len(report.POWER_SEEDS) >= 20 and len(set(report.POWER_SEEDS)) == len(report.POWER_SEEDS)


def test_without_a_benchmark_a_negative_result_is_not_concluded(fair_vip) -> None:
    """Thiếu (hay bị loại) số đo lượt hai thì chưa biết phép đo có đủ nhạy: không được nói "không hơn"."""
    soup = _soup(fair_vip, None)
    assert _verdict(soup) == "chua-ket-luan"
    headline = soup.select_one(".app-vip-verdict").get_text(strip=True)
    assert headline.startswith("Chưa kết luận được: chưa có số đo của lượt thử thứ hai")
    assert "Chưa có số đo của lượt thử thứ hai" in soup.get_text()


@pytest.mark.parametrize("case", ["fair", "planted", "no-bench"])
def test_the_detailed_conclusion_carries_the_same_headline(case, fair_vip, planted_vip, bench) -> None:
    """Kết luận ở khối trên và kết luận đầy đủ trong «Chi tiết phép đo» không được nói hai điều khác nhau."""
    vip, b = {"fair": (fair_vip, bench), "planted": (planted_vip, bench), "no-bench": (fair_vip, None)}[case]
    soup = _soup(vip, b)
    top = soup.select_one(".app-vip-verdict b").get_text(strip=True)
    detail = soup.select_one("#app-lab-conclusion p b").get_text(strip=True)
    assert top == detail
    v = page.verdict(vip, b)
    assert top == page._HEADLINE[(v["state"], v["reason"])] + "."


def test_without_a_benchmark_a_measured_edge_still_reads_better(planted_vip) -> None:
    """Bằng chứng dương của chính bộ lọc không cần lượt hai để đứng vững."""
    assert _verdict(_soup(planted_vip, None)) == "hon"


def test_the_release_check_measures_before_it_builds_the_page() -> None:
    """release_check dựng trang trên lịch sử hiện tại: bước đo phải chạy NGAY TRƯỚC trình dựng."""
    lines = [ln.strip() for ln in (ROOT / "scripts" / "release" / "release_check.sh").read_text(encoding="utf-8").splitlines()]
    build = lines.index("python src/build_multi_hit_page.py")
    assert lines[build - 1] == "python src/multi_hit_report.py"


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


def _strip(soup: BeautifulSoup, ident: str) -> list[str]:
    return [li.select_one("b").get_text(strip=True) for li in soup.select(f"#{ident} .app-vip-strip li")]


def test_the_picks_strip_lists_the_measured_top_k(planted_vip) -> None:
    soup = _soup(planted_vip, None)
    numbers = _strip(soup, "app-vip-picks")
    assert numbers == [p["number"] for p in planted_vip["picks"]]
    assert {int(n) for n in PLANTED} <= {int(n) for n in numbers}
    probs = [li.select_one("small").get_text(strip=True) for li in soup.select("#app-vip-picks .app-vip-strip li")]
    assert probs == [f"P {page._pct(p['probability'])}" for p in planted_vip["picks"]]


def test_every_strategy_of_the_benchmark_has_a_reader_facing_label(bench) -> None:
    names = [s["name"] for s in bench["strategies"]]
    assert len(names) >= 20                    # không quét tập rỗng
    missing = [n for n in names if n not in page.STRATEGY_LABELS]
    assert not missing, missing


def test_the_candidate_row_is_marked_and_only_that_row(bench, fair_vip) -> None:
    rows = _soup(fair_vip, bench).select("#app-vip-benchmark tbody tr")
    marked = [r.select_one("td").get_text(" ", strip=True) for r in rows if "ứng viên" in r.get_text()]
    assert marked == [f"{page.strategy_label(bench['candidate'])} ứng viên"]


def test_the_evidence_drawer_describes_the_methods_the_page_uses() -> None:
    """Ngăn kéo bằng chứng phải mô tả đúng phép tính mà bước đo dùng, không phải bản cũ."""
    import evidence_catalog

    _, sections = evidence_catalog._catalog({})[page.PAGE]
    steps = {sec["heading"]: " ".join(sec["reasoningTrace"]["steps"]) for sec in sections}
    assert "hiệu từng kỳ" in steps["Ít nhất một con về"]
    assert "2·p·(1 − p)" not in steps["Ít nhất một con về"]
    assert "cụm kỳ" in steps["Kết luận từ phép đo"] and "deff" in steps["Kết luận từ phép đo"]
    assert "C(d, 2)" in steps["Xiên 2"] and "chưa có bằng chứng" in steps["Xiên 2"]


def test_every_evidence_section_names_a_card_the_page_has(fair_vip, bench) -> None:
    """Ngăn kéo nhận khối theo tiền tố tiêu đề: đổi tên thẻ mà quên danh mục là mất bằng chứng."""
    import evidence_catalog

    vip = _vip_of(_pair_frame(160, pair=(12, 34)))
    titles = [h.get_text(strip=True) for h in _soup(vip, bench).select(".ui-card-head h2")]
    _, sections = evidence_catalog._catalog({})[page.PAGE]
    assert len(sections) >= 7
    for sec in sections:
        assert any(title.startswith(sec["heading"]) for title in titles), sec["heading"]


# --------------------------------------------------------------------------- cặp xiên 2


def _pair_frame(n: int, pair: tuple[int, int] | None = None, rate: float = 0.4, seed: int = 11):
    """Lịch sử giả định cùng khuôn sổ thật; ``pair`` (nếu có) được cài cùng về với xác suất ``rate``."""
    frame = m.mock_history(n, seed=seed)
    if pair is not None:
        rng = np.random.default_rng(seed + 1)
        cols = [c for c in frame.columns if c != "date"]
        for t in np.flatnonzero(rng.random(n) < rate):
            a, b = rng.choice(len(cols), size=2, replace=False)
            frame.loc[t, cols[a]], frame.loc[t, cols[b]] = pair
    return frame


def _pairs_of(frame, after: str = BEFORE_MOCK) -> dict:
    draws, labels = m.draws_from_frame(frame)
    return report.pairs_section(draws, labels, prospective_after=after)


def _present(frame) -> np.ndarray:
    return m.counts_matrix(m.draws_from_frame(frame)[0]) >= 1


def test_the_pair_baseline_is_two_fixed_numbers_both_coming() -> None:
    assert pairs.base_rate() == pytest.approx(1 - 2 * 0.99 ** 27 + 0.98 ** 27)
    present = _present(m.mock_history(4000, seed=3))
    assert (present[:, 12] & present[:, 34]).mean() == pytest.approx(pairs.base_rate(), abs=0.012)


def test_pair_picks_read_only_earlier_draws() -> None:
    present = _present(m.mock_history(260, seed=4))
    before = pairs.walk_forward(present)
    t = 200
    changed = present.copy()
    changed[t:] = ~changed[t:]                       # đảo toàn bộ từ kỳ t trở đi
    after = pairs.walk_forward(changed)
    upto = t - pairs.WINDOW + 1                     # các hàng chọn cho kỳ ≤ t
    assert (before["picks"][:upto] == after["picks"][:upto]).all()
    assert not (before["picks"][upto:] == after["picks"][upto:]).all()


def test_pair_hits_and_the_same_draw_baseline() -> None:
    present = _present(m.mock_history(180, seed=6))
    wf = pairs.walk_forward(present)
    for j, t in enumerate(wf["rows"]):
        row = present[t]
        chosen = wf["picks"][j]
        assert wf["hits"][j] == sum(bool(row[pairs.PAIR_A[i]] and row[pairs.PAIR_B[i]]) for i in chosen)
        d = int(row.sum())
        # Chọn bừa k cặp trong 4 950: kỳ có d con khác nhau về thì C(d, 2) cặp cùng về.
        assert wf["expected"][j] == pytest.approx(pairs.TOP_K * math.comb(d, 2) / 4950)


def test_the_pair_score_counts_draws_together_in_the_window() -> None:
    present = _present(m.mock_history(150, seed=7))
    wf = pairs.walk_forward(present)
    window = present[-pairs.WINDOW:]
    for i, together, last in zip(wf["picks"][-1], wf["together"], wf["last"], strict=True):
        a, b = pairs.PAIR_A[i], pairs.PAIR_B[i]
        both = window[:, a] & window[:, b]
        assert together == int(both.sum())
        assert last == len(present) - pairs.WINDOW + int(np.flatnonzero(both)[-1])


def test_the_measurement_prints_each_pair_s_own_window_count() -> None:
    frame = _pair_frame(300, pair=(12, 34))
    section = _pairs_of(frame)
    present, labels = _present(frame), list(frame["date"])
    window = present[-pairs.WINDOW:]
    assert section["picks"][0]["together"] > section["picks"][-1]["together"]
    for pick in section["picks"]:
        a, b = (int(x) for x in pick["pair"])
        both = window[:, a] & window[:, b]
        assert pick["together"] == int(both.sum())
        assert pick["last_date"] == labels[len(labels) - pairs.WINDOW + int(np.flatnonzero(both)[-1])]


def test_ties_go_to_the_pair_that_came_together_more_recently() -> None:
    together = np.zeros(pairs.N_PAIRS, dtype=int)
    last = np.full(pairs.N_PAIRS, -1)
    old, recent = 10, 4000                          # hai cặp cùng điểm cao nhất
    together[[old, recent]] = 9
    last[old], last[recent] = 50, 90
    assert pairs.pick_pairs(together, last, t=100, k=2) == [recent, old]


def test_a_number_sits_in_at_most_two_pairs() -> None:
    present = _present(m.mock_history(150, seed=8))
    present[:, 5] = True                            # con 5 về mọi kỳ: mọi cặp có 5 đều điểm cao
    picks = pairs.walk_forward(present)["picks"]
    for row in picks:
        used = np.bincount(np.concatenate([pairs.PAIR_A[row], pairs.PAIR_B[row]]), minlength=100)
        assert used.max() <= pairs.MAX_PER_NUMBER
    assert (np.bincount(np.concatenate([pairs.PAIR_A[picks[-1]], pairs.PAIR_B[picks[-1]]]),
                        minlength=100)[5] == pairs.MAX_PER_NUMBER)


def test_the_pair_rule_finds_a_planted_pair_and_the_page_says_so() -> None:
    section = _pairs_of(_pair_frame(400, pair=(12, 34)))
    assert section["picks"][0]["pair"] == ["12", "34"]
    assert section["backtest"]["lift"] > 2 and section["backtest"]["p_value"] < 1e-6
    assert section["prospective"]["p_anytime"] < 0.01 and section["confidence"] == "High"
    assert page.pair_verdict(section) == "hon"
    text = BeautifulSoup(page.pairs_card(section), "html.parser").get_text(" ", strip=True)
    assert "Có bằng chứng hơn chọn bừa" in text


def test_a_fair_history_has_no_pair_evidence_and_never_reads_not_better() -> None:
    section = _pairs_of(_pair_frame(400))
    assert section["confidence"] == "Low" and page.pair_verdict(section) == "chua-co-bang-chung"
    soup = BeautifulSoup(page.pairs_card(section), "html.parser")
    assert soup.select_one(".app-vip-pair-verdict").get_text(strip=True) == "Chưa có bằng chứng hơn chọn bừa."
    assert "không hơn" not in soup.get_text().lower()


def test_a_retrospective_pair_edge_alone_cannot_raise_the_confidence() -> None:
    frame = _pair_frame(400, pair=(12, 34))
    section = _pairs_of(frame, after=frame["date"].iloc[-1])
    assert section["backtest"]["p_value"] < 1e-6
    assert section["prospective"]["draws"] == 0 and section["prospective"]["lift"] is None
    assert section["confidence"] == "Low"


def test_only_draws_after_the_pair_freeze_are_prospective() -> None:
    frame = _pair_frame(220)
    labels = list(frame["date"])
    section = _pairs_of(frame, after=labels[189])
    assert section["prospective"]["draws"] == 30
    wf = pairs.walk_forward(_present(frame))
    assert section["prospective"]["hits"] == int(wf["hits"][-30:].sum())


def test_the_pair_measurement_is_strict_json_even_when_short() -> None:
    assert _pairs_of(m.mock_history(pairs.WINDOW, seed=1)) is None
    section = _pairs_of(m.mock_history(pairs.WINDOW + 1, seed=1))
    assert section["backtest"]["draws"] == 1
    json.dumps(section, allow_nan=False)
    assert "Chưa đủ lịch sử" in page.pairs_card(None)


def test_the_pairs_strip_lists_the_measured_pairs() -> None:
    vip = _vip_of(_pair_frame(160, pair=(12, 34)))
    soup = _soup(vip, None)
    assert _strip(soup, "app-vip-pairs") == [" · ".join(p["pair"]) for p in vip["pairs"]["picks"]]
    window = vip["pairs"]["config"]["window"]
    counts = [li.select_one("small").get_text(strip=True) for li in soup.select("#app-vip-pairs .app-vip-strip li")]
    assert counts == [f"{p['together']}/{window} kỳ" for p in vip["pairs"]["picks"]]


def test_the_recent_table_shows_each_draw_s_pairs(tmp_path) -> None:
    vip = _vip_of(_pair_frame(160, pair=(12, 34)))
    rows = _soup(vip, None).select("#app-vip-recent tbody tr")
    by_date = {r["date"]: r for r in vip["pairs"]["recent"]}
    assert len(rows) == len(vip["recent"])
    for tr, r in zip(rows, vip["recent"], strict=True):
        cells = tr.select("td")
        shown = by_date[r["date"]]
        assert [c.get_text(strip=True) for c in cells[3].select(".ui-badge")] == [
            " · ".join(x["pair"]) for x in shown["picks"]]
        assert [int(c["data-hit"]) for c in cells[3].select(".ui-badge")] == [int(x["hit"]) for x in shown["picks"]]
        assert cells[4].get_text(strip=True) == str(shown["hits"])


# --------------------------------------------------------------------------- trang đã xuất bản


def test_the_published_page_agrees_with_the_published_measurement() -> None:
    vip = json.loads((DATA / "vip.json").read_text(encoding="utf-8"))
    bench = json.loads((DATA / "benchmark.json").read_text(encoding="utf-8"))
    soup = BeautifulSoup((ROOT / "docs" / page.PAGE).read_text(encoding="utf-8"), "html.parser")
    assert _verdict(soup) == page.verdict(vip, bench)["state"]
    assert _strip(soup, "app-vip-picks") == [p["number"] for p in vip["picks"]]
    assert _strip(soup, "app-vip-pairs") == [" · ".join(p["pair"]) for p in vip["pairs"]["picks"]]
    assert soup.select_one(".app-vip-pair-verdict")["data-verdict"] == page.pair_verdict(vip["pairs"])
