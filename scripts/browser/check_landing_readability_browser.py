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
    simulation = page.locator("#mo-phong")
    expect(simulation.locator(".app-simulation-loto td")).to_have_count(27)
    loto = simulation.evaluate("""section => {
      const board=section.querySelector('.fun-board-wrap');
      const table=section.querySelector('.app-simulation-loto');
      const rect=e=>{const r=e.getBoundingClientRect();return {x:r.x,right:r.right,y:r.y,bottom:r.bottom,width:r.width,height:r.height}};
      return {expected:[...board.querySelectorAll('.fun-prize-number')].map(e=>e.textContent.trim().slice(-2)).sort(),
        actual:[...table.querySelectorAll('td')].map(e=>e.textContent.trim()),
        clipped:[...table.querySelectorAll('td')].some(e=>e.scrollWidth>e.clientWidth+1),
        board:rect(board),table:rect(table),note:rect(section.querySelector('.fun-simulation-note'))};
    }""")
    assert loto["actual"] == loto["expected"], loto
    assert not loto["clipped"], loto
    assert loto["board"]["bottom"] <= loto["table"]["y"] <= loto["board"]["bottom"] + 16, loto
    assert loto["table"]["bottom"] <= loto["note"]["y"], loto
    assert loto["table"]["width"] > 2 * loto["table"]["height"], loto
    assert loto["table"]["height"] < loto["board"]["height"] / 3, loto
    assert loto["table"]["x"] >= loto["board"]["x"] - 1, loto
    assert loto["table"]["right"] <= loto["board"]["right"] + 1, loto
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
        reverseTable:box(reverse.querySelector('.stat-table')),
        paths: [...document.querySelectorAll('.basis-merged > section')].map(section=>({
          outer:box(section), inner:box(section.querySelector('.table-wrap'))
        })),
        groups: [...document.querySelectorAll('.group-chart')].map(card=>({
          digits:[...card.querySelectorAll('.group-bar-row')].map(e=>e.dataset.groupValue),
          clipped:[...card.querySelectorAll('.group-bar-label,.group-bar-value')].some(e=>e.scrollWidth>e.clientWidth+1)
        }))
      };
    }""")
    measured["simulationLoto"] = loto
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
        assert measured["reverseTable"]["width"] <= table["width"], measured["reverseTable"]
    for path in measured["paths"]:
        assert path["inner"]["x"] - path["outer"]["x"] >= 12, path
        assert path["outer"]["right"] - path["inner"]["right"] >= 12, path
    assert len(measured["groups"]) == 3, measured["groups"]
    for group in measured["groups"]:
        assert group["digits"] == [str(i) for i in range(10)] and not group["clipped"], group
    return measured
