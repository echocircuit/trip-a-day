"""Flight price caching: TTL logic, cache hit/miss, and cache storage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from trip_a_day.db import PriceCache


def get_cache_ttl_days(advance_days: int) -> int:
    """Return cache TTL in days based on how far in advance the trip is booked.

    Prices change faster close to departure, so nearby dates expire sooner.
    """
    if advance_days <= 30:
        return 2
    elif advance_days <= 90:
        return 5
    elif advance_days <= 180:
        return 4
    else:
        return 2


def get_cached_flight(
    session: Session,
    origin: str,
    destination: str,
    departure_date: object,
    return_date: object,
    adults: int,
    children: int,
) -> PriceCache | None:
    """Return a non-expired cache entry for this route + dates + pax, or None."""
    now = datetime.now(UTC)
    return (
        session.query(PriceCache)
        .filter(
            PriceCache.origin_iata == origin,
            PriceCache.destination_iata == destination,
            PriceCache.departure_date == departure_date,
            PriceCache.return_date == return_date,
            PriceCache.adults == adults,
            PriceCache.children == children,
            PriceCache.expires_at > now,
        )
        .order_by(PriceCache.queried_at.desc())
        .first()
    )


def store_flight_cache(
    session: Session,
    origin: str,
    destination: str,
    departure_date: object,
    return_date: object,
    adults: int,
    children: int,
    price_usd: float,
    airline: str | None,
    stops: int | None,
    advance_days: int,
    is_mock: bool,
) -> PriceCache:
    """Store a flight price in the cache and return the new entry."""
    ttl_days = get_cache_ttl_days(advance_days)
    now = datetime.now(UTC)
    entry = PriceCache(
        origin_iata=origin,
        destination_iata=destination,
        departure_date=departure_date,
        return_date=return_date,
        adults=adults,
        children=children,
        price_usd=price_usd,
        airline=airline,
        stops=stops,
        queried_at=now,
        expires_at=now + timedelta(days=ttl_days),
        is_mock=is_mock,
    )
    session.add(entry)
    session.flush()
    return entry
