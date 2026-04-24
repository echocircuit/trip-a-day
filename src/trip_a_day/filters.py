"""Composable destination filters for Phase 6.

Each filter takes the current pool and returns a (possibly smaller) subset.
Filters are applied in order; if the combined result is empty the caller
falls back to the unfiltered pool and sets filter_fallback=True.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy.orm import Session

from trip_a_day.db import Destination, Trip
from trip_a_day.fetcher import haversine_miles


def apply_destination_filters(
    pool: list[Destination],
    session: Session,
    prefs: dict[str, str],
) -> tuple[list[Destination], bool]:
    """Apply all configured filters to *pool*.

    Returns ``(filtered_pool, filter_fallback)`` where ``filter_fallback``
    is True when every filter combined would have produced an empty pool and
    the original unfiltered pool was returned instead.
    """
    filtered = pool

    filtered = _filter_region_allowlist(filtered, prefs)
    filtered = _filter_region_blocklist(filtered, prefs)
    filtered = _filter_favorite_radius(filtered, session, prefs)
    filtered = _filter_exclude_previously_selected(filtered, session, prefs)
    filtered = _filter_exclude_booked(filtered, prefs)

    if not filtered:
        return pool, True
    return filtered, False


# ---------------------------------------------------------------------------
# Individual filter functions
# ---------------------------------------------------------------------------


def _parse_json_list(prefs: dict[str, str], key: str) -> list:
    raw = prefs.get(key, "[]")
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _filter_region_allowlist(
    pool: list[Destination], prefs: dict[str, str]
) -> list[Destination]:
    allowlist = _parse_json_list(prefs, "region_allowlist")
    if not allowlist:
        return pool
    allowed = {r.strip() for r in allowlist}
    return [d for d in pool if (d.region or "Other") in allowed]


def _filter_region_blocklist(
    pool: list[Destination], prefs: dict[str, str]
) -> list[Destination]:
    blocklist = _parse_json_list(prefs, "region_blocklist")
    if not blocklist:
        return pool
    blocked = {r.strip() for r in blocklist}
    return [d for d in pool if (d.region or "Other") not in blocked]


def _filter_favorite_radius(
    pool: list[Destination],
    session: Session,
    prefs: dict[str, str],
) -> list[Destination]:
    radius = int(prefs.get("favorite_radius_miles", "0") or "0")
    if radius <= 0:
        return pool

    # Use destinations marked as favorites (user_favorited=True) for their coordinates.
    favorited = (
        session.query(Destination).filter(Destination.user_favorited.is_(True)).all()
    )
    anchors = [
        (d.latitude, d.longitude)
        for d in favorited
        if d.latitude is not None and d.longitude is not None
    ]
    if not anchors:
        return pool

    def _within_radius(dest: Destination) -> bool:
        if dest.latitude is None or dest.longitude is None:
            return False
        return any(
            haversine_miles(lat, lon, dest.latitude, dest.longitude) <= radius
            for lat, lon in anchors
        )

    return [d for d in pool if _within_radius(d)]


def _filter_exclude_previously_selected(
    pool: list[Destination],
    session: Session,
    prefs: dict[str, str],
) -> list[Destination]:
    if prefs.get("exclude_previously_selected", "false").lower() != "true":
        return pool

    days = int(prefs.get("exclude_previously_selected_days", "0") or "0")
    query = session.query(Trip.destination_iata).filter(Trip.selected.is_(True))
    if days > 0:
        cutoff = date.today() - timedelta(days=days)
        query = query.filter(Trip.run_date >= cutoff)

    excluded_iatas = {row[0] for row in query.all()}
    return [d for d in pool if d.iata_code not in excluded_iatas]


def _filter_exclude_booked(
    pool: list[Destination], prefs: dict[str, str]
) -> list[Destination]:
    if prefs.get("exclude_booked", "false").lower() != "true":
        return pool
    return [d for d in pool if not d.user_booked]
