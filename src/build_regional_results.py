"""Dựng trang kết quả XSMT/XSMN từ kho dữ liệu vùng đã lưu."""

from __future__ import annotations

import csv
import html
from collections import defaultdict
from pathlib import Path
from typing import Sequence

from css_links import stylesheet_link
from page_output import write_page
from ui_theme import app_shell_close, app_shell_open
from web_security import json_for_html_script, security_meta_tags

PRIZE_ORDER = ("ĐB", "G.1", "G.2", "G.3", "G.4", "G.5", "G.6", "G.7", "G.8")
REGION_META = {
    "mt": ("Miền Trung", "XSMT", "ket-qua-mien-trung.html"),
    "mn": ("Miền Nam", "XSMN", "ket-qua-mien-nam.html"),
}


def load_rows(root: Path, region: str) -> list[dict[str, str]]:
    path = root / "data" / "regions" / f"xs{region}.csv"
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def grouped(rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, list[str]]]]:
    draws = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for row in rows:
        draws[row["date"]][row["province"]][row["prize"]].append(row["value"])
    return {d: {p: dict(v) for p, v in provinces.items()} for d, provinces in draws.items()}


def board(draw_date: str, provinces: dict[str, dict[str, list[str]]]) -> str:
    heads = "".join(f"<th>{html.escape(p)}</th>" for p in provinces)
    body = []
    for prize in PRIZE_ORDER:
        cells = []
        for province in provinces:
            values = provinces[province].get(prize, [])
            nums = "".join(f'<span class="rg-num">{html.escape(v)}</span>' for v in values) or "—"
            cells.append(f"<td>{nums}</td>")
        cls = ' class="rg-special"' if prize == "ĐB" else ""
        body.append(f'<tr{cls}><th scope="row">{prize}</th>{"".join(cells)}</tr>')
    return (
        f'<article class="rg-draw" data-date="{draw_date}">'
        f'<div class="rg-draw-head"><h2>{draw_date}</h2><span>{len(provinces)} đài</span></div>'
        f'<div class="rg-table-wrap"><table class="rg-table"><thead><tr><th>Giải</th>{heads}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div></article>'
    )


def render(region: str, rows: list[dict[str, str]]) -> str:
    name, code, filename = REGION_META[region]
    data = grouped(rows)
    dates = sorted(data, reverse=True)
    provinces = sorted({row["province"] for row in rows})
    latest = dates[0] if dates else "—"
    boards = "".join(board(d, data[d]) for d in dates[:120])
    if not boards:
        boards = '<div class="rg-empty"><strong>Chưa có dữ liệu đã lưu.</strong><span>Dữ liệu vùng sẽ có sau lượt đồng bộ kế tiếp.</span></div>'
    filter_data = json_for_html_script({"dates": dates, "provinces": provinces})

    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{security_meta_tags()}
{stylesheet_link()}
<title>Kết quả xổ số {name} · {code}</title>
<style>
.rg-hero{{display:flex;justify-content:space-between;gap:24px;align-items:flex-end;margin-bottom:24px;padding:24px;border:1px solid var(--ui-border);border-radius:24px;background:var(--ui-surface);box-shadow:var(--ui-sh-sm)}}
.rg-kicker{{margin:0 0 6px;color:var(--ui-brand-ink);font-size:12px;font-weight:800;letter-spacing:.08em}}.rg-hero h1{{margin:0 0 8px;font-size:clamp(28px,4vw,44px)}}.rg-hero p{{margin:0;color:var(--ui-ink-soft)}}.rg-priority{{max-width:310px;padding:12px 14px;border-radius:14px;background:var(--ui-brand-soft);color:var(--ui-ink-2);font-size:13px}}
.rg-filter{{display:grid;grid-template-columns:1fr 1fr auto;gap:12px;margin-bottom:18px;padding:16px;border:1px solid var(--ui-border);border-radius:16px;background:var(--ui-surface)}}.rg-filter label{{display:grid;gap:5px;font-size:12px;font-weight:700}}.rg-filter select{{min-height:42px;border:1px solid var(--ui-border);border-radius:10px;background:var(--ui-surface);color:var(--ui-ink);padding:0 10px}}.rg-btn{{align-self:end;min-height:42px;padding:0 16px;border:0;border-radius:10px;background:var(--ui-brand);color:var(--ui-on-brand);font-weight:700;cursor:pointer}}
.rg-meta{{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 18px}}.rg-meta span{{padding:7px 10px;border:1px solid var(--ui-border);border-radius:999px;background:var(--ui-surface);font-size:12px}}
.rg-results{{display:grid;gap:18px}}.rg-draw{{overflow:hidden;border:1px solid var(--ui-border);border-radius:18px;background:var(--ui-surface);box-shadow:var(--ui-sh-sm)}}.rg-draw-head{{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid var(--ui-border)}}.rg-draw-head h2{{margin:0;font-size:18px}}.rg-draw-head span{{color:var(--ui-ink-soft);font-size:12px}}.rg-table-wrap{{overflow:auto}}.rg-table{{width:100%;border-collapse:collapse;min-width:620px}}.rg-table th,.rg-table td{{padding:9px 12px;border-bottom:1px solid var(--ui-border);text-align:center;vertical-align:middle}}.rg-table thead th{{position:sticky;top:0;background:var(--ui-surface-2);z-index:1}}.rg-table tbody th{{width:72px;color:var(--ui-ink-soft)}}.rg-num{{display:inline-block;margin:2px 7px;font:700 16px var(--ui-mono);letter-spacing:.03em}}.rg-special td{{background:var(--ui-special-bg);color:var(--ui-special-ink)}}.rg-special .rg-num{{font-size:21px}}.rg-empty{{display:grid;gap:6px;padding:32px;border:1px dashed var(--ui-border);border-radius:18px;text-align:center;background:var(--ui-surface)}}.rg-empty span{{color:var(--ui-ink-soft)}}[hidden]{{display:none!important}}
@media(max-width:720px){{.rg-hero{{display:block;padding:18px}}.rg-priority{{margin-top:14px;max-width:none}}.rg-filter{{grid-template-columns:1fr}}}}
</style></head><body>
{app_shell_open(filename, wide=True)}
<section class="rg-hero"><div><p class="rg-kicker">KẾT QUẢ XỔ SỐ {name.upper()}</p><h1>{code} · Kết quả theo tỉnh</h1><p>Kết quả đã công bố, lưu theo tỉnh/thành để tra cứu và xây dựng cơ sở phân tích vùng.</p></div><div class="rg-priority"><strong>Ưu tiên hệ thống: XSMB</strong><br>Miền Trung/Miền Nam là lớp dữ liệu mở rộng; pipeline Miền Bắc vẫn giữ lịch, AI/ML và tài nguyên ưu tiên cao nhất.</div></section>
<section class="rg-filter" aria-label="Bộ lọc kết quả"><label>Ngày quay<select id="rg-date"><option value="">Tất cả ngày đang hiển thị</option>{"".join(f'<option value="{d}">{d}</option>' for d in dates[:120])}</select></label><label>Tỉnh / thành<select id="rg-province"><option value="">Tất cả đài</option>{"".join(f'<option value="{html.escape(p)}">{html.escape(p)}</option>' for p in provinces)}</select></label><button class="rg-btn" id="rg-reset" type="button">Đặt lại</button></section>
<div class="rg-meta"><span><strong>{len(dates)}</strong> ngày đã lưu</span><span><strong>{len(provinces)}</strong> tỉnh/thành</span><span>Mới nhất: <strong>{latest}</strong></span></div>
<section class="rg-results" id="rg-results">{boards}</section>
{app_shell_close(filename)}
<script id="rg-data" type="application/json">{filter_data}</script>
<script>
(()=>{{const d=document.getElementById('rg-date'),p=document.getElementById('rg-province'),reset=document.getElementById('rg-reset');const apply=()=>{{const dv=d.value,pv=p.value.toLowerCase();document.querySelectorAll('.rg-draw').forEach(card=>{{const dateOk=!dv||card.dataset.date===dv;const provinceOk=!pv||card.textContent.toLowerCase().includes(pv);card.hidden=!(dateOk&&provinceOk);}})}};d.addEventListener('change',apply);p.addEventListener('change',apply);reset.addEventListener('click',()=>{{d.value='';p.value='';apply();}});}})();
</script></body></html>"""


def build(root: Path) -> list[Path]:
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    outputs = []
    for region, (_, _, filename) in REGION_META.items():
        target = docs / filename
        write_page(target, render(region, load_rows(root, region)))
        outputs.append(target)
    return outputs


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    for path in build(root):
        print(f"đã ghi {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
