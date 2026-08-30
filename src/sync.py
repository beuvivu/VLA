from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, time as dtime, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from lottery import Lottery


logger = logging.getLogger(__name__)


def latest_complete_draw_date(*, now: datetime, cutoff: dtime = dtime(18, 35)) -> datetime.date:
    """Return the latest draw date that should have complete results.

    XSMB is typically announced in the evening. If running before the cutoff time
    (default 18:35 local), we treat "today" as not finished yet.
    """
    last_date = now.date()
    if now.time() < cutoff:
        last_date -= timedelta(days=1)
    return last_date


def _daterange(start, end) -> Iterable:
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def ensure_up_to_date(
    *,
    lottery: Lottery,
    tz_name: str = "Asia/Ho_Chi_Minh",
    cutoff: dtime = dtime(18, 35),
    fill_missing_days_back: int = 365,
    polite_sleep_s: float = 0.15,
    max_retries: int = 2,
    retry_backoff_s: float = 0.8,
    consensus_min_recent: int = 2,
    consensus_recent_days: int = 2,
) -> list[datetime]:
    """Fetch missing draw dates and fill recent holes.

    Improvements:
    - Uses draw cutoff to avoid fetching incomplete "today".
    - Fills holes for the last N days (default 365).
    - Retries failed dates (common with flaky sources / anti-bot).
    """
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    target = latest_complete_draw_date(now=now, cutoff=cutoff)

    existing_dates = lottery.get_dates()
    existing_last = lottery.get_last_date() if existing_dates else (target - timedelta(days=fill_missing_days_back))

    missing_set: set = set()

    # 1) Always fetch forward from the latest stored date.
    if existing_last < target:
        for d in _daterange(existing_last + timedelta(days=1), target):
            if d not in existing_dates:
                missing_set.add(d)

    # 2) Also fill any holes within a recent window.
    hole_start = target - timedelta(days=fill_missing_days_back)
    for d in _daterange(hole_start, target):
        if d not in existing_dates:
            missing_set.add(d)

    missing = sorted(missing_set)
    if not missing:
        logger.info("No new/missing dates to fetch (latest stored: %s, target: %s)", existing_last, target)
        lottery.generate_dataframes()
        lottery.dump()
        return []

    fetched: list[datetime] = []
    for d in missing:
        logger.info("Fetching: %s", d)
        had_before = lottery.has_date(d)

        ok = False
        for attempt in range(1, max_retries + 1):
            age_days = max(0, (target - d).days)
            min_agreement = consensus_min_recent if age_days <= consensus_recent_days else 1
            lottery.fetch(d, min_agreement=min_agreement)
            if lottery.has_date(d):
                ok = True
                break
            sleep_s = retry_backoff_s * attempt
            logger.warning("No data for %s (attempt %d/%d). Sleep %.1fs then retry.", d, attempt, max_retries, sleep_s)
            time.sleep(sleep_s)

        if not ok:
            logger.warning("No source returned data for %s (will retry in next run)", d)

        if (not had_before) and lottery.has_date(d):
            fetched.append(datetime(d.year, d.month, d.day, tzinfo=tz))

        time.sleep(polite_sleep_s)

    lottery.generate_dataframes()
    lottery.dump()
    return fetched


def _parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def main() -> None:
    ap = argparse.ArgumentParser(description="Sync XSMB data with retries + hole filling.")
    ap.add_argument("--tz", default="Asia/Ho_Chi_Minh")
    ap.add_argument("--cutoff", default="18:35", help="Draw cutoff local time (HH:MM).")
    ap.add_argument("--fill-missing-days-back", type=int, default=365)
    ap.add_argument("--max-retries", type=int, default=2)
    ap.add_argument("--retry-backoff-s", type=float, default=0.8)
    ap.add_argument("--consensus-min-recent", type=int, default=2, help="Sources that must agree for recent/final draws.")
    ap.add_argument("--consensus-recent-days", type=int, default=2, help="Apply consensus to target date and this many prior days.")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    lot = Lottery()
    # Always load the committed history before fetching. Without this step a
    # scheduled run would start from an empty in-memory store and could overwrite
    # the repository history with only the recent fill window.
    lot.load()
    fetched = ensure_up_to_date(
        lottery=lot,
        tz_name=args.tz,
        cutoff=_parse_hhmm(args.cutoff),
        fill_missing_days_back=args.fill_missing_days_back,
        max_retries=args.max_retries,
        retry_backoff_s=args.retry_backoff_s,
        consensus_min_recent=args.consensus_min_recent,
        consensus_recent_days=args.consensus_recent_days,
    )
    if fetched:
        logger.info("Fetched %d date(s). Latest now: %s", len(fetched), lot.get_last_date())


if __name__ == "__main__":
    main()
