"""Scoped presentation refinements for selected published VLA pages.

Builders remain responsible for data and semantic markup. This compositor is
applied at the HTML output boundary so daily regeneration cannot erase the
visual system. It only adds presentation classes, responsive wrappers and
visual modules; statistical values, element ids and JavaScript data hooks are
left untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["refine_page"]

_STYLE_ID = "vla-targeted-ui-refinement"
_STYLE_RE = re.compile(rf'<style id="{re.escape(_STYLE_ID)}">.*?</style>', re.I | re.S)
_BODY_RE = re.compile(r"<body(?P<attrs>[^>]*)>", re.I)
_CLASS_RE = re.compile(r'class=(?P<q>["\'])(?P<value>.*?)(?P=q)', re.I | re.S)

_TARGET_STAT_PAGES = {
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

_STAT_CSS = r"""
.sp-page{
  min-height:100vh;
  background:linear-gradient(135deg,#F4F5FF 0%,#EAEBFF 48%,#E8ECFF 100%);
}
.sp-page .ui-shell-wide{max-width:1280px;margin-inline:auto;padding-inline:clamp(1rem,2.4vw,2rem)}
.sp-page h1{letter-spacing:-.03em}
.sp-page .sp-controls{
  width:100%;margin:1rem 0 1.25rem;padding:1rem 1.1rem;
  background:rgba(255,255,255,.84);border-color:rgba(255,255,255,.92);
  box-shadow:0 8px 30px rgba(15,23,42,.05);
  backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)
}
.sp-page .sp-scroll,.sp-page .sp-duo>div,.sp-page .sp-recent-card{
  background:rgba(255,255,255,.88);border-color:rgba(255,255,255,.92);
  box-shadow:0 8px 30px rgba(15,23,42,.045);backdrop-filter:blur(12px);
  -webkit-backdrop-filter:blur(12px)
}
.sp-page .sp-subhead{display:flex;align-items:center;gap:.55rem;margin:1.35rem 0 .7rem;letter-spacing:-.015em}
.sp-page .sp-subhead::before{content:"";width:.45rem;height:.45rem;border-radius:50%;background:#4f46e5;box-shadow:0 0 0 5px #e0e7ff}
.sp-page .sp-table th{background:#f8fafc;color:#334155}
.sp-page .sp-table tbody tr:hover{background:#f8faff}
.sp-page .sp-note{border-radius:16px;box-shadow:0 8px 24px rgba(15,23,42,.035)}

.sp-page-bang-dac-biet .sp-scroll{width:100%;max-width:100%}
.sp-page-bang-dac-biet #sp-grid{width:100%;min-width:760px;table-layout:fixed}
.sp-page-bang-dac-biet #sp-grid th,.sp-page-bang-dac-biet #sp-grid td{text-align:center;padding:.76rem .55rem}
.sp-page-bang-dac-biet #sp-grid th:first-child,.sp-page-bang-dac-biet #sp-grid td:first-child{text-align:left}

.sp-page-lo-gan .sp-scroll{width:100%;max-width:100%;max-height:34rem;overflow:auto;overscroll-behavior:contain}
.sp-page-lo-gan #sp-grid,.sp-page-lo-gan #sp-pair-gan{width:100%}
.sp-page-lo-gan .sp-duo{grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}
.sp-page-lo-gan .sp-duo>div{max-height:30rem;overflow:auto;overscroll-behavior:contain}
.sp-page-lo-gan .sp-duo .sp-table{width:100%}
.sp-page-lo-gan .sp-note{margin-top:.25rem}
.sp-gan-dashboard .sp-controls{position:relative;z-index:2}

.sp-page-dau-duoi-loto .sp-duo{grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}
.sp-page-dau-duoi-loto .sp-duo .sp-table{width:100%}
.sp-page-dau-duoi-loto .sp-recent-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem;margin-top:1.25rem;align-items:start}
.sp-page-dau-duoi-loto .sp-recent-card{min-width:0;padding:1rem;border:1px solid rgba(255,255,255,.92);border-radius:18px}
.sp-page-dau-duoi-loto .sp-recent-card .sp-subhead{margin:.1rem 0 .75rem;font-size:.9rem}
.sp-page-dau-duoi-loto .sp-recent-card .sp-scroll{width:100%;max-width:100%;max-height:32rem;overflow:auto;box-shadow:none;border:0}
.sp-page-dau-duoi-loto .sp-recent-card .sp-table{width:100%}

.sp-page-giai-dac-biet-theo-tong .sp-scroll{width:100%;max-width:100%;overflow:auto}
.sp-page-giai-dac-biet-theo-tong #sp-grid,.sp-page-giai-dac-biet-theo-tong #sp-trans,.sp-page-giai-dac-biet-theo-tong #sp-parity{width:100%;min-width:max-content}
.sp-page-giai-dac-biet-theo-tong .sp-scroll:has(#sp-trans){max-height:38rem;overflow:auto;overscroll-behavior:contain}
.sp-page-giai-dac-biet-theo-tong .sp-note{max-width:none}
.sp-tong-dashboard .sp-controls{position:relative;z-index:2}

.sp-page-cau-dac-biet-theo-bo-so .sp-scroll,
.sp-page-giai-db-ngay-mai .sp-scroll,
.sp-page-cap-lon-loto .sp-scroll{width:100%;max-width:100%;max-height:38rem;overflow:auto;overscroll-behavior:contain}
.sp-page-cau-dac-biet-theo-bo-so #sp-grid,
.sp-page-giai-db-ngay-mai #sp-grid,
.sp-page-cap-lon-loto #sp-grid,
.sp-page-cap-lon-loto #sp-kep{width:100%}
.sp-page-cau-dac-biet-theo-bo-so .sp-scroll,
.sp-page-giai-db-ngay-mai .sp-scroll{border-radius:20px}
.sp-page-cap-lon-loto .sp-scroll{border-radius:18px}

@media(max-width:900px){
 .sp-page-lo-gan .sp-duo,.sp-page-dau-duoi-loto .sp-duo,.sp-page-dau-duoi-loto .sp-recent-grid{grid-template-columns:1fr}
 .sp-page-bang-dac-biet #sp-grid{min-width:680px}
}
@media(max-width:640px){
 .sp-page .ui-shell-wide{padding-inline:12px}
 .sp-page .sp-controls{padding:.85rem;border-radius:16px}
 .sp-page .sp-scroll{border-radius:16px}
}
"""

_PATH_CSS = r"""
.path-page{
  --bg:#F4F5FF;--card:rgba(255,255,255,.86);--text:#0f172a;--muted:#64748b;
  --line:#dbe3f0;--hit:#f59e0b;--hitde:#dc2626;--ok:#059669;--chip:#eef2ff;
  --ui-bg:#F4F5FF;--ui-surface:rgba(255,255,255,.9);--ui-surface-2:#f8fafc;
  --ui-ink:#0f172a;--ui-ink-2:#334155;--ui-ink-soft:#64748b;--ui-border:#dbe3f0;
  --ui-brand:#4f46e5;--ui-brand-soft:#eef2ff;--ui-brand-border:#c7d2fe;
  min-height:100vh;padding-bottom:calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 2rem);
  background:linear-gradient(135deg,#F4F5FF 0%,#EAEBFF 48%,#E8ECFF 100%);color:#0f172a
}
.path-page a{color:#4338ca}
.path-page .path-shell{max-width:1280px;margin-inline:auto;padding:clamp(1rem,2.5vw,2rem);padding-bottom:calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 2.25rem)}
.path-page .path-hero{padding:1.15rem 1.2rem;border:1px solid rgba(255,255,255,.92);border-radius:20px;background:rgba(255,255,255,.84);box-shadow:0 8px 30px rgba(15,23,42,.05);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}
.path-page .path-hero h1{font-size:clamp(1.3rem,2.5vw,2rem)!important;letter-spacing:-.03em;color:#0f172a}
.path-page .path-hero .small{color:#64748b}
.path-page .path-overview{gap:1rem;margin-top:1rem!important;grid-template-columns:minmax(0,1.15fr) minmax(18rem,.85fr)}
.path-page .card{border-radius:20px;border-color:rgba(255,255,255,.92);background:rgba(255,255,255,.86);box-shadow:0 8px 30px rgba(15,23,42,.045);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.path-page .card b,.path-page .quick-number{color:#0f172a}.path-page .small{color:#64748b}.path-page .chip{background:#eef2ff;border-color:#dbe3f0;color:#475569}
.path-page .btn{background:#4f46e5;color:#fff;border-color:#4f46e5}.path-page .btn.secondary{background:#fff;color:#334155;border-color:#dbe3f0}
.path-page .quick-pick{min-height:3.15rem;border-radius:14px;background:#fff;border-color:#dbe3f0;color:#0f172a}.path-page .quick-pick:hover{background:#eef2ff;border-color:#a5b4fc}
.path-page .dot.none{background:#94a3b8}.path-page table{background:transparent}.path-page th{background:rgba(248,250,252,.96);color:#334155}.path-page td{color:#0f172a;border-color:#e2e8f0}.path-page tr:hover td{background:#f8faff}
.path-page .cell{background:#fff;border-color:#dbe3f0;color:#0f172a}.path-page .cell.none{background-color:#E2E8F0;background-image:repeating-linear-gradient(135deg,transparent 0 7px,rgba(156,163,175,.32) 7px 8px);color:#475569}.path-page .cell.hit{background:#fff7ed;border-color:#fdba74;color:#9a3412}.path-page .cell.hitde{background:#FEE2E2;border-color:#f87171;color:#DC2626;font-weight:800}
.path-page .path-table-scroll{max-height:min(66vh,52rem);overflow:auto;overscroll-behavior:contain;border:1px solid #dbe3f0;border-radius:14px;background:#fff}
.path-page .path-table-scroll table{margin:0}.path-page .path-table-scroll th{top:0;z-index:3;box-shadow:0 1px 0 #dbe3f0}
.path-page .ui-nav-fallback{margin-bottom:calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 1rem)}
@media(max-width:979px){.path-page .path-overview{grid-template-columns:1fr}.path-page .path-table-scroll{max-height:58vh}}
@media(max-width:640px){.path-page .path-shell{padding:12px 12px calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 2.5rem)}.path-page .path-hero{padding:.9rem;border-radius:16px}.path-page .card{border-radius:16px;padding:12px}.path-page .quick-grid{grid-template-columns:1fr 1fr}}
"""

_DASHBOARD_CSS = r"""
.ai-command-center{min-height:100vh;background:linear-gradient(135deg,#F4F5FF 0%,#EAEBFF 48%,#E8ECFF 100%)}
.ai-command-center .ui-shell{max-width:1280px}
.ai-command-center .ui-header{position:relative;overflow:hidden;padding:clamp(1.35rem,3vw,2.2rem);border:1px solid rgba(255,255,255,.92);border-radius:24px;background:rgba(255,255,255,.82);box-shadow:0 8px 30px rgba(15,23,42,.05);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}
.ai-command-center .ui-header::after{content:"AI";position:absolute;right:1rem;top:-1.5rem;font-size:7rem;font-weight:900;letter-spacing:-.08em;color:rgba(79,70,229,.07);pointer-events:none}
.ai-status-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.8rem;margin:1rem 0 1.25rem}
.ai-status-item{position:relative;overflow:hidden;min-width:0;padding:1rem 1.05rem;border:1px solid rgba(255,255,255,.94);border-radius:18px;background:rgba(255,255,255,.84);box-shadow:0 8px 30px rgba(15,23,42,.04);backdrop-filter:blur(14px)}
.ai-status-item::after{content:"";position:absolute;left:1rem;right:1rem;bottom:.65rem;height:3px;border-radius:999px;background:linear-gradient(90deg,#4f46e5 0 32%,#818cf8 32% 63%,#c7d2fe 63% 100%);opacity:.75}
.ai-status-item span{display:block;font-size:.66rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#64748b}.ai-status-item strong{display:block;margin-top:.25rem;padding-bottom:.55rem;font-size:.92rem;color:#0f172a}
.ai-signal-grid{align-items:start}.ai-signal-grid>.ui-card{border-color:rgba(255,255,255,.94);background:rgba(255,255,255,.86);box-shadow:0 8px 30px rgba(15,23,42,.045);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.ai-signal-grid>.ui-card:nth-child(-n+2){position:relative;overflow:hidden;border-color:#c7d2fe;box-shadow:0 14px 36px rgba(79,70,229,.08)}.ai-signal-grid>.ui-card:nth-child(-n+2)::before{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:linear-gradient(180deg,#4f46e5,#818cf8)}
.ai-signal-grid>.ui-card .ui-card-head h2{letter-spacing:-.02em}.ai-command-center .ui-table{font-variant-numeric:tabular-nums}.ai-command-center .ui-table th{background:#f8fafc}
@media(max-width:760px){.ai-status-strip{grid-template-columns:1fr}.ai-command-center .ui-header::after{font-size:4.5rem}}
"""

_RESEARCH_CSS = r"""
.research-workspace{min-height:100vh;background:linear-gradient(135deg,#F4F5FF 0%,#EAEBFF 48%,#E8ECFF 100%)}
.research-workspace .ui-shell-wide{max-width:1280px;margin-inline:auto}
.research-workspace .rl-hero{position:relative;overflow:hidden;padding:clamp(1.5rem,3vw,2.5rem);background:radial-gradient(circle at 88% 20%,rgba(56,189,248,.18),transparent 17rem),linear-gradient(135deg,#07111f,#0f172a 58%,#111827);border:1px solid #263449;box-shadow:0 24px 65px rgba(2,6,23,.2);border-radius:24px}
.research-workspace .rl-hero::before{content:"LIVE AI PROCESSING";position:absolute;right:1.25rem;top:1.15rem;padding:.3rem .55rem;border:1px solid rgba(34,197,94,.35);border-radius:999px;background:rgba(34,197,94,.1);color:#86efac;font:800 .62rem ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em}
.research-workspace .rl-hero::after{content:"LAB / 01";position:absolute;right:1.25rem;bottom:.8rem;font:800 .68rem ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.16em;color:#64748b}
.rl-pipeline{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.65rem;margin:0 0 1rem}.rl-stage{position:relative;padding:.9rem .85rem;border:1px solid rgba(255,255,255,.94);border-radius:18px;background:rgba(255,255,255,.86);box-shadow:0 8px 30px rgba(15,23,42,.04);backdrop-filter:blur(14px)}
.rl-stage:not(:last-child)::after{content:"→";position:absolute;right:-.52rem;top:50%;transform:translateY(-50%);z-index:2;color:#64748b;font-weight:900}.rl-stage span{display:block;font-size:.64rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#64748b}.rl-stage strong{display:block;margin-top:.3rem;font-size:.86rem;color:#0f172a}.rl-stage:last-child{border-color:#c7d2fe;background:#eef2ff}
.rl-console{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.85rem;margin:0 0 1.25rem}.rl-console-card{position:relative;overflow:hidden;min-height:9rem;padding:1rem;border:1px solid rgba(99,102,241,.24);border-radius:18px;background:linear-gradient(180deg,rgba(255,255,255,.9),rgba(248,250,252,.84));box-shadow:0 10px 34px rgba(30,41,59,.05)}
.rl-console-card::before{content:"";position:absolute;inset:0;pointer-events:none;border-radius:inherit;box-shadow:inset 0 0 0 1px rgba(56,189,248,.08)}.rl-console-card::after{content:"";position:absolute;left:0;right:0;top:-30%;height:32%;background:linear-gradient(180deg,transparent,rgba(56,189,248,.10),transparent);animation:rl-scan 5s linear infinite;pointer-events:none}
.rl-console-card span{display:block;font:800 .62rem ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em;text-transform:uppercase;color:#6366f1}.rl-console-card strong{display:block;margin:.45rem 0 .35rem;font-size:1rem;color:#0f172a}.rl-console-card p{margin:0;color:#64748b;font-size:.75rem;line-height:1.55}.rl-gauge{width:3rem;height:3rem;margin-top:.55rem;border-radius:50%;background:conic-gradient(#4f46e5 0 28%,#22c55e 28% 58%,#38bdf8 58% 76%,#e2e8f0 76%);box-shadow:inset 0 0 0 8px #fff}
.rl-instruments>.ui-card{position:relative;overflow:hidden;border-color:rgba(99,102,241,.18);background:rgba(255,255,255,.88);box-shadow:0 8px 30px rgba(15,23,42,.045)}.rl-instruments>.ui-card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;background:linear-gradient(180deg,#4f46e5,#38bdf8)}
.research-workspace .metric-card{position:relative;overflow:hidden;background:linear-gradient(180deg,rgba(255,255,255,.94),rgba(248,250,252,.9));border-color:rgba(255,255,255,.95)}.research-workspace .metric-card::after{content:"";position:absolute;right:.85rem;top:.85rem;width:.46rem;height:.46rem;border-radius:50%;background:#22c55e;box-shadow:0 0 0 4px rgba(34,197,94,.1)}
@keyframes rl-scan{0%{transform:translateY(-140%)}100%{transform:translateY(480%)}}
@media(prefers-reduced-motion:reduce){.rl-console-card::after{animation:none}}
@media(max-width:1000px){.rl-console{grid-template-columns:repeat(2,minmax(0,1fr))}.rl-pipeline{grid-template-columns:repeat(2,minmax(0,1fr))}.rl-stage::after{display:none}}
@media(max-width:600px){.rl-console,.rl-pipeline{grid-template-columns:1fr}.research-workspace .rl-hero::before{position:static;display:inline-block;margin-bottom:.75rem}}
"""

_LIVE_CSS = r"""
.live-console{
  --bg:#F4F5FF;--card:rgba(255,255,255,.88);--card-2:#f8fafc;--line:#dbe3f0;
  --ink:#0f172a;--ink-2:#475569;--ink-3:#64748b;--accent:#4f46e5;
  --ok:#059669;--ok-line:#a7f3d0;--warn:#d97706;--warn-line:#fed7aa;--hot:#DC2626;
  min-height:100vh;padding-bottom:calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 1rem);
  background:linear-gradient(135deg,#F4F5FF 0%,#EAEBFF 48%,#E8ECFF 100%);color:#0f172a
}
.live-console .wrap{max-width:1280px;padding:24px 18px 36px;display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px}
.live-console .wrap>.top{grid-column:1/-1;padding:1rem 1.15rem;border:1px solid rgba(255,255,255,.94);border-radius:20px;background:rgba(255,255,255,.84);box-shadow:0 8px 30px rgba(15,23,42,.05);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}
.live-console .wrap>.top h1{color:#0f172a;letter-spacing:-.03em}.live-console .wrap>.top .muted{color:#64748b}
.live-console .card{margin:0;border-color:rgba(255,255,255,.94);border-radius:20px;background:rgba(255,255,255,.88);box-shadow:0 8px 30px rgba(15,23,42,.045);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.live-console .live-status-card{grid-column:span 4;align-self:start}.live-console .live-results-card{grid-column:span 8;grid-row:2/span 2}.live-console .live-sources-card{grid-column:span 4;align-self:start}
.live-console .live-status-card #status{display:flex;align-items:center;gap:.5rem;color:#0f172a}.live-console .live-status-card #status::before{content:"";width:.55rem;height:.55rem;border-radius:50%;background:#22c55e;box-shadow:0 0 0 5px rgba(34,197,94,.10)}
.live-console .bar{background:#e2e8f0}.live-console .fill{background:linear-gradient(90deg,#4f46e5,#22c55e)}
.live-console #results{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:16px}.live-console .prize{min-height:3.5rem;border-color:#e2e8f0}.live-console .prize[data-prize=special],.live-console .prize[data-prize=prize3],.live-console .prize[data-prize=prize5],.live-console .prize[data-prize=prize7]{grid-column:1/-1}
.live-console .prize-label{color:#475569}.live-console .dot{background:#94a3b8}.live-console .slot{background:#fff;border-color:#dbe3f0;color:#0f172a;box-shadow:0 2px 8px rgba(15,23,42,.03)}
.live-console .slot.is-empty{color:#64748b;background-color:#E2E8F0;background-image:repeating-linear-gradient(135deg,transparent 0 7px,rgba(156,163,175,.38) 7px 8px);border-color:#cbd5e1}
.live-console .slot.is-special{color:#DC2626;border-color:#f87171;background:#FEE2E2;box-shadow:0 4px 16px rgba(220,38,38,.08)}
.live-console .slot.is-fresh{border-color:#818cf8;box-shadow:0 0 0 3px rgba(99,102,241,.12)}
.live-console .src{border-color:#e2e8f0;color:#475569}.live-console .foot{color:#64748b}.live-console .muted{color:#64748b}.live-console a{color:#4338ca}.live-console .badge{border-color:#dbe3f0;color:#334155}.live-console .badge.ok{border-color:#a7f3d0;color:#047857;background:#ecfdf5}.live-console .badge.warn{border-color:#fed7aa;color:#b45309;background:#fff7ed}
.live-console .ui-live-nav{margin-top:1rem;padding-bottom:calc(var(--ui-dock-h,64px) + env(safe-area-inset-bottom) + 2.5rem);color:#475569}.live-console .ui-live-nav h2{color:#64748b}.live-console .ui-live-nav a{color:#4338ca}
@media(max-width:900px){.live-console .live-status-card,.live-console .live-results-card,.live-console .live-sources-card{grid-column:1/-1;grid-row:auto}.live-console #results{grid-template-columns:1fr}.live-console .prize{grid-column:1/-1!important}}
@media(max-width:620px){.live-console .wrap{padding:12px 12px 28px;gap:10px}.live-console .wrap>.top{padding:.9rem;border-radius:16px}.live-console .card{border-radius:16px;padding:13px}}
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
    slug = _TARGET_STAT_PAGES[filename]
    extras: list[str] = []
    if slug == "lo-gan":
        extras.append("sp-gan-dashboard")
    elif slug == "giai-dac-biet-theo-tong":
        extras.append("sp-tong-dashboard")
    page = _add_body_classes(page, "sp-page", f"sp-page-{slug}", *extras)
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
            '</section>'
            '<section class="rl-console" aria-label="Bộ công cụ phòng thí nghiệm">'
            '<article class="rl-console-card"><span>AI PARAMETERS</span><strong>Bảng tham số thuật toán AI</strong><p>FDR · hiệu chỉnh · tập giữ lại · kiểm tra thực tế. Giá trị thật nằm trong các mô-đun bên dưới.</p></article>'
            '<article class="rl-console-card"><span>BACKTEST RUNNER</span><strong>Khung chạy Backtest mô phỏng</strong><p>Walk-forward theo thời gian; tách huấn luyện, kiểm định và holdout để chặn leakage.</p></article>'
            '<article class="rl-console-card"><span>NUMBER × BÓNG MATRIX</span><strong>Ma trận ma sát số &amp; bóng</strong><p>Không gian 107 ô chữ số và các phép ghép/bóng được kiểm tra như một họ giả thuyết.</p></article>'
            '<article class="rl-console-card"><span>CONFIDENCE SCORE GAUGE</span><strong>FDR + OOS + Reality Check</strong><div class="rl-gauge" aria-hidden="true"></div><p>Gauge là trạng thái cổng kiểm chứng, không phải xác suất trúng.</p></article>'
            '</section>'
        )
        page = page.replace(
            '</section>\n<div class="ui-note"',
            f'{pipeline}\n<div class="ui-note"',
            1,
        )
    return _append_style(page, _RESEARCH_CSS)


def _refine_live(page: str) -> str:
    page = _add_body_classes(page, "live-console")
    page = page.replace('<div class="top" style="margin-bottom:4px">', '<div class="top live-hero" style="margin-bottom:4px">', 1)
    page = page.replace('<div class="card">', '<div class="card live-status-card">', 1)
    page = page.replace('<div class="card">', '<div class="card live-results-card">', 1)
    page = page.replace('<div class="card">', '<div class="card live-sources-card">', 1)
    return _append_style(page, _LIVE_CSS)


def refine_page(path: Path | str, page: str) -> str:
    """Return idempotently refined HTML for a selected output filename."""

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
