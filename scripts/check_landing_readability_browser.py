"""Đo những lỗi bố cục thực tế mà phép kiểm HTML không nhìn thấy."""

from pathlib import Path

from playwright.sync_api import expect


def check_landing(page, output: Path, width: int, dark: bool) -> dict:
    """Kiểm hàng ba thẻ, bảng dùng chung, căn cột và khoảng đệm thực."""
    board = page.locator("#app-daily-results")
    expect(board.locator(".tr-number")).to_have_count(27)
    expect(board.locator(".tr-loto")).to_have_count(0)
    number = board.locator(".tr-number").first
    number.click()
    expect(number).to_have_attribute("aria-pressed", "true")
    number.press("Enter")
    expect(number).to_have_attribute("aria-pressed", "false")
    number.press("Space")
    expect(number).to_have_attribute("aria-pressed", "true")
    number.click()
    expect(number).to_have_attribute("aria-pressed", "false")
    measured = page.evaluate("""() => {
      const box = element => {
        const r = element.getBoundingClientRect();
        return {x:r.x, y:r.y, width:r.width, height:r.height, bottom:r.bottom, right:r.right};
      };
      const textBox = element => {
        const range = document.createRange(); range.selectNodeContents(element);
        return box({getBoundingClientRect:()=>range.getBoundingClientRect()});
      };
      const next = document.querySelector('.next-day');
      const pair = document.querySelector('#tan-suat-cap table');
      const headers = [...pair.querySelectorAll('thead th')];
      const cells = [...pair.querySelectorAll('tbody tr:first-child td')];
      const reverse = document.querySelector('#cap-lon .two-col');
      const reverseCards = [...reverse.children].map(box);
      const reverseInner = [...reverse.querySelectorAll('.bar-list,.table-wrap')].map(box);
      return {
        sections: [...document.querySelectorAll('section[id]')].map(e=>e.id),
        next: [...next.children].map(box),
        columns: headers.map((e,i)=>({heading:textBox(e),value:textBox(cells[i])})),
        reverseCards, reverseInner,
        paths: [...document.querySelectorAll('.basis-merged > section')].map(section=>({
          outer:box(section), inner:box(section.querySelector('.table-wrap'))
        })),
        groups: [...document.querySelectorAll('.group-chart')].map(card=>({
          digits:[...card.querySelectorAll('.group-bar-row')].map(e=>e.dataset.groupValue),
          clipped:[...card.querySelectorAll('.group-bar-label,.group-bar-value')].some(e=>e.scrollWidth>e.clientWidth+1)
        }))
      };
    }""")
    # Lưu đủ bảy vùng ngay cả khi một phép đo sau đó không đạt.
    for target in ("ket-qua", "db-tuan-thang", "ai-ml", "tan-suat-cap", "cap-lon", "dau-duoi-tong", "duong-cau"):
        page.locator(f"#{target}").screenshot(
            path=str(output / f"landing-{target}-{width}-{'dark' if dark else 'light'}.png"),
            animations="disabled",
            style=".app-header { visibility: hidden !important; }",
        )
    order = measured["sections"]
    assert order.index("ma-tran-ngay") < order.index("db-tuan-thang") < order.index("ai-ml"), order
    next_cards = measured["next"]
    assert len(next_cards) == 3, next_cards
    assert max(card["y"] for card in next_cards) - min(card["y"] for card in next_cards) <= 1, next_cards
    assert max(card["height"] for card in next_cards) - min(card["height"] for card in next_cards) <= 2, next_cards
    for column in measured["columns"][1:]:
        assert abs(column["heading"]["right"] - column["value"]["right"]) <= 2, column
    left, right = measured["reverseCards"]
    if abs(left["y"] - right["y"]) <= 1:
        assert abs(left["bottom"] - right["bottom"]) <= 2, measured["reverseCards"]
        bars, table = measured["reverseInner"]
        assert abs(bars["bottom"] - table["bottom"]) <= 4, measured["reverseInner"]
    for path in measured["paths"]:
        assert path["inner"]["x"] - path["outer"]["x"] >= 12, path
        assert path["outer"]["right"] - path["inner"]["right"] >= 12, path
    assert len(measured["groups"]) == 3, measured["groups"]
    for group in measured["groups"]:
        assert group["digits"] == [str(i) for i in range(10)] and not group["clipped"], group
    return measured
