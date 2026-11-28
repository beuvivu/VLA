from __future__ import annotations

import re
from pathlib import Path

import pytest

from privacy_helpers import LEAK_TOKENS

ROOT = Path(__file__).resolve().parents[2]
PAGES = sorted((ROOT / "docs").glob("*.html"))

SHEETS = sorted((ROOT / "docs").rglob("*.css"))

_SCRIPT = re.compile(r'<script(?![^>]*application/json)[^>]*>(.*?)</script>', re.S | re.I)
_STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)


def _without_strings(code: str) -> str:
    code = re.sub(r"'(?:[^'\\\n]|\\.)*'", "''", code)
    code = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', code)
    return re.sub(r"`(?:[^`\\]|\\.)*`", "``", code)


def _without_literals(code: str) -> str:
    return re.sub(r"/(?![*/])(?:[^/\\\n\[]|\\.|\[(?:[^\]\\]|\\.)*\])+/[a-z]*",
                  "/re/", _without_strings(code))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_comment_survives_into_a_published_page(page: Path) -> None:
    html = page.read_text(encoding="utf-8", errors="replace")
    outside = _SCRIPT.sub("", _STYLE.sub("", html))
    assert not re.findall(r"<!--(?!\[if).*?-->", outside, flags=re.S), page.name
    for body in _STYLE.findall(html):
        assert "/*" not in _without_strings(body), page.name
    for body in _SCRIPT.findall(html):
        code = _without_literals(body)
        assert "/*" not in code, page.name
        assert not [ln for ln in code.splitlines() if ln.lstrip().startswith("//")], page.name


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_page_spells_out_where_the_data_lives(page: Path) -> None:
    html = page.read_text(encoding="utf-8", errors="replace")
    body = re.sub(r"<meta[^>]+Content-Security-Policy[^>]*>", "", html, flags=re.I)
    for token in LEAK_TOKENS:
        assert token not in body, f"{page.name} lộ {token!r}"


INTERNAL_WORDS = ("rawdata",)


def _internal_words(text: str) -> list[str]:
    return [word for word in INTERNAL_WORDS if word in text.lower()]


def test_the_internal_word_rule_catches_the_old_reason() -> None:
    assert _internal_words("Lý do chính: ML xác suất cao + cầu RawData mạnh") == ["rawdata"]
    assert _internal_words("Lý do chính: nhiều cặp vị trí ghép ra số") == []
    assert len(PAGES) >= 40


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_page_shows_an_internal_variable_name(page: Path) -> None:
    assert not _internal_words(page.read_text(encoding="utf-8", errors="replace")), page.name


@pytest.mark.parametrize("sheet", SHEETS, ids=lambda p: p.name)
def test_no_comment_survives_into_a_published_stylesheet(sheet: Path) -> None:
    assert "/*" not in _without_strings(sheet.read_text(encoding="utf-8", errors="replace")), sheet.name


@pytest.mark.parametrize("sheet", SHEETS, ids=lambda p: p.name)
def test_no_stylesheet_spells_out_where_the_data_lives(sheet: Path) -> None:
    body = sheet.read_text(encoding="utf-8", errors="replace")
    for token in LEAK_TOKENS:
        assert token not in body, f"{sheet.name} lộ {token!r}"


def test_the_only_place_a_real_host_may_appear_is_the_policy_header() -> None:
    offenders = []
    for page in PAGES:
        html = page.read_text(encoding="utf-8", errors="replace")
        for meta in re.findall(r"<meta[^>]+Content-Security-Policy[^>]*>", html, flags=re.I):
            if "connect-src" not in meta:
                offenders.append(page.name)
    assert not offenders, offenders
