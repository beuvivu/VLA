from pathlib import Path

from calendar_widget import load_special_results, render_calendar
from bs4 import BeautifulSoup
from build_landing_page import _LANDING_CSS, _latest_draw
from shared_results import render_result_board


def test_special_results_preserve_zeroes_and_reject_invalid_rows(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data/xsmb.csv").write_text(
        "date,special\n2026-09-01,00001\n2026-09-02,00000\n"
        "2026-09-03,12\n2026-02-30,34567\n2026-09-04,123456\n"
        "2026-09-05,NaN\n2026-09-06,\n", encoding="utf-8"
    )
    assert load_special_results(tmp_path) == {
        "2026-09-01": "00001", "2026-09-02": "00000", "2026-09-03": "00012"
    }


def test_calendar_handles_missing_data_and_uses_safe_embedded_json(tmp_path: Path) -> None:
    assert load_special_results(tmp_path) == {}
    page = render_calendar(tmp_path)
    assert 'id="app-calendar"' in page
    assert 'id="app-calendar-data"' in page
    assert 'role="grid"' in page
    assert "Lịch vạn niên" in page
    assert "Chưa có kết quả" in page


def test_daily_ledger_board_preserves_all_prizes_and_mark_targets() -> None:
    root = Path(__file__).resolve().parents[1]
    latest = _latest_draw(root)
    result = render_result_board(latest["draw"])
    soup = BeautifulSoup(result, "html.parser")
    prizes = soup.select(".tr-number")
    assert len(prizes) == 27
    assert [p.get_text() for p in prizes] == [v for g in latest["groups"] for v in g["values"]]
    assert all(p.get("role") == "button" and p.get("aria-pressed") == "false" for p in prizes)
    assert soup.select_one(".tr-special-tail") is not None
    assert soup.select_one(".tr-loto") is None
    assert "min-width: 520px" not in _LANDING_CSS
