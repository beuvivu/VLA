from __future__ import annotations

from pathlib import Path

from build_landing_page import _fmt2, build_landing_page
from web_security import json_for_html_script


def test_landing_page_contains_navigation_and_sections() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    outputs = build_landing_page(repo_root=repo_root)

    assert (repo_root / "docs" / "index.html") in outputs
    assert (repo_root / "docs" / "landing.html") in outputs

    html = (repo_root / "docs" / "landing.html").read_text(encoding="utf-8")

    for section_id in [
        "tong-quan",
        "ket-qua",
        "chuc-don-vi",
        "ai-ml",
        "tan-suat-loto",
        "tan-suat-de",
        "gan-nhip",
        "cap-lon",
        "dau-duoi-tong",
        "db-tuan-thang",
        "duong-cau",
        "backtest",
    ]:
        assert f'id="{section_id}"' in html or f"id='{section_id}'" in html
        assert f"#{section_id}" in html

    assert "Menu thống kê" in html
    assert "Kết quả hàng ngày" in html
    assert "Chục × đơn vị" in html
    assert "data-number" in html
    assert "landing-data" in html
    assert "statistics.html" in html


def test_landing_page_is_self_contained() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    build_landing_page(repo_root=repo_root)
    html = (repo_root / "docs" / "landing.html").read_text(encoding="utf-8")

    assert "https://cdn" not in html
    assert "http://cdn" not in html
    assert "<script type=\"application/json\" id=\"landing-data\">" in html


def test_landing_page_escapes_embedded_data_and_avoids_untrusted_inner_html() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    build_landing_page(repo_root=repo_root)
    rendered = (repo_root / "docs" / "landing.html").read_text(encoding="utf-8")

    payload = json_for_html_script({"value": "</script><img src=x onerror=alert(1)>&"})
    assert "</script>" not in payload
    assert "<img" not in payload
    assert "\\u003c" in payload and "\\u0026" in payload
    assert _fmt2("' onmouseover='alert(1)") == ""
    assert "li.innerHTML =" not in rendered
    assert "Content-Security-Policy" in rendered
    assert 'name="referrer" content="no-referrer"' in rendered
