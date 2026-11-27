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
    print(f"\n  == {ten} ({len(dem)} giá trị khác nhau) ==")
    for gia_tri, lan in dem.most_common(gioi_han):
        print(f"    {lan:5d}×  {gia_tri}")


def in_tap(ten: str, tap: list[str], gioi_han: int = TOP) -> None:
    print(f"\n  == {ten} ({len(tap)} giá trị khác nhau) ==")
    for gia_tri in tap[:gioi_han]:
        print(f"    {gia_tri}")


def khung_trang(soup: BeautifulSoup) -> None:
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
