from __future__ import annotations

import json
from pathlib import Path


def test_domain_glossary_has_required_relations_and_research_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads(
        (root / "config" / "number_domain_glossary.json").read_text(encoding="utf-8")
    )
    assert payload["schema_version"] == 1
    assert payload["policy"]["ontology_is_not_prediction"] is True
    assert payload["policy"]["production_weight_requires_validation"] is True

    terms = payload["terms"]
    required = {
        "cap_loto_50",
        "kep_bong",
        "lon_reverse",
        "bong_duong",
        "bong_am",
        "bo_he",
        "kep_bang",
        "kep_lech_duong",
        "kep_am",
        "cham",
        "tong_mod10",
        "gan",
        "khan",
        "nong_hot",
        "cam_dau",
        "cam_duoi",
        "hai_nhay",
        "roi",
        "bet",
        "tong_thieu",
        "cham_thieu",
        "trung_cau",
        "trung_bo",
        "nuoi_khung",
        "bac_nho",
        "sat_kep",
    }
    assert required.issubset(terms)
    assert terms["kep_bong"]["members"] == [
        "00-55",
        "11-66",
        "22-77",
        "33-88",
        "44-99",
    ]
    assert terms["bong_am"]["digit_pairs"] == [
        "0-7",
        "1-4",
        "2-9",
        "3-6",
        "5-8",
    ]
    assert terms["bo_he"]["family_ids"] == [
        "00",
        "01",
        "02",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "22",
        "23",
        "24",
        "33",
        "34",
        "44",
    ]
    for name in (
        "gan",
        "khan",
        "nong_hot",
        "cam_dau",
        "cam_duoi",
        "roi",
        "bet",
        "tong_thieu",
        "cham_thieu",
        "trung_cau",
        "trung_bo",
        "bac_nho",
    ):
        assert terms[name]["status"].startswith("research")
