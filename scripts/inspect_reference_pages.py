"""In cấu trúc bảng và điều khiển của các trang tham chiếu.

Vì sao tồn tại: sandbox của môi trường phát triển chặn toàn bộ HTTP ra ngoài
(kiểm chứng: cả ``example.com`` cũng không tới được), nên không đối chiếu được
thiết kế với trang gốc. Runner của Actions thì gọi được — kho vẫn cào
``hainhay.net`` hằng ngày qua chính đường này.

Script chỉ ĐỌC và in **cấu trúc**: nhan đề bảng, vài hàng mẫu, và các phần tử
điều khiển. Không lưu nội dung trang vào kho: nội dung là của họ, ta chỉ cần
biết bố cục có những cột nào để dựng cho khớp.

Mỗi trang gọi đúng một lần, có nhịp chờ giữa các lần — hai nghìn yêu cầu liên
tiếp vào một trang tin là hành vi lạm dụng.
"""

from __future__ import annotations

import os
import random
import sys
import time

import requests
from bs4 import BeautifulSoup

TIMEOUT = 20
DELAY_RANGE = (1.5, 3.0)
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
MAX_ROWS = 3
MAX_COLS = 16
MAX_TABLES = 6


def summarise_table(table, index: int) -> None:
    """In nhan đề và vài hàng đầu của một bảng."""
    headers = [th.get_text(" ", strip=True) for th in table.select("thead th")]
    if not headers:
        first = table.find("tr")
        if first:
            headers = [c.get_text(" ", strip=True) for c in first.find_all(["th", "td"])]

    body_rows = table.select("tbody tr") or table.find_all("tr")[1:]
    print(f"  Bảng #{index}: {len(body_rows)} hàng, {len(headers)} cột")
    if headers:
        print(f"    cột: {headers[:MAX_COLS]}")
    for row in body_rows[:MAX_ROWS]:
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        print(f"    hàng: {cells[:MAX_COLS]}")


def summarise_controls(soup) -> None:
    """In các phần tử người dùng bấm/chọn được."""
    selects = soup.find_all("select")
    for sel in selects[:6]:
        opts = [o.get_text(strip=True) for o in sel.find_all("option")]
        name = sel.get("name") or sel.get("id") or "?"
        print(f"    select {name!r}: {len(opts)} lựa chọn, ví dụ {opts[:6]}")

    inputs = soup.find_all("input")
    kinds = {}
    for inp in inputs:
        kinds.setdefault(inp.get("type", "text"), []).append(
            inp.get("name") or inp.get("id") or "?"
        )
    for kind, names in list(kinds.items())[:6]:
        print(f"    input[{kind}]: {names[:6]}")

    buttons = [
        b.get_text(" ", strip=True)
        for b in soup.find_all(["button", "a"])
        if b.get_text(strip=True) and len(b.get_text(strip=True)) < 24
    ]
    if buttons:
        print(f"    nút/liên kết: {buttons[:16]}")


def summarise_links(soup, base: str) -> None:
    """Liệt kê đường dẫn nội bộ, để biết site có những trang nào.

    Dò cấu trúc mà không biết đường dẫn thì phải đoán, và đoán sai thì tốn
    thêm một lượt gọi vào trang tin của người ta.
    """
    host = base.split("/")[2]
    seen: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and host not in href:
            continue
        path = href.split("?")[0].split("#")[0]
        if path.startswith("http"):
            path = "/" + path.split("/", 3)[-1] if path.count("/") > 2 else "/"
        if not path.startswith("/") or path in ("/", ""):
            continue
        label = a.get_text(" ", strip=True)[:40]
        if label and path not in seen:
            seen[path] = label
    print(f"    {len(seen)} đường dẫn nội bộ:")
    for path, label in sorted(seen.items())[:80]:
        print(f"      {path:44s} {label}")


def main() -> int:
    urls = [u.strip() for u in os.environ.get("URLS", "").split(",") if u.strip()]
    if not urls:
        print("Không có URL nào.", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers["User-Agent"] = UA

    failures = 0
    for i, url in enumerate(urls):
        print(f"\n{'=' * 72}\n{url}\n{'=' * 72}")
        try:
            response = session.get(url, timeout=TIMEOUT)
        except Exception as exc:  # noqa: BLE001 - một trang hỏng không dừng cả lô
            print(f"  LỖI MẠNG: {type(exc).__name__}: {exc}")
            failures += 1
            continue

        print(f"  HTTP {response.status_code}, {len(response.content) / 1024:.0f} KB")
        if response.status_code != 200:
            failures += 1
            continue

        soup = BeautifulSoup(response.text, "lxml")
        title = soup.find("title")
        if title:
            print(f"  <title>: {title.get_text(strip=True)!r}")

        heads = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])]
        if heads:
            print(f"  tiêu đề: {heads[:8]}")

        # Điều hướng lặp lại y hệt trên mọi trang của cùng một site, nên in
        # cho từng trang là tự đẩy phần cấu trúc bảng ra khỏi cửa sổ log. Chỉ
        # in ở trang ĐẦU, hoặc khi được yêu cầu rõ.
        if i == 0 or os.environ.get("DUMP_LINKS") == "1":
            print("  --- liên kết ---")
            summarise_links(soup, url)

        print("  --- điều khiển ---")
        summarise_controls(soup)

        print("  --- bảng ---")
        tables = soup.find_all("table")
        print(f"  tổng {len(tables)} bảng")
        for index, table in enumerate(tables[:MAX_TABLES], start=1):
            summarise_table(table, index)

        if i + 1 < len(urls):
            time.sleep(random.uniform(*DELAY_RANGE))

    print(f"\nXong. {len(urls) - failures}/{len(urls)} trang đọc được.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
