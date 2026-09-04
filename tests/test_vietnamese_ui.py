from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from ui_locale import column_label, mode_label, path_kind_label, value_label
from ui_theme import TAILWIND_LITE_CSS, tailwind_style_tag


ROOT = Path(__file__).resolve().parents[1]


def _visible_text(path: Path) -> str:
    document = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    return document.get_text(" ", strip=True)


def test_shared_display_labels_keep_machine_keys_out_of_the_ui() -> None:
    assert mode_label("loto") == "Lô tô"
    assert mode_label("de") == "Đặc Biệt"
    assert path_kind_label("active") == "Đang chạy"
    assert column_label("current_gap") == "Gan hiện tại"
    assert value_label("reverse_concat") == "Ghép đảo"


def test_local_tailwind_theme_is_csp_safe_and_has_required_utilities() -> None:
    assert "bg-slate-50" in TAILWIND_LITE_CSS
    assert "text-slate-800" in TAILWIND_LITE_CSS
    assert "hover\\:shadow-lg:hover" in TAILWIND_LITE_CSS
    style = tailwind_style_tag()
    assert 'id="vla-tailwind-lite"' in style
    assert "https://" not in style


def test_dashboard_builder_renders_vietnamese_without_shadowing_html_module() -> None:
    subprocess.run([sys.executable, "src/build_dashboard.py"], cwd=ROOT, check=True)

    dashboard = _visible_text(ROOT / "docs/dashboard.html")
    quality = _visible_text(ROOT / "docs/model-quality.html")
    assert "Bảng điều khiển phân tích XSMB" in dashboard
    assert "Chất lượng mô hình" in quality
    assert "Latest data date" not in dashboard
    assert "Model Quality" not in quality
    assert "Đề" not in dashboard


def test_public_pages_do_not_reintroduce_retired_english_ui_phrases() -> None:
    retired = (
        "Click-to-explain",
        "Predict for:",
        "Support paths",
        "Scientific Research Lab",
        "Top probabilities",
        "XSMB Near-Live",
    )
    pages = (
        "index.html",
        "statistics.html",
        "dashboard.html",
        "model-quality.html",
        "research-lab.html",
        "ml_top10_loto.html",
        "ml_top10_de.html",
        "soi-path-de-active.html",
        "soi-path-de-stable.html",
        "soi-path-loto-active.html",
    )
    for name in pages:
        text = _visible_text(ROOT / "docs" / name)
        for phrase in retired:
            assert phrase not in text, (name, phrase)
        assert "Đề" not in text, name
