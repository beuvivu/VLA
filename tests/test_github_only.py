from __future__ import annotations

import sys
from pathlib import Path

import sync

ROOT = Path(__file__).resolve().parents[1]


def test_no_server_deployment_bundle() -> None:
    forbidden = [
        "requirements-hosting.txt",
        "passenger_wsgi.py",
        "deploy",
        "hosting",
        "src/webapp.py",
        "src/hosting_health.py",
        "src/scheduler.py",
    ]
    assert all(not (ROOT / rel).exists() for rel in forbidden)


def test_sync_main_loads_committed_history_before_fetch(monkeypatch) -> None:
    calls: list[str] = []

    class FakeLottery:
        def load(self) -> None:
            calls.append("load")

        def get_last_date(self):
            return "2026-01-01"

    def fake_sync(*, lottery, **kwargs):
        assert isinstance(lottery, FakeLottery)
        calls.append("sync")
        return []

    monkeypatch.setattr(sync, "Lottery", FakeLottery)
    monkeypatch.setattr(sync, "ensure_up_to_date", fake_sync)
    monkeypatch.setattr(sys, "argv", ["sync.py"])

    sync.main()
    assert calls == ["load", "sync"]


def test_prediction_history_is_compact_csv() -> None:
    assert (ROOT / "data/history/pred_loto.csv").is_file()
    assert (ROOT / "data/history/pred_de.csv").is_file()
    assert not list((ROOT / "data/history").glob("pred_loto_*.csv"))
    assert not list((ROOT / "data/history").glob("pred_de_*.csv"))
    assert not list((ROOT / "data/history").glob("*.parquet"))


def test_model_quality_page_is_self_contained_for_docs_pages() -> None:
    page = (ROOT / "docs/model-quality.html").read_text(encoding="utf-8")
    assert "../data/" not in page
    assert "LogLoss" in page
    assert "Brier" in page
