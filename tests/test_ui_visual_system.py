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
    # Soi trong VÙNG NỘI DUNG, không soi cả tài liệu. Khung ứng dụng chèn nút
    # và kịch bản của chính nó vào trước nội dung trang, nên ``result.button``
    # trả về nút của khung: phép kiểm đỏ trong khi cái nó đặt tên — móc nối của
    # trang không đổi — vẫn đúng nguyên.
    noi_dung = result.select_one(".app-main") or result
    goc = BeautifulSoup(source, "html.parser")
    assert noi_dung.button.attrs == goc.button.attrs
    assert noi_dung.script.string == goc.script.string
    once = page.read_text()
    write_page(page, once)
    assert page.read_text() == once


def test_every_published_page_receives_same_skin(tmp_path: Path) -> None:
    docs = Path(__file__).resolve().parents[1] / "docs"
    for original in sorted(docs.glob("*.html")):
        target = tmp_path / original.name
        write_page(target, original.read_text())
        result = BeautifulSoup(target.read_text(), "html.parser")
        links = result.select("link[data-ui-visual-system]")
        # Một trang nhận ĐÚNG hai thẻ: thẻ tải không chặn, và bản dự phòng
        # trong <noscript> cho trình duyệt tắt JavaScript. Đếm gộp rồi đòi
        # bằng 1 là đếm sai thứ có thật — phép kiểm đỏ với một trang hoàn toàn
        # đúng, và đồng thời không thấy trường hợp thật sự hỏng: một thẻ tải
        # bị nhân đôi vẫn cho tổng bằng 2.
        direct = [link for link in links if link.find_parent("noscript") is None]
        fallback = [link for link in links if link.find_parent("noscript") is not None]
        assert len(direct) == 1, f"{original.name}: {len(direct)} thẻ tải"
        assert len(fallback) == 1, f"{original.name}: {len(fallback)} bản dự phòng"
        for link in links:
            assert (tmp_path / link["href"]).is_file(), original.name


def test_html_fragment_is_not_given_a_broken_stylesheet_link(tmp_path: Path) -> None:
    target = tmp_path / "fragment.html"
    write_page(target, '<div id="fragment">nội dung</div>')
    assert target.read_text() == '<div id="fragment">nội dung</div>'
    assert not (tmp_path / "assets").exists()
