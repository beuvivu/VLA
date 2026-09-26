"""Persistent UI refinements applied at the final HTML output boundary.

This layer intentionally changes presentation only. Builders keep ownership of
statistics, data semantics, element ids and JavaScript hooks; the refinement is
re-applied every time a published page is regenerated so the public site cannot
silently fall back to stale layouts after the daily pipeline runs.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["refine_page"]

# Id không mang tên dự án: nó đi thẳng vào HTML của mọi trang đã xuất bản.
_STYLE_ID = "ui-targeted-ui-refinement"
# Nhận diện các id từng được xuất ra để lần dựng tiếp theo gỡ được khối cũ,
# tránh giữ lại song song nhiều bản CSS trên cùng một trang.
_LEGACY_STYLE_IDS = ("vla-targeted-ui-refinement", "ui-targeted-refinement")
_STYLE_RE = re.compile(
    "<style id=\"(?:"
    + "|".join(re.escape(name) for name in (_STYLE_ID, *_LEGACY_STYLE_IDS))
    + ")\">.*?</style>",
    re.I | re.S,
)
_BODY_RE = re.compile(r"<body(?P<attrs>[^>]*)>", re.I)
_CLASS_RE = re.compile(r'class=(?P<q>["\'])(?P<value>.*?)(?P=q)', re.I | re.S)

_STAT_PAGES = {
    "bang-dac-biet.html": "bang-dac-biet",
    "lo-gan.html": "lo-gan",
    "dau-duoi-loto.html": "dau-duoi-loto",
    "giai-dac-biet-theo-tong.html": "giai-dac-biet-theo-tong",
    "cau-dac-biet-theo-bo-so.html": "cau-dac-biet-theo-bo-so",
    "giai-db-ngay-mai.html": "giai-db-ngay-mai",
    "cap-lon-loto.html": "cap-lon-loto",
}
_PATH_PAGES = {
    "soi-path-loto-active.html",
    "soi-path-loto-stable.html",
    "soi-path-de-active.html",
    "soi-path-de-stable.html",
}

_BASE_BG = "var(--ui-canvas)"

_STAT_CSS = rf"""
.sp-page{{min-height:100vh;background:{_BASE_BG}}}
.sp-page .ui-shell-wide{{max-width:1280px;margin-inline:auto;padding-inline:clamp(1rem,2.4vw,2rem)}}
.sp-page h1{{letter-spacing:-.03em}}
.sp-page .sp-controls{{width:100%;margin:1rem 0 1.25rem;padding:1rem 1.1rem;background:var(--ui-surface);border-color:var(--ui-border);border-radius:20px;box-shadow:0 8px 30px rgba(15,23,42,.05);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}}
.sp-page .sp-scroll,.sp-page .sp-duo>div,.sp-page .sp-recent-card{{background:var(--ui-surface);border-color:var(--ui-border);box-shadow:0 8px 30px rgba(15,23,42,.045);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)}}
.sp-page .sp-subhead{{display:flex;align-items:center;gap:.55rem;margin:1.35rem 0 .7rem;letter-spacing:-.015em}}
.sp-page .sp-subhead::before{{content:"";width:.45rem;height:.45rem;border-radius:50%;background:#2946f3;box-shadow:0 0 0 5px #e0e6fb}}
.sp-page .sp-table th{{background:var(--ui-surface-2);color:var(--ui-ink);position:sticky;top:0;z-index:2}}
.sp-page .sp-table tbody tr:hover{{background:var(--ui-surface-2)}}
.sp-page .sp-note{{border-radius:16px;box-shadow:0 8px 24px rgba(15,23,42,.035)}}

.sp-page-bang-dac-biet .sp-scroll{{width:100%;max-width:100%;overflow:auto}}
.sp-page-bang-dac-biet #sp-grid{{width:100%;min-width:760px;table-layout:fixed}}
.sp-page-bang-dac-biet #sp-grid th,.sp-page-bang-dac-biet #sp-grid td{{text-align:center;padding:.76rem .55rem}}

.sp-page-lo-gan .sp-scroll{{width:100%;max-width:100%;max-height:34rem;overflow:auto;overscroll-behavior:contain}}
.sp-page-lo-gan #sp-grid,.sp-page-lo-gan #sp-pair-gan{{width:100%}}
.sp-page-lo-gan .sp-duo{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem;align-items:start}}
.sp-page-lo-gan .sp-duo>div{{max-height:30rem;overflow:auto;overscroll-behavior:contain}}
.sp-page-lo-gan .sp-duo .sp-table{{width:100%}}

.sp-page-dau-duoi-loto .sp-duo{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1rem;align-items:start}}
.sp-page-dau-duoi-loto .sp-duo .sp-table{{width:100%}}
.sp-page-dau-duoi-loto .sp-recent-grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem;margin-top:1.25rem;align-items:start}}
.sp-page-dau-duoi-loto .sp-recent-card{{min-width:0;padding:1rem;border:1px solid var(--ui-border);border-radius:18px}}
.sp-page-dau-duoi-loto .sp-recent-card .sp-subhead{{margin:.1rem 0 .75rem;font-size:.9rem}}
.sp-page-dau-duoi-loto .sp-recent-card .sp-scroll{{width:100%;max-width:100%;max-height:32rem;overflow:auto;box-shadow:none;border:0}}
.sp-page-dau-duoi-loto .sp-recent-card .sp-table{{width:100%}}

.sp-page-giai-dac-biet-theo-tong .sp-scroll{{width:100%;max-width:100%;overflow:auto}}
.sp-page-giai-dac-biet-theo-tong #sp-grid,.sp-page-giai-dac-biet-theo-tong #sp-trans,.sp-page-giai-dac-biet-theo-tong #sp-parity{{width:100%;min-width:max-content}}
.sp-page-giai-dac-biet-theo-tong .sp-scroll:has(#sp-trans){{max-height:38rem;overflow:auto;overscroll-behavior:contain}}

.sp-page-cau-dac-biet-theo-bo-so .sp-scroll,.sp-page-giai-db-ngay-mai .sp-scroll,.sp-page-cap-lon-loto .sp-scroll{{width:100%;max-width:100%;max-height:38rem;overflow:auto;overscroll-behavior:contain;border-radius:18px}}
.sp-page-cau-dac-biet-theo-bo-so #sp-grid,.sp-page-giai-db-ngay-mai #sp-grid,.sp-page-cap-lon-loto #sp-grid,.sp-page-cap-lon-loto #sp-kep{{width:100%}}

@media(max-width:900px){{.sp-page-lo-gan .sp-duo,.sp-page-dau-duoi-loto .sp-duo,.sp-page-dau-duoi-loto .sp-recent-grid{{grid-template-columns:1fr}}.sp-page-bang-dac-biet #sp-grid{{min-width:680px}}}}
@media(max-width:640px){{.sp-page .ui-shell-wide{{padding-inline:12px}}.sp-page .sp-controls{{padding:.85rem;border-radius:16px}}.sp-page .sp-scroll{{border-radius:16px}}}}
"""

_PATH_CSS = rf"""
.path-page{{--bg:var(--ui-bg);--card:var(--ui-surface);--text:var(--ui-ink);--muted:var(--ui-ink-soft);--line:var(--ui-border);--hit:var(--ui-warn);--hitde:var(--ui-special-ink);--ok:var(--ui-ok);--chip:var(--ui-brand-soft);min-height:100vh;padding-bottom:calc(env(safe-area-inset-bottom) + 2rem);background:{_BASE_BG};color:var(--ui-ink)}}
.path-page a{{color:var(--ui-brand-ink)}}
.path-page .path-shell{{max-width:1280px;margin-inline:auto;padding:clamp(1rem,2.5vw,2rem);padding-bottom:calc(env(safe-area-inset-bottom) + 2.25rem)}}
.path-page .path-hero{{padding:1.15rem 1.2rem;border:1px solid var(--ui-border);border-radius:20px;background:var(--ui-surface);box-shadow:0 8px 30px rgba(15,23,42,.05);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}}
.path-page .path-hero h1{{font-size:clamp(1.3rem,2.5vw,2rem)!important;letter-spacing:-.03em;color:var(--ui-ink)}}
.path-page .path-overview{{gap:1rem;margin-top:1rem!important;grid-template-columns:minmax(0,1.15fr) minmax(18rem,.85fr)}}
.path-page .card{{border-radius:20px;border-color:var(--ui-border);background:var(--ui-surface);box-shadow:0 8px 30px rgba(15,23,42,.045);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}}
.path-page .card b,.path-page .quick-number{{color:var(--ui-ink)}}.path-page .small{{color:var(--ui-ink-soft)}}.path-page .chip{{background:var(--ui-brand-soft);border-color:var(--ui-border);color:var(--ui-ink-soft)}}
.path-page .btn{{background:var(--ui-brand);color:var(--ui-on-brand);border-color:var(--ui-brand)}}.path-page .btn.secondary{{background:var(--ui-surface);color:var(--ui-ink);border-color:var(--ui-border)}}
.path-page .quick-pick{{min-height:3.15rem;border-radius:14px;background:var(--ui-surface);border-color:var(--ui-border);color:var(--ui-ink)}}.path-page .quick-pick:hover{{background:var(--ui-brand-soft);border-color:var(--ui-brand-border)}}
.path-page th{{background:var(--ui-surface-2);color:var(--ui-ink)}}.path-page td{{color:var(--ui-ink);border-color:var(--ui-border)}}.path-page tr:hover td{{background:var(--ui-surface-2)}}
.path-page .cell{{background:var(--ui-surface);border-color:var(--ui-border);color:var(--ui-ink)}}.path-page .cell.none{{background-color:var(--ui-empty-bg);background-image:none;color:var(--ui-empty-ink)}}.path-page .cell.hit{{background:var(--ui-orange-bg);border-color:var(--ui-warn-border);color:var(--ui-orange-ink)}}.path-page .cell.hitde{{background:var(--ui-special-bg);border-color:var(--ui-special-border);color:var(--ui-special-ink);font-weight:800}}
.path-page .path-table-scroll{{max-height:min(66vh,52rem);overflow:auto;overscroll-behavior:contain;border:1px solid var(--ui-border);border-radius:14px;background:var(--ui-surface)}}
.path-page .path-table-scroll table{{margin:0}}.path-page .path-table-scroll th{{position:sticky;top:0;z-index:3;box-shadow:0 1px 0 var(--ui-border)}}
@media(max-width:979px){{.path-page .path-overview{{grid-template-columns:1fr}}.path-page .path-table-scroll{{max-height:58vh}}}}
@media(max-width:640px){{.path-page .path-shell{{padding:12px 12px calc(env(safe-area-inset-bottom) + 2.5rem)}}.path-page .path-hero{{padding:.9rem;border-radius:16px}}.path-page .card{{border-radius:16px;padding:12px}}.path-page .quick-grid{{grid-template-columns:1fr 1fr}}}}
"""

_DASHBOARD_CSS = rf"""
.ai-command-center{{min-height:100vh;background:{_BASE_BG}}}
.ai-command-center .ui-shell{{max-width:1280px}}
.ai-command-center .ui-header{{position:relative;overflow:hidden;padding:clamp(1.35rem,3vw,2.2rem);border:1px solid var(--ui-border);border-radius:24px;background:var(--ui-surface);box-shadow:0 8px 30px rgba(15,23,42,.05);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}}
.ai-command-center .ui-header::after{{content:"AI";position:absolute;right:1rem;top:-1.5rem;font-size:7rem;font-weight:900;letter-spacing:-.08em;color:rgba(79,70,229,.07);pointer-events:none}}
.ai-status-strip{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.8rem;margin:1rem 0 1.25rem}}
.ai-status-item{{position:relative;overflow:hidden;min-width:0;padding:1rem 1.05rem;border:1px solid var(--ui-border);border-radius:18px;background:var(--ui-surface);box-shadow:0 8px 30px rgba(15,23,42,.04);backdrop-filter:blur(14px)}}
.ai-status-item::after{{content:"";position:absolute;left:1rem;right:1rem;bottom:.65rem;height:3px;border-radius:999px;background:linear-gradient(90deg,#2946f3 0 32%,#7d8bfb 32% 63%,#c2cdfb 63% 100%);opacity:.75}}
.ai-status-item span{{display:block;font-size:.66rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--ui-ink-soft)}}.ai-status-item strong{{display:block;margin-top:.25rem;padding-bottom:.55rem;font-size:.92rem;color:var(--ui-ink)}}
.ai-signal-grid{{align-items:start}}.ai-signal-grid>.ui-card{{border-color:var(--ui-border);background:var(--ui-surface);box-shadow:0 8px 30px rgba(15,23,42,.045);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}}
.ai-signal-grid>.ui-card:nth-child(-n+2){{position:relative;overflow:hidden;border-color:var(--ui-brand-border);box-shadow:0 14px 36px rgba(79,70,229,.08)}}.ai-signal-grid>.ui-card:nth-child(-n+2)::before{{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:linear-gradient(180deg,#2946f3,#7d8bfb)}}
@media(max-width:760px){{.ai-status-strip{{grid-template-columns:1fr}}.ai-command-center .ui-header::after{{font-size:4.5rem}}}}
"""

_RESEARCH_CSS = rf"""
.research-workspace{{min-height:100vh;background:{_BASE_BG}}}
.research-workspace .ui-shell-wide{{max-width:1280px;margin-inline:auto}}
.research-workspace .rl-hero{{position:relative;overflow:hidden;padding:clamp(1.5rem,3vw,2.5rem);background:radial-gradient(circle at 88% 20%,rgba(56,189,248,.18),transparent 17rem),linear-gradient(135deg,#07111f,#0f172a 58%,#111827);border:1px solid #263449;box-shadow:0 24px 65px rgba(2,6,23,.2);border-radius:24px}}
.research-workspace .rl-hero::before{{content:"LIVE AI PROCESSING";position:absolute;right:1.25rem;top:1.15rem;padding:.3rem .55rem;border:1px solid rgba(34,197,94,.35);border-radius:999px;background:rgba(34,197,94,.1);color:#86efac;font:800 .62rem ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em}}
.rl-pipeline{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.65rem;margin:0 0 1rem}}.rl-stage{{position:relative;padding:.9rem .85rem;border:1px solid var(--ui-border);border-radius:18px;background:var(--ui-surface);box-shadow:0 8px 30px rgba(15,23,42,.04)}}
.rl-stage:not(:last-child)::after{{content:"→";position:absolute;right:-.52rem;top:50%;transform:translateY(-50%);z-index:2;color:var(--ui-ink-soft);font-weight:900}}.rl-stage span{{display:block;font-size:.64rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--ui-ink-soft)}}.rl-stage strong{{display:block;margin-top:.3rem;font-size:.86rem;color:var(--ui-ink)}}.rl-stage:last-child{{border-color:var(--ui-brand-border);background:var(--ui-brand-soft)}}
.rl-console{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.85rem;margin:0 0 1.25rem}}.rl-console-card{{position:relative;overflow:hidden;min-height:9rem;padding:1rem;border:1px solid rgba(99,102,241,.24);border-radius:18px;background:linear-gradient(180deg,var(--ui-surface),var(--ui-surface-2));box-shadow:0 10px 34px rgba(30,41,59,.05)}}
.rl-console-card::after{{content:"";position:absolute;left:0;right:0;top:-30%;height:32%;background:linear-gradient(180deg,transparent,rgba(56,189,248,.10),transparent);animation:rl-scan 5s linear infinite;pointer-events:none}}.rl-console-card span{{display:block;font:800 .62rem ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--ui-brand-ink)}}.rl-console-card strong{{display:block;margin:.45rem 0 .35rem;font-size:1rem;color:var(--ui-ink)}}.rl-console-card p{{margin:0;color:var(--ui-ink-soft);font-size:.75rem;line-height:1.55}}.rl-gauge{{width:3rem;height:3rem;margin-top:.55rem;border-radius:50%;background:conic-gradient(#2946f3 0 18%,var(--ui-border) 18% 25%,#22c55e 25% 43%,var(--ui-border) 43% 50%,#38bdf8 50% 68%,var(--ui-border) 68% 75%,#7d8bfb 75% 93%,var(--ui-border) 93%);box-shadow:inset 0 0 0 8px var(--ui-surface)}}
.rl-instruments>.ui-card{{position:relative;overflow:hidden;border-color:rgba(99,102,241,.18);background:var(--ui-surface);box-shadow:0 8px 30px rgba(15,23,42,.045)}}
@keyframes rl-scan{{0%{{transform:translateY(-140%)}}100%{{transform:translateY(480%)}}}}
@media(prefers-reduced-motion:reduce){{.rl-console-card::after{{animation:none}}}}
@media(max-width:1000px){{.rl-console{{grid-template-columns:repeat(2,minmax(0,1fr))}}.rl-pipeline{{grid-template-columns:repeat(2,minmax(0,1fr))}}.rl-stage::after{{display:none}}}}
@media(max-width:600px){{.rl-console,.rl-pipeline{{grid-template-columns:1fr}}.research-workspace .rl-hero::before{{position:static;display:inline-block;margin-bottom:.75rem}}}}
"""

_LIVE_CSS = rf"""
.live-console{{--bg:var(--ui-bg);--card:var(--ui-surface);--card-2:var(--ui-surface-2);--line:var(--ui-border);--ink:var(--ui-ink);--ink-2:var(--ui-ink-2);--ink-3:var(--ui-ink-soft);--accent:var(--ui-brand-ink);--ok:var(--ui-ok);--ok-line:var(--ui-ok-border);--warn:var(--ui-warn);--warn-line:var(--ui-warn-border);--hot:var(--ui-special-ink);min-height:100vh;padding-bottom:calc(env(safe-area-inset-bottom) + 1rem);background:{_BASE_BG};color:var(--ui-ink)}}
.live-console .wrap{{max-width:1280px;padding:24px 18px 36px;display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px}}
.live-console .wrap>.top{{grid-column:1/-1;padding:1rem 1.15rem;border:1px solid var(--ui-border);border-radius:20px;background:var(--ui-surface);box-shadow:0 8px 30px rgba(15,23,42,.05);backdrop-filter:blur(16px)}}
.live-console .card{{margin:0;border-color:var(--ui-border);border-radius:20px;background:var(--ui-surface);box-shadow:0 8px 30px rgba(15,23,42,.045);backdrop-filter:blur(14px)}}
.live-console .live-status-card{{grid-column:span 4;align-self:start}}.live-console .live-results-card{{grid-column:span 8;grid-row:2/span 2}}.live-console .live-sources-card{{grid-column:span 4;align-self:start}}
.live-console #results{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:16px}}.live-console .prize[data-prize=special],.live-console .prize[data-prize=prize3],.live-console .prize[data-prize=prize5],.live-console .prize[data-prize=prize7]{{grid-column:1/-1}}
.live-console .slot{{background:var(--ui-surface);border-color:var(--ui-border);color:var(--ui-ink)}}.live-console .slot.is-empty{{color:var(--ui-empty-ink);background-color:var(--ui-empty-bg);background-image:none;border-color:var(--ui-border)}}.live-console .slot.is-special{{color:var(--ui-special-ink);border-color:var(--ui-special-border);background:var(--ui-special-bg)}}
.live-console .ui-live-nav{{margin-top:1rem;padding-bottom:calc(env(safe-area-inset-bottom) + 2.5rem)}}
@media(max-width:900px){{.live-console .live-status-card,.live-console .live-results-card,.live-console .live-sources-card{{grid-column:1/-1;grid-row:auto}}.live-console #results{{grid-template-columns:1fr}}.live-console .prize{{grid-column:1/-1!important}}}}
@media(max-width:620px){{.live-console .wrap{{padding:12px 12px 28px;gap:10px}}.live-console .card{{border-radius:16px;padding:13px}}}}
"""

_RECENT_RE = re.compile(
    r'(<h3 class="sp-subhead">20 kỳ gần nhất theo chữ số ĐẦU</h3>\s*<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-head"></table></div>)\s*'
    r'(<h3 class="sp-subhead">20 kỳ gần nhất theo chữ số ĐUÔI \(đít\)</h3>\s*<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-tail"></table></div>)\s*'
    r'(<h3 class="sp-subhead">20 kỳ gần nhất theo TỔNG</h3>\s*<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-sum"></table></div>)',
    re.S,
)


def _add_body_classes(page: str, *classes: str) -> str:
    wanted = [item for item in classes if item]

    def repl(match: re.Match[str]) -> str:
        attrs = match.group("attrs")
        found = _CLASS_RE.search(attrs)
        if found:
            current = found.group("value").split()
            merged = current + [item for item in wanted if item not in current]
            quote = found.group("q")
            new_class = f'class={quote}{" ".join(merged)}{quote}'
            attrs = attrs[: found.start()] + new_class + attrs[found.end() :]
            return f"<body{attrs}>"
        return f'<body{attrs} class="{" ".join(wanted)}">'

    return _BODY_RE.sub(repl, page, count=1)


def _append_style(page: str, css: str) -> str:
    style = f'<style id="{_STYLE_ID}">{css}</style>'
    if _STYLE_RE.search(page):
        return _STYLE_RE.sub(style, page, count=1)
    return page.replace("</head>", f"{style}\n</head>", 1)


def _refine_stat(filename: str, page: str) -> str:
    slug = _STAT_PAGES[filename]
    page = _add_body_classes(page, "sp-page", f"sp-page-{slug}")
    if slug == "dau-duoi-loto" and "sp-recent-grid" not in page:
        def wrap(match: re.Match[str]) -> str:
            return (
                '<div class="sp-recent-grid">'
                f'<section class="sp-recent-card">{match.group(1)}</section>'
                f'<section class="sp-recent-card">{match.group(2)}</section>'
                f'<section class="sp-recent-card">{match.group(3)}</section>'
                "</div>"
            )
        page = _RECENT_RE.sub(wrap, page, count=1)
    return _append_style(page, _STAT_CSS)


def _refine_path(page: str) -> str:
    # KHONG gan `ui-dock-space`: dock da bi khung ung dung thay the, va tren
    # trang nay lop ay la cho DUY NHAT quy tac `padding-bottom` cua no khong
    # bi de. Do duoc: 86px trong duoi cung cho mot thanh dieu huong khong con
    # ton tai. 19 trang khac cung mang lop ay nhung tinh ra 0px, nen chung
    # khong lo ra van de.
    page = _add_body_classes(page, "path-page")
    page = page.replace('<div class="wrap">', '<div class="wrap path-shell">', 1)
    page = page.replace('<div class="top">', '<div class="top path-hero">', 1)
    page = page.replace('<div class="grid" style="margin-top:12px">', '<div class="grid path-overview" style="margin-top:12px">', 1)
    page = page.replace('<div style="margin-top:10px; overflow:auto">', '<div class="path-table-scroll" style="margin-top:10px; overflow:auto">', 1)
    return _append_style(page, _PATH_CSS)


def _refine_dashboard(page: str) -> str:
    page = _add_body_classes(page, "ai-command-center")
    page = page.replace('<div class="ui-grid">', '<div class="ui-grid ai-signal-grid">', 1)
    if "ai-status-strip" not in page:
        strip = (
            '<section class="ai-status-strip" aria-label="Cấu trúc bảng điều khiển AI/ML">'
            '<div class="ai-status-item"><span>Không gian</span><strong>AI/ML Command Center</strong></div>'
            '<div class="ai-status-item"><span>Tín hiệu</span><strong>Xác suất · Gợi ý · Xếp hạng</strong></div>'
            '<div class="ai-status-item"><span>Kiểm soát</span><strong>Trọng số · Hiệu chỉnh · Chất lượng</strong></div>'
            '</section>'
        )
        page = page.replace("</header>", f"</header>{strip}", 1)
    return _append_style(page, _DASHBOARD_CSS)


def _refine_research(page: str) -> str:
    page = _add_body_classes(page, "research-workspace")
    page = page.replace('<div class="ui-grid">', '<div class="ui-grid rl-instruments">', 1)
    if "rl-pipeline" not in page:
        pipeline = (
            '<section class="rl-pipeline" aria-label="Quy trình kiểm chứng nghiên cứu">'
            '<div class="rl-stage"><span>01 · Khám phá</span><strong>Giả thuyết</strong></div>'
            '<div class="rl-stage"><span>02 · Học</span><strong>Huấn luyện</strong></div>'
            '<div class="rl-stage"><span>03 · Soát</span><strong>Kiểm định</strong></div>'
            '<div class="rl-stage"><span>04 · OOS</span><strong>Tập giữ lại</strong></div>'
            '<div class="rl-stage"><span>05 · Firewall</span><strong>Cổng vận hành</strong></div>'
            '</section>'
            '<section class="rl-console" aria-label="Bộ công cụ phòng thí nghiệm">'
            '<article class="rl-console-card"><span>AI PARAMETERS</span><strong>Bảng tham số thuật toán AI</strong><p>FDR · hiệu chỉnh · tập giữ lại · kiểm tra thực tế.</p></article>'
            '<article class="rl-console-card"><span>BACKTEST RUNNER</span><strong>Khung chạy Backtest mô phỏng</strong><p>Walk-forward theo thời gian; tách huấn luyện, kiểm định và holdout.</p></article>'
            '<article class="rl-console-card"><span>NUMBER × BÓNG MATRIX</span><strong>Ma trận ma sát số &amp; bóng</strong><p>Không gian giả thuyết được kiểm tra có kiểm soát.</p></article>'
            '<article class="rl-console-card"><span>CONFIDENCE SCORE GAUGE</span><strong>FDR + OOS + Reality Check</strong><div class="rl-gauge" aria-hidden="true"></div><p>Gauge là trạng thái cổng kiểm chứng, không phải xác suất trúng.</p></article>'
            '</section>'
        )
        page = page.replace('</section>\n<div class="ui-note"', f'</section>{pipeline}\n<div class="ui-note"', 1)
    return _append_style(page, _RESEARCH_CSS)


def _refine_live(page: str) -> str:
    page = _add_body_classes(page, "live-console")
    page = page.replace('<div class="top" style="margin-bottom:4px">', '<div class="top live-hero" style="margin-bottom:4px">', 1)
    page = page.replace('<div class="card">', '<div class="card live-status-card">', 1)
    page = page.replace('<div class="card">', '<div class="card live-results-card">', 1)
    page = page.replace('<div class="card">', '<div class="card live-sources-card">', 1)
    return _append_style(page, _LIVE_CSS)


def refine_page(path: Path | str, page: str) -> str:
    """Return idempotently refined HTML for selected public pages."""
    filename = Path(path).name
    if filename in _STAT_PAGES:
        return _refine_stat(filename, page)
    if filename in _PATH_PAGES:
        return _refine_path(page)
    if filename == "dashboard.html":
        return _refine_dashboard(page)
    if filename == "research-lab.html":
        return _refine_research(page)
    if filename == "live.html":
        return _refine_live(page)
    return page
