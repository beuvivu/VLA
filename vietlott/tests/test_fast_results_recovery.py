"""Hồi quy sự cố Keno/Bingo18 ngày 19/10/2026; không gọi mạng thật."""
from __future__ import annotations

import asyncio
import json
import threading
import subprocess
import sys
from datetime import date, datetime, timedelta

import httpx
import pytest

from vietlott_engine.core.exceptions import SourceError
from vietlott_engine.core.products import ProductCode
from vietlott_engine.crawler.http import AsyncHttpClient, RetryPolicy
from vietlott_engine.crawler.product_store import ProductStore, ProductSyncPipeline
from vietlott_engine.forecast.schedule import VN as VN_TZ
from tests.test_fallback_sources import DRAW_COLS, _csv, _draw


def row(did, product=ProductCode.BINGO18):
    return {'id':did, 'date':date.today().isoformat(),
            'result':list(range(1,21)) if product == ProductCode.KENO else [1,2,3]}


def pipeline(store, client=None, **kwargs):
    return ProductSyncPipeline(client, store, vietlott_base_url='https://official.test',
        mirror_base_url='https://mirror.test', canonical_base_url='https://canonical.test',
        nhanaz_base_url='https://archive.test/datasets', **kwargs)


@pytest.mark.parametrize('status', [200,403,429,503])
def test_cloudflare_interstitial_is_never_data_or_retried(status):
    async def run():
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(status, text='<title>Just a moment...</title><script src="/cdn-cgi/challenge-platform/x"></script>',
                                  headers={'server':'cloudflare','content-type':'text/html'})
        async with AsyncHttpClient(transport=httpx.MockTransport(handler),
                                   retry=RetryPolicy(max_retries=2,base_delay=0)) as client:
            with pytest.raises(SourceError,match='not bypassed'):
                await client.get('https://official.test')
        assert len(calls)==1
    asyncio.run(run())


def test_large_store_reads_do_not_starve_other_product_deadlines(tmp_path):
    entered,pulse=threading.Event(),threading.Event()
    observations=[]
    class SlowStore(ProductStore):
        def load(self,*args,**kwargs):
            entered.set()
            observations.append(pulse.wait(2))
            return super().load(*args,**kwargs)
    class Source(ProductSyncPipeline):
        async def fetch(self,*args):
            return [row(1)]
    async def run():
        pipe=Source(None,SlowStore(tmp_path),vietlott_base_url='',mirror_base_url='',canonical_base_url='')
        async def heartbeat():
            while not entered.is_set():
                await asyncio.sleep(0)
            pulse.set()
        report,_=await asyncio.gather(pipe.run(ProductCode.BINGO18,'vietlott'),heartbeat())
        assert report.inserted==1
        assert observations and all(observations)
    asyncio.run(run())


def test_archive_retry_has_its_own_budget(tmp_path):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'seed')
    calls=[]
    record=_draw('bingo18','2',date.today().isoformat(),{'digits':[2,3,4]})
    record['validation_status']='valid'
    async def handler(request):
        if '/draws/' in request.url.path:
            calls.append(request)
            if len(calls)==1:
                raise httpx.ReadTimeout('transient',request=request)
            await asyncio.sleep(.05)
            return httpx.Response(200,text=_csv([record],DRAW_COLS))
        return httpx.Response(200,text='product,draw_id,draw_status\n')
    async def run():
        async with AsyncHttpClient(transport=httpx.MockTransport(handler),rate_limit_per_s=10000,
                burst=1000,retry=RetryPolicy(max_retries=1,base_delay=0)) as client:
            report=await pipeline(store,client,source_timeout_s=.03).run(ProductCode.BINGO18,'nhanaz')
        assert report.last_id==2
        assert report.inserted==1
        assert len(calls)==2
    asyncio.run(run())


@pytest.mark.parametrize('product',[ProductCode.KENO,ProductCode.BINGO18])
@pytest.mark.parametrize('fault',['pending','invalid','wrong_product','missing_status'])
def test_unverified_archive_rows_never_enter_live_store(tmp_path,product,fault):
    store=ProductStore(tmp_path)
    store.upsert(product,[row(1,product)],'seed')
    numbers={'numbers':list(range(1,21))} if product==ProductCode.KENO else {'digits':[2,3,4]}
    record=_draw(product.value,'2',date.today().isoformat(),numbers)
    record['validation_status']='valid'
    if fault=='pending':
        record['attributes_json']=json.dumps({'data_source':'xosominhngoc_net_vn','official_verification_status':'pending'})
    elif fault=='invalid':
        record['validation_status']='invalid'
    elif fault=='wrong_product':
        record['product']='mega645'
    else:
        record['draw_status']=''
    async def run():
        def handler(request):
            text=_csv([record],DRAW_COLS) if '/draws/' in request.url.path else 'product,draw_id,draw_status\n'
            return httpx.Response(200,text=text)
        async with AsyncHttpClient(transport=httpx.MockTransport(handler),rate_limit_per_s=10000,burst=1000) as client:
            report=await pipeline(store,client).run(product,'nhanaz')
        assert store.max_draw_id(product)==1
        assert report.error
        assert report.attempts[0]['rejected']>=1
    asyncio.run(run())


def test_fast_game_mirror_without_verification_cannot_advance_store(tmp_path):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'seed')
    async def run():
        async with AsyncHttpClient(transport=httpx.MockTransport(lambda request:
                httpx.Response(200,text=json.dumps(row(2))))) as client:
            report=await pipeline(store,client).run(ProductCode.BINGO18,'mirror')
        assert store.max_draw_id(ProductCode.BINGO18)==1
        assert report.error and 'verif' in report.error.lower()
    asyncio.run(run())


@pytest.mark.parametrize('fill_gap',[False,True])
def test_new_head_does_not_hide_a_missing_draw_and_fallback_can_fill_it(tmp_path,fill_gap):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'seed')
    asked=[]
    class Sources(ProductSyncPipeline):
        async def fetch(self,product,source,max_pages,full):
            asked.append(source)
            return [row(3)] if source=='vietlott' or not fill_gap else [row(2),row(3)]
    async def run():
        pipe=Sources(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='',
                     fallback_order=['vietlott','nhanaz'])
        report=await pipe.run(ProductCode.BINGO18)
        assert asked==['vietlott','nhanaz']
        assert store.max_draw_id(ProductCode.BINGO18)==(3 if fill_gap else 1)
        assert report.continuity['missing_ranges']==([] if fill_gap else [[2,2]])
        assert bool(report.error) is (not fill_gap)
    asyncio.run(run())


def test_announced_exclusion_is_not_a_missing_draw(tmp_path):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'seed')
    store.add_exclusions([{'product':'bingo18','draw_id':2,'draw_status':'not_confirmed'}])
    class Source(ProductSyncPipeline):
        async def fetch(self,*args):
            return [row(3)]
    report=asyncio.run(Source(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='').run(ProductCode.BINGO18,'vietlott'))
    assert report.last_id==3 and not report.error
    assert report.continuity['missing_ranges']==[]


def test_fallback_cannot_replace_known_results_with_conflicting_numbers(tmp_path):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'seed')
    class Source(ProductSyncPipeline):
        async def fetch(self,*args):
            return [dict(row(1),result=[6,6,6]),row(2)]
    report=asyncio.run(Source(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='').run(ProductCode.BINGO18,'nhanaz'))
    assert store.load(ProductCode.BINGO18).values[0].tolist()==[1,2,3]
    assert report.attempts[0]['conflicting_ids']==[1]


def test_runner_keeps_source_and_continuity_diagnostics_on_failure(tmp_path):
    from vlm.updates.runner import UpdateRunner
    async def update(product):
        return {'last_draw_id':1,'last_draw_date':date.today().isoformat(),'inserted':0,
                'error':'missing draws','source_attempts':[{'source':'nhanaz','error':'unverified'}],
                'continuity':{'missing_ranges':[[2,2]]}}
    async def run():
        runner=UpdateRunner(tmp_path/'status.json',update,products=('bingo18',))
        await runner.tick()
        entry=runner.status()['products']['bingo18']
        assert entry['source_attempts'][0]['error']=='unverified'
        assert entry['continuity']['missing_ranges']==[[2,2]]
        assert entry['error']
    asyncio.run(run())


def test_cancelled_writer_finishes_before_releasing_its_caller():
    from vietlott_engine.crawler.product_integrity import finish_store_write
    entered,release,finished=threading.Event(),threading.Event(),threading.Event()
    def write():
        entered.set()
        assert release.wait(3)
        finished.set()
    async def run():
        task=asyncio.create_task(finish_store_write(write))
        assert await asyncio.to_thread(entered.wait,1)
        try:
            task.cancel()
            await asyncio.sleep(.005)
            task.cancel()
            await asyncio.sleep(.005)
            assert not task.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
    asyncio.run(run())


def test_source_deadline_is_bounded_and_reported(tmp_path):
    class Blocked(ProductSyncPipeline):
        async def fetch(self,*args):
            await asyncio.Event().wait()
    async def run():
        pipe=Blocked(None,ProductStore(tmp_path),vietlott_base_url='',mirror_base_url='',
                     canonical_base_url='',source_timeout_s=.001,archive_timeout_s=.01)
        report=await pipe.run(ProductCode.BINGO18,'nhanaz')
        assert report.attempts[0]['timeout_s']==.01
        assert 'deadline exceeded' in report.attempts[0]['error']
        assert report.error and report.inserted==0
    asyncio.run(run())


def test_products_sync_cli_returns_failure_for_unverified_source(tmp_path,monkeypatch,capsys):
    from vietlott_engine.cli import main
    from vietlott_engine.core.config import get_settings
    monkeypatch.setenv('VQE_DATA_DIR',str(tmp_path/'data'))
    monkeypatch.setenv('VQE_PRODUCT_SEED_DIR',str(tmp_path/'seed'))
    get_settings.cache_clear()
    try:
        assert main(['products','sync','--product','bingo18','--source','mirror'])==1
        assert json.loads(capsys.readouterr().out)[0]['error']
    finally:
        get_settings.cache_clear()


def test_explicit_full_official_correction_still_runs_durable_precommit_hook(tmp_path):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1),row(2)],'seed')
    staged=[]
    class Official(ProductSyncPipeline):
        async def fetch(self,*args):
            return [dict(row(1),result=[2,3,4]),row(2)]
    report=asyncio.run(Official(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='').run(
        ProductCode.BINGO18,'vietlott',full=True,before_upsert=lambda history,source:staged.append(history.values.tolist())))
    assert not report.error
    assert staged==[[[2,3,4]]]
    assert store.load(ProductCode.BINGO18).values[0].tolist()==[2,3,4]


@pytest.mark.parametrize('fault',['future','backdated','invalid_values','conflict'])
def test_rejected_source_row_cannot_be_hidden_by_a_valid_cached_row(tmp_path,fault):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'seed')
    bad=row(2)
    # "Tương lai" là sau hôm nay GIỜ VIỆT NAM — đồng hồ engine dùng. date.today() của máy (UTC) chậm một ngày
    # từ 17:00 đến 24:00 UTC: khi ấy "ngày mai UTC" là "hôm nay VN", dòng hợp lệ và phép kiểm đỏ dù engine
    # đúng (31-10-2026, 22:29 UTC). Lùi ngày thì so với ngày của row(1), nên giữ đồng hồ máy.
    if fault=='future': bad['date']=(datetime.now(VN_TZ).date()+timedelta(days=1)).isoformat()
    elif fault=='backdated': bad['date']=(date.today()-timedelta(days=1)).isoformat()
    elif fault=='invalid_values': bad['result']=[7,8,9]
    else: bad=dict(row(1),result=[6,6,6])
    class Source(ProductSyncPipeline):
        async def fetch(self,*args):
            return [row(1),bad,row(2)] if fault=='conflict' else [row(1),bad]
    report=asyncio.run(Source(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='').run(ProductCode.BINGO18,'vietlott'))
    assert report.error
    assert report.inserted==0 and report.last_id==1


def test_asyncio_shutdown_drains_writer_without_spinning_forever():
    script='''
import asyncio,time
from vietlott_engine.crawler.product_integrity import finish_store_write
def write():
    time.sleep(.1)
async def main():
    asyncio.create_task(finish_store_write(write))
    await asyncio.sleep(.01)
asyncio.run(main())
print('shutdown complete')
'''
    result=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True,timeout=5)
    assert result.returncode==0, result.stderr
    assert 'shutdown complete' in result.stdout


def test_conflicting_duplicate_new_draw_is_not_silently_deduplicated(tmp_path):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'seed')
    class Source(ProductSyncPipeline):
        async def fetch(self,*args):
            return [row(2),dict(row(2),result=[6,6,6])]
    report=asyncio.run(Source(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='').run(ProductCode.BINGO18,'vietlott'))
    assert report.error
    assert report.last_id==1 and report.inserted==0


@pytest.mark.parametrize('filled',[False,True])
def test_historical_gaps_prevent_success_until_verified_rows_repair_them(tmp_path,filled):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1),row(3)],'seed')
    class Source(ProductSyncPipeline):
        async def fetch(self,*args):
            return [row(2),row(4)] if filled else [row(4)]
    report=asyncio.run(Source(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='').run(ProductCode.BINGO18,'vietlott'))
    assert bool(report.error) is (not filled)
    assert report.continuity['historical_missing_ranges']==([] if filled else [[2,2]])


def test_day_guard_uses_vietnam_day_even_on_a_utc_host(tmp_path,monkeypatch):
    import vietlott_engine.crawler.product_store as module
    day=date.today()
    class HostDate(date):
        @classmethod
        def today(cls): return day-timedelta(days=1)
    class VietnamDateTime(datetime):
        @classmethod
        def now(cls,tz=None): return datetime.combine(day,datetime.min.time(),tz)
    monkeypatch.setattr(module,'date',HostDate)
    monkeypatch.setattr(module,'datetime',VietnamDateTime,raising=False)
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'seed')
    class Source(ProductSyncPipeline):
        async def fetch(self,*args): return [row(2)]
    report=asyncio.run(Source(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='').run(ProductCode.BINGO18,'vietlott'))
    assert not report.error and report.last_id==2


@pytest.mark.parametrize('first_ids',[[4],[2]])
def test_auto_continues_after_a_new_head_with_old_gaps_or_a_stale_gap_repair(tmp_path,first_ids):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1),row(3)],'seed')
    asked=[]
    class Sources(ProductSyncPipeline):
        async def fetch(self,product,source,*args):
            asked.append(source)
            return [row(i) for i in first_ids] if source=='vietlott' else [row(2),row(4)]
    report=asyncio.run(Sources(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='',
        fallback_order=['vietlott','nhanaz']).run(ProductCode.BINGO18))
    assert asked==['vietlott','nhanaz']
    assert not report.error
    assert store.load(ProductCode.BINGO18).draw_ids.tolist()==[1,2,3,4]


@pytest.mark.parametrize('fault',['confirmed','wrong_origin','missing_status'])
def test_unverified_exclusion_cannot_certify_a_missing_draw(tmp_path,fault):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'seed')
    record=_draw('bingo18','3',date.today().isoformat(),{'digits':[1,2,3]})
    status='confirmed' if fault=='confirmed' else '' if fault=='missing_status' else 'not_confirmed'
    url='https://unverified.example/notice' if fault=='wrong_origin' else 'https://vietlott.vn/notice'
    async def run():
        def handler(request):
            text=_csv([record],DRAW_COLS) if '/draws/' in request.url.path else (
                f'product,draw_id,draw_status,effective_date,source_url\nbingo18,2,{status},{date.today()},{url}\n')
            return httpx.Response(200,text=text)
        async with AsyncHttpClient(transport=httpx.MockTransport(handler),rate_limit_per_s=10000,burst=1000) as client:
            report=await pipeline(store,client).run(ProductCode.BINGO18,'nhanaz')
        assert report.error
        assert report.last_id==1 and report.inserted==0
        assert 2 not in store.exclusions().get('bingo18',set())
    asyncio.run(run())


def test_archive_agreement_uses_an_already_verified_official_correction(tmp_path):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'seed')
    corrected=dict(row(1),result=[2,3,4])
    class Sources(ProductSyncPipeline):
        async def fetch(self,product,source,*args):
            return [corrected,row(3)] if source=='vietlott' else [corrected,row(2),row(3)]
    report=asyncio.run(Sources(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='',
        fallback_order=['vietlott','nhanaz']).run(ProductCode.BINGO18,full=True))
    assert not report.error and report.last_id==3
    assert store.load(ProductCode.BINGO18).values[0].tolist()==[2,3,4]


def test_verified_contiguous_prefix_is_saved_when_later_rows_are_invalid(tmp_path):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'seed')
    class Source(ProductSyncPipeline):
        async def fetch(self,*args):
            return [row(2),dict(row(3),result=[7,8,9]),row(4)]
    report=asyncio.run(Source(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='').run(ProductCode.BINGO18,'vietlott'))
    assert report.error
    assert report.inserted==1 and report.last_id==2
    assert store.load(ProductCode.BINGO18).draw_ids.tolist()==[1,2]


def test_legacy_cursor_is_not_relabelled_as_officially_verified_when_sources_fail(tmp_path):
    store=ProductStore(tmp_path)
    store.upsert(ProductCode.BINGO18,[row(1)],'existing-history')
    class Blocked(ProductSyncPipeline):
        async def fetch(self,*args): raise SourceError('blocked')
    report=asyncio.run(Blocked(None,store,vietlott_base_url='',mirror_base_url='',canonical_base_url='').run(ProductCode.BINGO18,'vietlott'))
    assert report.last_id==1
    assert report.continuity['latest_verified'] is None
