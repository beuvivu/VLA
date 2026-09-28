"""In chi tiết cách một trang soi cầu tham chiếu đánh số vị trí và tô đường cầu.

Vì sao tồn tại: chủ dự án muốn hệ thống soi cầu theo đúng nguyên lý của một
trang tham chiếu (tham số kiểu ``vt=6x22``, ``lon``, ``nhay``, ``db``). Proxy của
môi trường phát triển chặn trang ấy; runner của Actions thì gọi được. Đoán quy
ước đánh số vị trí là cách chắc chắn nhất để dựng sai, nên phải đọc tận nơi.

Script chỉ ĐỌC và in ra log: tham số của biểu mẫu, đoạn chú giải, và TỪNG Ô của
các bảng kết quả kèm lớp/kiểu tô màu của phần tử con — đủ để suy ra vị trí nào
được tô, kỳ nào được tô, và số nào được ghép. Không lưu nội dung trang vào kho.
Mỗi URL gọi đúng một lần, có nhịp chờ giữa các lần.
"""

from __future__ import annotations

import os
import random
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

TIMEOUT = 25
DELAY_RANGE = (2.0, 4.0)
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
MAX_TABLES = int(os.environ.get("MAX_TABLES", "8"))
MAX_ROWS = int(os.environ.get("MAX_ROWS", "30"))
TEXT_CHARS = int(os.environ.get("TEXT_CHARS", "5000"))


def marked(cell) -> list[str]:
    """Các phần tử con có lớp hoặc kiểu riêng — đó là chỗ trang tô màu."""
    out = []
    for el in cell.find_all(True):
        text = el.get_text("", strip=True)
        cls = ".".join(el.get("class") or [])
        style = el.get("style") or ""
        if text and (cls or style) and len(text) <= 12:
            out.append(f"{text}<{el.name}{'.' + cls if cls else ''}{' ' + style if style else ''}>")
    return out


def dump_table(table, index: int) -> None:
    rows = table.find_all("tr")
    cls = ".".join(table.get("class") or [])
    print(f"  --- bảng #{index} ({len(rows)} hàng) class={cls!r} id={table.get('id')!r}")
    for tr in rows[:MAX_ROWS]:
        cells = []
        for td in tr.find_all(["td", "th"]):
            text = td.get_text(" ", strip=True)
            extra = marked(td)
            td_cls = ".".join(td.get("class") or [])
            td_style = td.get("style") or ""
            head = f"[{td_cls}{' ' + td_style if td_style else ''}]" if (td_cls or td_style) else ""
            cells.append(f"{head}{text}" + (f" {{{' '.join(extra)}}}" if extra else ""))
        print("    " + " | ".join(cells)[:900])


def dump_controls(soup) -> None:
    for form in soup.find_all("form")[:4]:
        print(f"  form action={form.get('action')!r} method={form.get('method')!r}")
    for sel in soup.find_all("select")[:12]:
        opts = [f"{o.get('value')}={o.get_text(strip=True)}" for o in sel.find_all("option")]
        print(f"    select {sel.get('name') or sel.get('id')!r}: {opts[:40]}")
    for inp in soup.find_all("input")[:40]:
        print(f"    input name={inp.get('name')!r} type={inp.get('type')!r} "
              f"value={inp.get('value')!r} checked={inp.has_attr('checked')}")
    for label in soup.find_all("label")[:40]:
        print(f"    label: {label.get_text(' ', strip=True)!r}")


def dump_styles(soup, classes: set[str]) -> None:
    """Quy tắc CSS nội tuyến cho các lớp tô màu đã thấy."""
    css = " ".join(s.get_text(" ") for s in soup.find_all("style"))
    for name in sorted(classes)[:40]:
        for match in re.finditer(r"[^{}]*\." + re.escape(name) + r"\b[^{}]*\{[^}]*\}", css):
            print(f"    css: {match.group(0).strip()[:200]}")


def main() -> int:
    urls = [u.strip() for u in os.environ.get("URLS", "").split(",") if u.strip()]
    if not urls:
        print("Không có URL nào.", file=sys.stderr)
        return 2
    session = requests.Session()
    session.headers["User-Agent"] = UA
    for i, url in enumerate(urls):
        print(f"\n{'=' * 72}\n{url}\n{'=' * 72}")
        try:
            response = session.get(url, timeout=TIMEOUT)
        except Exception as exc:  # noqa: BLE001 - một trang hỏng không dừng cả lô
            print(f"  LỖI MẠNG: {type(exc).__name__}: {exc}")
            continue
        print(f"  HTTP {response.status_code}, {len(response.content) / 1024:.0f} KB")
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "lxml")
            for tag in soup(["script", "noscript"]):
                tag.decompose()
            title = soup.find("title")
            print(f"  <title>: {title.get_text(strip=True) if title else None!r}")
            print("  --- điều khiển ---")
            dump_controls(soup)
            print("  --- chữ trên trang ---")
            print("  " + soup.get_text(" | ", strip=True)[:TEXT_CHARS])
            print("  --- liên kết soi cầu ---")
            links = [a["href"] for a in soup.find_all("a", href=True) if "showcau" in a["href"]]
            for href in links[:40]:
                print(f"    {href}")
            classes: set[str] = set()
            tables = soup.find_all("table")
            print(f"  --- {len(tables)} bảng ---")
            for index, table in enumerate(tables[:MAX_TABLES], start=1):
                dump_table(table, index)
                for el in table.find_all(True):
                    classes.update(el.get("class") or [])
            print("  --- css các lớp trong bảng ---")
            dump_styles(soup, classes)
        if i + 1 < len(urls):
            time.sleep(random.uniform(*DELAY_RANGE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
