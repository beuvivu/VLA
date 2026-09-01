from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_markdown_dashboard_builder_runs_on_repository_data() -> None:
    subprocess.run([sys.executable, "src/build_markdown_dashboard_v3.py"], check=True)

    dashboard = Path("DASHBOARD.md")
    assert dashboard.is_file()
    text = dashboard.read_text(encoding="utf-8")

    required = [
        "# ✨ VLA · XSMB ANALYTICAL COCKPIT",
        "Balanced UI · explicit legends",
        "## 🎟️ Daily & Next Draw",
        "## 🔮 Probability Arena",
        "## 🔥 Frequency Heatmaps 00–99",
        "## ⏳ Gap & Rhythm",
        "## 🤖 AI/ML & Dynamics",
        "## 🧬 Markov · Transition · Dependency",
        "## 🧩 Structure & Pairs",
        "## 📆 Special Boards & Conditional",
        "## 🧪 Significance & Research",
        "Màu | Khoảng giá trị | Ý nghĩa",
        "Đối tượng | Giá trị | So sánh / căn cứ | Ý nghĩa | Visual",
        "Lift vs baseline",
        "calendar 7 cột",
        "Co-occurrence Phi",
        "Strategy Lab",
        "q(FDR)",
        "Audit & Deep Links",
    ]
    for marker in required:
        assert marker in text, marker

    # Heatmaps must always explain their color scale and standard analytical
    # tables must expose a dedicated interpretation column.
    assert text.count("Đầu\\Đuôi") >= 12
    assert text.count("Màu | Khoảng giá trị | Ý nghĩa") >= 12
    assert text.count("| Ý nghĩa | Visual |") >= 20
    assert text.count("▰") >= 20
    assert text.count("🟪") >= 10

    # Prevent the previous bottom-page layout failure: the 31-column monthly
    # board is replaced by calendar-shaped 7-column tables and lag panels render.
    assert "| month_key | 01 | 02 | 03 | 04 | 05 |" not in text
    assert "Multi-lag dependency Loto\n_Chưa có dữ liệu._" not in text
    assert "Multi-lag dependency ĐB\n_Chưa có dữ liệu._" not in text

    assert "Complete Data Catalog" not in text
    assert len(text) > 70_000
