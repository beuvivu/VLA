"""Đo THẬT trang Sổ kết quả trong trình duyệt, thay vì đọc CSS bằng mắt.

Vì sao cần: hai lỗi của trang này chỉ lộ ra khi RENDER.

* Chân bảng lấn lề đo được là 1 px ở bản cũ — đọc CSS thì thấy
  ``.tr-prizes`` không có đệm, nhưng không biết con số thật là bao nhiêu.
* Bản sửa đầu tiên của tôi vẫn để chân tụt về 2 px, nhưng CHỈ ở tổ hợp
  "màn hình ≤ 900 px + ẩn cả hai bảng phụ". Đọc mắt thường không ra; phép
  quét 96 trạng thái ra ngay.

Chạy:  python scripts/check_traditional_results_page.py
Cần:   pip install playwright  (trình duyệt đã có sẵn trong môi trường CI/dev)
"""

from __future__ import annotations

import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "so-ket-qua-truyen-thong.html"
WIDTHS = (1440, 1180, 900, 760, 640, 390)
MIN_FOOTER_GAP_PX = 8

MEASURE = """() => {
  const day = document.querySelector('.tr-day');
  if (!day) return null;
  const box = day.getBoundingClientRect();
  const gaps = [];
  for (const node of day.querySelectorAll(
      '.tr-prizes, .tr-head-tail-scroll, .tr-loto-list')) {
    const rect = node.getBoundingClientRect();
    if (rect.height > 0) gaps.push(Math.round(box.bottom - rect.bottom));
  }
  // Tràn BÊN TRONG lưới số, và chữ bị cắt trong chính ô.
  //
  // Bản đầu chỉ kiểm `documentElement.scrollWidth` — tức trang có cuộn ngang
  // không. `.tr-day{overflow:hidden}` CẮT phần tràn thay vì làm trang cuộn,
  // nên phép kiểm ấy xanh trong khi bố cục 3 và 4 cột tràn 56 px và 172 px,
  // sáu ô số bị cắt mất chữ. Phải đo ở CẤP PHẦN TỬ.
  let gridOverflow = 0;
  let clippedCells = 0;
  let narrowest = Infinity;
  for (const grid of day.querySelectorAll('.tr-number-grid')) {
    gridOverflow = Math.max(gridOverflow, grid.scrollWidth - grid.clientWidth);
    for (const cell of grid.children) {
      narrowest = Math.min(narrowest, Math.round(cell.getBoundingClientRect().width));
      if (cell.scrollWidth > cell.clientWidth + 1) clippedCells += 1;
    }
  }
  // Cạnh phải bảng trong không được dính vào khung ngoài.
  const prizes = day.querySelector('.tr-prizes').getBoundingClientRect();
  return {
    min_gap: Math.min(...gaps),
    gaps,
    grid_overflow: gridOverflow,
    clipped_cells: clippedCells,
    narrowest_cell: narrowest,
    right_inset: Math.round(box.right - prizes.right),
    left_inset: Math.round(prizes.left - box.left),
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  };
}"""

MIN_SIDE_INSET_PX = 8


def _chromium(playwright):
    """Trình duyệt của môi trường, không tải thêm."""
    for candidate in sorted((pathlib.Path("/opt/pw-browsers")).glob("chromium-*/chrome-linux/chrome")):
        return playwright.chromium.launch(executable_path=str(candidate), args=["--no-sandbox"])
    return playwright.chromium.launch(args=["--no-sandbox"])


def main() -> int:
    from playwright.sync_api import sync_playwright

    rows = list(csv.DictReader((ROOT / "data" / "xsmb.csv").open(encoding="utf-8")))
    by_date = {row["date"][:10]: row for row in rows}
    dates = sorted(by_date)

    failures: list[str] = []
    with sync_playwright() as playwright:
        browser = _chromium(playwright)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda exc: failures.append(f"lỗi JS: {exc}"))
        page.goto(PAGE.resolve().as_uri(), wait_until="load")
        page.wait_for_timeout(900)

        # --- 1. Chân bảng và tràn ngang, mọi tổ hợp -------------------------
        scanned = 0
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 1000})
            for layout in ("1", "2", "3", "4"):
                page.evaluate(
                    "(value) => { const r = document.querySelector("
                    "`input[name=tr-layout][value='${value}']`);"
                    " r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true})); }",
                    layout,
                )
                for head_tail in (True, False):
                    for loto in (True, False):
                        page.evaluate(
                            "([ht, lo]) => { for (const [id, on] of"
                            " [['tr-toggle-headtail', ht], ['tr-toggle-loto', lo]]) {"
                            " const c = document.getElementById(id); c.checked = on;"
                            " c.dispatchEvent(new Event('change', {bubbles: true})); } }",
                            [head_tail, loto],
                        )
                        page.wait_for_timeout(40)
                        found = page.evaluate(MEASURE)
                        scanned += 1
                        label = (f"rộng={width} bố cục={layout} "
                                 f"đầu-đuôi={'on' if head_tail else 'off'} "
                                 f"lô-tô={'on' if loto else 'off'}")
                        if found["min_gap"] < MIN_FOOTER_GAP_PX:
                            failures.append(
                                f"{label}: chân bảng chỉ {found['min_gap']}px {found['gaps']}")
                        if found["overflow"]:
                            failures.append(f"{label}: trang cuộn ngang")
                        if found["grid_overflow"] > 0:
                            failures.append(
                                f"{label}: lưới số tràn {found['grid_overflow']}px")
                        if found["clipped_cells"] > 0:
                            failures.append(
                                f"{label}: {found['clipped_cells']} ô bị cắt mất chữ")
                        for side in ("left_inset", "right_inset"):
                            if found[side] < MIN_SIDE_INSET_PX:
                                failures.append(
                                    f"{label}: bảng trong dính cạnh "
                                    f"{'trái' if side.startswith('left') else 'phải'} "
                                    f"({found[side]}px)")
        print(f"đã quét {scanned} tổ hợp bố cục × công tắc × bề rộng")

        # --- 2. Tra cứu quá khứ, đối chiếu SỐ THẬT --------------------------
        page.set_viewport_size({"width": 1440, "height": 1000})
        checks = [
            (dates[0], dates[0][:8] + "28"),
            ("2021-06-01", "2021-06-30"),
            ("2023-02-01", "2023-02-28"),
            ("2025-04-28", "2025-04-30"),
            ("2019-01-01", "2019-12-31"),
        ]
        for low, high in checks:
            page.evaluate(
                "([lo, hi]) => { const p = document.getElementById('tr-period');"
                " p.value = 'custom'; p.dispatchEvent(new Event('change', {bubbles: true}));"
                " document.getElementById('tr-from').value = lo;"
                " document.getElementById('tr-to').value = hi;"
                " document.getElementById('tr-form').dispatchEvent("
                "   new Event('submit', {bubbles: true, cancelable: true})); }",
                [low, high],
            )
            page.wait_for_timeout(120)
            got = page.evaluate(
                # `n` là số kỳ ĐƯỢC CHỌN, đọc từ ô tổng quan — không phải số
                # thẻ đã dựng, vì danh sách dựng theo lô 100 kỳ một lần.
                "() => ({ n: Number(document.getElementById('tr-result-count').textContent),"
                " rendered: document.querySelectorAll('.tr-day').length,"
                " special: [...document.querySelectorAll("
                "   '.tr-prize-row[data-prize=special] .tr-number')].map(x => x.textContent),"
                " detail: document.getElementById('tr-empty-detail').textContent })"
            )
            expected = [d for d in dates if low <= d <= high]
            if got["n"] != len(expected):
                failures.append(f"[{low}..{high}]: hiện {got['n']} kỳ, CSDL có {len(expected)}")
                continue
            for day, shown in zip(sorted(expected, reverse=True)[:got["rendered"]],
                                  got["special"], strict=True):
                want = by_date[day]["special"].strip().zfill(5)
                if shown != want:
                    failures.append(f"{day}: giải ĐB hiện {shown!r}, CSDL {want!r}")
            if not expected and "ngoài dải dữ liệu" not in got["detail"]:
                failures.append(
                    "khoảng ngoài dải dữ liệu phải nói rõ lý do, "
                    f"đang báo: {got['detail']!r}")
            print(f"  [{low}..{high}] -> {got['n']} kỳ, khớp CSDL")

        # --- 3. Mốc nhanh ---------------------------------------------------
        for preset, want in (("10", 10), ("120", 120), ("1000", 1000), ("all", len(dates))):
            page.evaluate(
                "(value) => { const p = document.getElementById('tr-period');"
                " p.value = value; p.dispatchEvent(new Event('change', {bubbles: true})); }",
                preset,
            )
            page.wait_for_timeout(350)
            state = page.evaluate(
                "() => ({ selected: Number(document.getElementById('tr-result-count').textContent),"
                " rendered: document.querySelectorAll('.tr-day').length,"
                " more: !document.getElementById('tr-more').hidden })"
            )
            print(f"  mốc {preset:>4} -> chọn {state['selected']} kỳ, "
                  f"dựng {state['rendered']}, còn nút xem thêm: {state['more']}")
            if state["selected"] != want:
                failures.append(f"mốc {preset}: chọn {state['selected']} kỳ, mong đợi {want}")
            if state["rendered"] > 100:
                failures.append(
                    f"mốc {preset}: dựng thẳng {state['rendered']} thẻ — "
                    "phải dựng theo lô để không treo trình duyệt")
            if want > 100 and not state["more"]:
                failures.append(f"mốc {preset}: còn kỳ chưa dựng mà không có nút xem thêm")

        # --- 4. Nút "xem thêm" phải dựng tiếp đúng phần còn lại -------------
        page.evaluate(
            "() => { const p = document.getElementById('tr-period');"
            " p.value = 'all'; p.dispatchEvent(new Event('change', {bubbles: true})); }"
        )
        page.wait_for_timeout(300)
        before = page.evaluate("() => document.querySelectorAll('.tr-day').length")
        page.click("#tr-more-btn")
        page.wait_for_timeout(300)
        after = page.evaluate("() => document.querySelectorAll('.tr-day').length")
        print(f"  nút xem thêm: {before} -> {after} thẻ")
        if after != before + 100:
            failures.append(f"nút xem thêm dựng {after - before} thẻ, mong đợi 100")
        # --- 5. Đánh dấu số bằng cú nhấp -----------------------------------
        page.evaluate(
            "() => { const p = document.getElementById('tr-period');"
            " p.value = '30'; p.dispatchEvent(new Event('change', {bubbles: true}));"
            " const r = document.querySelector(\"input[name=tr-layout][value='1']\");"
            " r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true})); }"
        )
        page.wait_for_timeout(300)
        cell = page.query_selector(".tr-day .tr-prize-row[data-prize=prize3] .tr-number")
        key = cell.inner_text().strip()[-2:]
        marked = "() => document.querySelectorAll('[data-marked]').length"
        background = "(el) => getComputedStyle(el).backgroundColor"

        plain = page.evaluate(background, cell)
        if page.evaluate(marked) != 0:
            failures.append("ban đầu không được có ô nào đánh dấu sẵn")

        cell.click()
        page.wait_for_timeout(120)
        first = page.evaluate(marked)
        if first == 0:
            failures.append("bấm lần 1 không đánh dấu gì")
        if page.evaluate(background, cell) == plain:
            failures.append("bấm lần 1 không đổi màu nền")
        if not page.is_visible("#tr-mark-clear"):
            failures.append("có đánh dấu thì nút bỏ đánh dấu phải hiện")
        elsewhere = page.evaluate(
            "(k) => { const days = [...document.querySelectorAll('.tr-day')]; let n = 0;"
            " for (let i = 1; i < days.length; i += 1)"
            "   for (const c of days[i].querySelectorAll('.tr-number[data-marked]'))"
            "     if (c.textContent.trim().slice(-2) === k) n += 1;"
            " return n; }", key)
        if elsewhere == 0:
            failures.append(f"số {key} ở các kỳ khác phải cùng sáng lên")
        print(f"  đánh dấu số {key}: {first} ô sáng, {elsewhere} trong đó ở kỳ khác")

        cell.click()
        # Chờ QUÁ thời gian hiệu ứng chuyển màu (120 ms) rồi mới đo.
        # Đo đúng ở mốc 120 ms bắt được phần đuôi của hiệu ứng —
        # `rgba(253, 230, 138, 0.016)` — và báo hỏng nhầm. Trạng thái đã đúng
        # ngay lập tức; chỉ màu là còn đang tan.
        page.wait_for_timeout(400)
        if page.evaluate(marked) != 0:
            failures.append("bấm lần 2 phải bỏ đánh dấu")
        if page.evaluate(background, cell) != plain:
            failures.append("bấm lần 2 phải trả màu nền về ban đầu")
        if page.is_visible("#tr-mark-clear"):
            failures.append("hết đánh dấu thì nút phải ẩn lại")

        cell.click()
        page.wait_for_timeout(100)
        page.evaluate(
            "() => { const r = document.querySelector(\"input[name=tr-layout][value='3']\");"
            " r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true}));"
            " const p = document.getElementById('tr-period');"
            " p.value = '60'; p.dispatchEvent(new Event('change', {bubbles: true})); }"
        )
        page.wait_for_timeout(350)
        if page.evaluate(marked) == 0:
            failures.append("đánh dấu phải sống qua lần dựng lại danh sách")
        page.click("#tr-mark-clear")
        page.wait_for_timeout(120)
        if page.evaluate(marked) != 0:
            failures.append("nút bỏ đánh dấu không xoá hết")
        print("  bật/tắt, sống qua dựng lại, và xoá sạch: đạt")

        page.evaluate("() => document.querySelector('.tr-number').focus()")
        page.keyboard.press("Enter")
        page.wait_for_timeout(120)
        if page.evaluate(marked) == 0:
            failures.append("phím Enter phải đánh dấu được")
        print("  bàn phím Enter: đạt")

        browser.close()

    if failures:
        print("\nKHÔNG ĐẠT:")
        for item in failures:
            print(f"  {item}")
        return 1
    print("\nĐẠT: chân bảng thoáng ở mọi trạng thái, và mọi khoảng quá khứ khớp CSDL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
