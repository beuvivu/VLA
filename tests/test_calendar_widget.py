from pathlib import Path

from calendar_widget import load_special_results, render_calendar
from build_landing_page import _LANDING_CSS, _latest_draw, _render_result_table


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


def test_compact_draw_preserves_all_prizes_and_click_targets() -> None:
    root = Path(__file__).resolve().parents[1]
    latest = _latest_draw(root)
    result = _render_result_table(latest)
    assert "app-prize-table" in result
    assert result.count("data-number=") == 27
    for group in latest["groups"]:
        for value in group["values"]:
            assert f"aria-label='{group['label']} {value}. Xem LOTO {value[-2:]}'" in result
    assert "app-special-tail" in result
    assert "min-width: 520px" not in _LANDING_CSS
