from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections import defaultdict
from datetime import datetime

from vietlott_engine.core.games import GAMES, get_game
from vietlott_engine.core.models import Draw
from vietlott_engine.core.prizes import PrizeRecord
from vietlott_engine.core.products import ProductCode, history_to_rows
from vietlott_engine.crawler.pipeline import SyncPipeline, build_http_client, build_source
from vietlott_engine.crawler.product_store import ProductSyncPipeline, _prefer_prize_record, sync_canonical_prizes
from vietlott_engine.crawler.storage import DuckDBRepository
from vietlott_engine.forecast.schedule import VN
from vlm.database.schema import DrawRecord
from pydantic import ValidationError


def journal_path(state):
    return (state.settings.auto_update_dir or state.settings.data_dir / 'updates') / 'results.jsonl'


def _read_journal(path) -> list[DrawRecord]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    records, prefix = [], bytearray()
    for index, line in enumerate(lines):
        if not line.strip():
            prefix.extend(line)
            continue
        try:
            records.append(DrawRecord.model_validate_json(line))
        except ValidationError as exc:
            if index != len(lines)-1 or line.endswith(b'\n') or not any(e['type']=='json_invalid' for e in exc.errors()):
                raise
            quarantine = path.with_name(path.name + '.' + datetime.now(VN).strftime('%Y%m%dT%H%M%S%f') + '.corrupt')
            quarantine.write_bytes(line)
            with tempfile.NamedTemporaryFile('wb', dir=path.parent, delete=False) as out:
                name = out.name
                out.write(prefix)
                out.flush()
                os.fsync(out.fileno())
            try:
                os.replace(name, path)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
            return records
        prefix.extend(line)
    if raw and not raw.endswith(b'\n'):
        with path.open('ab') as out:
            out.write(b'\n')
            out.flush()
            os.fsync(out.fileno())
    return records


def _identity(record: DrawRecord) -> tuple:
    return (record.draw_date.date(), record.winning_numbers, record.bonus_number)


def _journal_identity(record: DrawRecord) -> tuple:
    sub = record.sub_prizes_json or {}
    finance = {key: getattr(record, key) for key in
               ('jackpot1_value', 'jackpot2_value', 'jackpot1_winners', 'jackpot2_winners')}
    finance.update({key: sub.get(key) for key in ('winners', 'field_sources', 'finance_source')})
    return (*_identity(record), json.dumps(finance, sort_keys=True))


def _fsync_directory(path):
    if os.name == 'nt' or not hasattr(os, 'O_DIRECTORY'):
        return
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _pending_path(state, product):
    return journal_path(state).parent / f'pending-{product}.json'


def _read_pending(path):
    raw = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(raw, dict) or raw.get('version') != 1 or not isinstance(raw.get('records'), list):
        raise ValueError('invalid pending results')
    records = {}
    for item in raw['records']:
        if not isinstance(item, dict) or set(item) != {'before','after'}:
            raise ValueError('invalid pending result')
        after = DrawRecord.model_validate(item['after'])
        before = DrawRecord.model_validate(item['before']) if item['before'] is not None else None
        key = (after.game_type, after.draw_id)
        if path.name != f'pending-{after.game_type.value}.json' or key in records or (
                before is not None and (before.game_type, before.draw_id) != key):
            raise ValueError('invalid pending result identity')
        records[key] = (before, after)
    return records


def _stage_pending(state, records, previous):
    changed = [r for r in records if previous.get((r.game_type,r.draw_id)) is None or
               _journal_identity(previous[(r.game_type,r.draw_id)]) != _journal_identity(r)]
    if not changed:
        return
    product = changed[0].game_type.value
    path = _pending_path(state, product)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = _read_pending(path) if path.exists() else {}
    for record in changed:
        key = (record.game_type,record.draw_id)
        before = previous.get(key)
        if key in pending:
            original, staged = pending[key]
            if not _matches_pending(before, original, staged):
                raise ValueError('pending result conflicts with cache')
        pending[key] = (before, record)
    payload = {'version':1, 'records':[{'before':before.model_dump(mode='json') if before else None,
                                      'after':after.model_dump(mode='json')}
                                     for before,after in pending.values()]}
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False, encoding='utf-8') as out:
            name = out.name
            json.dump(payload, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
        _fsync_directory(path.parent)
        _fsync_directory(path.parent.parent)
    finally:
        if name is not None and os.path.exists(name):
            os.unlink(name)


def _clear_pending(state, product):
    path = _pending_path(state, product)
    if path.exists():
        with journal_path(state).open('ab') as out:
            out.flush()
            os.fsync(out.fileno())
        path.unlink()
        _fsync_directory(path.parent)


def _matches_pending(cached, before, after):
    if cached is None:
        return True
    actual, target = _journal_identity(cached), _journal_identity(after)
    expected = _journal_identity(before) if before is not None else None
    if actual in (expected, target):
        return True
    if expected is not None and actual[:3] == target[:3]:
        baseline_finance = json.loads(expected[3])
        if baseline_finance['finance_source'] is None and baseline_finance['field_sources'] is None:
            intermediate_finance = json.loads(target[3])
            intermediate_finance.update(field_sources=None, finance_source=None)
            if actual[3] == json.dumps(intermediate_finance, sort_keys=True):
                return True
    if expected is None and actual[:3] == target[:3]:
        bare = _journal_identity(after.model_copy(update={
            'jackpot1_value':None, 'jackpot2_value':None, 'jackpot1_winners':None,
            'jackpot2_winners':None, 'sub_prizes_json':None}))[3]
        finance = json.loads(target[3])
        finance.update(field_sources=None, finance_source=None)
        return actual[3] in (bare, json.dumps(finance, sort_keys=True))
    return expected is not None and expected[:3] != target[:3] and (
        actual[:3] in (expected[:3], target[:3]) and actual[3] in (expected[3], target[3]))


def _replay_pending(state, product=None):
    directory = journal_path(state).parent
    paths = list(directory.glob('pending-*.json')) if product is None else [_pending_path(state, product)]
    pending = [(path,_read_pending(path)) for path in paths if path.exists()]
    pending_keys = set()
    for path, records in pending:
        code = path.name[len('pending-'):-len('.json')]
        if code in GAMES:
            current = {(r.game_type,r.draw_id):r for r in _matrix_records(state.repository, get_game(code))}
        else:
            history = state.product_store().load(ProductCode(code), include_unconfirmed=True)
            current = {(code,int(r['id'])):DrawRecord.from_legacy(code,r) for r in history_to_rows(history)}
        conflict = False
        for key, (before, after) in records.items():
            cached = current.get(key)
            if not _matches_pending(cached, before, after):
                state.replay_conflicts.append({'game_type':code, 'draw_id':after.draw_id})
                conflict = True
                continue
            _append(state, [after])
            if code in GAMES:
                if before is not None and _identity(before) != _identity(after):
                    state.repository.invalidate_finance(code, [after.draw_id])
                winners = dict((after.sub_prizes_json or {}).get('winners', {}))
                for tier in ('jackpot1','jackpot2'):
                    count = getattr(after, tier + '_winners')
                    if count is not None:
                        winners[tier] = count
                state.repository.upsert([Draw(game=code, draw_id=after.draw_id, draw_date=after.draw_date.date(),
                    numbers=after.winning_numbers, bonus=after.bonus_number, source=after.source,
                    jackpot1_value=after.jackpot1_value, jackpot2_value=after.jackpot2_value,
                    tier_winners=winners or None)])
                pots = {tier:getattr(after,tier+'_value') for tier in ('jackpot1','jackpot2')
                        if getattr(after,tier+'_value') is not None}
                if (winners or pots) and 'finance_source' in (after.sub_prizes_json or {}):
                    state.repository.upsert_prizes([PrizeRecord(game=code, draw_id=after.draw_id,
                        draw_date=after.draw_date.date(), winners=winners, jackpot_pots=pots or None,
                        source=(after.sub_prizes_json or {}).get('finance_source', after.source))])
                state.invalidate(get_game(code))
            else:
                state.product_store().upsert(ProductCode(code), [{'id':after.draw_id,
                    'date':after.draw_date.date().isoformat(), 'result':list(after.winning_numbers)}], after.source)
                state.invalidate_product(ProductCode(code))
        if not conflict:
            _clear_pending(state, code)
        else:
            pending_keys.update(records)
    return pending_keys


def _journal_index(state) -> dict:
    if state._journal_seen is None:
        state._journal_seen = {(r.game_type,r.draw_id):_journal_identity(r) for r in _read_journal(journal_path(state))}
    return state._journal_seen


def _product_baseline(history) -> dict:
    return {int(i):(str(day),tuple(values.tolist()))
            for i,day,values in zip(history.draw_ids,history.dates,history.values)}


def _product_records(code, history, baseline: dict, journal_ids: set[int], source: str,
                     *, keep_latest: bool = True) -> list[DrawRecord]:
    newest = str(history.dates.max()) if keep_latest and len(history) else None
    records = []
    for i, day, values in zip(history.draw_ids,history.dates,history.values):
        identity = (str(day),tuple(values.tolist()))
        if baseline.get(int(i)) != identity or identity[0] == newest or int(i) in journal_ids:
            records.append(DrawRecord.from_legacy(code.value, {'id':int(i), 'date':str(day),
                                                              'result':values.tolist(), 'source':source}))
    return records


def _append(state, records: list[DrawRecord], *, baseline: dict | None = None) -> None:
    if not records:
        return
    path = journal_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    _journal_index(state)
    if baseline is not None:
        newest = max(r.draw_date.date() for r in records)
        records = [r for r in records if baseline.get((r.game_type,r.draw_id)) != _journal_identity(r)
                   or r.draw_date.date() == newest or (r.game_type,r.draw_id) in state._journal_seen]
    records = [r for r in records if state._journal_seen.get((r.game_type,r.draw_id)) != _journal_identity(r)]
    if not records:
        return
    payload = ''.join(r.model_dump_json() + '\n' for r in records)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        with os.fdopen(fd, 'a', encoding='utf-8') as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
    except OSError:
        state._journal_seen = None
        raise
    state._journal_seen.update(((r.game_type,r.draw_id),_journal_identity(r)) for r in records)


def _matrix_record(draw: Draw, finance: PrizeRecord | None = None) -> DrawRecord:
    row = {'id':draw.draw_id, 'date':draw.draw_date.isoformat(),
        'result':list(draw.numbers), 'bonus_number':draw.bonus, 'source':draw.source,
        'jackpot1_value':draw.jackpot1_value, 'jackpot2_value':draw.jackpot2_value,
        'winners':draw.tier_winners or {}}
    if finance is not None and (finance.game, finance.draw_id, finance.draw_date) == (draw.game, draw.draw_id, draw.draw_date):
        row['winners'] = {**row['winners'], **finance.winners}
        fields = {}
        for tier, value in (finance.jackpot_pots or {}).items():
            row[tier + '_value'] = value
            fields[tier + '_value'] = finance.source
        row['sub_prizes_json'] = {'winners':row['winners'], 'field_sources':fields,
                                 'finance_source':finance.source}
    return DrawRecord.from_legacy(draw.game.value, row)


def _matrix_records(repository, spec) -> list[DrawRecord]:
    finance = {p.draw_id:p for p in repository.load_prizes(spec.code)}
    return [_matrix_record(d, finance.get(d.draw_id)) for d in repository.load(spec.code)]


def replay_results(state) -> int:
    pending_keys = _replay_pending(state)
    path = journal_path(state)
    if not path.exists():
        return 0
    records = {(r.game_type,r.draw_id):r for r in _read_journal(path)}
    products = defaultdict(list)
    matrix = []
    prizes = []
    existing = {spec.code.value:{d.draw_id:d for d in state.repository.load(spec.code)} for spec in GAMES.values()}
    for r in records.values():
        if (r.game_type,r.draw_id) in pending_keys:
            continue
        if r.game_type in GAMES:
            current = existing[r.game_type].get(r.draw_id)
            if current is not None:
                if _identity(_matrix_record(current)) != _identity(r):
                    state.replay_conflicts.append({'game_type':r.game_type, 'draw_id':r.draw_id})
                    continue
            winners = dict((r.sub_prizes_json or {}).get('winners', {}))
            for tier in ('jackpot1', 'jackpot2'):
                count = getattr(r, tier + '_winners')
                if count is not None:
                    winners[tier] = count
            recovered = Draw(game=r.game_type, draw_id=r.draw_id, draw_date=r.draw_date.date(),
                               numbers=tuple(r.winning_numbers), bonus=r.bonus_number, source=r.source,
                               jackpot1_value=r.jackpot1_value, jackpot2_value=r.jackpot2_value,
                               tier_winners=winners or None)
            if current is not None:
                recovered = current.model_copy(update={
                    'jackpot1_value':current.jackpot1_value if current.jackpot1_value is not None else recovered.jackpot1_value,
                    'jackpot2_value':current.jackpot2_value if current.jackpot2_value is not None else recovered.jackpot2_value,
                    'tier_winners':{**winners, **(current.tier_winners or {})} or None,
                })
            if recovered != current:
                matrix.append(recovered)
            pots = {tier:getattr(r, tier + '_value') for tier in ('jackpot1', 'jackpot2')
                    if getattr(r, tier + '_value') is not None}
            if winners or pots:
                cached = next((p for p in state.repository.load_prizes(r.game_type.value)
                               if p.draw_id == r.draw_id and p.draw_date == r.draw_date.date()), None)
                prize = PrizeRecord(game=r.game_type, draw_id=r.draw_id, draw_date=r.draw_date.date(),
                    winners=winners, jackpot_pots=pots or None,
                    source=(r.sub_prizes_json or {}).get('finance_source', r.source))
                prizes.append(_prefer_prize_record(prize, cached) if cached else prize)
        else:
            products[ProductCode(r.game_type)].append({'id':r.draw_id, 'date':r.draw_date.date().isoformat(),
                                                      'result':list(r.winning_numbers)})
    if matrix:
        state.repository.upsert(matrix)
        for product in {d.game for d in matrix}:
            state.invalidate(get_game(product))
    if prizes:
        state.repository.upsert_prizes(prizes)
    for product, rows in products.items():
        store = state.product_store()
        current = {row['id']:row for row in history_to_rows(store.load(product, include_unconfirmed=True))}
        missing = []
        for row in rows:
            if row['id'] not in current:
                missing.append(row)
            elif current[row['id']]['date'] != row['date'] or [int(n) for n in current[row['id']]['result']] != [int(n) for n in row['result']]:
                state.replay_conflicts.append({'game_type':product.value,'draw_id':row['id']})
        store.upsert(product, missing, 'updates-journal')
        state.invalidate_product(product)
    return len(records)


async def sync_matrix(state, spec, *, source: str | None = None, full_refresh: bool = False,
                      learn: bool = True) -> dict:
    async with state.sync_lock(spec.code.value):
        if _replay_pending(state, spec.code.value):
            raise ValueError('pending result conflicts with cache')
        previous = {(r.game_type,r.draw_id):r for r in _matrix_records(state.repository, spec)}
        before = {key:_journal_identity(r) for key,r in previous.items()}
        cached_draws = {d.draw_id:d for d in state.repository.load(spec.code)}
        cached_finance = {p.draw_id:p for p in state.repository.load_prizes(spec.code)}
        def persist_results(draws):
            records = []
            prepared = []
            for draw in draws:
                old_identity = before.get((draw.game.value, draw.draw_id))
                corrected = old_identity is not None and old_identity[:3] != _identity(_matrix_record(draw))
                if corrected:
                    draw = draw.model_copy(update={
                        'jackpot1_value':None, 'jackpot2_value':None, 'tier_winners':None})
                elif isinstance(state.repository, DuckDBRepository) and draw.draw_id in cached_draws:
                    cached = cached_draws[draw.draw_id]
                    draw = draw.model_copy(update={
                        'jackpot1_value':draw.jackpot1_value if draw.jackpot1_value is not None else cached.jackpot1_value,
                        'jackpot2_value':draw.jackpot2_value if draw.jackpot2_value is not None else cached.jackpot2_value,
                        'tier_winners':draw.tier_winners or cached.tier_winners})
                record = _matrix_record(draw, None if corrected else cached_finance.get(draw.draw_id))
                if old_identity != _journal_identity(record):
                    records.append(record)
                prepared.append(draw)
            _stage_pending(state, records, previous)
            _append(state, records)
            return prepared
        async with build_http_client(state.settings) as client:
            report = await SyncPipeline(build_source(state.settings, client, source), state.repository).run(
                spec, full_refresh, before_upsert=persist_results)
        changed = [d.draw_id for d in state.repository.load(spec.code)
                   if (d.game.value, d.draw_id) in before
                   and before[(d.game.value, d.draw_id)][:3] != _identity(_matrix_record(d))]
        if changed:
            state.repository.invalidate_finance(spec.code, changed)
            if isinstance(state.repository, DuckDBRepository) and state.repository.parquet_dir is not None:
                state.repository.export_parquet(spec.code)
        _append(state, _matrix_records(state.repository, spec), baseline=before)
        _clear_pending(state, spec.code.value)
        state.invalidate(spec)
    return {**report.to_dict(), 'learning':await _learn(state, spec.code.value) if learn else None}


async def sync_product(state, code, *, source: str = 'auto', max_pages: int | None = None, full: bool = False,
                       learn: bool = True) -> dict:
    async with state.sync_lock(code.value):
        if _replay_pending(state, code.value):
            raise ValueError('pending result conflicts with cache')
        s, store = state.settings, state.product_store()
        history = await asyncio.to_thread(store.load, code, include_unconfirmed=True)
        before = await asyncio.to_thread(_product_baseline, history)
        def persist_results(accepted, origin):
            records = _product_records(code, accepted, before, set(), origin, keep_latest=False)
            previous = {(code.value,r.draw_id):DrawRecord.from_legacy(code.value,
                {'id':r.draw_id,'date':before[r.draw_id][0],'result':before[r.draw_id][1]})
                for r in records if r.draw_id in before}
            _stage_pending(state, records, previous)
            _append(state, records)
        async with build_http_client(s) as client:
            pipe = ProductSyncPipeline(client, store, vietlott_base_url=s.vietlott_base_url,
                mirror_base_url=s.product_mirror_base_url, canonical_base_url=s.canonical_base_url,
                bootstrap_cookie=s.vietlott_cookie_bootstrap, pages_per_batch=s.max_concurrency,
                nhanaz_base_url=s.nhanaz_base_url, nhanaz_dir=s.nhanaz_dir, v130_dir=s.v130_dir,
                fallback_order=s.fallback_order, source_timeout_s=s.source_timeout_s,
                archive_timeout_s=s.archive_timeout_s)
            report = await pipe.run(code, source, max_pages or s.product_sync_max_pages, full,
                                    before_upsert=persist_results)
        h = await asyncio.to_thread(store.load, code)
        journal_ids = {i for (product,i) in _journal_index(state) if product == code.value}
        records = await asyncio.to_thread(_product_records, code, h, before, journal_ids, report.source_used or source)
        _append(state, records)
        _clear_pending(state, code.value)
        state.invalidate_product(code)
    return {**report.to_dict(), 'learning':await _learn(state, code.value) if learn else None}


async def _learn(state, product: str) -> dict:
    if not state.settings.ml_auto_update_enabled:
        return {'enabled':False, 'error':None}
    from vlm.forecast.service import refresh_models
    job = state._ml_jobs.get(product)
    if job is None:
        async def guarded_refresh():
            async with state.sync_lock(product):
                return await refresh_models(state, product)
        job = asyncio.create_task(guarded_refresh(), name=f'vlm-learn-{product}')
        state._ml_jobs[product] = job
        def done(task):
            if state._ml_jobs.get(product) is task:
                state._ml_jobs.pop(product, None)
            if not task.cancelled():
                task.exception()
        job.add_done_callback(done)
    try:
        return await asyncio.wait_for(asyncio.shield(job), state.settings.ml_learning_timeout_s)
    except TimeoutError:
        return {'enabled':True, 'error':'TimeoutError', 'pending':True}
    except Exception as exc:
        return {'enabled':True, 'error':type(exc).__name__}


async def finish_learning(state) -> None:
    if state._ml_jobs:
        await asyncio.gather(*list(state._ml_jobs.values()), return_exceptions=True)


async def update_product(state, product: str, *, learn: bool = True) -> dict:
    prize_error = None
    if product in GAMES:
        spec = get_game(product)
        report = await sync_matrix(state, spec, source='auto', learn=False)
        draws = state.repository.load(spec.code)
        last = max(draws, key=lambda d:d.draw_id) if draws else None
        last_date = last.draw_date.isoformat() if last else None
        count = sum(d.draw_date == last.draw_date for d in draws) if last else 0
        try:
            async with state.sync_lock(product):
                before = {(r.game_type, r.draw_id):_journal_identity(r) for r in _matrix_records(state.repository, spec)}
                def persist_finance(additions, accepted):
                    draws = {d.draw_id:d for d in state.repository.load(spec.code)}
                    draws.update((d.draw_id,d) for d in additions)
                    finance = {p.draw_id:p for p in accepted}
                    affected = set(finance) | {d.draw_id for d in additions}
                    records = [_matrix_record(draws[draw_id], finance.get(draw_id)) for draw_id in sorted(affected)]
                    previous = {(r.game_type,r.draw_id):r for r in _matrix_records(state.repository, spec)}
                    _stage_pending(state, records, previous)
                    _append(state, records)
                try:
                    async with build_http_client(state.settings) as client:
                        s = state.settings
                        finance = await asyncio.wait_for(sync_canonical_prizes(client, state.repository, spec,
                            source='auto', last=3, canonical_base_url=s.canonical_base_url,
                            vietlott_base_url=s.vietlott_base_url, bootstrap_cookie=s.vietlott_cookie_bootstrap,
                            nhanaz_base_url=s.nhanaz_base_url, nhanaz_dir=s.nhanaz_dir, v130_dir=s.v130_dir,
                            before_upsert=persist_finance), min(45, s.auto_update_timeout_s / 4))
                        prize_error = 'SourceError' if finance.error else None
                    _append(state, _matrix_records(state.repository, spec), baseline=before)
                    _clear_pending(state, product)
                finally:
                    state.invalidate(spec)
        except Exception as exc:
            prize_error = type(exc).__name__
        return {'last_draw_id':last.draw_id if last else None, 'last_draw_date':last_date,
                'draws_on_last_date':count, 'inserted':report['inserted'], 'source':report['source'], 'prize_error':prize_error,
                'learning':await _learn(state, product) if learn else None}
    code = ProductCode(product)
    report = await sync_product(state, code, learn=False)
    h = await asyncio.to_thread(state.product_store().load, code)
    count = int((h.dates == h.dates[-1]).sum()) if len(h) else 0
    return {'last_draw_id':report['last_id'], 'last_draw_date':report['last_date'], 'draws_on_last_date':count,
            'inserted':report['inserted'], 'source':report['source_used'], 'latest_source':report.get('latest_source'),
            'error':report['error'],
            'source_attempts':report['attempts'], 'continuity':report['continuity'],
            'learning':await _learn(state, product) if learn else None}


def make_runner(state):
    from vlm.updates.runner import UpdateRunner
    return UpdateRunner(journal_path(state).parent / 'status.json',
                        lambda product:update_product(state, product, learn=False),
                        learn=lambda product:_learn(state, product), timeout_s=state.settings.auto_update_timeout_s)


def update_status(state) -> dict:
    status = state.updater.status() if state.updater is not None else {'products':{}}
    return {'enabled':state.settings.auto_update_enabled, 'running':state.updater is not None, 'timezone':'Asia/Ho_Chi_Minh',
            'observed_at':datetime.now(VN).isoformat(), 'replay_conflicts':state.replay_conflicts, **status}
