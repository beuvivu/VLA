from __future__ import annotations

from pathlib import Path

from build_landing_page import build_landing_page


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
