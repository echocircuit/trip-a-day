"""Destination selection strategies for the daily batch."""

from __future__ import annotations

import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from trip_a_day.db import Destination, Preference, Trip

# Human-readable labels for each strategy (used in the UI dropdown).
STRATEGY_LABELS: dict[str, str] = {
    "least_recently_queried": "Least Recently Queried (default)",
    "random": "Random",
    "round_robin": "Round Robin (sequential by IATA)",
    "maximize_short_term_region_variety": "Maximize Region Variety (this batch)",
    "maximize_long_term_region_variety": "Maximize Region Variety (recent history)",
    "cycle_through_regions": "Cycle Through Regions",
    "proportional_by_region": "Proportional by Region",
    "favorites_first": "Favorites First",
}

STRATEGIES = list(STRATEGY_LABELS.keys())


def select_daily_batch(
    strategy: str,
    batch_size: int,
    session: Session,
) -> list[Destination]:
    """Return up to *batch_size* enabled, non-excluded destinations using *strategy*."""
    fn = _STRATEGY_MAP.get(strategy, _least_recently_queried)
    return fn(batch_size, session)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _enabled_pool(session: Session) -> list[Destination]:
    """All enabled, non-excluded destinations."""
    return (
        session.query(Destination)
        .filter(Destination.enabled.is_(True), Destination.excluded.is_(False))
        .all()
    )


def _least_recently_queried(batch_size: int, session: Session) -> list[Destination]:
    """Sort by last_queried_at ASC (NULLs first — never queried destinations first)."""
    return (
        session.query(Destination)
        .filter(Destination.enabled.is_(True), Destination.excluded.is_(False))
        .order_by(
            Destination.last_queried_at.is_(None).desc(),
            Destination.last_queried_at.asc(),
        )
        .limit(batch_size)
        .all()
    )


def _random(batch_size: int, session: Session) -> list[Destination]:
    pool = _enabled_pool(session)
    return random.sample(pool, min(batch_size, len(pool)))


def _round_robin(batch_size: int, session: Session) -> list[Destination]:
    pool = (
        session.query(Destination)
        .filter(Destination.enabled.is_(True), Destination.excluded.is_(False))
        .order_by(Destination.iata_code)
        .all()
    )
    if not pool:
        return []

    offset_pref = session.get(Preference, "round_robin_offset")
    offset = int(offset_pref.value or "0") if offset_pref else 0
    pool_size = len(pool)
    offset = offset % pool_size

    selected: list[Destination] = []
    for i in range(batch_size):
        selected.append(pool[(offset + i) % pool_size])

    new_offset = (offset + batch_size) % pool_size
    if offset_pref:
        offset_pref.value = str(new_offset)
    else:
        from trip_a_day.db import Preference as Pref

        session.add(Pref(key="round_robin_offset", value=str(new_offset)))
    session.flush()
    return selected


def _maximize_short_term_region_variety(
    batch_size: int, session: Session
) -> list[Destination]:
    """Maximise distinct regions in this batch; within each region pick LRQ."""
    pool = _enabled_pool(session)
    if not pool:
        return []

    # Group pool by region.
    by_region: dict[str, list[Destination]] = {}
    for d in pool:
        r = d.region or "Other"
        by_region.setdefault(r, []).append(d)

    # Sort each region's destinations by last_queried_at (NULLs first).
    def _lrq_key(d: Destination) -> tuple:
        return (d.last_queried_at is not None, d.last_queried_at or 0)

    for r in by_region:
        by_region[r].sort(key=_lrq_key)

    regions = list(by_region.keys())
    random.shuffle(regions)

    selected: list[Destination] = []
    region_idx = 0
    while len(selected) < batch_size and any(by_region[r] for r in regions):
        r = regions[region_idx % len(regions)]
        if by_region[r]:
            selected.append(by_region[r].pop(0))
        region_idx += 1
    return selected


def _maximize_long_term_region_variety(
    batch_size: int, session: Session
) -> list[Destination]:
    """Bias toward regions least featured in the last 14 days of trips."""
    cutoff = date.today() - timedelta(days=14)
    recent_trips = (
        session.query(Trip.destination_iata).filter(Trip.run_date >= cutoff).all()
    )
    recent_iatas = {t[0] for t in recent_trips}

    # Map recent destination IATAs to their regions.
    region_recent_count: dict[str, int] = {}
    if recent_iatas:
        recent_dests = (
            session.query(Destination)
            .filter(Destination.iata_code.in_(recent_iatas))
            .all()
        )
        for d in recent_dests:
            r = d.region or "Other"
            region_recent_count[r] = region_recent_count.get(r, 0) + 1

    pool = _enabled_pool(session)
    if not pool:
        return []

    # Score destinations: lower recent count = higher priority.
    def _score(d: Destination) -> tuple:
        r = d.region or "Other"
        return (
            region_recent_count.get(r, 0),
            d.last_queried_at is not None,
            d.last_queried_at or 0,
        )

    pool.sort(key=_score)
    return pool[:batch_size]


def _cycle_through_regions(batch_size: int, session: Session) -> list[Destination]:
    """All batch_size slots from the current region; advance region on each call."""
    pool = _enabled_pool(session)
    if not pool:
        return []

    regions = sorted({d.region or "Other" for d in pool})
    if not regions:
        return _least_recently_queried(batch_size, session)

    idx_pref = session.get(Preference, "region_cycle_index")
    idx = int(idx_pref.value or "0") if idx_pref else 0
    idx = idx % len(regions)
    current_region = regions[idx]

    region_dests = [d for d in pool if (d.region or "Other") == current_region]
    region_dests.sort(
        key=lambda d: (d.last_queried_at is not None, d.last_queried_at or 0)
    )

    new_idx = (idx + 1) % len(regions)
    if idx_pref:
        idx_pref.value = str(new_idx)
    else:
        from trip_a_day.db import Preference as Pref

        session.add(Pref(key="region_cycle_index", value=str(new_idx)))
    session.flush()

    return region_dests[:batch_size]


def _proportional_by_region(batch_size: int, session: Session) -> list[Destination]:
    """Allocate slots proportionally across regions by destination count."""
    pool = _enabled_pool(session)
    if not pool:
        return []

    total = len(pool)
    by_region: dict[str, list[Destination]] = {}
    for d in pool:
        r = d.region or "Other"
        by_region.setdefault(r, []).append(d)

    def _lrq_key(d: Destination) -> tuple:
        return (d.last_queried_at is not None, d.last_queried_at or 0)

    for r in by_region:
        by_region[r].sort(key=_lrq_key)

    # Proportional floor allocation.
    slots: dict[str, int] = {
        r: max(0, int(batch_size * len(dests) / total))
        for r, dests in by_region.items()
    }
    remainder = batch_size - sum(slots.values())

    # Distribute remainder to regions with the largest fractional parts.
    fractional = sorted(
        by_region.keys(),
        key=lambda r: (batch_size * len(by_region[r]) / total) - slots[r],
        reverse=True,
    )
    for r in fractional[:remainder]:
        slots[r] += 1

    selected: list[Destination] = []
    for r, n in slots.items():
        selected.extend(by_region[r][:n])
    return selected[:batch_size]


def _favorites_first(batch_size: int, session: Session) -> list[Destination]:
    """All favorited destinations first, then fill with LRQ."""
    favorites = (
        session.query(Destination)
        .filter(
            Destination.enabled.is_(True),
            Destination.excluded.is_(False),
            Destination.user_favorited.is_(True),
        )
        .all()
    )
    selected = list(favorites[:batch_size])
    if len(selected) < batch_size:
        remaining = batch_size - len(selected)
        fav_iatas = {d.iata_code for d in selected}
        fill = (
            session.query(Destination)
            .filter(
                Destination.enabled.is_(True),
                Destination.excluded.is_(False),
                ~Destination.iata_code.in_(fav_iatas),
            )
            .order_by(
                Destination.last_queried_at.is_(None).desc(),
                Destination.last_queried_at.asc(),
            )
            .limit(remaining)
            .all()
        )
        selected.extend(fill)
    return selected


_STRATEGY_MAP = {
    "least_recently_queried": _least_recently_queried,
    "random": _random,
    "round_robin": _round_robin,
    "maximize_short_term_region_variety": _maximize_short_term_region_variety,
    "maximize_long_term_region_variety": _maximize_long_term_region_variety,
    "cycle_through_regions": _cycle_through_regions,
    "proportional_by_region": _proportional_by_region,
    "favorites_first": _favorites_first,
}
