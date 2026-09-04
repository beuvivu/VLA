from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from number_reference import (
    all_bo,
    all_cap_loto_50,
    bo,
    bo_family_id,
    bo_seed_catalog,
    bong_am,
    bong_duong,
    cap_bong_duong,
    cap_lon,
    cap_loto_50_id,
    cap_loto_50_kind,
    cap_loto_50_partner,
    dan_cham,
    dan_dau,
    dan_duoi,
    dan_tong_mod10,
    digit_sum,
    digit_sum_mod10,
    head,
    kep_am,
    kep_bang,
    kep_bong_pairs,
    kep_lech,
    normalize_two_digit,
    pair_key,
    pair_relation_tags,
    reverse,
    sat_kep,
    sat_kep_vong,
    tail,
    unique_bo_catalog,
    validate_ontology,
)


def test_digit_domain_rules_cover_edge_numbers() -> None:
    assert head("00") == 0
    assert tail("00") == 0
    assert digit_sum("00") == 0
    assert digit_sum_mod10("00") == 0
    assert reverse("00") == "00"
    assert head("99") == 9
    assert tail("99") == 9
    assert digit_sum("99") == 18
    assert digit_sum_mod10("99") == 8
    assert reverse("99") == "99"
    assert len(dan_dau(0)) == 10
    assert len(dan_duoi(9)) == 10
    assert len(dan_cham(0)) == 19
    assert len(dan_tong_mod10(8)) == 10


def test_bong_relations_and_reverse_are_involutions() -> None:
    for n in range(100):
        s = f"{n:02d}"
        assert bong_duong(bong_duong(s)) == s
        assert bong_am(bong_am(s)) == s
        assert reverse(reverse(s)) == s


def test_bong_duong_examples() -> None:
    assert bong_duong("00") == "55"
    assert bong_duong("16") == "61"
    assert bong_duong("27") == "72"
    assert bong_duong("49") == "94"
    assert cap_bong_duong("16") == frozenset({"16", "61"})


def test_bong_am_examples() -> None:
    assert bong_am("07") == "70"
    assert bong_am("14") == "41"
    assert bong_am("29") == "92"
    assert bong_am("36") == "63"
    assert bong_am("58") == "85"


def test_bo_seed_labels_collapse_to_15_unique_families() -> None:
    validate_ontology()
    seeds = bo_seed_catalog()
    unique = unique_bo_catalog()
    assert len(seeds) == 100
    assert len(unique) == 15
    assert len(all_bo()) == 15
    assert sorted(row["family_size"] for row in unique).count(4) == 5
    assert sorted(row["family_size"] for row in unique).count(8) == 10
    assert sum(row["family_kind"] == "bo_kep" for row in unique) == 5
    assert sum(row["family_kind"] == "bo_thuong" for row in unique) == 10
    assert {row["canonical_family_id"] for row in unique} == {
        "00", "01", "02", "03", "04", "11", "12", "13", "14", "22",
        "23", "24", "33", "34", "44",
    }
    members = [m for row in unique for m in row["members"]]
    assert len(members) == 100
    assert set(members) == {f"{n:02d}" for n in range(100)}


def test_bo_family_is_stable_across_members() -> None:
    family = bo("01")
    assert family == frozenset({"01", "06", "10", "15", "51", "56", "60", "65"})
    family_id = bo_family_id("01")
    assert all(bo_family_id(member) == family_id for member in family)
    assert bo("00") == frozenset({"00", "05", "50", "55"})


def test_common_50_pair_partition() -> None:
    pairs = all_cap_loto_50()
    assert len(pairs) == 50
    assert all(len(pair) == 2 for pair in pairs)
    flat = [n for pair in pairs for n in pair]
    assert len(flat) == 100
    assert len(set(flat)) == 100

    assert cap_loto_50_id("00") == "00-55"
    assert cap_loto_50_id("55") == "00-55"
    assert cap_loto_50_id("11") == "11-66"
    assert cap_loto_50_id("22") == "22-77"
    assert cap_loto_50_id("33") == "33-88"
    assert cap_loto_50_id("44") == "44-99"
    assert cap_loto_50_kind("00") == "kep_bong"
    assert cap_loto_50_partner("00") == "55"
    assert cap_loto_50_partner("55") == "00"

    assert cap_loto_50_id("13") == "13-31"
    assert cap_loto_50_kind("13") == "reverse"
    assert cap_loto_50_partner("13") == "31"
    assert cap_loto_50_partner("31") == "13"

    assert {"-".join(pair) for pair in kep_bong_pairs()} == {
        "00-55", "11-66", "22-77", "33-88", "44-99"
    }


def test_pair_semantics_are_not_conflated() -> None:
    assert cap_lon("13") == frozenset({"13", "31"})
    assert pair_key("31", "13") == "13-31"
    assert "reverse" in pair_relation_tags("13", "31")
    assert "cap_loto_50" in pair_relation_tags("13", "31")
    assert "same_bo_family" in pair_relation_tags("13", "31")
    assert "reverse" not in pair_relation_tags("00", "55")
    assert "kep_bong" in pair_relation_tags("00", "55")
    assert "bong_duong" in pair_relation_tags("00", "55")


def test_kep_definitions() -> None:
    assert set(kep_bang()) == {f"{d}{d}" for d in range(10)}
    assert set(kep_lech()) == {
        "05", "50", "16", "61", "27", "72", "38", "83", "49", "94"
    }
    assert set(kep_am()) == {
        "07", "70", "14", "41", "29", "92", "36", "63", "58", "85"
    }
    assert "12" in sat_kep()
    assert "21" in sat_kep()
    assert "09" not in sat_kep()
    assert "90" not in sat_kep()
    assert "09" in sat_kep_vong()
    assert "90" in sat_kep_vong()


def test_normalization_rejects_dirty_tokens_but_accepts_numpy_integers() -> None:
    assert normalize_two_digit(np.int64(7)) == "07"
    assert normalize_two_digit("07") == "07"
    with pytest.raises(ValueError):
        normalize_two_digit("0a7")
    with pytest.raises(ValueError):
        normalize_two_digit(True)
    with pytest.raises(ValueError):
        normalize_two_digit(100)
