"""Dựng trang Sổ kết quả truyền thống từ dữ liệu chuẩn VLA.

Trang hoạt động ngay cả khi Worker chưa được cấu hình nhờ lịch sử nhúng. Khi
có Worker, trình duyệt gọi REST API để nhận lớp bù xskt.vn; cả hai đường dùng
cùng schema_version=1 nên giao diện không có hai nhánh dựng bảng khác nhau.
"""

from __future__ import annotations

import argparse
import csv
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Sequence

from ui_theme import app_shell_close, app_shell_open, stylesheet_link
from web_security import json_for_html_script, security_meta_tags

PRIZE_ORDER = (
    "special", "prize1", "prize2", "prize3",
    "prize4", "prize5", "prize6", "prize7",
)
PRIZE_WIDTHS = {
    "special": 5, "prize1": 5, "prize2": 5, "prize3": 5,
    "prize4": 4, "prize5": 4, "prize6": 3, "prize7": 2,
}
PRIZE_LABELS = {
    "special": "Đặc Biệt",
    "prize1": "Giải Nhất",
    "prize2": "Giải Nhì",
    "prize3": "Giải Ba",
    "prize4": "Giải Tư",
    "prize5": "Giải Năm",
    "prize6": "Giải Sáu",
    "prize7": "Giải Bảy",
}
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


def _asset(name: str) -> str:
    path = Path(__file__).resolve().parent / "templates" / name
    return path.read_text(encoding="utf-8")


def _head_tail(prizes: dict[str, list[str]]) -> dict[str, dict[str, list[str]]]:
    heads = {str(i): [] for i in range(10)}
    tails = {str(i): [] for i in range(10)}
    for key in PRIZE_ORDER:
        for value in prizes[key]:
            two = value[-2:]
            heads[two[0]].append(two[1])
            tails[two[1]].append(two[0])
    for digit in map(str, range(10)):
        heads[digit].sort()
        tails[digit].sort()
    return {"heads": heads, "tails": tails}


def _draw(row: dict[str, str]) -> dict[str, object] | None:
    draw_date = str(row.get("date", ""))[:10]
    try:
        date.fromisoformat(draw_date)
    except ValueError:
        return None
    prizes: dict[str, list[str]] = {}
    for key in PRIZE_ORDER:
        width = PRIZE_WIDTHS[key]
        raw = [row.get(field) for field in PRIZE_FIELDS[key]]
        if any(value is None or not str(value).strip() for value in raw):
            return None
        values = [str(value).strip().zfill(width) for value in raw]
        if any(len(value) != width or not value.isascii() or not value.isdigit() for value in values):
            return None
        prizes[key] = values
    return {
        "id": f"north:hanoi:{draw_date}",
        "region": {"code": "north", "name": "Miền Bắc"},
        "province": {"code": "hanoi", "name": "Hà Nội"},
        "draw_date": draw_date,
        "status": "official",
        "source": {
            "kind": "vla_db",
            "provider": "VLA canonical database",
            "canonical": True,
        },
        "prizes": [
            {
                "code": key,
                "name": PRIZE_LABELS[key],
                "width": PRIZE_WIDTHS[key],
                "values": prizes[key],
            }
            for key in PRIZE_ORDER
        ],
        "head_tail": _head_tail(prizes),
    }


def load_draws(repo_root: Path, *, limit: int = 500) -> list[dict[str, object]]:
    """Nạp tối đa ``limit`` kỳ mới nhất từ CSV chuẩn, giữ số 0 ở đầu."""

    path = repo_root / "data" / "xsmb.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    draws = [draw for row in rows if (draw := _draw(row)) is not None]
    draws.sort(key=lambda item: str(item["draw_date"]), reverse=True)
    return draws[:limit]


def embedded_payload(draws: list[dict[str, object]], *, generated: str) -> dict[str, object]:
    latest = str(draws[0]["draw_date"]) if draws else None
    return {
        "schema_version": 1,
        "query": {
            "region": "north",
            "province": "hanoi",
            "from": None,
            "to": latest,
            "preset_days": 30,
            "timezone": "Asia/Ho_Chi_Minh",
        },
        "meta": {
            "generated_at_utc": generated,
            "total_results": len(draws),
            "latest_draw_date": latest,
            "source_counts": {"vla_db": len(draws), "xskt_fallback": 0},
            "sources_used": ["vla_db"] if draws else [],
            "fallback_requested": False,
            "fallback_network_fetch": False,
            "unresolved_dates": [],
            "primary_cache": "embedded",
            "warning": None,
        },
        "data": draws,
    }


def render_page(payload: dict[str, object]) -> str:
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{security_meta_tags(connect_sources=("https://*.workers.dev",))}
{stylesheet_link()}
<title>Sổ kết quả truyền thống · VLA</title>
<style>{_asset("traditional_results.css")}</style>
</head><body>
{app_shell_open("so-ket-qua-truyen-thong.html", wide=True)}
<header class="tr-hero">
  <div>
    <p class="tr-eyebrow">DỮ LIỆU XỔ SỐ KIẾN THIẾT</p>
    <h1>Sổ kết quả truyền thống</h1>
    <p>Tra cứu kết quả theo ngày từ CSDL VLA; ngày thiếu được API bù từ xskt.vn và lưu cache.</p>
  </div>
  <div class="tr-trust" aria-label="Chính sách nguồn">
    <span class="tr-status-dot" aria-hidden="true"></span>
    <strong>VLA ưu tiên</strong><small>xskt.vn chỉ là nguồn bù</small>
  </div>
</header>

<section class="tr-filter" aria-labelledby="tr-filter-title">
  <div class="tr-filter-head">
    <div><p class="tr-section-kicker">BỘ LỌC TRA CỨU</p><h2 id="tr-filter-title">Chọn dữ liệu cần xem</h2></div>
    <p id="tr-source-status" class="tr-source-status" role="status" aria-live="polite"></p>
  </div>
  <form id="tr-form" class="tr-form">
    <label>Khu vực / Tỉnh thành
      <select id="tr-province" name="province">
        <option value="hanoi">Miền Bắc / Hà Nội</option>
      </select>
    </label>
    <label>Khoảng thời gian
      <select id="tr-period" name="period">
        <option value="30">30 ngày</option><option value="60">60 ngày</option>
        <option value="90">90 ngày</option><option value="100">100 ngày</option>
        <option value="custom">Tùy chọn ngày</option>
      </select>
    </label>
    <div class="tr-custom-dates" id="tr-custom-dates" hidden>
      <label>Từ ngày<input id="tr-from" name="from" type="date"></label>
      <label>Đến ngày<input id="tr-to" name="to" type="date"></label>
    </div>
    <div class="tr-actions">
      <button class="tr-btn tr-btn-primary" type="submit">Xem kết quả</button>
      <button class="tr-btn" id="tr-export-csv" type="button">Tải CSV</button>
      <button class="tr-btn" id="tr-export-xlsx" type="button">Tải Excel</button>
    </div>
  </form>
</section>

<section class="tr-summary" aria-label="Tổng quan kết quả">
  <div><span>Số kỳ hiển thị</span><strong id="tr-result-count">0</strong></div>
  <div><span>Kỳ mới nhất</span><strong id="tr-latest">—</strong></div>
  <div><span>Nguồn chuẩn VLA</span><strong id="tr-vla-count">0</strong></div>
  <div><span>Nguồn bù xskt.vn</span><strong id="tr-xskt-count">0</strong></div>
</section>

<section id="tr-results" class="tr-results" aria-live="polite"></section>
<div id="tr-empty" class="tr-empty" hidden>
  <strong>Chưa có kết quả trong khoảng đã chọn.</strong>
  <span>Hãy đổi dải ngày hoặc thử lại sau khi kỳ quay hoàn tất.</span>
</div>
{app_shell_close("so-ket-qua-truyen-thong.html")}

<script id="tr-embedded-data" type="application/json">{json_for_html_script(payload)}</script>
<script>
// Bộ cài Worker sẽ tự điền endpoint này. Để trống thì trang vẫn dùng dữ liệu nhúng.
window.VLA_RESULTS_API_URL = '';
{_asset("traditional_results.js")}
</script>
</body></html>
"""


def build(repo_root: Path, docs_dir: Path, *, generated: str | None = None) -> Path:
    draws = load_draws(repo_root)
    if not draws:
        raise SystemExit("không có kỳ hợp lệ để dựng Sổ kết quả")
    stamp = generated or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    docs_dir.mkdir(parents=True, exist_ok=True)
    target = docs_dir / "so-ket-qua-truyen-thong.html"
    target.write_text(render_page(embedded_payload(draws, generated=stamp)), encoding="utf-8")
    return target


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dựng trang Sổ kết quả truyền thống.")
    parser.add_argument("--docs-dir", default="docs")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    target = build(root, root / args.docs_dir)
    print(f"đã ghi {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
