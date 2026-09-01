from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_markdown_dashboard_builder_runs_on_repository_data() -> None:
    subprocess.run([sys.executable, "src/build_markdown_dashboard.py"], check=True)

    dashboard = Path("DASHBOARD.md")
    assert dashboard.is_file()
    text = dashboard.read_text(encoding="utf-8")

    assert "# 🎯 VLA · XSMB Analytics Dashboard" in text
    assert "## 🎟️ Daily Results" in text
    assert "## 🔮 Forecast & Prediction" in text
    assert "## 📊 Statistical Data Center" in text
    assert "## 🗃️ Complete Data Catalog" in text
    assert "data/advanced" in text
    assert "data/research" in text
    assert "data/statistical_signal" in text
    assert "data/xsmb.csv" in text
    assert len(text) > 20_000
