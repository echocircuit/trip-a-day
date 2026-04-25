"""Smoke test for the main.py pipeline.

Mocks all external API calls so the full orchestration path runs without
network access. Catches import errors, DB init failures, and orchestration
bugs that wouldn't be caught by unit tests on individual modules.

Architecture note: Pass 1 is now delegated to find_cheapest_in_window
(window_search.py). Most tests mock find_cheapest_in_window as a whole;
tests that validate Pass-2 behavior patch get_flight_offers directly.
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
        city="New York",
        country="United States",
        region="North America",
        excluded=False,
        last_queried_at=None,
        query_count=0,
        last_known_price_usd=None,
        last_known_price_date=None,
    )


def _fake_airport(iata: str = "JFK") -> AirportInfo:
    return AirportInfo(
        iata=iata,
        city="New York",
        country="United States",
        country_code="US",
        region="North America",
        latitude=40.6413,
        longitude=-73.7781,
    )


def _fake_cost(flight: float = 400.0) -> CostBreakdown:
    return CostBreakdown(
        flights=flight,
        hotel=700.0,
        car=100.0,
        food=200.0,
        car_is_estimate=True,
    )


def _fake_flight(depart: date, price: float = 400.0) -> FlightOffer:
    return FlightOffer(
        origin="HSV",
        destination="JFK",
        departure_date=depart,
        return_date=depart + timedelta(days=7),
        price_total=price,
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


def _window_result(
    cost: CostBreakdown | None = None,
    depart: date | None = None,
    live_calls: int = 1,
    cache_hits: int = 0,
):
    """Return value tuple for mocking find_cheapest_in_window."""
    if cost is None:
        cost = _fake_cost()
    if depart is None:
        depart = date.today() + timedelta(days=7)
    return (cost, depart, live_calls, cache_hits)


def test_run_succeeds_with_one_candidate(in_memory_session):
    """Full pipeline runs to completion when Pass 1 returns one valid candidate."""
    import main

    depart = date.today() + timedelta(days=7)

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_fake_dest()]),
        patch(
            "main.find_cheapest_in_window", return_value=_window_result(depart=depart)
        ),
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
        # All window searches return no result
        patch("main.find_cheapest_in_window", return_value=(None, None, 0, 0)),
        pytest.raises(SystemExit) as exc_info,
    ):
        main.run()

    assert exc_info.value.code == 1


def test_run_excludes_zero_flight_cost_and_continues(in_memory_session):
    """Destination with $0 flight cost in Pass 2 is excluded; pipeline continues."""
    import json

    import main

    depart = date.today() + timedelta(days=7)

    # Two destinations: both make it through Pass 1 (window search).
    # In Pass 2, OAK's get_flight_offers returns $0 → is_valid_cost_breakdown fails.
    bad_dest = _fake_dest("OAK")
    bad_dest.city = "Oakland"
    good_dest = _fake_dest("JFK")

    def _window_side_effect(*args, **kwargs):
        # Both destinations return a valid cost in Pass 1 (window search found them)
        return _window_result(depart=depart)

    def _flight_side_effect(*args, **kwargs):
        dest = kwargs.get("destination") or (args[1] if len(args) > 1 else "JFK")
        price = 0.0 if dest == "OAK" else 400.0
        return FlightOffer(
            origin=kwargs.get("origin", "HSV"),
            destination=dest,
            departure_date=depart,
            return_date=depart + timedelta(days=7),
            price_total=price,
            booking_url="https://example.com/flight",
            raw="{}",
        )

    def _airport_side_effect(iata, session):
        city = "Oakland" if iata == "OAK" else "New York"
        return AirportInfo(
            iata=iata,
            city=city,
            country="United States",
            country_code="US",
            region="North America",
            latitude=40.6413,
            longitude=-73.7781,
        )

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[bad_dest, good_dest]),
        patch("main.find_cheapest_in_window", side_effect=_window_side_effect),
        patch("main.get_airport_info", side_effect=_airport_side_effect),
        patch("main.get_flight_offers", side_effect=_flight_side_effect),
        patch("main.get_hotel_offers", return_value=_fake_hotel(depart)),
        patch("main.get_food_cost", return_value=_fake_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()  # must not raise

    # Verify the winner was JFK (valid price), not OAK ($0 price in Pass 2).
    with in_memory_session() as s:
        from trip_a_day.db import RunLog, Trip

        run = s.query(RunLog).order_by(RunLog.id.desc()).first()
        assert run is not None
        assert run.status == "success"

        # OAK was excluded in Pass 2 for $0 flight
        assert run.destinations_excluded == 1
        exclusions = json.loads(run.invalid_data_exclusions)
        assert any(e["iata"] == "OAK" for e in exclusions)

        # Winner must be JFK (valid price)
        winner = s.get(Trip, run.winner_trip_id)
        assert winner is not None
        assert winner.destination_iata == "JFK"
        assert winner.flight_cost_usd > 0


def _fake_cache_hit(price: float = 350.0) -> SimpleNamespace:
    """A minimal PriceCache-like object with a valid cached price."""
    return SimpleNamespace(price_usd=price)


def test_run_log_destinations_evaluated_is_batch_size(in_memory_session):
    """destinations_evaluated must equal len(batch), not len(Pass-2 winners)."""
    import main

    depart = date.today() + timedelta(days=7)
    batch = [_fake_dest(f"D{i:02d}") for i in range(5)]

    def _airport_side_effect(iata, session):
        return AirportInfo(
            iata=iata,
            city=iata,
            country="United States",
            country_code="US",
            region="North America",
            latitude=34.6,
            longitude=-86.7,
        )

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=batch),
        patch(
            "main.find_cheapest_in_window", return_value=_window_result(depart=depart)
        ),
        patch("main.get_airport_info", side_effect=_airport_side_effect),
        patch("main.get_flight_offers", return_value=_fake_flight(depart)),
        patch("main.get_hotel_offers", return_value=_fake_hotel(depart)),
        patch("main.get_food_cost", return_value=_fake_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()

    with in_memory_session() as s:
        from trip_a_day.db import RunLog

        run = s.query(RunLog).order_by(RunLog.id.desc()).first()
        assert run is not None
        assert run.destinations_evaluated == 5  # batch size, not Pass-2 count


def test_run_log_cache_hits_counted(in_memory_session):
    """cache_hits_flights reflects the cache hits returned by find_cheapest_in_window."""
    import main

    depart = date.today() + timedelta(days=7)
    # Batch of 3: first 2 report cache hits from window search, last one is a live call.
    batch = [_fake_dest("AA1"), _fake_dest("AA2"), _fake_dest("AA3")]
    call_count = [0]

    def _window_side_effect(*args, **kwargs):
        call_count[0] += 1
        # First two calls: 1 cache hit each; third: 0 cache hits
        hits = 1 if call_count[0] <= 2 else 0
        return _window_result(
            depart=depart, live_calls=0 if hits else 1, cache_hits=hits
        )

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=batch),
        patch("main.find_cheapest_in_window", side_effect=_window_side_effect),
        patch("main.get_airport_info", return_value=_fake_airport()),
        patch("main.get_flight_offers", return_value=_fake_flight(depart)),
        patch("main.get_hotel_offers", return_value=_fake_hotel(depart)),
        patch("main.get_food_cost", return_value=_fake_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()

    with in_memory_session() as s:
        from trip_a_day.db import RunLog

        run = s.query(RunLog).order_by(RunLog.id.desc()).first()
        assert run is not None
        assert run.cache_hits_flights == 2


def test_run_log_destinations_excluded_counted(in_memory_session):
    """destinations_excluded equals the number of invalid-cost destinations in Pass 2."""
    import main

    depart = date.today() + timedelta(days=7)
    bad_dest = _fake_dest("OAK")
    bad_dest.city = "Oakland"
    good_dest = _fake_dest("JFK")

    def _flight_side_effect(*args, **kwargs):
        dest = kwargs.get("destination") or (args[1] if len(args) > 1 else "JFK")
        price = 0.0 if dest == "OAK" else 400.0
        return FlightOffer(
            origin="HSV",
            destination=dest,
            departure_date=depart,
            return_date=depart + timedelta(days=7),
            price_total=price,
            booking_url="https://example.com/flight",
            raw="{}",
        )

    def _airport_side_effect(iata, session):
        return AirportInfo(
            iata=iata,
            city=iata,
            country="United States",
            country_code="US",
            region="North America",
            latitude=40.6,
            longitude=-73.7,
        )

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[bad_dest, good_dest]),
        # Both make it through Pass 1 (window search found them)
        patch(
            "main.find_cheapest_in_window", return_value=_window_result(depart=depart)
        ),
        patch("main.get_airport_info", side_effect=_airport_side_effect),
        patch("main.get_flight_offers", side_effect=_flight_side_effect),
        patch("main.get_hotel_offers", return_value=_fake_hotel(depart)),
        patch("main.get_food_cost", return_value=_fake_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()

    with in_memory_session() as s:
        from trip_a_day.db import RunLog

        run = s.query(RunLog).order_by(RunLog.id.desc()).first()
        assert run is not None
        assert run.destinations_excluded == 1  # OAK excluded for $0 flight in Pass 2


def test_run_summary_logged(in_memory_session, caplog):
    """Run summary line appears in the log at INFO level."""
    import logging

    import main

    depart = date.today() + timedelta(days=7)

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_fake_dest()]),
        patch(
            "main.find_cheapest_in_window", return_value=_window_result(depart=depart)
        ),
        patch("main.get_airport_info", return_value=_fake_airport()),
        patch("main.get_flight_offers", return_value=_fake_flight(depart)),
        patch("main.get_hotel_offers", return_value=_fake_hotel(depart)),
        patch("main.get_food_cost", return_value=_fake_food()),
        patch("main.send_trip_notification", return_value=True),
        caplog.at_level(logging.INFO, logger="main"),
    ):
        main.run()

    assert any("Run complete:" in r.message for r in caplog.records)
    assert any("destinations evaluated" in r.message for r in caplog.records)


def test_run_exits_1_when_all_flights_missing(in_memory_session):
    """Pipeline exits with code 1 when Pass 1 has prices but Pass 2 yields no complete trips."""
    import main

    depart = date.today() + timedelta(days=7)

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_fake_dest()]),
        # Pass 1 succeeds
        patch(
            "main.find_cheapest_in_window", return_value=_window_result(depart=depart)
        ),
        patch("main.get_airport_info", return_value=_fake_airport()),
        # Pass 2 flight lookup always succeeds …
        patch("main.get_flight_offers", return_value=_fake_flight(depart)),
        # … but hotel lookup always fails, so Pass 2 builds no candidates.
        patch("main.get_hotel_offers", return_value=None),
        pytest.raises(SystemExit) as exc_info,
    ):
        main.run()

    assert exc_info.value.code == 1
