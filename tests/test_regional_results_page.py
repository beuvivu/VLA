from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from build_regional_results import render


ROOT = Path(__file__).resolve().parents[1]
PRIZES = {
    "ĐB": ("Đặc Biệt", ["030118"]),
    "G.1": ("Giải Nhất", ["00019"]),
    "G.2": ("Giải Nhì", ["00120"]),
    "G.3": ("Giải Ba", ["00021", "00122"]),
    "G.4": ("Giải Tư", ["00023", "00024", "00025", "00026", "00027", "00028", "00029"]),
    "G.5": ("Giải Năm", ["0030"]),
    "G.6": ("Giải Sáu", ["0031", "0032", "0033"]),
    "G.7": ("Giải Bảy", ["034"]),
    "G.8": ("Giải Tám", ["05"]),
}
OTHER_PRIZES = {
    "ĐB": ["040118"], "G.1": ["10019"], "G.2": ["10120"],
    "G.3": ["10021", "10122"],
    "G.4": ["10023", "10024", "10025", "10026", "10027", "10028", "10029"],
    "G.5": ["1030"], "G.6": ["1031", "1032", "1033"], "G.7": ["134"], "G.8": ["15"],
}


def sample_rows() -> list[dict[str, str]]:
    """Hai đài cùng ngày và một ngày thiếu đài, có đủ mọi độ dài giải."""
    rows = []
    for prize, (_, values) in PRIZES.items():
        for index, value in enumerate(values):
            rows.extend((
                {"date": "2026-10-05", "province": "Huế", "prize": prize, "value": value, "position": str(index + 1)},
                {"date": "2026-10-05", "province": "Thừa Thiên Huế", "prize": prize,
                 "value": OTHER_PRIZES[prize][index], "position": str(index + 1)},
            ))
    rows.append({"date": "2026-10-04", "province": "Thừa Thiên Huế", "prize": "ĐB", "value": "050118", "position": "1"})
    return rows


def test_regional_pages_render_without_seed_data():
    for region, label in (("mt", "XSMT"), ("mn", "XSMN")):
        page = render(region, [])
        assert label in page
        assert "Chưa có dữ liệu đã lưu." in page
        assert 'id="rg-data"' in page
        assert "json.dumps" not in page


def test_regional_pages_offer_every_saved_date_and_station_in_the_filters():
    """Bỏ một ngày hoặc đài khỏi bộ chọn sẽ khiến dữ liệu ấy không tra được."""
    soup = BeautifulSoup(render("mt", sample_rows()), "html.parser")
    assert [node.get("value") for node in soup.select("#rg-date option")] == ["", "2026-10-05", "2026-10-04"]
    assert [node.get("value") for node in soup.select("#rg-province option")] == ["", "Huế", "Thừa Thiên Huế"]


def test_regional_pages_never_name_where_the_data_comes_from():
    """Luật riêng tư của kho: không vẽ danh tính nguồn dữ liệu ra trình duyệt."""
    from sources import REGIONAL_SOURCE_NAMES

    row = {"date": "2026-10-05", "province": "Cà Mau", "prize": "ĐB", "value": "030118"}
    for region in ("mt", "mn"):
        for rows in ([], [row]):
            page = render(region, rows)
            for name in REGIONAL_SOURCE_NAMES:
                assert name not in page
            assert "vla" not in page.lower().replace("vietlott", "")


@pytest.mark.parametrize("region", ["mt", "mn"])
def test_each_province_and_prize_keeps_all_original_digits(region: str) -> None:
    """Cắt Đặc Biệt còn 5 số, ép integer hay trộn hai cột đều làm đỏ."""
    soup = BeautifulSoup(render(region, sample_rows()), "html.parser")
    table = soup.select_one('.rg-draw[data-date="2026-10-05"] table')
    assert table is not None
    headers = table.select("thead th")
    assert [node.get_text(strip=True) for node in headers] == ["Giải", "Huế", "Thừa Thiên Huế"]
    prize_rows = table.select("tbody tr")
    assert len(prize_rows) == 9
    for row, (prize, (label, values)) in zip(prize_rows, PRIZES.items(), strict=True):
        cells = row.find_all("td", recursive=False)
        assert len(cells) == 2
        assert [node.get_text() for node in cells[0].select(".tr-number")] == values
        assert [node.get_text() for node in cells[1].select(".tr-number")] == OTHER_PRIZES[prize]
        prize_header = row.find("th")
        assert prize_header.get("scope") == "row"
        assert prize_header.get_text(strip=True) == label
        for header, cell in zip(headers[1:], cells, strict=True):
            assert cell.get("headers") == [prize_header["id"], header["id"]]
    assert all(node.get("scope") == "col" for node in headers)
    assert len(soup.select(".rg-draw .tr-number")) == 37
    assert len({node["data-cell"] for node in soup.select(".rg-draw .tr-number")}) == 37
    earlier = soup.select_one('.rg-draw[data-date="2026-10-04"] table')
    assert [node.get_text() for node in earlier.select(".tr-number")] == ["050118"]
    assert len(earlier.select(".rg-missing")) == 8


@pytest.mark.parametrize("region", ["mt", "mn"])
def test_accessible_number_names_keep_the_full_result_and_draw_context(region: str) -> None:
    """Đọc riêng 2 số cuối làm người dùng bàn phím mất số gốc và đài quay."""
    soup = BeautifulSoup(render(region, sample_rows()), "html.parser")
    rows = soup.select('.rg-draw[data-date="2026-10-05"] tbody tr')
    for row, (prize, (label, values)) in zip(rows, PRIZES.items(), strict=True):
        cells = row.find_all("td", recursive=False)
        for province, cell, expected in (("Huế", cells[0], values), ("Thừa Thiên Huế", cells[1], OTHER_PRIZES[prize])):
            for node, value in zip(cell.select(".tr-number"), expected, strict=True):
                accessible_name = node.get("aria-label", "")
                for context in (value, label, province, "05/10/2026"):
                    assert context in accessible_name
    earlier = soup.select_one('.rg-draw[data-date="2026-10-04"] .tr-number')
    for context in ("050118", "Đặc Biệt", "Thừa Thiên Huế", "04/10/2026"):
        assert context in earlier.get("aria-label", "")


@pytest.fixture(scope="module")
def regional_browser_effects() -> dict:
    """Chạy bộ lọc và đánh dấu thật trên DOM, không thay bằng bộ giả."""
    node = os.environ.get("CODEX_PRIMARY_RUNTIME_NODE") or shutil.which("node")
    if not node or not (ROOT / "tests/frontend/node_modules/jsdom").exists():
        pytest.skip("Cần Node và npm ci --prefix tests/frontend để kiểm hành vi DOM")
    script = r"""
import fs from 'node:fs';
import { JSDOM } from 'jsdom';
const dom = new JSDOM(fs.readFileSync(0, 'utf8'), { url: 'https://example.test/', runScripts: 'outside-only' });
const d = dom.window.document;
const values = () => [...d.querySelectorAll('.rg-draw .tr-number')].map(n => n.textContent);
const before = values();
for (const s of d.querySelectorAll('script:not([src])')) {
  if (s.type !== 'application/json') dom.window.eval(s.textContent);
}
const after = values();
const first = d.querySelector('.rg-draw .tr-number');
const marked = () => [...d.querySelectorAll('.tr-number[data-marked]')].map(n => n.textContent);
const stages = {};
first?.click(); stages.click = marked();
stages.pressed = first?.getAttribute('aria-pressed');
if (first) first.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
stages.enter = marked();
const space = new dom.window.KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true });
first?.dispatchEvent(space); stages.space = marked(); stages.spacePrevented = space.defaultPrevented;
d.getElementById('rg-mark-clear')?.click(); stages.clear = marked();
const pair = d.getElementById('rg-pair-mode');
if (pair) { pair.checked = true; pair.dispatchEvent(new dom.window.Event('change')); }
first?.click(); stages.pair = marked();
const province = d.getElementById('rg-province'), date = d.getElementById('rg-date');
province.value = 'Huế'; province.dispatchEvent(new dom.window.Event('change'));
const visibleDates = () => [...d.querySelectorAll('.rg-draw')].filter(n => !n.hidden).map(n => n.dataset.date);
stages.provinceDates = visibleDates();
const current = d.querySelector('.rg-draw[data-date="2026-10-05"]');
stages.provinceColumns = [...current.querySelectorAll('thead th')].slice(1).filter(n => !n.hidden).map(n => n.textContent);
stages.provinceSpecials = [...current.querySelectorAll('tbody tr:first-child td')].filter(n => !n.hidden).map(n => n.textContent);
date.value = '2026-10-04'; date.dispatchEvent(new dom.window.Event('change'));
stages.emptyDates = visibleDates(); stages.emptyVisible = d.getElementById('rg-filter-empty')?.hidden === false;
d.getElementById('rg-reset').click(); stages.resetDates = visibleDates();
stages.resetColumns = [...current.querySelectorAll('thead th')].slice(1).filter(n => !n.hidden).map(n => n.textContent);
stages.afterReset = values();
d.getElementById('rg-mark-clear')?.click(); stages.clearAfterFilter = marked();
console.log(JSON.stringify({ before, after, ...stages }));
dom.window.close();
"""
    result = subprocess.run(
        [node, "--input-type=module", "-e", script], input=render("mt", sample_rows()),
        cwd=ROOT / "tests/frontend", check=True, capture_output=True, text=True, timeout=15,
    )
    return json.loads(result.stdout)


def test_marks_use_the_same_click_keyboard_and_pair_rules_as_the_northern_board(regional_browser_effects) -> None:
    """Thiếu bộ đánh dấu hoặc bỏ tỉnh khỏi khóa ô sẽ làm sáng sai số."""
    effects = regional_browser_effects
    assert effects["click"] == ["030118"]
    assert effects["pressed"] == "true"
    assert effects["enter"] == []
    assert effects["space"] == ["030118"]
    assert effects["spacePrevented"] is True
    assert effects["clear"] == []
    assert effects["pair"] == ["030118", "040118", "050118"]
    assert effects["clearAfterFilter"] == []


def test_province_filter_hides_only_other_stations_and_keeps_saved_digits(regional_browser_effects) -> None:
    """Tìm chuỗi trong cả thẻ sẽ lẫn Huế với Thừa Thiên Huế, không lọc cột."""
    effects = regional_browser_effects
    assert effects["provinceDates"] == ["2026-10-05"]
    assert effects["provinceColumns"] == ["Huế"]
    assert effects["provinceSpecials"] == ["030118"]
    assert effects["emptyDates"] == []
    assert effects["emptyVisible"] is True
    assert effects["resetDates"] == ["2026-10-05", "2026-10-04"]
    assert effects["resetColumns"] == ["Huế", "Thừa Thiên Huế"]
    assert effects["before"] == effects["after"] == effects["afterReset"]
    assert len(effects["afterReset"]) == 37


def test_a4_pdf_keeps_every_full_result_from_all_four_stations(tmp_path: Path) -> None:
    """Giữ min-width/overflow của màn hình khi in sẽ cắt số ở đài cuối."""
    playwright = pytest.importorskip("playwright.sync_api")
    fitz = pytest.importorskip("fitz")
    from page_output import write_page

    with (ROOT / "data/regions/xsmn.csv").open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["date"] == "2026-10-03"]
    assert len(rows) == 72
    assert len({row["province"] for row in rows}) == 4
    assets = tmp_path / "assets"
    assets.mkdir()
    shutil.copyfile(ROOT / "docs/assets/ui.css", assets / "ui.css")
    target = tmp_path / "ket-qua-mien-nam.html"
    write_page(target, render("mn", rows))
    with playwright.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except playwright.Error as error:
            if "Executable doesn't exist" in str(error):
                pytest.skip("Cần playwright install chromium để đối chiếu PDF")
            raise
        page = browser.new_page(viewport={"width": 794, "height": 1123})
        page.goto(target.as_uri(), wait_until="networkidle")
        pdf = page.pdf(format="A4", margin={side: "10mm" for side in ("top", "right", "bottom", "left")}, print_background=True)
        browser.close()
    printed = []
    with fitz.open(stream=pdf, filetype="pdf") as document:
        for sheet in document:
            for block in sheet.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = "".join(span["text"] for span in line["spans"]).replace(" ", "")
                    if re.fullmatch(r"\d{2,6}", text):
                        printed.append(text)
    assert Counter(printed) == Counter(row["value"] for row in rows)
