from __future__ import annotations

"""Bất biến đầu-cuối của chế độ đánh dấu cặp, đo trong trình duyệt thật.

Bảng do JS dựng lúc chạy, nên đây là chỗ DUY NHẤT nhìn thấy được ``data-key``
thật và lớp ``marked`` thật. Các bất biến cấu trúc nằm ở
``tests/test_pair_marking.py`` và chạy ở mọi nơi; tệp này cần Chromium nên nó
TỰ BỎ QUA khi không có. Bỏ qua thì không bảo vệ được gì, nên hai tệp bổ sung
cho nhau chứ không thay nhau.
"""

import os
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
CHROMIUM = os.environ.get(
    "VN_LOTTERY_CHROMIUM", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
)

pytest.importorskip("playwright.sync_api", reason="cần playwright để đo trong trình duyệt")
if not Path(CHROMIUM).exists():  # pragma: no cover - phụ thuộc máy chạy
    pytest.skip(f"không có Chromium tại {CHROMIUM}", allow_module_level=True)

PAIR_RE = r"/\|(?:n|c)([0-9]{2}(?:-[0-9]{2})?)/"

CLICK_BEST_PAIR = """() => {
  const re = %s;
  const all = [...document.querySelectorAll('td.cell[data-key], th.cell[data-key]')];
  const byPair = {};
  all.forEach((e) => {
    const m = re.exec(e.dataset.key);
    if (m) (byPair[m[1]] = byPair[m[1]] || []).push(e);
  });
  const best = Object.entries(byPair).sort((a, b) => b[1].length - a[1].length)[0];
  if (!best) return null;
  best[1][0].click();
  const marked = [...document.querySelectorAll('.marked')];
  return {
    pair: best[0],
    expected: best[1].length,
    marked: marked.length,
    wrong: marked.filter((e) => (re.exec(e.dataset.key) || [])[1] !== best[0]).length,
  };
}""" % PAIR_RE


def _pages() -> list[Path]:
    return sorted(
        p for p in DOCS.glob("*.html")
        if 'id="sp-pair-mode"' in p.read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        pg = browser.new_page(viewport={"width": 1400, "height": 900})
        yield pg
        browser.close()


def _open(pg, path: Path) -> None:
    pg.goto(f"file://{path}")
    pg.wait_for_timeout(1400)


@pytest.mark.parametrize("path", _pages(), ids=lambda p: p.name)
def test_marking_one_cell_lights_every_cell_carrying_the_same_pair(page, path) -> None:
    _open(page, path)
    page.evaluate("try { localStorage.clear(); } catch (e) {}")
    _open(page, path)
    page.check("#sp-pair-mode")
    got = page.evaluate(CLICK_BEST_PAIR)
    assert got is not None, (
        f"{path.name} bày ô tick nhưng KHÔNG ô nào mang cặp trong data-key, nên "
        "bật lên cũng không làm gì"
    )
    assert got["marked"] == got["expected"] and got["wrong"] == 0, (
        f"{path.name}: bấm một ô mang cặp {got['pair']} thì phải sáng đúng "
        f"{got['expected']} ô mang cặp ấy, nhưng sáng {got['marked']} ô "
        f"({got['wrong']} ô mang cặp khác)"
    )


def test_a_pair_marked_on_one_page_is_still_marked_on_another(page) -> None:
    """Giá trị thật của chế độ cặp: dõi MỘT con qua NHIỀU trang."""
    source, target = DOCS / "chu-ky-dac-biet.html", DOCS / "tan-suat-loto.html"
    _open(page, source)
    page.evaluate("try { localStorage.clear(); } catch (e) {}")
    _open(page, source)
    page.check("#sp-pair-mode")
    clicked = page.evaluate("""() => {
      const re = %s;
      const t = [...document.querySelectorAll('td.cell[data-key]')]
        .find((e) => (re.exec(e.dataset.key) || [])[1] === '34');
      if (!t) return false;
      t.click();
      return true;
    }""" % PAIR_RE)
    assert clicked, "không tìm thấy ô mang số 34 ở trang nguồn"

    _open(page, target)
    got = page.evaluate("""() => {
      const re = %s;
      const all = [...document.querySelectorAll('td.cell[data-key], th.cell[data-key]')];
      const same = all.filter((e) => (re.exec(e.dataset.key) || [])[1] === '34');
      const marked = [...document.querySelectorAll('.marked')];
      return {same: same.length, marked: marked.length};
    }""" % PAIR_RE)
    assert got["same"] > 0, "trang đích không có ô nào mang 34; phép kiểm mất đối tượng"
    assert got["marked"] == got["same"], (
        f"đánh dấu 34 ở {source.name} nhưng sang {target.name} chỉ sáng "
        f"{got['marked']}/{got['same']} ô — dấu cặp đang bị nhốt theo trang"
    )
