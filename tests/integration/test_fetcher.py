"""Integration tests for fetcher.py — uses fast-flights (Google Flights, no key required).

These tests make real network calls to Google Flights via the fast-flights library.
They are marked @pytest.mark.integration to keep them out of the default test run.

Run with:
    pytest tests/integration/test_fetcher.py -m integration -v
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trip_a_day.db import Base, seed_preferences


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
def test_get_cheapest_destinations_returns_list(test_session):
    """get_cheapest_destinations iterates seed airports and returns sorted results."""
    from trip_a_day.fetcher import get_cheapest_destinations

    departure = date.today() + timedelta(days=14)
    results = get_cheapest_destinations("ATL", departure, test_session, n=3)
    assert isinstance(results, list)
    for dest in results:
        assert dest.origin == "ATL"
        assert len(dest.destination) == 3
        assert dest.price_total > 0
    # Results must be sorted ascending by price
    prices = [r.price_total for r in results]
    assert prices == sorted(prices)


@pytest.mark.integration
def test_get_flight_offers_returns_offer_or_none(test_session):
    """get_flight_offers returns a FlightOffer with a Google Flights booking URL."""
    from trip_a_day.fetcher import get_flight_offers

    departure = date.today() + timedelta(days=14)
    return_d = departure + timedelta(days=7)
    result = get_flight_offers(
        origin="ATL",
        destination="LHR",
        depart_date=departure,
        return_date=return_d,
        adults=2,
        children=0,
        session=test_session,
    )
    if result is not None:
        assert result.price_total > 0
        assert result.origin == "ATL"
        assert result.destination == "LHR"
        assert "google.com/flights" in result.booking_url


@pytest.mark.integration
def test_get_hotel_offers_always_returns_estimate(test_session):
    """get_hotel_offers always returns a per diem estimate (never None for known airports)."""
    from trip_a_day.fetcher import get_hotel_offers

    departure = date.today() + timedelta(days=14)
    return_d = departure + timedelta(days=7)
    result = get_hotel_offers(
        city_code="LHR",
        checkin=departure,
        checkout=return_d,
        adults=2,
        session=test_session,
    )
    assert result is not None
    assert result.price_total > 0
    assert "per_diem" in result.hotel_id


@pytest.mark.integration
def test_get_food_cost_returns_estimate(test_session):
    """get_food_cost returns a non-zero estimate from per diem or fallback."""
    from trip_a_day.fetcher import get_food_cost

    result = get_food_cost(
        city="London",
        country="United Kingdom",
        region="Western Europe",
        days=7,
        people=2,
        session=test_session,
    )
    assert result.total_cost > 0
    assert result.cost_per_person_per_day > 0


@pytest.mark.integration
def test_get_airport_info_returns_seed_data(test_session):
    """get_airport_info returns data from seed_airports.json for known airports."""
    from trip_a_day.fetcher import get_airport_info

    result = get_airport_info("JFK", test_session)
    assert result is not None
    assert result.iata == "JFK"
    assert result.city == "New York"
    assert result.country == "United States"


@pytest.mark.integration
def test_get_airport_info_returns_none_for_unknown(test_session):
    """get_airport_info returns None for airports not in the seed list."""
    from trip_a_day.fetcher import get_airport_info

    result = get_airport_info("ZZZ", test_session)
    assert result is None


@pytest.mark.integration
def test_haversine_hsv_to_jfk():
    """Haversine gives a reasonable distance for HSV→JFK (known ~822 miles)."""
    from trip_a_day.fetcher import haversine_miles

    # HSV: 34.6418°N, 86.7751°W  |  JFK: 40.6413°N, 73.7781°W
    dist = haversine_miles(34.6418, -86.7751, 40.6413, -73.7781)
    assert 800 < dist < 860, f"Expected ~822 miles, got {dist}"
