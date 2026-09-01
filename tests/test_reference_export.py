from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from export_number_reference import export_reference


def test_reference_export_has_100_seed_labels_and_15_unique_families(tmp_path: Path) -> None:
    export_reference(tmp_path)
    numbers = pd.read_csv(tmp_path / "number_ontology_00_99.csv", dtype=str)
    seeds = pd.read_csv(tmp_path / "bo_seed_catalog_00_99.csv", dtype=str)
    families = pd.read_csv(tmp_path / "bo_unique_families.csv", dtype=str)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert len(numbers) == 100
    assert len(seeds) == 100
    assert len(families) == 15
    assert numbers["number_str"].tolist()[0] == "00"
    assert numbers["number_str"].tolist()[-1] == "99"
    assert seeds["seed_label"].tolist()[0] == "00"
    assert manifest["bo_seed_label_count"] == 100
    assert manifest["bo_unique_family_count"] == 15
    assert manifest["bong_am"]["status"] == "non_canonical"
