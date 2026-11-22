"""Điều khiển của trang trên điện thoại, đo trong Chromium thật.

Hai lỗi tìm thấy khi rà 50 trang ngày 21-11-2026, cả hai chỉ thấy được bằng bố cục thật:

* Ô chọn cắt chữ của chính lựa chọn: «Từ độ dài này trở lên» (soi cầu vị trí, 390–412px), «Tất cả ngày
  đang hiển thị» (kết quả miền, 412–430px), «Gan nhiều nhất» và «Tất cả các thứ» (tần suất, 320–360px).
  Mỗi trang có ngưỡng một cột riêng, đặt hẹp hơn chỗ chữ cần.
* Nút «Hiệu ứng» ghim ``position: fixed`` ở góc phải dưới, che chữ của bảng và đoạn văn khi cuộn.

Chạy trong job trình duyệt của CI với ``UI_BROWSER_REQUIRED=1``; nơi khác thiếu Chromium thì bỏ qua.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
#: Khổ màn hình điện thoại phổ biến, từ máy nhỏ nhất còn dùng tới máy lớn.
PHONE_WIDTHS = (320, 360, 390, 412, 430)
#: Trang đại diện cho bốn kiểu khung: trang chủ, công cụ soi cầu, Vietlott, bảng thống kê.
TOGGLE_PAGES = ("index.html", "soi-cau-vi-tri.html", "vietlott-keno.html", "tan-suat-loto.html")

#: Bề rộng cần lấy từ CHÍNH Chromium: bản sao của ô chọn đặt cạnh ô gốc (cùng bộ chọn CSS, cùng phông, lề và
#: mũi tên của theme), bề rộng ``max-content`` = chữ của lựa chọn dài nhất + lề + mũi tên. Ô gốc hẹp hơn bản sao
#: là cắt chữ. Đừng ước lượng mũi tên bằng một hằng số: 20px rộng hơn mũi tên thật 1px, và trên runner CI (không
#: có phông Inter) hai ô tự co giãn theo nội dung ở bảng Đặc Biệt tháng/năm bị báo nhầm như thế.
_CLIPPED_SELECTS = """() => {
  const out = [];
  for (const s of document.querySelectorAll('select')) {
    if (!s.offsetParent) continue;
    const twin = s.cloneNode(true);
    twin.removeAttribute('id');
    twin.removeAttribute('name');
    for (const [k, v] of [['position', 'absolute'], ['visibility', 'hidden'], ['width', 'max-content'],
                          ['min-width', '0'], ['max-width', 'none'], ['left', '0'], ['top', '0']]) {
      twin.style.setProperty(k, v, 'important');
    }
    s.after(twin);
    const need = twin.getBoundingClientRect().width;
    twin.remove();
    const have = s.getBoundingClientRect().width;
    if (have + 0.5 < need) {
      const longest = [...s.options].map(o => o.textContent.trim()).sort((a, b) => b.length - a.length)[0];
      out.push(`${s.id || s.name}: «${longest}» cần ${Math.ceil(need)}px, có ${Math.floor(have)}px`);
    }
  }
  return out;
}"""

_TEXT_UNDER_TOGGLE = """() => {
  const toggle = document.getElementById('app-motion-toggle');
  if (!toggle || toggle.hidden) return {missing: true, covered: []};
  const t = toggle.getBoundingClientRect();
  const covered = [];
  const main = document.getElementById('app-main') || document.body;
  for (const el of main.querySelectorAll('*')) {
    if (el === toggle || toggle.contains(el) || el.contains(toggle)) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    // Chữ trong <details> đang đóng vẫn có khung toạ độ nhưng không được vẽ.
    if (!el.checkVisibility({contentVisibilityAuto: true, opacityProperty: true, visibilityProperty: true})) continue;
    // Phần chữ người dùng thấy: khung của phần tử cắt theo mọi khung cuộn bao ngoài.
    let r = el.getBoundingClientRect();
    let box = {left: r.left, top: r.top, right: r.right, bottom: r.bottom};
    for (let a = el.parentElement; a && a !== document.documentElement; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (s.overflowX === 'visible' && s.overflowY === 'visible') continue;
      const c = a.getBoundingClientRect();
      box = {left: Math.max(box.left, c.left), top: Math.max(box.top, c.top),
             right: Math.min(box.right, c.right), bottom: Math.min(box.bottom, c.bottom)};
    }
    if (box.right - box.left <= 1 || box.bottom - box.top <= 1) continue;
    const x = Math.min(box.right, t.right) - Math.max(box.left, t.left);
    const y = Math.min(box.bottom, t.bottom) - Math.max(box.top, t.top);
    if (x > 1 && y > 1) covered.push(el.textContent.trim().slice(0, 40));
  }
  return {missing: false, covered, top: t.top, bottom: t.bottom, height: innerHeight};
}"""


@pytest.fixture(scope="module")
def chromium():
    if os.environ.get("UI_BROWSER_REQUIRED") == "1":
        import playwright.sync_api as playwright
    else:
        playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as pw:
        options = {"args": ["--no-sandbox"]}
        if os.environ.get("UI_CHROMIUM_EXECUTABLE"):
            options["executable_path"] = os.environ["UI_CHROMIUM_EXECUTABLE"]
        if os.environ.get("UI_CHROMIUM_ARGS_FILE"):
            options["args"] = json.loads(Path(os.environ["UI_CHROMIUM_ARGS_FILE"]).read_text())
        try:
            browser = pw.chromium.launch(**options)
        except playwright.Error:
            if os.environ.get("UI_BROWSER_REQUIRED") == "1" or options.get("executable_path"):
                raise
            pytest.skip("chưa cài Chromium; browser CI phải cài và chạy phép kiểm này")
        yield browser
        browser.close()


def _pages_with_selects() -> list[str]:
    return sorted(p.name for p in DOCS.glob("*.html") if "<select" in p.read_text(encoding="utf-8"))


def test_the_pages_under_test_exist() -> None:
    """Tập quét không được rỗng: hai phép kiểm dưới chỉ đỏ được khi có trang để mở."""
    pages = _pages_with_selects()
    assert len(pages) >= 20, pages
    assert {"soi-cau-vi-tri.html", "ket-qua-mien-nam.html", "tan-suat-loto.html"} <= set(pages)
    assert all((DOCS / name).is_file() for name in TOGGLE_PAGES)


def test_the_select_rule_catches_a_clipped_option(chromium) -> None:
    """Ghim chính luật đo trên mẫu dựng sẵn: ô 120px không chứa nổi chữ dài, ô 360px thì chứa được."""
    page = chromium.new_page(viewport={"width": 390, "height": 600})
    page.set_content(
        '<select id="hep" style="width:120px;padding:0 12px;font:13px sans-serif">'
        "<option>Tất cả ngày đang hiển thị</option></select>"
        '<select id="rong" style="width:360px;padding:0 12px;font:13px sans-serif">'
        "<option>Tất cả ngày đang hiển thị</option></select>"
    )
    found = page.evaluate(_CLIPPED_SELECTS)
    page.close()
    assert len(found) == 1 and found[0].startswith("hep:"), found


def test_the_toggle_rule_catches_text_under_a_fixed_button(chromium) -> None:
    """Ghim luật đo chồng lấn: chữ thật dưới nút ghim cố định bị bắt; chữ trong ``<details>`` đóng và chữ
    bị khung cuộn cắt mất thì không, vì người dùng không thấy chúng."""
    page = chromium.new_page(viewport={"width": 390, "height": 400})
    page.set_content(
        '<main id="app-main"><div style="height:330px"></div>'
        '<details><summary>Mở</summary><p style="margin:0">ẩn trong details</p></details>'
        '<div style="height:20px;overflow:hidden"><div style="height:40px"></div><p>bị khung cuộn cắt</p></div>'
        '<p id="lo" style="margin:0;text-align:right">chữ bị che</p>'
        '<button id="app-motion-toggle" style="position:fixed;right:0;bottom:0;width:200px;height:60px">'
        "Hiệu ứng</button></main>"
    )
    state = page.evaluate(_TEXT_UNDER_TOGGLE)
    page.close()
    assert "chữ bị che" in state["covered"], state
    assert not {"ẩn trong details", "bị khung cuộn cắt"} & set(state["covered"]), state


@pytest.mark.parametrize("width", PHONE_WIDTHS)
def test_no_select_clips_an_option_on_a_phone(chromium, width: int) -> None:
    context = chromium.new_context(viewport={"width": width, "height": 800}, is_mobile=True, has_touch=True)
    page = context.new_page()
    clipped: list[str] = []
    for name in _pages_with_selects():
        page.goto((DOCS / name).as_uri(), wait_until="load")
        clipped += [f"{name} @{width}px: {item}" for item in page.evaluate(_CLIPPED_SELECTS)]
    context.close()
    assert not clipped, "\n".join(clipped)


@pytest.mark.parametrize("name", TOGGLE_PAGES)
def test_the_motion_toggle_never_covers_text_on_a_phone(chromium, name: str) -> None:
    """Cuộn từ đầu tới cuối trang: không lúc nào nút «Hiệu ứng» nằm đè lên chữ của nội dung.

    Bật hiệu ứng (không giảm chuyển động) vì khi giảm chuyển động nút bị ẩn hẳn và phép kiểm trống.
    """
    context = chromium.new_context(viewport={"width": 390, "height": 760}, is_mobile=True, has_touch=True,
                                   reduced_motion="no-preference")
    page = context.new_page()
    page.goto((DOCS / name).as_uri(), wait_until="load")
    page.wait_for_function("() => document.getElementById('app-motion-toggle')?.hidden === false")
    seen_on_screen = False
    problems: list[str] = []
    # Cuộn TỨC THÌ: trang đặt scroll-behavior: smooth, nên khi bật hiệu ứng mỗi lần cuộn là một hoạt cảnh và
    # đo giữa chừng thì nút chưa tới (trang chủ dài ~30 000px). Đọc lại chiều cao ở mỗi bước vì khối tải chậm
    # làm trang dài thêm; bước cuối cuộn thẳng tới nút để luôn có ít nhất một lần nút ở trên màn hình.
    for label in ("0%", "25%", "50%", "75%", "nút"):
        if label == "nút":
            page.evaluate("() => document.getElementById('app-motion-toggle').scrollIntoView({block: 'end', behavior: 'instant'})")
        else:
            page.evaluate("f => window.scrollTo({top: document.documentElement.scrollHeight * f, behavior: 'instant'})", int(label[:-1]) / 100)
        page.wait_for_timeout(100)
        state = page.evaluate(_TEXT_UNDER_TOGGLE)
        assert not state["missing"], name
        if state["bottom"] > 0 and state["top"] < state["height"]:
            seen_on_screen = True
        if state["covered"]:
            problems.append(f"cuộn {label}: {state['covered'][:3]}")
    context.close()
    assert seen_on_screen, f"{name}: nút không lần nào hiện trên màn hình, phép kiểm không đo được gì"
    assert not problems, f"{name}: " + "; ".join(problems)
