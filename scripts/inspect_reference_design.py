"""In ĐẶC TÍNH THIẾT KẾ của một trang tham chiếu: màu, gradient, bóng, bán
kính, phông, hiệu ứng.

Vì sao tồn tại: proxy của môi trường phát triển chặn toàn bộ HTTP ra ngoài
(đã đo: ``craftohtml.themezaa.com`` trả 403 ở tầng CONNECT, cả qua ``curl``
lẫn qua trình lấy trang), nên không đọc được trang mẫu mà chủ dự án đưa.
Runner của Actions thì gọi được — đây là cùng đường mà
``scripts/inspect_reference_pages.py`` đã dùng.

Khác ``inspect_reference_pages.py``: script ấy in cấu trúc BẢNG (để dựng
trang dữ liệu cho khớp). Script này in đặc tính THỊ GIÁC, vì câu hỏi lần này
là "nền và hiệu ứng trông thế nào", không phải "bảng có cột gì".

Nó chỉ in SỐ ĐO tổng hợp — mã màu, chuỗi gradient, giá trị bóng, tên
``@keyframes`` — chứ không lưu HTML, CSS hay hình ảnh của trang vào kho.
Trang mẫu là sản phẩm thương mại có bản quyền; ta đọc để biết ngôn ngữ thị
giác của nó rồi tự viết CSS của mình, không bê nguyên tệp của họ về.

Mỗi tài nguyên gọi đúng MỘT lần, có nhịp chờ giữa các lần.
"""

from __future__ import annotations

import os
import random
import re
import sys
import time
from collections import Counter
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

TIMEOUT = 25
DELAY_RANGE = (1.0, 2.0)
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
#: Chặn trên số biểu định kiểu và dung lượng mỗi tệp. Một trang mẫu thương mại
#: hay kéo theo hàng chục tệp; đọc hết vừa chậm vừa không thêm thông tin.
#: Đọc tới 16 biểu định kiểu. Mức 8 cũ quá thấp cho một dashboard: đã đo trên
#: NexLink, trang nạp MƯỜI tệp và tám cái đầu toàn là thư viện icon/widget,
#: nên bản đọc thu về 0 biến chủ đề và 0 quy tắc body.
MAX_SHEETS = 16
MAX_BYTES = 3_000_000
TOP = 24

RE_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
RE_RGBA = re.compile(r"rgba?\([^)]{3,60}\)")
RE_VAR_DECL = re.compile(r"(--[a-zA-Z0-9-]+)\s*:\s*([^;}]{1,120})")
RE_GRADIENT = re.compile(
    r"(?:repeating-)?(?:linear|radial|conic)-gradient\((?:[^()]|\([^()]*\))*\)"
)
RE_SHADOW = re.compile(r"box-shadow\s*:\s*([^;}]{1,160})")
RE_RADIUS = re.compile(r"border-radius\s*:\s*([^;}]{1,80})")
RE_FONT = re.compile(r"font-family\s*:\s*([^;}]{1,160})")
RE_KEYFRAMES = re.compile(r"@keyframes\s+([A-Za-z0-9_-]+)")
RE_TRANSITION = re.compile(r"transition\s*:\s*([^;}]{1,120})")
RE_FILTER = re.compile(r"(?:backdrop-)?filter\s*:\s*([^;}]{1,120})")
RE_CLAMP = re.compile(r"clamp\((?:[^()]|\([^()]*\))*\)")
RE_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def fetch(url: str, session: requests.Session) -> str:
    """Lấy một tài nguyên, trả chuỗi rỗng nếu không lấy được."""
    try:
        resp = session.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
    except requests.RequestException as exc:
        print(f"    !! không lấy được {url}: {exc}")
        return ""
    if resp.status_code != 200:
        print(f"    !! {url} trả HTTP {resp.status_code}")
        return ""
    if len(resp.content) > MAX_BYTES:
        print(f"    !! {url} dài {len(resp.content)} byte, bỏ qua")
        return ""
    return resp.text


def nhip_cho() -> None:
    time.sleep(random.uniform(*DELAY_RANGE))


def in_bang_dem(ten: str, dem: Counter, gioi_han: int = TOP) -> None:
    """In một bảng đếm đã sắp theo tần suất."""
    print(f"\n  == {ten} ({len(dem)} giá trị khác nhau) ==")
    for gia_tri, lan in dem.most_common(gioi_han):
        print(f"    {lan:5d}×  {gia_tri}")


def in_tap(ten: str, tap: list[str], gioi_han: int = TOP) -> None:
    print(f"\n  == {ten} ({len(tap)} giá trị khác nhau) ==")
    for gia_tri in tap[:gioi_han]:
        print(f"    {gia_tri}")


def khung_trang(soup: BeautifulSoup) -> None:
    """In bộ xương các khối lớn: thẻ, lớp CSS, và ĐỘ DÀI nhan đề.

    In độ dài chứ không in nguyên văn: bố cục là thứ ta cần biết, còn câu chữ
    của họ thì không.
    """
    print("\n  == Bộ xương khối lớn ==")
    for i, khoi in enumerate(soup.select("body > section, body > div > section, body > header, body > footer")[:24], 1):
        lop = " ".join(khoi.get("class") or [])[:110]
        tieu_de = khoi.find(["h1", "h2", "h3"])
        nhan = f"{tieu_de.name} dài {len(tieu_de.get_text(' ', strip=True))} ký tự" if tieu_de else "không có nhan đề"
        print(f"    {i:2d}. <{khoi.name}> class={lop!r} — {nhan}")


def phong_tu_google(soup: BeautifulSoup) -> None:
    print("\n  == Phông nạp từ ngoài ==")
    thay = False
    for link in soup.find_all("link", href=True):
        href = link["href"]
        if "fonts.googleapis" in href or "fonts.gstatic" in href or href.endswith((".woff2", ".woff")):
            print(f"    {href[:160]}")
            thay = True
    if not thay:
        print("    (không có link phông rõ ràng trong <head>)")


def doc_mot_trang(url: str, session: requests.Session) -> None:
    print(f"\n{'=' * 78}\nTRANG: {url}\n{'=' * 78}")
    html = fetch(url, session)
    if not html:
        return
    soup = BeautifulSoup(html, "lxml")

    print(f"\n  HTML: {len(html)} ký tự, <title> dài {len(soup.title.get_text(strip=True)) if soup.title else 0} ký tự")
    khung_trang(soup)
    phong_tu_google(soup)

    css_parts: list[str] = []
    for style in soup.find_all("style"):
        css_parts.append(style.get_text())
    print("\n  == Biểu định kiểu rời ==")
    hrefs = []
    for link in soup.find_all("link", rel=True, href=True):
        rel = " ".join(link.get("rel") or []).lower()
        if "stylesheet" in rel:
            hrefs.append(urljoin(url, link["href"]))
    for href in hrefs[:MAX_SHEETS]:
        print(f"    {href[:160]}")
    if len(hrefs) > MAX_SHEETS:
        print(f"    (còn {len(hrefs) - MAX_SHEETS} tệp nữa, không đọc)")
    for href in hrefs[:MAX_SHEETS]:
        nhip_cho()
        css_parts.append(fetch(href, session))

    css = RE_COMMENT.sub(" ", "\n".join(css_parts))
    print(f"\n  CSS đã đọc: {len(css)} ký tự")

    mau = Counter(m.group(0).lower() for m in RE_HEX.finditer(css))
    mau.update(m.group(0).replace(" ", "") for m in RE_RGBA.finditer(css))
    in_bang_dem("Màu, theo tần suất", mau)

    bien = {}
    for m in RE_VAR_DECL.finditer(css):
        bien.setdefault(m.group(1), m.group(2).strip())
    # Tách biến CỦA CHỦ ĐỀ khỏi biến của framework. Một trang Bootstrap khai
    # hơn năm trăm biến `--bs-*`; in gộp rồi cắt ở 60 dòng thì danh sách toàn
    # `--bs-*` và những biến thật sự mang bản sắc thiết kế — phông, màu nhấn —
    # bị đẩy ra ngoài khung in. Đã đo: lần chạy đầu không thấy `--primary-font`
    # lẫn `--alt-font` vì đúng lý do đó.
    rieng = {k: v for k, v in bien.items() if not k.startswith("--bs-")}
    framework = {k: v for k, v in bien.items() if k.startswith("--bs-")}
    in_tap("Gradient", sorted({m.group(0) for m in RE_GRADIENT.finditer(css)}, key=len))
    in_bang_dem("box-shadow", Counter(m.group(1).strip() for m in RE_SHADOW.finditer(css)))
    in_bang_dem("border-radius", Counter(m.group(1).strip() for m in RE_RADIUS.finditer(css)))
    in_bang_dem("font-family", Counter(m.group(1).strip()[:90] for m in RE_FONT.finditer(css)))
    in_tap("@keyframes", sorted({m.group(1) for m in RE_KEYFRAMES.finditer(css)}), 60)
    in_bang_dem("transition", Counter(m.group(1).strip() for m in RE_TRANSITION.finditer(css)))
    in_bang_dem("filter / backdrop-filter", Counter(m.group(1).strip() for m in RE_FILTER.finditer(css)))
    in_tap("clamp() — thang chữ co giãn", sorted({m.group(0) for m in RE_CLAMP.finditer(css)}, key=len))

    print(f"\n  == Biến RIÊNG của chủ đề ({len(rieng)} biến) ==")
    for ten, gia_tri in rieng.items():
        print(f"    {ten}: {gia_tri[:110]}")
    # Không in giá trị biến framework: chúng là mặc định của Bootstrap, tra
    # được ở tài liệu của họ, và in ra thì đẩy phần mang bản sắc ra khỏi khung.
    print(f"\n  == Biến framework: {len(framework)} biến (không in) ==")

    print("\n  == Khai báo cho body / html ==")
    for m in re.finditer(r"(?:^|\})\s*(?:html|body)[^{}]{0,80}\{([^{}]{1,600})\}", css):
        khoi = " ".join(m.group(1).split())
        if any(k in khoi for k in ("background", "font-family", "color")):
            print(f"    {khoi[:300]}")

    print("\n  == @font-face: họ phông thật ==")
    ho = sorted({m.group(1).strip().strip('\'"') for m in re.finditer(r"@font-face[^{}]*\{[^{}]*font-family\s*:\s*([^;}]{1,60})", css)})
    for h in ho[:40]:
        print(f"    {h}")


def main() -> int:
    tho = os.environ.get("URLS", "").strip()
    if not tho:
        print("Thiếu biến môi trường URLS", file=sys.stderr)
        return 2
    urls = [u.strip() for u in tho.split(",") if u.strip()]
    for u in urls:
        scheme = urlparse(u).scheme
        if scheme != "https":
            print(f"Chỉ nhận https, gặp {scheme!r} ở {u}", file=sys.stderr)
            return 2
    for i, u in enumerate(urls):
        if i:
            nhip_cho()
        doc_mot_trang(u, requests.Session())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
