"""In toàn văn các bài phân tích của một trang tham chiếu để học CÁCH phân tích.

Vì sao tồn tại: chủ dự án muốn hệ thống hoá phương pháp của một chuyên mục bài
dự đoán XSMB thành thuật toán riêng. Proxy của môi trường phát triển chặn trang
ấy; runner của Actions thì gọi được. Script chỉ ĐỌC và in ra log: danh sách bài
của trang chuyên mục (theo các trang phân trang), rồi chữ của từng bài và các
bảng trong bài. Không lưu nội dung vào kho. Mỗi URL gọi đúng một lần, có nhịp
chờ giữa các lần.
"""

from __future__ import annotations

import os
import random
import re
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

TIMEOUT = 25
DELAY_RANGE = (2.0, 4.0)
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "20"))
MAX_LIST_PAGES = int(os.environ.get("MAX_LIST_PAGES", "3"))
TEXT_CHARS = int(os.environ.get("TEXT_CHARS", "15000"))
MAX_ROWS = int(os.environ.get("MAX_ROWS", "25"))


def get(session: requests.Session, url: str) -> BeautifulSoup | None:
    try:
        response = session.get(url, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - một trang hỏng không dừng cả lô
        print(f"  LỖI MẠNG {url}: {type(exc).__name__}: {exc}")
        return None
    print(f"  HTTP {response.status_code}, {len(response.content) / 1024:.0f} KB  {url}")
    if response.status_code != 200:
        return None
    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup(["script", "noscript", "style"]):
        tag.decompose()
    return soup


PAGINATION = re.compile(r"([?&]page=\d+|/page/\d+)")


def category_prefix(start: str) -> str:
    """Tiền tố đường dẫn của bài: phần trước ``/type/``, hoặc thư mục cha của trang.

    Không bao giờ rỗng hay chỉ là ``/``: tiền tố ấy khớp mọi liên kết điều hướng.
    """
    path = urlparse(start).path
    prefix = path.split("/type/")[0].rstrip("/")
    if not prefix:
        prefix = path.rstrip("/").rsplit("/", 1)[0]
    if not prefix:
        raise SystemExit("Không suy ra được tiền tố bài viết; đặt ARTICLE_PREFIX.")
    return prefix + "/"


def article_links(soup: BeautifulSoup, base: str, prefix: str) -> list[str]:
    """Liên kết CÙNG host tới bài dưới ``prefix``, trừ trang chuyên mục và trang phân trang."""
    host = urlparse(base).netloc
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"]).split("#")[0]
        parsed = urlparse(href)
        path = parsed.path
        if parsed.netloc != host or PAGINATION.search(href):
            continue
        if path.startswith(prefix) and "/type/" not in path and path.rstrip("/") != prefix.rstrip("/"):
            if href not in out:
                out.append(href)
    return out


def page_links(soup: BeautifulSoup, base: str) -> list[str]:
    """Liên kết phân trang của trang chuyên mục (``?page=``, ``/page/``)."""
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"])
        if PAGINATION.search(href) and href not in out:
            out.append(href)
    return out


def main_content(soup: BeautifulSoup):
    for selector in ("article", "main", "[class*=content]", "[class*=post]", "body"):
        found = soup.select(selector)
        if found:
            return max(found, key=lambda el: len(el.get_text(" ", strip=True)))
    return soup


def dump_tables(root, limit: int = 8) -> None:
    tables = root.find_all("table")
    print(f"  --- {len(tables)} bảng trong bài ---")
    for index, table in enumerate(tables[:limit], start=1):
        print(f"  [bảng {index}]")
        for row in table.find_all("tr")[:MAX_ROWS]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            print("    | " + " | ".join(cells))


def main() -> int:
    start = os.environ.get("START_URL", "").strip()
    extra = [u.strip() for u in os.environ.get("ARTICLE_URLS", "").split(",") if u.strip()]
    if not start and not extra:
        print("Không có URL nào.", file=sys.stderr)
        return 2
    session = requests.Session()
    session.headers["User-Agent"] = UA
    articles: list[str] = list(extra)
    if start:
        prefix = os.environ.get("ARTICLE_PREFIX", "").strip() or category_prefix(start)
        queue, seen = [start], set()
        while queue and len(seen) < MAX_LIST_PAGES:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            print(f"\n{'=' * 72}\nTRANG CHUYÊN MỤC {url}\n{'=' * 72}")
            soup = get(session, url)
            if soup is None:
                continue
            title = soup.find("title")
            print(f"  <title>: {title.get_text(strip=True) if title else None!r}")
            for href in article_links(soup, url, prefix):
                if href not in articles:
                    articles.append(href)
            for href in page_links(soup, url):
                if href not in seen and href not in queue:
                    queue.append(href)
            time.sleep(random.uniform(*DELAY_RANGE))
    print(f"\n--- {len(articles)} bài tìm thấy ---")
    for href in articles:
        print(f"    {href}")
    for href in articles[:MAX_ARTICLES]:
        print(f"\n{'=' * 72}\nBÀI {href}\n{'=' * 72}")
        soup = get(session, href)
        if soup is not None:
            title = soup.find("h1") or soup.find("title")
            print(f"  tiêu đề: {title.get_text(' ', strip=True) if title else None!r}")
            root = main_content(soup)
            print("  --- chữ ---")
            print("  " + root.get_text(" | ", strip=True)[:TEXT_CHARS])
            dump_tables(root)
        time.sleep(random.uniform(*DELAY_RANGE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
