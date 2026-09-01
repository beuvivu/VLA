from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_markdown_dashboard_builder_runs_on_repository_data() -> None:
    subprocess.run([sys.executable, "src/build_markdown_dashboard.py"], check=True)

    dashboard = Path("DASHBOARD.md")
    assert dashboard.is_file()
    text = dashboard.read_text(encoding="utf-8")

    required = [
        "# ✨ VLA · XSMB ANALYTICAL COCKPIT",
        "## 🎟️ Daily & Next Draw",
        "## 🔮 Probability Arena",
        "## 🔥 Frequency Heatmaps 00–99",
        "## ⏳ Gap & Rhythm",
        "## 🤖 AI/ML & Number Dynamics",
        "## 🧬 Markov · Transition · Dependency",
        "## 🧩 Head · Tail · Total · Pairs",
        "## 📆 Special Boards & Conditional Next-day",
        "## 🧪 Significance & Research Firewall",
        "Ma trận probability 00–99",
        "Higher-order dynamics",
        "100×100 transition lift",
        "Co-occurrence Phi",
        "Strategy Lab",
        "FDR",
        "35644",
        "30972",
        "77",
        "83",
    ]
    for marker in required:
        assert marker in text, marker

    # Dense GitHub-native presentation: several 10x10 number matrices and
    # numeric/statistical tables should materially outweigh a simple file index.
    assert text.count("Đầu\\Đuôi") >= 12
    assert text.count("▰") >= 20
    assert text.count("🟪") >= 10
    assert "Complete Data Catalog" not in text
    assert len(text) > 70_000
