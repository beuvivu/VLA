from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.regional_domain import LOTO_BASELINE_RATE
from evaluation import regional_benchmark as rb
from regional_helpers import biased_law, fair_region, station_rows, write_region
from stats.regional_stats import build_stations, read_rows
from stats.statistical_corrections import holm


def _states(rows: list[dict[str, str]], mode: str, region: str = "mn") -> list[rb.StationState]:
    return [rb.station_state(s, mode) for s in build_stations(rows, region)]


def test_station_state_only_counts_draws_before_the_one_it_describes() -> None:
    rows = station_rows("mn", "Đài A", 30, np.random.default_rng(1))
    (state,) = _states(rows, "loto")
    hit = state.hit
    assert state.cum[0].sum() == 0 and state.window[0].sum() == 0 and not state.last[0].any()
    for t in (1, 7, 25, 29):
        assert (state.cum[t] == hit[:t].sum(axis=0)).all()
        assert (state.window[t] == hit[max(0, t - rb.ROLLING) : t].sum(axis=0)).all()
        assert (state.recent[t] == hit[max(0, t - rb.RECENT) : t].sum(axis=0)).all()
        assert (state.last[t] == hit[t - 1]).all()
        for number in (3, 50, 97):
            seen = np.flatnonzero(hit[:t, number])
            assert state.gap[t, number] == (t - 1 - seen[-1] if len(seen) else t)
        assert state.cage[t].sum() == 82 * t


@pytest.mark.parametrize("mode", rb.MODES)
def test_no_forecast_reads_a_draw_on_or_after_its_target(mode: str) -> None:
    rows = fair_region("mn", stations=5, draws=44, seed=2)
    full_stations = build_stations(rows, "mn")
    days = sorted({day for s in full_stations for day in s.dates})
    cut = days[len(days) * 2 // 3]
    early = [r for r in rows if r["date"] <= cut]
    full = rb.forecasts([rb.station_state(s, mode) for s in full_stations], mode)
    part_stations = build_stations(early, "mn")
    part = rb.forecasts([rb.station_state(s, mode) for s in part_stations], mode)
    assert set(full) == set(rb.PROBABILITY_MODELS)
    for name in rb.PROBABILITY_MODELS:
        for whole, cutoff, station in zip(full[name], part[name], part_stations, strict=True):
            assert np.array_equal(whole[: len(station)], cutoff), name
    ranks_full = rb.ranking_scores([rb.station_state(s, mode) for s in full_stations])
    ranks_part = rb.ranking_scores([rb.station_state(s, mode) for s in part_stations])
    for name in rb.RANKINGS:
        for whole, cutoff in zip(ranks_full[name], ranks_part[name], strict=True):
            assert np.array_equal(whole[: len(cutoff)], cutoff), name


@pytest.mark.parametrize("mode", rb.MODES)
def test_the_target_draw_itself_never_enters_its_own_forecast(mode: str) -> None:
    rows = fair_region("mn", stations=4, draws=42, seed=21)
    last = {r["province"]: max(x["date"] for x in rows if x["province"] == r["province"]) for r in rows}
    changed = [dict(r) for r in rows]
    for r in changed:
        if r["date"] == last[r["province"]]:
            r["value"] = "".join(str((int(ch) + 3) % 10) for ch in r["value"])
    before = rb.forecasts(_states(rows, mode), mode)
    after = rb.forecasts(_states(changed, mode), mode)
    for name in rb.PROBABILITY_MODELS:
        for old_p, new_p in zip(before[name], after[name], strict=True):
            assert np.array_equal(old_p, new_p), name
    scores_before, scores_after = rb.ranking_scores(_states(rows, mode)), rb.ranking_scores(_states(changed, mode))
    for name in rb.RANKINGS:
        for old_s, new_s in zip(scores_before[name], scores_after[name], strict=True):
            assert np.array_equal(old_s, new_s), name


def test_two_stations_drawing_on_the_same_day_cannot_see_each_other() -> None:
    rng = np.random.default_rng(3)
    a = station_rows("mn", "Đài A", 40, rng, weekday=0)
    b = station_rows("mn", "Đài B", 40, rng, weekday=0)
    changed = [dict(r) for r in b]
    last_day = max(r["date"] for r in b)
    for r in changed:
        if r["date"] == last_day:
            r["value"] = "".join(str((int(ch) + 5) % 10) for ch in r["value"])
    for mode in rb.MODES:
        before = rb.forecasts(_states(a + b, mode), mode)
        after = rb.forecasts(_states(a + changed, mode), mode)
        for name in rb.PROBABILITY_MODELS:
            assert np.array_equal(before[name][0], after[name][0]), (mode, name)


def test_special_forecasts_sum_to_one_and_loto_forecasts_stay_probabilities() -> None:
    rows = fair_region("mn", stations=3, draws=40, seed=4)
    for mode in rb.MODES:
        states = _states(rows, mode)
        for name, per_station in rb.forecasts(states, mode).items():
            for p in per_station:
                assert np.isfinite(p).all() and (p > 0).all() and (p < 1).all(), (mode, name)
                if mode == "de":
                    assert p.sum(axis=1) == pytest.approx(np.ones(len(p))), name
    uniform = rb.uniform(_states(rows, "loto")[0], "loto")
    assert uniform.sum(axis=1) == pytest.approx(np.full(40, 100 * LOTO_BASELINE_RATE))


def test_log_loss_matches_the_textbook_formula() -> None:
    hit = np.zeros((1, 100), dtype=bool)
    hit[0, [3, 8]] = True
    p = np.full((1, 100), 0.2)
    assert rb.log_loss("loto", p, hit)[0] == pytest.approx(-(2 * np.log(0.2) + 98 * np.log(0.8)) / 100)
    special = np.zeros((1, 100), dtype=bool)
    special[0, 42] = True
    q = np.full((1, 100), 0.01)
    assert rb.log_loss("de", q, special)[0] == pytest.approx(np.log(100))


def test_cage_models_put_the_short_ball_numbers_below_baseline() -> None:
    rng = np.random.default_rng(5)
    rows = station_rows("mn", "Đài Lệch", 60, rng, law=biased_law({0: 6, 1: 4}))
    (state,) = _states(rows, "loto")
    for model in (rb.cage_digits, rb.cage_empirical_bayes):
        p = model(state, "loto")[-1]
        assert p.argmin() == 46
        assert p[46] < 0.5 * LOTO_BASELINE_RATE < LOTO_BASELINE_RATE < p[17]
        special = model(state, "de")[-1]
        assert special.sum() == pytest.approx(1.0) and special.argmin() == 46
    assert rb.cage_digits(state, "loto")[0] == pytest.approx(np.full(100, LOTO_BASELINE_RATE))
    assert rb.cage_empirical_bayes(state, "loto")[0] == pytest.approx(np.full(100, LOTO_BASELINE_RATE))


def test_empirical_bayes_cage_model_collapses_to_uniform_on_a_fair_station() -> None:
    rows = station_rows("mn", "Đài Đều", 60, np.random.default_rng(6))
    (state,) = _states(rows, "loto")
    fixed = np.abs(rb.cage_digits(state, "loto")[30:] - LOTO_BASELINE_RATE).mean()
    learned = np.abs(rb.cage_empirical_bayes(state, "loto")[30:] - LOTO_BASELINE_RATE).mean()
    assert learned < 0.5 * fixed


def test_a_fair_region_shows_no_edge_and_says_so() -> None:
    rows = fair_region("mt", stations=8, draws=50, seed=7)
    modes = {mode: rb.evaluate_mode(_states(rows, mode, "mt"), mode) for mode in rb.MODES}
    for block in modes.values():
        assert block["station_draws"] == 8 * (50 - rb.WARMUP) and block["edge"] == []
        assert block["models"]["deu"]["ranking"]["hit_rate"] == pytest.approx(block["models"]["deu"]["ranking"]["chance"], abs=0.02)
        assert all(not block["models"][name]["edge"] for name in rb.PROBABILITY_MODELS if name != "deu")
        assert all(not row["edge"] for row in block["rankings"].values())
        assert all(block["models"][name]["stations_with_edge"] == [] for name in rb.PROBABILITY_MODELS if name != "deu")
        assert block["models"]["tan_suat_truot"]["mean_gain"] < 0
    assert modes["de"]["models"]["deu"]["log_loss"] == pytest.approx(np.log(100))
    assert modes["de"]["models"]["deu"]["ranking"]["mrr"] == pytest.approx(
        modes["de"]["models"]["deu"]["ranking"]["chance_mrr"]
    )
    text = rb.reading("Miền Trung", modes)
    assert text.startswith("Miền Trung: CHƯA CHỨNG MINH ĐƯỢC LỢI THẾ DỰ BÁO cho lô và đuôi Đặc Biệt")
    assert "Riêng từng đài" not in text and rb.station_edges(modes) == []


def test_a_planted_cage_bias_wins_out_of_sample_at_that_station_only() -> None:
    rng = np.random.default_rng(8)
    rows = fair_region("mn", stations=6, draws=60, seed=9)
    rows += station_rows("mn", "Đài Lệch", 60, rng, weekday=2, law=biased_law({0: 6, 1: 4, 2: 1}))
    modes = {"loto": rb.evaluate_mode(_states(rows, "loto"), "loto")}
    block = modes["loto"]["models"]
    assert block["long_chu_so"]["stations_with_edge"] == ["Đài Lệch"]
    assert block["long_bayes"]["stations_with_edge"] == ["Đài Lệch"]
    assert block["long_bayes"]["post_hoc"] and not block["long_chu_so"]["post_hoc"]
    assert block["tan_suat"]["stations_with_edge"] == []
    (edge,) = rb.station_edges(modes)
    winners = {
        name: next(r["mean_gain"] for r in model["stations"] if r["province"] == "Đài Lệch")
        for name, model in block.items()
        if name != "deu" and "Đài Lệch" in model["stations_with_edge"] and not model["post_hoc"]
    }
    assert (edge["province"], edge["post_hoc"]) == ("Đài Lệch", False)
    assert edge["model"] == max(winners, key=winners.get) == "long_chu_so"
    boosted = json.loads(json.dumps(modes))
    for row in boosted["loto"]["models"]["long_bayes"]["stations"]:
        row["mean_gain"] = 9.0
    assert rb.station_edges(boosted)[0]["model"] == "long_chu_so"
    for name in winners:
        boosted["loto"]["models"][name]["stations_with_edge"] = []
    assert [(e["model"], e["post_hoc"]) for e in rb.station_edges(boosted)] == [("long_bayes", True)]
    candidates = [name for name in rb.PROBABILITY_MODELS if name != "deu"]
    family = [row for name in candidates for row in block[name]["stations"]]
    assert len(family) == len(candidates) * 7
    joint = holm([row["p_value"] for row in family])
    assert [row["p_holm"] for row in family] == joint
    per_model = [a for name in candidates for a in holm([r["p_value"] for r in block[name]["stations"]])]
    assert any(alone < together for alone, together in zip(per_model, joint, strict=True))
    text = rb.reading("Miền Nam", modes)
    assert "Riêng từng đài" in text and "Đài Lệch — Chữ số theo lồng cho lô" in text
    assert "hiệu chỉnh Holm trên mọi cặp đài × mô hình" in text
    assert "chỉ thành lợi thế khi phép kiểm tiến cứu đã đăng ký xác nhận" in text
    assert f"(lợi +{edge['mean_gain']:.4f}".replace(".", ",") in text


def test_a_planted_hot_number_in_every_station_gives_a_regional_edge() -> None:
    rng = np.random.default_rng(10)
    rows = []
    for index in range(8):
        station = station_rows("mn", f"Đài {index + 1}", 60, rng, weekday=index % 7)
        draws = sorted({r["date"] for r in station})
        forced = {day for day in draws if rng.random() < 0.45}
        for r in station:
            if r["date"] in forced and r["prize"] == "G.8":
                r["value"] = "77"
        rows += station
    block = rb.evaluate_mode(_states(rows, "loto"), "loto")
    assert block["models"]["bayes_thuc_nghiem"]["edge"] and "bayes_thuc_nghiem" in block["edge"]
    assert block["models"]["bayes_thuc_nghiem"]["mean_gain"] > 0
    assert block["models"]["bayes_thuc_nghiem"]["ci_low"] > 0
    assert "Thắng dự báo đều ngoài mẫu: Bayes thực nghiệm cho lô" in rb.reading("Miền Nam", {"loto": block})


def test_a_region_too_short_to_score_is_reported_as_such() -> None:
    rows = fair_region("mn", stations=2, draws=rb.WARMUP, seed=11)
    modes = {mode: rb.evaluate_mode(_states(rows, mode), mode) for mode in rb.MODES}
    assert all(block["station_draws"] == 0 and block["models"] == {} for block in modes.values())
    assert rb.reading("Miền Nam", modes) == f"Miền Nam: chưa đủ kỳ để chấm (mỗi đài cần hơn {rb.WARMUP} kỳ)."


def test_run_writes_a_deterministic_report_with_its_frozen_configuration(tmp_path: Path) -> None:
    write_region(tmp_path, "mn", fair_region("mn", stations=3, draws=40, seed=12))
    write_region(tmp_path, "mt", fair_region("mt", stations=3, draws=40, seed=13))
    path = rb.run(tmp_path)
    first = path.read_bytes()
    assert rb.run(tmp_path).read_bytes() == first
    report = json.loads(first)
    assert report["config"] == rb.CONFIG and report["config"]["benchmark_version"] == rb.BENCHMARK_VERSION
    assert set(report["regions"]) == {"mt", "mn"}
    assert "generated" not in first.decode("utf-8")
    for block in report["regions"].values():
        assert set(block["modes"]) == set(rb.MODES) and block["reading"]
        assert set(block["modes"]["loto"]["models"]) == set(rb.PROBABILITY_MODELS)
        assert set(block["modes"]["loto"]["rankings"]) == set(rb.RANKINGS)


def test_the_committed_report_matches_the_committed_ledgers() -> None:
    root = Path(__file__).resolve().parents[2]
    report = json.loads((root / "data" / rb.OUT).read_text(encoding="utf-8"))
    assert report["config"] == rb.CONFIG and set(report["regions"]) == {"mt", "mn"}
    for region, block in report["regions"].items():
        rows = read_rows(root / "data" / "regions" / f"xs{region}.csv")
        assert block["data_through"] <= max(r["date"] for r in rows)
        stations = build_stations([r for r in rows if r["date"] <= block["data_through"]], region)
        assert block["data_through"] == max(s.dates[-1] for s in stations)
        scored = sum(max(0, len(s) - rb.WARMUP) for s in stations)
        assert block["modes"]["loto"]["station_draws"] == scored == block["modes"]["de"]["station_draws"]
        assert block["reading"] == rb.reading(block["region_name"], block["modes"])
