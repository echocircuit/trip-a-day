"""Smoke test for Phase 7 multi-airport departure pipeline.

Verifies that when search_radius_miles > 0, the pipeline:
1. Searches from both the home airport and a nearby airport
2. Adds transport cost for the nearby airport
3. Selects the globally cheapest trip (including transport) as the winner
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trip_a_day.costs import CostBreakdown
from trip_a_day.db import Base
from trip_a_day.fetcher import AirportInfo, FlightOffer, FoodEstimate, HotelOffer


@pytest.fixture()
def in_memory_session(tmp_path, monkeypatch):
    db_path = tmp_path / "multi_airport_smoke.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("trip_a_day.db.engine", engine)
    monkeypatch.setattr("trip_a_day.db.SessionFactory", factory)
    monkeypatch.setattr("trip_a_day.db.init_db", lambda: None)
    return factory


def _airport(iata: str, lat: float = 34.0, lon: float = -86.0) -> AirportInfo:
    return AirportInfo(
        iata=iata,
        city=f"City-{iata}",
        country="United States",
        country_code="US",
        region="North America",
        latitude=lat,
        longitude=lon,
    )


def _dest(iata: str = "JFK") -> SimpleNamespace:
    return SimpleNamespace(
        iata_code=iata,
        city="New York",
        country="United States",
        region="North America",
        excluded=False,
        last_queried_at=None,
        query_count=0,
        last_known_price_usd=None,
        last_known_price_date=None,
    )


def _flight(origin: str, dest: str, price: float, depart: date) -> FlightOffer:
    return FlightOffer(
        origin=origin,
        destination=dest,
        departure_date=depart,
        return_date=depart + timedelta(days=7),
        price_total=price,
        booking_url="https://example.com/flight",
        raw="{}",
    )


def _hotel(depart: date) -> HotelOffer:
    return HotelOffer(
        hotel_id="H001",
        hotel_name="Test Hotel",
        city_code="JFK",
        check_in=depart,
        check_out=depart + timedelta(days=7),
        price_total=700.0,
        booking_url="https://example.com/hotel",
        raw="{}",
    )


def _food() -> FoodEstimate:
    return FoodEstimate(
        city="New York",
        country="United States",
        cost_per_person_per_day=50.0,
        total_cost=1400.0,
        source="fallback",
    )


def _cost(flight: float = 400.0, transport: float = 0.0) -> CostBreakdown:
    return CostBreakdown(
        flights=flight,
        hotel=700.0,
        car=100.0,
        food=200.0,
        car_is_estimate=True,
        transport_usd=transport,
    )


def test_multi_airport_selects_cheapest_globally(in_memory_session):
    """Pipeline picks the globally cheapest trip even when it departs from a nearby airport.

    Setup:
    - Home airport HSV, nearby airport BHM (~73 mi away).
    - HSV Pass 1 cost: $1,800 total (flight $800 + hotel $700 + car $100 + food $200).
    - BHM Pass 1 cost: $1,402 total (flight $300 + transport $102 + hotel $700 + car $100 + food $200).
    - Winner must be the BHM departure (cheaper globally).
    """
    from datetime import UTC, datetime

    import main

    from trip_a_day.db import Preference

    # Pre-seed preferences so the test is independent of global defaults.
    with in_memory_session() as s:
        s.merge(
            Preference(
                key="search_radius_miles", value="100", updated_at=datetime.now(UTC)
            )
        )
        # Fix home_airport to HSV so the BHM transport cost ($102) is as designed.
        s.merge(
            Preference(key="home_airport", value="HSV", updated_at=datetime.now(UTC))
        )
        s.commit()

    depart = date.today() + timedelta(days=7)
    nearby_bhm = _airport("BHM", lat=33.5629, lon=-86.7535)

    # Pass 1: window search returns different costs per departure airport
    def _window_side_effect(*args, **kwargs):
        origin = kwargs.get("origin_iata") or args[0]
        transport = 102.0 if origin == "BHM" else 0.0
        flight_cost = 300.0 if origin == "BHM" else 800.0
        c = _cost(flight=flight_cost, transport=transport)
        return (c, depart, 1, 0)

    # Pass 2: get_flight_offers returns different prices per origin
    def fake_get_flights(
        origin,
        destination,
        depart_date,
        return_date,
        adults,
        children,
        session,
        direct_only=True,
        is_mock=False,
    ):
        price = 300.0 if origin == "BHM" else 800.0
        return _flight(origin, destination, price, depart_date)

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_dest("JFK")]),
        patch("main.find_cheapest_in_window", side_effect=_window_side_effect),
        patch(
            "main.get_airport_info",
            side_effect=lambda iata, session: _airport(
                iata,
                lat=34.6418
                if iata == "HSV"
                else (33.5629 if iata == "BHM" else 40.6413),
                lon=-86.7751
                if iata == "HSV"
                else (-86.7535 if iata == "BHM" else -73.7781),
            ),
        ),
        patch("main.get_nearby_airports", return_value=[nearby_bhm]),
        patch("main.get_flight_offers", side_effect=fake_get_flights),
        patch("main.get_hotel_offers", return_value=_hotel(depart)),
        patch("main.get_food_cost", return_value=_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()

    # Verify the winning candidate came from BHM (cheaper globally)
    with in_memory_session() as s:
        from trip_a_day.db import RunLog, Trip

        run = s.query(RunLog).order_by(RunLog.id.desc()).first()
        assert run is not None
        assert run.status == "success"
        winner = s.get(Trip, run.winner_trip_id)
        assert winner is not None
        assert winner.departure_iata == "BHM"


def test_radius_zero_uses_only_home_airport(in_memory_session):
    """When search_radius_miles=0, get_nearby_airports is not called."""
    import main

    depart = date.today() + timedelta(days=7)

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_dest("JFK")]),
        patch("main.find_cheapest_in_window", return_value=(_cost(), depart, 1, 0)),
        patch("main.get_airport_info", return_value=_airport("HSV")),
        patch("main.get_nearby_airports") as mock_nearby,
        patch(
            "main.get_flight_offers", return_value=_flight("HSV", "JFK", 400.0, depart)
        ),
        patch("main.get_hotel_offers", return_value=_hotel(depart)),
        patch("main.get_food_cost", return_value=_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()

    # When radius=0, main skips get_nearby_airports entirely (early-exit optimisation).
    # The pipeline should complete successfully with just the home airport.
    mock_nearby.assert_not_called()
