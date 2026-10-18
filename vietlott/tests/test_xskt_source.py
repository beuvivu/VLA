"""Nguồn ``xskt``: đọc đúng bảng kết quả Mega/Power/Lotto, lọc theo số kỳ, và đứng sau bản sao
cộng đồng trong chuỗi ``auto`` — bản sao chậm thì kỳ mới vẫn vào được.

HTML mẫu chép nguyên từ trang thật, đọc qua runner Actions ngày 06-10-2026 (crawler Vietlott
cũ của VLA, ``tests/test_vietlott_results.py`` trước commit dc13ab6e).
"""
import asyncio
from datetime import date

import pytest

from vietlott_engine.core.config import Settings
from vietlott_engine.core.exceptions import SourceError
from vietlott_engine.core.games import GameCode, get_game
from vietlott_engine.core.models import Draw
from vietlott_engine.crawler.pipeline import SyncPipeline, build_source
from vietlott_engine.crawler.product_store import ProductSyncPipeline
from vietlott_engine.crawler.sources.base import DrawSource, FetchResult
from vietlott_engine.crawler.sources.fallback import FallbackDrawSource
from vietlott_engine.crawler.sources.xskt import XsktDrawSource, parse_page
from vietlott_engine.core.products import ProductCode
from vietlott_engine.crawler.storage import InMemoryRepository

MEGA = (
    '<table class="result"><tr><td class="kmt" colspan="2"><span>Kỳ mở thưởng:</span> '
    '<a href="/xsmega645/ngay-4-10-2026"><b>#01571</b></a></td></tr><tr><td class="ketquatxt">Kết quả</td>'
    '<td class="megaresult"><em>15 20 29 37 40 45</em></td></tr></table>'
    '<table class="trunggiai"><tr><td colspan="4">Thống kê trúng giải</td></tr><tr><th>Giải</th>'
    "<th>Trùng khớp</th><th>Số người trúng</th><th>Trị giá giải (VNĐ)</th></tr>"
    "<tr><td>J.pot</td><td></td><td><em>1</em></td><td><em>199,576,277,000</em></td></tr>"
    "<tr><td>G.1</td><td></td><td><b>153</b></td><td>10,000,000</td></tr></table>"
)
LOTTO = (
    '<table class="result"><tr><td class="kmt" colspan="2"><span>Kỳ mở thưởng:</span> '
    '<a href="/xslotto-21h/ngay-5-10-2026"><b>#00928 (21h)</b></a></td></tr><tr><td class="ketquatxt">'
    'Kết quả</td><td class="megaresult"><em>01 13 16 20 26 <span>11</span></em></td></tr></table>'
    '<table class="trunggiai"><tr><td colspan="4">Thống kê trúng giải</td></tr>'
    "<tr><td>J.pot</td><td></td><td><b>0</b></td><td>10,323,886,500</td></tr></table>"
)
POWER = (
    '<table class="result"><tr><td class="kmt" colspan="2"><a href="/xspower/ngay-3-10-2026"><b>#01406</b>'
    '</a></td></tr><tr><td class="ketquatxt">Kết quả</td><td class="megaresult"><em>07 11 13 16 18 54</em>'
    "</td></tr><tr><td>Số JP2</td><td><em>41</em></td></tr></table>"
    '<table class="trunggiai"><tr><td>J.pot</td><td></td><td>0</td><td>112,784,140,200</td></tr>'
    "<tr><td>Jpot2</td><td></td><td>0</td><td>3,695,872,550</td></tr></table>"
)
#: Kỳ trước đó trên cùng trang tổng (cùng khuôn), để kiểm lọc theo số kỳ.
LOTTO_13H = (
    '<table class="result"><tr><td class="kmt" colspan="2"><a href="/xslotto-13h/ngay-5-10-2026">'
    '<b>#00927 (13h)</b></a></td></tr><tr><td class="megaresult"><em>02 05 19 30 33 <span>07</span></em>'
    "</td></tr></table>"
)


def test_mega_reads_numbers_draw_id_date_and_jackpot():
    (draw,) = parse_page(get_game(GameCode.MEGA_645), MEGA).draws
    assert (draw.draw_id, draw.draw_date, draw.numbers, draw.bonus) == (1571, date(2026, 10, 4), (15, 20, 29, 37, 40, 45), None)
    assert draw.jackpot1_value == 199_576_277_000 and draw.source == "xskt"


def test_lotto_keeps_the_special_number_and_both_sessions():
    draws = parse_page(get_game(GameCode.LOTTO_535), LOTTO_13H + LOTTO).draws
    assert [(d.draw_id, d.draw_date, d.numbers, d.bonus) for d in draws] == [
        (927, date(2026, 10, 5), (2, 5, 19, 30, 33), 7),
        (928, date(2026, 10, 5), (1, 13, 16, 20, 26), 11)]


def test_power_reads_the_jackpot_2_number_and_both_jackpots():
    (draw,) = parse_page(get_game(GameCode.POWER_655), POWER).draws
    assert (draw.draw_id, draw.numbers, draw.bonus) == (1406, (7, 11, 13, 16, 18, 54), 41)
    assert (draw.jackpot1_value, draw.jackpot2_value) == (112_784_140_200, 3_695_872_550)


def test_incomplete_tables_are_skipped_and_impossible_numbers_rejected_not_invented():
    partial = MEGA.replace("15 20 29 37 40 45", "15 20 29 37 40")
    assert parse_page(get_game(GameCode.MEGA_645), partial).draws == []
    out_of_range = parse_page(get_game(GameCode.MEGA_645), MEGA.replace("45</em>", "46</em>"))
    assert out_of_range.draws == [] and len(out_of_range.rejected) == 1
    no_special = parse_page(get_game(GameCode.LOTTO_535), LOTTO.replace(" <span>11</span>", ""))
    assert no_special.draws == []


def test_a_page_that_disagrees_with_itself_is_an_error():
    other = MEGA.replace("15 20 29 37 40 45", "15 20 29 37 40 44")
    with pytest.raises(SourceError):
        parse_page(get_game(GameCode.MEGA_645), MEGA + other)


class _Client:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages, self.urls = pages, []

    async def get(self, url: str):  # type: ignore[no-untyped-def]
        self.urls.append(url)
        if url not in self.pages:
            raise SourceError(f"GET {url} failed with non-retryable HTTP 404")
        return type("R", (), {"text": self.pages[url]})()


def test_fetch_reads_the_product_page_and_keeps_only_newer_draws():
    client = _Client({"https://xskt.com.vn/xslotto-5-35": LOTTO_13H + LOTTO})
    got = asyncio.run(XsktDrawSource(client, "https://xskt.com.vn/").fetch(get_game(GameCode.LOTTO_535), since_id=927))
    assert [d.draw_id for d in got.draws] == [928] and client.urls == ["https://xskt.com.vn/xslotto-5-35"]


def test_an_unreadable_page_fails_the_source_instead_of_claiming_no_new_draw():
    client = _Client({"https://xskt.com.vn/xsmega645": "<html><body>Bảo trì</body></html>"})
    with pytest.raises(SourceError):
        asyncio.run(XsktDrawSource(client, "https://xskt.com.vn").fetch(get_game(GameCode.MEGA_645), since_id=1))


class _Stale(DrawSource):
    name = "nhanaz"

    async def fetch(self, spec, since_id=None):  # type: ignore[no-untyped-def]
        return FetchResult(draws=[d for d in [Draw(game=spec.code, draw_id=927, draw_date=date(2026, 10, 5),
                                                    numbers=(2, 5, 19, 30, 33), bonus=7, source="nhanaz")]
                                  if since_id is None or d.draw_id > since_id])


def test_a_lagging_archive_no_longer_hides_a_draw_the_republisher_already_has():
    """Bản sao dừng ở #927; chuỗi phải hỏi tiếp và lấy #928 từ xskt thay vì báo "không có kỳ mới"."""
    client = _Client({"https://xskt.com.vn/xslotto-5-35": LOTTO_13H + LOTTO})
    chain = FallbackDrawSource([_Stale(), XsktDrawSource(client, "https://xskt.com.vn")])
    got = asyncio.run(chain.fetch(get_game(GameCode.LOTTO_535), since_id=927))
    assert [d.draw_id for d in got.draws] == [928] and chain.name == "auto:xskt"


def test_the_default_chain_asks_xskt_after_the_archive_and_only_for_matrix_games():
    order = Settings().fallback_order
    assert order.index("nhanaz") < order.index("xskt") < order.index("github_mirror")
    source = build_source(Settings(), object(), "auto")  # type: ignore[arg-type]
    assert [s.name for s in source.sources][:3] == ["vietlott", "nhanaz", "xskt"]
    products = ProductSyncPipeline(object(), object(), vietlott_base_url="", mirror_base_url="", canonical_base_url="",  # type: ignore[arg-type]
                                   fallback_order=order)
    assert "xskt" not in products.chain(ProductCode.MAX3D)


def test_the_source_can_be_chosen_through_the_environment(monkeypatch):
    """``VQE_SOURCE=xskt`` phải qua được kiểm cấu hình, không chỉ cờ dòng lệnh."""
    monkeypatch.setenv("VQE_SOURCE", "xskt")
    settings = Settings()
    assert settings.source == "xskt"
    assert isinstance(build_source(settings, object()), XsktDrawSource)  # type: ignore[arg-type]


def test_a_partially_caught_up_archive_is_extended_by_the_later_source():
    """Kho dừng ở #926, bản sao mới có #927, xskt đã có #928: lấy cả hai, #927 vẫn từ bản sao."""
    client = _Client({"https://xskt.com.vn/xslotto-5-35": LOTTO_13H + LOTTO})
    chain = FallbackDrawSource([_Stale(), XsktDrawSource(client, "https://xskt.com.vn")])
    got = asyncio.run(chain.fetch(get_game(GameCode.LOTTO_535), since_id=926))
    assert [(d.draw_id, d.source) for d in got.draws] == [(927, "nhanaz"), (928, "xskt")]
    assert chain.name == "auto:nhanaz+xskt" and chain.log.used == "nhanaz"


class _Fixed(DrawSource):
    def __init__(self, name: str, draws: list[Draw]) -> None:
        self.name, self.draws = name, draws
        self.cursors: list[int | None] = []

    async def fetch(self, spec, since_id=None):  # type: ignore[no-untyped-def]
        self.cursors.append(since_id)
        return FetchResult(draws=[d for d in self.draws if since_id is None or d.draw_id > since_id])


def _mega(draw_id: int, numbers: tuple[int, ...] = (1, 2, 3, 4, 5, 6)) -> Draw:
    return Draw(game=GameCode.MEGA_645, draw_id=draw_id, draw_date=date(2026, 10, 1 + draw_id - 927), numbers=numbers)


def test_a_later_source_never_replaces_a_draw_and_never_leaves_a_gap():
    first = _Fixed("nhanaz", [_mega(927)])
    later = _Fixed("xskt", [_mega(927, (7, 8, 9, 10, 11, 12)), _mega(928), _mega(930)])
    got = asyncio.run(FallbackDrawSource([first, later]).fetch(get_game(GameCode.MEGA_645), since_id=926))
    assert [d.draw_id for d in got.draws] == [927, 928] and got.draws[0].numbers == (1, 2, 3, 4, 5, 6)


def test_xskt_refuses_a_page_window_that_would_leave_a_gap():
    client = _Client({"https://xskt.com.vn/xslotto-5-35": LOTTO_13H + LOTTO})
    with pytest.raises(SourceError, match="#901"):
        asyncio.run(XsktDrawSource(client, "https://xskt.com.vn").fetch(get_game(GameCode.LOTTO_535), since_id=900))


def _lotto_table(draw_id: int, day: int, numbers: str, special: str) -> str:
    return (f'<table class="result"><tr><td class="kmt" colspan="2"><a href="/xslotto-13h/ngay-{day}-10-2026">'
            f'<b>#{draw_id:05d} (13h)</b></a></td></tr><tr><td class="megaresult"><em>{numbers} <span>{special}</span>'
            '</em></td></tr></table>')


def test_later_sources_are_asked_from_the_merged_tail_not_the_original_cursor():
    """Kho ở #920, bản sao lấp #921–#927, trang xskt chỉ giữ #925–#928: vẫn nối được #928."""
    archive = _Fixed("nhanaz", [Draw(game=GameCode.LOTTO_535, draw_id=i, draw_date=date(2026, 10, i - 920),
                                     numbers=(1, 2, 3, 4, 5), bonus=6, source="nhanaz") for i in range(921, 928)])
    page = "".join(_lotto_table(i, i - 920, "01 02 03 04 05", "06") for i in range(925, 929))
    client = _Client({"https://xskt.com.vn/xslotto-5-35": page})
    chain = FallbackDrawSource([archive, XsktDrawSource(client, "https://xskt.com.vn")])
    got = asyncio.run(chain.fetch(get_game(GameCode.LOTTO_535), since_id=920))
    assert [d.draw_id for d in got.draws] == list(range(921, 929)) and got.draws[-1].source == "xskt"


def _gap_draw(draw_id: int, source: str, numbers=(1, 2, 3, 4, 5, 6)) -> Draw:
    return Draw(game="mega645", draw_id=draw_id, draw_date=date(2026, 10, 7 + 2 * (draw_id - 1)),
                numbers=numbers, source=source)


def test_first_source_gap_is_filled_without_losing_its_buffered_draw():
    repo = InMemoryRepository([_gap_draw(1, "canonical")])
    primary = _Fixed("primary", [_gap_draw(3, "primary")])
    backup = _Fixed("backup", [_gap_draw(2, "backup"), _gap_draw(3, "backup", (7, 8, 9, 10, 11, 12))])
    chain = FallbackDrawSource([primary, backup])
    report = asyncio.run(SyncPipeline(chain, repo).run(get_game("mega645")))
    draws = repo.load("mega645")
    assert [draw.draw_id for draw in draws] == [1, 2, 3]
    assert (draws[2].numbers, draws[2].source) == ((1, 2, 3, 4, 5, 6), "primary")
    assert backup.cursors == [1]
    assert [(a.source, a.ok, a.rows) for a in chain.log.attempts] == [("primary", True, 1), ("backup", True, 1)]
    assert chain.name == "auto:primary+backup" and report.integrity.id_gaps == []


def test_first_source_internal_gap_keeps_descending_buffer_and_advances_cursor():
    primary = _Fixed("primary", [_gap_draw(4, "primary"), _gap_draw(2, "primary")])
    backup = _Fixed("backup", [_gap_draw(5, "backup"), _gap_draw(4, "backup", (7, 8, 9, 10, 11, 12)),
                               _gap_draw(3, "backup")])
    chain = FallbackDrawSource([primary, backup])
    got = asyncio.run(chain.fetch(get_game("mega645"), since_id=1))
    assert [draw.draw_id for draw in got.draws] == [2, 3, 4, 5]
    assert (got.draws[2].numbers, got.draws[2].source) == ((1, 2, 3, 4, 5, 6), "primary")
    assert backup.cursors == [2]
    assert [(a.source, a.rows) for a in chain.log.attempts] == [("primary", 2), ("backup", 2)]


@pytest.mark.parametrize("fails", [False, True])
def test_unresolved_internal_gap_does_not_publish_buffered_later_draw(fails):
    class Backup(_Fixed):
        async def fetch(self, spec, since_id=None):
            if fails:
                raise SourceError("unavailable")
            return await super().fetch(spec, since_id)

    primary = _Fixed("primary", [_gap_draw(2, "primary"), _gap_draw(4, "primary")])
    got = asyncio.run(FallbackDrawSource([primary, Backup("backup", [])]).fetch(get_game("mega645"), since_id=1))
    assert [draw.draw_id for draw in got.draws] == [2]


def test_missing_first_new_draw_remains_an_error_after_all_sources():
    chain = FallbackDrawSource([_Fixed("primary", [_gap_draw(3, "primary")]),
                                _Fixed("backup", [_gap_draw(4, "backup")])])
    with pytest.raises(SourceError, match="#2"):
        asyncio.run(chain.fetch(get_game("mega645"), since_id=1))


def test_source_failure_does_not_discard_buffered_primary_draw():
    class Unavailable(DrawSource):
        name = "unavailable"

        async def fetch(self, spec, since_id=None):
            raise SourceError("unavailable")

    primary = _Fixed("primary", [_gap_draw(3, "primary")])
    backup = _Fixed("backup", [_gap_draw(2, "backup"), _gap_draw(3, "backup"), _gap_draw(4, "backup")])
    chain = FallbackDrawSource([primary, Unavailable(), backup])
    got = asyncio.run(chain.fetch(get_game("mega645"), since_id=1))
    assert [(draw.draw_id, draw.source) for draw in got.draws] == [(2, "backup"), (3, "primary"), (4, "backup")]
    assert backup.cursors == [1]


def test_buffered_contributors_retain_their_rejected_rows_once():
    class Source(_Fixed):
        async def fetch(self, spec, since_id=None):
            if self.name == "unavailable":
                raise SourceError("unavailable")
            result = await super().fetch(spec, since_id)
            result.rejected.append((self.name, "invalid row"))
            return result

    chain = FallbackDrawSource([Source("primary", [_gap_draw(3, "primary")]), Source("unavailable", []),
                                Source("backup", [_gap_draw(2, "backup"), _gap_draw(3, "backup")])])
    got = asyncio.run(chain.fetch(get_game("mega645"), since_id=1))
    assert [draw.draw_id for draw in got.draws] == [2, 3]
    assert got.rejected == [("primary", "invalid row"), ("backup", "invalid row")]


def test_cold_start_retains_the_first_available_batch_without_inferring_its_prefix():
    primary = _Fixed("primary", [_mega(929), _mega(927)])
    backup = _Fixed("backup", [_mega(930)])
    got = asyncio.run(FallbackDrawSource([primary, backup]).fetch(get_game("mega645"), since_id=None))
    assert [draw.draw_id for draw in got.draws] == [927, 929, 930]
    assert primary.cursors == [None] and backup.cursors == [929]
