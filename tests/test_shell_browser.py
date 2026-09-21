from __future__ import annotations

"""Kiểm khung ứng dụng trong TRÌNH DUYỆT THẬT, ở bảy viewport của spec.

Mục X nói thẳng: "do not rely on CSS media queries alone". Một quy tắc
``@media`` đọc đúng vẫn có thể cho ra trang tràn ngang, drawer che nội dung,
hay cái nút không bấm được. Tệp này mở trang bằng Chromium và ĐO.

Mục XVI cũng nói "a screenshot alone is not proof that a page works", nên ở
đây không có phép kiểm nào chỉ chụp ảnh: mỗi phép kiểm đo một đại lượng hoặc
thực hiện một tương tác rồi kiểm hệ quả của nó.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PREVIEW = ROOT / "docs" / "_shell-preview.html"

#: Bảy viewport mục X đòi.
VIEWPORTS: tuple[tuple[str, int, int], ...] = (
    ("small-mobile", 320, 720),
    ("mobile", 375, 812),
    ("large-mobile", 430, 932),
    ("tablet", 768, 1024),
    ("small-laptop", 1024, 768),
    ("desktop", 1440, 900),
    ("large-desktop", 1920, 1080),
)

CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def _have_browser() -> bool:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return Path(CHROMIUM).exists()


pytestmark = pytest.mark.skipif(
    not _have_browser(), reason="cần Playwright và Chromium tại /opt/pw-browsers"
)


def _ensure_preview() -> None:
    if not PREVIEW.exists():
        subprocess.run(
            [sys.executable, str(SRC / "build_shell_preview.py")],
            check=True,
            cwd=ROOT,
            env={"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin"},
            capture_output=True,
        )


def _probe(script: str, *, width: int, height: int, theme: str = "light") -> dict:
    """Mở trang xem thử rồi chạy ``script`` trong đó, trả về kết quả JSON.

    Gom mọi phép đo của một viewport vào MỘT lần mở trang: khởi động Chromium
    mất khoảng một giây, và mở lại cho từng phép đo sẽ biến tệp này thành phần
    chậm nhất của cả bộ kiểm.

    ``script`` được phép trả về Promise, và đó là điều KHÔNG tuỳ chọn với các
    phép đo sau một tương tác. Bản đầu của tệp này đo ngay sau ``click()``
    trong khi transition 120-180ms còn đang chạy, nên nó báo drawer "không mở"
    và liên kết bỏ qua "vẫn ẩn" — cả hai đều SAI, lỗi nằm ở phép kiểm chứ
    không ở trang. Dùng ``waitTransition`` trong script để chờ đúng chỗ.
    """
    _ensure_preview()
    runner = f"""
import json, sys
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path={CHROMIUM!r}, args=["--no-sandbox"])
    context = browser.new_context(
        viewport={{"width": {width}, "height": {height}}},
        color_scheme={theme!r},
    )
    page = context.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    failed = []
    page.on("requestfailed", lambda r: failed.append(r.url))
    page.goto({PREVIEW.as_uri()!r}, wait_until="load")
    helper = \"\"\"
      const waitTransition = (ms) => new Promise(resolve => setTimeout(resolve, ms));
    \"\"\"
    result = page.evaluate("async () => {{" + helper + \"\"\"{script}\"\"\" + "}}")
    result["console_errors"] = errors
    result["failed_requests"] = failed
    browser.close()
    print("<<<JSON>>>" + json.dumps(result))
"""
    completed = subprocess.run(
        [sys.executable, "-c", runner],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=ROOT,
        check=False,
    )
    assert "<<<JSON>>>" in completed.stdout, (
        f"probe thất bại:\nstdout={completed.stdout[-2000:]}\nstderr={completed.stderr[-2000:]}"
    )
    return json.loads(completed.stdout.split("<<<JSON>>>", 1)[1])


@pytest.mark.parametrize(("name", "width", "height"), VIEWPORTS, ids=[v[0] for v in VIEWPORTS])
def test_no_viewport_makes_the_page_overflow_horizontally(name: str, width: int, height: int) -> None:
    """Trang KHÔNG được tràn ngang, dù bảng bên trong có cuộn ngang.

    Đây là phân biệt cốt lõi của mục X: cuộn trong khung bảng là có chủ đích,
    trang tràn ngang là lỗi. Trang xem thử cố tình chứa một bảng 24 cột rộng
    hơn mọi màn hình, nên phép kiểm này thật sự có thể đỏ.
    """
    data = _probe(
        """
        const doc = document.documentElement;
        const scroller = document.querySelector('.vla-table-scroll');
        const overflowX = scroller ? getComputedStyle(scroller).overflowX : '';
        return {
          docScrollWidth: doc.scrollWidth,
          docClientWidth: doc.clientWidth,
          contentWider: scroller ? scroller.scrollWidth > scroller.clientWidth + 1 : false,
          overflowX,
          // Cuộn THẬT: đặt scrollLeft rồi đọc lại. `scrollWidth > clientWidth`
          // một mình là điều kiện quá lỏng — nó vẫn đúng khi `overflow` là
          // `visible`, tức nội dung rộng hơn nhưng KHÔNG cuộn được.
          canActuallyScroll: (() => {
            if (!scroller) { return false; }
            scroller.scrollLeft = 120;
            const moved = scroller.scrollLeft > 0;
            scroller.scrollLeft = 0;
            return moved;
          })(),
        };
        """,
        width=width,
        height=height,
    )
    assert data["docScrollWidth"] <= data["docClientWidth"] + 1, (
        f"{name}: trang tràn ngang {data['docScrollWidth']}px > {data['docClientWidth']}px"
    )
    assert data["contentWider"], (
        f"{name}: bảng 24 cột không rộng hơn khung — bảng bị bóp lại, "
        "làm mất chính khả năng so sánh mà trang tồn tại để phục vụ"
    )
    assert data["overflowX"] in {"auto", "scroll"}, (
        f"{name}: khung bảng có overflow-x={data['overflowX']!r} — nội dung rộng "
        "hơn khung mà không cuộn được thì phần bên phải là không thể đọc tới"
    )
    assert data["canActuallyScroll"], (
        f"{name}: đặt scrollLeft không có tác dụng — khung không cuộn thật"
    )
    assert not data["console_errors"], f"{name}: lỗi console {data['console_errors']}"
    assert not data["failed_requests"], f"{name}: tài nguyên lỗi {data['failed_requests']}"


@pytest.mark.parametrize(("name", "width", "height"), VIEWPORTS, ids=[v[0] for v in VIEWPORTS])
def test_navigation_is_reachable_at_every_viewport(name: str, width: int, height: int) -> None:
    """Điều hướng phải tới được ở MỌI kích thước, bằng chuột hoặc bàn phím.

    Dưới 1024px sidebar nằm ngoài màn hình, nên phải có nút mở nó THẤY ĐƯỢC.
    Từ 1024px sidebar cố định, nên nút ấy phải ẩn đi — hai nút điều hướng cùng
    hiện là hai đường làm một việc.
    """
    data = _probe(
        """
        const toggle = document.querySelector('[data-vla-nav-toggle]');
        const sidebar = document.getElementById('vla-sidebar');
        const box = sidebar.getBoundingClientRect();
        const style = getComputedStyle(toggle);
        return {
          toggleVisible: style.display !== 'none' && toggle.offsetParent !== null,
          sidebarOnScreen: box.left >= -1 && box.right <= window.innerWidth + 1,
          navLinks: document.querySelectorAll('.vla-nav-link').length,
          openGroups: document.querySelectorAll('.vla-nav-group[open]').length,
          currentMarked: document.querySelectorAll('.vla-nav-link[aria-current="page"]').length,
        };
        """,
        width=width,
        height=height,
    )
    assert data["navLinks"] == 27, f"{name}: sidebar có {data['navLinks']} liên kết, cần 27"
    assert data["currentMarked"] == 1, (
        f"{name}: {data['currentMarked']} mục mang aria-current — phải đúng một"
    )
    assert data["openGroups"] == 1, (
        f"{name}: {data['openGroups']} nhóm mở sẵn — nhóm chứa trang đang mở phải mở, các nhóm khác đóng"
    )
    if width < 1024:
        assert data["toggleVisible"], f"{name}: không có nút mở điều hướng"
        assert not data["sidebarOnScreen"], (
            f"{name}: sidebar chiếm màn hình khi chưa mở — mục X cấm điều hướng che nội dung"
        )
    else:
        assert not data["toggleVisible"], f"{name}: nút ba gạch còn hiện dù sidebar đã cố định"
        assert data["sidebarOnScreen"], f"{name}: sidebar phải hiện cố định từ 1024px"


def test_the_mobile_drawer_opens_traps_focus_and_closes_on_escape() -> None:
    """Drawer phải mở, giữ focus bên trong, và đóng bằng Esc.

    Ba thứ đi liền nhau. Thiếu vòng focus thì Tab thoát ra vùng đang bị nền mờ
    che — con trỏ ở chỗ không thấy được, lỗi nặng hơn cả không có drawer.
    Thiếu Esc thì người dùng bàn phím không có đường đóng nó.
    """
    data = _probe(
        """
        const toggle = document.querySelector('[data-vla-nav-toggle]');
        const sidebar = document.getElementById('vla-sidebar');
        const main = document.getElementById('vla-main');
        const before = sidebar.getBoundingClientRect().left;
        toggle.click();
        await waitTransition(320);
        const afterOpen = {
          left: sidebar.getBoundingClientRect().left,
          expanded: toggle.getAttribute('aria-expanded'),
          mainInert: main.hasAttribute('inert'),
          bodyLocked: document.body.style.overflow === 'hidden',
          focusInside: sidebar.contains(document.activeElement),
          backdropOpen: document.getElementById('vla-backdrop').getAttribute('data-open'),
        };
        document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
        await waitTransition(320);
        return {
          before,
          afterOpen,
          closedLeft: sidebar.getBoundingClientRect().left,
          closedExpanded: toggle.getAttribute('aria-expanded'),
          mainInertAfterClose: main.hasAttribute('inert'),
          bodyLockedAfterClose: document.body.style.overflow === 'hidden',
        };
        """,
        width=375,
        height=812,
    )
    assert data["before"] < 0, "sidebar phải nằm ngoài màn hình khi chưa mở"
    opened = data["afterOpen"]
    assert opened["left"] >= -1, "drawer không mở ra"
    assert opened["expanded"] == "true", "aria-expanded không đổi khi mở"
    assert opened["backdropOpen"] == "true", "nền mờ không hiện"
    assert opened["mainInert"], "nội dung phía sau không được đặt inert — Tab lọt ra vùng bị che"
    assert opened["bodyLocked"], "trang phía sau vẫn cuộn được khi drawer mở"
    assert opened["focusInside"], "focus không chuyển vào drawer khi mở"

    assert data["closedLeft"] < 0, "Esc không đóng drawer"
    assert data["closedExpanded"] == "false", "aria-expanded không trả về false"
    assert not data["mainInertAfterClose"], "inert không được nhả sau khi đóng"
    assert not data["bodyLockedAfterClose"], "khoá cuộn không được nhả sau khi đóng"


def test_the_theme_button_cycles_three_states_and_actually_repaints() -> None:
    """Nút chủ đề phải xoay ba trạng thái VÀ thật sự đổi màu đã vẽ.

    Đổi thuộc tính mà màu không đổi là cái nút vô nghĩa, nên ở đây đo
    ``getComputedStyle`` của ``body`` chứ không chỉ đọc ``data-theme``. Đó là
    khác biệt giữa "thuộc tính đã đổi" và "người đọc thấy khác".
    """
    data = _probe(
        """
        const button = document.querySelector('[data-vla-theme-toggle]');
        const root = document.documentElement;
        const bg = () => getComputedStyle(document.body).backgroundColor;
        const snap = () => ({
          state: root.getAttribute('data-theme-state'),
          theme: root.getAttribute('data-theme'),
          bg: bg(),
          live: (document.getElementById('vla-theme-live') || {}).textContent || '',
        });
        const seen = [snap()];
        for (let i = 0; i < 3; i += 1) { button.click(); seen.push(snap()); }
        const labels = Array.from(document.querySelectorAll('.vla-theme-label'))
          .filter(node => getComputedStyle(node).display !== 'none').length;
        return {seen, visibleLabels: labels};
        """,
        width=1440,
        height=900,
        theme="light",
    )
    states = [snap["state"] for snap in data["seen"]]
    assert states == ["system", "light", "dark", "system"], f"chuỗi trạng thái sai: {states}"

    system, light, dark = data["seen"][0], data["seen"][1], data["seen"][2]
    assert system["theme"] is None, (
        "trạng thái 'theo hệ thống' KHÔNG được đặt data-theme — đặt nó là ghi đè "
        "prefers-color-scheme, tức mất luôn khả năng theo hệ điều hành"
    )
    assert light["theme"] == "light" and dark["theme"] == "dark"
    assert light["bg"] != dark["bg"], (
        f"màu nền không đổi giữa sáng và tối ({light['bg']}) — thuộc tính đổi mà trang không đổi"
    )
    assert data["visibleLabels"] == 1, (
        f"{data['visibleLabels']} nhãn chủ đề cùng hiện — phải đúng một"
    )
    assert "tối" in dark["live"], f"vùng aria-live không thông báo chủ đề: {dark['live']!r}"


def test_the_system_theme_state_follows_the_operating_system() -> None:
    """Ở trạng thái 'theo hệ thống', máy đặt tối thì trang phải tối.

    Đây là tầng ``@media (prefers-color-scheme: dark)``. Không có nó, trạng
    thái 'theo hệ thống' luôn ra trang sáng — tức nó không theo gì cả.
    """
    light = _probe(
        "return {bg: getComputedStyle(document.body).backgroundColor};",
        width=1440,
        height=900,
        theme="light",
    )
    dark = _probe(
        "return {bg: getComputedStyle(document.body).backgroundColor};",
        width=1440,
        height=900,
        theme="dark",
    )
    assert light["bg"] != dark["bg"], (
        f"chủ đề hệ điều hành không ảnh hưởng gì ({light['bg']}) — "
        "tầng prefers-color-scheme không hoạt động"
    )


def test_the_skip_link_is_the_first_thing_a_keyboard_reaches() -> None:
    """Phím Tab đầu tiên phải gặp liên kết bỏ qua điều hướng.

    Với 27 liên kết trong sidebar, không có nó thì người dùng bàn phím phải Tab
    qua toàn bộ điều hướng trên MỌI trang mới tới được nội dung.
    """
    data = _probe(
        """
        const link = document.querySelector('.vla-skip-link');
        link.focus();
        await waitTransition(260);
        const box = link.getBoundingClientRect();
        return {
          isFirstTabbable: document.querySelector('a[href], button') === link,
          href: link.getAttribute('href'),
          visibleWhenFocused: box.top >= 0,
          targetExists: !!document.querySelector(link.getAttribute('href')),
        };
        """,
        width=1440,
        height=900,
    )
    assert data["isFirstTabbable"], "liên kết bỏ qua không phải phần tử bấm được đầu tiên"
    assert data["href"] == "#vla-content"
    assert data["visibleWhenFocused"], "liên kết bỏ qua vẫn ẩn khi được focus"
    assert data["targetExists"], "đích của liên kết bỏ qua không tồn tại"


def test_no_interactive_control_is_smaller_than_the_touch_target() -> None:
    """Mọi nút phải đạt vùng chạm 40px trên điện thoại.

    Nút chỉ có icon là chỗ thường bị bóp nhỏ, vì nó trông cân đối ở 28px.
    """
    data = _probe(
        """
        const nodes = Array.from(document.querySelectorAll('button, .vla-nav-link'));
        const small = nodes
          .filter(n => n.offsetParent !== null)
          .map(n => ({tag: n.className, w: n.getBoundingClientRect().width, h: n.getBoundingClientRect().height}))
          .filter(m => m.h < 40 - 0.5);
        return {small, total: nodes.length};
        """,
        width=375,
        height=812,
    )
    assert not data["small"], f"vùng chạm dưới 40px: {data['small']}"


@pytest.mark.parametrize(("name", "width", "height"), VIEWPORTS, ids=[v[0] for v in VIEWPORTS])
def test_a_kpi_number_never_wraps_and_the_row_keeps_one_height(name: str, width: int, height: int) -> None:
    """Số KPI phải nằm MỘT dòng, và cả hàng thẻ phải cùng một chiều cao.

    Hai điều này là một: con số xuống dòng làm thẻ ấy cao hơn các thẻ bên
    cạnh, và mục 5.2 cấm chiều cao lệch trong cùng nhóm thị giác.

    Phép kiểm này đã bắt được một lỗi thật ở ĐÚNG 1024px: lưới KPI bật bốn cột
    từ 1024px, nhưng sidebar ăn 264px nên mỗi thẻ còn 159px và "2026-09-21" ở
    2rem xuống hai dòng — chiều cao nhảy 143px lên 181px. Đã chuyển mốc bốn
    cột lên 1280px.

    ĐẾM SỐ DÒNG, không đo chiều rộng. Lượt đo đầu của tôi kiểm ``scrollWidth``
    và báo "không tràn" nên tôi tưởng ổn — con số không tràn ngang vì nó xuống
    dòng được. Đo sai đại lượng thì kết luận đúng cũng là tình cờ.
    """
    data = _probe(
        """
        const values = Array.from(document.querySelectorAll('.vla-kpi-value'));
        const wrapped = values
          .filter(v => v.getBoundingClientRect().height / parseFloat(getComputedStyle(v).lineHeight) > 1.5)
          .map(v => v.textContent.trim());
        const heights = Array.from(document.querySelectorAll('.vla-kpi-grid .vla-card'))
          .map(c => Math.round(c.getBoundingClientRect().height));
        return {count: values.length, wrapped, heights: Array.from(new Set(heights))};
        """,
        width=width,
        height=height,
    )
    assert data["count"] == 4, f"{name}: thấy {data['count']} thẻ KPI, cần 4"
    assert not data["wrapped"], f"{name}: số KPI xuống dòng: {data['wrapped']}"
    assert len(data["heights"]) == 1, (
        f"{name}: các thẻ KPI cao khác nhau {data['heights']} — mục 5.2 cấm chiều cao "
        "lệch trong cùng nhóm thị giác"
    )


def test_the_topbar_does_not_repeat_the_page_title() -> None:
    """Đầu trang dính nói NHÓM, không nhắc lại tiêu đề ngay bên dưới.

    Đo trên ảnh chụp 375px: lặp tiêu đề ăn 64px chiều cao của màn 812px để
    hiện đúng thứ nằm cách đó 40px. Trên điện thoại sidebar đóng nên tên nhóm
    là thông tin duy nhất nói người đọc đang ở nhánh nào.
    """
    data = _probe(
        """
        const bar = document.querySelector('.vla-topbar-context').textContent.trim();
        const title = document.querySelector('.vla-page-title').textContent.trim();
        const current = document.querySelector('.vla-nav-link[aria-current="page"]');
        const group = current.closest('.vla-nav-group').querySelector('.vla-nav-group-label').textContent.trim();
        return {bar, title, group};
        """,
        width=375,
        height=812,
    )
    assert data["bar"] != data["title"], (
        f"đầu trang lặp lại tiêu đề {data['title']!r}"
    )
    assert data["bar"] == data["group"], (
        f"đầu trang ghi {data['bar']!r} nhưng nhóm đang mở là {data['group']!r}"
    )


def test_nothing_overlaps_the_sticky_topbar_content() -> None:
    """Đầu trang dính không được che tiêu đề hay hàng thẻ đầu tiên.

    Đây là lỗi kinh điển của topbar ``position: sticky``: nó nằm trên nội dung
    và ăn mất hàng đầu khi cuộn về đầu trang.
    """
    data = _probe(
        """
        const bar = document.querySelector('.vla-topbar').getBoundingClientRect();
        const title = document.querySelector('.vla-page-title').getBoundingClientRect();
        const firstCard = document.querySelector('.vla-card').getBoundingClientRect();
        return {barBottom: bar.bottom, titleTop: title.top, cardTop: firstCard.top};
        """,
        width=1440,
        height=900,
    )
    assert data["titleTop"] >= data["barBottom"] - 1, (
        f"đầu trang dính che tiêu đề (bar {data['barBottom']} > title {data['titleTop']})"
    )
    assert data["cardTop"] >= data["barBottom"] - 1, "đầu trang dính che thẻ đầu tiên"
