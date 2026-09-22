"""Dock phải dùng được bằng ngón tay, không chỉ bằng con trỏ chuột.

Dock từng CHẾT HẲN trên điện thoại: menu con mở ra nhưng không ô nào nhận
được cú chạm. Đo bằng Chromium ở chế độ cảm ứng, 390px: 0/9 liên kết chạm
được, trong khi máy bàn 9/9. Ba nguyên nhân độc lập, tệp này khoá cả ba lại.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

#: MỌI trang đã xuất bản. Không lọc theo "trang nào có dock": lọc như thế thì
#: phép kiểm tự định nghĩa phạm vi của mình, và một trang đánh rơi dock sẽ
#: lặng lẽ rơi khỏi danh sách thay vì làm phép kiểm đỏ.
DOCK_PAGES = sorted(DOCS.glob("*.html"))

#: Ngưỡng màn hẹp của bản thiết kế.
MOBILE_AT = "@media (max-width:640px){"

#: Dải mà dock chiếm ở đáy màn hình: `bottom:24px` cộng chiều cao 54px. Bất kỳ
#: phần tử nổi nào rơi vào dải này đều đè lên nút dock.
DOCK_BAND_PX = 78

#: `z-index` của dock. Phần tử nổi từ mức này trở lên sẽ chặn cú chạm.
DOCK_Z = 60


def _norm(css: str) -> str:
    """Nén khoảng trắng nhưng GIỮ khoảng trắng bên trong giá trị.

    Cách nén thô ``replace(" ", "")`` biến ``flex:1 1 0`` thành ``flex:110``,
    nên mọi khẳng định về giá trị nhiều thành phần đều phải viết dưới dạng đã
    méo — một cái bẫy đọc không ra. Ở đây chỉ bỏ khoảng trắng QUANH dấu phân
    cách, phần còn lại giữ nguyên.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    return re.sub(r"\s*([{};:,])\s*", r"\1", css).strip()


def _css(path: Path) -> str:
    """CSS thực sự áp lên trang: thẻ ``<style>`` cộng biểu định kiểu liên kết.

    Trang chủ nhúng thẳng CSS; các trang khung chung liên kết tới
    ``assets/ui.css``. Đọc thiếu một nguồn là test bỏ sót cả một họ trang.
    """
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    parts = [tag.get_text() for tag in soup.find_all("style")]
    for link in soup.find_all("link", rel="stylesheet"):
        sheet = path.parent / (link.get("href") or "")
        if sheet.suffix == ".css" and sheet.exists():
            parts.append(sheet.read_text(encoding="utf-8"))
    return _norm("\n".join(parts))


def _mobile_css(css: str) -> str:
    """Nối thân của MỌI khối ``@media (max-width:640px)``.

    Phải khớp ngoặc chứ không cắt tới ``}`` đầu tiên: thân khối chứa hàng chục
    quy tắc, cắt sớm sẽ nhìn nhầm quy tắc khác là quy tắc của dock.
    """
    bodies: list[str] = []
    start = 0
    while (i := css.find(MOBILE_AT, start)) >= 0:
        j = i + len(MOBILE_AT)
        depth = 1
        while depth and j < len(css):
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        bodies.append(css[i + len(MOBILE_AT) : j - 1])
        start = j
    return "".join(bodies)


def _rules(block: str, wanted: str) -> list[tuple[str, str]]:
    """Các cặp (bộ chọn, thân) trong ``block`` có bộ chọn chứa ``wanted``."""
    found = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", block):
        selector = match.group(1)
        if wanted in selector:
            found.append((selector, match.group(2)))
    return found


def _bodies(block: str, *selectors: str) -> list[str]:
    """Thân của các quy tắc có bộ chọn ĐÚNG BẰNG một trong ``selectors``."""
    return [body for sel, body in _rules(block, "dock") if sel in selectors]


def _has_class(selector: str, name: str) -> bool:
    """Bộ chọn có mang ĐÚNG lớp ``name`` hay không.

    Không dùng ``in`` được: ``".ui-js" in ".ui-js-x ..."`` là đúng, nên một
    bộ chọn đã đổi tên vẫn lọt qua. Đây là đúng con đột biến đã sống sót ở
    lần chạy đầu — test báo xanh trong khi quy tắc không còn khớp gì cả.
    """
    return re.search(rf"\.{re.escape(name)}(?![\w-])", selector) is not None


def test_every_published_page_carries_the_dock() -> None:
    """Dock là điều hướng CHÍNH của cả trang, nên trang nào thiếu là ngõ cụt.

    Bốn trang từng thiếu: ``live.html`` (viết tay, không builder nào sinh ra),
    ``statistics.html`` (có điều hướng riêng), và hai trang ML mở bằng khung
    không dock. Cả bốn đều là ĐÍCH ĐẾN trong :data:`SITE_NAV` — vào được mà
    không có lối ra nào ngoài nút Back.
    """
    missing = [
        page.name
        for page in DOCK_PAGES
        if not BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser").select(".ui-dock, .dock")
    ]
    assert not missing, f"thiếu dock: {missing}"


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_dock_bar_is_not_a_scroll_box_on_narrow_screens(page: Path) -> None:
    """Nguyên nhân gốc: dải dock từng mang ``overflow-x:auto`` ở màn hẹp.

    Một hộp cuộn CẮT mọi hậu duệ nằm ngoài nó. Dải dock chỉ cao 54px còn menu
    con bung LÊN phía trên, nên menu bị xén sạch — đo được menu ở y 623..751
    trong khi dải ở y 766..820, và ``elementFromPoint`` giữa menu trả về nội
    dung trang chứ không phải liên kết.

    ``position:fixed`` không cứu được: dải dock có ``backdrop-filter``, mà
    backdrop-filter biến phần tử thành khối chứa cho cả hậu duệ ``fixed``.
    """
    block = _mobile_css(_css(page))
    for selector, body in _rules(block, "dock-inner"):
        assert "overflow" not in body, f"{page.name}: {selector}{{{body}}}"


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_dock_groups_share_the_width_instead_of_scrolling(page: Path) -> None:
    """Bỏ cuộn ngang thì N nhóm phải tự co lại cho vừa bề ngang.

    Đo ở 320px — màn hẹp nhất còn dùng thật — icon còn 33x40px, vẫn bấm được.
    """
    block = _mobile_css(_css(page))
    bodies = _bodies(block, ".ui-dock-group", ".dock-group")
    assert bodies, f"{page.name}: không có quy tắc nhóm nào ở màn hẹp"
    assert any("flex:1 1 0" in body for body in bodies), f"{page.name}: {bodies}"


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_submenu_is_anchored_to_the_whole_bar_on_narrow_screens(page: Path) -> None:
    """Menu rộng cố định canh giữa theo NÚT thì các nhóm hai đầu đẩy nó ra
    ngoài viền: 390px hỏng 3/7 nhóm, 360px hỏng 4/7.

    Neo vào cả dải dock thì menu rộng đúng bằng dock, mà dock đã nằm trọn
    trong màn hình.
    """
    block = _mobile_css(_css(page))
    groups = _bodies(block, ".ui-dock-group", ".dock-group")
    assert any("position:static" in body for body in groups), f"{page.name}: {groups}"
    pops = _bodies(block, ".ui-dock-pop", ".dock-pop")
    assert pops, f"{page.name}: không có quy tắc menu con nào ở màn hẹp"
    assert any("left:0" in body and "right:0" in body for body in pops), f"{page.name}: {pops}"


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_touch_gets_an_explicit_switch(page: Path) -> None:
    """Màn cảm ứng KHÔNG CÓ ``:hover``, còn ``:focus-within`` thì mở được mà
    không đóng được: chạm lần hai chẳng đổi gì vì nút vẫn đang giữ focus.

    Nên phải có một công tắc tường minh, và nút phải báo trạng thái của nó.
    """
    soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
    buttons = soup.select(".ui-dock-btn, .dock-btn")
    assert buttons, f"{page.name}: không tìm thấy nút dock nào"
    for button in buttons:
        assert button.get("aria-expanded") == "false", f"{page.name}: {button}"

    switch = [s.get_text() for s in soup.find_all("script") if "ui-open" in s.get_text()]
    assert switch, f"{page.name}: thiếu kịch bản công tắc"
    body = switch[0]
    assert 'classList.toggle("ui-open"' in body, page.name
    assert 'addEventListener("click"' in body, page.name
    assert 'setAttribute("aria-expanded"' in body, page.name


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_the_switch_is_the_only_opener_once_javascript_runs(page: Path) -> None:
    """Nếu ``:focus-within`` vẫn còn hiệu lực ở màn hẹp thì cú chạm thứ hai
    không đóng được menu: nút vẫn giữ focus nên menu mở mãi.

    Chỉ tắt khi CÓ JavaScript (lớp ``ui-js``); không có JavaScript thì hành vi
    cũ vẫn còn, tốt hơn là chẳng còn gì.
    """
    block = _mobile_css(_css(page))
    silenced = [
        body
        for sel, body in _rules(block, "dock-pop")
        if _has_class(sel, "ui-js") and ":focus-within" in sel
    ]
    assert silenced, f"{page.name}: ``:focus-within`` vẫn mở menu ở màn hẹp"
    assert all("visibility:hidden" in body for body in silenced), f"{page.name}: {silenced}"

    opened = [body for sel, body in _rules(block, "dock-pop") if _has_class(sel, "ui-open")]
    assert opened, f"{page.name}: không có quy tắc nào mở menu bằng công tắc"
    assert any("visibility:visible" in body for body in opened), f"{page.name}: {opened}"


@pytest.mark.parametrize("page", DOCK_PAGES, ids=lambda p: p.name)
def test_no_floating_element_covers_the_dock(page: Path) -> None:
    """Một "viên thuốc" nổi ``right:16px;bottom:16px;z-index:9999`` từng đè
    đúng lên nút nhóm cuối cùng.

    Máy bàn không thấy vì dock canh giữa màn rộng; điện thoại thì dock căng
    hết bề ngang nên hai thứ chồng lên nhau, và trình duyệt từ chối cú chạm
    với lý do "intercepts pointer events".
    """
    soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
    for element in soup.select("[style]"):
        style = (element.get("style") or "").replace(" ", "")
        if "position:fixed" not in style:
            continue
        bottom = re.search(r"bottom:(\d+)px", style)
        z_index = re.search(r"z-index:(\d+)", style)
        if not bottom or int(bottom.group(1)) >= DOCK_BAND_PX:
            continue
        if z_index and int(z_index.group(1)) >= DOCK_Z:
            pytest.fail(f"{page.name}: {element.get('id') or element.name} đè lên dock — {style}")
