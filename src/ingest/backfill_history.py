from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from collections.abc import Callable, Iterable, Sequence

from core.atomic_io import atomic_write_text
from core.paths import REPO_ROOT

logger = logging.getLogger(__name__)

EARLIEST_SUPPORTED = date(2015, 1, 1)


@dataclass
class BackfillReport:

    requested: int = 0
    already_present: int = 0
    fetched: int = 0
    failed: list[date] = field(default_factory=list)
    checkpoints: int = 0
    elapsed_seconds: float = 0.0

    @property
    def attempted(self) -> int:
        return self.fetched + len(self.failed)

    @property
    def success_rate(self) -> float:
        return 1.0 if self.attempted == 0 else self.fetched / self.attempted

    def summary(self) -> str:
        return (
            f"yêu cầu {self.requested}, đã có {self.already_present}, "
            f"lấy mới {self.fetched}, hỏng {len(self.failed)}, "
            f"ghi {self.checkpoints} lần, {self.elapsed_seconds:.0f}s"
        )


def date_range(start: date, end: date) -> list[date]:
    if start > end:
        return []
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def missing_dates(wanted: Iterable[date], have: set[date]) -> list[date]:
    return sorted({d for d in wanted if d not in have}, reverse=True)


def _persist(lottery) -> None:
    lottery.generate_dataframes()
    lottery.dump()


def backfill(
    lottery,
    start: date,
    end: date,
    *,
    min_agreement: int = 1,
    checkpoint_every: int = 25,
    delay_range: tuple[float, float] = (1.5, 3.0),
    max_failures: int = 40,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> BackfillReport:
    if start > end:
        raise ValueError(f"start ({start}) phải trước hoặc bằng end ({end})")
    if start < EARLIEST_SUPPORTED:
        raise ValueError(
            f"start ({start}) sớm hơn mốc {EARLIEST_SUPPORTED} — "
            "các nguồn không còn lưu trữ đầy đủ trước mốc này"
        )
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every phải >= 1")
    if max_failures < 1:
        raise ValueError("max_failures phải >= 1")
    low, high = delay_range
    if low < 0 or high < low:
        raise ValueError("delay_range phải là (min>=0, max>=min)")

    began = clock()
    wanted = date_range(start, end)
    have = lottery.get_dates()
    todo = missing_dates(wanted, have)

    report = BackfillReport(
        requested=len(wanted),
        already_present=len(wanted) - len(todo),
    )
    logger.info(
        "Dải %s → %s: %d kỳ, đã có %d, cần lấy %d",
        start, end, report.requested, report.already_present, len(todo),
    )

    consecutive_failures = 0
    since_checkpoint = 0

    for index, day in enumerate(todo, start=1):
        try:
            ok = lottery.fetch(day, min_agreement=min_agreement)
        except Exception as exc:
            logger.debug("kỳ %s lỗi: %s", day, exc)
            ok = False

        if ok:
            report.fetched += 1
            since_checkpoint += 1
            consecutive_failures = 0
        else:
            report.failed.append(day)
            consecutive_failures += 1
            if consecutive_failures >= max_failures:
                logger.error(
                    "Dừng sớm: %d kỳ hỏng liên tiếp (tới %s). Nguồn nhiều khả "
                    "năng đã chặn hoặc đổi cấu trúc.",
                    consecutive_failures, day,
                )
                break

        if since_checkpoint >= checkpoint_every:
            _persist(lottery)
            report.checkpoints += 1
            since_checkpoint = 0
            logger.info(
                "Đã ghi %d/%d kỳ (%.0f%%)",
                report.fetched, len(todo), 100.0 * index / len(todo),
            )

        if index < len(todo):
            sleeper(random.uniform(low, high))

    if since_checkpoint > 0:
        _persist(lottery)
        report.checkpoints += 1

    report.elapsed_seconds = clock() - began
    logger.info("Xong: %s", report.summary())
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bổ sung lịch sử KQXS theo dải ngày.")
    parser.add_argument(
        "--merge-store",
        default=None,
        metavar="PATH",
        help=(
            "Hợp nhất một bản kho đã lưu vào data/xsmb.json rồi dựng lại các "
            "tệp dẫn xuất, sau đó thoát. Dùng khi nhánh chính đã tiến lên "
            "trong lúc backfill chạy."
        ),
    )
    parser.add_argument(
        "--drop-repeats",
        action="store_true",
        help=(
            "Loại các bản ghi trùng khít ngày liền trước rồi dựng lại kho, "
            "sau đó thoát. Đó là ngày XSMB không quay (Tết, giãn cách 2020) "
            "mà nguồn trả kết quả cũ."
        ),
    )
    parser.add_argument("--start", required=False, help="Ngày đầu YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="Ngày cuối YYYY-MM-DD (mặc định: hôm qua)")
    parser.add_argument("--min-agreement", type=int, default=1)
    parser.add_argument("--checkpoint-every", type=int, default=25)
    parser.add_argument("--delay-min", type=float, default=1.5)
    parser.add_argument("--delay-max", type=float, default=3.0)
    parser.add_argument("--max-failures", type=int, default=40)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from ingest.lottery import Lottery, vietnam_today

    if args.merge_store:
        root = REPO_ROOT
        canonical = root / "data" / "xsmb.json"
        merge_stores(Path(args.merge_store), canonical, canonical)
        merged = Lottery()
        merged.load()
        merged.dump()
        logger.info("Đã hợp nhất và dựng lại: %d kỳ", len(merged.get_dates()))
        return 0

    if args.drop_repeats:
        root = REPO_ROOT
        canonical = root / "data" / "xsmb.json"
        records = json.loads(canonical.read_text(encoding="utf-8"))
        drop = set(repeated_draw_dates(records))
        if not drop:
            logger.info("Không có kỳ trùng khít nào.")
            return 0
        kept = [r for r in records if str(r["date"])[:10] not in drop]
        atomic_write_text(canonical, json.dumps(kept, indent=2))
        cleaned = Lottery()
        cleaned.load()
        cleaned.generate_dataframes()
        cleaned.dump()
        logger.info(
            "Đã loại %d kỳ không quay (%s → %s); còn %d kỳ",
            len(drop), min(drop), max(drop), len(cleaned.get_dates()),
        )
        return 0

    if not args.start:
        parser.error("--start là bắt buộc khi không dùng --merge-store hoặc --drop-repeats")

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else vietnam_today() - timedelta(days=1)

    lottery = Lottery()
    lottery.load()
    before = len(lottery.get_dates())

    report = backfill(
        lottery,
        start,
        end,
        min_agreement=args.min_agreement,
        checkpoint_every=args.checkpoint_every,
        delay_range=(args.delay_min, args.delay_max),
        max_failures=args.max_failures,
    )

    after = len(lottery.get_dates())
    logger.info("Kho: %d → %d kỳ (+%d)", before, after, after - before)

    if report.attempted and report.fetched == 0:
        logger.error("Không lấy được kỳ nào trong %d lần thử.", report.attempted)
        return 1
    return 0


def repeated_draw_dates(records: Sequence[dict]) -> list[str]:
    def fingerprint(record: dict) -> tuple[str, ...]:
        return tuple(str(v) for k, v in sorted(record.items()) if k != "date")

    ordered = sorted(records, key=lambda r: str(r["date"])[:10])
    drop: list[str] = []
    seen: dict[tuple[str, ...], str] = {}
    for record in ordered:
        current = fingerprint(record)
        day = str(record["date"])[:10]
        if current in seen:
            drop.append(day)
        else:
            seen[current] = day
    return drop


def merge_stores(mine: Path, theirs: Path, out: Path) -> tuple[int, int, int]:
    def _load(path: Path) -> dict[str, dict]:
        if not path.exists():
            return {}
        rows = json.loads(path.read_text(encoding="utf-8"))
        return {str(row["date"]): row for row in rows}

    a, b = _load(mine), _load(theirs)
    merged = {**a, **b}
    ordered = [merged[k] for k in sorted(merged)]
    atomic_write_text(out, json.dumps(ordered, ensure_ascii=False))
    logger.info("hợp nhất: %d + %d -> %d bản ghi", len(a), len(b), len(ordered))
    return len(a), len(b), len(ordered)

if __name__ == "__main__":
    sys.exit(main())
