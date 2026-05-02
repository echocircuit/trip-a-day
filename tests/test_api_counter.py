"""API call counter consistency tests.

Verifies that api_usage.calls_made and run_log.api_calls_flights are
consistent — both count all *attempted* live calls, including those that
fail due to exceptions inside get_flights().

Root-cause background: before the fix, record_api_call() was only called
when get_flights() succeeded. Exceptions caused api_usage to under-count
while the in-memory live_calls_made counter still incremented, producing
the Dashboard "40 vs 7" discrepancy.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trip_a_day.costs import CostBreakdown
from trip_a_day.db import ApiUsage, Base, RunLog
from trip_a_day.fetcher import (
    AirportInfo,
    FlightOffer,
    FoodEstimate,
    HotelOffer,
    get_flight_offers,
)

DEPART = date.today() + timedelta(days=14)
RETURN = DEPART + timedelta(days=7)


@pytest.fixture()
def db_session(tmp_path):
    """In-memory SQLite session with the full schema."""
    engine = create_engine(f"sqlite:///{tmp_path / 'counter_test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        yield session


@pytest.fixture()
def pipeline_session(tmp_path, monkeypatch):
    """In-memory session wired into the real DB module for pipeline tests."""
    engine = create_engine(f"sqlite:///{tmp_path / 'pipeline_test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("trip_a_day.db.engine", engine)
    monkeypatch.setattr("trip_a_day.db.SessionFactory", factory)
    monkeypatch.setattr("trip_a_day.db.init_db", lambda: None)
    return factory


def _make_flight_obj(stops=0, price="$400"):
    return SimpleNamespace(stops=stops, price=price, name="Test Airline")


def _mock_ff_result(flights=None):
    if flights is None:
        flights = [_make_flight_obj()]
    return SimpleNamespace(flights=flights)


# ── Test 1: mock mode records zero calls ───────────────────────────────────


def test_mock_mode_does_not_increment_api_usage(db_session):
    """In mock mode, get_flight_offers never calls record_api_call.

    api_usage must stay at 0 after a mock flight query.
    """
    get_flight_offers("HSV", "JFK", DEPART, RETURN, 2, 0, db_session, is_mock=True)

    row = (
        db_session.query(ApiUsage).filter(ApiUsage.api_name == "google_flights").first()
    )
    assert row is None or row.calls_made == 0


# ── Test 2: live mode — successful call increments counter ─────────────────


def test_successful_live_call_increments_api_usage(db_session):
    """A successful live call to get_flights increments api_usage by 1."""
    with patch(
        "trip_a_day.fetcher.get_flights",
        return_value=_mock_ff_result([_make_flight_obj(stops=0, price="$400")]),
    ):
        offer = get_flight_offers(
            "HSV", "JFK", DEPART, RETURN, 2, 0, db_session, is_mock=False
        )

    db_session.flush()
    row = (
        db_session.query(ApiUsage).filter(ApiUsage.api_name == "google_flights").first()
    )
    assert row is not None
    assert row.calls_made == 1
    assert offer is not None


def test_multiple_live_calls_accumulate_in_api_usage(db_session):
    """N sequential live calls produces api_usage.calls_made == N."""
    n = 3

    with patch(
        "trip_a_day.fetcher.get_flights",
        return_value=_mock_ff_result([_make_flight_obj(stops=0, price="$300")]),
    ):
        for _ in range(n):
            get_flight_offers(
                "HSV", "JFK", DEPART, RETURN, 2, 0, db_session, is_mock=False
            )

    db_session.flush()
    row = (
        db_session.query(ApiUsage).filter(ApiUsage.api_name == "google_flights").first()
    )
    assert row is not None
    assert row.calls_made == n


# ── Test 3: exception path now also increments counter (Bug 2 fix) ─────────


def test_exception_in_get_flights_still_increments_api_usage(db_session, monkeypatch):
    """When get_flights() raises, the call attempt is still counted in api_usage.

    Before the fix: record_api_call was only called after a successful
    get_flights(); exceptions bypassed it, causing api_usage to under-count.
    After the fix: record_api_call is called before get_flights() in the live
    branch, so every attempted call is counted regardless of outcome.
    """
    with patch(
        "trip_a_day.fetcher.get_flights",
        side_effect=RuntimeError("playwright 401"),
    ):
        offer = get_flight_offers(
            "HSV", "LHR", DEPART, RETURN, 2, 0, db_session, is_mock=False
        )

    assert offer is None  # exception was caught and returned as None

    db_session.flush()
    row = (
        db_session.query(ApiUsage).filter(ApiUsage.api_name == "google_flights").first()
    )
    assert row is not None
    assert row.calls_made == 1  # counted even though get_flights raised


def test_multiple_exceptions_all_counted(db_session):
    """Multiple failing calls each increment the counter."""
    n = 5

    with patch(
        "trip_a_day.fetcher.get_flights",
        side_effect=ConnectionError("timeout"),
    ):
        for _ in range(n):
            get_flight_offers(
                "HSV", "CDG", DEPART, RETURN, 1, 0, db_session, is_mock=False
            )

    db_session.flush()
    row = (
        db_session.query(ApiUsage).filter(ApiUsage.api_name == "google_flights").first()
    )
    assert row is not None
    assert row.calls_made == n


# ── Test 4: counter not double-incremented in window_search multi-probe ────


def test_window_search_does_not_double_count(db_session, monkeypatch):
    """window_search.find_cheapest_in_window probing 3 dates counts 3 calls, not 6.

    Before the fix, record_api_call fired after get_flights() succeeded, and
    live_calls_used incremented separately — these were the same N for successful
    calls. After the fix, record_api_call fires BEFORE get_flights(). The count
    should still be exactly N (number of probes), not 2N.
    """
    from trip_a_day.window_search import find_cheapest_in_window

    dest = SimpleNamespace(
        iata_code="LHR",
        city="London",
        country="United Kingdom",
        region="Western Europe",
    )

    with patch(
        "trip_a_day.fetcher.get_flights",
        return_value=_mock_ff_result([_make_flight_obj(stops=0, price="$800")]),
    ):
        _cost, _best_date, live_calls, _cache_hits = find_cheapest_in_window(
            origin_iata="HSV",
            destination=dest,
            min_days=7,
            max_days=30,
            trip_length_nights=7,
            adults=2,
            children=0,
            num_rooms=1,
            car_rental_required=False,
            direct_flights_only=False,
            cache_ttl_enabled=False,
            is_mock=False,
            db_session=db_session,
            live_calls_remaining=10,
        )

    db_session.flush()
    row = (
        db_session.query(ApiUsage).filter(ApiUsage.api_name == "google_flights").first()
    )
    # 3 probes = 3 calls in api_usage and live_calls returned from window_search
    assert row is not None
    assert row.calls_made == live_calls  # api_usage matches in-memory counter
    assert live_calls == 3  # default probe count


# ── Test 5: run_log.api_calls_flights matches api_usage delta ─────────────


def _fake_airport(iata="JFK"):
    return AirportInfo(
        iata=iata,
        city="New York",
        country="United States",
        country_code="US",
        region="North America",
        latitude=40.6413,
        longitude=-73.7781,
    )


def _fake_flight(depart):
    return FlightOffer(
        origin="HSV",
        destination="JFK",
        departure_date=depart,
        return_date=depart + timedelta(days=7),
        price_total=400.0,
        booking_url="https://example.com/flight",
        raw="{}",
    )


def _fake_hotel(depart):
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


def _fake_food():
    return FoodEstimate(
        city="New York",
        country="United States",
        cost_per_person_per_day=50.0,
        total_cost=200.0,
        source="fallback",
    )


def test_run_log_api_calls_matches_api_usage_delta(pipeline_session):
    """After a mock run, run_log.api_calls_flights == 0 and api_usage has 0 calls.

    In mock mode, no live calls are made. Both counters must agree on 0.
    This prevents the 40 vs 7 discrepancy seen on 2026-04-25.
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

    with (
        patch("main.init_db"),
        patch("main.SessionFactory", pipeline_session),
        patch(
            "main.select_daily_batch",
            return_value=[
                SimpleNamespace(
                    iata_code="JFK",
                    city="New York",
                    country="United States",
                    region="North America",
                    excluded=False,
                    last_queried_at=None,
                    query_count=0,
                    last_known_price_usd=None,
                    last_known_price_date=None,
                )
            ],
        ),
        patch("main.find_cheapest_in_window", return_value=(good_cost, depart, 0, 0)),
        patch("main.get_airport_info", return_value=_fake_airport()),
        patch("main.get_flight_offers", return_value=_fake_flight(depart)),
        patch("main.get_hotel_offers", return_value=_fake_hotel(depart)),
        patch("main.get_food_cost", return_value=_fake_food()),
        patch("main.send_trip_notification", return_value=True),
    ):
        main.run()

    with pipeline_session() as s:
        run = s.query(RunLog).order_by(RunLog.id.desc()).first()
        api_row = (
            s.query(ApiUsage).filter(ApiUsage.api_name == "google_flights").first()
        )

    # Mock mode: no live calls at all
    assert run is not None
    assert run.status == "success"
    assert run.api_calls_flights == 0

    # api_usage should be absent or 0 in pure mock mode
    assert api_row is None or api_row.calls_made == 0
