"""Integration tests for fetcher.py — uses Amadeus sandbox.

These tests require AMADEUS_API_KEY and AMADEUS_API_SECRET in the environment.
They make real API calls against the Amadeus sandbox (AMADEUS_ENV=test).

Run with:
    pytest tests/integration/test_fetcher.py -m integration -v
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trip_a_day.db import Base, seed_preferences


@pytest.fixture(scope="module")
def amadeus_creds():
    key = os.environ.get("AMADEUS_API_KEY")
    secret = os.environ.get("AMADEUS_API_SECRET")
    if not key or not secret:
        pytest.skip("AMADEUS_API_KEY and AMADEUS_API_SECRET not set")
    return key, secret


@pytest.fixture(scope="module")
def test_session(tmp_path_factory):
    """In-memory SQLite session for integration tests."""
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        seed_preferences(session)
        session.commit()
        yield session


@pytest.mark.integration
def test_get_cheapest_destinations_returns_list(amadeus_creds, test_session):
    """Flight Inspiration Search returns a list of destinations."""
    from trip_a_day.fetcher import get_cheapest_destinations

    departure = date.today() + timedelta(days=7)
    results = get_cheapest_destinations("HSV", departure, test_session, n=5)
    # Sandbox may return empty — we accept that but ensure type is correct
    assert isinstance(results, list)
    for dest in results:
        assert dest.origin == "HSV"
        assert len(dest.destination) == 3
        assert dest.price_total > 0


@pytest.mark.integration
def test_get_flight_offers_returns_offer_or_none(amadeus_creds, test_session):
    """Flight Offers Search returns a FlightOffer or None (sandbox data may be absent)."""
    from trip_a_day.fetcher import get_cheapest_destinations, get_flight_offers

    departure = date.today() + timedelta(days=7)
    return_d = departure + timedelta(days=7)

    # Get a destination that the sandbox knows about
    destinations = get_cheapest_destinations("HSV", departure, test_session, n=3)
    if not destinations:
        pytest.skip("No destinations returned by sandbox for this date")

    dest_iata = destinations[0].destination
    result = get_flight_offers(
        origin="HSV",
        destination=dest_iata,
        depart_date=departure,
        return_date=return_d,
        adults=2,
        children=2,
        session=test_session,
    )
    # Result is either a valid FlightOffer or None (sandbox may lack data)
    if result is not None:
        assert result.price_total > 0
        assert result.origin == "HSV"
        assert result.destination == dest_iata


@pytest.mark.integration
def test_get_airport_info_returns_info_or_none(amadeus_creds, test_session):
    """Airport reference data returns AirportInfo for a known airport."""
    from trip_a_day.fetcher import get_airport_info

    # JFK is well-known and should be in Amadeus reference data
    result = get_airport_info("JFK", test_session)
    if result is not None:
        assert result.iata == "JFK"
        assert result.city != ""
        assert result.latitude != 0.0 or result.longitude != 0.0


@pytest.mark.integration
def test_haversine_hsv_to_jfk():
    """Haversine gives a reasonable distance for HSV→JFK (known ~880 miles)."""
    from trip_a_day.fetcher import haversine_miles

    # HSV: 34.6418°N, 86.7751°W  |  JFK: 40.6413°N, 73.7781°W
    dist = haversine_miles(34.6418, -86.7751, 40.6413, -73.7781)
    assert 800 < dist < 860, f"Expected ~822 miles, got {dist}"
