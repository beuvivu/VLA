from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime
from pathlib import Path
from collections.abc import Sequence
from zoneinfo import ZoneInfo

import requests

from ingest.sources import (
    EXPECTED_COUNTS,
    PRIZE_ORDER,
    STALE_PAGE_ERROR,
    Source,
    default_sources,
    load_previous_draw,
    primary_has_failed,
    shows_previous_draw,
    source_consensus_partial,
)

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")

TOTAL_SLOTS = sum(EXPECTED_COUNTS.values())

DEFAULT_REQUEST_TIMEOUT = 8.0

USER_AGENTS: tuple[str, ...] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
)


def now_ict() -> datetime:
    return datetime.now(TZ)


def stamp(moment: datetime | None = None) -> str:
    moment = (moment or now_ict()).astimezone(TZ)
    return (
        f"{moment:%H:%M:%S} ICT "
        f"({moment.astimezone(ZoneInfo('UTC')):%H:%M:%S} UTC)"
    )


def build_session(user_agent: str | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent or random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )
    return session


class _TimeoutCappedSession:

    RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

    def __init__(
        self,
        inner: requests.Session,
        cap: float,
        *,
        max_attempts: int = 3,
        backoff_base: float = 0.5,
        backoff_cap: float = 4.0,
        sleeper=time.sleep,
    ) -> None:
        self.inner = inner
        self.cap = cap
        self.max_attempts = max(1, max_attempts)
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.sleeper = sleeper
        self.last_error: str | None = None
        self.last_status: int | None = None
        self.attempts = 0

    def _backoff_delay(self, attempt: int, response: object | None) -> float:
        delay = min(self.backoff_base * (2 ** (attempt - 1)), self.backoff_cap)
        headers = getattr(response, "headers", None) or {}
        raw = headers.get("Retry-After") if hasattr(headers, "get") else None
        if raw:
            try:
                delay = max(delay, float(raw))
            except (TypeError, ValueError):
                pass
        delay = min(delay, self.backoff_cap)
        return delay * random.uniform(0.5, 1.0)

    def get(self, url: str, timeout: int | float = 0, **kwargs: object) -> object:
        effective = self.cap if not timeout else min(float(timeout), self.cap)
        last_exc: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            self.attempts = attempt
            try:
                response = self.inner.get(url, timeout=effective, **kwargs)
            except Exception as exc:  # noqa: BLE001 - lỗi mạng là chuyện thường
                last_exc = exc
                self.last_error = f"{type(exc).__name__}: {str(exc)[:120]}"
                self.last_status = None
                if attempt < self.max_attempts:
                    self.sleeper(self._backoff_delay(attempt, None))
                    continue
                raise

            status = getattr(response, "status_code", None)
            self.last_status = status
            self.last_error = None if status == 200 else f"HTTP {status}"
            if status in self.RETRY_STATUS and attempt < self.max_attempts:
                self.sleeper(self._backoff_delay(attempt, response))
                continue
            return response

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("không thực hiện được lần thử nào")


@dataclass(frozen=True)
class PollConfig:

    target: date
    window_start: dtime = dtime(18, 15)
    deadline: dtime = dtime(19, 30)
    interval_seconds: tuple[float, float] = (60.0, 90.0)
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    min_agreement: int = 1
    max_rounds: int = 90
    max_attempts: int = 3
    previous_draw: dict[str, list[str]] | None = None

    def __post_init__(self) -> None:
        low, high = self.interval_seconds
        if low <= 0 or high < low:
            raise ValueError("interval_seconds phải là (min>0, max>=min)")
        if self.request_timeout <= 0:
            raise ValueError("request_timeout phải > 0")
        if self.min_agreement < 1:
            raise ValueError("min_agreement phải >= 1")
        if self.max_rounds < 1:
            raise ValueError("max_rounds phải >= 1")
        if self.max_attempts < 1:
            raise ValueError("max_attempts phải >= 1")
        worst_case = self.max_attempts * self.request_timeout
        if worst_case > self.interval_seconds[0]:
            raise ValueError(
                f"ngân sách thử lại {worst_case:.0f}s vượt chu kỳ thăm dò "
                f"{self.interval_seconds[0]:.0f}s"
            )

    def deadline_at(self) -> datetime:
        return datetime.combine(self.target, self.deadline, tzinfo=TZ)

    def window_start_at(self) -> datetime:
        return datetime.combine(self.target, self.window_start, tzinfo=TZ)


@dataclass
class PollOutcome:

    verified: bool
    verified_slots: int
    total_slots: int
    rounds: int
    prize_map: dict[str, list[str]]
    started_at: datetime
    finished_at: datetime
    source_stats: list[dict[str, object]] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, object]:
        return {
            "verified": self.verified,
            "verified_slots": self.verified_slots,
            "total_slots": self.total_slots,
            "rounds": self.rounds,
            "started_at_ict": self.started_at.isoformat(),
            "finished_at_ict": self.finished_at.isoformat(),
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "prize_map": self.prize_map,
            "source_stats": self.source_stats,
        }


def _fetch_one(
    source: Source,
    target: date,
    timeout: float,
    max_attempts: int = 3,
    previous: dict[str, list[str]] | None = None,
) -> tuple[str, dict[str, list[str]], str | None, int, int]:
    started = time.perf_counter()
    error: str | None = None
    prize_map: dict[str, list[str]] = {k: [] for k in PRIZE_ORDER}
    http = _TimeoutCappedSession(build_session(), timeout, max_attempts=max_attempts)
    try:
        prize_map = source.fetch_partial(target, http, live=True)
    except Exception as exc:  # noqa: BLE001 - phải nuốt mọi lỗi mạng
        error = f"{type(exc).__name__}: {str(exc)[:120]}"
    error = error or http.last_error
    if shows_previous_draw(prize_map, previous):
        prize_map = {k: [] for k in PRIZE_ORDER}
        error = STALE_PAGE_ERROR
    latency_ms = int(round((time.perf_counter() - started) * 1000.0))
    return source.name, prize_map, error, latency_ms, http.attempts


def poll_once(
    sources: Sequence[Source],
    target: date,
    *,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
    min_agreement: int = 1,
    max_attempts: int = 3,
    previous: dict[str, list[str]] | None = None,
) -> tuple[dict[str, list[str]], int, list[dict[str, object]]]:
    partials: list[tuple[int, str, dict[str, list[str]]]] = []
    stats: list[dict[str, object]] = []

    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as pool:
        futures = {
            pool.submit(_fetch_one, source, target, timeout, max_attempts, previous): priority
            for priority, source in enumerate(sources, start=1)
        }
        for future in as_completed(futures):
            priority = futures[future]
            name, prize_map, error, latency_ms, attempts = future.result()
            received = sum(len(prize_map.get(k, [])) for k in PRIZE_ORDER)
            partials.append((priority, name, prize_map))
            stats.append(
                {
                    "priority": priority,
                    "source": name,
                    "received_values": received,
                    "complete": received == TOTAL_SLOTS,
                    "latency_ms": latency_ms,
                    "attempts": attempts,
                    "error": error,
                }
            )

    partials.sort(key=lambda item: item[0])
    stats.sort(key=lambda item: item["priority"])

    merged, meta = source_consensus_partial(
        [(name, pmap) for _, name, pmap in partials],
        min_agreement=min_agreement,
    )
    verified_slots = int(meta.get("verified_slots", 0))
    return merged, verified_slots, stats


def poll_until_complete(
    config: PollConfig,
    *,
    sources: Sequence[Source] | None = None,
    sleeper=time.sleep,
    clock=now_ict,
) -> PollOutcome:
    sources = list(sources if sources is not None else default_sources())
    started = clock()
    deadline_at = config.deadline_at()
    window_at = config.window_start_at()

    if started < window_at:
        wait = (window_at - started).total_seconds()
        logger.info(
            "Còn %.0f phút mới tới khung quay %s; chờ. Bây giờ %s",
            wait / 60.0,
            config.window_start.strftime("%H:%M"),
            stamp(started),
        )
        sleeper(wait)

    merged: dict[str, list[str]] = {k: [] for k in PRIZE_ORDER}
    stats: list[dict[str, object]] = []
    verified_slots = 0
    rounds = 0
    best_slots = -1

    while rounds < config.max_rounds:
        now = clock()
        if now >= deadline_at and rounds > 0:
            logger.warning(
                "Hết hạn %s mà mới có %d/%d ô.",
                config.deadline.strftime("%H:%M"),
                verified_slots,
                TOTAL_SLOTS,
            )
            break

        rounds += 1
        poll = dict(
            timeout=config.request_timeout,
            min_agreement=config.min_agreement,
            max_attempts=config.max_attempts,
            previous=config.previous_draw,
        )
        if config.min_agreement > 1:
            merged, verified_slots, stats = poll_once(sources, config.target, **poll)
        else:
            merged, verified_slots, stats = poll_once(sources[:1], config.target, **poll)
            failed, _ = primary_has_failed(merged, target=config.target, now=clock())
            if failed and len(sources) > 1:
                merged, verified_slots, backup = poll_once(sources[1:], config.target, **poll)
                stats = stats + [{**row, "priority": row["priority"] + 1} for row in backup]

        if verified_slots != best_slots:
            live = sum(1 for s in stats if not s["error"])
            logger.info(
                "Vòng %d lúc %s: %d/%d ô đã xác minh, %d/%d nguồn trả lời.",
                rounds,
                stamp(clock()),
                verified_slots,
                TOTAL_SLOTS,
                live,
                len(sources),
            )
            best_slots = verified_slots

        if verified_slots >= TOTAL_SLOTS:
            logger.info(
                "Đủ %d ô sau %d vòng lúc %s — thoát ngay.",
                TOTAL_SLOTS,
                rounds,
                stamp(clock()),
            )
            break

        nap = random.uniform(*config.interval_seconds)
        remaining = (deadline_at - clock()).total_seconds()
        if remaining <= 0:
            break
        sleeper(min(nap, remaining))

    finished = clock()
    return PollOutcome(
        verified=verified_slots >= TOTAL_SLOTS,
        verified_slots=verified_slots,
        total_slots=TOTAL_SLOTS,
        rounds=rounds,
        prize_map=merged,
        started_at=started,
        finished_at=finished,
        source_stats=stats,
    )


def _parse_hhmm(value: str) -> dtime:
    try:
        hh, mm = value.split(":")
        return dtime(int(hh), int(mm))
    except Exception as exc:  # noqa: BLE001
        raise argparse.ArgumentTypeError(f"giờ không hợp lệ: {value!r}") from exc


def _write_github_output(outcome: PollOutcome) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"verified={'true' if outcome.verified else 'false'}\n")
        handle.write(f"verified_slots={outcome.verified_slots}\n")
        handle.write(f"rounds={outcome.rounds}\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Thăm dò tới khi đủ 27 ô kết quả XSMB được xác minh."
    )
    parser.add_argument("--date", default=None, help="Ngày quay YYYY-MM-DD (mặc định: hôm nay theo giờ VN)")
    parser.add_argument("--window-start", type=_parse_hhmm, default=dtime(18, 15))
    parser.add_argument("--deadline", type=_parse_hhmm, default=dtime(19, 30))
    parser.add_argument("--interval-min", type=float, default=60.0)
    parser.add_argument("--interval-max", type=float, default=90.0)
    parser.add_argument("--timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT)
    parser.add_argument("--min-agreement", type=int, default=1)
    parser.add_argument("--max-attempts", type=int, default=3,
                        help="Số lần thử mỗi yêu cầu (lùi mũ giữa các lần)")
    parser.add_argument("--json-out", default=None, help="Ghi tóm tắt JSON ra tệp")
    parser.add_argument(
        "--history", default="data/xsmb.csv",
        help="Sổ chuẩn; kỳ đã lưu gần nhất dùng để nhận ra nguồn còn hiện kỳ trước.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    target = date.fromisoformat(args.date) if args.date else now_ict().date()
    config = PollConfig(
        target=target,
        window_start=args.window_start,
        deadline=args.deadline,
        interval_seconds=(args.interval_min, args.interval_max),
        request_timeout=args.timeout,
        min_agreement=args.min_agreement,
        max_attempts=args.max_attempts,
        previous_draw=load_previous_draw(Path(args.history), before=target),
    )

    logger.info(
        "Bắt đầu thăm dò kỳ %s, khung %s-%s giờ VN, hạn mỗi yêu cầu %.1fs. Bây giờ %s",
        target.isoformat(),
        config.window_start.strftime("%H:%M"),
        config.deadline.strftime("%H:%M"),
        config.request_timeout,
        stamp(),
    )

    outcome = poll_until_complete(config)

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(outcome.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    _write_github_output(outcome)

    logger.info(
        "Kết thúc: %s — %d/%d ô sau %d vòng, %.0f giây.",
        "ĐỦ" if outcome.verified else "THIẾU",
        outcome.verified_slots,
        outcome.total_slots,
        outcome.rounds,
        outcome.elapsed_seconds,
    )
    return 0 if outcome.verified else 1


if __name__ == "__main__":
    sys.exit(main())
