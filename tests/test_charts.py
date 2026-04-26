"""Tests for chart generation edge cases — no visual assertions, only type/None checks."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from trip_a_day.charts import generate_price_history_chart
from trip_a_day.db import Base, Trip

BASE_DATE = date(2026, 1, 1)
# today_run_date used in tests: far enough in the future that no trip qualifies as
# a "recent pick" for Series 2 unless the test explicitly places one within 7 days.
FAR_DATE = date(2030, 1, 1)


def _make_trip(
    iata: str,
    run_date: date,
    total_cost: float,
    *,
    selected: bool = False,
) -> Trip:
    return Trip(
        run_date=run_date,
        destination_iata=iata,
        departure_date=run_date + timedelta(days=7),
        return_date=run_date + timedelta(days=14),
        flight_cost_usd=total_cost * 0.6,
        hotel_cost_usd=total_cost * 0.2,
        car_cost_usd=total_cost * 0.1,
        food_cost_usd=total_cost * 0.1,
        total_cost_usd=total_cost,
        distance_miles=1000.0,
        selected=selected,
    )


def _build_engine(trips: list[Trip]):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        for t in trips:
            s.add(t)
        s.commit()
    return engine


# ── Existing Series-1-only tests (updated for new signature) ──────────────────


def test_returns_none_with_fewer_than_3_s1_points_and_no_s2():
    trips = [
        _make_trip("MCO", BASE_DATE, 1000.0),
        _make_trip("MCO", BASE_DATE + timedelta(days=1), 1050.0),
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "MCO", "Orlando, USA", 1050.0, FAR_DATE, session
        )
    assert result is None


def test_returns_none_with_zero_data_points():
    engine = _build_engine([])
    with Session(engine) as session:
        result = generate_price_history_chart(
            "MCO", "Orlando, USA", 1000.0, FAR_DATE, session
        )
    assert result is None


def test_returns_png_bytes_with_sufficient_s1_data():
    trips = [
        _make_trip("MCO", BASE_DATE + timedelta(days=i), 1000.0 + i * 10)
        for i in range(5)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "MCO", "Orlando, USA", 1040.0, FAR_DATE, session
        )
    assert result is not None
    assert isinstance(result, bytes)


def test_returned_bytes_are_valid_png():
    trips = [
        _make_trip("JFK", BASE_DATE + timedelta(days=i), 2000.0 + i * 5)
        for i in range(4)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "JFK", "New York, USA", 2015.0, FAR_DATE, session
        )
    assert result is not None
    assert result[:4] == b"\x89PNG"


def test_does_not_raise_when_today_cost_higher_than_all_history():
    trips = [_make_trip("LAX", BASE_DATE + timedelta(days=i), 500.0) for i in range(5)]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "LAX", "Los Angeles, USA", 9999.0, FAR_DATE, session
        )
    assert result is None or isinstance(result, bytes)


def test_does_not_raise_when_today_cost_lower_than_all_history():
    trips = [_make_trip("LAX", BASE_DATE + timedelta(days=i), 5000.0) for i in range(5)]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "LAX", "Los Angeles, USA", 1.0, FAR_DATE, session
        )
    assert result is None or isinstance(result, bytes)


def test_does_not_raise_when_all_historical_values_identical():
    trips = [
        _make_trip("ORD", BASE_DATE + timedelta(days=i), 1234.56) for i in range(5)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "ORD", "Chicago, USA", 1234.56, FAR_DATE, session
        )
    assert result is None or isinstance(result, bytes)


def test_uses_7_point_rolling_window_when_enough_data():
    trips = [
        _make_trip("SEA", BASE_DATE + timedelta(days=i), 1000.0 + i * 20)
        for i in range(10)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "SEA", "Seattle, USA", 1180.0, FAR_DATE, session
        )
    assert result is not None
    assert result[:4] == b"\x89PNG"


# ── New Series-2 degradation tests ────────────────────────────────────────────


def test_s2_omitted_when_fewer_than_2_recent_picks():
    """Only 1 selected trip in the past 7 days — Series 2 is skipped, Series 1 renders."""
    today = BASE_DATE + timedelta(days=20)
    trips = (
        # Series 1: 5 history points for the target destination
        [
            _make_trip("DEN", BASE_DATE + timedelta(days=i), 800.0 + i * 10)
            for i in range(5)
        ]
        # Series 2: only 1 recent pick — below the 2-point threshold
        + [_make_trip("DEN", today - timedelta(days=1), 820.0, selected=True)]
    )
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "DEN", "Denver, USA", 850.0, today, session
        )
    # Series 1 has 6 points (≥3) so chart renders; Series 2 is omitted silently
    assert result is not None
    assert result[:4] == b"\x89PNG"


def test_renders_s2_only_when_s1_has_fewer_than_3_points():
    """Destination has only 2 history points — Series 1 skipped, Series 2 renders."""
    today = BASE_DATE + timedelta(days=10)
    trips = [
        # Series 1: only 2 points for destination — below threshold
        _make_trip("MIA", BASE_DATE, 900.0),
        _make_trip("MIA", BASE_DATE + timedelta(days=1), 920.0),
        # Series 2: 3 recent selected picks for various destinations
        _make_trip("LAS", today - timedelta(days=3), 700.0, selected=True),
        _make_trip("ATL", today - timedelta(days=2), 750.0, selected=True),
        _make_trip("MIA", today - timedelta(days=1), 900.0, selected=True),
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "MIA", "Miami, USA", 900.0, today, session
        )
    # Series 2 has 3 points (≥2) so chart renders despite Series 1 being insufficient
    assert result is not None
    assert result[:4] == b"\x89PNG"


def test_both_series_sufficient_renders_valid_png():
    """Both series have enough data — chart should include both."""
    today = BASE_DATE + timedelta(days=15)
    trips = (
        # Series 1: 5 history points for target
        [
            _make_trip("BOS", BASE_DATE + timedelta(days=i), 1100.0 + i * 15)
            for i in range(5)
        ]
        # Series 2: 5 recent picks
        + [
            _make_trip("CDG", today - timedelta(days=4), 1500.0, selected=True),
            _make_trip("NRT", today - timedelta(days=3), 1600.0, selected=True),
            _make_trip("LHR", today - timedelta(days=2), 1400.0, selected=True),
            _make_trip("DXB", today - timedelta(days=1), 1300.0, selected=True),
            _make_trip("BOS", today, 1160.0, selected=True),
        ]
    )
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "BOS", "Boston, USA", 1160.0, today, session
        )
    assert result is not None
    assert result[:4] == b"\x89PNG"


def test_no_raise_when_today_destination_in_both_series():
    """Today's destination appears in both Series 1 history and Series 2 picks."""
    today = BASE_DATE + timedelta(days=10)
    trips = (
        # Series 1: history for SFO
        [
            _make_trip("SFO", BASE_DATE + timedelta(days=i), 1200.0 + i * 10)
            for i in range(5)
        ]
        # Series 2: recent picks ending with SFO today
        + [
            _make_trip("PDX", today - timedelta(days=2), 800.0, selected=True),
            _make_trip("SLC", today - timedelta(days=1), 750.0, selected=True),
            _make_trip("SFO", today, 1240.0, selected=True),
        ]
    )
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "SFO", "San Francisco, USA", 1240.0, today, session
        )
    # Should not raise; result is bytes (both series ≥ threshold)
    assert result is not None
    assert isinstance(result, bytes)
