"""Bảng giải phải đúng kỳ, còn nguyên sau mất cache và không bị nguồn cũ che."""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import date

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


def test_old_seed_finance_failure_keeps_retryable_cache_and_recovers_after_restart(tmp_path, monkeypatch):
    """Finance của kỳ cũ chưa có journal phải bền trước khi baseline cache đổi."""
    import os
    settings = Settings(data_dir=tmp_path, product_seed_dir=tmp_path / 'empty-seed',
                        source='github_mirror', fallback_order=['github_mirror'], ml_auto_update_enabled=False)
    rows = [canonical(1, '2026-09-30'), canonical()]
    repo = repository()
    repo.upsert([Draw(game='mega645', draw_id=1, draw_date='2026-09-30',
                      numbers=(10, 14, 36, 37, 41, 43), source='seed')])
    state = AppState(settings, repo)
    def handler(request):
        if request.url.path.endswith('power645.jsonl'):
            return httpx.Response(200, text=''.join(json.dumps({'id':row['draw_id'], 'date':row['draw_date'],
                      'result':row['result']['main_numbers']}) + '\n' for row in rows))
        if request.url.path.endswith('mega645.jsonl'):
            return httpx.Response(200, text=''.join(json.dumps(row) + '\n' for row in rows))
        return httpx.Response(404)
    @asynccontextmanager
    async def client(_settings):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            yield http
    monkeypatch.setattr(service, 'build_http_client', client)
    real_open = os.open
    journal_writes = 0
    def fail_finance(path, flags, *args, **kwargs):
        nonlocal journal_writes
        if os.fspath(path) == os.fspath(service.journal_path(state)):
            journal_writes += 1
            if journal_writes > 1:
                raise OSError('finance journal unavailable')
        return real_open(path, flags, *args, **kwargs)
    with monkeypatch.context() as failed:
        failed.setattr(os, 'open', fail_finance)
        report = asyncio.run(service.update_product(state, 'mega645', learn=False))
    assert report['prize_error'] == 'OSError'
    assert repo.load_prizes('mega645') == []

    restarted = AppState(settings, repo)
    report = asyncio.run(service.update_product(restarted, 'mega645', learn=False))
    assert report['prize_error'] is None
    recovered = AppState(settings, InMemoryRepository())
    service.replay_results(recovered)
    prize = next(p for p in recovered.repository.load_prizes('mega645') if p.draw_id == 1)
    assert prize.jackpot_pots == {'jackpot1':14_163_913_000}
    assert prize.winners == {'jackpot1':0, 'first':18, 'second':1063, 'third':19569}


@pytest.mark.parametrize('backend', ['memory', 'duckdb'])
@pytest.mark.parametrize('incoming_finance', [False, True])
def test_pending_result_correction_recovers_after_upsert_before_old_finance_is_removed(tmp_path, monkeypatch, backend, incoming_finance):
    """Commit số và loại finance là hai bước; CAS phải nhận trạng thái ở giữa."""
    repo = repository() if backend == 'memory' else DuckDBRepository(tmp_path / 'cache.duckdb')
    if backend == 'duckdb':
        repo.upsert(repository().load('mega645'))
    repo.upsert_prizes([PrizeRecord(game='mega645', draw_id=2, draw_date='2026-10-07',
        winners={'jackpot1':0, 'first':18}, jackpot_pots={'jackpot1':14_163_913_000}, source='vietlott.vn')])
    settings = Settings(data_dir=tmp_path, ml_auto_update_enabled=False)
    state = AppState(settings, repo)
    @asynccontextmanager
    async def client(_settings):
        text = json.dumps({'id':2, 'date':'2026-10-07', 'result':[1,2,3,4,5,6]}) + '\n'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200, text=text))) as http:
            yield http
    monkeypatch.setattr(service, 'build_http_client', client)
    if incoming_finance:
        from vietlott_engine.crawler.sources.base import FetchResult
        class Source:
            name = 'validated-source'
            async def fetch(self, *_args, **_kwargs):
                return FetchResult(draws=[Draw(game='mega645', draw_id=2, draw_date='2026-10-07',
                    numbers=(1,2,3,4,5,6), jackpot1_value=999, tier_winners={'jackpot1':7, 'second':999})])
        monkeypatch.setattr(service, 'build_source', lambda *_args:Source())
    with monkeypatch.context() as crash:
        def interrupt(*args, **kwargs):
            raise RuntimeError('crash before finance invalidation')
        crash.setattr(repo, 'invalidate_finance', interrupt)
        with pytest.raises(RuntimeError, match='crash before finance invalidation'):
            asyncio.run(service.sync_matrix(state, MEGA_645, source='github_mirror', full_refresh=True, learn=False))
    restarted = AppState(settings, repo)
    service.replay_results(restarted)
    assert restarted.replay_conflicts == []
    assert repo.load('mega645')[0].numbers == (1,2,3,4,5,6)
    assert repo.load_prizes('mega645') == []
    assert not list((tmp_path / 'updates').glob('pending-*.json'))
    if backend == 'duckdb':
        repo.close()


def test_pending_new_finance_recovers_when_only_its_draw_was_committed(tmp_path, monkeypatch):
    """Kỳ mới đã ghi draws nhưng crash trước prizes vẫn có thể hoàn tất outbox."""
    settings = Settings(data_dir=tmp_path, ml_auto_update_enabled=False)
    repo = InMemoryRepository()
    state = AppState(settings, repo)
    async def fetch(*args, **kwargs):
        return [canonical()]
    import vietlott_engine.crawler.product_store as product_store
    monkeypatch.setattr(product_store, '_prize_records', fetch)
    def persist(additions, accepted):
        finance = {p.draw_id:p for p in accepted}
        records = [service._matrix_record(draw, finance.get(draw.draw_id)) for draw in additions]
        service._stage_pending(state, records, {})
        service._append(state, records)
    with monkeypatch.context() as crashed:
        def interrupt(*args, **kwargs):
            raise RuntimeError('crash before prize commit')
        crashed.setattr(repo, 'upsert_prizes', interrupt)
        with pytest.raises(RuntimeError, match='crash before prize commit'):
            asyncio.run(sync_canonical_prizes(None, repo, MEGA_645, source='canonical',
                canonical_base_url='', vietlott_base_url='', before_upsert=persist))
    assert repo.count('mega645') == 1
    assert repo.load_prizes('mega645') == []
    restarted = AppState(settings, repo)
    service.replay_results(restarted)
    assert restarted.replay_conflicts == []
    assert repo.load_prizes('mega645')[0].jackpot_pots == {'jackpot1':14_163_913_000}
    assert not list((tmp_path / 'updates').glob('pending-*.json'))


def test_multibatch_pending_finance_recovers_from_last_committed_batch(tmp_path):
    """Batch B đã commit phải là baseline hợp lệ khi batch C dừng trước upsert."""
    state = AppState(Settings(data_dir=tmp_path), repository())
    draw = state.repository.load('mega645')[0]
    def record(count):
        return service._matrix_record(draw, PrizeRecord(game='mega645', draw_id=2, draw_date='2026-10-07',
            winners={'first':count}, source='vietlott.vn'))
    original = service._matrix_record(draw)
    first, second = record(1), record(2)
    service._stage_pending(state, [first], {('mega645',2):original})
    service._append(state, [first])
    state.repository.upsert_prizes([PrizeRecord(game='mega645', draw_id=2, draw_date='2026-10-07',
        winners={'first':1}, source='vietlott.vn')])
    committed = service._matrix_records(state.repository, MEGA_645)[0]
    service._stage_pending(state, [second], {('mega645',2):committed})
    service._append(state, [second])
    restarted = AppState(state.settings, state.repository)
    service.replay_results(restarted)
    assert restarted.replay_conflicts == []
    assert state.repository.load_prizes('mega645')[0].winners == {'first':2}
    assert not list((tmp_path / 'updates').glob('pending-*.json'))


def test_refused_pending_finance_is_not_applied_by_the_ordinary_journal(tmp_path):
    """Sau khi CAS từ chối, đường replay thường không được ghi đè canonical khác."""
    state = AppState(Settings(data_dir=tmp_path), repository())
    draw = state.repository.load('mega645')[0]
    before = service._matrix_record(draw)
    after = service._matrix_record(draw, PrizeRecord(game='mega645', draw_id=2, draw_date='2026-10-07',
        winners={'first':1}, source='vietlott.vn'))
    service._stage_pending(state, [after], {('mega645',2):before})
    service._append(state, [after])
    canonical = PrizeRecord(game='mega645', draw_id=2, draw_date='2026-10-07', winners={'first':9}, source='canonical')
    state.repository.upsert_prizes([canonical])
    restarted = AppState(state.settings, state.repository)
    service.replay_results(restarted)
    assert restarted.replay_conflicts
    assert restarted.repository.load_prizes('mega645') == [canonical]
    assert list((tmp_path / 'updates').glob('pending-*.json'))


@pytest.mark.parametrize('backend', ['memory', 'duckdb'])
def test_matrix_finance_only_seed_correction_is_staged_before_cache_commit(tmp_path, monkeypatch, backend):
    """Draw giữ nguyên số nhưng đổi jackpot cũng phải lưu delta trước cache."""
    import os
    from vietlott_engine.crawler.sources.base import FetchResult
    repo = InMemoryRepository() if backend == 'memory' else DuckDBRepository(tmp_path / 'cache.duckdb')
    old = Draw(game='mega645', draw_id=1, draw_date='2026-09-30', numbers=(1,2,3,4,5,6),
               jackpot1_value=100, tier_winners={'first':5})
    latest = old.model_copy(update={'draw_id':2, 'draw_date':date(2026,10,2), 'jackpot1_value':None})
    repo.upsert([old,latest])
    corrected = old.model_copy(update={'jackpot1_value':200, 'tier_winners':None})
    class Source:
        name = 'archive'
        async def fetch(self, *_args, **_kwargs):
            return FetchResult(draws=[corrected,latest])
    monkeypatch.setattr(service, 'build_source', lambda *_args:Source())
    @asynccontextmanager
    async def client(_settings):
        yield None
    monkeypatch.setattr(service, 'build_http_client', client)
    settings = Settings(data_dir=tmp_path, ml_auto_update_enabled=False)
    state = AppState(settings, repo)
    real_open = os.open
    def refuse_journal(path, flags, *args, **kwargs):
        if os.fspath(path) == os.fspath(service.journal_path(state)):
            raise OSError('journal unavailable')
        return real_open(path, flags, *args, **kwargs)
    with monkeypatch.context() as failed:
        failed.setattr(os, 'open', refuse_journal)
        with pytest.raises(OSError, match='journal unavailable'):
            asyncio.run(service.sync_matrix(state, MEGA_645, full_refresh=True, learn=False))
    assert repo.load('mega645')[0].jackpot1_value == 100
    restarted = AppState(settings, repo)
    service.replay_results(restarted)
    assert repo.load('mega645')[0].jackpot1_value == 200
    assert repo.load('mega645')[0].tier_winners == ({'first':5} if backend == 'duckdb' else None)
    restored = AppState(settings, InMemoryRepository())
    service.replay_results(restored)
    assert restored.repository.load('mega645')[0].jackpot1_value == 200
    assert restored.repository.load('mega645')[0].tier_winners == ({'first':5} if backend == 'duckdb' else None)
    if backend == 'duckdb':
        repo.close()


@pytest.mark.parametrize('existing_cache', [False, True])
def test_pending_draw_finance_replay_keeps_exact_metadata_when_cleanup_is_interrupted(tmp_path, monkeypatch, existing_cache):
    """Replay không được tự tạo metadata finance khiến lần retry từ chối chính nó."""
    repo = repository() if existing_cache else InMemoryRepository()
    settings = Settings(data_dir=tmp_path)
    state = AppState(settings, repo)
    after = service._matrix_record(Draw(game='mega645', draw_id=2, draw_date='2026-10-07',
        numbers=(10,14,36,37,41,43), jackpot1_value=100))
    previous = {(r.game_type,r.draw_id):r for r in service._matrix_records(repo, MEGA_645)}
    service._stage_pending(state, [after], previous)
    service._append(state, [after])
    with monkeypatch.context() as interrupted:
        def crash(*args, **kwargs):
            raise RuntimeError('crash before pending cleanup')
        interrupted.setattr(service, '_clear_pending', crash)
        with pytest.raises(RuntimeError, match='crash before pending cleanup'):
            service.replay_results(state)
    assert service._journal_identity(service._matrix_records(repo, MEGA_645)[0]) == service._journal_identity(after)
    assert list((tmp_path / 'updates').glob('pending-*.json'))
    restarted = AppState(settings, repo)
    service.replay_results(restarted)
    assert restarted.replay_conflicts == []
    assert repo.load('mega645')[0].jackpot1_value == 100
    assert not list((tmp_path / 'updates').glob('pending-*.json'))


def test_mixed_pending_conflict_keeps_successful_draw_metadata_retryable(tmp_path):
    """Outbox còn conflict không cho journal đổi metadata của key đã phục hồi."""
    repo = repository()
    state = AppState(Settings(data_dir=tmp_path), repo)
    draw = repo.load('mega645')[0]
    before_second = service._matrix_record(draw)
    after_first = service._matrix_record(draw.model_copy(update={'draw_id':1, 'jackpot1_value':100}))
    after_second = service._matrix_record(draw, PrizeRecord(game='mega645', draw_id=2, draw_date='2026-10-07',
        winners={'first':1}, source='vietlott.vn'))
    service._stage_pending(state, [after_first, after_second], {('mega645',2):before_second})
    service._append(state, [after_first, after_second])
    unrelated = PrizeRecord(game='mega645', draw_id=2, draw_date='2026-10-07',
                            winners={'first':9}, source='canonical')
    repo.upsert_prizes([unrelated])

    restarted = AppState(state.settings, repo)
    service.replay_results(restarted)
    assert restarted.replay_conflicts == [{'game_type':'mega645', 'draw_id':2}]
    assert repo.load_prizes('mega645') == [unrelated]
    recovered_first = next(r for r in service._matrix_records(repo, MEGA_645) if r.draw_id == 1)
    assert service._journal_identity(recovered_first) == service._journal_identity(after_first)
    assert list((tmp_path / 'updates').glob('pending-*.json'))

    # Giải quyết riêng conflict thứ hai, giữ nguyên key đã phục hồi để thử lại.
    repo.invalidate_finance('mega645', [2])
    retried = AppState(state.settings, repo)
    service.replay_results(retried)
    assert retried.replay_conflicts == []
    assert repo.load('mega645')[0].jackpot1_value == 100
    assert next(p for p in repo.load_prizes('mega645') if p.draw_id == 2).winners == {'first':1}
    assert not list((tmp_path / 'updates').glob('pending-*.json'))


@pytest.mark.parametrize('backend', ['memory', 'duckdb'])
def test_existing_draw_finance_replay_survives_crash_between_draw_and_prizes(tmp_path, monkeypatch, backend):
    """Replay lần hai phải nhận đúng trạng thái dở dang do lần đầu tự ghi."""
    settings = Settings(data_dir=tmp_path, ml_auto_update_enabled=False)
    repo = repository() if backend == 'memory' else DuckDBRepository(tmp_path / 'results.duckdb')
    if backend == 'duckdb':
        repo.upsert(repository().load('mega645'))
    state = AppState(settings, repo)
    draw = repo.load('mega645')[0]
    before = service._matrix_record(draw)
    prize = PrizeRecord(game='mega645', draw_id=2, draw_date='2026-10-07',
                        winners={'jackpot1':0, 'first':1}, jackpot_pots={'jackpot1':100}, source='vietlott.vn')
    after = service._matrix_record(draw, prize)
    service._stage_pending(state, [after], {('mega645',2):before})
    with monkeypatch.context() as interrupted:
        def crash(_rows):
            raise OSError('interrupted prize replay')
        interrupted.setattr(repo, 'upsert_prizes', crash)
        with pytest.raises(OSError, match='interrupted prize replay'):
            service.replay_results(state)
    assert repo.load('mega645')[0].jackpot1_value == 100
    assert repo.load_prizes('mega645') == []
    assert service._pending_path(state, 'mega645').exists()
    restarted = AppState(settings, repo)
    service.replay_results(restarted)
    assert restarted.replay_conflicts == []
    assert service._journal_identity(service._matrix_records(repo, MEGA_645)[0]) == service._journal_identity(after)
    assert repo.load_prizes('mega645') == [prize]
    assert not service._pending_path(restarted, 'mega645').exists()
    if backend == 'duckdb':
        repo.close()
