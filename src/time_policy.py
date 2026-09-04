"""Canonical clock policy for Vietnamese lottery operations.

GitHub Actions cron expressions are always UTC.  All domain decisions, draw
cutoffs and user-facing timestamps use ``Asia/Ho_Chi_Minh`` (UTC+7).  Keeping
the policy in one module prevents a runner's local timezone from changing the
meaning of "today" or the latest completed draw.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


VIETNAM_TIMEZONE = "Asia/Ho_Chi_Minh"
VIETNAM_TZ = ZoneInfo(VIETNAM_TIMEZONE)
VIETNAM_UTC_OFFSET_HOURS = 7
DEFAULT_DRAW_CUTOFF = time(18, 35)


def now_vietnam() -> datetime:
    """Return an aware current timestamp in Vietnam time."""

    return datetime.now(VIETNAM_TZ)


def vietnam_date(now: datetime | None = None) -> date:
    """Return the calendar date in Vietnam, never the runner's local date."""

    current = now or now_vietnam()
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(VIETNAM_TZ).date()


def latest_complete_draw_date(
    *, now: datetime, cutoff: time = DEFAULT_DRAW_CUTOFF
) -> date:
    """Return the latest draw date expected to be complete at ``now``."""

    local = now.astimezone(VIETNAM_TZ) if now.tzinfo else now.replace(tzinfo=VIETNAM_TZ)
    target = local.date()
    if local.time().replace(tzinfo=None) < cutoff:
        target -= timedelta(days=1)
    return target


def utc_cron_for_vietnam(local_hour: int, local_minute: int) -> str:
    """Convert a Vietnam wall-clock time to a GitHub UTC cron expression."""

    if not (0 <= local_hour <= 23 and 0 <= local_minute <= 59):
        raise ValueError("Vietnam local time must be a valid HH:MM")
    total = local_hour * 60 + local_minute - VIETNAM_UTC_OFFSET_HOURS * 60
    total %= 24 * 60
    utc_hour, utc_minute = divmod(total, 60)
    return f"{utc_minute} {utc_hour} * * *"


def iso_local(now: datetime | None = None) -> str:
    """Render an aware Vietnam timestamp for public diagnostics."""

    current = (now or now_vietnam()).astimezone(VIETNAM_TZ)
    return current.isoformat(timespec="seconds")


def iso_utc(now: datetime | None = None) -> str:
    """Render an aware UTC timestamp for machine/audit fields."""

    current = (now or now_vietnam()).astimezone(UTC)
    return current.isoformat(timespec="seconds").replace("+00:00", "Z")
