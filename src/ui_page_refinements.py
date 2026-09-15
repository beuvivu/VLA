"""Page-specific presentation refinements applied at the HTML output boundary.

The project intentionally keeps data/statistical builders focused on semantic
content.  A handful of published pages need a stronger presentation hierarchy
than their generic builders can express without duplicating the whole builder.
This module is the single, idempotent place for those *visual-only* refinements.

No statistical value, table id, JavaScript data hook or navigation target is
changed here.  Builders may regenerate content every day and the same layout
contract is re-applied just before the page is written.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["refine_page"]

_STYLE_ID = "vla-targeted-ui-refinement"

_TARGET_STAT_PAGES = {
    "bang-dac-biet.html": "bang-dac-biet",
    "lo-gan.html": "lo-gan",
    "dau-duoi-loto.html": "dau-duoi-loto",
    "giai-dac-biet-theo-tong.html": "giai-dac-biet-theo-tong",
}

_PATH_PAGES = {
    "soi-path-loto-active.html",
    "soi-path-loto-stable.html",
    "soi-path-de-active.html",
    "soi-path-de-stable.html",
}

_BODY_RE = re.compile(r"<body(?P<attrs>[^>]*)>", re.I)
_CLASS_RE = re.compile(r'class=(?P<q>["\'])(?P<value>.*?)(?P=q)', re.I | re.S)


_STAT_CSS = r"""
.sp-page .sp-controls{backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.sp-page .sp-subhead{display:flex;align-items:center;gap:.55rem;margin:1.35rem 0 .7rem}
.sp-page .sp-subhead::before{content:"";width:.45rem;height:.45rem;border-radius:50%;background:var(--ui-brand);box-shadow:0 0 0 5px var(--ui-brand-soft)}

.sp-page-bang-dac-biet .sp-scroll{width:100%;max-width:100%}
.sp-page-bang-dac-biet #sp-grid{width:100%;min-width:760px;table-layout:fixed}
.sp-page-bang-dac-biet #sp-grid th,
.sp-page-bang-dac-biet #sp-grid td{text-align:center;padding:.72rem .55rem}
.sp-page-bang-dac-biet #sp-grid th:first-child,
.sp-page-bang-dac-biet #sp-grid td:first-child{text-align:left}

.sp-page-lo-gan .sp-scroll:has(#sp-grid),
.sp-page-lo-gan .sp-scroll:has(#sp-pair-gan){width:100%;max-width:100%;max-height:34rem;overflow:auto}
.sp-page-lo-gan #sp-grid,
.sp-page-lo-gan #sp-pair-gan{width:100%}
.sp-page-lo-gan .sp-duo{grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}
.sp-page-lo-gan .sp-duo>div{max-height:30rem;overflow:auto;background:linear-gradient(180deg,var(--ui-surface),var(--ui-surface-2))}
.sp-page-lo-gan .sp-duo .sp-table{width:100%}
.sp-page-lo-gan .sp-note{margin-top:.25rem}
.sp-gan-dashboard .sp-controls{position:relative;z-index:2}

.sp-page-dau-duoi-loto .sp-duo{grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}
.sp-page-dau-duoi-loto .sp-duo .sp-table{width:100%}
.sp-page-dau-duoi-loto .sp-recent-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem;margin-top:1.25rem;align-items:start}
.sp-page-dau-duoi-loto .sp-recent-card{min-width:0;padding:1rem;border:1px solid var(--ui-border);border-radius:var(--ui-r-lg);background:var(--ui-surface);box-shadow:var(--ui-sh-sm)}
.sp-page-dau-duoi-loto .sp-recent-card .sp-subhead{margin:.1rem 0 .75rem;font-size:.9rem}
.sp-page-dau-duoi-loto .sp-recent-card .sp-scroll{width:100%;max-width:100%;max-height:32rem;overflow:auto;box-shadow:none}
.sp-page-dau-duoi-loto .sp-recent-card .sp-table{width:100%}

.sp-page-giai-dac-biet-theo-tong .sp-scroll{width:100%;max-width:100%;overflow:auto}
.sp-page-giai-dac-biet-theo-tong #sp-grid,
.sp-page-giai-dac-biet-theo-tong #sp-trans,
.sp-page-giai-dac-biet-theo-tong #sp-parity{width:100%;min-width:max-content}
.sp-page-giai-dac-biet-theo-tong .sp-scroll:has(#sp-trans){max-height:38rem;overflow:auto}
.sp-page-giai-dac-biet-theo-tong .sp-note{max-width:none}
.sp-tong-dashboard .sp-controls{position:relative;z-index:2}

@media(max-width:900px){
  .sp-page-lo-gan .sp-duo,
  .sp-page-dau-duoi-loto .sp-duo,
  .sp-page-dau-duoi-loto .sp-recent-grid{grid-template-columns:1fr}
  .sp-page-bang-dac-biet #sp-grid{min-width:680px}
}
"""

_PATH_CSS = r"""
.path-page{min-height:100vh;padding-bottom:calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 2rem);background:
 radial-gradient(circle at 8% 0%,rgba(59,130,246,.12),transparent 26rem),
 radial-gradient(circle at 92% 6%,rgba(139,92,246,.10),transparent 28rem),var(--bg)}
.path-page .path-shell{max-width:1440px;padding:clamp(1rem,2.5vw,2rem);padding-bottom:calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 2.25rem)}
.path-page .path-hero{padding:1.15rem 1.2rem;border:1px solid var(--line);border-radius:18px;background:linear-gradient(135deg,rgba(30,41,59,.86),rgba(15,23,42,.68));box-shadow:0 20px 55px rgba(2,6,23,.2)}
.path-page .path-hero h1{font-size:clamp(1.3rem,2.5vw,2rem)!important;letter-spacing:-.025em}
.path-page .path-overview{gap:1rem;margin-top:1rem!important;grid-template-columns:minmax(0,1.15fr) minmax(18rem,.85fr)}
.path-page .card{border-radius:18px;border-color:rgba(148,163,184,.16);background:linear-gradient(180deg,rgba(15,23,42,.96),rgba(15,23,42,.82));box-shadow:0 16px 44px rgba(2,6,23,.18)}
.path-page .quick-pick{min-height:3.15rem;border-radius:12px}
.path-page .path-table-scroll{max-height:min(66vh,52rem);overflow:auto;overscroll-behavior:contain;border:1px solid var(--line);border-radius:12px}
.path-page .path-table-scroll table{margin:0}
.path-page .path-table-scroll th{top:0;z-index:3;box-shadow:0 1px 0 var(--line)}
.path-page .ui-nav-fallback{margin-bottom:calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 1rem)}
@media(max-width:979px){
  .path-page .path-overview{grid-template-columns:1fr}
  .path-page .path-table-scroll{max-height:58vh}
}
@media(max-width:640px){
  .path-page .path-shell{padding:12px 12px calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 2.5rem)}
  .path-page .path-hero{padding:.9rem;border-radius:15px}
  .path-page .card{border-radius:15px;padding:12px}
  .path-page .quick-grid{grid-template-columns:1fr 1fr}
}
"""

_DASHBOARD_CSS = r"""
.ai-command-center{background:
 radial-gradient(circle at 12% -8%,color-mix(in srgb,var(--ui-brand) 16%,transparent),transparent 30rem),
 radial-gradient(circle at 90% 4%,color-mix(in srgb,#8b5cf6 12%,transparent),transparent 28rem),var(--ui-bg)}
.ai-command-center .ui-header{position:relative;overflow:hidden;padding:clamp(1.25rem,3vw,2rem);border:1px solid var(--ui-border);border-radius:var(--ui-r-xl);background:linear-gradient(135deg,var(--ui-surface),var(--ui-surface-2));box-shadow:var(--ui-sh-md)}
.ai-command-center .ui-header::after{content:"AI";position:absolute;right:1rem;top:-1.35rem;font-size:7rem;font-weight:900;letter-spacing:-.08em;color:color-mix(in srgb,var(--ui-brand) 7%,transparent);pointer-events:none}
.ai-status-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.8rem;margin:1rem 0 1.25rem}
.ai-status-item{min-width:0;padding:.85rem 1rem;border:1px solid var(--ui-border);border-radius:var(--ui-r-lg);background:color-mix(in srgb,var(--ui-surface) 88%,transparent);box-shadow:var(--ui-sh-sm)}
.ai-status-item span{display:block;font-size:.66rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--ui-ink-soft)}
.ai-status-item strong{display:block;margin-top:.25rem;font-size:.92rem;color:var(--ui-ink)}
.ai-signal-grid{align-items:start}
.ai-signal-grid>.ui-card:nth-child(-n+2){position:relative;overflow:hidden;border-color:var(--ui-brand-border);box-shadow:var(--ui-sh-md)}
.ai-signal-grid>.ui-card:nth-child(-n+2)::before{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--ui-brand)}
.ai-signal-grid>.ui-card .ui-card-head h2{letter-spacing:-.015em}
.ai-command-center .ui-table{font-variant-numeric:tabular-nums}
@media(max-width:760px){.ai-status-strip{grid-template-columns:1fr}.ai-command-center .ui-header::after{font-size:4.5rem}}
"""

_RESEARCH_CSS = r"""
.research-workspace{background:
 linear-gradient(180deg,color-mix(in srgb,#020617 7%,var(--ui-bg)) 0,var(--ui-bg) 30rem)}
.research-workspace .rl-hero{position:relative;overflow:hidden;padding:clamp(1.4rem,3vw,2.35rem);background:
 radial-gradient(circle at 88% 20%,rgba(56,189,248,.18),transparent 17rem),
 linear-gradient(135deg,#07111f,#0f172a 58%,#111827);border:1px solid #263449;box-shadow:0 24px 65px rgba(2,6,23,.28)}
.research-workspace .rl-hero::after{content:"LAB / 01";position:absolute;right:1.25rem;bottom:.8rem;font:800 .68rem ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.16em;color:#64748b}
.rl-pipeline{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.65rem;margin:0 0 1.25rem}
.rl-stage{position:relative;padding:.85rem .8rem;border:1px solid var(--ui-border);border-radius:var(--ui-r-lg);background:var(--ui-surface);box-shadow:var(--ui-sh-sm)}
.rl-stage:not(:last-child)::after{content:"→";position:absolute;right:-.52rem;top:50%;transform:translateY(-50%);z-index:2;color:var(--ui-ink-soft);font-weight:900}
.rl-stage span{display:block;font-size:.64rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--ui-ink-soft)}
.rl-stage strong{display:block;margin-top:.3rem;font-size:.86rem;color:var(--ui-ink)}
.rl-stage:last-child{border-color:var(--ui-brand-border);background:var(--ui-brand-soft)}
.rl-instruments>.ui-card{position:relative;overflow:hidden}
.rl-instruments>.ui-card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;background:color-mix(in srgb,var(--ui-brand) 55%,transparent)}
.research-workspace .metric-card{position:relative;overflow:hidden;background:linear-gradient(180deg,var(--ui-surface),var(--ui-surface-2))}
.research-workspace .metric-card::after{content:"";position:absolute;right:.85rem;top:.85rem;width:.46rem;height:.46rem;border-radius:50%;background:#22c55e;box-shadow:0 0 0 4px rgba(34,197,94,.1)}
@media(max-width:900px){.rl-pipeline{grid-template-columns:1fr 1fr}.rl-stage::after{display:none}}
@media(max-width:560px){.rl-pipeline{grid-template-columns:1fr}}
"""

_LIVE_CSS = r"""
.live-console{padding-bottom:calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 1rem)}
.live-console .wrap{max-width:1120px;padding:24px 18px 36px}
.live-console .wrap>.top{padding:1rem 1.1rem;border:1px solid rgba(148,163,184,.16);border-radius:18px;background:linear-gradient(135deg,rgba(13,27,45,.92),rgba(18,34,54,.72));box-shadow:0 18px 50px rgba(0,0,0,.18)}
.live-console .card{border-color:rgba(148,163,184,.18);background:linear-gradient(180deg,rgba(13,27,45,.96),rgba(13,27,45,.84));box-shadow:0 16px 44px rgba(0,0,0,.16)}
.live-console .prize{min-height:3.4rem}
.live-console .ui-live-nav{margin-top:1rem;padding-bottom:calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 2.5rem)}
@media(max-width:620px){.live-console .wrap{padding:12px 12px 28px}.live-console .wrap>.top{padding:.85rem;border-radius:15px}.live-console .card{border-radius:15px;padding:13px}}
"""

_RECENT_RE = re.compile(
    r'(<h3 class="sp-subhead">20 kỳ gần nhất theo chữ số ĐẦU</h3>\s*'
    r'<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-head"></table></div>)\s*'
    r'(<h3 class="sp-subhead">20 kỳ gần nhất theo chữ số ĐUÔI \(đít\)</h3>\s*'
    r'<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-tail"></table></div>)\s*'
    r'(<h3 class="sp-subhead">20 kỳ gần nhất theo TỔNG</h3>\s*'
    r'<div class="sp-scroll"><table class="sp-table sp-grid-lines sp-crosshair" id="sp-day-sum"></table></div>)',
    re.S,
)


def _add_body_classes(page: str, *classes: str) -> str:
    """Add body classes without dropping existing classes; idempotent."""

    wanted = [item for item in classes if item]

    def repl(match: re.Match[str]) -> str:
        attrs = match.group("attrs")
        class_match = _CLASS_RE.search(attrs)
        if class_match:
            current = class_match.group("value").split()
            merged = current + [item for item in wanted if item not in current]
            replacement = f'class={class_match.group("q")}{" ".join(merged)}{class_match.group("q")}'
            attrs2 = attrs[: class_match.start()] + replacement + attrs[class_match.end() :]
            return f"<body{attrs2}>"
        return f'<body{attrs} class="{" ".join(wanted)}">'

    return _BODY_RE.sub(repl, page, count=1)


def _append_style(page: str, css: str) -> str:
    if f'id="{_STYLE_ID}"' in page:
        return page
    style = f'<style id="{_STYLE_ID}">{css}</style>'
    return page.replace("</head>", f"{style}\n</head>", 1)


def _refine_stat(filename: str, page: str) -> str:
    slug = _TARGET_STAT_PAGES[filename]
    extra = []
    if slug == "lo-gan":
        extra.append("sp-gan-dashboard")
    elif slug == "giai-dac-biet-theo-tong":
        extra.append("sp-tong-dashboard")
    page = _add_body_classes(page, "sp-page", f"sp-page-{slug}", *extra)

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
    page = _add_body_classes(page, "ui-dock-space", "path-page")
    page = page.replace('<div class="wrap">', '<div class="wrap path-shell">', 1)
    page = page.replace('<div class="top">', '<div class="top path-hero">', 1)
    page = page.replace(
        '<div class="grid" style="margin-top:12px">',
        '<div class="grid path-overview" style="margin-top:12px">',
        1,
    )
    page = page.replace(
        '<div style="margin-top:10px; overflow:auto">',
        '<div class="path-table-scroll" style="margin-top:10px; overflow:auto">',
        1,
    )
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
            "</section>"
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
            "</section>"
        )
        page = page.replace('</section>\n<div class="ui-note"', f"</section>{pipeline}\n<div class=\"ui-note\"", 1)
    return _append_style(page, _RESEARCH_CSS)


def _refine_live(page: str) -> str:
    page = _add_body_classes(page, "live-console")
    return _append_style(page, _LIVE_CSS)


def refine_page(path: Path | str, page: str) -> str:
    """Return page HTML with the scoped visual refinement for ``path``.

    The function is intentionally a no-op for every non-target page and is
    idempotent for target pages, so live-page refreshes cannot stack styles or
    duplicate UI sections.
    """

    filename = Path(path).name
    if filename in _TARGET_STAT_PAGES:
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
