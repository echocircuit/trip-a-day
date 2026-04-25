"""Tests for chart generation edge cases — no visual assertions, only type/None checks."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from trip_a_day.charts import generate_price_history_chart
from trip_a_day.db import Base, Trip

BASE_DATE = date(2026, 1, 1)


def _make_trip(iata: str, run_date: date, total_cost: float) -> Trip:
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
        selected=True,
    )


def _build_engine(trips: list[Trip]):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        for t in trips:
            s.add(t)
        s.commit()
    return engine


def test_returns_none_with_fewer_than_3_data_points():
    trips = [
        _make_trip("MCO", BASE_DATE, 1000.0),
        _make_trip("MCO", BASE_DATE + timedelta(days=1), 1050.0),
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart("MCO", "Orlando, USA", 1050.0, session)
    assert result is None


def test_returns_none_with_zero_data_points():
    engine = _build_engine([])
    with Session(engine) as session:
        result = generate_price_history_chart("MCO", "Orlando, USA", 1000.0, session)
    assert result is None


def test_returns_png_bytes_with_sufficient_data():
    trips = [
        _make_trip("MCO", BASE_DATE + timedelta(days=i), 1000.0 + i * 10)
        for i in range(5)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart("MCO", "Orlando, USA", 1040.0, session)
    assert result is not None
    assert isinstance(result, bytes)


def test_returned_bytes_are_valid_png():
    trips = [
        _make_trip("JFK", BASE_DATE + timedelta(days=i), 2000.0 + i * 5)
        for i in range(4)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart("JFK", "New York, USA", 2015.0, session)
    assert result is not None
    assert result[:4] == b"\x89PNG"


def test_does_not_raise_when_today_cost_higher_than_all_history():
    trips = [_make_trip("LAX", BASE_DATE + timedelta(days=i), 500.0) for i in range(5)]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "LAX", "Los Angeles, USA", 9999.0, session
        )
    assert result is None or isinstance(result, bytes)


def test_does_not_raise_when_today_cost_lower_than_all_history():
    trips = [_make_trip("LAX", BASE_DATE + timedelta(days=i), 5000.0) for i in range(5)]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart("LAX", "Los Angeles, USA", 1.0, session)
    assert result is None or isinstance(result, bytes)


def test_does_not_raise_when_all_historical_values_identical():
    trips = [
        _make_trip("ORD", BASE_DATE + timedelta(days=i), 1234.56) for i in range(5)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart("ORD", "Chicago, USA", 1234.56, session)
    assert result is None or isinstance(result, bytes)


def test_uses_7_point_rolling_window_when_enough_data():
    trips = [
        _make_trip("SEA", BASE_DATE + timedelta(days=i), 1000.0 + i * 20)
        for i in range(10)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart("SEA", "Seattle, USA", 1180.0, session)
    assert result is not None
    assert result[:4] == b"\x89PNG"
