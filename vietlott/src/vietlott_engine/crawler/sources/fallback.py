from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from vietlott_engine.core.exceptions import SourceError
from vietlott_engine.core.games import GameSpec
from vietlott_engine.core.logging import get_logger
from vietlott_engine.core.models import Draw
from vietlott_engine.core.products import ProductCode
from vietlott_engine.crawler.official_data import import_canonical
from vietlott_engine.crawler.sources.base import DrawSource, FetchResult

log = get_logger(__name__)


@dataclass
class Attempt:
    source: str
    ok: bool
    rows: int = 0
    error: str | None = None


@dataclass
class FallbackLog:
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def used(self) -> str | None:
        return next((a.source for a in self.attempts if a.ok), None)

    def to_list(self) -> list[dict]:
        return [a.__dict__ for a in self.attempts]


class ArchiveDrawSource(DrawSource):

    def __init__(self, archive=None, v130_dir=None) -> None:
        if (archive is None) == (v130_dir is None):
            raise ValueError("give exactly one of archive / v130_dir")
        self.archive = archive
        self.v130_dir = v130_dir
        self.name = "nhanaz" if archive is not None else "v130"
        self.last_records: list[dict] = []

    async def fetch(self, spec: GameSpec, since_id: int | None = None) -> FetchResult:
        product = ProductCode(spec.code.value)
        if self.archive is not None:
            got = await self.archive.draws(product)
        else:
            from vietlott_engine.crawler.sources.vqe130 import import_v130

            got = import_v130(self.v130_dir, product)
        records = [r for r in got.rows if since_id is None or int(r["draw_id"]) > since_id]
        self.last_records = records
        imp = import_canonical(records, spec.code)
        origin = {int(r["draw_id"]): r.get("data_source", "unknown") for r in records}
        draws = [d.model_copy(update={"source": f"{self.name}:{origin.get(d.draw_id, 'unknown')}"}) for d in imp.draws]
        res = FetchResult(draws=sorted(draws, key=lambda d: d.draw_id))
        res.rejected = [(str(r.get("draw_id")), r.get("error", "")) for r in imp.rejected + got.rejected]
        return res


class FallbackDrawSource(DrawSource):
    name = "auto"

    def __init__(self, sources: list[DrawSource], source_timeout_s: float = 20) -> None:
        if not sources:
            raise ValueError("no sources")
        self.sources = sources
        self.source_timeout_s = source_timeout_s
        self.log = FallbackLog()

    async def fetch(self, spec: GameSpec, since_id: int | None = None) -> FetchResult:
        self.log = FallbackLog()
        empty = None
        result: FetchResult | None = None
        pending: dict[int, tuple[Draw, int]] = {}
        rejected_by_attempt: dict[int, list[tuple[str, str]]] = {}
        used: list[str] = []
        for src in self.sources:
            cursor = result.draws[-1].draw_id if result is not None else since_id
            try:
                res = await asyncio.wait_for(src.fetch(spec, cursor), self.source_timeout_s)
            except (SourceError, OSError, KeyError, ValueError, TimeoutError) as exc:
                msg = (str(exc).splitlines() or [type(exc).__name__])[0][:300]
                log.warning("%s: source %s failed (%s); trying the next one", spec.code.value, src.name, msg)
                self.log.attempts.append(Attempt(src.name, False, error=msg))
                continue
            if since_id is not None:
                attempt_index = len(self.log.attempts)
                self.log.attempts.append(Attempt(src.name, False, error=f'no contiguous draws after #{cursor}'))
                rejected_by_attempt[attempt_index] = res.rejected
                if not res.draws:
                    empty = empty or res
                for draw in res.draws:
                    if draw.draw_id > cursor:
                        pending.setdefault(draw.draw_id, (draw, attempt_index))
                extra, nxt = [], cursor + 1
                while nxt in pending:
                    draw, origin = pending.pop(nxt)
                    extra.append(draw)
                    attempt = self.log.attempts[origin]
                    attempt.ok, attempt.error = True, None
                    attempt.rows += 1
                    nxt += 1
                if extra:
                    if result is None:
                        result = FetchResult()
                    result.draws += extra
                continue
            if result is None:
                if not res.draws:
                    self.log.attempts.append(Attempt(src.name, False, error='no newer draws'))
                    empty = empty or res
                    continue
                result = FetchResult(draws=sorted(res.draws, key=lambda d: d.draw_id), rejected=list(res.rejected))
                self.log.attempts.append(Attempt(src.name, True, rows=len(res.draws)))
                used.append(src.name)
                continue
            extra, nxt = [], result.draws[-1].draw_id + 1
            for draw in sorted(res.draws, key=lambda d: d.draw_id):
                if draw.draw_id < nxt:
                    continue
                if draw.draw_id != nxt:
                    break
                extra.append(draw)
                nxt += 1
            if extra:
                result.draws += extra
                result.rejected += res.rejected
                self.log.attempts.append(Attempt(src.name, True, rows=len(extra)))
                used.append(src.name)
            else:
                self.log.attempts.append(Attempt(src.name, False, error=f'no draws after #{nxt - 1}'))
        if result is not None:
            if since_id is not None:
                used = [attempt.source for attempt in self.log.attempts if attempt.ok]
                result.rejected = [item for index, rejected in rejected_by_attempt.items()
                                   if self.log.attempts[index].ok for item in rejected]
            self.name = "auto:" + "+".join(used)
            return result
        if pending:
            raise SourceError(f"all sources exhausted with missing draw #{since_id + 1}")
        if empty is not None:
            return empty
        raise SourceError("all sources failed: " + "; ".join(f"{a.source}: {a.error}" for a in self.log.attempts))
