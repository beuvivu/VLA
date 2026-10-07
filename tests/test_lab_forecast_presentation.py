"""Tóm tắt ML phải phân biệt xác suất dự báo và mức tin thành phần."""

from pathlib import Path
import json

import pandas as pd
import pytest
from bs4 import BeautifulSoup

import build_docs_ml


@pytest.mark.parametrize("trust, expected", [(0.0, "0,0%"), (0.25, "25,0%"), (None, "—"),
                                           ([0.1, 0.2], "10,0%–20,0%")])
def test_forecast_summary_reads_trust_without_substituting_probability(
    tmp_path: Path, monkeypatch, trust, expected: str,
) -> None:
    """Lấy nhầm prob=24% hoặc mặc định thiếu thành 0 đều phải bị phát hiện."""
    data = tmp_path / "ml"
    data.mkdir()
    count = len(trust) if isinstance(trust, list) else 1
    values = {"predict_for_date": ["2026-10-08"] * count, "number": ["03", "07"][:count],
              "prob": [0.24] * count, "prob_percent": [24.0] * count}
    if trust is not None:
        values["model_trust"] = trust if isinstance(trust, list) else [trust]
    for mode in ("loto", "de"):
        pd.DataFrame(values).to_csv(data / f"predict_next_{mode}_ml_top10.csv", index=False)
    monkeypatch.setattr(build_docs_ml, "ML_DIR", data)
    monkeypatch.setattr(build_docs_ml, "DOCS_DIR", tmp_path / "docs")
    build_docs_ml.build()
    for mode in ("loto", "de"):
        page = BeautifulSoup((tmp_path / "docs" / f"ml_top10_{mode}.html").read_text(), "html.parser")
        metric = page.select_one("[data-ml-trust]")
        assert metric is not None, "Thiếu mức tin thành phần trong tóm tắt dự báo"
        assert metric.get_text(strip=True) == expected
        if isinstance(trust, list):
            ident = metric.get("data-evidence")
            assert ident, "Khoảng hai số phải mở được bằng chứng riêng"
            entries = {}
            for block in page.select("[data-app-evidence-values]"):
                entries.update(json.loads(block.get_text()))
            assert ident in entries
            assert entries[ident]["sources"]
        note = page.select_one(".app-lab-trust-note").get_text(" ", strip=True)
        if trust == 0:
            assert "xác suất nền" in note
        if trust is None:
            assert "Chưa có" in note
        assert page.select_one(".app-lab-forecast-date").get_text(strip=True) == "2026-10-08"
        assert "24.000%" in page.select_one("#app-lab-ranking table").get_text()
