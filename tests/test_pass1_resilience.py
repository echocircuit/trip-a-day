"""Pass 1 failure resilience tests.

Verifies that when Pass 1 returns no valid prices the pipeline:
- Exits with code 0 instead of 1 (so APScheduler keeps running)
- Tries a stale-cache fallback before giving up
- Logs and skips individual exceptions rather than aborting the whole run
- Writes a structured pass1_diagnostics JSON blob to run_log
- _stale_cache_fallback excludes is_mock=True cache entries
- last_queried_at updated for no-price destinations that consumed live calls
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trip_a_day.costs import CostBreakdown
from trip_a_day.db import Base, PriceCache, RunLog
from trip_a_day.fetcher import AirportInfo, FlightOffer, FoodEstimate, HotelOffer
from trip_a_day.ranker import TripCandidate


@pytest.fixture()
def in_memory_session(tmp_path, monkeypatch):
    db_path = tmp_path / "resilience.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("trip_a_day.db.engine", engine)
    monkeypatch.setattr("trip_a_day.db.SessionFactory", factory)
    monkeypatch.setattr("trip_a_day.db.init_db", lambda: None)
    return factory


def _airport(iata="HSV"):
    return AirportInfo(
        iata=iata,
        city="Huntsville",
        country="United States",
        country_code="US",
        region="North America",
        latitude=34.6418,
        longitude=-86.7751,
    )


def _dest(iata="JFK"):
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


def _hotel(depart=None):
    if depart is None:
        depart = date.today() + timedelta(days=14)
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


def _food():
    return FoodEstimate(
        city="New York",
        country="United States",
        cost_per_person_per_day=50.0,
        total_cost=200.0,
        source="fallback",
    )


def _stale_candidate(iata="JFK"):
    depart = date.today() + timedelta(days=14)
    cost = CostBreakdown(
        flights=350.0,
        hotel=700.0,
        car=100.0,
        food=200.0,
        car_is_estimate=True,
        transport_usd=0.0,
    )
    return TripCandidate(
        destination_iata=iata,
        city="New York",
        country="United States",
        region="North America",
        departure_date=depart,
        return_date=depart + timedelta(days=7),
        cost=cost,
        distance_miles=900.0,
        flight_booking_url="https://example.com/flight",
        hotel_booking_url="https://example.com/hotel",
        car_booking_url="https://example.com/car",
        raw_flight_data='{"source": "stale_cache", "price_usd": 350.0}',
        raw_hotel_data="{}",
        departure_airport="HSV",
        stale_cache=True,
    )


# ── Test 1: empty Pass 1 exits cleanly with code 0 ─────────────────────────


def test_empty_pass1_exits_with_code_0(in_memory_session):
    """When all destinations return None and no stale cache exists, exit 0 not 1.

    Previously crashed APScheduler by exiting with code 1. The graceful
    exit (0) lets the scheduler keep its process alive for the next day.
    """
    import main

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_dest()]),
        patch("main.find_cheapest_in_window", return_value=(None, None, 0, 0)),
        patch("main.get_airport_info", return_value=_airport()),
        patch("main._stale_cache_fallback", return_value=[]),
        patch("main.send_no_results_notification", return_value=True),
        pytest.raises(SystemExit) as exc_info,
    ):
        main.run()

    assert exc_info.value.code == 0


def test_empty_pass1_writes_failed_runlog(in_memory_session):
    """A failed Pass 1 with no stale cache writes a failed run_log entry."""
    import main

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_dest()]),
        patch("main.find_cheapest_in_window", return_value=(None, None, 0, 0)),
        patch("main.get_airport_info", return_value=_airport()),
        patch("main._stale_cache_fallback", return_value=[]),
        patch("main.send_no_results_notification", return_value=True),
        pytest.raises(SystemExit),
    ):
        main.run()

    with in_memory_session() as s:
        run = s.query(RunLog).order_by(RunLog.id.desc()).first()
    assert run is not None
    assert run.status == "failed"
    assert run.error_message == "Pass 1 returned no prices"


# ── Test 2: stale cache fallback produces a successful run ─────────────────


def test_stale_cache_used_when_all_live_calls_fail(in_memory_session):
    """When live calls all fail but stale cache exists, the run succeeds.

    The winning trip must be marked stale_cache=True in the DB.
    """
    import main

    depart = date.today() + timedelta(days=14)

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_dest()]),
        patch("main.find_cheapest_in_window", return_value=(None, None, 0, 0)),
        patch("main.get_airport_info", return_value=_airport()),
        # Stale cache returns one candidate
        patch("main._stale_cache_fallback", return_value=[_stale_candidate()]),
        patch("main.get_flight_offers", return_value=None),
        patch("main.get_hotel_offers", return_value=_hotel(depart)),
        patch("main.get_food_cost", return_value=_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()

    with in_memory_session() as s:
        from trip_a_day.db import Trip

        run = s.query(RunLog).order_by(RunLog.id.desc()).first()
        assert run is not None
        assert run.status == "success"

        winner = s.get(Trip, run.winner_trip_id)
        assert winner is not None
        assert winner.stale_cache is True


def test_stale_cache_diagnostics_flag_set(in_memory_session):
    """When stale cache is used, pass1_diagnostics contains stale_cache_used=1."""
    import main

    depart = date.today() + timedelta(days=14)

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_dest()]),
        patch("main.find_cheapest_in_window", return_value=(None, None, 0, 0)),
        patch("main.get_airport_info", return_value=_airport()),
        patch("main._stale_cache_fallback", return_value=[_stale_candidate()]),
        patch("main.get_flight_offers", return_value=None),
        patch("main.get_hotel_offers", return_value=_hotel(depart)),
        patch("main.get_food_cost", return_value=_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()

    with in_memory_session() as s:
        run = s.query(RunLog).order_by(RunLog.id.desc()).first()
    assert run.pass1_diagnostics is not None
    diag = json.loads(run.pass1_diagnostics)
    assert diag.get("stale_cache_used") == 1


# ── Test 3: exception in find_cheapest_in_window skips destination ─────────


def test_exception_in_window_search_skips_destination_not_run(in_memory_session):
    """An exception raised inside find_cheapest_in_window skips that destination.

    The run continues with remaining destinations rather than aborting.
    If at least one other destination returns a valid price, the run succeeds.
    """
    import main

    depart = date.today() + timedelta(days=14)
    good_cost = CostBreakdown(
        flights=400.0,
        hotel=700.0,
        car=100.0,
        food=200.0,
        car_is_estimate=True,
        transport_usd=0.0,
    )
    call_count = [0]

    def _window_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Simulated window search failure")
        return (good_cost, depart, 1, 0)

    flight = FlightOffer(
        origin="HSV",
        destination="LAX",
        departure_date=depart,
        return_date=depart + timedelta(days=7),
        price_total=400.0,
        booking_url="https://example.com/flight",
        raw="{}",
    )

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        # Two destinations: first raises, second succeeds
        patch("main.select_daily_batch", return_value=[_dest("JFK"), _dest("LAX")]),
        patch("main.find_cheapest_in_window", side_effect=_window_side_effect),
        patch("main.get_airport_info", return_value=_airport()),
        patch("main.get_flight_offers", return_value=flight),
        patch("main.get_hotel_offers", return_value=_hotel(depart)),
        patch("main.get_food_cost", return_value=_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()  # must not raise — second destination saves the run

    with in_memory_session() as s:
        run = s.query(RunLog).order_by(RunLog.id.desc()).first()
    assert run is not None
    assert run.status == "success"


def test_exception_logged_at_warning_level(in_memory_session, caplog):
    """An exception in find_cheapest_in_window is logged at WARNING level."""
    import logging

    import main

    depart = date.today() + timedelta(days=14)
    good_cost = CostBreakdown(
        flights=400.0,
        hotel=700.0,
        car=100.0,
        food=200.0,
        car_is_estimate=True,
        transport_usd=0.0,
    )
    call_count = [0]

    def _window_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ValueError("Test error")
        return (good_cost, depart, 1, 0)

    flight = FlightOffer(
        origin="HSV",
        destination="LAX",
        departure_date=depart,
        return_date=depart + timedelta(days=7),
        price_total=400.0,
        booking_url="https://example.com/flight",
        raw="{}",
    )

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_dest("JFK"), _dest("LAX")]),
        patch("main.find_cheapest_in_window", side_effect=_window_side_effect),
        patch("main.get_airport_info", return_value=_airport()),
        patch("main.get_flight_offers", return_value=flight),
        patch("main.get_hotel_offers", return_value=_hotel(depart)),
        patch("main.get_food_cost", return_value=_food()),
        patch("main.send_trip_notification", return_value=True),
        caplog.at_level(logging.WARNING, logger="main"),
    ):
        main.run()

    warning_messages = [
        r.message for r in caplog.records if r.levelno >= logging.WARNING
    ]
    assert any("unhandled exception in window search" in m for m in warning_messages)
    assert any("ValueError" in m for m in warning_messages)


# ── Test 4: pass1_diagnostics counter ─────────────────────────────────────


def test_pass1_diagnostics_tallies_failures(in_memory_session):
    """pass1_diagnostics JSON in run_log correctly counts no_price destinations."""
    import main

    depart = date.today() + timedelta(days=14)
    good_cost = CostBreakdown(
        flights=400.0,
        hotel=700.0,
        car=100.0,
        food=200.0,
        car_is_estimate=True,
        transport_usd=0.0,
    )
    call_count = [0]

    def _window_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] <= 2:
            return (None, None, 0, 0)  # 2 failures
        return (good_cost, depart, 1, 0)  # 1 success

    flight = FlightOffer(
        origin="HSV",
        destination="SFO",
        departure_date=depart,
        return_date=depart + timedelta(days=7),
        price_total=400.0,
        booking_url="https://example.com/flight",
        raw="{}",
    )

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch(
            "main.select_daily_batch",
            return_value=[_dest("JFK"), _dest("ORD"), _dest("SFO")],
        ),
        patch("main.find_cheapest_in_window", side_effect=_window_side_effect),
        patch("main.get_airport_info", return_value=_airport()),
        patch("main.get_flight_offers", return_value=flight),
        patch("main.get_hotel_offers", return_value=_hotel(depart)),
        patch("main.get_food_cost", return_value=_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()

    with in_memory_session() as s:
        run = s.query(RunLog).order_by(RunLog.id.desc()).first()

    assert run.status == "success"
    assert run.pass1_diagnostics is not None
    diag = json.loads(run.pass1_diagnostics)
    assert diag["no_price"] == 2
    assert diag["valid"] == 1
    assert diag["budget_exhausted"] == 0


def test_pass1_diagnostics_present_on_failed_run(in_memory_session):
    """Failed runs also write pass1_diagnostics to run_log."""
    import main

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[_dest("JFK"), _dest("ORD")]),
        patch("main.find_cheapest_in_window", return_value=(None, None, 0, 0)),
        patch("main.get_airport_info", return_value=_airport()),
        patch("main._stale_cache_fallback", return_value=[]),
        patch("main.send_no_results_notification", return_value=True),
        pytest.raises(SystemExit),
    ):
        main.run()

    with in_memory_session() as s:
        run = s.query(RunLog).order_by(RunLog.id.desc()).first()

    assert run.status == "failed"
    assert run.pass1_diagnostics is not None
    diag = json.loads(run.pass1_diagnostics)
    assert diag["no_price"] == 2
    assert diag["valid"] == 0


# ── Test 5: _stale_cache_fallback excludes is_mock=True entries ────────────


def test_stale_cache_fallback_excludes_mock_entries(tmp_path):
    """_stale_cache_fallback must not use is_mock=True cache entries.

    A mock cache row (is_mock=True) should be ignored even if it has a
    future departure date, leaving no candidate; a real row (is_mock=False)
    for the same destination should be returned.
    """
    from types import SimpleNamespace

    import main

    engine = create_engine(f"sqlite:///{tmp_path / 'stale_mock.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    future = date.today() + timedelta(days=30)
    past_expire = datetime(2020, 1, 1)

    with factory() as s:
        # Mock entry — should be ignored
        s.add(
            PriceCache(
                origin_iata="HSV",
                destination_iata="CDG",
                departure_date=future,
                return_date=future + timedelta(days=7),
                adults=2,
                children=0,
                price_usd=360.0,
                expires_at=past_expire,
                is_mock=True,
            )
        )
        s.commit()

    dest = SimpleNamespace(iata_code="CDG", excluded=False)

    with factory() as s:
        result = main._stale_cache_fallback(
            session=s,
            batch=[dest],
            dep_iata="HSV",
            transport_usd=0.0,
            home_lat=34.6,
            home_lon=-86.8,
            num_adults=2,
            num_children=0,
            num_rooms=1,
            car_rental_required=False,
            trip_nights=7,
            preferred_car_site="kayak",
        )

    assert result == [], "Mock cache entry must not produce a stale candidate"


def test_stale_cache_fallback_uses_real_entries(tmp_path):
    """_stale_cache_fallback returns candidates when is_mock=False entries exist."""
    from types import SimpleNamespace
    from unittest.mock import patch

    import main

    engine = create_engine(f"sqlite:///{tmp_path / 'stale_real.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    future = date.today() + timedelta(days=30)
    past_expire = datetime(2020, 1, 1)

    with factory() as s:
        s.add(
            PriceCache(
                origin_iata="HSV",
                destination_iata="CDG",
                departure_date=future,
                return_date=future + timedelta(days=7),
                adults=2,
                children=0,
                price_usd=500.0,
                expires_at=past_expire,
                is_mock=False,
            )
        )
        s.commit()

    dest = SimpleNamespace(iata_code="CDG", excluded=False)

    mock_airport = AirportInfo(
        iata="CDG",
        city="Paris",
        country="France",
        country_code="FR",
        region="Western Europe",
        latitude=48.86,
        longitude=2.35,
    )

    with (
        factory() as s,
        patch("main.get_airport_info", return_value=mock_airport),
        patch("main.get_hotel_offers", return_value=_hotel(future)),
        patch("main.get_food_cost", return_value=_food()),
        patch("main.build_flight_url", return_value="https://example.com/f"),
        patch("main.build_car_url", return_value="https://example.com/c"),
    ):
        result = main._stale_cache_fallback(
            session=s,
            batch=[dest],
            dep_iata="HSV",
            transport_usd=0.0,
            home_lat=34.6,
            home_lon=-86.8,
            num_adults=2,
            num_children=0,
            num_rooms=1,
            car_rental_required=False,
            trip_nights=7,
            preferred_car_site="kayak",
        )

    assert len(result) == 1
    assert result[0].destination_iata == "CDG"
    assert result[0].stale_cache is True


# ── Test 6: last_queried_at updated for no-price destinations with live calls ─


def test_last_queried_at_updated_for_no_price_with_live_calls(in_memory_session):
    """last_queried_at is updated even when no price is found, if a live call was made.

    Destinations that consistently return no price (e.g. European cities from HSV)
    were permanently stuck at the top of the least-recently-queried queue because
    last_queried_at was only updated on success. This fix ensures they rotate out.
    """
    import main

    dest = _dest("JFK")
    assert dest.last_queried_at is None

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", in_memory_session),
        patch("main.select_daily_batch", return_value=[dest]),
        # No price found but 1 live call consumed
        patch("main.find_cheapest_in_window", return_value=(None, None, 1, 0)),
        patch("main.get_airport_info", return_value=_airport()),
        patch("main._stale_cache_fallback", return_value=[]),
        patch("main.send_no_results_notification", return_value=True),
        pytest.raises(SystemExit),
    ):
        main.run()

    assert dest.last_queried_at is not None, (
        "last_queried_at should be set after a live call, even with no price"
    )
