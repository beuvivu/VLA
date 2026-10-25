"""Trang ML ưu tiên bảng đọc được, giữ nguyên số liệu và căn cứ công bố."""

import json
from pathlib import Path

from bs4 import BeautifulSoup
import pandas as pd
import pytest

from pages import build_docs_ml


def _render(tmp_path: Path, monkeypatch, frame: pd.DataFrame) -> dict[str, BeautifulSoup]:
    """Dựng bằng CSV thật và chỉ chuyển đầu vào/đầu ra vào thư mục tạm."""
    data = tmp_path / "ml"
    data.mkdir()
    if not frame.empty:
        for mode in ("de", "loto"):
            frame.to_csv(data / f"predict_next_{mode}_ml_top10.csv", index=False)
    monkeypatch.setattr(build_docs_ml, "ML_DIR", data)
    monkeypatch.setattr(build_docs_ml, "DOCS_DIR", tmp_path / "docs")
    build_docs_ml.build()
    return {
        filename: BeautifulSoup((tmp_path / "docs" / filename).read_text(), "html.parser")
        for filename in ("ml_top10_de.html", "ml_top10_loto.html", "index.html")
    }


@pytest.fixture
def forecast() -> pd.DataFrame:
    return pd.DataFrame({
        "predict_for_date": ["2026-10-26"] * 3,
        "number": ["07", "00", "83"],
        "prob_percent": [1.23456, 0.78912, 0.67891],
        "prob": [0.0123456, 0.0078912, 0.0067891],
        "raw_model_prob": [0.05, 0.04, 0.03],
        "model_trust": [0.0, 0.0, 0.0],
        "quality_pass": [False, False, False],
    })


@pytest.mark.parametrize("mode, label", [("de", "Đặc Biệt"), ("loto", "LOTO")])
def test_forecast_exposes_mode_switch_before_the_ranking(
    tmp_path: Path, monkeypatch, forecast: pd.DataFrame, mode: str, label: str,
) -> None:
    """Mất đường chuyển loại, sai mục đang xem hoặc hero che bảng đều bị chặn."""
    pages = _render(tmp_path, monkeypatch, forecast)
    page = pages[f"ml_top10_{mode}.html"]
    content = page.select_one(".app-ml-forecast")
    assert content is not None
    assert content.select_one("h1").get_text(strip=True) == f"Top 10 {label}"
    switch = content.select_one('nav[aria-label="Chọn loại dự báo"]')
    assert switch is not None
    assert [(a["href"], a.get_text(strip=True)) for a in switch.select("a")] == [
        ("ml_top10_de.html", "Đặc Biệt"), ("ml_top10_loto.html", "LOTO"),
    ]
    assert switch.select_one('[aria-current="page"]')["href"] == f"ml_top10_{mode}.html"
    assert content.select_one(".app-lab-hero, .app-lab-orbit, .app-lab-stat") is None
    ranking = content.select_one("#app-lab-ranking")
    assert ranking is not None
    assert ranking.find_previous("nav") is switch
    region = ranking.select_one('.ui-table-wrap[role="region"][tabindex="0"][aria-label]')
    assert region is not None
    assert region.select_one("table") is not None
    guide = content.select_one("details#app-lab-guide")
    assert guide is not None and not guide.has_attr("open")
    assert ranking.find_next("details") is guide
    assert page.select_one("#app-ml-forecast-style") is not None
    assert pages["index.html"].select_one("#app-ml-forecast-style, .app-ml-forecast") is None
    assert len(pages["index.html"].select(".panel table")) == 2


@pytest.mark.parametrize("mode", ["de", "loto"])
def test_forecast_keeps_published_order_precision_and_evidence(
    tmp_path: Path, monkeypatch, forecast: pd.DataFrame, mode: str,
) -> None:
    """Tri, bỏ số 0 đầu, làm tròn thêm hoặc gắn nhầm căn cứ hàng đều bị chặn."""
    page = _render(tmp_path, monkeypatch, forecast)[f"ml_top10_{mode}.html"]
    rows = page.select("#app-lab-ranking table tbody tr")
    assert [[cell.get_text(strip=True) for cell in row.select("td")] for row in rows] == [
        ["1", "07", "1.235%", "0.012346"],
        ["2", "00", "0.789%", "0.007891"],
        ["3", "83", "0.679%", "0.006789"],
    ]
    assert [row["data-evidence-row"] for row in rows] == [
        f"ml-{mode}-07", f"ml-{mode}-00", f"ml-{mode}-83",
    ]
    assert all(row["data-evidence-cols"] == "2,3" for row in rows)
    entries = {}
    for block in page.select("[data-app-evidence-values]"):
        entries.update(json.loads(block.get_text()))
    for row in rows:
        assert entries[row["data-evidence-row"]]["sources"]
    trust = page.select_one("[data-ml-trust]")
    assert page.select_one(entries[trust["data-evidence"]]["match"]) is not None
    assert page.select_one(".app-lab-forecast-date").get_text(strip=True) == "2026-10-26"
    assert trust.get_text(strip=True) == "0,0%"
    assert page.select_one('[data-ml-trust-state="zero"]') is not None
    assert "xác suất nền" in page.select_one(".app-lab-trust-note").get_text(" ", strip=True)


def test_missing_forecast_keeps_switch_without_inventing_ranks(tmp_path: Path, monkeypatch) -> None:
    """Thiếu CSV phải hiện chờ dữ liệu, không sinh Top 10 hay coi mức tin là 0."""
    pages = _render(tmp_path, monkeypatch, pd.DataFrame())
    for mode in ("de", "loto"):
        page = pages[f"ml_top10_{mode}.html"]
        assert len(page.select('.app-ml-forecast nav[aria-label="Chọn loại dự báo"] a')) == 2
        assert page.select_one("#app-lab-ranking table") is None
        empty = page.select_one("#app-lab-ranking .ui-table-empty")
        assert empty is not None
        assert "Chưa có bản dự báo" in empty.get_text()
        assert page.select_one(".app-lab-forecast-date").get_text(strip=True) == "—"
        assert page.select_one("[data-ml-trust]").get_text(strip=True) == "—"
        assert page.select_one('[data-ml-trust-state="missing"]') is not None
        assert "Chưa có" in page.select_one(".app-lab-trust-note").get_text()
