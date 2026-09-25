"""Critical Rendering Path optimized stylesheet links (CSP-safe, no inline)."""

from __future__ import annotations

from pathlib import Path

try:
    from critical_css_generated import CRITICAL_CSS as _GENERATED
except Exception:
    _GENERATED = None

_FALLBACK_CRITICAL = (
    ":root{--ui-bg:#f0f4fd;--ui-bg-2:#eaedff;--ui-surface:#fff;--ui-border:#e4e7f2;"
    "--ui-ink:#202329;--ui-ink-2:#262b35;--ui-ink-soft:#5c6270;--ui-brand:#2946f3;"
    "--ui-brand-ink:#2038cf;--ui-brand-soft:#eaedff;--ui-on-brand:#fff;"
    "--ui-font:system-ui,-apple-system,\"Segoe UI\",Roboto,Arial,sans-serif;"
    "--ui-page-max:1280px;--ui-page-gutter:clamp(16px,2.5vw,32px);"
    "--ui-r-xl:1.5rem}"
    "*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}"
    "body{margin:0;color:var(--ui-ink-2);"
    "background:linear-gradient(180deg,var(--ui-bg) 0%,var(--ui-bg-2) 100%);"
    "background-color:var(--ui-bg);font-family:var(--ui-font);font-size:14px;line-height:1.6;"
    "min-height:100vh;-webkit-font-smoothing:antialiased}"
    ".ui-app,.app{min-height:100vh}"
    ".ui-shell,.main,.path-shell{width:100%;max-width:var(--ui-page-max);margin-inline:auto;"
    "padding:1.5rem var(--ui-page-gutter) 3rem;min-width:0}"
    ".ui-header,header.ui-header,.path-hero{margin-bottom:1.25rem;padding:1.25rem 1.5rem;"
    "border-radius:var(--ui-r-xl);background:rgba(255,255,255,.9);border:1px solid rgba(255,255,255,.8)}"
    ".ui-header h1,h1{margin:0 0 .35rem;font-size:clamp(1.35rem,2.4vw,1.875rem);font-weight:600;"
    "letter-spacing:-.02em;color:var(--ui-ink);line-height:1.25}"
    ".ui-card,.card{background:rgba(255,255,255,.9);border:1px solid rgba(255,255,255,.8);"
    "border-radius:var(--ui-r-xl);overflow:hidden}"
)

CRITICAL_CSS = _GENERATED or _FALLBACK_CRITICAL


def ensure_critical_css_file(assets_dir: Path | None = None) -> Path:
    root = Path(__file__).resolve().parents[1]
    path = (assets_dir or (root / "docs" / "assets")) / "critical.css"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CRITICAL_CSS, encoding="utf-8")
    return path


def stylesheet_link() -> str:
    """CRP head links without inline script/style handlers (CSP 'self' only)."""
    parts = [
        '<link rel="preload" href="assets/InterVariable.woff2" as="font" type="font/woff2" crossorigin />',
        '<link rel="stylesheet" href="assets/critical.css" />',
        '<link rel="preload" href="assets/ui.css" as="style" />',
        '<link rel="preload" href="assets/ui-visual-system.css" as="style" />',
        '<link rel="stylesheet" href="assets/ui.css" media="print" data-async-css="1" />',
        '<link rel="stylesheet" href="assets/ui-visual-system.css" media="print" data-async-css="1" data-ui-visual-system />',
        '<script src="assets/css-async.js" defer></script>',
        '<noscript>',
        '<link rel="stylesheet" href="assets/ui.css" />',
        '<link rel="stylesheet" href="assets/ui-visual-system.css" data-ui-visual-system />',
        '</noscript>',
    ]
    return "\n  ".join(parts)
