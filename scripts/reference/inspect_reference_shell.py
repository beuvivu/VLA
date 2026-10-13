"""Đo KHUNG ỨNG DỤNG của trang tham chiếu: hai cấp điều hướng, thanh trên,
vùng nội dung, và trạng thái thu/mở.

Khác ``inspect_reference_layout.py``: tệp kia đo MỘT thanh bên và các thành
phần lẻ (thẻ, bảng, nút). Khung của trang tham chiếu lần này có HAI dải trái
nằm cạnh nhau — dải biểu tượng và dải chi tiết — cùng một nút trong thanh trên
điều khiển chúng. Muốn dựng lại thì phải đo cả hai dải VÀ đo lại sau khi bấm
nút, vì bề rộng khi thu là con số không suy ra được từ CSS tĩnh.

Không tải hiện vật của trang về kho. Chỉ in số đo.
"""

from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

TIMEOUT = 45_000
#: Đo ở bốn bề ngang. Mỗi lần đo in một dòng: log của Actions chỉ lấy về được
#: phần cuối, nên in gọn là điều kiện để đọc được hết.
BE_NGANG = [(1440, 900, "light"), (1440, 900, "dark"), (1024, 768, "light"), (390, 844, "light")]

JS = r"""
() => {
  const cs = el => getComputedStyle(el);
  const hop = el => el.getBoundingClientRect();
  const lay = (el, ...props) => {
    if (!el) return null;
    const s = cs(el), r = hop(el);
    const o = {tag: el.tagName.toLowerCase(), cls: (el.className||'').toString().slice(0,60),
               x: Math.round(r.left), y: Math.round(r.top),
               w: Math.round(r.width), h: Math.round(r.height)};
    for (const p of props) o[p] = s.getPropertyValue(p);
    return o;
  };
  const tat = Array.from(document.querySelectorAll('*'));

  // MỌI dải dọc bên trái: cao >= 55% màn hình, mép trái < 40% bề ngang,
  // rộng 40-400px, và được định vị (fixed/sticky/absolute). Sắp theo toạ độ x
  // để dải biểu tượng đứng trước dải chi tiết.
  const dai = tat.filter(el => {
    const r = hop(el), s = cs(el);
    return r.height >= innerHeight*0.55 && r.left < innerWidth*0.4
        && r.width >= 40 && r.width <= 400
        && ['fixed','sticky','absolute'].includes(s.position);
  });
  // Bỏ phần tử lồng nhau cùng bề rộng: giữ cái NGOÀI cùng cho mỗi cột.
  const cot = new Map();
  for (const el of dai) {
    const r = hop(el);
    const k = Math.round(r.left) + ':' + Math.round(r.width);
    if (!cot.has(k)) cot.set(k, el);
  }
  const daiSapXep = [...cot.values()].sort((a,b) => hop(a).left - hop(b).left).slice(0,3);

  const header = tat.filter(el => {
    const r = hop(el), s = cs(el);
    return r.width >= innerWidth*0.4 && r.top <= 8 && r.height >= 40 && r.height <= 130
        && ['fixed','sticky'].includes(s.position);
  }).sort((a,b) => hop(b).width - hop(a).width)[0];

  const main = document.querySelector('main, .app-content, .page-content, .content-wrapper')
            || (header ? header.parentElement.querySelector(':scope > div:last-child') : null);

  // Mục điều hướng: thẻ <a> nằm trong một dải trái.
  const trongDai = el => daiSapXep.some(d => d.contains(el));
  const mucNav = tat.filter(el => el.tagName === 'A' && trongDai(el) && hop(el).height >= 20);
  const mucDau = mucNav[0] || null;
  const mucHoatDong = mucNav.find(el =>
      el.classList.contains('active') || el.getAttribute('aria-current')
      || (el.parentElement && el.parentElement.classList.contains('active'))) || null;

  return {
    vp: {w: innerWidth, h: innerHeight},
    body: lay(document.body, 'background-color', 'color', 'font-family'),
    dai: daiSapXep.map(d => lay(d, 'background-color', 'box-shadow', 'border-right', 'overflow-y', 'z-index')),
    header: lay(header, 'background-color', 'border-bottom', 'padding', 'box-shadow', 'z-index'),
    main: lay(main, 'padding', 'margin-left', 'background-color', 'max-width'),
    soMucNav: mucNav.length,
    navMuc: lay(mucDau, 'padding', 'border-top-left-radius', 'color', 'font-size', 'font-weight', 'gap'),
    navHoatDong: lay(mucHoatDong, 'background-color', 'color', 'border-top-left-radius', 'font-weight'),
    tranNgang: document.documentElement.scrollWidth > innerWidth + 1,
  };
}
"""

#: Ứng viên nút thu/mở trong thanh trên. Dò theo nhiều dấu hiệu vì tên lớp là
#: của riêng chủ đề.
NUT = ("button.app-toggler", "[data-toggle='sidebar']", ".sidebar-toggle",
       "header button:first-of-type", "header button")


def bam_nut(pg) -> str:
    for sel in NUT:
        try:
            el = pg.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=3000)
                pg.wait_for_timeout(700)
                return sel
        except Exception:
            continue
    return ""


def main() -> int:
    urls = [u.strip() for u in os.environ.get("URLS", "").split(",") if u.strip()]
    if not urls:
        print("Thiếu biến môi trường URLS", file=sys.stderr)
        return 2
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--no-sandbox"])
        for url in urls:
            print(f"\n{'=' * 70}\nTRANG: {url}\n{'=' * 70}")
            for w, h, che_do in BE_NGANG:
                pg = b.new_page(viewport={"width": w, "height": h}, color_scheme=che_do)
                try:
                    pg.goto(url, wait_until="networkidle", timeout=TIMEOUT)
                    pg.wait_for_timeout(900)
                    print(f"\n### {w}x{h} {che_do} MO")
                    print(json.dumps(pg.evaluate(JS), ensure_ascii=False, separators=(",", ":")))
                    sel = bam_nut(pg)
                    print(f"### {w}x{h} {che_do} SAU KHI BAM {sel!r}")
                    print(json.dumps(pg.evaluate(JS), ensure_ascii=False, separators=(",", ":")))
                except Exception as exc:
                    print(f"  !! {w}x{h}/{che_do}: {type(exc).__name__}: {exc}")
                pg.close()
        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
