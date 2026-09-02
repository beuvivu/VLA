from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from export_number_reference import export_reference


def test_reference_export_has_complete_number_pair_and_bo_catalogs(tmp_path: Path) -> None:
    export_reference(tmp_path)
    numbers = pd.read_csv(tmp_path / "number_ontology_00_99.csv", dtype=str)
    seeds = pd.read_csv(tmp_path / "bo_seed_catalog_00_99.csv", dtype=str)
    families = pd.read_csv(tmp_path / "bo_unique_families.csv", dtype=str)
    pairs = pd.read_csv(tmp_path / "cap_loto_50.csv", dtype=str)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert len(numbers) == 100
    assert len(seeds) == 100
    assert len(families) == 15
    assert len(pairs) == 50
    assert numbers["number_str"].tolist()[0] == "00"
    assert numbers["number_str"].tolist()[-1] == "99"
    assert seeds["seed_label"].tolist()[0] == "00"

    assert set(pairs.loc[pairs["pair_kind"] == "kep_bong", "pair_id"]) == {
        "00-55", "11-66", "22-77", "33-88", "44-99"
    }
    assert int((pairs["pair_kind"] == "kep_bong").sum()) == 5
    assert int((pairs["pair_kind"] == "reverse").sum()) == 45

    assert manifest["bo_seed_label_count"] == 100
    assert manifest["bo_unique_family_count"] == 15
    assert manifest["cap_loto_50_count"] == 50
    assert manifest["cap_loto_50_kind_distribution"] == {
        "reverse": 45,
        "kep_bong": 5,
    }
    assert manifest["bong_am"]["status"] == "documented_domain_convention"
    assert manifest["bong_am"]["predictive_status"] == "must_be_empirically_validated"
