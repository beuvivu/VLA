from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dtos import Result
from lottery import Lottery, RepoPaths


def _result(d: date, *, special: int) -> Result:
    values = {
        "date": d,
        "special": special,
        "prize1": 12345,
        "prize2_1": 11111,
        "prize2_2": 22222,
        "prize3_1": 30001,
        "prize3_2": 30002,
        "prize3_3": 30003,
        "prize3_4": 30004,
        "prize3_5": 30005,
        "prize3_6": 30006,
        "prize4_1": 4001,
        "prize4_2": 4002,
        "prize4_3": 4003,
        "prize4_4": 4004,
        "prize5_1": 5001,
        "prize5_2": 5002,
        "prize5_3": 5003,
        "prize5_4": 5004,
        "prize5_5": 5005,
        "prize5_6": 5006,
        "prize6_1": 601,
        "prize6_2": 602,
        "prize6_3": 603,
        "prize7_1": 71,
        "prize7_2": 72,
        "prize7_3": 73,
        "prize7_4": 74,
    }
    return Result(**values)


@dataclass
class FakeSource:
    name: str
    result: Result | None

    def fetch(self, selected_date: date, http: object) -> Result | None:
        return self.result


def _lottery(tmp_path: Path, sources: list[FakeSource]) -> Lottery:
    paths = RepoPaths(root=tmp_path, data_dir=tmp_path / "data", images_dir=tmp_path / "images")
    return Lottery(paths=paths, http=object(), sources=sources)  # type: ignore[arg-type]


def test_consensus_accepts_two_matching_sources(tmp_path: Path) -> None:
    d = date(2026, 8, 30)
    a = _result(d, special=12345)
    lot = _lottery(tmp_path, [FakeSource("a", a), FakeSource("b", a), FakeSource("c", _result(d, special=99999))])

    assert lot.fetch(d, min_agreement=2) is True
    assert lot.has_date(d)
    audit = lot._fetch_audit[d.isoformat()]  # regression: audit is part of persisted provenance contract
    assert audit["agreement"] == 2
    assert audit["accepted"] is True
    assert audit["ambiguous_tie"] is False


def test_consensus_rejects_conflicting_single_sources_without_mutating_canonical(tmp_path: Path) -> None:
    d = date(2026, 8, 30)
    lot = _lottery(
        tmp_path,
        [FakeSource("a", _result(d, special=12345)), FakeSource("b", _result(d, special=54321))],
    )

    assert lot.fetch(d, min_agreement=2) is False
    assert not lot.has_date(d)
    audit = lot._fetch_audit[d.isoformat()]
    assert audit["accepted"] is False
    assert audit["distinct_results"] == 2
    assert audit["ambiguous_tie"] is False


def test_two_minhnngoc_mirrors_alone_do_not_satisfy_two_provider_consensus(tmp_path: Path) -> None:
    d = date(2026, 8, 30)
    a = _result(d, special=12345)
    lot = _lottery(
        tmp_path,
        [
            FakeSource("www.minhngoc.net.vn", a),
            FakeSource("xosominhngoc.com", a),
        ],
    )

    assert lot.fetch(d, min_agreement=2) is False
    assert not lot.has_date(d)
    audit = lot._fetch_audit[d.isoformat()]
    assert audit["agreement"] == 1
    assert audit["source_agreement"] == 2


def test_consensus_rejects_equal_independent_group_tie(tmp_path: Path) -> None:
    d = date(2026, 9, 1)
    a = _result(d, special=12345)
    b = _result(d, special=54321)
    lot = _lottery(
        tmp_path,
        [
            FakeSource("xoso.com.vn", a),
            FakeSource("xosodaiphat.com", a),
            FakeSource("mketqua.net", b),
            FakeSource("hainhay.net", b),
        ],
    )

    assert lot.fetch(d, min_agreement=2) is False
    assert not lot.has_date(d)
    audit = lot._fetch_audit[d.isoformat()]
    assert audit["accepted"] is False
    assert audit["agreement"] == 2
    assert audit["runner_up_agreement"] == 2
    assert audit["ambiguous_tie"] is True


def test_consensus_accepts_unique_two_group_winner_over_mirror_pair(tmp_path: Path) -> None:
    d = date(2026, 9, 1)
    winner = _result(d, special=12345)
    mirror_result = _result(d, special=54321)
    lot = _lottery(
        tmp_path,
        [
            FakeSource("xoso.com.vn", winner),
            FakeSource("xosodaiphat.com", winner),
            FakeSource("www.minhngoc.net.vn", mirror_result),
            FakeSource("xosominhngoc.com", mirror_result),
        ],
    )

    assert lot.fetch(d, min_agreement=2) is True
    assert lot.has_date(d)
    audit = lot._fetch_audit[d.isoformat()]
    assert audit["accepted"] is True
    assert audit["agreement"] == 2
    assert audit["runner_up_agreement"] == 1
    assert audit["ambiguous_tie"] is False
