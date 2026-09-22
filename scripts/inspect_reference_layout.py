"""Đo BỐ CỤC ĐÃ RENDER của một trang tham chiếu bằng trình duyệt thật.

Vì sao cần, dù đã có ``inspect_reference_design.py``: tệp kia đọc CSS dạng văn
bản. Cách ấy đủ cho một trang tiếp thị khai gần hết bằng biến CSS, nhưng hỏng
với một dashboard. Đã đo trên NexLink: trang nạp MƯỜI biểu định kiểu, tám cái
đầu là thư viện icon và widget, nên bản đọc văn bản thu về 0 biến chủ đề, 0
quy tắc ``body`` và một bộ xương rỗng — không có gì dùng được.

Script này thay vào đó hỏi thẳng trình duyệt ``getComputedStyle``: số đo là
thứ người dùng thật sự nhìn thấy, sau khi mọi biểu định kiểu và mọi lớp tiện
ích đã hoà vào nhau.

Nó KHÔNG tải hiện vật của trang về kho. Nó in số đo: bề rộng, chiều cao, màu
đã tính, bán kính, bóng, giãn cách, cỡ chữ. Trang tham chiếu là sản phẩm
thương mại; ta đọc ngôn ngữ thị giác rồi tự viết CSS của mình.
"""

from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

TIMEOUT = 45_000
#: Ba lần đo, không phải sáu. Log của Actions chỉ lấy về được phần cuối (tải
#: trọn tệp log bị proxy chặn), nên in ít mà đủ hơn là in hết rồi mất phần đầu.
LAN_DO = [("pc", 1440, 900, "light"), ("pc", 1440, 900, "dark"), ("dt", 390, 844, "light")]

#: Tìm thành phần theo VAI TRÒ bố cục chứ không theo tên lớp. Tên lớp là của
#: riêng chủ đề và đổi giữa các bản; vai trò thì không: thanh bên là khối cao
#: gần bằng màn hình nằm sát mép trái, thanh trên là khối rộng nằm sát mép
#: trên, thẻ là hình chữ nhật có nền riêng và bo góc, lặp lại nhiều lần.
JS_DO = r"""
() => {
  const cs = el => getComputedStyle(el);
  const hop = el => el.getBoundingClientRect();
  const lay = (el, ...props) => {
    if (!el) return null;
    const s = cs(el), r = hop(el);
    const o = {tag: el.tagName.toLowerCase(), cls: (el.className||'').toString().slice(0,80),
               w: Math.round(r.width), h: Math.round(r.height)};
    for (const p of props) o[p] = s.getPropertyValue(p);
    return o;
  };
  const tat = Array.from(document.querySelectorAll('*'));

  // Thanh bên: cao >= 60% màn hình, sát mép trái, rộng 40-360px.
  const sidebar = tat.filter(el => {
    const r = hop(el), s = cs(el);
    return r.height >= innerHeight*0.6 && r.left <= 8 && r.width >= 40 && r.width <= 360
           && (s.position === 'fixed' || s.position === 'sticky' || s.position === 'absolute');
  }).sort((a,b) => hop(b).height - hop(a).height)[0];

  // Thanh trên: rộng >= 50% màn hình, sát mép trên, cao 40-120px.
  const topbar = tat.filter(el => {
    const r = hop(el), s = cs(el);
    return r.width >= innerWidth*0.5 && r.top <= 8 && r.height >= 40 && r.height <= 120
           && (s.position === 'fixed' || s.position === 'sticky');
  }).sort((a,b) => hop(b).width - hop(a).width)[0];

  // Thẻ: có nền riêng khác nền trang, có bo góc, và kiểu dáng ấy lặp lại.
  const nenTrang = cs(document.body).backgroundColor;
  const ungVien = tat.filter(el => {
    const r = hop(el), s = cs(el);
    return r.width >= 160 && r.height >= 80 && r.width <= innerWidth
           && parseFloat(s.borderTopLeftRadius) >= 2
           && s.backgroundColor !== 'rgba(0, 0, 0, 0)' && s.backgroundColor !== nenTrang;
  });
  const dem = new Map();
  for (const el of ungVien) {
    const s = cs(el);
    const k = [s.backgroundColor, s.borderTopLeftRadius, s.boxShadow, s.borderTopWidth, s.borderTopColor].join('|');
    dem.set(k, (dem.get(k)||[]).concat([el]));
  }
  const nhomThe = [...dem.entries()].sort((a,b) => b[1].length - a[1].length)[0];
  const card = nhomThe ? nhomThe[1][0] : null;

  const bang = document.querySelector('table');
  const th = bang ? bang.querySelector('th') : null;
  const td = bang ? bang.querySelector('tbody td, td') : null;
  const nut = document.querySelector('button, .btn, a.btn');
  const oNhap = document.querySelector('input:not([type=hidden]), select');

  const chu = {};
  for (const sel of ['h1','h2','h3','h4','h5','p','body','small','label','th','td']) {
    const el = document.querySelector(sel);
    if (el) {
      const s = cs(el);
      chu[sel] = {'font-size': s.fontSize, 'font-weight': s.fontWeight,
                  'line-height': s.lineHeight, 'letter-spacing': s.letterSpacing,
                  color: s.color, 'font-family': s.fontFamily.slice(0,46)};
    }
  }

  return {
    vieport: {w: innerWidth, h: innerHeight},
    body: lay(document.body, 'background-color', 'background-image', 'color', 'font-family', 'font-size'),
    sidebar: lay(sidebar, 'background-color', 'border-right', 'width', 'padding', 'box-shadow'),
    topbar: lay(topbar, 'background-color', 'border-bottom', 'height', 'padding', 'box-shadow', 'backdrop-filter'),
    the: lay(card, 'background-color', 'border-top-left-radius', 'box-shadow', 'border-top-width',
             'border-top-color', 'padding'),
    soThe: nhomThe ? nhomThe[1].length : 0,
    bang_th: lay(th, 'background-color', 'color', 'font-size', 'font-weight', 'padding', 'border-bottom',
                 'text-transform', 'letter-spacing'),
    bang_td: lay(td, 'background-color', 'color', 'font-size', 'padding', 'border-bottom'),
    nut: lay(nut, 'background-color', 'color', 'border-top-left-radius', 'padding', 'font-size',
             'font-weight', 'border-top-width', 'box-shadow'),
    o_nhap: lay(oNhap, 'background-color', 'color', 'border-top-left-radius', 'padding', 'font-size',
                'border-top-width', 'border-top-color', 'height'),
    chu: chu,
    tranNgang: document.documentElement.scrollWidth > innerWidth + 1,
  };
}
"""


def main() -> int:
    urls = [u.strip() for u in os.environ.get("URLS", "").split(",") if u.strip()]
    if not urls:
        print("Thiếu biến môi trường URLS", file=sys.stderr)
        return 2
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--no-sandbox"])
        for url in urls:
            print(f"\n{'=' * 78}\nTRANG: {url}\n{'=' * 78}")
            for ten, w, h, che_do in LAN_DO:
                pg = b.new_page(viewport={"width": w, "height": h}, color_scheme=che_do)
                try:
                    pg.goto(url, wait_until="networkidle", timeout=TIMEOUT)
                    pg.wait_for_timeout(900)
                    do = pg.evaluate(JS_DO)
                except Exception as exc:
                    print(f"  !! {ten}/{che_do}: {type(exc).__name__}: {exc}")
                    pg.close()
                    continue
                print(f"\n--- {ten} {w}x{h} / {che_do} ---")
                print(json.dumps(do, ensure_ascii=False, indent=1))
                pg.close()
        b.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
