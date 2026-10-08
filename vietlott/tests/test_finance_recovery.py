"""Bảng giải phải đúng kỳ, còn nguyên sau mất cache và không bị nguồn cũ che."""
import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest

from vietlott_engine.api.deps import AppState
from vietlott_engine.core.config import Settings
from vietlott_engine.core.games import MEGA_645, POWER_655
from vietlott_engine.core.models import Draw
from vietlott_engine.core.prizes import PrizeRecord
from vietlott_engine.crawler.product_store import sync_canonical_prizes
from vietlott_engine.crawler.storage import DuckDBRepository, InMemoryRepository
from vlm.database.schema import DrawRecord
from vlm.updates import service


def canonical(draw_id=2, day='2026-10-07', numbers=None, *, prizes=True):
    row = {'draw_id': draw_id, 'draw_date': day,
           'result': {'main_numbers': numbers or [10, 14, 36, 37, 41, 43], 'bonus_numbers': []}}
    if prizes:
        row['prizes'] = [
            {'code': 'jackpot', 'winner_count': 0, 'jackpot_vnd': 14_163_913_000},
            {'code': 'giai-nhat', 'winner_count': 18},
            {'code': 'giai-nhi', 'winner_count': 1063},
            {'code': 'giai-ba', 'winner_count': 19569},
        ]
    return row


def repository():
    return InMemoryRepository([Draw(game='mega645', draw_id=2, draw_date='2026-10-07',
                                   numbers=(10, 14, 36, 37, 41, 43), source='github_mirror')])


@pytest.mark.parametrize('first', [canonical(1, '2026-10-04'), canonical(prizes=False)])
def test_auto_finance_continues_past_stale_or_prizeless_source(monkeypatch, first):
    """Dừng ở dữ liệu cũ hoặc chỉ có số quay sẽ bỏ mất jackpot đúng kỳ ở nguồn sau."""
    import vietlott_engine.crawler.product_store as store
    async def fetch(_client, _repo, _spec, source, **_kwargs):
        return [first] if source == 'canonical' else [canonical()]
    monkeypatch.setattr(store, '_prize_records', fetch)
    repo = repository()
    rep = asyncio.run(sync_canonical_prizes(None, repo, MEGA_645, source='auto', last=1,
                     canonical_base_url='', vietlott_base_url='', fallback_order=['canonical', 'nhanaz']))
    prize = next(p for p in repo.load_prizes('mega645') if p.draw_id == 2)
    assert prize.jackpot_pots == {'jackpot1': 14_163_913_000}
    assert prize.winners['third'] == 19569
    assert rep.error is None


@pytest.mark.parametrize('wrong', [canonical(day='2026-10-04'), canonical(numbers=[1, 2, 3, 4, 5, 6])])
def test_finance_source_cannot_replace_existing_draw_to_make_its_table_match(monkeypatch, wrong):
    """Bỏ gate ngày/số sẽ gắn bảng giải khác vào mã kỳ đã xác thực."""
    import vietlott_engine.crawler.product_store as store
    async def fetch(*_args, **_kwargs): return [wrong]
    monkeypatch.setattr(store, '_prize_records', fetch)
    repo = repository()
    rep = asyncio.run(sync_canonical_prizes(None, repo, MEGA_645, source='auto', last=1,
                     canonical_base_url='', vietlott_base_url='', fallback_order=['canonical']))
    draw = repo.load('mega645')[0]
    assert (draw.draw_date.isoformat(), draw.numbers) == ('2026-10-07', (10, 14, 36, 37, 41, 43))
    assert repo.load_prizes('mega645') == []
    assert rep.error


def test_old_finance_does_not_report_latest_finance_success(monkeypatch):
    """Đếm bảng giải lịch sử không chứng minh kỳ mới đã có dữ liệu tài chính."""
    import vietlott_engine.crawler.product_store as store
    async def fetch(*_args, **_kwargs): return [canonical(1, '2026-10-04')]
    monkeypatch.setattr(store, '_prize_records', fetch)
    repo = repository()
    rep = asyncio.run(sync_canonical_prizes(None, repo, MEGA_645, source='auto', last=1,
                     canonical_base_url='', vietlott_base_url='', fallback_order=['canonical']))
    assert rep.error
    assert [p.draw_id for p in repo.load_prizes('mega645')] == [1]


@pytest.mark.parametrize('field', ['game', 'game_type', 'product'])
def test_declared_other_product_cannot_supply_same_number_finance(monkeypatch, field):
    """Bỏ tên sản phẩm khai trong row sẽ biến bảng giải Power thành Mega."""
    import vietlott_engine.crawler.product_store as store
    async def fetch(*_args, **_kwargs): return [canonical() | {field:'power655'}]
    monkeypatch.setattr(store, '_prize_records', fetch)
    repo = repository()
    rep = asyncio.run(sync_canonical_prizes(None, repo, MEGA_645, source='auto', last=1,
                     canonical_base_url='', vietlott_base_url='', fallback_order=['canonical']))
    assert repo.load_prizes('mega645') == []
    assert rep.error


def test_rejected_duplicate_draw_cannot_poison_matching_rows_finance(monkeypatch):
    """Gate từng số quay nhưng join lại chỉ theo ID sẽ nhận pot của row đã bị loại."""
    import vietlott_engine.crawler.product_store as store
    wrong = canonical(numbers=[1, 2, 3, 4, 5, 6])
    wrong['prizes'][0]['jackpot_vnd'] = 999_000_000_000
    async def fetch(*_args, **_kwargs): return [canonical(), wrong]
    monkeypatch.setattr(store, '_prize_records', fetch)
    repo = repository()
    asyncio.run(sync_canonical_prizes(None, repo, MEGA_645, source='canonical', last=1,
                canonical_base_url='', vietlott_base_url=''))
    assert repo.load_prizes('mega645')[0].jackpot_pots == {'jackpot1':14_163_913_000}


def test_partial_official_table_does_not_relabel_a_secondary_jackpot(monkeypatch):
    """Ghép pot từ nguồn cũ rồi gắn source mới làm provenance khẳng định sai."""
    import vietlott_engine.crawler.product_store as store
    partial = canonical()
    partial['prizes'][0].pop('jackpot_vnd')
    async def fetch(*_args, **_kwargs): return [partial]
    monkeypatch.setattr(store, '_prize_records', fetch)
    repo = repository()
    repo.upsert_prizes([PrizeRecord(game='mega645', draw_id=2, draw_date='2026-10-07',
        winners={'jackpot1':0, 'first':18, 'second':1063, 'third':19569},
        jackpot_pots={'jackpot1':14_163_913_000}, source='mirror')])
    asyncio.run(sync_canonical_prizes(None, repo, MEGA_645, source='canonical', last=1,
                canonical_base_url='', vietlott_base_url=''))
    prize = repo.load_prizes('mega645')[0]
    assert (prize.jackpot_pots, prize.source) == ({'jackpot1':14_163_913_000}, 'mirror')


def test_power_finance_requires_the_same_bonus_ball(monkeypatch):
    """Bonus cũng thuộc danh tính kết quả, dù sáu số chính khớp."""
    import vietlott_engine.crawler.product_store as store
    row = {'draw_id':1408, 'draw_date':'2026-10-08',
           'result':{'main_numbers':[1, 7, 12, 27, 31, 52], 'bonus_numbers':[8]},
           'prizes':[{'code':code, 'winner_count':0, **({'jackpot_vnd':value} if code.startswith('jackpot') else {})}
                     for code, value in [('jackpot-1',100), ('jackpot-2',200),
                                        ('giai-nhat',0), ('giai-nhi',0), ('giai-ba',0)]]}
    async def fetch(*_args, **_kwargs): return [row]
    monkeypatch.setattr(store, '_prize_records', fetch)
    repo = InMemoryRepository([Draw(game='power655', draw_id=1408, draw_date='2026-10-08',
                                   numbers=(1, 7, 12, 27, 31, 52), bonus=6)])
    rep = asyncio.run(sync_canonical_prizes(None, repo, POWER_655, source='canonical', last=1,
                     canonical_base_url='', vietlott_base_url=''))
    assert repo.load('power655')[0].bonus == 6
    assert repo.load_prizes('power655') == []
    assert rep.error


def test_complete_secondary_power_table_can_fill_matching_partial_official_table(monkeypatch):
    """Một dict pot không rỗng vẫn có thể thiếu Jackpot 2; không được che bảng đủ ở nguồn sau."""
    import vietlott_engine.crawler.product_store as store
    row = {'draw_id':1408, 'draw_date':'2026-10-08', 'data_source':'mirror',
           'result':{'main_numbers':[1, 7, 12, 27, 31, 52], 'bonus_numbers':[6]},
           'prizes':[{'code':code, 'winner_count':0, **({'jackpot_vnd':value} if code.startswith('jackpot') else {})}
                     for code, value in [('jackpot-1',100), ('jackpot-2',200),
                                        ('giai-nhat',0), ('giai-nhi',0), ('giai-ba',0)]]}
    async def fetch(*_args, **_kwargs): return [row]
    monkeypatch.setattr(store, '_prize_records', fetch)
    repo = InMemoryRepository([Draw(game='power655', draw_id=1408, draw_date='2026-10-08',
                                   numbers=(1, 7, 12, 27, 31, 52), bonus=6)])
    repo.upsert_prizes([PrizeRecord(game='power655', draw_id=1408, draw_date='2026-10-08',
                       winners={'jackpot1':0}, jackpot_pots={'jackpot1':100}, source='vietlott.vn')])
    rep = asyncio.run(sync_canonical_prizes(None, repo, POWER_655, source='auto', last=1,
                     canonical_base_url='', vietlott_base_url='', fallback_order=['nhanaz']))
    prize = repo.load_prizes('power655')[0]
    assert prize.jackpot_pots == {'jackpot1':100, 'jackpot2':200}
    assert prize.source == 'mirror'
    assert rep.error is None


@pytest.mark.parametrize('existing_cache', [False, True])
def test_update_persists_finance_only_change_and_replays_the_exact_table(tmp_path, monkeypatch, existing_cache):
    """Bỏ lần ghi sau finance, dedup finance hoặc replay bảng giải sẽ làm jackpot mất sau cache loss."""
    settings = Settings(data_dir=tmp_path, product_seed_dir=tmp_path / 'empty-seed',
                        source='github_mirror', fallback_order=['github_mirror'], ml_auto_update_enabled=False)
    state = AppState(settings, repository())
    record = DrawRecord.from_legacy('mega645', {'id':2, 'date':'2026-10-07',
                                   'result':[10, 14, 36, 37, 41, 43], 'source':'github_mirror'})
    service._append(state, [record])
    def handler(request):
        if request.url.path.endswith('power645.jsonl'):
            return httpx.Response(200, text=json.dumps({'id':2, 'date':'2026-10-07',
                                    'result':[10, 14, 36, 37, 41, 43]}) + '\n')
        if request.url.path.endswith('mega645.jsonl'):
            return httpx.Response(200, text=json.dumps(canonical()) + '\n')
        return httpx.Response(404)
    @asynccontextmanager
    async def client(_settings):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http: yield http
    monkeypatch.setattr(service, 'build_http_client', client)
    result = asyncio.run(service.update_product(state, 'mega645', learn=False))
    assert result['prize_error'] is None
    restored = AppState(settings, repository() if existing_cache else InMemoryRepository())
    service.replay_results(restored)
    prize = restored.repository.load_prizes('mega645')[0]
    assert (prize.draw_id, prize.draw_date.isoformat()) == (2, '2026-10-07')
    assert prize.jackpot_pots == {'jackpot1': 14_163_913_000}
    assert prize.winners == {'jackpot1':0, 'first':18, 'second':1063, 'third':19569}
    assert prize.source == 'vietlott.vn'
    before = service.journal_path(state).read_text()
    asyncio.run(service.update_product(state, 'mega645', learn=False))
    assert service.journal_path(state).read_text() == before


def test_replay_finance_never_attaches_to_current_corrected_numbers(tmp_path):
    """Bỏ đối chiếu bộ số khi replay sẽ làm bảng giải cũ theo mã kỳ thắng bản sửa."""
    settings = Settings(data_dir=tmp_path)
    writer = AppState(settings, InMemoryRepository())
    row = canonical()
    row['source'] = 'vietlott.vn'
    service._append(writer, [DrawRecord.from_legacy('mega645', row)])
    corrected = Draw(game='mega645', draw_id=2, draw_date='2026-10-07', numbers=(1, 2, 3, 4, 5, 6))
    restored = AppState(settings, InMemoryRepository([corrected]))
    service.replay_results(restored)
    assert restored.repository.load('mega645')[0].numbers == (1, 2, 3, 4, 5, 6)
    assert restored.repository.load_prizes('mega645') == []
    assert restored.replay_conflicts


def test_replay_does_not_label_journal_pots_with_a_partial_cached_tables_source(tmp_path):
    """Bổ sung pot từ journal không thể coi nguồn của cache không có pot là nguồn pot."""
    settings = Settings(data_dir=tmp_path)
    writer = AppState(settings, InMemoryRepository())
    service._append(writer, [DrawRecord.from_legacy('mega645', canonical() | {'source':'mirror'})])
    repo = repository()
    repo.upsert_prizes([PrizeRecord(game='mega645', draw_id=2, draw_date='2026-10-07',
                       winners={'jackpot1':0, 'first':18, 'second':1063, 'third':19569}, source='vietlott.vn')])
    service.replay_results(AppState(settings, repo))
    prize = repo.load_prizes('mega645')[0]
    assert (prize.jackpot_pots, prize.source) == ({'jackpot1':14_163_913_000}, 'mirror')


@pytest.mark.parametrize('backend', ['memory', 'duckdb'])
def test_sync_result_correction_discards_old_numbers_finance_before_journaling(tmp_path, monkeypatch, backend):
    """Cùng ID/ngày nhưng số đã sửa phải loại bảng giải còn gắn với số cũ."""
    settings = Settings(data_dir=tmp_path, ml_auto_update_enabled=False)
    repo = repository() if backend == 'memory' else DuckDBRepository(tmp_path / 'vietlott.duckdb', tmp_path / 'parquet')
    if backend == 'duckdb':
        repo.upsert([d.model_copy(update={'jackpot1_value':14_163_913_000, 'tier_winners':{'jackpot1':0}})
                     for d in repository().load('mega645')])
    prize = PrizeRecord(game='mega645', draw_id=2, draw_date='2026-10-07',
                        winners={'jackpot1':0, 'first':18, 'second':1063, 'third':19569},
                        jackpot_pots={'jackpot1':14_163_913_000}, source='vietlott.vn')
    repo.upsert_prizes([prize])
    state = AppState(settings, repo)
    service._append(state, [service._matrix_record(repo.load('mega645')[0], prize)])
    @asynccontextmanager
    async def client(_settings):
        response = json.dumps({'id':2, 'date':'2026-10-07', 'result':[1, 2, 3, 4, 5, 6]}) + '\n'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200, text=response))) as http:
            yield http
    monkeypatch.setattr(service, 'build_http_client', client)
    asyncio.run(service.sync_matrix(state, MEGA_645, source='github_mirror', full_refresh=True, learn=False))
    assert repo.load_prizes('mega645') == []
    latest = json.loads(service.journal_path(state).read_text().splitlines()[-1])
    assert latest['winning_numbers'] == [1, 2, 3, 4, 5, 6]
    assert latest['jackpot1_value'] is None
    assert latest['jackpot1_winners'] is None
    if backend == 'duckdb':
        import duckdb
        with duckdb.connect() as con:
            exported = con.execute('SELECT jackpot1_value, tier_winners FROM read_parquet(?)',
                                   [str(tmp_path / 'parquet' / 'mega645.parquet')]).fetchall()
        assert exported == [(None, None)]
        repo.close()
