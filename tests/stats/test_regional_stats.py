"""Thống kê và kiểm định từng đài XSMT/XSMN: lịch sử công bằng không sinh phát hiện, độ lệch cài sẵn bị bắt."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from scipy import stats as scipy_stats

from core.regional_domain import LOTO_BASELINE_RATE, SLOT_WIDTHS
from regional_helpers import FIRST_DAY, biased_law, fair_region, station_rows, write_region
from stats import regional_stats as rs

SIMS = 300


def _one(rows: list[dict[str, str]], region: str = "mn") -> rs.StationHistory:
    (station,) = rs.build_stations(rows, region)
    return station


def test_real_regional_ledgers_are_structurally_valid() -> None:
    """Sổ đã commit của hai miền phải dựng được thành lịch sử từng đài."""
    root = Path(__file__).resolve().parents[2]
    for region in ("mt", "mn"):
        rows = rs.read_rows(root / "data" / "regions" / f"xs{region}.csv")
        assert rows, region
        assert rs.structural_issues(rows, region) == []
        stations = rs.build_stations(rows, region)
        assert sum(len(s) for s in stations) * 18 == len(rows)
        assert all(s.tails.shape == (len(s), 18) and s.digits.shape == (len(s), 82) for s in stations)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda rows: rows[0].__setitem__("region", "mt"), "miền"),
        (lambda rows: rows[0].__setitem__("value", "7"), "không phải 2 chữ số"),
        (lambda rows: rows[1].__setitem__("value", "12a"), "không phải 3 chữ số"),
        (lambda rows: rows[0].__setitem__("prize", "G.9"), "giải/vị trí lạ"),
        (lambda rows: rows[0].__setitem__("date", "2025-13-40"), "ngày không hợp lệ"),
        (lambda rows: rows.append(dict(rows[0])), "khoá trùng"),
        (lambda rows: rows.pop(3), "17/18 ô"),
        (lambda rows: rows[0].__setitem__("province", " "), "thiếu tên đài"),
    ],
)
def test_a_structurally_broken_ledger_never_reaches_the_statistics(change, message: str) -> None:
    rows = station_rows("mn", "Đài A", 3, np.random.default_rng(1))
    assert rs.structural_issues(rows, "mn") == []
    change(rows)
    assert any(message in issue for issue in rs.structural_issues(rows, "mn"))
    with pytest.raises(rs.RegionalDataError):
        rs.build_stations(rows, "mn")


def test_station_history_keeps_every_digit_and_the_special_tail() -> None:
    rows = station_rows("mn", "Đài A", 2, np.random.default_rng(2))
    station = _one(rows)
    first = [r["value"] for r in rows[:18]]
    assert "".join(map(str, station.digits[0])) == "".join(first)
    assert station.tails[0].tolist() == [int(v[-2:]) for v in first]
    assert station.special[0] == int(first[-1][-2:])
    assert station.counts.sum(axis=1).tolist() == [18, 18]
    assert station.hits("de").sum(axis=1).tolist() == [1, 1]
    assert (station.hits("loto") == (station.counts > 0)).all()


def test_quality_report_finds_gaps_missing_stations_and_copied_draws() -> None:
    rng = np.random.default_rng(3)
    a = station_rows("mn", "Đài A", 10, rng, weekday=0)
    b = station_rows("mn", "Đài B", 10, rng, weekday=0)
    c = station_rows("mn", "Đài C", 10, rng, weekday=1)
    clean = a + b + c
    report = rs.quality_report(clean, rs.build_stations(clean, "mn"))
    assert report["station_draws"] == 30 and report["stations"] == 3 and report["origins"] == 1
    assert report["weekly_schedule"] == {"0": ["Đài A", "Đài B"], "1": ["Đài C"]}
    assert report["off_schedule"] == [] and report["repeated_draws"] == [] and report["cloned_draws"] == []
    # Thứ Tư … Chủ nhật không đài nào quay: ngày lịch trống được liệt kê, không bị giấu.
    assert len(report["calendar_gaps"]) == 9 * 5

    week3 = (FIRST_DAY + timedelta(days=14)).isoformat()
    missing = [r for r in clean if not (r["province"] == "Đài B" and r["date"] == week3)]
    report = rs.quality_report(missing, rs.build_stations(missing, "mn"))
    assert report["off_schedule"] == [{"date": week3, "missing": ["Đài B"], "unexpected": []}]

    copied = [dict(r) for r in clean]
    week4 = (FIRST_DAY + timedelta(days=21)).isoformat()
    source = {(r["prize"], r["position"]): r["value"] for r in copied if r["province"] == "Đài A" and r["date"] == week3}
    for r in copied:
        if r["province"] == "Đài A" and r["date"] == week4:
            r["value"] = source[(r["prize"], r["position"])]
        if r["province"] == "Đài B" and r["date"] == week3:
            r["value"] = source[(r["prize"], r["position"])]
    report = rs.quality_report(copied, rs.build_stations(copied, "mn"))
    assert report["repeated_draws"] == [{"province": "Đài A", "date": week4}]
    assert report["cloned_draws"] == [{"date": week3, "provinces": ["Đài A", "Đài B"]}]


def test_the_content_fingerprint_ignores_fetch_time_and_row_order_but_not_values() -> None:
    rows = station_rows("mn", "Đài A", 4, np.random.default_rng(4))
    base = rs.quality_report(rows, rs.build_stations(rows, "mn"))["content_sha256"]
    shuffled = [dict(r, fetched_at="2030-01-01T00:00:00+07:00") for r in reversed(rows)]
    assert rs.quality_report(shuffled, rs.build_stations(shuffled, "mn"))["content_sha256"] == base
    changed = [dict(r) for r in rows]
    changed[0]["value"] = f"{(int(changed[0]['value']) + 1) % 100:02d}"
    assert rs.quality_report(changed, rs.build_stations(changed, "mn"))["content_sha256"] != base


def test_frequency_table_counts_presence_gap_and_exact_binomial_p() -> None:
    rows = station_rows("mn", "Đài A", 12, np.random.default_rng(5))
    station = _one(rows)
    table = rs.frequency_table([station])
    assert table["number"].tolist() == [f"{n:02d}" for n in range(100)]
    assert table["nhay"].sum() == 12 * 18 and (table["draws"] == 12).all()
    present = station.hits("loto")
    for number in (0, 37, 99):
        row = table.iloc[number]
        assert row["present"] == present[:, number].sum()
        seen = np.flatnonzero(present[:, number])
        assert row["gap"] == (11 - seen[-1] if len(seen) else 12)
        assert row["p_value"] == pytest.approx(
            scipy_stats.binomtest(int(row["present"]), 12, LOTO_BASELINE_RATE).pvalue, abs=1e-9
        )
    assert table["expected_present"].iloc[0] == pytest.approx(12 * LOTO_BASELINE_RATE, abs=1e-6)
    assert table["special_hits"].sum() == 12


def test_cage_table_pools_every_prize_that_draws_from_the_same_cage() -> None:
    digits = np.zeros((1, 82), dtype=np.int8)
    ends = np.cumsum(SLOT_WIDTHS)
    digits[0, ends - 1] = 7  # mọi giải: hàng đơn vị = 7
    digits[0, ends - 2] = 3  # mọi giải: hàng chục = 3
    table = rs.cage_table(digits)
    assert table.sum(axis=1).tolist() == [18, 18, 17, 16, 12, 1]
    assert table[0, 7] == 18 and table[1, 3] == 18 and table[2, 0] == 17
    assert rs.position_table(digits).sum(axis=1).tolist() == [1] * 82
    # Lồng đơn vị dồn cả 18 lần rút vào một quả: χ² = (18 − 1,8)²/1,8 + 9·1,8.
    units_only = np.zeros((6, 10))
    units_only[0, 7] = 18
    assert rs._chi_square_rows(units_only) == pytest.approx((18 - 1.8) ** 2 / 1.8 + 9 * 1.8)
    # Phép theo lồng chỉ cộng năm lồng thấp. Hai kỳ giống hệt nhau, rồi đổi chữ số ĐẦU của Đặc Biệt
    # (lồng trăm nghìn) ở kỳ thứ hai: lồng ấy từ "hai lần cùng một quả" thành "hai quả khác nhau",
    # χ² của riêng nó đổi từ 18 xuống 8, nhưng thống kê theo lồng không được đổi.
    two = np.vstack([digits, digits])
    moved = two.copy()
    moved[1, ends[-1] - 6] = 9
    assert rs._chi_square_rows(rs.cage_table(two)[5:]) == pytest.approx(18.0)
    assert rs._chi_square_rows(rs.cage_table(moved)[5:]) == pytest.approx(8.0)
    assert rs.cage_chi_square(moved) == rs.cage_chi_square(two)
    assert rs.digit_chi_square(moved) != rs.digit_chi_square(two)


def test_the_battery_computes_exactly_the_public_statistics() -> None:
    """Tám cột của bộ kiểm là đúng tám hàm công khai, theo đúng thứ tự của ``TESTS``."""
    station = _one(station_rows("mn", "Đài A", 34, np.random.default_rng(31)))
    counts = station.counts
    present = counts > 0
    from stats import randomness_battery as battery

    expected = [
        rs.cage_chi_square(station.digits),
        rs.digit_chi_square(station.digits),
        rs.special_digit_chi_square(station.digits),
        battery.marginal_chi_square(counts),
        battery.dispersion_index(counts),
        rs.repeat_lift(present),
        rs.gap_ks(present),
        battery.hot_number_persistence(counts),
    ]
    assert rs._statistics(station.digits) == pytest.approx(expected, abs=1e-12)
    assert rs.TEST_CODES == (
        "cage_uniformity", "digit_uniformity", "special_digits", "loto_uniformity",
        "dispersion", "repeat_lift", "gap_shape", "hot_persistence",
    )
    results, observed, _ = rs.station_battery(station, simulations=20, seed=1)
    assert [r["test"] for r in results] == list(rs.TEST_CODES)
    assert observed == pytest.approx(expected, abs=1e-12)


def test_repeat_lift_and_gap_ks_on_hand_built_histories() -> None:
    present = np.zeros((4, 100), dtype=bool)
    present[0, :10] = True
    present[1, :5] = True  # 5/10 con vừa về lặp lại, 0/90 con chưa về xuất hiện
    assert rs.repeat_lift(present[:2]) == pytest.approx(0.5)
    assert rs.repeat_lift(np.zeros((3, 100), dtype=bool)) == 0.0
    # Mọi con về đúng mỗi 2 kỳ: khoảng cách luôn bằng 2, hàm phân phối kinh nghiệm nhảy từ 0 lên 1 ở 2.
    periodic = np.zeros((40, 100), dtype=bool)
    periodic[::2] = True
    # Hình học cho F(1) = b và F(2) = 1 − (1 − b)²; lệch lớn nhất là max(b, (1 − b)²) = (1 − b)².
    assert rs.gap_ks(periodic) == pytest.approx((1 - LOTO_BASELINE_RATE) ** 2, abs=1e-12)
    assert rs.gap_ks(np.zeros((5, 100), dtype=bool)) == 0.0


def test_a_fair_station_gets_calibrated_p_values() -> None:
    """Trên đài công bằng, p của từng phép phải gần đều: không phép nào tự sinh phát hiện."""
    rows = fair_region("mn", stations=40, draws=40, seed=6)
    small = []
    for station in rs.build_stations(rows, "mn"):
        results, _, null = rs.station_battery(station, simulations=150, seed=11)
        assert null.shape == (150, len(rs.TESTS))
        small.extend(r["p_value"] for r in results)
    p = np.array(small)
    assert len(p) == 40 * 8
    assert 0.01 <= (p < 0.05).mean() <= 0.10
    assert 0.38 <= np.median(p) <= 0.62


def test_a_station_result_does_not_depend_on_which_other_stations_exist() -> None:
    rng = np.random.default_rng(7)
    alone = station_rows("mn", "Đài A", 35, rng)
    station = _one(alone)
    first, _, _ = rs.station_battery(station, simulations=80, seed=3)
    again, _, _ = rs.station_battery(station, simulations=80, seed=3)
    assert first == again
    renamed = rs.StationHistory("mn", "Đài Khác", station.dates, station.tails, station.digits)
    other, _, _ = rs.station_battery(renamed, simulations=80, seed=3)
    assert [r["statistic"] for r in other] == [r["statistic"] for r in first]
    assert [r["p_value"] for r in other] != [r["p_value"] for r in first]  # hạt giống theo tên đài


def test_a_planted_cage_bias_is_flagged_by_name_and_a_fair_region_is_not(tmp_path: Path) -> None:
    rng = np.random.default_rng(8)
    rows = fair_region("mn", stations=6, draws=45, seed=9)
    rows += station_rows("mn", "Đài Lệch", 45, rng, weekday=3, law=biased_law({0: 6, 1: 4, 2: 1}))
    stations = rs.build_stations(rows, "mn")
    summary = rs.summarize(rows, stations, rs.frequency_table(stations), simulations=SIMS, seed=5)
    flagged = {block["province"]: block["tests"] for block in summary["tests"]["flagged_stations"]}
    assert list(flagged) == ["Đài Lệch"] and "Chữ số theo lồng" in flagged["Đài Lệch"]
    block = next(b for b in summary["tests"]["per_station"] if b["province"] == "Đài Lệch")
    cage = next(t for t in block["tests"] if t["test"] == "cage_uniformity")
    # p mô phỏng chạm sàn 1/301; p dùng cho đa kiểm là đuôi χ²(45), nhỏ hơn nhiều bậc.
    assert cage["p_simulated"] == pytest.approx(1 / (SIMS + 1))
    assert cage["p_value"] == cage["p_asymptotic"] < 1e-12
    assert np.array(block["cage_counts"])[0, 6] < 45 * 18 * 0.06
    assert all("cage_counts" not in b for b in summary["tests"]["per_station"] if b["province"] != "Đài Lệch")
    assert "Đài Lệch (chữ số theo lồng" in summary["reading"] and "chưa phải lợi thế dự báo" in summary["reading"]
    pooled = {t["test"]: t for t in summary["tests"]["pooled"]}
    assert pooled["cage_uniformity"]["p_value"] < 0.01

    fair = fair_region("mt", stations=6, draws=45, seed=10)
    fair_stations = rs.build_stations(fair, "mt")
    clean = rs.summarize(fair, fair_stations, rs.frequency_table(fair_stations), simulations=SIMS, seed=5)
    assert clean["tests"]["flagged_stations"] == [] and clean["tests"]["significant_cells"] == 0
    assert clean["reading"].startswith("Không phép kiểm nào trong 48 phép")
    assert clean["numbers"]["significant"] == 0


def test_the_summary_states_the_game_and_what_it_could_have_detected() -> None:
    rows = fair_region("mn", stations=3, draws=32, seed=12)
    stations = rs.build_stations(rows, "mn")
    summary = rs.summarize(rows, stations, rs.frequency_table(stations), simulations=60, seed=1)
    assert summary["game"]["prizes_per_station_draw"] == 18
    assert summary["game"]["loto_baseline"] == pytest.approx(1 - 0.99**18)
    assert summary["game"]["expected_distinct_numbers"] == pytest.approx(100 * (1 - 0.99**18), abs=1e-6)
    assert abs(summary["game"]["observed_distinct_numbers"] - 16.55) < 0.5
    per_station = summary["detectable"]["per_station"]
    assert per_station["draws"] == 32 and per_station["hypotheses"] == 100
    z = scipy_stats.norm.isf(0.05 / 100 / 2) + scipy_stats.norm.isf(0.2)
    assert per_station["absolute_lift"] == pytest.approx(
        z * np.sqrt(LOTO_BASELINE_RATE * (1 - LOTO_BASELINE_RATE) / 32), abs=1e-6
    )
    assert summary["detectable"]["pooled_region"]["absolute_lift"] < per_station["absolute_lift"]
    shown = f"{per_station['absolute_lift'] * 100:.1f}".replace(".", ",")
    assert f"{shown} điểm phần trăm" in summary["reading"] and "." not in shown


def test_stations_below_the_minimum_history_are_not_tested() -> None:
    rows = fair_region("mn", stations=2, draws=rs.MIN_DRAWS_FOR_TESTS - 1, seed=13)
    stations = rs.build_stations(rows, "mn")
    summary = rs.summarize(rows, stations, rs.frequency_table(stations), simulations=20, seed=1)
    assert summary["tests"]["cells"] == 0 and summary["tests"]["per_station"] == []
    assert summary["reading"] == f"Chưa đài nào đủ {rs.MIN_DRAWS_FOR_TESTS} kỳ để kiểm định."


def test_run_writes_one_csv_and_one_summary_per_region_and_reruns_byte_identical(tmp_path: Path) -> None:
    write_region(tmp_path, "mn", fair_region("mn", stations=2, draws=31, seed=14))
    write_region(tmp_path, "mt", fair_region("mt", stations=2, draws=31, seed=15))
    written = rs.run(tmp_path, simulations=40)
    assert sorted(p.name for p in written) == [
        "frequency_mn.csv", "frequency_mt.csv", "summary_mn.json", "summary_mt.json",
    ]
    before = {p.name: p.read_bytes() for p in written}
    rs.run(tmp_path, simulations=40)
    assert {p.name: p.read_bytes() for p in written} == before
    summary = json.loads((tmp_path / "data" / "stats" / "regional" / "summary_mn.json").read_text(encoding="utf-8"))
    assert summary["region"] == "mn" and summary["data_through"] == max(
        (FIRST_DAY + timedelta(days=7 * 30 + i)).isoformat() for i in range(2)
    )
    # Không dấu giờ trong tệp: chạy lại vào ngày khác vẫn ra đúng tệp ấy.
    today = datetime.now(UTC).date()
    stamped = {(today + timedelta(days=shift)).isoformat() for shift in (-1, 0, 1)}
    assert "generated" not in json.dumps(summary) and not any(day in json.dumps(summary) for day in stamped)
    header = (tmp_path / "data" / "stats" / "regional" / "frequency_mn.csv").read_text(encoding="utf-8").splitlines()
    assert header[0].split(",")[:3] == ["region", "province", "number"] and header[1].split(",")[2] == "00"


def test_a_broken_ledger_stops_the_run_instead_of_being_summarised(tmp_path: Path) -> None:
    rows = fair_region("mn", stations=1, draws=31, seed=16)
    rows[5]["value"] = "x"
    write_region(tmp_path, "mn", rows)
    with pytest.raises(rs.RegionalDataError):
        rs.run(tmp_path, simulations=10)
    assert list((tmp_path / "data" / "stats" / "regional").glob("*")) == []
