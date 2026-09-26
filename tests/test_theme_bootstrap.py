"""Khôi phục chủ đề trước khung vẽ đầu tiên, không nhân script khi xuất lại."""

from pathlib import Path

from bs4 import BeautifulSoup

from page_output import write_page


def test_theme_script_is_local_synchronous_and_precedes_styles(tmp_path: Path) -> None:
    page = tmp_path / "example.html"
    source = ('<!doctype html><html><head><meta charset="utf-8">'
              '<meta http-equiv="Content-Security-Policy" content="script-src \'self\'">'
              '<style>body{margin:0}</style></head><body><p>07</p></body></html>')
    write_page(page, source)
    once = page.read_text()
    soup = BeautifulSoup(once, "html.parser")
    script = soup.select_one('head script[src="assets/app-theme.js"]')
    assert script is not None
    assert not script.has_attr("defer") and not script.has_attr("async")
    assert once.index('Content-Security-Policy') < once.index('src="assets/app-theme.js"')
    assert once.index('src="assets/app-theme.js"') < once.index('<style')
    assert (tmp_path / "assets/app-theme.js").read_text() == (
        Path(__file__).resolve().parents[1] / "src/assets/app-theme.js"
    ).read_text()
    write_page(page, once)
    assert page.read_text() == once


def test_critical_styles_have_matching_light_and_dark_tokens() -> None:
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("critical_extractor", root / "scripts/extract_critical_css.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    css = (':root{--ui-bg:#ffffff;--ui-ink:#111111;--ui-surface:#eeeeee;}'
           ':root.dark,:root[data-ui-theme="dark"]{--ui-bg:#121418;--ui-ink:#eeeeee;--ui-surface:#222222;}'
           '@media(prefers-color-scheme:dark){:root:not([data-ui-theme="light"]){'
           '--ui-bg:#121418;--ui-ink:#eeeeee;--ui-surface:#222222;}}'
           '.ui-card{background:var(--ui-surface);color:var(--ui-ink)}')
    actual = module.extract(css)
    assert ':root.dark' in actual
    assert 'prefers-color-scheme:dark' in actual
    assert actual.count('--ui-bg:#121418') == 2
    assert 'color-scheme:dark' in actual
