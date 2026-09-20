from __future__ import annotations

"""Security helpers shared by the static HTML builders."""

import json
import re
from typing import Any

# Strict CSP — no unsafe-inline for scripts or styles.
# Remaining page-specific <style>/<script> blocks should use CSP hashes
# (see scripts/patch_csp_no_inline.py) or be moved to assets/*.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "form-action 'none'; "
    "frame-src 'none'; "
    "img-src 'self' data:; "
    "object-src 'none'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "upgrade-insecure-requests"
)


def security_meta_tags(*, connect_sources: tuple[str, ...] = ()) -> str:
    """Return defense-in-depth policy tags for self-contained static pages."""
    for source in connect_sources:
        if re.fullmatch(r"https://(?:\*\.)?[A-Za-z0-9.-]+(?::\d+)?", source) is None:
            raise ValueError(f"invalid CSP connect source: {source!r}")
    connect = " ".join(("'self'", *connect_sources))
    policy = CONTENT_SECURITY_POLICY.replace("connect-src 'self'", f"connect-src {connect}")
    return (
        f'<meta http-equiv="Content-Security-Policy" content="{policy}" />\n'
        '<meta name="referrer" content="no-referrer" />'
    )


def json_for_html_script(payload: Any) -> str:
    """Serialize JSON without allowing data to terminate its script element."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def security_script_tags() -> str:
    """External scripts required when CSP disallows unsafe-inline."""
    return (
        '<script src="assets/css-async.js" defer></script>\n'
        '<script src="assets/apply-data-styles.js" defer></script>\n'
        '<script src="assets/ui-dock.js" defer></script>'
    )
