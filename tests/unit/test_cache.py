"""Unit tests for the flight price cache (cache.py)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trip_a_day.cache import get_cache_ttl_days, get_cached_flight, store_flight_cache
from trip_a_day.db import Base, PriceCache


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cache_test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as s:
        yield s


# ── TTL logic ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "advance_days, expected_ttl",
    [
        (7, 2),
        (30, 2),
        (31, 5),
        (90, 5),
        (91, 4),
        (180, 4),
        (181, 2),
        (365, 2),
    ],
)
def test_cache_ttl_days(advance_days, expected_ttl):
    assert get_cache_ttl_days(advance_days) == expected_ttl


# ── Cache miss ────────────────────────────────────────────────────────────────


def test_get_cached_flight_returns_none_when_empty(session):
    result = get_cached_flight(
        session, "HSV", "JFK", date(2026, 5, 1), date(2026, 5, 8), 2, 2
    )
    assert result is None


def test_get_cached_flight_returns_none_when_expired(session):
    now = datetime.now(UTC)
    entry = PriceCache(
        origin_iata="HSV",
        destination_iata="JFK",
        departure_date=date(2026, 5, 1),
        return_date=date(2026, 5, 8),
        adults=2,
        children=2,
        price_usd=400.0,
        queried_at=now - timedelta(days=10),
        expires_at=now - timedelta(days=1),  # already expired
        is_mock=False,
    )
    session.add(entry)
    session.flush()

    result = get_cached_flight(
        session, "HSV", "JFK", date(2026, 5, 1), date(2026, 5, 8), 2, 2
    )
    assert result is None


def test_get_cached_flight_returns_none_wrong_route(session):
    store_flight_cache(
        session,
        "HSV",
        "JFK",
        date(2026, 5, 1),
        date(2026, 5, 8),
        2,
        2,
        400.0,
        "Delta",
        0,
        14,
        True,
    )
    # Different destination
    result = get_cached_flight(
        session, "HSV", "LAX", date(2026, 5, 1), date(2026, 5, 8), 2, 2
    )
    assert result is None


# ── Cache hit ─────────────────────────────────────────────────────────────────


def test_store_and_retrieve_cache_hit(session):
    store_flight_cache(
        session,
        "HSV",
        "JFK",
        date(2026, 5, 1),
        date(2026, 5, 8),
        2,
        2,
        400.0,
        "Delta",
        0,
        14,
        True,
    )
    hit = get_cached_flight(
        session, "HSV", "JFK", date(2026, 5, 1), date(2026, 5, 8), 2, 2
    )
    assert hit is not None
    assert hit.price_usd == 400.0
    assert hit.origin_iata == "HSV"
    assert hit.destination_iata == "JFK"


def test_cache_hit_returns_most_recent_entry(session):
    dep = date(2026, 5, 1)
    ret = date(2026, 5, 8)
    # Older entry
    store_flight_cache(
        session, "HSV", "JFK", dep, ret, 2, 2, 380.0, None, None, 14, True
    )
    # Newer entry
    store_flight_cache(
        session, "HSV", "JFK", dep, ret, 2, 2, 420.0, None, None, 14, True
    )

    hit = get_cached_flight(session, "HSV", "JFK", dep, ret, 2, 2)
    assert hit is not None
    assert hit.price_usd == 420.0


def test_cache_is_mock_flag_stored(session):
    store_flight_cache(
        session,
        "HSV",
        "CDG",
        date(2026, 6, 1),
        date(2026, 6, 8),
        2,
        0,
        800.0,
        "Air France",
        1,
        45,
        is_mock=True,
    )
    hit = get_cached_flight(
        session, "HSV", "CDG", date(2026, 6, 1), date(2026, 6, 8), 2, 0
    )
    assert hit is not None
    assert hit.is_mock is True


def test_cache_different_pax_no_hit(session):
    dep = date(2026, 5, 1)
    ret = date(2026, 5, 8)
    store_flight_cache(
        session, "HSV", "JFK", dep, ret, 2, 2, 400.0, None, None, 14, True
    )

    # Different number of adults — should miss
    result = get_cached_flight(session, "HSV", "JFK", dep, ret, 1, 0)
    assert result is None
