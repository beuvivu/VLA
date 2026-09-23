"""Khung ứng dụng phải dùng được bằng ngón tay, và không trang nào đánh rơi nó.

Tệp này thay ``test_dock_on_mobile.py``. Dock nổi ở chân trang đã được khung
hai cấp thay thế, nên những phép kiểm cũ soi một thành phần không còn tồn tại
— và một phép kiểm quét qua tập rỗng là phép kiểm không thể đỏ. Các BÀI HỌC
thì vẫn nguyên giá trị nên chúng được chuyển sang đây:

* điều hướng phải chạm được bằng ngón tay ở 390px, không chỉ bằng con trỏ;
* không phần tử nổi nào được che điều khiển điều hướng;
* mọi trang xuất bản phải có điều hướng, không trang nào rơi khỏi danh sách.

Thêm vào đó là các bất biến ĐO ĐƯỢC của trang tham chiếu mà bản dựng này phải
giữ: dải chi tiết PHỦ LÊN nội dung chứ không đẩy nó.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT / "src"))

#: MỌI trang đã xuất bản. Không lọc theo "trang nào có khung": lọc như thế thì
#: phép kiểm tự định nghĩa phạm vi của mình, và một trang đánh rơi khung sẽ
#: lặng lẽ rơi khỏi danh sách thay vì làm phép kiểm đỏ.
PAGES = sorted(DOCS.glob("*.html"))

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def test_the_published_tree_holds_at_least_one_page() -> None:
    """Chốt chặn cho mọi phép kiểm chạy theo tham số ở tệp này."""
    assert PAGES, "docs/ không có trang nào — các phép kiểm dưới sẽ quét tập rỗng"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_published_page_carries_the_shell(page: Path) -> None:
    """Không trang nào được đánh rơi khung dùng chung."""
    text = page.read_text(encoding="utf-8")
    for dau in ('class="app-rail"', 'class="app-panel"', 'class="app-header"',
                'class="app-main"', 'id="app-toggle"'):
        assert dau in text, f"{page.name} thiếu {dau}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_published_page_carries_the_shell_twice(page: Path) -> None:
    """Khung phải có ĐÚNG MỘT lớp, không phải "ít nhất một".

    Phép kiểm trên chỉ đòi khung CÓ MẶT, nên nó xanh y nguyên khi trang mang
    hai khung lồng nhau. Đã xảy ra thật với ``docs/live.html`` — trang duy
    nhất viết tay và commit thẳng, nên mỗi lượt dựng đọc lại chính bản đã có
    khung. Hệ quả nhìn thấy được, đo bằng ``elementFromPoint``: chữ thương
    hiệu của khung NGOÀI nằm đúng trên nút tab đầu của dải TRONG, nên mục
    điều hướng đầu tiên bấm không ăn.

    Đếm từng dấu một chứ không đếm mỗi ``app-rail``: khung có thể nhân đôi
    lệch nhau — bản hỏng của ``live.html`` có hai ``</main>`` nhưng chỉ một
    thẻ kịch bản, vì lượt chuẩn hoá gộp hai thẻ ``src`` trùng nhau lại.
    """
    text = page.read_text(encoding="utf-8")
    for dau in ('class="app-rail"', 'class="app-panel"', 'class="app-header"',
                'class="app-main"', 'id="app-toggle"'):
        assert text.count(dau) == 1, (
            f"{page.name} có {text.count(dau)} lần {dau}, phải đúng 1"
        )


def test_wrapping_a_page_twice_gives_the_same_page() -> None:
    """Bọc khung phải LUỸ ĐẲNG, và phải SỬA được trang đã bọc chồng.

    Ghim chính LUẬT trên dữ liệu dựng sẵn, không dựa vào việc quét
    ``docs/``: nếu một ngày nào đó không trang nào hỏng thì phép kiểm trên
    vẫn xanh dù ``wrap_page`` đã hỏng hẳn. Ở đây trang hỏng được DỰNG RA.
    """
    from app_shell import wrap_page

    goc = "<html><head></head><body><p>Nội dung thật</p></body></html>"
    mot = wrap_page(goc, "index.html")
    assert mot.count('class="app-rail"') == 1
    assert "<p>Nội dung thật</p>" in mot

    # Bọc lại bản đã bọc: phải cho ra ĐÚNG bản cũ, không dày thêm một lớp.
    assert wrap_page(mot, "index.html") == mot

    # Trang đã bọc chồng phải được SỬA, không phải được để yên.
    #
    # Dựng đúng hình dạng đã xảy ra: khung LỒNG NHAU, tức lớp ngoài chứa trọn
    # lớp trong. Hai khung cạnh nhau là một hình dạng khác và chưa từng xảy
    # ra — dựng nhầm nó thì phép kiểm đo một thứ không có thật.
    from app_shell import header_html, panel_html, rail_html

    than = mot.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    long_nhau = (
        rail_html("index.html")
        + panel_html("index.html")
        + '<div class="app-scrim" id="app-scrim" hidden></div>'
        + header_html("index.html")
        + '<main class="app-main" id="app-main">'
        + than
        + "</main>"
        + '<script src="assets/app-shell.js" defer></script>'
    )
    assert long_nhau.count('class="app-rail"') == 2, "mẫu dựng sẵn phải thật sự hỏng"

    sua = wrap_page("<html><head></head><body>" + long_nhau + "</body></html>", "index.html")
    assert sua.count('class="app-rail"') == 1, "trang bọc chồng phải được bóc về một lớp"
    assert "<p>Nội dung thật</p>" in sua, "bóc khung không được đánh rơi nội dung"

    # Và hình dạng mà `docs/live.html` thật sự mang: khung trong MẤT thẻ kịch
    # bản, vì lượt chuẩn hoá gộp hai thẻ `src` trùng nhau lại làm một.
    mat_script = long_nhau.replace(
        '<script src="assets/app-shell.js" defer></script>', "", 1
    )
    sua2 = wrap_page("<html><head></head><body>" + mat_script + "</body></html>", "index.html")
    assert sua2.count('class="app-rail"') == 1, "thiếu thẻ kịch bản vẫn phải bóc được"
    assert "<p>Nội dung thật</p>" in sua2


def test_the_rail_has_one_button_per_navigation_group() -> None:
    """Dải biểu tượng phải phủ đúng các nhóm của mô hình điều hướng.

    Ghim vào chính ``SITE_NAV`` chứ không vào một con số viết tay: thêm nhóm
    mà quên dựng nút thì phép kiểm đỏ, và đổi số nhóm không làm nó đỏ oan.
    """
    from ui_theme import SITE_NAV

    text = (DOCS / "statistics.html").read_text(encoding="utf-8")
    assert text.count('class="app-rail-btn"') == len(SITE_NAV)


def test_every_navigation_target_is_a_real_page() -> None:
    """Không liên kết chết trong điều hướng."""
    from ui_theme import SITE_NAV

    thieu = [
        href
        for _, muc in SITE_NAV
        for href, _, _ in muc
        if not (DOCS / href.split("#", 1)[0]).is_file()
    ]
    assert not thieu, f"điều hướng trỏ tới trang không có: {thieu}"


@pytest.fixture(scope="module")
def trinh_duyet():
    playwright = pytest.importorskip("playwright.sync_api")
    if not Path(CHROME).exists():
        pytest.skip("không có Chromium ở đường dẫn đã ghim")
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        yield b
        b.close()


def _mo(trinh_duyet, w: int, h: int, cam_ung: bool = False):
    return trinh_duyet.new_page(
        viewport={"width": w, "height": h},
        has_touch=cam_ung,
        is_mobile=cam_ung,
    )


def test_the_detail_panel_overlays_the_content_instead_of_pushing_it(trinh_duyet) -> None:
    """Mở dải chi tiết KHÔNG được làm nội dung xếp lại.

    Đây là hành vi đo được của trang tham chiếu: ``margin-left`` của vùng nội
    dung giữ nguyên ở cả hai trạng thái. Nếu dải đẩy nội dung thì mỗi lần mở
    menu là cả một bảng số phải dàn lại — thứ khó đọc nhất có thể làm với một
    trang phân tích.
    """
    pg = _mo(trinh_duyet, 1440, 900)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    truoc = pg.evaluate("() => getComputedStyle(document.querySelector('.app-main')).marginLeft")
    pg.click("#app-toggle")
    pg.wait_for_timeout(500)
    sau = pg.evaluate("() => getComputedStyle(document.querySelector('.app-main')).marginLeft")
    mo = pg.evaluate("() => document.body.classList.contains('app-panel-open')")
    pg.close()
    assert mo, "bấm nút mà dải chi tiết không mở"
    assert truoc == sau, f"nội dung bị đẩy: {truoc} -> {sau}"


def test_the_toggle_stays_clickable_while_the_panel_is_open(trinh_duyet) -> None:
    """Mở rồi phải đóng lại được.

    Dải chi tiết từng có ``z-index`` cao hơn thanh trên: nó phủ lên chính nút
    đã mở nó, nên mở ra là không còn đường đóng.
    """
    pg = _mo(trinh_duyet, 1440, 900)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    pg.click("#app-toggle")
    pg.wait_for_timeout(500)
    tren_cung = pg.evaluate(
        """() => {
          const t = document.getElementById('app-toggle');
          const r = t.getBoundingClientRect();
          const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return t === el || t.contains(el);
        }"""
    )
    pg.click("#app-toggle")
    pg.wait_for_timeout(400)
    dong = pg.evaluate("() => !document.body.classList.contains('app-panel-open')")
    pg.close()
    assert tren_cung, "nút thu/mở bị dải chi tiết che"
    assert dong, "bấm lần hai không đóng được"


def test_touch_can_reach_every_navigation_link_on_a_phone(trinh_duyet) -> None:
    """Bài học của dock cũ, chuyển sang khung mới.

    Dock từng CHẾT HẲN trên điện thoại: menu mở ra nhưng không ô nào nhận được
    cú chạm — đo được 0/9 liên kết chạm được ở 390px trong khi máy bàn 9/9.
    """
    pg = _mo(trinh_duyet, 390, 844, cam_ung=True)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    pg.tap("#app-toggle")
    pg.wait_for_timeout(600)
    do = pg.evaluate(
        """() => {
          const items = [...document.querySelectorAll('.app-panel-group:not([hidden]) .app-nav-item')];
          let cham = 0;
          for (const a of items) {
            const r = a.getBoundingClientRect();
            if (r.width < 4 || r.height < 4) continue;
            const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            if (a === el || a.contains(el)) cham += 1;
          }
          return {tong: items.length, cham: cham};
        }"""
    )
    pg.close()
    assert do["tong"] >= 3, f"chỉ thấy {do['tong']} liên kết — menu chưa mở?"
    assert do["cham"] == do["tong"], f"chỉ {do['cham']}/{do['tong']} liên kết chạm được"


def test_no_floating_element_covers_the_navigation_controls(trinh_duyet) -> None:
    """Không phần tử nổi nào được đè lên thanh trên hay dải biểu tượng."""
    pg = _mo(trinh_duyet, 1440, 900)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    che = pg.evaluate(
        """() => {
          const diem = [];
          const h = document.querySelector('.app-header').getBoundingClientRect();
          diem.push([h.left + 40, h.top + h.height / 2]);
          const r = document.querySelector('.app-rail').getBoundingClientRect();
          diem.push([r.left + r.width / 2, r.top + 150]);
          const xau = [];
          for (const [x, y] of diem) {
            const el = document.elementFromPoint(x, y);
            if (!el) { xau.push('không có phần tử'); continue; }
            if (!el.closest('.app-header, .app-rail, .app-panel')) {
              xau.push(el.tagName + '.' + (el.className || '').toString().slice(0, 40));
            }
          }
          return xau;
        }"""
    )
    pg.close()
    assert not che, f"phần tử nổi che điều hướng: {che}"


def test_the_theme_button_cycles_three_states_and_remembers(trinh_duyet) -> None:
    """Ba trạng thái, và "theo hệ" KHÔNG được đặt thuộc tính chủ đề.

    Đặt ``data-ui-theme`` cho trạng thái "theo hệ" là đè mất
    ``prefers-color-scheme``: người dùng mất luôn khả năng đi theo cài đặt máy.
    """
    pg = _mo(trinh_duyet, 1440, 900)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    thay = []
    for _ in range(4):
        thay.append(pg.evaluate("() => document.documentElement.getAttribute('data-ui-theme')"))
        pg.click("#app-theme")
        pg.wait_for_timeout(250)
    luu = pg.evaluate("() => localStorage.getItem('app-theme')")
    pg.close()
    assert thay[0] is None, "trạng thái đầu phải là theo hệ, không đặt thuộc tính"
    assert thay[1:4] == ["light", "dark", None], f"vòng chuyển sai: {thay}"
    assert luu in {"auto", "light", "dark"}, f"không ghi nhớ lựa chọn: {luu!r}"


def test_the_search_only_offers_pages_that_exist(trinh_duyet) -> None:
    """Ô tìm không được nhận chữ rồi trả về thứ không dẫn tới đâu."""
    pg = _mo(trinh_duyet, 1440, 900)
    pg.goto(f"file://{DOCS / 'statistics.html'}", wait_until="load")
    pg.wait_for_timeout(500)
    pg.click("#app-toggle")
    pg.wait_for_timeout(400)
    pg.fill("#app-search", "tần suất")
    pg.wait_for_timeout(400)
    href = pg.evaluate(
        """() => [...document.querySelectorAll('.app-nav-item')]
               .filter(a => a.offsetParent !== null)
               .map(a => a.getAttribute('href'))"""
    )
    trong = pg.evaluate("""() => { document.getElementById('app-search').value='zzzz';
        document.getElementById('app-search').dispatchEvent(new Event('input'));
        return document.getElementById('app-search-empty').hidden; }""")
    pg.close()
    assert href, "tìm 'tần suất' không ra kết quả nào"
    thieu = [h for h in href if not (DOCS / h.split("#", 1)[0]).is_file()]
    assert not thieu, f"kết quả tìm trỏ tới trang không có: {thieu}"
    assert trong is False, "không khớp gì mà vẫn không báo cho người dùng"
