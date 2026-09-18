"""The output boundary must preserve behavior while publishing the shared skin."""

from pathlib import Path

from bs4 import BeautifulSoup

from page_output import write_page


def test_output_publishes_skin_after_page_styles_without_changing_hooks(tmp_path: Path) -> None:
    page = tmp_path / "example.html"
    source = '''<!doctype html><html><head><link rel="stylesheet" href="assets/ui.css">
    <style>.card{background:red}</style></head><body class="existing">
    <button id="filter" class="chip on" data-range="30">30 kỳ</button>
    <script>document.querySelector('#filter').onclick=()=>{location.hash='30';};</script>
    </body></html>'''
    write_page(page, source)
    result = BeautifulSoup(page.read_text(), "html.parser")
    skin = result.head.find_all(["link", "style"])[-1]
    assert skin.name == "link"
    assert (tmp_path / skin["href"]).is_file()
    assert result.body["class"] == ["existing"]
    assert result.button.attrs == BeautifulSoup(source, "html.parser").button.attrs
    assert result.script.string == BeautifulSoup(source, "html.parser").script.string
    once = page.read_text()
    write_page(page, once)
    assert page.read_text() == once


def test_every_published_page_receives_same_skin(tmp_path: Path) -> None:
    docs = Path(__file__).resolve().parents[1] / "docs"
    for original in sorted(docs.glob("*.html")):
        target = tmp_path / original.name
        write_page(target, original.read_text())
        result = BeautifulSoup(target.read_text(), "html.parser")
        links = result.select('link[data-ui-visual-system]')
        assert len(links) == 1, original.name
        assert (tmp_path / links[0]["href"]).is_file(), original.name


def test_html_fragment_is_not_given_a_broken_stylesheet_link(tmp_path: Path) -> None:
    target = tmp_path / "fragment.html"
    write_page(target, '<div id="fragment">nội dung</div>')
    assert target.read_text() == '<div id="fragment">nội dung</div>'
    assert not (tmp_path / "assets").exists()
