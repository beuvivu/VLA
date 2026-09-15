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

#: Sàn cỡ chữ của ô cặp lô tô, mọi bố cục. Bản trước tụt xuống 9px ở bố cục
#: 4 cột — đó là lý do có yêu cầu "tăng cỡ chữ".
MIN_LOTO_PAIR_FS = 11.0


def _weekday(value: str) -> int:
    """Thứ của một nhãn ngày `YYYY-MM-DD`, không dính múi giờ."""
    from datetime import date as _date

    year, month, day = (int(part) for part in value.split("-"))
    # `isoweekday()` cho thứ Hai = 1 … Chủ nhật = 7; JavaScript dùng Chủ
    # nhật = 0, nên đưa về cùng quy ước với trang.
    return _date(year, month, day).isoweekday() % 7
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
                # Soi thứ NHÌN THẤY, không soi thuộc tính. `hidden` chỉ ẩn được
                # nhờ `display:none` mặc định của trình duyệt, và bất kỳ quy tắc
                # `display` nào của tác giả cũng thắng nó — đúng lỗi đã để ô
                # "Chưa có kết quả" nằm lì dưới trang suốt.
                " more: getComputedStyle(document.getElementById('tr-more'))"
                "   .display !== 'none' })"
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
        # --- 4b. `hidden` phải THẬT SỰ ẩn -----------------------------------
        #
        # Thuộc tính `hidden` chỉ ẩn nhờ một dòng `display:none` trong biểu
        # định kiểu mặc định của trình duyệt, và BẤT KỲ quy tắc `display` nào
        # của tác giả cũng thắng nó. Ba phần tử của trang từng rơi vào bẫy ấy:
        # ô chọn ngày (70px), nút xem thêm (56px) và ô "Chưa có kết quả"
        # (220px) — cả ba mang `hidden` đúng lúc và cả ba hiện ra suốt.
        #
        # Quét ở MỌI trạng thái dưới đây, vì phần tử nào mang `hidden` còn tuỳ
        # bộ lọc đang chọn.
        leaked: list[str] = []
        for setup in (
            "p.value = '30'",
            "p.value = 'all'",
            "p.value = 'custom'",
        ):
            page.evaluate(
                "(code) => { const p = document.getElementById('tr-period');"
                " eval(code); p.dispatchEvent(new Event('change', {bubbles: true})); }",
                setup,
            )
            page.wait_for_timeout(250)
            leaked += page.evaluate(
                "(label) => [...document.querySelectorAll('[hidden]')]"
                "  .filter(e => getComputedStyle(e).display !== 'none')"
                "  .map(e => `${label}: #${e.id || e.className} vẫn hiện"
                " (${Math.round(e.getBoundingClientRect().height)}px)`)",
                setup,
            )
        if leaked:
            failures.extend(leaked)
        print("  mọi phần tử mang `hidden` đều thật sự bị ẩn ở 3 trạng thái bộ lọc")

        # --- 5. Bảng lô tô theo đầu ----------------------------------------
        #
        # Trả TOÀN BỘ trạng thái về mặc định trước: phép quét ở trên kết thúc
        # ở bề rộng 390 px với cả hai bảng phụ ĐANG ẨN. Không đặt lại thì
        # bảng lô tô có bề rộng 0 và mọi phép so kích thước đạt một cách rỗng
        # tuếch — bản đầu của đoạn này in ra "kéo giãn 0/0px" rồi báo đạt.
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.evaluate(
            "() => { const p = document.getElementById('tr-period');"
            " p.value = '30'; p.dispatchEvent(new Event('change', {bubbles: true}));"
            " const r = document.querySelector(\"input[name=tr-layout][value='1']\");"
            " r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true}));"
            " for (const id of ['tr-toggle-headtail', 'tr-toggle-loto', 'tr-toggle-tail']) {"
            "   const c = document.getElementById(id); c.checked = true;"
            "   c.dispatchEvent(new Event('change', {bubbles: true})); } }"
        )
        page.wait_for_timeout(300)
        table = page.evaluate(
            "() => { const t = document.querySelector('.tr-day .tr-head-tail table');"
            " const wrap = t.closest('.tr-head-tail-scroll').getBoundingClientRect();"
            " return { columns: [...t.querySelectorAll('th')].map(x => x.textContent.trim()),"
            "   cells_per_row: t.querySelector('tbody tr').children.length,"
            "   head_colour: getComputedStyle(t.querySelector('.tr-digit')).color,"
            "   special_colour: getComputedStyle(document.querySelector("
            "     '.tr-prize-row[data-prize=special] .tr-prize-label')).color,"
            "   table_width: Math.round(t.getBoundingClientRect().width),"
            "   frame_width: Math.round(wrap.width) }; }"
        )
        # "Lô tô" chứ không phải "Đuôi tương ứng": ô nay chứa CẶP hai chữ số,
        # nên nhãn cũ mô tả sai thứ nằm bên dưới nó. Trùng luôn nhãn của trang
        # tham chiếu (đã đọc cấu trúc: cột `['Đầu', 'Lô tô']`).
        if table["columns"] != ["Đầu", "Lô tô"]:
            failures.append(f"bảng lô tô phải còn đúng hai cột, đang là {table['columns']}")
        if table["cells_per_row"] != 2:
            failures.append(f"mỗi hàng phải có 2 ô, đang có {table['cells_per_row']}")
        if table["head_colour"] != table["special_colour"]:
            failures.append(
                f"màu số đầu {table['head_colour']} phải trùng màu giải đặc biệt "
                f"{table['special_colour']}")
        # Chặn phép so rỗng: bảng bị ẩn cho bề rộng 0, và `0 < -3` là sai nên
        # phép so dưới sẽ "đạt" mà không kiểm được gì.
        if table["frame_width"] < 200:
            failures.append(
                f"khung bảng lô tô chỉ rộng {table['frame_width']}px — có lẽ đang bị ẩn")
        elif table["table_width"] < table["frame_width"] - 3:
            failures.append(
                f"bảng chưa kéo giãn kín khung: {table['table_width']}/{table['frame_width']}")
        print(f"  bảng lô tô: {table['columns']}, kéo giãn "
              f"{table['table_width']}/{table['frame_width']}px, màu khớp giải đặc biệt")

        # --- 6. Đánh dấu: chế độ mặc định là MỘT Ô --------------------------
        marked = "() => document.querySelectorAll('[data-marked]').length"
        pair_mode = page.query_selector("#tr-pair-mode")
        if pair_mode.is_checked():
            failures.append("chế độ đánh dấu cặp phải TẮT mặc định")
        cell = page.query_selector(".tr-day .tr-prize-row[data-prize=prize3] .tr-number")
        pair = cell.inner_text().strip()[-2:]
        plain = page.evaluate("(el) => getComputedStyle(el).backgroundColor", cell)

        cell.click()
        page.wait_for_timeout(150)
        single = page.evaluate(marked)
        if single != 1:
            failures.append(f"mặc định phải sáng ĐÚNG một ô, đang sáng {single}")
        if page.evaluate("(el) => getComputedStyle(el).backgroundColor", cell) == plain:
            failures.append("bấm lần 1 không đổi màu nền")
        if not page.is_visible("#tr-mark-clear"):
            failures.append("có đánh dấu thì nút bỏ đánh dấu phải hiện")

        cell.click()
        # Chờ QUÁ thời gian hiệu ứng chuyển màu (120 ms) rồi mới đo màu.
        page.wait_for_timeout(400)
        if page.evaluate(marked) != 0:
            failures.append("bấm lần 2 phải bỏ đánh dấu")
        if page.evaluate("(el) => getComputedStyle(el).backgroundColor", cell) != plain:
            failures.append("bấm lần 2 phải trả màu nền về ban đầu")

        mini = page.query_selector(".tr-day .tr-mini")
        mini.click()
        page.wait_for_timeout(150)
        if page.evaluate(marked) != 1:
            failures.append("ô mini ở chế độ mặc định cũng chỉ được sáng một ô")
        mini.click()
        page.wait_for_timeout(150)
        print("  mặc định: bấm ô giải và ô mini đều sáng đúng một ô")

        # --- 7. Đánh dấu: chế độ CẶP TRÙNG ----------------------------------
        pair_mode.check()
        page.wait_for_timeout(100)
        cell.click()
        page.wait_for_timeout(200)
        group = page.evaluate(
            "(want) => { const lit = [...document.querySelectorAll('[data-marked]')];"
            " return { total: lit.length,"
            "   all_same_pair: lit.every(n =>"
            "     (n.dataset.value || n.textContent.trim().slice(-2)) === want),"
            "   minis: lit.filter(n => n.classList.contains('tr-mini')).length }; }", pair)
        if group["total"] <= 1:
            failures.append("chế độ cặp phải làm sáng nhiều ô")
        if not group["all_same_pair"]:
            failures.append("có ô sáng không đúng cặp số")
        if group["minis"] == 0:
            failures.append(
                "ô mini cùng cặp phải sáng theo — bản trước khoá mini bằng MỘT chữ số "
                "nên nó không bao giờ khớp với ô giải")
        print(f"  chế độ cặp: cặp {pair} làm sáng {group['total']} ô "
              f"({group['minis']} trong đó là ô mini)")

        cell.click()
        page.wait_for_timeout(200)
        if page.evaluate(marked) != 0:
            failures.append("bấm lại ô đang sáng theo cặp phải tắt CẢ NHÓM")

        # --- 8. Đổi chế độ không được xoá dấu đã có -------------------------
        pair_mode.uncheck()
        page.wait_for_timeout(100)
        cell.click()
        page.wait_for_timeout(150)
        states = [page.evaluate(marked)]
        pair_mode.check()
        page.wait_for_timeout(150)
        states.append(page.evaluate(marked))
        pair_mode.uncheck()
        page.wait_for_timeout(150)
        states.append(page.evaluate(marked))
        if states != [1, 1, 1]:
            failures.append(f"đổi chế độ không được làm mất dấu đã có: {states}")
        print("  đổi chế độ giữ nguyên dấu đã đánh")

        page.evaluate(
            "() => { const r = document.querySelector(\"input[name=tr-layout][value='3']\");"
            " r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true})); }"
        )
        page.wait_for_timeout(300)
        if page.evaluate(marked) == 0:
            failures.append("đánh dấu phải sống qua lần dựng lại danh sách")
        page.click("#tr-mark-clear")
        page.wait_for_timeout(150)
        if page.evaluate(marked) != 0:
            failures.append("nút bỏ đánh dấu không xoá hết")

        page.evaluate("() => document.querySelector('.tr-number').focus()")
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)
        if page.evaluate(marked) == 0:
            failures.append("phím Enter phải đánh dấu được")
        print("  sống qua dựng lại, xoá sạch, bàn phím Enter: đạt")

        # --- Bộ lọc thứ trong tuần ------------------------------------
        #
        # Kiểm bằng cách ĐỌC LẠI NGÀY trên các thẻ đang hiện rồi tự tính thứ,
        # chứ không hỏi lại chính hàm của trang — hỏi lại thì hai bên cùng sai
        # vẫn "khớp".
        #
        # Chạy ở HAI múi giờ. `getDay()` đọc theo múi giờ máy người xem, nên
        # một bản cài đặt hỏng vẫn đúng ở Việt Nam và chỉ sai ở nửa kia địa
        # cầu — đo một múi giờ là bỏ lọt đúng lỗi ấy. Đã đo: với 2026-09-14
        # (thứ Hai), `new Date(d).getDay()` trả 0 ở America/Los_Angeles.
        print("\nBộ lọc thứ trong tuần:")
        before_weekday = len(failures)
        weekday_js = """() => {
          const days = [...document.querySelectorAll(".tr-day time")].map((t) => {
            const [y, m, d] = t.dateTime.split("-").map(Number);
            return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
          });
          const labels = [...document.querySelectorAll(".tr-day time")]
            .map((t) => t.textContent.split(",")[0].trim().toLowerCase());
          return {count: days.length, days: [...new Set(days)],
                  labels: [...new Set(labels)]};
        }"""
        names = {0: "chủ nhật", 1: "thứ hai", 2: "thứ ba", 3: "thứ tư",
                 4: "thứ năm", 5: "thứ sáu", 6: "thứ bảy"}
        for timezone in ("Asia/Ho_Chi_Minh", "America/Los_Angeles"):
            context = browser.new_context(viewport={"width": 1440, "height": 1000},
                                          timezone_id=timezone)
            tz_page = context.new_page()
            tz_page.on("pageerror", lambda exc: failures.append(f"lỗi JS: {exc}"))
            tz_page.goto(PAGE.resolve().as_uri(), wait_until="load")
            tz_page.wait_for_timeout(700)
            tz_page.select_option("#tr-period", "500")
            tz_page.wait_for_timeout(300)
            for value, name in names.items():
                tz_page.select_option("#tr-weekday", str(value))
                tz_page.wait_for_timeout(200)
                found = tz_page.evaluate(weekday_js)
                label = f"{timezone} {name}"
                if found["count"] == 0:
                    failures.append(f"{label}: không kỳ nào hiện ra")
                    continue
                if found["days"] != [value]:
                    failures.append(
                        f"{label}: lọc ra các thứ {found['days']}, phải chỉ có [{value}]")
                # Nhãn NGƯỜI XEM THẤY phải khớp thứ đã lọc. Logic đúng mà nhãn
                # lệch thì với người dùng vẫn là hỏng.
                if found["labels"] != [name]:
                    failures.append(
                        f"{label}: nhãn trên thẻ là {found['labels']}, phải là ['{name}']")
            # Rỗng vì lọc thứ phải nói khác rỗng vì khoảng sai.
            tz_page.select_option("#tr-period", "custom")
            tz_page.wait_for_timeout(200)
            tz_page.fill("#tr-from", dates[-3])
            tz_page.fill("#tr-to", dates[-1])
            tz_page.dispatch_event("#tr-to", "change")
            tz_page.wait_for_timeout(250)
            in_range = tz_page.evaluate("() => document.querySelectorAll('.tr-day').length")
            missing = next(
                (d for d in range(7)
                 if d not in {_weekday(x) for x in dates[-3:]}), None)
            if missing is not None:
                tz_page.select_option("#tr-weekday", str(missing))
                tz_page.wait_for_timeout(250)
                state = tz_page.evaluate("""() => ({
                  n: document.querySelectorAll('.tr-day').length,
                  shown: getComputedStyle(document.getElementById('tr-empty')).display !== 'none',
                  detail: document.getElementById('tr-empty-detail').textContent,
                })""")
                if state["n"] != 0 or not state["shown"]:
                    failures.append(f"{timezone}: lọc thứ rỗng nhưng không hiện ô giải thích")
                elif names[missing] not in state["detail"].lower():
                    failures.append(
                        f"{timezone}: lời giải thích không nhắc tới thứ đã chọn:"
                        f" {state['detail']!r}")
            context.close()
        # Đếm lỗi CỦA RIÊNG mục này. Bản đầu tôi viết `if not failures`, tức
        # đọc danh sách lỗi toàn cục — nó in "xem lỗi bên dưới" cho mục này
        # trong khi lỗi thật nằm ở một mục hoàn toàn khác. Một dòng báo cáo
        # chỉ sai chỗ thôi cũng đủ làm người đọc đi tìm nhầm hướng.
        print(f"  7 thứ × 2 múi giờ, nhãn khớp, nhánh rỗng có giải thích:"
              f" {'đạt' if len(failures) == before_weekday else 'KHÔNG ĐẠT'}")

        # --- Bảng lô tô: cỡ chữ, cặp đầy đủ, không vỡ khi nhiều cột --------
        print("\nBảng lô tô theo đầu:")
        before_loto = len(failures)
        loto_js = """() => {
          const digit = document.querySelector(".tr-digit");
          const mini = document.querySelector(".tr-mini");
          const cs = (n) => getComputedStyle(n);
          let overflow = 0, clipped = 0;
          for (const d of document.querySelectorAll(".tr-day")) {
            overflow = Math.max(overflow, d.scrollWidth - d.clientWidth);
          }
          for (const n of document.querySelectorAll(".tr-mini")) {
            if (n.scrollWidth > n.clientWidth + 1) clipped += 1;
          }
          const pairs = [...document.querySelectorAll(".tr-mini")].map((n) => n.textContent.trim());
          return {
            digitFs: parseFloat(cs(digit).fontSize), digitColor: cs(digit).color,
            miniFs: parseFloat(cs(mini).fontSize),
            notPairs: pairs.filter((v) => !/^\d{2}$/.test(v)).slice(0, 4),
            overflow, clipped,
          };
        }"""
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.select_option("#tr-period", "30")
        page.select_option("#tr-weekday", "all")
        page.wait_for_timeout(300)
        special_color = page.evaluate(
            "() => getComputedStyle(document.querySelector("
            "'.tr-prize-row[data-prize=special] .tr-prize-label')).color")
        for width in (1440, 1180, 900, 640):
            page.set_viewport_size({"width": width, "height": 1000})
            for layout in ("1", "2", "3", "4"):
                page.evaluate(
                    "(value) => { const r = document.querySelector("
                    "`input[name=tr-layout][value='${value}']`);"
                    " r.checked = true; r.dispatchEvent(new Event('change', {bubbles: true})); }",
                    layout,
                )
                page.wait_for_timeout(120)
                found = page.evaluate(loto_js)
                label = f"rộng={width} bố cục={layout}"
                if found["overflow"] > 0:
                    failures.append(f"{label}: thẻ tràn ngang {found['overflow']}px")
                if found["clipped"]:
                    failures.append(f"{label}: {found['clipped']} ô lô tô bị cắt chữ")
                if found["notPairs"]:
                    failures.append(
                        f"{label}: ô lô tô phải là cặp hai chữ số, thấy {found['notPairs']}")
                # Ngưỡng đọc được. Bản trước để 9px ở bố cục 4 cột — nhỏ hơn
                # cả cỡ chữ chú thích, và đó chính là thứ được yêu cầu sửa.
                if found["miniFs"] < MIN_LOTO_PAIR_FS:
                    failures.append(
                        f"{label}: cỡ chữ cặp lô tô {found['miniFs']}px"
                        f" < {MIN_LOTO_PAIR_FS}px")
                if found["digitFs"] <= found["miniFs"]:
                    failures.append(
                        f"{label}: cột Đầu ({found['digitFs']}px) phải to hơn"
                        f" ô cặp ({found['miniFs']}px)")
                if found["digitColor"] != special_color:
                    failures.append(
                        f"{label}: cột Đầu màu {found['digitColor']},"
                        f" phải trùng màu giải đặc biệt {special_color}")
        print(f"  16 tổ hợp: cặp đủ hai chữ số, cỡ chữ >= {MIN_LOTO_PAIR_FS}px,"
              f" cột Đầu đỏ, không tràn/không cắt:"
              f" {'đạt' if len(failures) == before_loto else 'KHÔNG ĐẠT'}")

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
