"""Giữ bất biến dữ liệu và khả năng dựng lại khi thay hệ thống trình bày."""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from build_landing_page import build_landing_page
from page_output import write_page


def test_effect_toggle_does_not_pause_functional_updates() -> None:
    """Live reveal bắt đầu opacity 0; pause toàn trang sẽ giữ số mới vô hình."""
    css = (Path(__file__).resolve().parents[1] / "src/templates/app_design.css").read_text()
    pause_rules = [selectors for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]+)\}", css)
                   if re.search(r"animation-play-state\s*:\s*paused", declarations)]
    assert pause_rules
    for selectors in pause_rules:
        assert "*" not in selectors, "Tắt trang trí không được đóng băng animation của dữ liệu thật"
        assert ".slot" not in selectors


def test_design_assets_are_local_and_follow_existing_shell(tmp_path: Path) -> None:
    page = tmp_path / "statistics.html"
    write_page(page, '<html><head></head><body><button id="filter">Lọc</button></body></html>')
    doc = BeautifulSoup(page.read_text(), "html.parser")
    assert doc.body.get("data-app-design") == "crafto"
    links = [link["href"] for link in doc.select("head > link[rel=stylesheet]")]
    assert links[-1] == "assets/app-design.css"
    assert links.index("assets/app-shell.css") < links.index("assets/app-design.css")
    assert (tmp_path / links[-1]).is_file()
    script = doc.select_one('head script[src="assets/app-motion.js"]')
    assert script and script.has_attr("defer")
    assert (tmp_path / script["src"]).is_file()
    assert doc.select_one("#filter").text == "Lọc"


def test_design_republication_is_idempotent_and_preserves_payload(tmp_path: Path) -> None:
    page = tmp_path / "index.html"
    payload = {"number": "07", "rate": 0.17}
    source = ('<html><head></head><body><section id="ket-qua">'
              '<button data-number="07">07</button></section>'
              f'<script type="application/json" id="landing-data">{json.dumps(payload)}</script>'
              '</body></html>')
    write_page(page, source)
    first = page.read_text()
    write_page(page, first)
    second = page.read_text()
    assert second == first
    doc = BeautifulSoup(second, "html.parser")
    assert len(doc.select("[data-app-effects]")) == 1
    assert len(doc.select(".app-main")) == 1
    assert len(doc.select(".app-header")) == 1
    assert json.loads(doc.select_one("#landing-data").text) == payload
    assert doc.select_one('[data-number="07"]').text == "07"
    assert doc.select_one(".app-ambience")["aria-hidden"] == "true"
    toggle = doc.select_one("#app-motion-toggle")
    assert toggle.name == "button" and toggle.get("type") == "button"


def test_landing_hero_uses_actual_data_and_keeps_analysis_sections(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    build_landing_page(repo_root=root, docs_dir=tmp_path)
    doc = BeautifulSoup((tmp_path / "index.html").read_text(), "html.parser")
    hero = doc.select_one("#tong-quan")
    assert hero.select_one(".app-hero-visual") is not None
    special_tile = next(t for t in doc.select(".metric-tile") if t.span.text == "Đặc Biệt")
    assert hero.select_one(".app-hero-number").text == special_tile.strong.text
    assert "Vietnam Lottery Analysis" in hero.select_one(".app-marquee").text
    assert hero.select_one(".app-marquee")["aria-hidden"] == "true"
    assert doc.select_one("#ket-qua table")
    assert doc.select_one("#landing-data")
    assert len(hero.select("h1")) == 1
    for link in hero.select("a[href^='#']"):
        assert doc.find(id=link["href"][1:]), link["href"]
