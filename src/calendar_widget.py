"""Lịch vạn niên phía trình duyệt, kèm kết quả Đặc Biệt đã xác thực."""

import csv
import re
from datetime import date
from pathlib import Path

from web_security import json_for_html_script

TEMPLATES = Path(__file__).resolve().parent / "templates"


def load_special_results(repo_root: Path) -> dict[str, str]:
    """Chỉ lấy ngày hợp lệ và giải đủ độ rộng; không suy ra số từ dữ liệu thiếu."""
    path = repo_root / "data" / "xsmb.csv"
    if not path.exists():
        return {}
    results = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            key, value = (row.get("date") or "").strip(), (row.get("special") or "").strip()
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", key) or not re.fullmatch(r"[0-9]{1,5}", value):
                continue
            try:
                date.fromisoformat(key)
            except ValueError:
                continue
            results[key] = value.zfill(5)
    return dict(sorted(results.items()))


def render_calendar(repo_root: Path) -> str:
    """Nhúng dữ liệu và tài nguyên để lịch hoạt động cả khi mở trang từ tệp."""
    results = load_special_results(repo_root)
    payload = json_for_html_script({"results": results, "latest": max(results, default="")})
    css = (TEMPLATES / "calendar_widget.css").read_text(encoding="utf-8")
    scripts = "\n".join((TEMPLATES / name).read_text(encoding="utf-8")
                        for name in ("vietnamese_calendar.js", "calendar_widget.js"))
    months = "".join(f'<option value="{month}">Tháng {month:02d}</option>' for month in range(1, 13))
    weekdays = "".join(f'<span role="columnheader">{day}</span>' for day in
                       ("Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "CN"))
    return f"""
<style id="app-calendar-style">{css}</style>
<div id="app-calendar" class="app-calendar" aria-label="Lịch vạn niên">
  <div class="app-calendar-toolbar">
    <div class="app-calendar-heading"><span class="app-calendar-eyebrow">LỊCH VIỆT NAM · UTC+7</span>
      <h3 id="app-calendar-title">Lịch vạn niên</h3>
      <p id="app-calendar-summary" role="status" aria-live="polite"></p></div>
    <div class="app-calendar-controls">
      <button type="button" id="app-calendar-prev" aria-label="Tháng trước">‹</button>
      <label><span class="app-sr">Chọn tháng</span><select id="app-calendar-month">{months}</select></label>
      <label><span class="app-sr">Chọn năm, từ 1900 đến 2099</span><input id="app-calendar-year" type="number" min="1900" max="2099" step="1" inputmode="numeric" value="2026" /></label>
      <button type="button" id="app-calendar-next" aria-label="Tháng sau">›</button>
      <button type="button" id="app-calendar-today" class="app-calendar-today">Hôm nay</button>
    </div>
  </div>
  <div class="app-calendar-layout">
    <div class="app-calendar-month-view">
      <div class="app-calendar-grid" role="grid" aria-labelledby="app-calendar-title">
        <div class="app-calendar-weekdays" role="row">{weekdays}</div>
        <div id="app-calendar-days" role="rowgroup"></div>
      </div>
      <div class="app-calendar-legend"><span><i class="app-calendar-dot"></i>Ngày lễ / ngày rằm</span>
        <span><b>ĐB</b> Giải Đặc Biệt đủ 5 số</span><span>Số nhỏ: ngày âm lịch</span></div>
      <p class="app-calendar-hint">Chọn một ngày để xem chi tiết. Dùng phím mũi tên để chuyển ngày.</p>
    </div>
    <aside id="app-calendar-detail" class="app-calendar-detail" aria-label="Thông tin ngày đã chọn"></aside>
  </div>
  <noscript><p>Bật JavaScript để xem lịch âm và kết quả Đặc Biệt theo ngày.</p></noscript>
</div>
<script id="app-calendar-data" type="application/json">{payload}</script>
<script>{scripts}</script>
"""
