"""Đo HỆ BIỂU TƯỢNG và MENU của trang tham chiếu.

Vì sao cần một bản đo riêng: ``inspect_reference_shell.py`` đo hình học của
hai dải và thanh trên — bề rộng, đệm, bo góc. Nó không nói biểu tượng được
VẼ BẰNG GÌ, mà đó mới là câu hỏi ở đây. Một biểu tượng có thể là:

* ký tự của một phông biểu tượng, nằm trong ``content`` của ``::before``;
* một phần tử ``<svg>`` với ``stroke-width`` và ``viewBox`` riêng;
* một ảnh nền.

Ba lối ấy đòi ba cách dựng lại khác hẳn nhau, nên đoán sai là dựng sai.

KHÔNG tải hiện vật của họ về kho: không lưu HTML, CSS, phông hay đường vẽ
SVG. Chỉ in SỐ ĐO và TÊN — cỡ, nét, màu, hộp chứa, và ẩn dụ của từng mục
menu — để tự viết lại bằng tay theo đúng ngôn ngữ thị giác ấy.
"""

from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

TIMEOUT = 45_000

JS = r"""
() => {
  const cs = (e) => getComputedStyle(e);
  const hop = (e) => e.getBoundingClientRect();

  // Tìm dải điều hướng bên trái theo VAI TRÒ, không theo tên lớp: tên lớp là
  // thứ riêng của họ và đổi theo phiên bản, còn "phần tử cao gần bằng màn,
  // dính bên trái, chứa nhiều liên kết" thì không đổi.
  let dai = null, diem = -1;
  for (const e of document.querySelectorAll('aside, nav, div')) {
    const r = hop(e), s = cs(e);
    if (r.height < window.innerHeight * 0.5 || r.left > 160 || r.width > 400) continue;
    const lien_ket = e.querySelectorAll('a').length;
    if (lien_ket < 4) continue;
    const d = lien_ket + (s.position === 'fixed' ? 10 : 0);
    if (d > diem) { diem = d; dai = e; }
  }
  if (!dai) return { loi: 'khong tim thay dai dieu huong' };

  const muc = [];
  for (const a of dai.querySelectorAll('a')) {
    const r = hop(a);
    if (r.width === 0 && r.height === 0) continue;
    const s = cs(a);
    const o = {
      nhan: (a.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40),
      w: Math.round(r.width), h: Math.round(r.height),
      pad: s.padding, gap: s.gap, radius: s.borderRadius,
      font: s.fontSize + '/' + s.fontWeight, mau: s.color,
    };

    // Biểu tượng: thử cả ba lối, in ra lối nào TRÚNG.
    const svg = a.querySelector('svg');
    if (svg) {
      const sr = hop(svg), ss = cs(svg);
      o.icon_kieu = 'svg';
      o.icon_hop = Math.round(sr.width) + 'x' + Math.round(sr.height);
      o.icon_viewbox = svg.getAttribute('viewBox');
      o.icon_stroke = ss.strokeWidth;
      o.icon_fill = ss.fill;
      o.icon_mau = ss.color;
      // ĐẾM hình con, không chép đường vẽ: số hình nói lên độ phức tạp.
      o.icon_so_hinh = svg.querySelectorAll('path,circle,rect,line,polyline,polygon').length;
    } else {
      const con = a.querySelector('i, span[class*="icon"], span[class*="ico"], em');
      const goc = con || a;
      for (const gia of ['::before', '::after']) {
        const ps = getComputedStyle(goc, gia);
        const noi = ps.content;
        if (noi && noi !== 'none' && noi !== 'normal' && noi !== '""') {
          o.icon_kieu = 'phong bieu tuong';
          o.icon_phong = ps.fontFamily;
          o.icon_co = ps.fontSize;
          o.icon_net = ps.fontWeight;
          o.icon_mau = ps.color;
          // Mã điểm, không phải hình: đủ để biết họ dùng bộ nào và mục nào
          // ánh xạ sang ẩn dụ nào, mà không chép phông về.
          o.icon_ma = Array.from(noi.replace(/^"|"$/g, ''))
            .map((c) => 'U+' + c.codePointAt(0).toString(16).toUpperCase()).join(' ');
          break;
        }
      }
      if (!o.icon_kieu && con) {
        const csx = cs(con), cr = hop(con);
        o.icon_kieu = csx.backgroundImage !== 'none' ? 'anh nen' : 'khong ro';
        o.icon_hop = Math.round(cr.width) + 'x' + Math.round(cr.height);
        o.icon_co = csx.fontSize;
        o.icon_mau = csx.color;
      }
    }
    muc.push(o);
  }

  const ds = cs(dai), dr = hop(dai);
  return {
    dai: { w: Math.round(dr.width), nen: ds.backgroundColor, pad: ds.padding },
    so_muc: muc.length,
    // Bộ phông biểu tượng mà trang NẠP VỀ, đọc từ @font-face đã áp dụng.
    phong_bieu_tuong: Array.from(document.fonts)
      .map((f) => f.family).filter((v, i, a) => a.indexOf(v) === i).slice(0, 12),
    muc: muc.slice(0, 40),
  };
}
"""


def main() -> int:
    """Đo từng URL rồi in số đo ra log.

    Returns:
        0 nếu đo được ít nhất một URL, 1 nếu không.
    """
    urls = [u.strip() for u in os.environ.get("URLS", "").split(",") if u.strip()]
    if not urls:
        print("Chưa truyền URLS", file=sys.stderr)
        return 1
    ok = False
    with sync_playwright() as pw:
        trinh = pw.chromium.launch()
        for url in urls:
            if not url.startswith("https://"):
                print(f"BỎ QUA (không phải https): {url}")
                continue
            trang = trinh.new_page(viewport={"width": 1440, "height": 900})
            try:
                trang.goto(url, wait_until="networkidle", timeout=TIMEOUT)
                trang.wait_for_timeout(1500)
                do = trang.evaluate(JS)
                print(f"=== {url}")
                print(json.dumps(do, ensure_ascii=False, indent=1))
                ok = True
            except Exception as loi:  # noqa: BLE001 - in ra rồi đo URL kế
                print(f"LỖI {url}: {type(loi).__name__}: {loi}")
            finally:
                trang.close()
        trinh.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
