from __future__ import annotations

from pathlib import Path


def test_pipeline_validates_canonical_history_before_any_analytics() -> None:
    text = (Path(__file__).resolve().parents[1] / "src" / "pipeline.py").read_text(encoding="utf-8")
    validate = text.index('"src/validate_data.py"')
    first_stats = text.index('"src/analyze.py"')
    research = text.index('"src/research_diagnostics.py"')
    path = text.index('"src/run_path_ui.py"')
    ml = text.index('"src/ml_train.py"')
    assert validate < first_stats < research < path < ml


def test_pipeline_treats_canonical_validation_as_hard_failure() -> None:
    text = (Path(__file__).resolve().parents[1] / "src" / "pipeline.py").read_text(encoding="utf-8")
    start = text.index('"src/validate_data.py"')
    block = text[start : start + 260]
    assert "allow_fail=False" in block


def test_pipeline_treats_simulation_refresh_as_hard_failure() -> None:
    text = (Path(__file__).resolve().parents[1] / "src" / "pipeline.py").read_text(
        encoding="utf-8"
    )
    marker = '_py("src/build_fun_prediction.py")'
    start = text.index(marker)
    assert "allow_fail=False" in text[start : start + 180]
