from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from number_reference import (
    all_bo,
    bo,
    bo_family_id,
    bo_seed_catalog,
    bong_duong,
    cap_bong_duong,
    cap_lon,
    kep_bang,
    kep_lech,
    normalize_two_digit,
    pair_key,
    pair_relation_tags,
    reverse,
    sat_kep,
    sat_kep_vong,
    unique_bo_catalog,
    validate_ontology,
)


def test_bong_duong_and_reverse_are_involutions() -> None:
    for n in range(100):
        s = f"{n:02d}"
        assert bong_duong(bong_duong(s)) == s
        assert reverse(reverse(s)) == s


def test_bong_duong_examples() -> None:
    assert bong_duong("00") == "55"
    assert bong_duong("16") == "61"
    assert bong_duong("27") == "72"
    assert bong_duong("49") == "94"
    assert cap_bong_duong("16") == frozenset({"16", "61"})


def test_bo_seed_labels_collapse_to_15_unique_families() -> None:
    validate_ontology()
    seeds = bo_seed_catalog()
    unique = unique_bo_catalog()
    assert len(seeds) == 100
    assert len(unique) == 15
    assert len(all_bo()) == 15
    assert sorted(row["family_size"] for row in unique).count(4) == 5
    assert sorted(row["family_size"] for row in unique).count(8) == 10
    members = [m for row in unique for m in row["members"]]
    assert len(members) == 100
    assert set(members) == {f"{n:02d}" for n in range(100)}


def test_bo_family_is_stable_across_members() -> None:
    family = bo("01")
    assert family == frozenset({"01", "06", "10", "15", "51", "56", "60", "65"})
    family_id = bo_family_id("01")
    assert all(bo_family_id(member) == family_id for member in family)


def test_pair_semantics_are_not_conflated() -> None:
    assert cap_lon("13") == frozenset({"13", "31"})
    assert pair_key("31", "13") == "13-31"
    assert "reverse" in pair_relation_tags("13", "31")
    assert "same_bo_family" in pair_relation_tags("13", "31")
    assert "reverse" not in pair_relation_tags("13", "55")


def test_kep_definitions() -> None:
    assert set(kep_bang()) == {f"{d}{d}" for d in range(10)}
    assert set(kep_lech()) == {
        "05",
        "50",
        "16",
        "61",
        "27",
        "72",
        "38",
        "83",
        "49",
        "94",
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
