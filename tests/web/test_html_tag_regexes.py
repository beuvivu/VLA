from __future__ import annotations

import importlib.util
from pathlib import Path

from web.page_output import strip_comments

ROOT = Path(__file__).resolve().parents[2]


def _patch_csp():
    spec = importlib.util.spec_from_file_location("patch_csp_no_inline", ROOT / "scripts" / "web" / "patch_csp_no_inline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_comment_closed_with_bang_ends_where_the_browser_ends_it() -> None:
    assert strip_comments("<p>a</p><!-- x --!><p>b</p>") == "<p>a</p><p>b</p>"
    assert strip_comments("<p>a</p><!-- x --><p>b</p>") == "<p>a</p><p>b</p>"
    assert strip_comments("<!--[if IE]><p>c</p><![endif]-->") == "<!--[if IE]><p>c</p><![endif]-->"


def test_the_csp_hash_covers_only_the_script_body_when_the_end_tag_has_a_space(tmp_path: Path) -> None:
    module = _patch_csp()
    page = tmp_path / "x.html"
    page.write_text("<html><head></head><body><script>a()</script ><p>b</p><script>c()</script></body></html>",
                    encoding="utf-8")
    module.rewrite_html(page)
    html = page.read_text(encoding="utf-8")
    assert module.sha256_csp("a()") in html
    assert module.sha256_csp("c()") in html
