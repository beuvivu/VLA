"""Phần điều hành phải phản ánh báo cáo, không tạo trạng thái nghiên cứu giả."""

import json
from pathlib import Path

from bs4 import BeautifulSoup

from pages.build_research_lab import build


def _render(tmp_path: Path, diagnostics: dict, firewall: dict) -> BeautifulSoup:
    research = tmp_path / "data" / "research"
    research.mkdir(parents=True)
    for filename, payload in (("scientific_diagnostics.json", diagnostics),
                              ("research_firewall_report.json", firewall)):
        (research / filename).write_text(json.dumps(payload), encoding="utf-8")
    return BeautifulSoup(build(tmp_path / "data", tmp_path / "docs").read_text(), "html.parser")


def test_overview_keeps_family_counts_and_holdout_scope_separate(tmp_path: Path) -> None:
    """Cộng nhầm kỳ giữ lại hoặc dùng số giả thuyết làm số đạt sẽ bị chặn."""
    page = _render(tmp_path, {"draw_days": 123, "end_date": "2026-10-06"}, {
        "anchor_date": "2026-10-05", "modes": {
            "loto": {"hypotheses": 20, "fdr_significant_train": 2,
                     "holdout_days": 12, "production_eligible_count": 1},
            "de": {"hypotheses": 10, "fdr_significant_train": 1,
                   "holdout_days": 11, "production_eligible_count": 0},
        },
    })
    values = {el["id"]: el.get_text(strip=True) for el in page.select("[data-lab-metric]")}
    assert values == {"rl-hypotheses": "30", "rl-fdr": "3", "rl-holdout": "12", "rl-eligible": "1"}
    assert "2026-10-06" in page.select_one(".rl-hero-stats").get_text()
    assert "2026-10-05" in page.select_one(".rl-overview").get_text()
    assert "LOTO" in page.select_one("#rl-holdout").parent.get_text()
    assert "chưa tự động đưa vào vận hành" in page.select_one("#rl-eligible").parent.get_text()


def test_missing_reports_are_unknown_instead_of_zero_or_live(tmp_path: Path) -> None:
    """Thiếu báo cáo không được biến thành kết luận không có tín hiệu."""
    page = _render(tmp_path, {}, {})
    assert [el.get_text(strip=True) for el in page.select("[data-lab-metric]")] == ["—"] * 4
    assert "Chưa có báo cáo" in page.select_one(".rl-overview").get_text()
    assert "LIVE AI PROCESSING" not in str(page)
    assert len(page.select(".rl-pipeline")) == 1


def test_lab_navigation_reaches_all_existing_research_tables(tmp_path: Path) -> None:
    """Menu phải dẫn đến nội dung thật, giữ đầy đủ cả các bảng ít nổi bật."""
    page = _render(tmp_path, {}, {})
    links = page.select(".rl-nav a[href^='#']")
    assert len(links) >= 5
    for link in links:
        assert page.select_one(link["href"]) is not None
    assert len(page.select(".rl-panel table")) == 10
    assert all(table.select("th[scope='col']") for table in page.select(".rl-panel table"))


def test_venue_cards_print_the_measured_reading_or_say_nothing_is_measured(tmp_path: Path) -> None:
    """Thẻ đài quay in câu kết luận và từng dãy TỪ tệp số đo; thiếu tệp thì nói chưa có, không bịa."""
    empty = _render(tmp_path / "trong", {}, {})
    assert "Chưa có số đo theo đài quay." in empty.select_one("#rl-venue").get_text()
    assert "Chưa có số đo theo đài." in empty.select_one("#rl-venue-tests").get_text()

    venue_dir = tmp_path / "co" / "data" / "stats" / "venue"
    venue_dir.mkdir(parents=True)
    (venue_dir / "xsmb_venue_effects.json").write_text(json.dumps({
        "reading": "Câu kết luận đo được 12345.",
        "cage_monitor": [{"venue": "Đài Thử", "draws": 610, "draws_per_week": 1, "p_value": 0.5, "p_holm": 0.9,
                          "detector_log10_max": 7.5, "detector_log10_threshold": 6.1,
                          "detector_alarm_on": "2024-04-20", "detector_alarm_last": "2024-11-24",
                          "detector_in_alarm": False}],
        "heterogeneity": [{"label": "số lần ra của 100 con LOTO", "grouping": "đài", "p_value": 0.004,
                           "p_holm": 0.04, "rejected": False}],
        "benchmark": {"test_draws": 730, "modes": {"loto": {"comparisons": {
            "đài": {"vs_pooled": {"z": 2.5}, "promoted": True}}}},
            "adaptive_cage": {"draws": 3908, "gated": {"z": 0.91, "promoted": False}}},
    }), encoding="utf-8")
    page = _render(tmp_path / "co", {}, {})
    monitor = page.select_one("#rl-venue")
    assert "Câu kết luận đo được 12345." in monitor.get_text()
    row = [td.get_text(strip=True) for td in monitor.select("tbody tr")[0].select("td")]
    assert row[0] == "Đài Thử" and row[-1] == "Từ 2024-04-20 tới 2024-11-24"
    tests = page.select_one("#rl-venue-tests").get_text()
    assert "z = 2.50" in tests and "z = 0.91" in tests
    assert page.select_one(".rl-nav a[href='#rl-venue']") is not None
