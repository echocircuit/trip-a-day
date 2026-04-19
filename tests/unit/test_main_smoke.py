"""Smoke test for the main.py pipeline.

Mocks all external API calls so the full orchestration path runs without
network access. Catches import errors, DB init failures, and orchestration
bugs that wouldn't be caught by unit tests on individual modules.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trip_a_day.db import Base
from trip_a_day.fetcher import (
    AirportInfo,
    FlightOffer,
    FoodEstimate,
    HotelOffer,
)


@pytest.fixture()
def in_memory_session(tmp_path, monkeypatch):
    """Replace the real DB with a fresh in-memory SQLite for each test."""
    db_path = tmp_path / "smoke.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    monkeypatch.setattr("trip_a_day.db.engine", engine)
    monkeypatch.setattr("trip_a_day.db.SessionFactory", factory)

    # Patch init_db so it doesn't recreate tables against the real engine
    monkeypatch.setattr("trip_a_day.db.init_db", lambda: None)

    return factory


def _fake_dest(iata: str = "JFK") -> SimpleNamespace:
    return SimpleNamespace(
        iata_code=iata,
        excluded=False,
        last_queried_at=None,
        query_count=0,
        last_known_price_usd=None,
        last_known_price_date=None,
    )


def _fake_airport() -> AirportInfo:
    return AirportInfo(
        iata="JFK",
        city="New York",
        country="United States",
        country_code="US",
        region="North America",
        latitude=40.6413,
        longitude=-73.7781,
    )


def _fake_flight(depart: date) -> FlightOffer:
    return FlightOffer(
        origin="HSV",
        destination="JFK",
        departure_date=depart,
        return_date=depart + timedelta(days=7),
        price_total=400.0,
        booking_url="https://example.com/flight",
        raw="{}",
    )


def _fake_hotel(depart: date) -> HotelOffer:
    return HotelOffer(
        hotel_id="HJFK001",
        hotel_name="Test Hotel",
        city_code="JFK",
        check_in=depart,
        check_out=depart + timedelta(days=7),
        price_total=700.0,
        booking_url="https://example.com/hotel",
        raw="{}",
    )


def _fake_food() -> FoodEstimate:
    return FoodEstimate(
        city="New York",
        country="United States",
        cost_per_person_per_day=50.0,
        total_cost=1400.0,
        source="fallback",
    )


def test_run_succeeds_with_one_candidate(in_memory_session):
    """Full pipeline runs to completion when mocked fetcher returns one destination."""
    import main

    depart = date.today() + timedelta(days=7)

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_fake_dest()]),
        patch("main.get_cached_flight", return_value=None),
        patch("main.store_flight_cache"),
        patch("main.get_airport_info", return_value=_fake_airport()),
        patch("main.get_flight_offers", return_value=_fake_flight(depart)),
        patch("main.get_hotel_offers", return_value=_fake_hotel(depart)),
        patch("main.get_food_cost", return_value=_fake_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()  # must not raise


def test_run_exits_1_when_no_destinations(in_memory_session):
    """Pipeline exits with code 1 (not a crash) when Pass 1 yields no prices."""
    import main

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_fake_dest()]),
        patch("main.get_cached_flight", return_value=None),
        patch("main.get_flight_offers", return_value=None),
        pytest.raises(SystemExit) as exc_info,
    ):
        main.run()

    assert exc_info.value.code == 1


def test_run_exits_1_when_all_flights_missing(in_memory_session):
    """Pipeline exits with code 1 when Pass 1 has prices but Pass 2 yields no complete trips."""
    import main

    depart = date.today() + timedelta(days=7)

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_fake_dest()]),
        patch("main.get_cached_flight", return_value=None),
        patch("main.store_flight_cache"),
        patch("main.get_airport_info", return_value=_fake_airport()),
        # Pass 1 succeeds (returns price)…
        patch("main.get_flight_offers", return_value=_fake_flight(depart)),
        # …but hotel lookup always fails, so Pass 2 builds no candidates.
        patch("main.get_hotel_offers", return_value=None),
        pytest.raises(SystemExit) as exc_info,
    ):
        main.run()

    assert exc_info.value.code == 1
