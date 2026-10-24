from __future__ import annotations


from ingest.sources import (
    EXPECTED_COUNTS,
    PRIZE_ORDER,
    default_sources,
    extract_partial_prize_map,
    fallback_sources,
    primary_sources,
    source_consensus_partial,
)


COMPLETE = """
<html><body>
<h2>XSMB 30/08/2026</h2>
<div>Đặc Biệt 83772</div>
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
    """Thứ tự ưu tiên là chính sách, không phải chi tiết cài đặt.

    Từ 13-10-2026: một nguồn chính, hai nguồn dự phòng theo đúng thứ tự gọi. Đổi danh mục
    phải là thay đổi CÓ CHỦ Ý và nhìn thấy được trong diff.
    """
    assert [s.name for s in primary_sources()] == ["xoso.com.vn"]
    assert [s.name for s in fallback_sources()] == ["mketqua.net", "www.minhngoc.net.vn"]
    assert [s.name for s in default_sources()] == (
        [s.name for s in primary_sources()] + [s.name for s in fallback_sources()]
    )


def test_retired_sources_are_neither_called_nor_printable() -> None:
    """Nguồn đã nghỉ không còn trong danh mục gọi, nhưng tên vẫn bị cấm in ra."""
    from ingest.sources import RETIRED_SOURCE_NAMES, known_source_domains

    called = {s.name for s in default_sources()}
    assert called.isdisjoint(RETIRED_SOURCE_NAMES)
    assert {"xosothudo.com.vn", "xskt.vn", "xosodaiphat.com", "hainhay.net"} <= set(RETIRED_SOURCE_NAMES)
    assert set(RETIRED_SOURCE_NAMES) <= set(known_source_domains())


def test_generic_parser_accepts_complete_exact_width_block() -> None:
    p = extract_partial_prize_map(COMPLETE)
    assert p["special"] == ["83772"]
    assert p["prize3"] == ["57053", "92810", "56241", "65128", "33811", "42264"]
    assert p["prize7"] == ["66", "21", "34", "78"]
    assert sum(len(p[k]) for k in PRIZE_ORDER) == sum(EXPECTED_COUNTS.values())


def test_generic_parser_never_zero_fills_short_live_placeholders() -> None:
    p = extract_partial_prize_map("<div>Đặc Biệt 8377</div><div>G1 —</div><div>G6 93 751</div><div>G7 6 21</div>")
    assert p["prize7"] == ["21"]
    assert p["prize6"] == ["751"]
    assert p["special"] == []


def test_generic_parser_rejects_unicode_digits_before_consensus() -> None:
    p = extract_partial_prize_map("<div>Đặc Biệt １２３４５</div><div>G7 １２ 34</div>")
    assert p["special"] == []
    assert p["prize7"] == ["34"]

    mixed = extract_partial_prize_map("<div>Đặc Biệt １12345２</div><div>G7 １12２</div>")
    assert mixed["special"] == []
    assert mixed["prize7"] == []


def test_consensus_discards_malformed_tokens_and_invalid_thresholds() -> None:
    import pytest

    malicious = {k: [] for k in PRIZE_ORDER}
    malicious["prize7"] = ["</script><script>alert(1)</script>"]
    merged, meta = source_consensus_partial(
        [("a", malicious), ("b", malicious)], min_agreement=2
    )
    assert merged["prize7"] == []
    assert meta["received_slots"] == 0
    assert meta["verified_slots"] == 0
    for invalid in (0, True, 1.5):
        with pytest.raises(ValueError, match="min_agreement"):
            source_consensus_partial([], min_agreement=invalid)  # type: ignore[arg-type]


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
      <tr><td>G.Đặc Biệt</td><td>07523</td></tr>
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


def test_every_kept_source_is_its_own_independent_group() -> None:
    from ingest.sources import source_independence_key

    keys = [source_independence_key(s.name) for s in default_sources()]
    assert keys == ["xoso", "mketqua", "minhngoc"]


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


def test_two_disagreeing_fallbacks_leave_the_slot_unverified() -> None:
    """Nguồn chính hỏng, hai nguồn dự phòng nói khác nhau: với ngưỡng một nhóm, ô ấy là hoà
    giữa hai nhóm — hiện tạm giá trị của nguồn ưu tiên hơn, không bao giờ đánh dấu xác minh."""
    maps = []
    for source, value in [("mketqua.net", "11"), ("www.minhngoc.net.vn", "22")]:
        p = {k: [] for k in PRIZE_ORDER}
        p["prize7"] = [value]
        maps.append((source, p))

    merged, meta = source_consensus_partial(maps, min_agreement=1)
    slot = meta["slot_meta"]["prize7[0]"]
    assert merged["prize7"][0] == "11"
    assert slot["verified"] is False
    assert slot["ambiguous_tie"] is True
    assert meta["conflicts"] == ["prize7[0]"]


class _ManyCandidates:
    """Nguồn giả có nhiều đường dẫn ứng viên — cơ chế dùng chung của ``_TextPageSource``."""

    def __new__(cls):
        from ingest.sources import _TextPageSource

        class Source(_TextPageSource):
            name = "nhieu-ung-vien.example"

            def date_urls(self, selected_date):
                return tuple(f"https://nguon.example/ngay/{n}" for n in range(3))

            def live_urls(self, selected_date):
                return tuple(f"https://nguon.example/live/{n}" for n in range(3))

        return Source()


def test_a_source_tries_every_candidate_url_until_one_parses() -> None:
    """Nguồn có nhiều mẫu đường dẫn phải thử lần lượt, không dừng ở cái đầu.

    Chốt cứng một phỏng đoán sẽ hỏng ÂM THẦM: trang trả 404, bộ bóc nhận chuỗi rỗng, nguồn
    báo "không có gì" thay vì "sai địa chỉ".
    """
    from datetime import date

    ngay = date(2026, 9, 5)
    source = _ManyCandidates()
    urls = source.date_urls(ngay)
    assert len(urls) > 1

    hit_on = urls[-1]
    seen: list[str] = []

    class Http:
        def get(self, url, timeout=20):
            seen.append(url)
            class R:
                status_code = 200
                text = COMPLETE if url == hit_on else "<html>404</html>"
            return R()

    prize_map = source.fetch_partial(ngay, Http())
    assert seen == list(urls), "phải thử đủ mọi ứng viên trước khi bỏ cuộc"
    assert prize_map["special"] == ["83772"]


def test_a_complete_first_candidate_stops_the_remaining_requests() -> None:
    """Bóc đủ 27 giá trị thì dừng — không gọi thừa vào trang nguồn."""
    from datetime import date

    seen: list[str] = []

    class Http:
        def get(self, url, timeout=20):
            seen.append(url)
            class R:
                status_code = 200
                text = COMPLETE
            return R()

    _ManyCandidates().fetch_partial(date(2026, 9, 5), Http())
    assert len(seen) == 1


def test_the_richest_candidate_wins_even_when_a_later_one_also_parses() -> None:
    """Giữ bản bóc được NHIỀU NHẤT, không phải bản cuối cùng bóc được.

    Trang tường thuật trực tiếp thường mới có vài giải; trang theo ngày thì
    đủ. Thứ tự ứng viên KHÔNG đảm bảo trang đầy đủ đứng cuối, nên "giữ bản
    cuối khác rỗng" là sai — và nó sai âm thầm, vì kết quả vẫn hợp lệ, chỉ
    thiếu giải.

    Bản đầu của phép kiểm này đặt trang đầy đủ ở CUỐI, nên một đột biến đổi
    "giữ bản nhiều nhất" thành "giữ bản cuối" vẫn xanh.
    """
    from datetime import date

    ngay = date(2026, 9, 5)
    source = _ManyCandidates()
    urls = source.live_urls(ngay)
    assert len(urls) > 2

    rich = ("<div>Đặc Biệt 83772</div><div>G1 68785</div>"
            "<div>G2 50518 27452</div>"
            "<div>G7 66 21 34 78</div>")

    class Http:
        def get(self, url, timeout=20):
            class R:
                status_code = 200
                # Ứng viên ĐẦU giàu nhất; các ứng viên sau vẫn bóc được nhưng ít hơn.
                text = rich if url == urls[0] else "<div>Đặc Biệt 11111</div>"
            return R()

    prize_map = source.fetch_partial(ngay, Http(), live=True)
    assert prize_map["special"] == ["83772"], "đã lấy nhầm bản nghèo hơn ở cuối"
    assert prize_map["prize7"] == ["66", "21", "34", "78"]
