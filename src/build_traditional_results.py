"""Dựng trang Sổ kết quả truyền thống từ cơ sở dữ liệu lịch sử cục bộ.

Toàn bộ lịch sử được nhúng thẳng vào trang, ở dạng nén. Trang không gọi mạng
ra ngoài và không phụ thuộc dịch vụ nào — mở là chạy.

Vì sao nén, và vì sao điều đó là phần SỬA LỖI chứ không phải tối ưu
==================================================================
Bản trước nhúng ``limit=500`` kỳ ở dạng JSON đầy đủ, mỗi kỳ mang theo ``id``,
``region``, ``province``, ``status``, ``source``, nhãn và độ rộng của từng
giải, cộng hai mươi mảng ``head_tail``. Kết quả đo được:

    500 kỳ, JSON đầy đủ     658 KB    phủ 2025-04-29 → 2026-09-14 (503 ngày)
    2 399 kỳ, dạng nén      281 KB    phủ 2020-01-01 → 2026-09-14

Tức bản nén vừa NHỎ HƠN 2,3 lần vừa phủ nhiều hơn 4,8 lần. Mọi thứ bị bỏ đi
đều là thứ suy lại được ở trình duyệt: nhãn giải là hằng số, ``head_tail``
tính từ chính các giải, còn ``region``/``province``/``status``/``source``
giống hệt nhau ở cả 2 399 kỳ.

Đây là nguyên nhân gốc của lỗi "không tra cứu được quá khứ": người dùng chọn
một ngày trước 2025-04-29 thì bộ lọc chạy đúng, trả về rỗng, và trang báo
"Chưa có kết quả trong khoảng đã chọn" — đọc như thể hôm ấy không quay.
"""

from __future__ import annotations

import argparse
import csv
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Sequence

from ui_theme import app_shell_close, app_shell_open, stylesheet_link
from web_security import json_for_html_script, security_meta_tags

#: Thứ tự giải, nhãn và độ rộng. Bên JS giữ một bản y hệt; chúng phải khớp
#: nhau và ``tests/test_traditional_results_page.py`` kiểm điều đó.
PRIZE_SPEC: tuple[tuple[str, str, int, int], ...] = (
    # mã, nhãn, số lượng, độ rộng
    ("special", "Đặc Biệt", 1, 5),
    ("prize1", "Giải Nhất", 1, 5),
    ("prize2", "Giải Nhì", 2, 5),
    ("prize3", "Giải Ba", 6, 5),
    ("prize4", "Giải Tư", 4, 4),
    ("prize5", "Giải Năm", 6, 4),
    ("prize6", "Giải Sáu", 3, 3),
    ("prize7", "Giải Bảy", 4, 2),
)
PRIZE_ORDER = tuple(code for code, _, _, _ in PRIZE_SPEC)
PRIZE_WIDTHS = {code: width for code, _, _, width in PRIZE_SPEC}
PRIZE_LABELS = {code: label for code, label, _, _ in PRIZE_SPEC}
PRIZE_COUNTS = {code: count for code, _, count, _ in PRIZE_SPEC}
PRIZE_FIELDS = {
    "special": ("special",),
    "prize1": ("prize1",),
    "prize2": ("prize2_1", "prize2_2"),
    "prize3": tuple(f"prize3_{i}" for i in range(1, 7)),
    "prize4": tuple(f"prize4_{i}" for i in range(1, 5)),
    "prize5": tuple(f"prize5_{i}" for i in range(1, 7)),
    "prize6": tuple(f"prize6_{i}" for i in range(1, 4)),
    "prize7": tuple(f"prize7_{i}" for i in range(1, 5)),
}

#: Độ dài một dòng nén: 10 ký tự ngày + 107 chữ số giải.
DATE_WIDTH = 10
PRIZE_DIGITS = sum(PRIZE_COUNTS[code] * PRIZE_WIDTHS[code] for code in PRIZE_ORDER)
ROW_WIDTH = DATE_WIDTH + PRIZE_DIGITS


def _asset(name: str) -> str:
    path = Path(__file__).resolve().parent / "templates" / name
    return path.read_text(encoding="utf-8")


def encode_row(row: dict[str, str]) -> str | None:
    """Một kỳ thành một chuỗi ``YYYY-MM-DD`` + 107 chữ số, hoặc ``None``.

    Trả ``None`` cho mọi kỳ thiếu dữ liệu. KHÔNG bịa số 0 thay cho ô trống:
    một kỳ thiếu phải biến mất khỏi sổ, chứ không được hiện ra như thể giải
    ấy về 0000.
    """
    draw_date = str(row.get("date", ""))[:DATE_WIDTH]
    try:
        date.fromisoformat(draw_date)
    except ValueError:
        return None
    digits: list[str] = []
    for code in PRIZE_ORDER:
        width = PRIZE_WIDTHS[code]
        for field in PRIZE_FIELDS[code]:
            raw = row.get(field)
            if raw is None or not str(raw).strip():
                return None
            value = str(raw).strip().zfill(width)
            if len(value) != width or not (value.isascii() and value.isdigit()):
                return None
            digits.append(value)
    encoded = draw_date + "".join(digits)
    return encoded if len(encoded) == ROW_WIDTH else None


def load_rows(repo_root: Path, *, limit: int | None = None) -> list[str]:
    """Nạp lịch sử đã nén, kỳ mới nhất trước.

    ``limit=None`` nghĩa là LẤY HẾT — và đó là mặc định có chủ ý. Giới hạn
    mặc định 500 của bản trước chính là lỗi "không tra cứu được quá khứ".
    """
    path = repo_root / "data" / "xsmb.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    encoded = [value for row in rows if (value := encode_row(row)) is not None]
    encoded.sort(reverse=True)
    return encoded if limit is None else encoded[:limit]


def embedded_payload(rows: list[str], *, generated: str) -> dict[str, object]:
    latest = rows[0][:DATE_WIDTH] if rows else None
    earliest = rows[-1][:DATE_WIDTH] if rows else None
    return {
        "schema_version": 2,
        "generated_at_utc": generated,
        "row_width": ROW_WIDTH,
        "total_draws": len(rows),
        "latest_draw_date": latest,
        "earliest_draw_date": earliest,
        "timezone": "Asia/Ho_Chi_Minh",
        "rows": rows,
    }


#: Các mốc nhanh. Trang tham chiếu có 11 lựa chọn (10/30/60/90/100/120…);
#: bản trước chỉ có bốn, nên không có cách nào xem xa hơn 100 kỳ ngoài việc
#: tự gõ ngày — mà gõ ngày thì lại rơi ra ngoài cửa sổ 500 kỳ đã nhúng.
PERIOD_PRESETS: tuple[tuple[str, str], ...] = (
    ("10", "10 kỳ gần nhất"),
    ("30", "30 kỳ gần nhất"),
    ("60", "60 kỳ gần nhất"),
    ("90", "90 kỳ gần nhất"),
    ("100", "100 kỳ gần nhất"),
    ("120", "120 kỳ gần nhất"),
    ("200", "200 kỳ gần nhất"),
    ("300", "300 kỳ gần nhất"),
    ("500", "500 kỳ gần nhất"),
    ("1000", "1000 kỳ gần nhất"),
    ("all", "Toàn bộ lịch sử"),
    ("custom", "Chọn khoảng ngày"),
)

#: Số cột hiển thị. Trang tham chiếu dùng bốn nút chọn bố cục.
LAYOUT_CHOICES: tuple[tuple[str, str], ...] = (
    ("1", "1 cột"),
    ("2", "2 cột"),
    ("3", "3 cột"),
    ("4", "4 cột"),
)


def _period_options() -> str:
    return "".join(
        f'<option value="{value}"{" selected" if value == "30" else ""}>{label}</option>'
        for value, label in PERIOD_PRESETS
    )


def _layout_radios() -> str:
    return "".join(
        f'<label class="tr-chip"><input type="radio" name="tr-layout" value="{value}"'
        f'{" checked" if value == "1" else ""}><span>{label}</span></label>'
        for value, label in LAYOUT_CHOICES
    )


def render_page(payload: dict[str, object]) -> str:
    latest = payload.get("latest_draw_date") or ""
    earliest = payload.get("earliest_draw_date") or ""
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{security_meta_tags()}
{stylesheet_link()}
<title>Sổ kết quả truyền thống · Xổ số Miền Bắc</title>
<style>{_asset("traditional_results.css")}</style>
</head><body>
{app_shell_open("so-ket-qua-truyen-thong.html", wide=True)}
<header class="tr-hero">
  <div>
    <p class="tr-eyebrow">KẾT QUẢ XỔ SỐ KIẾN THIẾT MIỀN BẮC</p>
    <h1>Sổ kết quả truyền thống</h1>
    <p>Tra cứu đầy đủ các giải và bảng lô tô đầu đuôi của mọi kỳ quay, từ
    {earliest} đến {latest}.</p>
  </div>
  <div class="tr-trust" aria-label="Phạm vi dữ liệu">
    <span class="tr-status-dot" aria-hidden="true"></span>
    <strong>Sổ KQ XSMB</strong><small>{payload.get("total_draws", 0)} kỳ đã lưu</small>
  </div>
</header>

<section class="tr-filter" aria-labelledby="tr-filter-title">
  <div class="tr-filter-head">
    <div><p class="tr-section-kicker">BỘ LỌC TRA CỨU</p><h2 id="tr-filter-title">Chọn dữ liệu cần xem</h2></div>
    <p id="tr-source-status" class="tr-source-status" role="status" aria-live="polite"></p>
  </div>
  <form id="tr-form" class="tr-form">
    <label>Khoảng thời gian
      <select id="tr-period" name="period">{_period_options()}</select>
    </label>
    <div class="tr-custom-dates" id="tr-custom-dates" hidden>
      <label>Từ ngày<input id="tr-from" name="from" type="date"
        min="{earliest}" max="{latest}" value="{earliest}"></label>
      <label>Đến ngày<input id="tr-to" name="to" type="date"
        min="{earliest}" max="{latest}" value="{latest}"></label>
    </div>
    <div class="tr-actions">
      <button class="tr-btn tr-btn-primary" type="submit">Xem kết quả</button>
      <button class="tr-btn" id="tr-export-csv" type="button">Tải CSV</button>
      <button class="tr-btn" id="tr-export-xlsx" type="button">Tải Excel</button>
      <button class="tr-btn" id="tr-print" type="button">In sổ</button>
    </div>
  </form>
  <div class="tr-view-options">
    <fieldset class="tr-chips">
      <legend>Bố cục</legend>
      {_layout_radios()}
    </fieldset>
    <fieldset class="tr-chips">
      <legend>Hiển thị</legend>
      <label class="tr-chip"><input type="checkbox" id="tr-toggle-headtail" checked><span>Bảng đầu đuôi</span></label>
      <label class="tr-chip"><input type="checkbox" id="tr-toggle-loto" checked><span>Dãy lô tô</span></label>
      <label class="tr-chip"><input type="checkbox" id="tr-toggle-tail" checked><span>Tô đậm 2 số cuối</span></label>
    </fieldset>
  </div>
</section>

<section class="tr-summary" aria-label="Tổng quan kết quả">
  <div><span>Số kỳ hiển thị</span><strong id="tr-result-count">0</strong></div>
  <div><span>Kỳ mới nhất</span><strong id="tr-latest">—</strong></div>
  <div><span>Kỳ cũ nhất</span><strong id="tr-oldest">—</strong></div>
  <div><span>Dữ liệu máy chủ</span><strong id="tr-total-count">0</strong></div>
</section>

<section id="tr-results" class="tr-results" data-layout="1" aria-live="polite">
  <div id="tr-more" class="tr-more" hidden>
    <button class="tr-btn" id="tr-more-btn" type="button">Xem thêm</button>
  </div>
</section>
<div id="tr-empty" class="tr-empty" hidden>
  <strong>Chưa có kết quả trong khoảng đã chọn.</strong>
  <span id="tr-empty-detail"></span>
</div>
{app_shell_close("so-ket-qua-truyen-thong.html")}

<script id="tr-embedded-data" type="application/json">{json_for_html_script(payload)}</script>
<script>
{_asset("traditional_results.js")}
</script>
</body></html>
"""


def build(repo_root: Path, docs_dir: Path, *, generated: str | None = None) -> Path:
    rows = load_rows(repo_root)
    if not rows:
        raise SystemExit("không có kỳ hợp lệ để dựng Sổ kết quả")
    stamp = generated or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    docs_dir.mkdir(parents=True, exist_ok=True)
    target = docs_dir / "so-ket-qua-truyen-thong.html"
    target.write_text(render_page(embedded_payload(rows, generated=stamp)), encoding="utf-8")
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dựng trang Sổ kết quả truyền thống.")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    target = build(root, root / args.docs_dir)
    print(f"đã ghi {target} ({target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
