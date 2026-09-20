"""Dung trang So ket qua truyen thong tu co so du lieu lich su cuc bo.

Toan bo lich su duoc nhung thang vao trang, o dang nen. Trang khong goi mang
ra ngoai va khong phu thuoc dich vu nao — mo la chay.
"""

from __future__ import annotations

import argparse
import csv
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Sequence

from ui_theme import app_shell_close, app_shell_open
from css_links import stylesheet_link
from web_security import json_for_html_script, security_meta_tags
from page_output import write_page

PRIZE_SPEC: tuple[tuple[str, str, int, int], ...] = (
    ("special", "Dac Biet", 1, 5),
    ("prize1", "Giai Nhat", 1, 5),
    ("prize2", "Giai Nhi", 2, 5),
    ("prize3", "Giai Ba", 6, 5),
    ("prize4", "Giai Tu", 4, 4),
    ("prize5", "Giai Nam", 6, 4),
    ("prize6", "Giai Sau", 3, 3),
    ("prize7", "Giai Bay", 4, 2),
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

DATE_WIDTH = 10
PRIZE_DIGITS = sum(PRIZE_COUNTS[code] * PRIZE_WIDTHS[code] for code in PRIZE_ORDER)
ROW_WIDTH = DATE_WIDTH + PRIZE_DIGITS


def _asset(name: str) -> str:
    path = Path(__file__).resolve().parent / "templates" / name
    return path.read_text(encoding="utf-8")


def encode_row(row: dict[str, str]) -> str | None:
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


PERIOD_PRESETS: tuple[tuple[str, str], ...] = (
    ("10", "10 ky gan nhat"),
    ("30", "30 ky gan nhat"),
    ("60", "60 ky gan nhat"),
    ("90", "90 ky gan nhat"),
    ("100", "100 ky gan nhat"),
    ("120", "120 ky gan nhat"),
    ("200", "200 ky gan nhat"),
    ("300", "300 ky gan nhat"),
    ("500", "500 ky gan nhat"),
    ("1000", "1000 ky gan nhat"),
    ("all", "Toan bo lich su"),
    ("custom", "Chon khoang ngay"),
)

WEEKDAY_CHOICES: tuple[tuple[str, str], ...] = (
    ("all", "Tat ca cac thu"),
    ("1", "Thu hai"),
    ("2", "Thu ba"),
    ("3", "Thu tu"),
    ("4", "Thu nam"),
    ("5", "Thu sau"),
    ("6", "Thu bay"),
    ("0", "Chu nhat"),
)

LAYOUT_CHOICES: tuple[tuple[str, str], ...] = (
    ("1", "1 cot"),
    ("2", "2 cot"),
    ("3", "3 cot"),
    ("4", "4 cot"),
)


def _period_options() -> str:
    return "".join(
        f'<option value="{value}"{" selected" if value == "30" else ""}>{label}</option>'
        for value, label in PERIOD_PRESETS
    )


def _weekday_options() -> str:
    return "".join(
        f'<option value="{value}"{" selected" if value == "all" else ""}>{label}</option>'
        for value, label in WEEKDAY_CHOICES
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
<title>So ket qua truyen thong · Xo so Mien Bac</title>
<style>{_asset("traditional_results.css")}</style>
</head><body>
{app_shell_open("so-ket-qua-truyen-thong.html", wide=True)}
<header class="tr-hero">
  <div>
    <p class="tr-eyebrow">KET QUA XO SO KIEN THIET MIEN BAC</p>
    <h1>So ket qua truyen thong</h1>
    <p>Tra cuu day du cac giai va bang LOTO dau duoi, tu {earliest} den {latest}.</p>
  </div>
  <div class="tr-trust" aria-label="Pham vi du lieu">
    <span class="tr-status-dot" aria-hidden="true"></span>
    <strong>SO KET QUA XSMB</strong><small>{payload.get("total_draws", 0)} ky da luu</small>
  </div>
</header>

<section class="tr-filter" aria-labelledby="tr-filter-title">
  <div class="tr-filter-head">
    <div><p class="tr-section-kicker">BO LOC TRA CUU</p><h2 id="tr-filter-title">Chon du lieu can xem</h2></div>
    <p id="tr-source-status" class="tr-source-status" role="status" aria-live="polite"></p>
  </div>
  <form id="tr-form" class="tr-form">
    <label>Khoang thoi gian
      <select id="tr-period" name="period">{_period_options()}</select>
    </label>
    <label>Thu trong tuan
      <select id="tr-weekday" name="weekday">{_weekday_options()}</select>
    </label>
    <div class="tr-custom-dates" id="tr-custom-dates" hidden>
      <label>Tu ngay<input id="tr-from" name="from" type="date"
        min="{earliest}" max="{latest}" value="{earliest}"></label>
      <label>Den ngay<input id="tr-to" name="to" type="date"
        min="{earliest}" max="{latest}" value="{latest}"></label>
    </div>
    <div class="tr-actions">
      <button class="tr-btn tr-btn-primary" type="submit">Xem ket qua</button>
      <button class="tr-btn" id="tr-export-csv" type="button">Tai CSV</button>
      <button class="tr-btn" id="tr-export-xlsx" type="button">Tai Excel</button>
      <button class="tr-btn" id="tr-print" type="button">In so</button>
    </div>
  </form>
  <div class="tr-view-options">
    <fieldset class="tr-chips">
      <legend>Bo cuc</legend>
      {_layout_radios()}
    </fieldset>
    <fieldset class="tr-chips">
      <legend>Hien thi</legend>
      <label class="tr-chip"><input type="checkbox" id="tr-toggle-headtail" checked><span>Bang dau duoi</span></label>
      <label class="tr-chip"><input type="checkbox" id="tr-toggle-loto" checked><span>Day LOTO</span></label>
      <label class="tr-chip"><input type="checkbox" id="tr-toggle-tail" checked><span>To dam 2 so cuoi</span></label>
    </fieldset>
    <fieldset class="tr-chips">
      <legend>Danh dau</legend>
      <label class="tr-chip"><input type="checkbox" id="tr-pair-mode"><span>Tu dong danh dau cap trung</span></label>
    </fieldset>
    <button class="tr-btn tr-mark-clear" id="tr-mark-clear" type="button" hidden>Bo danh dau</button>
  </div>
</section>

<section class="tr-summary" aria-label="Tong quan ket qua">
  <div><span>So ky hien thi</span><strong id="tr-result-count">0</strong></div>
  <div><span>Ky moi nhat</span><strong id="tr-latest">—</strong></div>
  <div><span>Ky cu nhat</span><strong id="tr-oldest">—</strong></div>
  <div><span>Du lieu may chu</span><strong id="tr-total-count">0</strong></div>
</section>

<section id="tr-results" class="tr-results" data-layout="1" aria-live="polite">
  <div id="tr-more" class="tr-more" hidden>
    <button class="tr-btn" id="tr-more-btn" type="button">Xem them</button>
  </div>
</section>
<div id="tr-empty" class="tr-empty" hidden>
  <strong>Chua co ket qua trong khoang da chon.</strong>
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
        raise SystemExit("khong co ky hop le de dung So ket qua")
    stamp = generated or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    docs_dir.mkdir(parents=True, exist_ok=True)
    target = docs_dir / "so-ket-qua-truyen-thong.html"
    write_page(target, render_page(embedded_payload(rows, generated=stamp)))
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dung trang So ket qua truyen thong.")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    target = build(root, root / args.docs_dir)
    print(f"da ghi {target} ({target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
