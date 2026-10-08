"""Loại tài chính sai kỳ trên cả hai kho mà không đổi kết quả quay."""

from pathlib import Path

import pytest

from vietlott_engine.core.models import Draw
from vietlott_engine.core.prizes import PrizeRecord
from vietlott_engine.crawler.storage import DuckDBRepository, InMemoryRepository


@pytest.fixture(params=["memory", "duckdb"])
def repo(request, tmp_path: Path):
    repository = InMemoryRepository() if request.param == "memory" else DuckDBRepository(tmp_path / "draws.duckdb")
    yield repository
    if isinstance(repository, DuckDBRepository):
        repository.close()


def _draw(game: str, draw_id: int) -> Draw:
    return Draw(
        game=game,
        draw_id=draw_id,
        draw_date="2026-10-08",
        numbers=(1, 2, 3, 4, 5, 6),
        bonus=7 if game == "power655" else None,
        jackpot1_value=30_000_000_000,
        jackpot2_value=3_000_000_000 if game == "power655" else None,
        tier_winners={"jackpot1": 1, "first": 10},
        source="vietlott.vn",
    )


def _prize(game: str, draw_id: int) -> PrizeRecord:
    return PrizeRecord(
        game=game,
        draw_id=draw_id,
        draw_date="2026-10-08",
        winners={"jackpot1": 1, "first": 10},
        jackpot_pots={"jackpot1": 30_000_000_000},
        source="vietlott.vn",
    )


def test_invalidate_finance_clears_selected_draws_and_preserves_other_rows(repo):
    """Xóa thiếu điều kiện game/ID hoặc xóa kết quả quay sẽ làm phép kiểm này đỏ."""
    repo.upsert([_draw("power655", i) for i in (100, 101, 102)] + [_draw("mega645", 100)])
    repo.upsert_prizes([_prize("power655", i) for i in (100, 101, 102)] + [_prize("mega645", 100)])

    repo.invalidate_finance("power655", [100, 101, 100, 999])

    power = repo.load("power655")
    assert [d.draw_id for d in power] == [100, 101, 102]
    for draw in power[:2]:
        assert (draw.draw_date.isoformat(), draw.numbers, draw.bonus, draw.source) == (
            "2026-10-08", (1, 2, 3, 4, 5, 6), 7, "vietlott.vn"
        )
        assert (draw.jackpot1_value, draw.jackpot2_value, draw.tier_winners) == (None, None, None)
    assert power[2] == _draw("power655", 102)
    assert repo.load_prizes("power655") == [_prize("power655", 102)]
    assert repo.load("mega645") == [_draw("mega645", 100)]
    assert repo.load_prizes("mega645") == [_prize("mega645", 100)]


def test_invalidate_finance_clears_direct_values_without_a_prize_record(repo):
    """Không được chỉ xóa bảng prizes rồi để số tiền cũ trên Draw."""
    repo.upsert([_draw("power655", 100)])

    repo.invalidate_finance("power655", [100])

    draw = repo.load("power655")[0]
    assert (draw.jackpot1_value, draw.jackpot2_value, draw.tier_winners) == (None, None, None)


def test_invalidate_finance_removes_prize_without_a_draw(repo):
    """Bảng giải rời không được sống sót vì kho chưa có kết quả quay."""
    repo.upsert_prizes([_prize("power655", 100)])

    repo.invalidate_finance("power655", [100])

    assert repo.load_prizes("power655") == []
    assert repo.load("power655") == []


def test_invalidate_finance_with_no_ids_preserves_all_finance(repo):
    """Danh sách rỗng không được biến thành xóa cả game."""
    repo.upsert([_draw("power655", 100)])
    repo.upsert_prizes([_prize("power655", 100)])

    repo.invalidate_finance("power655", [])

    assert repo.load("power655") == [_draw("power655", 100)]
    assert repo.load_prizes("power655") == [_prize("power655", 100)]
