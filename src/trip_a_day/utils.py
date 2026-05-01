"""Shared utility helpers for trip-a-day."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def to_local_display(dt: datetime, timezone_str: str) -> str:
    """Convert a UTC datetime to a display string in the user's local timezone.

    Example output: "2026-04-26 05:00 CST"

    If *dt* has no tzinfo it is assumed to be UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    local_tz = ZoneInfo(timezone_str)
    local_dt = dt.astimezone(local_tz)
    abbr = local_dt.strftime("%Z")
    return local_dt.strftime(f"%Y-%m-%d %H:%M {abbr}")


def to_local_time_only(dt: datetime, timezone_str: str) -> str:
    """Compact display — time only, no date.  E.g., '05:00 CST'

    If *dt* has no tzinfo it is assumed to be UTC.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    local_tz = ZoneInfo(timezone_str)
    local_dt = dt.astimezone(local_tz)
    abbr = local_dt.strftime("%Z")
    return local_dt.strftime(f"%H:%M {abbr}")
