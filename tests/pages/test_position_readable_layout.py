"""Luồng thao tác soi cầu có nhãn rõ và tách phần kiểm chứng khỏi kết quả."""

from copy import deepcopy
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from pages import build_position_bridges as page

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def report() -> dict:
    return page.load(ROOT / "data")


def _assert_workspace(markup: str) -> None:
    soup = BeautifulSoup(markup, "html.parser")
    steps = soup.select(".app-position-steps li")
    assert len(steps) == 3
    assert [item.get_text(" ", strip=True) for item in steps] == [
        "1 Chọn điều kiện", "2 Chọn số và cầu", "3 Xem từng kỳ",
    ]
    limit = soup.select_one('input[name="limit"]')
    assert "kỳ quay" in limit.find_parent("label").get_text()
    assert limit.get("aria-describedby") == "app-bridge-period-help"
    assert "ngày lịch" in soup.select_one("#app-bridge-period-help").get_text()
    results = soup.select_one("#app-bridge-results")
    history = soup.select_one(".app-bridge-path")
    assert results and history
    disclosures = soup.select("details.app-position-disclosure")
    assert len(disclosures) == 2
    assert all(not item.has_attr("open") for item in disclosures)
    assert soup.select_one("#kiem-chung").name == "details"
    order = list(soup.find_all(["section", "details"]))
    assert order.index(results) < order.index(history) < order.index(disclosures[0])


def test_primary_workspace_precedes_closed_evidence_and_explains_draw_units(report: dict) -> None:
    _assert_workspace(page.render(report))


def test_published_page_keeps_one_compact_guide_without_a_generic_hero(
    report: dict, tmp_path: Path,
) -> None:
    """Kiểm bước xuất thật vì lớp hậu xử lý từng chèn thêm hero và hướng dẫn."""
    output = tmp_path / page.PAGE
    page.write_page(output, page.render(report))
    soup = BeautifulSoup(output.read_text(encoding="utf-8"), "html.parser")
    guides = soup.select("[data-app-workspace-guide]")
    assert len(guides) == 1
    assert "app-position-steps" in guides[0].get("class", [])
    assert soup.select_one(".app-workspace-hero, .app-workspace-guide") is None
    _assert_workspace(str(soup))


def test_layout_contract_rejects_reopened_evidence_and_missing_units(report: dict) -> None:
    markup = page.render(report)
    assert 'class="app-position-disclosure"' in markup
    with pytest.raises(AssertionError):
        _assert_workspace(markup.replace('class="app-position-disclosure"',
                                        'class="app-position-disclosure" open', 1))
    with pytest.raises(AssertionError):
        _assert_workspace(markup.replace('aria-describedby="app-bridge-period-help"', "", 1))


def test_collapsed_evidence_still_uses_the_measured_verdict(report: dict) -> None:
    changed = deepcopy(report)
    rows = changed["modes"]["lo"]["streaks"]["rows"]
    for mode in changed["modes"].values():
        for row in mode["streaks"]["rows"] + mode["consensus"]["rows"]:
            row["z"] = 0
    baseline = BeautifulSoup(page.render(changed), "html.parser").select_one("#kiem-chung").get_text()
    assert "Không hàng nào" in baseline
    rows[0]["n"], rows[0]["z"] = 1000, page.Z_ALERT + 1
    measured = BeautifulSoup(page.render(changed), "html.parser").select_one("#kiem-chung").get_text()
    assert "1 trên" in measured
    assert measured != baseline
