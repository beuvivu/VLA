from __future__ import annotations

from pathlib import Path


def test_pipeline_runs_reference_excel_and_pair_integrity_in_order() -> None:
    text = (Path(__file__).resolve().parents[1] / "src" / "pipeline.py").read_text(
        encoding="utf-8"
    )
    validate = text.index('"src/validate_data.py"')
    ontology = text.index('"src/export_number_reference.py"')
    excel = text.index('"src/validate_excel_integrity.py"')
    pair_stats = text.index('"src/pair_stats.py"')
    descriptive = text.index('"src/descriptive_extensions.py"')
    normalize = text.index('"src/normalize_pair_artifacts.py"')
    assert validate < ontology < excel < pair_stats < descriptive < normalize
