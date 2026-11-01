import asyncio
import json
from datetime import datetime, timedelta

import pytest


def _sync_response(product,rows,request):
    """Số mẫu từ nguồn chính thức cho kiểm thử journal; matrix giữ JSONL cũ."""
    import httpx
    if product=='mega645':
        return httpx.Response(200,text=''.join(json.dumps(r)+'\n' for r in rows))
    from tests.test_all_products import _bingo_html
    page=json.loads(request.content)['PageIndex'] if request.method=='POST' else -1
    html=_bingo_html([(datetime.fromisoformat(r['date']).strftime('%d/%m/%Y'),r['id'],r['result'])
                      for r in rows]) if page==1 else ''
    return httpx.Response(200,json={'value':{'HtmlContent':html}})


def test_pending_fsync_failure_closes_temp_before_cleanup(tmp_path, monkeypatch):
    """Mô phỏng Windows: không unlink tệp còn mở, không che lỗi fsync gốc."""
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.database.schema import DrawRecord
    from vlm.updates import service

    state = AppState(Settings(data_dir=tmp_path), InMemoryRepository())
    record = DrawRecord.from_legacy('mega645', {'id':1, 'date':'2026-10-07', 'result':[1,2,3,4,5,6]})
    handles = []
    original_temp = service.tempfile.NamedTemporaryFile
    original_unlink = service.os.unlink
    def track_temp(*args, **kwargs):
        handle = original_temp(*args, **kwargs)
        handles.append(handle)
        return handle
    def refuse_open_unlink(path, *args, **kwargs):
        if any(not handle.closed for handle in handles):
            raise PermissionError('temporary file is still open')
        return original_unlink(path, *args, **kwargs)
    def fail_fsync(_fd):
        raise OSError('original fsync failure')
    monkeypatch.setattr(service.tempfile, 'NamedTemporaryFile', track_temp)
    monkeypatch.setattr(service.os, 'unlink', refuse_open_unlink)
    monkeypatch.setattr(service.os, 'fsync', fail_fsync)
    with pytest.raises(OSError, match='original fsync failure'):
        service._stage_pending(state, [record], {})
    assert all(handle.closed for handle in handles)
    assert list((tmp_path / 'updates').iterdir()) == []


@pytest.mark.parametrize('product,now,want', [
    ('mega645','2026-10-03T19:00:00+07:00','2026-10-02T18:30:00+07:00'),
    ('power655','2026-10-03T18:29:59+07:00','2026-10-01T18:30:00+07:00'),
    ('power655','2026-10-03T11:30:00+00:00','2026-10-03T18:30:00+07:00'),
    ('max3d','2026-10-05T18:30:00+07:00','2026-10-05T18:30:00+07:00'),
    ('max3dpro','2026-10-04T01:00:00+07:00','2026-10-03T18:30:00+07:00'),
    ('lotto535','2026-10-03T13:09:59+07:00','2026-10-02T21:10:00+07:00'),
    ('lotto535','2026-10-03T21:10:00+07:00','2026-10-03T21:10:00+07:00'),
])
def test_completed_slots_respect_draw_day_delay_and_vietnam_time(product,now,want):
    from vlm.updates.schedule import latest_completed_slot
    assert latest_completed_slot(product,datetime.fromisoformat(now)).isoformat()==want


@pytest.mark.parametrize('product,now,want', [
    ('keno','2026-10-03T06:00:00+07:00',120),
    ('bingo18','2026-10-03T22:14:59+07:00',120),
    ('keno','2026-10-03T22:15:00+07:00',3600),
    ('power655','2026-10-03T18:00:00+07:00',120),
    ('mega645','2026-10-03T18:30:00+07:00',3600),
    ('lotto535','2026-10-03T21:30:00+07:00',120),
])
def test_poll_only_uses_each_products_live_window(product,now,want):
    from vlm.updates.schedule import poll_interval
    assert poll_interval(product,datetime.fromisoformat(now))==want


def test_date_only_fast_results_and_one_lotto_draw_cannot_certify_current_results():
    from vlm.updates.schedule import freshness
    now=datetime.fromisoformat('2026-10-03T22:00:00+07:00')
    assert freshness('keno',now,'2026-10-03',100)['verified'] is False
    assert freshness('lotto535',now,'2026-10-03',1)['status']=='behind_schedule'
    assert freshness('lotto535',now,'2026-10-03',2)['verified'] is True
    assert freshness('power655',now,'2026-10-01',1)['status']=='behind_schedule'


def test_runner_failure_isolated_persisted_and_retried_after_restart(tmp_path):
    from vlm.updates.runner import UpdateRunner
    async def run():
        now=datetime.fromisoformat('2026-10-03T18:35:00+07:00')
        async def update(product):
            if product=='power655': raise RuntimeError('secret proxy password')
            return {'last_draw_id':1,'last_draw_date':'2026-10-03','draws_on_last_date':4,'inserted':1,'source':'test'}
        path=tmp_path/'updates.json'
        r=UpdateRunner(path,update,products=('power655','bingo18'),clock=lambda:now)
        await r.tick()
        status=json.loads(path.read_text())['products']
        assert status['power655']['failures']==1
        assert status['power655']['error']=='RuntimeError'
        assert status['bingo18']['last_draw_id']==1
        assert status['bingo18']['freshness']['verified'] is False
        assert 'secret' not in path.read_text()
        now+=timedelta(seconds=30)
        restarted=UpdateRunner(path,update,products=('power655','bingo18'),clock=lambda:now)
        await restarted.tick()
        assert restarted.status()['products']['power655']['failures']==2
        assert not list(tmp_path.glob('*.tmp'))
    asyncio.run(run())


def test_stalled_source_cannot_starve_another_product_and_overlapping_ticks_skip(tmp_path):
    from vlm.updates.runner import UpdateRunner
    async def run():
        async def update(product):
            if product=='keno': await asyncio.Event().wait()
            return {'last_draw_id':99,'last_draw_date':'2026-10-03','draws_on_last_date':2,'inserted':1}
        r=UpdateRunner(tmp_path/'status.json',update,products=('keno','lotto535'),timeout_s=0.02,
                       clock=lambda:datetime.fromisoformat('2026-10-03T21:30:00+07:00'))
        await asyncio.gather(r.tick(),r.tick())
        status=r.status()['products']
        assert status['keno']['failures']==1
        assert status['keno']['error']=='TimeoutError'
        assert status['lotto535']['last_draw_id']==99
        assert status['lotto535']['freshness']['verified'] is True
    asyncio.run(run())


def test_empty_success_is_stale_and_new_due_slot_overrides_old_next_attempt(tmp_path):
    from vlm.updates.runner import UpdateRunner
    async def run():
        now=datetime.fromisoformat('2026-10-03T13:09:00+07:00')
        async def update(product): return {'last_draw_id':9,'last_draw_date':'2026-10-02','draws_on_last_date':2,'inserted':0}
        r=UpdateRunner(tmp_path/'status.json',update,products=('lotto535',),clock=lambda:now)
        await r.tick()
        before=r.status()['products']['lotto535']['last_attempt']
        now+=timedelta(minutes=1)
        await r.tick()
        entry=r.status()['products']['lotto535']
        assert entry['last_attempt']!=before
        assert entry['freshness']['status']=='behind_schedule'
    asyncio.run(run())


def test_overdue_weekly_result_is_retried_within_five_minutes_after_live_window(tmp_path):
    from vlm.updates.runner import UpdateRunner
    async def run():
        now = datetime.fromisoformat('2026-10-03T20:00:00+07:00')
        async def update(product):
            return {'last_draw_id':1, 'last_draw_date':'2026-10-01', 'draws_on_last_date':1, 'inserted':0}
        r = UpdateRunner(tmp_path / 'status.json', update, products=('power655',), clock=lambda:now)
        entry = (await r.tick())['products']['power655']
        assert entry['freshness']['status'] == 'behind_schedule'
        assert datetime.fromisoformat(entry['next_attempt']) - now <= timedelta(minutes=5)
    asyncio.run(run())


def test_api_starts_periodic_updater_and_cancels_it_before_closing_storage(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from vietlott_engine.api.main import create_app
    from vietlott_engine.core.config import Settings
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.updates.runner import UpdateRunner
    stopped=[]
    async def run_forever(self):
        try: await asyncio.Event().wait()
        finally: stopped.append(True)
    monkeypatch.setattr(UpdateRunner,'run_forever',run_forever)
    app=create_app(Settings(storage_backend='memory',data_dir=tmp_path,auto_update_enabled=True),repository=InMemoryRepository())
    with TestClient(app) as client:
        status=client.get('/updates/status')
        assert status.status_code==200
        assert status.json()['enabled'] is True
        assert status.json()['timezone']=='Asia/Ho_Chi_Minh'
    assert stopped==[True]


def test_sync_service_saves_results_and_invalidates_api_cache(tmp_path,monkeypatch):
    from contextlib import asynccontextmanager
    from fastapi.testclient import TestClient
    from vietlott_engine.api.main import create_app
    from vietlott_engine.core.config import Settings
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.updates.service import update_product
    import vlm.updates.service as service
    import httpx
    def handler(request):
        if request.url.path.endswith('power645.jsonl'):
            return httpx.Response(200,text='{"id":1,"date":"2026-10-02","result":[1,2,3,4,5,6]}\n')
        return httpx.Response(404)
    @asynccontextmanager
    async def client(_settings):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c: yield c
    monkeypatch.setattr(service,'build_http_client',client)
    settings=Settings(storage_backend='memory',data_dir=tmp_path,source='github_mirror',fallback_order=['github_mirror'],
                      auto_update_enabled=False)
    app=create_app(settings,repository=InMemoryRepository())
    with TestClient(app) as c:
        assert c.get('/games/mega645/draws').status_code==409
        result=c.portal.call(update_product,app.state.vqe,'mega645')
        assert result['last_draw_id']==1
        assert result['inserted']==1
        assert c.get('/games/mega645/draws').json()['total']==1
    journal=tmp_path/'updates'/'results.jsonl'
    rows=[json.loads(line) for line in journal.read_text().splitlines()]
    assert rows[0]['game_type']=='mega645'
    assert rows[0]['draw_id']==1
    assert rows[0]['winning_numbers']==[1,2,3,4,5,6]


def test_matrix_empty_or_timed_out_source_falls_through_to_real_new_result():
    from vietlott_engine.crawler.sources.fallback import FallbackDrawSource
    from vietlott_engine.crawler.sources.base import FetchResult
    from vietlott_engine.core.games import MEGA_645
    from vietlott_engine.core.models import Draw
    async def run():
        class Empty:
            name='stale'
            async def fetch(self,*args): return FetchResult()
        class Blocked:
            name='blocked'
            async def fetch(self,*args): await asyncio.Event().wait()
        class Fresh:
            name='fresh'
            async def fetch(self,*args):
                return FetchResult(draws=[Draw(game='mega645',draw_id=2,draw_date='2026-10-02',numbers=(1,2,3,4,5,6))])
        source=FallbackDrawSource([Empty(),Blocked(),Fresh()],source_timeout_s=0.02)
        result=await source.fetch(MEGA_645,1)
        assert result.draws[0].draw_id==2
        assert source.log.used=='fresh'
    asyncio.run(run())


def test_product_stale_source_does_not_hide_newer_fallback(tmp_path):
    from vietlott_engine.crawler.product_store import ProductStore, ProductSyncPipeline
    from vietlott_engine.core.products import ProductCode
    async def run():
        store=ProductStore(tmp_path,None)
        store.upsert(ProductCode.BINGO18,[{'id':1,'date':'2026-10-03','result':[1,2,3]}],'seed')
        class Sources(ProductSyncPipeline):
            async def fetch(self,product,source,max_pages,full):
                return [{'id':1 if source=='nhanaz' else 2,'date':'2026-10-03','result':[1,2,3]}]
        pipe=Sources(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='',
                     fallback_order=['nhanaz','mirror'])
        report=await pipe.run(ProductCode.BINGO18)
        assert report.last_id==2
        assert report.source_used=='mirror'
    asyncio.run(run())


def test_results_journal_recovers_a_lost_database_without_duplicate_rows(tmp_path):
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.database.schema import DrawRecord
    from vlm.updates.service import _append,replay_results
    settings=Settings(data_dir=tmp_path)
    writer=AppState(settings,InMemoryRepository())
    draw=DrawRecord.from_legacy('mega645',{'id':1570,'date':'2026-10-02','result':[1,6,20,27,31,41]})
    _append(writer,[draw])
    _append(writer,[draw])
    restored=AppState(settings,InMemoryRepository())
    assert replay_results(restored)==1
    assert restored.repository.load('mega645')[0].numbers==(1,6,20,27,31,41)
    assert replay_results(restored)==1
    assert restored.repository.count('mega645')==1


def test_exclusive_writer_lease_rejects_second_process_owner(tmp_path):
    from vlm.updates.lease import WriterLease
    with WriterLease(tmp_path/'writer.lock'):
        with pytest.raises(RuntimeError,match='already running'):
            with WriterLease(tmp_path/'writer.lock'): pass
    with WriterLease(tmp_path/'writer.lock'): pass


def test_cli_status_does_not_open_or_write_a_database(tmp_path,capsys):
    from vlm.updates.cli import main
    path=tmp_path/'state'
    path.mkdir()
    (path/'status.json').write_text(json.dumps({'version':1,'products':{'power655':{'error':'TimeoutError'}}}))
    assert main(['--status','--state-dir',str(path)])==0
    assert json.loads(capsys.readouterr().out)['products']['power655']['error']=='TimeoutError'
    assert sorted(p.name for p in path.iterdir())==['status.json']


def test_one_hung_game_does_not_suppress_next_healthy_poll(tmp_path):
    from vlm.updates.runner import UpdateRunner
    async def run():
        now=datetime.fromisoformat('2026-10-03T18:00:00+07:00')
        async def update(product):
            if product=='keno': await asyncio.Event().wait()
            return {'last_draw_id':int((now.hour*3600+now.minute*60)/120),
                    'last_draw_date':'2026-10-03','draws_on_last_date':1,'inserted':1}
        r=UpdateRunner(tmp_path/'status.json',update,products=('keno','bingo18'))
        r.clock=lambda:now
        await r.tick(wait=False)
        await asyncio.sleep(0.01)
        first=r.status()['products']['bingo18']['last_draw_id']
        now+=timedelta(seconds=120)
        await r.tick(wait=False)
        await asyncio.sleep(0.01)
        assert r.status()['products']['bingo18']['last_draw_id']==first+1
        await r.stop()
    asyncio.run(run())


def test_replay_preserves_current_corrections_and_journals_the_correction(tmp_path):
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.core.models import Draw
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.database.schema import DrawRecord
    from vlm.updates.service import _append,replay_results
    state=AppState(Settings(data_dir=tmp_path),InMemoryRepository())
    old=DrawRecord.from_legacy('mega645',{'id':1,'date':'2026-10-02','result':[1,2,3,4,5,6]})
    corrected=old.model_copy(update={'winning_numbers':(1,2,3,4,5,7)})
    _append(state,[old])
    state.repository.upsert([Draw(game='mega645',draw_id=1,draw_date='2026-10-02',numbers=(1,2,3,4,5,7))])
    replay_results(state)
    assert state.repository.load('mega645')[0].numbers==(1,2,3,4,5,7)
    _append(state,[corrected])
    restored=AppState(state.settings,InMemoryRepository())
    replay_results(restored)
    assert restored.repository.load('mega645')[0].numbers==(1,2,3,4,5,7)


def test_torn_final_journal_record_retains_valid_prefix_and_can_append_again(tmp_path):
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.database.schema import DrawRecord
    from vlm.updates.service import _append,replay_results,journal_path
    state=AppState(Settings(data_dir=tmp_path),InMemoryRepository())
    draw=DrawRecord.from_legacy('mega645',{'id':1,'date':'2026-10-02','result':[1,2,3,4,5,6]})
    _append(state,[draw])
    with journal_path(state).open('a') as f: f.write('{"game_type":')
    restored=AppState(state.settings,InMemoryRepository())
    replay_results(restored)
    assert restored.repository.count('mega645')==1
    _append(restored,[draw.model_copy(update={'draw_id':2})])
    again=AppState(state.settings,InMemoryRepository())
    replay_results(again)
    assert again.repository.count('mega645')==2
    assert list(journal_path(state).parent.glob('*.corrupt'))


def test_valid_unterminated_journal_tail_is_separated_before_next_append(tmp_path):
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.database.schema import DrawRecord
    from vlm.updates.service import _append, replay_results, journal_path
    state = AppState(Settings(data_dir=tmp_path), InMemoryRepository())
    draw = DrawRecord.from_legacy('mega645', {'id':1, 'date':'2026-10-02', 'result':[1,2,3,4,5,6]})
    _append(state, [draw])
    path = journal_path(state)
    path.write_bytes(path.read_bytes().rstrip(b'\n'))
    restored = AppState(state.settings, InMemoryRepository())
    assert replay_results(restored) == 1
    _append(restored, [draw.model_copy(update={'draw_id':2})])
    again = AppState(state.settings, InMemoryRepository())
    assert replay_results(again) == 2
    assert [d.draw_id for d in again.repository.load('mega645')] == [1,2]


@pytest.mark.parametrize('product', ['mega645', 'bingo18'])
def test_sync_service_journals_corrections_to_older_existing_draws(tmp_path,monkeypatch,product):
    from contextlib import asynccontextmanager
    import httpx
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.core.games import get_game
    from vietlott_engine.core.models import Draw
    from vietlott_engine.core.products import ProductCode
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.database.schema import DrawRecord
    import vlm.updates.service as service
    numbers = [1,2,3,4,5,6] if product == 'mega645' else [1,2,3]
    old = {'id':1, 'date':'2026-09-30', 'result':numbers}
    latest = old | {'id':2, 'date':'2026-10-02'}
    corrected = old | {'result':numbers[:-1] + [7 if product == 'mega645' else 4]}
    settings = Settings(data_dir=tmp_path, product_seed_dir=tmp_path / 'empty-seed')
    state = AppState(settings, InMemoryRepository())
    if product == 'mega645':
        state.repository.upsert([Draw(game=product,draw_id=r['id'],draw_date=r['date'],numbers=r['result']) for r in (old,latest)])
    else:
        state.product_store().upsert(ProductCode(product), [old,latest], 'seed')
    service._append(state, [DrawRecord.from_legacy(product,r) for r in (old,latest)])
    @asynccontextmanager
    async def client(_settings):
        transport = httpx.MockTransport(lambda request:_sync_response(product,(corrected,latest),request))
        async with httpx.AsyncClient(transport=transport) as c: yield c
    monkeypatch.setattr(service, 'build_http_client', client)
    if product == 'mega645':
        asyncio.run(service.sync_matrix(state, get_game(product), source='github_mirror', full_refresh=True))
    else:
        asyncio.run(service.sync_product(state, ProductCode(product), source='vietlott', full=True))
    restored = AppState(settings, InMemoryRepository())
    # Simulate cache/database loss for the product store as well.
    if product == 'bingo18':
        for path in (tmp_path / 'products').iterdir(): path.unlink()
    service.replay_results(restored)
    values = list(restored.repository.load(product)[0].numbers) if product == 'mega645' else restored.product_store().load(product).values[0].tolist()
    assert values == corrected['result']


def test_off_schedule_weekly_result_is_never_certified_fresh():
    from vlm.updates.schedule import freshness
    r=freshness('mega645',datetime.fromisoformat('2026-10-03T19:00:00+07:00'),'2026-10-03',1)
    assert r['verified'] is False
    assert r['status']=='invalid_schedule'


def test_fast_game_no_id_advance_for_twenty_minutes_is_reported(tmp_path):
    from vlm.updates.runner import UpdateRunner
    async def run():
        now=datetime.fromisoformat('2026-10-03T08:00:00+07:00')
        async def update(product):
            return {'last_draw_id':77,'last_draw_date':'2026-10-03','draws_on_last_date':1,'inserted':0}
        r=UpdateRunner(tmp_path/'status.json',update,products=('keno',),clock=lambda:now)
        await r.tick()
        now+=timedelta(minutes=20)
        await r.tick()
        entry=r.status()['products']['keno']
        assert entry['freshness']['status']=='not_advancing'
        assert entry['freshness']['verified'] is False
    asyncio.run(run())


@pytest.mark.parametrize('source, hours, expected', [('mirror', 12, 'date_only'), ('mirror', 14, 'not_advancing'),
                                                     ('vietlott', 1, 'not_advancing')])
def test_fast_game_stall_is_judged_by_the_cadence_of_the_source_that_last_advanced(tmp_path, source, hours, expected):
    """Bản sao cập nhật 12 giờ một lần (01-11-2026): chờ nó 12 giờ là bình thường, quá 13 giờ là lỡ một lượt.
    Nguồn khác vẫn bị báo sau 20 phút không tiến."""
    from vlm.updates.runner import UpdateRunner
    async def run():
        now=datetime.fromisoformat('2026-10-03T07:05:00+07:00')
        ids=iter([76, 77])
        async def update(product):
            return {'last_draw_id':next(ids, 77),'last_draw_date':'2026-10-03','draws_on_last_date':1,'inserted':1,
                    'source':source}
        r=UpdateRunner(tmp_path/'status.json',update,products=('keno',),clock=lambda:now)
        await r.tick()
        now+=timedelta(minutes=10)
        await r.tick()
        now+=timedelta(hours=hours)
        assert r.status()['products']['keno']['freshness']['status']==expected
    asyncio.run(run())


@pytest.mark.parametrize('filename', ['draws.jsonl', 'draws.jsonl.gz'])
def test_product_atomic_write_failure_keeps_existing_results(tmp_path,monkeypatch,filename):
    from vietlott_engine.core.products import write_jsonl,read_jsonl
    import os
    path=tmp_path/filename
    old={'id':1,'date':'2026-10-03','result':[1,2,3]}
    write_jsonl(path,[old])
    def blocked(*args): raise OSError('disk unavailable')
    monkeypatch.setattr(os,'replace',blocked)
    with pytest.raises(OSError): write_jsonl(path,[old,old|{'id':2}])
    assert read_jsonl(path)==[old]
    assert sorted(p.name for p in tmp_path.iterdir())==[filename]


def test_api_failed_startup_releases_storage_and_writer_lease(tmp_path):
    from fastapi.testclient import TestClient
    from vietlott_engine.api.main import create_app
    from vietlott_engine.core.config import Settings
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.updates.lease import WriterLease
    class Repository(InMemoryRepository):
        closed = False
        def close(self): self.closed = True
    repo = Repository()
    directory = tmp_path / 'updates'
    directory.mkdir()
    (directory / 'results.jsonl').write_text('{bad}\n')
    app = create_app(Settings(storage_backend='memory', data_dir=tmp_path, auto_update_enabled=True), repo)
    with pytest.raises(ValueError):
        with TestClient(app): pass
    with WriterLease(directory / 'writer.lock'): pass
    assert repo.closed


@pytest.mark.parametrize('worker_error', [False, True])
def test_cli_once_returns_failure_for_stale_results_or_failed_checkpoint(tmp_path,monkeypatch,capsys,worker_error):
    from vietlott_engine.core.config import Settings
    from vlm.updates.cli import main
    from vlm.updates.runner import UpdateRunner
    import vlm.updates.cli as cli
    import vlm.updates.service as service
    settings = Settings(storage_backend='memory', data_dir=tmp_path, seed_file_dir=None)
    monkeypatch.setattr(cli, 'get_settings', lambda: settings)
    async def update(product):
        return {'last_draw_id':1, 'last_draw_date':'2026-10-03' if worker_error else '2026-10-01',
                'draws_on_last_date':1, 'inserted':0}
    def make(state):
        runner = UpdateRunner(tmp_path / 'updates' / 'status.json', update, products=('power655',),
                              clock=lambda:datetime.fromisoformat('2026-10-03T19:00:00+07:00'))
        if worker_error:
            def save(): raise OSError('secret disk path')
            monkeypatch.setattr(runner, '_save', save)
        return runner
    monkeypatch.setattr(service, 'make_runner', make)
    assert main(['--once', '--product', 'power655']) == 1
    result = json.loads(capsys.readouterr().out)
    assert result['products']['power655']['freshness']['status'] == ('caught_up' if worker_error else 'behind_schedule')
    if worker_error: assert result['worker_error'] == 'OSError'
    else: assert (tmp_path / 'updates' / 'status.json').exists()
    assert 'secret' not in json.dumps(result)


@pytest.mark.parametrize('product', ['mega645', 'bingo18'])
@pytest.mark.parametrize('failure', ['open', 'fsync'])
def test_seed_only_old_correction_is_durable_before_cache_commit(tmp_path, monkeypatch, product, failure):
    """Lỗi journal không được đẩy correction khỏi baseline của lần thử lại."""
    from contextlib import asynccontextmanager
    import os
    import httpx
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.core.games import get_game
    from vietlott_engine.core.models import Draw
    from vietlott_engine.core.products import ProductCode
    from vietlott_engine.crawler.storage import InMemoryRepository
    import vlm.updates.service as service

    numbers = [1, 2, 3, 4, 5, 6] if product == 'mega645' else [1, 2, 3]
    old = {'id':1, 'date':'2026-09-30', 'result':numbers}
    latest = old | {'id':2, 'date':'2026-10-02'}
    corrected = old | {'result':numbers[:-1] + [7 if product == 'mega645' else 4]}
    settings = Settings(data_dir=tmp_path, product_seed_dir=tmp_path / 'empty-seed', ml_auto_update_enabled=False)
    repo = InMemoryRepository()
    state = AppState(settings, repo)
    if product == 'mega645':
        repo.upsert([Draw(game=product, draw_id=r['id'], draw_date=r['date'], numbers=r['result'])
                     for r in (old, latest)])
    else:
        state.product_store().upsert(ProductCode(product), [old, latest], 'seed')

    @asynccontextmanager
    async def client(_settings):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:_sync_response(product,(corrected,latest),request))) as c:
            yield c
    monkeypatch.setattr(service, 'build_http_client', client)

    def sync(target):
        if product == 'mega645':
            return asyncio.run(service.sync_matrix(target, get_game(product), source='github_mirror', full_refresh=True, learn=False))
        return asyncio.run(service.sync_product(target, ProductCode(product), source='vietlott', full=True, learn=False))

    def values(target):
        if product == 'mega645':
            return list(target.repository.load(product)[0].numbers)
        return target.product_store().load(product).values[0].tolist()

    with monkeypatch.context() as failed:
        if failure == 'open':
            real_open = os.open
            def refuse_journal(path, flags, *args, **kwargs):
                if os.fspath(path) == os.fspath(service.journal_path(state)):
                    raise OSError('journal unavailable')
                return real_open(path, flags, *args, **kwargs)
            failed.setattr(os, 'open', refuse_journal)
        else:
            failed.setattr(os, 'fsync', lambda fd:(_ for _ in ()).throw(OSError('journal unavailable')))
        with pytest.raises(OSError, match='journal unavailable'):
            sync(state)
    assert values(state) == old['result']

    # Không phụ thuộc hàng đợi RAM: tạo AppState mới rồi tải đúng nguồn lần nữa.
    retried = AppState(settings, repo)
    sync(retried)
    records = [json.loads(line) for line in service.journal_path(retried).read_text().splitlines()]
    assert next(row for row in reversed(records) if row['draw_id'] == 1)['winning_numbers'] == corrected['result']
    assert values(retried) == corrected['result']

    if product != 'mega645':
        for path in (tmp_path / 'products').iterdir():
            path.unlink()
    recovered = AppState(settings, InMemoryRepository())
    service.replay_results(recovered)
    assert values(recovered) == corrected['result']


def test_unchanged_keno_seed_is_not_copied_into_the_journal(tmp_path, monkeypatch):
    """Fast poll không được biến toàn lịch sử seed thành delta cần lưu bền."""
    from contextlib import asynccontextmanager
    import httpx
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.core.products import ProductCode
    from vietlott_engine.crawler.storage import InMemoryRepository
    import vlm.updates.service as service
    state = AppState(Settings(data_dir=tmp_path, product_seed_dir=tmp_path / 'empty-seed',
                              ml_auto_update_enabled=False), InMemoryRepository())
    rows = [{'id':i, 'date':day, 'result':list(range(1, 21))}
            for i, day in enumerate(('2026-09-30', '2026-10-01', '2026-10-02'), 1)]
    state.product_store().upsert(ProductCode.KENO, rows, 'seed')
    @asynccontextmanager
    async def client(_settings):
        text = ''.join(json.dumps(row) + '\n' for row in rows)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200, text=text))) as http:
            yield http
    monkeypatch.setattr(service, 'build_http_client', client)
    asyncio.run(service.sync_product(state, ProductCode.KENO, source='mirror', full=True, learn=False))
    path = service.journal_path(state)
    saved = path.read_text()
    assert [json.loads(line)['draw_id'] for line in saved.splitlines()] == [3]
    asyncio.run(service.sync_product(state, ProductCode.KENO, source='mirror', full=True, learn=False))
    assert path.read_text() == saved


def test_product_precommit_journal_excludes_invalid_and_newly_unconfirmed_rows(tmp_path, monkeypatch):
    """Hook không được lưu các dòng bị validation hoặc thông báo loại kỳ bỏ qua."""
    from contextlib import asynccontextmanager
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.core.products import ProductCode
    from vietlott_engine.crawler.product_store import ProductSyncPipeline
    from vietlott_engine.crawler.storage import InMemoryRepository
    import vlm.updates.service as service
    state = AppState(Settings(data_dir=tmp_path, product_seed_dir=tmp_path / 'empty-seed',
                              ml_auto_update_enabled=False), InMemoryRepository())
    async def fetch(pipe, *_args):
        pipe._pending_exclusions = [{'product':'bingo18', 'draw_id':2}]
        return [{'id':1, 'date':'2026-10-01', 'result':[1, 2, 3]},
                {'id':2, 'date':'2026-10-02', 'result':[1, 2, 3]},
                {'id':3, 'date':'2026-10-03', 'result':[7, 8, 9]}]
    @asynccontextmanager
    async def client(_settings):
        yield None
    monkeypatch.setattr(ProductSyncPipeline, 'fetch', fetch)
    monkeypatch.setattr(service, 'build_http_client', client)
    asyncio.run(service.sync_product(state, ProductCode.BINGO18, source='mirror', learn=False))
    records = [json.loads(line) for line in service.journal_path(state).read_text().splitlines()]
    assert [row['draw_id'] for row in records] == [1]
    assert state.product_store().load(ProductCode.BINGO18).draw_ids.tolist() == [1]


@pytest.mark.parametrize('product', ['mega645', 'bingo18'])
@pytest.mark.parametrize('restart', ['recover', 'conflict', 'torn'])
def test_durable_pending_correction_recovers_crash_before_cache_without_overriding_conflicts(
        tmp_path, monkeypatch, product, restart):
    """Crash sau journal phải phục hồi correction, chỉ khi cache còn đúng baseline."""
    from contextlib import asynccontextmanager
    import httpx
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.core.games import get_game
    from vietlott_engine.core.models import Draw
    from vietlott_engine.core.products import ProductCode
    from vietlott_engine.crawler.product_store import ProductStore
    from vietlott_engine.crawler.storage import InMemoryRepository
    import vlm.updates.service as service
    numbers = [1, 2, 3, 4, 5, 6] if product == 'mega645' else [1, 2, 3]
    rows = [{'id':1, 'date':'2026-09-30', 'result':numbers},
            {'id':2, 'date':'2026-10-02', 'result':numbers}]
    corrected = rows[0] | {'result':numbers[:-1] + [7 if product == 'mega645' else 4]}
    unrelated = rows[0] | {'result':numbers[:-1] + [8 if product == 'mega645' else 5]}
    settings = Settings(data_dir=tmp_path, product_seed_dir=tmp_path / 'empty-seed', ml_auto_update_enabled=False)
    repo = InMemoryRepository()
    state = AppState(settings, repo)
    def store(target, data):
        if product == 'mega645':
            target.repository.upsert([Draw(game=product, draw_id=r['id'], draw_date=r['date'], numbers=r['result']) for r in data])
        else:
            target.product_store().upsert(ProductCode(product), data, 'seed')
    def values(target):
        return list(target.repository.load(product)[0].numbers) if product == 'mega645' else target.product_store().load(product).values[0].tolist()
    store(state, rows)
    @asynccontextmanager
    async def client(_settings):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request:_sync_response(product,(corrected,rows[1]),request))) as http:
            yield http
    monkeypatch.setattr(service, 'build_http_client', client)
    def crash(*args, **kwargs):
        raise RuntimeError('crash before cache commit')
    with monkeypatch.context() as failed:
        if product == 'mega645':
            failed.setattr(repo, 'upsert', crash)
        else:
            failed.setattr(ProductStore, 'upsert', crash)
        with pytest.raises(RuntimeError, match='crash before cache commit'):
            if product == 'mega645':
                asyncio.run(service.sync_matrix(state, get_game(product), source='github_mirror', full_refresh=True, learn=False))
            else:
                asyncio.run(service.sync_product(state, ProductCode(product), source='vietlott', full=True, learn=False))
    assert values(state) == numbers
    if restart == 'conflict':
        store(state, [unrelated])
    restarted = AppState(settings, repo)
    if restart == 'torn':
        pending, = (tmp_path / 'updates').glob('pending-*.json')
        pending.write_text('{"records":[')
        with pytest.raises((ValueError, json.JSONDecodeError)):
            service.replay_results(restarted)
        assert pending.read_text() == '{"records":['
        assert values(restarted) == numbers
        return
    before = service.journal_path(state).read_text()
    service.replay_results(restarted)
    assert values(restarted) == (unrelated if restart == 'conflict' else corrected)['result']
    if restart == 'conflict':
        assert restarted.replay_conflicts
        assert list((tmp_path / 'updates').glob('pending-*.json'))
    else:
        assert not list((tmp_path / 'updates').glob('pending-*.json'))
        service.replay_results(restarted)
        assert service.journal_path(restarted).read_text() == before


def test_pending_outboxes_for_two_products_recover_independently_before_journal_creation(tmp_path):
    """Hai sản phẩm cùng dừng sau stage không được ghi đè outbox của nhau."""
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.core.products import ProductCode
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.database.schema import DrawRecord
    import vlm.updates.service as service
    settings = Settings(data_dir=tmp_path, product_seed_dir=tmp_path / 'empty-seed')
    state = AppState(settings, InMemoryRepository())
    records = [DrawRecord.from_legacy(product, {'id':1, 'date':'2026-10-02', 'result':numbers})
               for product, numbers in [('mega645',[1,2,3,4,5,6]), ('bingo18',[1,2,3])]]
    for record in records:
        service._stage_pending(state, [record], {})
    assert len(list((tmp_path / 'updates').glob('pending-*.json'))) == 2
    assert not service.journal_path(state).exists()
    restarted = AppState(settings, InMemoryRepository())
    assert service.replay_results(restarted) == 2
    assert restarted.repository.load('mega645')[0].numbers == (1,2,3,4,5,6)
    assert restarted.product_store().load(ProductCode.BINGO18).values.tolist() == [[1,2,3]]
    assert not list((tmp_path / 'updates').glob('pending-*.json'))


def test_pending_results_support_platforms_without_directory_fsync(tmp_path, monkeypatch):
    """Windows không có O_DIRECTORY vẫn phải ghi file bền và phục hồi được."""
    import os
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.database.schema import DrawRecord
    import vlm.updates.service as service
    monkeypatch.delattr(os, 'O_DIRECTORY', raising=False)
    settings = Settings(data_dir=tmp_path)
    state = AppState(settings, InMemoryRepository())
    record = DrawRecord.from_legacy('mega645', {'id':1, 'date':'2026-10-02', 'result':[1,2,3,4,5,6]})
    service._stage_pending(state, [record], {})
    restarted = AppState(settings, InMemoryRepository())
    service.replay_results(restarted)
    assert restarted.repository.load('mega645')[0].numbers == (1,2,3,4,5,6)
    assert not list((tmp_path / 'updates').glob('pending-*.json'))


def test_pending_is_retained_until_journal_fsync_succeeds_after_restart(tmp_path, monkeypatch):
    """Đọc được JSON đủ không thay cho fsync đã lỗi; không được xóa outbox sớm."""
    import os
    from vietlott_engine.api.deps import AppState
    from vietlott_engine.core.config import Settings
    from vietlott_engine.crawler.storage import InMemoryRepository
    from vlm.database.schema import DrawRecord
    import vlm.updates.service as service
    settings = Settings(data_dir=tmp_path)
    state = AppState(settings, InMemoryRepository())
    record = DrawRecord.from_legacy('mega645', {'id':1, 'date':'2026-10-02', 'result':[1,2,3,4,5,6]})
    service._stage_pending(state, [record], {})
    path = service.journal_path(state)
    real_fsync = os.fsync
    attempted = []
    def fail_only_journal(fd):
        if path.exists() and (os.fstat(fd).st_dev, os.fstat(fd).st_ino) == (path.stat().st_dev, path.stat().st_ino):
            attempted.append(fd)
            raise OSError('journal fsync failed')
        return real_fsync(fd)
    with monkeypatch.context() as failed:
        failed.setattr(os, 'fsync', fail_only_journal)
        with pytest.raises(OSError, match='journal fsync failed'):
            service._append(state, [record])
        assert path.read_text().endswith('\n')
        restarted = AppState(settings, InMemoryRepository())
        with pytest.raises(OSError, match='journal fsync failed'):
            service.replay_results(restarted)
    assert len(attempted) == 2
    assert list((tmp_path / 'updates').glob('pending-*.json'))
    journal_syncs = []
    def observe_fsync(fd):
        if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) == (path.stat().st_dev, path.stat().st_ino):
            journal_syncs.append(fd)
        return real_fsync(fd)
    monkeypatch.setattr(os, 'fsync', observe_fsync)
    restored = AppState(settings, InMemoryRepository())
    service.replay_results(restored)
    assert journal_syncs
    assert restored.repository.load('mega645')[0].numbers == (1,2,3,4,5,6)
    assert not list((tmp_path / 'updates').glob('pending-*.json'))
