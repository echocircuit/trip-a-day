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


def test_run_excludes_zero_flight_cost_and_continues(in_memory_session):
    """Destination with $0 flight cost is excluded; pipeline continues to next candidate."""
    import json

    import main

    depart = date.today() + timedelta(days=7)

    # Two destinations: first has $0 flight, second has a valid flight.
    bad_dest = _fake_dest("OAK")
    good_dest = _fake_dest("JFK")

    def _flight_side_effect(*args, **kwargs):
        # Pass 1: both return a price so top_iatas contains both
        # Pass 2: OAK returns $0, JFK returns valid
        dest = kwargs.get("destination") or args[1]
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
        patch("main.get_cached_flight", return_value=None),
        patch("main.store_flight_cache"),
        patch("main.get_airport_info", side_effect=_airport_side_effect),
        patch("main.get_flight_offers", side_effect=_flight_side_effect),
        patch("main.get_hotel_offers", return_value=_fake_hotel(depart)),
        patch("main.get_food_cost", return_value=_fake_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()  # must not raise

    # Verify the winner was JFK (valid price), not OAK ($0 price).
    with in_memory_session() as s:
        from trip_a_day.db import RunLog, Trip

        run = s.query(RunLog).order_by(RunLog.id.desc()).first()
        assert run is not None
        assert run.status == "success"

        # invalid_data_exclusions should mention OAK
        assert run.invalid_data_exclusions is not None
        exclusions = json.loads(run.invalid_data_exclusions)
        assert any(e["iata"] == "OAK" for e in exclusions)

        # Winner must not be OAK
        winner = s.get(Trip, run.winner_trip_id)
        assert winner is not None
        assert winner.destination_iata != "OAK"
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
        patch("main.get_cached_flight", return_value=None),
        patch("main.store_flight_cache"),
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
    """cache_hits_flights reflects the number of Pass-1 cache hits used."""
    import main

    depart = date.today() + timedelta(days=7)
    # Batch of 3: first 2 return cache hits, last one is a live call.
    batch = [_fake_dest("AA1"), _fake_dest("AA2"), _fake_dest("AA3")]

    def _cache_side_effect(session, dep, dest, *args, **kwargs):
        # AA1 and AA2 hit the cache; AA3 misses
        return _fake_cache_hit(300.0) if dest in ("AA1", "AA2") else None

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=batch),
        patch("main.get_cached_flight", side_effect=_cache_side_effect),
        patch("main.store_flight_cache"),
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
    """destinations_excluded equals the number of invalid-cost destinations."""
    import main

    depart = date.today() + timedelta(days=7)
    bad_dest = _fake_dest("OAK")
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
        patch("main.get_cached_flight", return_value=None),
        patch("main.store_flight_cache"),
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
        assert run.destinations_excluded == 1  # OAK excluded for $0 flight


def test_run_summary_logged(in_memory_session, caplog):
    """Run summary line appears in the log at INFO level."""
    import logging

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
