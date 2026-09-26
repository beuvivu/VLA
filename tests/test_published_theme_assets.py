"""Bản xuất bản phải theo đúng nguồn đã kiểm, không giữ CSS tạm khi dựng."""
from pathlib import Path

import pytest

from page_output import strip_css

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("source,published", [
    ("templates/app_design.css", "app-design.css"),
    ("templates/app_shell.css", "app-shell.css"),
    ("templates/ui_visual_system.css", "ui-visual-system.css"),
    ("assets/app-theme.js", "app-theme.js"),
    ("assets/app-motion.js", "app-motion.js"),
    ("assets/app-shell.js", "app-shell.js"),
])
def test_published_theme_asset_matches_its_reviewed_source(source, published):
    expected = (ROOT / "src" / source).read_text(encoding="utf-8")
    if source.endswith(".css"):
        expected = strip_css(expected)
    assert (ROOT / "docs/assets" / published).read_text(encoding="utf-8") == expected
