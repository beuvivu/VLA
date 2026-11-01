"""Cổng hồ sơ kiểm chứng của bản sao Keno/Bingo18 (01-11-2026); không gọi mạng thật.

Bản sao cộng đồng chỉ được nhập khi nó trùng tuyệt đối mọi kỳ chính thức của seed mà nó chồng lên
(đủ dài) VÀ mọi kỳ «trang đăng lại» độc lập của kho cộng đồng mà nó chồng lên (đủ nhiều). Mỗi phép
kiểm dưới đây đảo đúng một điều kiện và đòi kho không tiến.
"""
from __future__ import annotations

import asyncio
import gzip
import json

import httpx
import pytest

import vietlott_engine.crawler.product_store as product_store
from vietlott_engine.core.products import ProductCode
from vietlott_engine.crawler.http import AsyncHttpClient
from vietlott_engine.crawler.product_store import ProductStore, ProductSyncPipeline
from tests.test_fallback_sources import DRAW_COLS, _csv, _draw

OFFICIAL = 'vietlott.vn/list'
SEED_IDS = range(1, 13)        # 12 kỳ chính thức trong seed
NEW_IDS = range(13, 21)        # 8 kỳ mới chỉ bản sao có
CROSS_IDS = range(13, 18)      # 5 kỳ mới kho cộng đồng đăng lại từ trang thứ cấp


def digits(did: int) -> list[int]:
    return [did % 6 + 1, (did + 1) % 6 + 1, (did + 3) % 6 + 1]


def day(did: int) -> str:
    return f'2026-01-{did:02d}'


def write_seed(path, src=OFFICIAL):
    path.mkdir(parents=True, exist_ok=True)
    with gzip.open(path / 'bingo18.jsonl.gz', 'wt', encoding='utf-8') as fh:
        for did in SEED_IDS:
            fh.write(json.dumps({'id': did, 'date': day(did), 'result': digits(did), 'src': src}) + '\n')


def write_archive(root, override=None):
    folder = root / 'datasets' / 'draws' / 'bingo18'
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    for did in CROSS_IDS:
        value = (override or {}).get(did, digits(did))
        record = _draw('bingo18', f'{did:07d}', day(did), {'digits': value}, source='xosominhngoc_net_vn',
                       official_verification_status='pending')
        records.append(record)
    (folder / '2026-01.csv').write_text(_csv(records, DRAW_COLS), encoding='utf-8')
    (root / 'datasets' / 'exclusions.csv').write_text('product,draw_id,draw_status\n', encoding='utf-8')
    return root / 'datasets'


def mirror_text(override=None):
    lines = []
    for did in [*SEED_IDS, *NEW_IDS]:
        value = (override or {}).get(did, digits(did))
        lines.append(json.dumps({'date': day(did), 'id': f'{did:07d}', 'result': value}))
    return '\n'.join(lines) + '\n'


def sync(tmp_path, *, seed_src=OFFICIAL, mirror_override=None, archive_override=None, store_rows=False):
    seed = tmp_path / 'seed'
    if store_rows:
        write_seed(seed, src='nhanaz:xoso_com_vn_archive')
    else:
        write_seed(seed, src=seed_src)
    store = ProductStore(tmp_path / 'data', seed_dir=seed)
    if store_rows:
        # Dòng đã nằm trong kho không mang xuất xứ: đếm chúng là để bản sao tự chứng nhận.
        store.upsert(ProductCode.BINGO18, [{'id': d, 'date': day(d), 'result': digits(d)} for d in SEED_IDS], 'mirror')
    archive = write_archive(tmp_path / 'archive', archive_override)
    text = mirror_text(mirror_override)

    async def run():
        handler = lambda request: httpx.Response(200, text=text)  # noqa: E731
        async with AsyncHttpClient(transport=httpx.MockTransport(handler), rate_limit_per_s=10000, burst=1000) as client:
            pipe = ProductSyncPipeline(client, store, vietlott_base_url='https://official.test',
                                       mirror_base_url='https://mirror.test', canonical_base_url='https://canonical.test',
                                       nhanaz_dir=archive, fallback_order=['nhanaz', 'mirror'])
            return await pipe.run(ProductCode.BINGO18, 'auto')
    return store, asyncio.run(run())


@pytest.fixture(autouse=True)
def small_thresholds(monkeypatch):
    monkeypatch.setattr(product_store, 'MIRROR_TRACK_RECORD_MIN', 12)
    monkeypatch.setattr(product_store, 'MIRROR_CROSS_CHECK_MIN', 5)


def mirror_attempt(report):
    return next(a for a in report.attempts if a['source'] == 'mirror')


def test_a_mirror_with_a_clean_track_record_and_cross_check_fills_the_missing_draws(tmp_path):
    store, report = sync(tmp_path)
    assert store.max_draw_id(ProductCode.BINGO18) == 20
    assert report.source_used == 'mirror' and report.error is None
    audit = mirror_attempt(report)['audit']
    assert (audit['official_overlap'], audit['official_mismatches']) == (12, 0)
    assert (audit['cross_checked'], audit['cross_mismatches']) == (5, 0)
    loaded = store.load(ProductCode.BINGO18)
    assert loaded.values[-1].tolist() == digits(20)


@pytest.mark.parametrize('fault', ['official_mismatch', 'cross_mismatch', 'short_track', 'short_cross',
                                   'unofficial_seed', 'store_rows_self_certify'])
def test_the_mirror_is_refused_when_any_part_of_its_evidence_fails(tmp_path, monkeypatch, fault):
    kwargs = {}
    if fault == 'official_mismatch':
        kwargs['mirror_override'] = {5: [6, 6, 6]}
    elif fault == 'cross_mismatch':
        kwargs['archive_override'] = {15: [6, 6, 6]}
    elif fault == 'short_track':
        monkeypatch.setattr(product_store, 'MIRROR_TRACK_RECORD_MIN', 13)
    elif fault == 'short_cross':
        monkeypatch.setattr(product_store, 'MIRROR_CROSS_CHECK_MIN', 6)
    elif fault == 'unofficial_seed':
        kwargs['seed_src'] = 'nhanaz:xoso_com_vn_archive'
    else:
        kwargs['store_rows'] = True
    store, report = sync(tmp_path, **kwargs)
    assert store.max_draw_id(ProductCode.BINGO18) == 12
    attempt = mirror_attempt(report)
    assert not attempt['ok'] and 'unverified fast-game mirror' in attempt['error']
    assert report.error


@pytest.mark.parametrize('registered, expect_error', [([[6, 7]], False), ([[6, 6]], True), (None, True)])
def test_only_gaps_audited_as_absent_everywhere_stop_counting_as_sync_errors(tmp_path, registered, expect_error):
    """Khoảng hở 6–7 không nguồn nào có: nằm TRỌN trong sổ đã kiểm thì không đỏ; trùng một phần hay
    không có sổ thì vẫn là lỗi. Sổ không thêm kết quả nào và không làm kho tiến qua khoảng hở mới."""
    seed = tmp_path / 'seed'
    seed.mkdir()
    with gzip.open(seed / 'bingo18.jsonl.gz', 'wt', encoding='utf-8') as fh:
        for did in [*range(1, 6), *range(8, 11)]:
            fh.write(json.dumps({'id': did, 'date': day(did), 'result': digits(did), 'src': OFFICIAL}) + '\n')
    if registered is not None:
        (seed / 'known_gaps.json').write_text(json.dumps({'audited': '2026-11-01', 'products': {'bingo18': registered}}))
    store = ProductStore(tmp_path / 'data', seed_dir=seed)

    class Source(ProductSyncPipeline):
        async def fetch(self, product, source, max_pages, full):
            return [{'id': 11, 'date': day(11), 'result': digits(11)}]

    report = asyncio.run(Source(None, store, vietlott_base_url='https://official.test', mirror_base_url='https://m.test',
                                canonical_base_url='https://c.test').run(ProductCode.BINGO18, 'vietlott'))
    assert store.max_draw_id(ProductCode.BINGO18) == 11
    assert 6 not in store.load(ProductCode.BINGO18).draw_ids.tolist()
    assert bool(report.error) is expect_error
    assert ('historical verified draw gaps remain' in (report.error or '')) is expect_error


def _feb(did: int) -> str:
    return f'2026-01-{did:02d}' if did <= 31 else f'2026-02-{did - 31:02d}'


def test_a_later_sync_cross_checks_on_the_mirror_window_and_waits_for_newer_republished_draws(tmp_path):
    """Lượt production thứ hai ngày 01-11-2026: kho đã đuổi kịp bản sao, phần kho cộng đồng tải theo ngày của
    kho chỉ còn kỳ MỚI HƠN bản sao, nên phép đối chiếu cũ ra 0 và cổng từ chối mọi lượt sau. Cửa sổ nay neo
    theo ngày mới nhất của bản sao; kỳ đăng lại mới hơn là «chờ xác minh», không phải lỗi."""
    seed = tmp_path / 'seed'
    write_seed(seed)
    store = ProductStore(tmp_path / 'data', seed_dir=seed)
    store.upsert(ProductCode.BINGO18, [{'id': d, 'date': _feb(d), 'result': digits(d)} for d in range(13, 39)], 'mirror')
    folder = tmp_path / 'archive' / 'datasets' / 'draws' / 'bingo18'
    folder.mkdir(parents=True)
    def partition(ids):
        return _csv([_draw('bingo18', f'{d:07d}', _feb(d), {'digits': digits(d)}, source='xosominhngoc_net_vn',
                           official_verification_status='pending') for d in ids], DRAW_COLS)
    (folder / '2026-01.csv').write_text(partition(range(13, 31)), encoding='utf-8')
    (folder / '2026-02.csv').write_text(partition(range(41, 44)), encoding='utf-8')
    (tmp_path / 'archive' / 'datasets' / 'exclusions.csv').write_text('product,draw_id,draw_status\n', encoding='utf-8')
    text = '\n'.join(json.dumps({'date': _feb(d), 'id': f'{d:07d}', 'result': digits(d)}) for d in range(1, 41)) + '\n'

    async def run():
        handler = lambda request: httpx.Response(200, text=text)  # noqa: E731
        async with AsyncHttpClient(transport=httpx.MockTransport(handler), rate_limit_per_s=10000, burst=1000) as client:
            pipe = ProductSyncPipeline(client, store, vietlott_base_url='https://official.test',
                                       mirror_base_url='https://mirror.test', canonical_base_url='https://canonical.test',
                                       nhanaz_dir=tmp_path / 'archive' / 'datasets', fallback_order=['nhanaz', 'mirror'])
            return await pipe.run(ProductCode.BINGO18, 'auto')
    report = asyncio.run(run())
    assert store.max_draw_id(ProductCode.BINGO18) == 40
    assert mirror_attempt(report)['audit']['cross_checked'] == 18
    assert report.error is None
    assert report.continuity['awaiting_verification'] == 3
