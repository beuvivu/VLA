from __future__ import annotations

from datetime import date

from sources import (
    EXPECTED_COUNTS,
    PRIZE_ORDER,
    default_sources,
    extract_partial_prize_map,
    source_consensus_partial,
)


COMPLETE = """
<html><body>
<h2>XSMB 30/08/2026</h2>
<div>ĐB 83772</div>
<div>G1 68785</div>
<div>G2 50518 27452</div>
<div>G3 57053 92810 56241 65128 33811 42264</div>
<div>G4 4753 1152 6777 3507</div>
<div>G5 9460 2913 3232 2999 3670 5129</div>
<div>G6 939 751 594</div>
<div>G7 66 21 34 78</div>
</body></html>
"""


def test_source_policy_exact_priority_and_no_removed_provider() -> None:
    names = [s.name for s in default_sources()]
    assert names == [
        "xoso.com.vn",
        "mketqua.net",
        "www.minhngoc.net.vn",
        "xosominhngoc.com",
        "xosodaiphat.com",
        "hainhay.net",
    ]


def test_generic_parser_accepts_complete_exact_width_block() -> None:
    p = extract_partial_prize_map(COMPLETE)
    assert p["special"] == ["83772"]
    assert p["prize3"] == ["57053", "92810", "56241", "65128", "33811", "42264"]
    assert p["prize7"] == ["66", "21", "34", "78"]
    assert sum(len(p[k]) for k in PRIZE_ORDER) == sum(EXPECTED_COUNTS.values())


def test_generic_parser_never_zero_fills_short_live_placeholders() -> None:
    p = extract_partial_prize_map("<div>ĐB 8377</div><div>G1 —</div><div>G6 93 751</div><div>G7 6 21</div>")
    assert p["prize7"] == ["21"]
    assert p["prize6"] == ["751"]
    assert p["special"] == []


def test_slot_consensus_uses_priority_only_for_provisional_values() -> None:
    a = {k: [] for k in PRIZE_ORDER}
    b = {k: [] for k in PRIZE_ORDER}
    c = {k: [] for k in PRIZE_ORDER}
    a["prize7"] = ["66", "21"]
    b["prize7"] = ["66", "34"]
    c["prize7"] = ["66", "34"]
    merged, meta = source_consensus_partial([("a", a), ("b", b), ("c", c)], min_agreement=2)
    assert merged["prize7"] == ["66", "34"]
    assert meta["slot_meta"]["prize7[0]"]["verified"] is True
    assert meta["slot_meta"]["prize7[1]"]["verified"] is True
    assert "prize7[1]" in meta["conflicts"]


def test_parser_accepts_xosodaiphat_dotted_g_labels() -> None:
    html = """
    <table>
      <tr><td>G.ĐB</td><td>07523</td></tr>
      <tr><td>G.1</td><td>03402</td></tr>
      <tr><td>G.2</td><td>71264 70743</td></tr>
      <tr><td>G.3</td><td>23922 98532 50759 33811 64437 25606</td></tr>
      <tr><td>G.4</td><td>4096 2934 0699 0661</td></tr>
      <tr><td>G.5</td><td>5404 1432 4959 9897 3794 2391</td></tr>
      <tr><td>G.6</td><td>468 074 622</td></tr>
      <tr><td>G.7</td><td>88 34 47 00</td></tr>
    </table>
    """
    parsed = extract_partial_prize_map(html)
    assert {k: len(v) for k, v in parsed.items()} == EXPECTED_COUNTS
    assert parsed["special"] == ["07523"]
    assert parsed["prize7"] == ["88", "34", "47", "00"]


def test_minhnngoc_mirrors_count_as_one_independent_group() -> None:
    from sources import source_independence_key

    assert source_independence_key("www.minhngoc.net.vn") == "minhngoc"
    assert source_independence_key("xosominhngoc.com") == "minhngoc"
    assert source_independence_key("xoso.com.vn") != "minhngoc"


def test_slot_consensus_rejects_equal_two_group_tie_as_unverified() -> None:
    maps = []
    for source, value in [
        ("xoso.com.vn", "11"),
        ("xosodaiphat.com", "11"),
        ("mketqua.net", "22"),
        ("hainhay.net", "22"),
    ]:
        p = {k: [] for k in PRIZE_ORDER}
        p["prize7"] = [value]
        maps.append((source, p))

    merged, meta = source_consensus_partial(maps, min_agreement=2)
    slot = meta["slot_meta"]["prize7[0]"]
    assert merged["prize7"][0] == "11"  # priority display only
    assert slot["verified"] is False
    assert slot["ambiguous_tie"] is True
    assert meta["verified_slots"] == 0


def test_slot_consensus_accepts_unique_independent_winner_over_mirrors() -> None:
    maps = []
    for source, value in [
        ("xoso.com.vn", "11"),
        ("xosodaiphat.com", "11"),
        ("www.minhngoc.net.vn", "22"),
        ("xosominhngoc.com", "22"),
    ]:
        p = {k: [] for k in PRIZE_ORDER}
        p["prize7"] = [value]
        maps.append((source, p))

    merged, meta = source_consensus_partial(maps, min_agreement=2)
    slot = meta["slot_meta"]["prize7[0]"]
    assert merged["prize7"][0] == "11"
    assert slot["verified"] is True
    assert slot["ambiguous_tie"] is False
    assert slot["support_groups"] == ["xoso", "xosodaiphat"]
