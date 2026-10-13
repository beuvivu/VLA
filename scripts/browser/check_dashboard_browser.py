"""Đo khoảng đệm, cột và mã số Dashboard trên HTML đã xuất bản."""

from functools import partial
from http.server import ThreadingHTTPServer
import json
import threading

from playwright.sync_api import expect, sync_playwright

from check_ui_browser import OUT, ROOT, QuietHandler, check_evidence


MEASURE = """() => {
  const box = e => e.getBoundingClientRect();
  const root = document.querySelector('.app-lab-dashboard');
  const visible = e => e.getClientRects().length > 0 && !e.closest('details:not([open])');
  const tables = [...root.querySelectorAll('.ui-table-wrap')].filter(visible);
  const cards = [...root.querySelectorAll('.app-dash-group .ui-card')];
  return {
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    cards: cards.length,
    tables: tables.map(e => {
      const r = box(e), card = box(e.closest('.ui-card'));
      return {id:e.closest('.ui-card').id, left:r.left-card.left,
        right:card.right-r.right, bottom:card.bottom-r.bottom,
        overflow:e.scrollWidth-e.clientWidth};
    }),
    groups: [...root.querySelectorAll('.app-dash-group .ui-grid')].map(e => ({
      columns:getComputedStyle(e).gridTemplateColumns.split(' ').length,
      children:[...e.children].map(c => ({left:box(c).left, right:box(c).right,
        top:box(c).top, bottom:box(c).bottom}))
    })),
    codes: [...root.querySelectorAll('.app-dash-codes')].map(e => ({
      count:e.children.length,
      clipped:[...e.children].some(c => box(c).left < box(e).left-1 ||
        box(c).right > box(e).right+1 || c.scrollWidth > c.clientWidth+1)
    })),
    blocks: [...root.querySelectorAll('.app-dash-facts,.app-dash-proof,pre')]
      .filter(visible).map(e => ({class:e.className,overflow:e.scrollWidth-e.clientWidth}))
  };
}"""


def check_layout(page):
    """Không coi overflow:hidden là bằng chứng nội dung đã vừa khung."""
    result = page.evaluate(MEASURE)
    assert result["cards"] == 8 and len(result["tables"]) >= 8, result
    assert result["overflow"] <= 1, result
    for table in result["tables"]:
        assert min(table["left"], table["right"], table["bottom"]) >= 12, table
        assert table["overflow"] <= 1, table
    for group in result["groups"]:
        assert group["columns"] in (1, 2), group
        left, right = group["children"]
        if group["columns"] == 1:
            assert right["top"] - left["bottom"] >= 15, group
        else:
            assert right["left"] - left["right"] >= 15, group
            assert abs(left["top"] - right["top"]) <= 1, group
    assert [c["count"] for c in result["codes"]] == [4, 8, 10] * 2, result
    assert not any(c["clipped"] for c in result["codes"]), result
    assert not any(b["overflow"] > 1 for b in result["blocks"]), result
    return result


def check_padding_regression_is_detected(page):
    """Tái tạo lỗi sát viền để xác nhận phép đo thật sự phát hiện hồi quy."""
    style = page.add_style_tag(content=".app-lab-dashboard .app-dash-group .ui-card-body{padding:0!important}")
    detected = False
    try:
        check_layout(page)
    except AssertionError:
        detected = True
    finally:
        style.evaluate("e => e.remove()")
    assert detected, "Phép kiểm không phát hiện bảng chạm viền thẻ"
    check_layout(page)


def main():
    OUT.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "docs")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    results = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for width in (320, 390, 768, 900, 1024, 1280, 1440):
                page = browser.new_page(viewport={"width": width, "height": 950}, reduced_motion="reduce")
                page.goto(f"http://127.0.0.1:{server.server_port}/dashboard.html", wait_until="load")
                page.locator("body[data-app-shell-ready]").wait_for()
                for dark in (False, True):
                    if page.locator("html").evaluate("e => e.classList.contains('dark')") != dark:
                        page.locator("#app-theme").click()
                    for opened in (False, True):
                        for details in page.locator(".app-dash-proof details").all():
                            if (details.get_attribute("open") is not None) != opened:
                                details.locator("summary").click()
                        result = check_layout(page)
                        results.append({"width": width, "dark": dark, "opened": opened, **result})
                    if width == 1440 and not dark:
                        check_padding_regression_is_detected(page)
                    # Kiểm các con số vẫn mở được bằng chứng sau đổi bố cục.
                    check_evidence(page, "dashboard.html", width, dark)
                    if width in (390, 1440):
                        page.locator("#app-lab-picks").scroll_into_view_if_needed()
                        page.screenshot(path=str(OUT / f"dashboard-{width}-{'dark' if dark else 'light'}.png"))
                    # Bảng có tên truy cập được; không mất vùng focus khi thêm khoảng đệm.
                    expect(page.locator("#app-lab-loto > .ui-card-body > [role=region]")).to_have_count(1)
                page.close()
            browser.close()
    finally:
        server.shutdown()
        (OUT / "dashboard-layout.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"Dashboard: {len(results)} trạng thái bố cục đạt.")


if __name__ == "__main__":
    main()
