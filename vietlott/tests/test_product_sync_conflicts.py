"""Max 3D / 3D Pro / 4D: nguồn không được sửa kỳ đã lưu (05-11-2026).

Bản sao và kho canonical trả CẢ lịch sử. Trước bản vá, ``ProductSyncPipeline.run`` gửi mọi dòng ấy vào
``ProductStore.upsert``, và kỳ trùng mã bị ghi đè lặng lẽ bằng bản của nguồn — khác với luật của
Keno/Bingo18 (``_run_fast``) và Mega/Power/Lotto (``SyncPipeline``). Luật chung: ``auto`` bỏ nguồn mâu
thuẫn và hỏi nguồn kế tiếp; chọn đích danh một nguồn thì chỉ bỏ kỳ mâu thuẫn; chỉ ``--full`` từ
vietlott.vn chính thức được sửa kỳ cũ.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from vietlott_engine.core.products import ProductCode
from vietlott_engine.crawler.product_store import ProductStore, ProductSyncPipeline

GOOD = {did: [f"{(did * 37 + i * 11) % 1000:03d}" for i in range(20)] for did in range(1, 6)}
WRONG_2 = ["999"] * 20  # kỳ 2 do một nguồn đăng sai


def _row(did: int, values: list[str] | None = None) -> dict:
    return {"id": did, "date": f"2026-10-{did:02d}", "result": values or GOOD[did]}


class _Pipeline(ProductSyncPipeline):
    """Mỗi nguồn trả đúng dòng dựng sẵn; không gọi mạng."""

    def __init__(self, store: ProductStore, served: dict[str, list[dict]], order: list[str]) -> None:
        super().__init__(None, store, vietlott_base_url="https://v", mirror_base_url="https://m",  # type: ignore[arg-type]
                         canonical_base_url="https://c", fallback_order=order)
        self.served = served

    async def fetch(self, product, source, max_pages, full):  # type: ignore[no-untyped-def,override]
        return [dict(r) for r in self.served[source]]


def _store(tmp_path: Path) -> ProductStore:
    store = ProductStore(tmp_path / "data", None)
    store.upsert(ProductCode.MAX3D, [_row(1), _row(2), _row(3)], "seed")
    return store


def _values(store: ProductStore, did: int) -> list[str]:
    h = store.load(ProductCode.MAX3D)
    return [f"{int(v):03d}" for v in h.values[list(h.draw_ids).index(did)]]


def _run(store: ProductStore, served: dict[str, list[dict]], source: str, order: list[str], full: bool = False):  # type: ignore[no-untyped-def]
    return asyncio.run(_Pipeline(store, served, order).run(ProductCode.MAX3D, source, full=full))


def test_auto_skips_a_source_that_rewrites_a_stored_draw(tmp_path: Path) -> None:
    store = _store(tmp_path)
    served = {"mirror": [_row(1), _row(2, WRONG_2), _row(3), _row(4)],
              "canonical": [_row(1), _row(2), _row(3), _row(4), _row(5)]}
    rep = _run(store, served, "auto", ["mirror", "canonical"])
    assert _values(store, 2) == GOOD[2]
    assert rep.source_used == "canonical" and rep.inserted == 2 and rep.last_id == 5
    assert rep.attempts[0]["conflicting_ids"] == [2] and not rep.attempts[0]["ok"]
    assert "conflicting source results kept out: [2]" in (rep.error or "")


def test_a_named_source_keeps_its_new_draws_but_not_its_rewrite(tmp_path: Path) -> None:
    store = _store(tmp_path)
    rep = _run(store, {"mirror": [_row(2, WRONG_2), _row(4)]}, "mirror", ["mirror"])
    assert _values(store, 2) == GOOD[2] and _values(store, 4) == GOOD[4]
    assert rep.inserted == 1 and "conflicting" in (rep.error or "")


def test_a_conflicting_source_alone_writes_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)
    rep = _run(store, {"mirror": [_row(2, WRONG_2), _row(4)]}, "auto", ["mirror"])
    assert _values(store, 2) == GOOD[2] and list(store.load(ProductCode.MAX3D).draw_ids) == [1, 2, 3]
    assert rep.inserted == 0 and rep.source_used is None and "conflicting" in (rep.error or "")


def test_only_a_full_official_refresh_may_correct_a_stored_draw(tmp_path: Path) -> None:
    store = _store(tmp_path)
    rep = _run(store, {"vietlott": [_row(2, WRONG_2), _row(4)]}, "vietlott", ["vietlott"], full=True)
    assert _values(store, 2) == WRONG_2 and rep.error is None
    store = _store(tmp_path / "again")
    _run(store, {"vietlott": [_row(2, WRONG_2), _row(4)]}, "vietlott", ["vietlott"], full=False)
    assert _values(store, 2) == GOOD[2]


def test_agreeing_sources_still_sync_without_errors(tmp_path: Path) -> None:
    store = _store(tmp_path)
    rep = _run(store, {"mirror": [_row(1), _row(2), _row(3), _row(4)]}, "auto", ["mirror"])
    assert rep.error is None and rep.inserted == 1 and rep.source_used == "mirror"
