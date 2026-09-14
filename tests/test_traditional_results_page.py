"""Trang Sổ kết quả: schema nhúng, bộ lọc, xuất file và giao diện."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from bs4 import BeautifulSoup

from build_traditional_results import _draw, embedded_payload, load_draws, render_page
from ui_theme import nav_targets

ROOT = Path(__file__).resolve().parents[1]


def test_embedded_schema_preserves_widths_and_head_tail_counts() -> None:
    draws = load_draws(ROOT, limit=2)
    assert len(draws) == 2
    with (ROOT / "data" / "xsmb.csv").open() as stream:
        latest = max(csv.DictReader(stream), key=lambda row: row["date"])
    assert draws[0]["draw_date"] == latest["date"][:10]
    assert draws[0]["prizes"][0]["values"] == [latest["special"].zfill(5)]
    assert all(len(value) == prize["width"] for prize in draws[0]["prizes"] for value in prize["values"])
    assert sum(len(values) for values in draws[0]["head_tail"]["heads"].values()) == 27
    assert sum(len(values) for values in draws[0]["head_tail"]["tails"].values()) == 27


def test_page_contains_requested_filters_exports_and_safe_worker_csp() -> None:
    payload = embedded_payload(load_draws(ROOT, limit=3), generated="2026-09-13T13:00:00Z")
    html = render_page(payload)
    soup = BeautifulSoup(html, "html.parser")

    assert soup.select_one("#tr-province option[value=hanoi]").get_text(strip=True) == "Miền Bắc / Hà Nội"
    assert [option.get("value") for option in soup.select("#tr-period option")] == [
        "30", "60", "90", "100", "custom",
    ]
    assert soup.select_one("#tr-from[type=date]")
    assert soup.select_one("#tr-to[type=date]")
    assert soup.select_one("#tr-export-csv")
    assert soup.select_one("#tr-export-xlsx")
    csp = soup.select_one('meta[http-equiv="Content-Security-Policy"]')["content"]
    assert "connect-src 'self' https://*.workers.dev" in csp
    assert "window.VLA_RESULTS_API_URL = '';" in html


def test_page_javascript_highlights_special_tail_and_builds_real_xlsx() -> None:
    script = (ROOT / "src" / "templates" / "traditional_results.js").read_text(encoding="utf-8")
    assert '"tr-special-tail"' in script
    assert "0x04034b50" in script, "Excel phải là gói ZIP OOXML, không phải CSV đổi đuôi"
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in script
    assert "replaceChildren" in script
    assert ".innerHTML" not in script, "không đưa payload mạng vào innerHTML"


def test_generated_page_is_in_navigation_and_exists() -> None:
    assert "so-ket-qua-truyen-thong.html" in nav_targets()
    page = ROOT / "docs" / "so-ket-qua-truyen-thong.html"
    assert page.is_file() and page.stat().st_size > 100_000


def test_builder_output_is_deterministic_for_a_fixed_timestamp() -> None:
    payload = embedded_payload(load_draws(ROOT, limit=5), generated="2026-09-13T13:00:00Z")
    assert render_page(payload) == render_page(payload)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_incomplete_draw_is_not_fabricated_as_zero(value) -> None:
    with (ROOT / "data" / "xsmb.csv").open() as stream:
        row = next(csv.DictReader(stream))
    row["prize7_1"] = value
    assert _draw(row) is None
