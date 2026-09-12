from __future__ import annotations

from pathlib import Path

from build_landing_page import _fmt2, build_landing_page
from web_security import json_for_html_script


def test_landing_page_contains_navigation_and_sections(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    outputs = build_landing_page(repo_root=repo_root, docs_dir=tmp_path)

    assert (tmp_path / "index.html") in outputs
    assert (tmp_path / "landing.html") in outputs

    html = (tmp_path / "landing.html").read_text(encoding="utf-8")

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

    # Sidebar đã thay bằng dock nổi; điều hướng vẫn phải phủ đủ nhóm.
    assert 'class="dock"' in html
    assert "Điều hướng chính" in html
    assert "Kết quả hàng ngày" in html
    assert "Chục × đơn vị" in html
    assert "data-number" in html
    assert "landing-data" in html
    assert "statistics.html" in html


def test_landing_page_is_self_contained(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    build_landing_page(repo_root=repo_root, docs_dir=tmp_path)
    html = (tmp_path / "landing.html").read_text(encoding="utf-8")

    assert "https://cdn" not in html
    assert "http://cdn" not in html
    assert "<script type=\"application/json\" id=\"landing-data\">" in html


def test_landing_page_escapes_embedded_data_and_avoids_untrusted_inner_html(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    build_landing_page(repo_root=repo_root, docs_dir=tmp_path)
    rendered = (tmp_path / "landing.html").read_text(encoding="utf-8")

    payload = json_for_html_script({"value": "</script><img src=x onerror=alert(1)>&"})
    assert "</script>" not in payload
    assert "<img" not in payload
    assert "\\u003c" in payload and "\\u0026" in payload
    assert _fmt2("' onmouseover='alert(1)") == ""
    assert "li.innerHTML =" not in rendered
    assert "Content-Security-Policy" in rendered
    assert 'name="referrer" content="no-referrer"' in rendered


def test_landing_variants_share_snapshot_across_minute_boundary(tmp_path, monkeypatch):
    import hashlib
    from datetime import UTC, datetime
    import build_landing_page as landing

    instants = iter([
        datetime(2026, 9, 12, 12, 0, 59, tzinfo=UTC),
        datetime(2026, 9, 12, 12, 1, 0, tzinfo=UTC),
    ])

    class AdvancingClock:
        @staticmethod
        def now(tz):
            return next(instants)

    monkeypatch.setattr(landing, "datetime", AdvancingClock)
    landing.build_landing_page(repo_root=Path(__file__).resolve().parents[1], docs_dir=tmp_path)
    normal = (tmp_path / "index.html").read_text()
    desktop = (tmp_path / "landing_desktop.html").read_text().replace(' class="desktop-view"', '', 1)
    assert hashlib.sha256(normal.encode()).digest() == hashlib.sha256(desktop.encode()).digest()
    assert '2026-09-12 12:00 UTC' in normal
