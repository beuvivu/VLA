from __future__ import annotations

"""Security helpers shared by the static HTML builders."""

import json
from typing import Any


CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "base-uri 'none'; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "form-action 'none'; "
    "frame-src 'none'; "
    "img-src 'self' data:; "
    "object-src 'none'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'"
)


def security_meta_tags() -> str:
    """Return defense-in-depth policy tags for self-contained static pages."""
    return (
        f'<meta http-equiv="Content-Security-Policy" content="{CONTENT_SECURITY_POLICY}" />\n'
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
