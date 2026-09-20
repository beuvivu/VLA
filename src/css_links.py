"""Critical Rendering Path optimized stylesheet links.

Strategy:
1. Inline critical CSS for first paint (tokens, shell, header, cards)
2. Preload full sheets + font so they start early on the network
3. Load full CSS non-blocking via media=print onload swap
4. <noscript> keeps full CSS for no-JS clients
"""

from __future__ import annotations

# Above-the-fold critical CSS — keep in sync with docs/assets/ui.css tokens
CRITICAL_CSS = r""":root{--ui-bg:#F2F4FF;--ui-bg-2:#E6EAFB;--ui-surface:#fff;--ui-surface-2:#F7F8FE;--ui-border:#E7EAF6;--ui-ink:#161C2D;--ui-ink-2:#28304A;--ui-ink-soft:#5A6480;--ui-brand:#4f46e5;--ui-brand-ink:#4338ca;--ui-brand-soft:#eef2ff;--ui-on-brand:#fff;--ui-font:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;--ui-page-max:1280px;--ui-page-gutter:clamp(16px,2.5vw,32px);--ui-dock-safe:calc(72px + env(safe-area-inset-bottom,0px));--ui-r-xl:24px}*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}body{margin:0;color:var(--ui-ink-2);background:linear-gradient(162deg,#F2F4FF,#E6EAFB);background-color:#F2F4FF;font-family:var(--ui-font);font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased;min-height:100vh}.ui-app,.app{min-height:100vh;padding-bottom:var(--ui-dock-safe)}.ui-shell,.main,.path-shell{width:100%;max-width:var(--ui-page-max);margin-inline:auto;padding:1.5rem var(--ui-page-gutter) 3rem;min-width:0}.ui-header,header.ui-header,.path-hero{margin-bottom:1.25rem;padding:1.25rem 1.5rem;border-radius:var(--ui-r-xl);background:rgba(255,255,255,.9);border:1px solid rgba(255,255,255,.8)}.ui-header h1,h1{margin:0 0 .35rem;font-size:clamp(1.35rem,2.4vw,1.875rem);font-weight:600;letter-spacing:-.02em;color:var(--ui-ink);line-height:1.25}.ui-sub{color:var(--ui-ink-soft);font-size:.875rem;margin:0}.ui-nav{display:flex;flex-wrap:wrap;gap:.5rem;margin:0 0 1.5rem}.ui-nav a{display:inline-flex;padding:.375rem .75rem;border-radius:.75rem;border:1px solid var(--ui-border);background:var(--ui-surface);color:var(--ui-ink-soft);font-size:.8125rem;font-weight:500;text-decoration:none}.ui-card,.card{background:rgba(255,255,255,.9);border:1px solid rgba(255,255,255,.8);border-radius:var(--ui-r-xl);overflow:hidden}.ui-card-head{padding:1rem 1.25rem;border-bottom:1px solid var(--ui-border)}.ui-card-body{padding:1.25rem}.ui-grid{display:grid;gap:1.25rem}.ui-table-wrap{overflow:auto;max-width:100%}.ui-badge{display:inline-flex;padding:.15rem .55rem;border-radius:999px;font-size:.75rem;font-weight:600}.ui-badge-brand{background:var(--ui-brand-soft);color:var(--ui-brand-ink)}.ui-dock,.dock{position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:60;pointer-events:none}@media(max-width:640px){.ui-shell,.main{padding-left:14px;padding-right:14px}.ui-dock,.dock{left:12px;right:12px;transform:none}}"""


def stylesheet_link() -> str:
    """CRP-friendly head links: critical inline + async full CSS + font preload."""
    parts = [
        # 1) Font early (non-render-blocking; font-display:swap in @font-face)
        '<link rel="preload" href="assets/InterVariable.woff2" as="font" type="font/woff2" crossorigin />',
        # 2) Critical CSS — first paint without waiting for full sheets
        f'<style id="ui-critical">{CRITICAL_CSS}</style>',
        # 3) Preload full stylesheets (high priority fetch, apply async below)
        '<link rel="preload" href="assets/ui.css" as="style" />',
        '<link rel="preload" href="assets/ui-visual-system.css" as="style" />',
        # 4) Apply full CSS without blocking first paint
        '<link rel="stylesheet" href="assets/ui.css" media="print" onload="this.media=\'all\'" />',
        '<link rel="stylesheet" href="assets/ui-visual-system.css" media="print" onload="this.media=\'all\'" data-ui-visual-system />',
        # 5) No-JS fallback
        '<noscript>',
        '<link rel="stylesheet" href="assets/ui.css" />',
        '<link rel="stylesheet" href="assets/ui-visual-system.css" data-ui-visual-system />',
        '</noscript>',
    ]
    return "\n  ".join(parts)
