"""Phép kiểm tiến cứu độ lệch theo lồng: hợp lệ khi không có gì, nhạy khi có thật, và sổ không bị viết lại."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from core.regional_domain import CAGE_OF_DIGIT
from regional_helpers import biased_law, fair_region, station_rows, write_region
from research import regional_cage_test as ct
from stats import regional_stats as rs

BIAS = {0: 6, 1: 4, 2: 1}


def _station(rows: list[dict[str, str]]) -> rs.StationHistory:
    (station,) = rs.build_stations(rows, "mn")
    return station


def _summary(region: str, stations: list[rs.StationHistory], flagged: dict[str, float]) -> dict:
    """Bản tóm tắt tối thiểu: mỗi đài một phép ``cage_uniformity`` với q cho trước (mặc định 0,5)."""
    return {
        "data_through": max(s.dates[-1] for s in stations),
        "tests": {"per_station": [
            {"province": s.province, "tests": [{
                "test": ct.TRIGGER_TEST, "p_value": 1e-6, "p_asymptotic": 1e-6,
                "q_value": flagged.get(s.province, 0.5),
            }]} for s in stations
        ]},
    }


def test_the_frozen_law_is_a_shrunk_distribution_per_cage() -> None:
    station = _station(station_rows("mn", "Đài Lệch", 50, np.random.default_rng(1), law=biased_law(BIAS)))
    law = np.array(ct.frozen_law(station))
    assert law.shape == (6, 10) and law.sum(axis=1) == pytest.approx(np.ones(6))
    counts = rs.cage_table(station.digits)
    assert law[0, 6] == pytest.approx((counts[0, 6] + 5.0) / (counts[0].sum() + 50.0), abs=1e-12)
    assert law[0, 6] < 0.06 < 0.1 < law[0, 0]
    # Lồng trăm nghìn chỉ có 50 quan sát: 50 quan sát giả kéo nó về gần đều.
    assert np.abs(law[5] - 0.1).max() < np.abs(counts[5] / counts[5].sum() - 0.1).max()


def test_log_evidence_is_the_sum_of_log_likelihood_ratios_over_all_82_digits() -> None:
    law = biased_law(BIAS).tolist()
    digits = np.random.default_rng(2).integers(0, 10, size=82)
    expected = sum(math.log(law[CAGE_OF_DIGIT[j]][int(digits[j])] / 0.1) for j in range(82))
    assert ct.log_evidence(law, digits) == pytest.approx(expected, abs=1e-12)
    assert ct.log_evidence(np.full((6, 10), 0.1).tolist(), digits) == pytest.approx(0.0, abs=1e-12)


def test_one_draw_of_evidence_has_expectation_exactly_one_under_a_fair_machine() -> None:
    """E[e] = Π_vị trí Σ_chữ số 0,1 · (luật/0,1) = Π Σ luật = 1: tính CHÍNH XÁC, không mô phỏng."""
    law = np.array(ct.frozen_law(_station(station_rows("mn", "Đài Lệch", 40, np.random.default_rng(3),
                                                       law=biased_law(BIAS)))))
    per_position = np.array([sum(0.1 * law[c, d] / 0.1 for d in range(10)) for c in CAGE_OF_DIGIT])
    assert per_position == pytest.approx(np.ones(82), abs=1e-9)
    assert float(np.prod(per_position)) == pytest.approx(1.0, abs=1e-7)


def test_a_fair_machine_rarely_ever_crosses_the_threshold() -> None:
    """Ville: P(e từng ≥ 1/α) ≤ α, dù nhìn sau mỗi kỳ. Đo với α = 0,05 trên 3 000 đài công bằng."""
    law = np.log(biased_law(BIAS, share=0.05) * 10.0)
    cages = np.array(CAGE_OF_DIGIT)
    rng = np.random.default_rng(4)
    digits = rng.integers(0, 10, size=(3000, 60, 82))
    paths = np.cumsum(law[cages, digits].sum(axis=2), axis=1)
    crossed = (paths.max(axis=1) >= math.log(1 / 0.05)).mean()
    assert crossed <= 0.05
    assert np.median(paths[:, -1]) < 0  # luật đối sai thì bằng chứng trôi về 0


def test_a_truly_biased_machine_is_confirmed_within_a_few_draws(tmp_path: Path) -> None:
    rng = np.random.default_rng(5)
    history = station_rows("mn", "Đài Lệch", 50, rng, law=biased_law(BIAS))
    station = _station(history)
    registry = {"registrations": []}
    summaries = {"mn": _summary("mn", [station], {"Đài Lệch": 0.001})}
    (entry,) = ct.register(registry, summaries, {"mn": [station]})
    assert entry["registered_through"] == station.dates[-1] and entry["draws_used"] == 50
    assert entry["family"] == 1 and entry["threshold"] == 1 / ct.ALPHA

    later = station_rows("mn", "Đài Lệch", 12, rng, law=biased_law(BIAS), start_week=50)
    grown = _station(history + later)
    ledger: list[dict[str, str]] = []
    new_rows = ct.score(registry, ledger, {"mn": [grown]})
    assert [row["date"] for row in new_rows] == list(grown.dates[50:])
    (row,) = ct.status(registry, ledger)
    assert row["confirmed"] and row["draws_scored"] == 12 and row["confirmed_on"] <= grown.dates[55]
    assert "ĐÃ XÁC NHẬN" in ct.reading(row)

    fair_later = station_rows("mn", "Đài Lệch", 12, np.random.default_rng(6), start_week=50)
    ledger = []
    ct.score(registry, ledger, {"mn": [_station(history + fair_later)]})
    (row,) = ct.status(registry, ledger)
    assert not row["confirmed"] and row["log10_e"] < 0
    assert "KHÔNG ủng hộ" in ct.reading(row)


def test_only_draws_after_registration_are_scored_and_never_twice() -> None:
    rng = np.random.default_rng(7)
    history = station_rows("mn", "Đài Lệch", 40, rng, law=biased_law(BIAS))
    station = _station(history)
    registry = {"registrations": []}
    ct.register(registry, {"mn": _summary("mn", [station], {"Đài Lệch": 0.001})}, {"mn": [station]})
    ledger: list[dict[str, str]] = []
    assert ct.score(registry, ledger, {"mn": [station]}) == []  # chưa có kỳ nào sau ngày đăng ký
    (row,) = ct.status(registry, ledger)
    assert row["draws_scored"] == 0 and "chưa có kỳ mới nào để chấm" in ct.reading(row)

    grown = _station(history + station_rows("mn", "Đài Lệch", 3, rng, law=biased_law(BIAS), start_week=40))
    first = ct.score(registry, ledger, {"mn": [grown]})
    assert len(first) == 3 and [r["draws"] for r in first] == ["1", "2", "3"]
    assert float(first[-1]["log_e_total"]) == pytest.approx(sum(float(r["log_e"]) for r in first), abs=1e-9)
    snapshot = [dict(r) for r in ledger]
    assert ct.score(registry, ledger, {"mn": [grown]}) == [] and ledger == snapshot


def test_registration_happens_once_and_is_never_rewritten() -> None:
    rng = np.random.default_rng(8)
    history = station_rows("mn", "Đài Lệch", 40, rng, law=biased_law(BIAS))
    station = _station(history)
    fair = rs.build_stations(fair_region("mt", stations=2, draws=40, seed=9), "mt")
    registry = {"registrations": []}
    summaries = {"mn": _summary("mn", [station], {"Đài Lệch": 0.001}), "mt": _summary("mt", fair, {})}
    stations = {"mn": [station], "mt": fair}
    added = ct.register(registry, summaries, stations)
    assert [e["province"] for e in added] == ["Đài Lệch"]  # đài không bị gắn cờ không được đăng ký
    assert added[0]["family"] == 3 and added[0]["threshold"] == 3 / ct.ALPHA
    frozen = json.dumps(registry, sort_keys=True)

    # Thêm kỳ mới rồi gắn cờ lại: luật đối KHÔNG được tính lại trên dữ liệu đã thấy kỳ sau đăng ký.
    grown = _station(history + station_rows("mn", "Đài Lệch", 5, rng, start_week=40))
    again = ct.register(registry, {"mn": _summary("mn", [grown], {"Đài Lệch": 1e-9}), "mt": summaries["mt"]},
                        {"mn": [grown], "mt": fair})
    assert again == [] and json.dumps(registry, sort_keys=True) == frozen


def test_a_stale_summary_cannot_freeze_a_hypothesis_on_newer_data() -> None:
    rng = np.random.default_rng(10)
    history = station_rows("mn", "Đài Lệch", 40, rng, law=biased_law(BIAS))
    old_summary = _summary("mn", [_station(history)], {"Đài Lệch": 0.001})
    grown = _station(history + station_rows("mn", "Đài Lệch", 2, rng, start_week=40))
    registry = {"registrations": []}
    assert ct.register(registry, {"mn": old_summary}, {"mn": [grown]}) == []
    assert registry["registrations"] == []


def test_run_registers_from_the_real_summary_then_appends_without_touching_old_lines(tmp_path: Path) -> None:
    rng = np.random.default_rng(11)
    fair = fair_region("mn", stations=4, draws=40, seed=12)
    biased = station_rows("mn", "Đài Lệch", 40, rng, weekday=5, law=biased_law(BIAS))
    write_region(tmp_path, "mn", fair + biased)
    write_region(tmp_path, "mt", fair_region("mt", stations=2, draws=40, seed=13))
    rs.run(tmp_path, simulations=120)
    registry_path, ledger_path = ct.run(tmp_path)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert [e["province"] for e in registry["registrations"]] == ["Đài Lệch"]
    assert registry["registrations"][0]["family"] == 7
    assert ledger_path.read_text(encoding="utf-8") == ",".join(ct.FIELDS) + "\n"
    frozen = json.dumps(registry["registrations"], sort_keys=True)

    # Hai kỳ mới của đài lệch: sổ nối thêm hai dòng, dòng tiêu đề và đăng ký giữ nguyên.
    more = station_rows("mn", "Đài Lệch", 2, rng, weekday=5, law=biased_law(BIAS), start_week=40)
    write_region(tmp_path, "mn", fair + biased + more)
    rs.run(tmp_path, simulations=120)
    ct.run(tmp_path)
    after_two = ledger_path.read_text(encoding="utf-8")
    assert after_two.count("\n") == 3 and after_two.startswith(",".join(ct.FIELDS) + "\n")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert json.dumps(registry["registrations"], sort_keys=True) == frozen
    assert registry["status"][0]["draws_scored"] == 2 and registry["status"][0]["reading"]

    last = station_rows("mn", "Đài Lệch", 1, rng, weekday=5, law=biased_law(BIAS), start_week=42)
    write_region(tmp_path, "mn", fair + biased + more + last)
    rs.run(tmp_path, simulations=120)
    ct.run(tmp_path)
    after_three = ledger_path.read_text(encoding="utf-8")
    assert after_three.startswith(after_two) and after_three.count("\n") == 4
    ct.run(tmp_path)  # chạy lại trên cùng dữ liệu: không dòng nào thêm, không byte nào đổi
    assert ledger_path.read_text(encoding="utf-8") == after_three


def test_the_committed_registry_is_frozen_before_any_draw_it_scores() -> None:
    """Đăng ký đã commit: mỗi dòng sổ phải là kỳ SAU ngày đóng băng, và luật đối là một phân phối."""
    root = Path(__file__).resolve().parents[2]
    registry = json.loads((root / "data" / ct.REGISTRY).read_text(encoding="utf-8"))
    assert registry["registrations"], "sổ miền đã commit có đài bị gắn cờ: phải có đăng ký"
    through = {e["id"]: e["registered_through"] for e in registry["registrations"]}
    for entry in registry["registrations"]:
        assert np.array(entry["law"]).sum(axis=1) == pytest.approx(np.ones(6), abs=1e-9)
        assert entry["threshold"] == entry["family"] / entry["alpha"] and entry["alpha"] == ct.ALPHA
        assert entry["version"] == ct.VERSION and entry["prior_strength"] == ct.PRIOR_STRENGTH
    for row in ct._read_ledger(root / "data" / ct.LEDGER):
        assert row["date"] > through[row["id"]]
