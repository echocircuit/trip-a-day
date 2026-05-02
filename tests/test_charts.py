"""Tests for chart generation edge cases — no visual assertions, only type/None checks."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from trip_a_day.charts import generate_price_history_chart
from trip_a_day.db import Base, Trip

BASE_DATE = date(2026, 1, 1)
# FAR_DATE is more than 30 days after BASE_DATE, so BASE_DATE-anchored trips fall
# outside Series 1's 30-day window when FAR_DATE is used as today_run_date.
FAR_DATE = date(2030, 1, 1)


def _make_trip(
    iata: str,
    run_date: date,
    total_cost: float,
    *,
    selected: bool = False,
    is_mock: bool = False,
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
        is_mock=is_mock,
    )


def _build_engine(trips: list[Trip]):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        for t in trips:
            s.add(t)
        s.commit()
    return engine


# ── Series-1-only tests ───────────────────────────────────────────────────────


def test_returns_none_with_fewer_than_3_s1_points_and_no_s2():
    """2 points in window, no S2 → None."""
    today = BASE_DATE + timedelta(days=10)
    trips = [
        _make_trip("MCO", BASE_DATE, 1000.0),
        _make_trip("MCO", BASE_DATE + timedelta(days=1), 1050.0),
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "MCO", "Orlando, USA", 1050.0, today, session
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
    """5 trips within 30 days → Series 1 renders."""
    today = BASE_DATE + timedelta(days=25)
    trips = [
        _make_trip("MCO", BASE_DATE + timedelta(days=i), 1000.0 + i * 10)
        for i in range(5)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "MCO", "Orlando, USA", 1040.0, today, session
        )
    assert result is not None
    assert isinstance(result, bytes)


def test_returned_bytes_are_valid_png():
    """PNG magic bytes must be present."""
    today = BASE_DATE + timedelta(days=25)
    trips = [
        _make_trip("JFK", BASE_DATE + timedelta(days=i), 2000.0 + i * 5)
        for i in range(4)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "JFK", "New York, USA", 2015.0, today, session
        )
    assert result is not None
    assert result[:4] == b"\x89PNG"


def test_does_not_raise_when_today_cost_higher_than_all_history():
    today = BASE_DATE + timedelta(days=25)
    trips = [_make_trip("LAX", BASE_DATE + timedelta(days=i), 500.0) for i in range(5)]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "LAX", "Los Angeles, USA", 9999.0, today, session
        )
    assert result is None or isinstance(result, bytes)


def test_does_not_raise_when_today_cost_lower_than_all_history():
    today = BASE_DATE + timedelta(days=25)
    trips = [_make_trip("LAX", BASE_DATE + timedelta(days=i), 5000.0) for i in range(5)]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "LAX", "Los Angeles, USA", 1.0, today, session
        )
    assert result is None or isinstance(result, bytes)


def test_does_not_raise_when_all_historical_values_identical():
    today = BASE_DATE + timedelta(days=25)
    trips = [
        _make_trip("ORD", BASE_DATE + timedelta(days=i), 1234.56) for i in range(5)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "ORD", "Chicago, USA", 1234.56, today, session
        )
    assert result is None or isinstance(result, bytes)


def test_uses_7_point_rolling_window_when_enough_data():
    """10 trips within 30 days → rolling average path exercised."""
    today = BASE_DATE + timedelta(days=29)
    trips = [
        _make_trip("SEA", BASE_DATE + timedelta(days=i), 1000.0 + i * 20)
        for i in range(10)
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "SEA", "Seattle, USA", 1180.0, today, session
        )
    assert result is not None
    assert result[:4] == b"\x89PNG"


# ── 30-day window boundary tests ──────────────────────────────────────────────


def test_s1_filters_to_30_days_trips_outside_window_not_counted():
    """Trips older than 30 days must not contribute to Series 1."""
    today = BASE_DATE + timedelta(days=50)
    # 5 trips well outside the 30-day window (> 30 days before today)
    old_trips = [
        _make_trip("MCO", BASE_DATE + timedelta(days=i), 900.0 + i * 10)
        for i in range(5)
    ]
    # Only 2 trips within the window — below the 3-point threshold
    recent_trips = [
        _make_trip("MCO", today - timedelta(days=5), 950.0),
        _make_trip("MCO", today - timedelta(days=2), 960.0),
    ]
    engine = _build_engine(old_trips + recent_trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "MCO", "Orlando, USA", 960.0, today, session
        )
    # Only 2 points in the 30-day window, no S2 → None
    assert result is None


def test_s1_includes_trips_within_30_days():
    """Trips exactly within the 30-day window must be counted."""
    today = BASE_DATE + timedelta(days=50)
    trips = [
        _make_trip("MCO", today - timedelta(days=29), 1000.0),
        _make_trip("MCO", today - timedelta(days=20), 1010.0),
        _make_trip("MCO", today - timedelta(days=10), 1020.0),
        _make_trip("MCO", today - timedelta(days=1), 1030.0),
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "MCO", "Orlando, USA", 1030.0, today, session
        )
    assert result is not None
    assert result[:4] == b"\x89PNG"


def test_s2_filters_to_30_days():
    """Selected trips older than 30 days must not contribute to Series 2."""
    today = BASE_DATE + timedelta(days=60)
    # S1: 4 trips within 30 days
    s1_trips = [
        _make_trip("DEN", today - timedelta(days=i * 5), 800.0 + i * 10)
        for i in range(4)
    ]
    # S2: 5 selected trips, but all older than 30 days
    old_selected = [
        _make_trip("LAS", today - timedelta(days=31 + i), 700.0, selected=True)
        for i in range(5)
    ]
    engine = _build_engine(s1_trips + old_selected)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "DEN", "Denver, USA", 840.0, today, session
        )
    # S1 has 4 points so chart renders, but S2 is empty (all outside window)
    assert result is not None  # S1 alone renders
    assert result[:4] == b"\x89PNG"


# ── Series-2 degradation tests ────────────────────────────────────────────────


def test_s2_omitted_when_fewer_than_3_recent_picks():
    """Only 2 selected trips in the past 30 days — S2 requires ≥3, so it is skipped."""
    today = BASE_DATE + timedelta(days=20)
    trips = (
        # Series 1: 5 history points within 30 days
        [
            _make_trip("DEN", BASE_DATE + timedelta(days=i), 800.0 + i * 10)
            for i in range(5)
        ]
        # Series 2: only 2 recent picks — below the 3-point threshold
        + [
            _make_trip("DEN", today - timedelta(days=2), 815.0, selected=True),
            _make_trip("DEN", today - timedelta(days=1), 820.0, selected=True),
        ]
    )
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "DEN", "Denver, USA", 850.0, today, session
        )
    # Series 1 has 5 points (≥3) so chart renders; Series 2 is omitted silently
    assert result is not None
    assert result[:4] == b"\x89PNG"


def test_renders_s2_only_when_s1_has_fewer_than_3_points():
    """Destination has only 2 history points — S1 skipped, S2 (≥3) renders."""
    today = BASE_DATE + timedelta(days=10)
    trips = [
        # Series 1: only 2 points within 30 days — below threshold
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
    # Series 2 has 3 points (≥3) so chart renders despite S1 being insufficient
    assert result is not None
    assert result[:4] == b"\x89PNG"


def test_returns_none_when_both_series_below_3_points():
    """Both series with < 3 points → None."""
    today = BASE_DATE + timedelta(days=10)
    trips = [
        _make_trip("MIA", BASE_DATE, 900.0),
        _make_trip("MIA", BASE_DATE + timedelta(days=1), 920.0),
        _make_trip("LAS", today - timedelta(days=1), 700.0, selected=True),
        _make_trip("ATL", today - timedelta(days=2), 750.0, selected=True),
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "MIA", "Miami, USA", 900.0, today, session
        )
    assert result is None


def test_both_series_sufficient_renders_valid_png():
    """Both series have ≥3 data points — chart renders."""
    today = BASE_DATE + timedelta(days=15)
    trips = (
        # Series 1: 5 history points for target within 30 days
        [
            _make_trip("BOS", BASE_DATE + timedelta(days=i), 1100.0 + i * 15)
            for i in range(5)
        ]
        # Series 2: 5 recent picks within 30 days
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
    """Today's destination appearing in both series must not raise."""
    today = BASE_DATE + timedelta(days=10)
    trips = [
        _make_trip("SFO", BASE_DATE + timedelta(days=i), 1200.0 + i * 10)
        for i in range(5)
    ] + [
        _make_trip("PDX", today - timedelta(days=2), 800.0, selected=True),
        _make_trip("SLC", today - timedelta(days=1), 750.0, selected=True),
        _make_trip("SFO", today, 1240.0, selected=True),
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "SFO", "San Francisco, USA", 1240.0, today, session
        )
    assert result is not None
    assert isinstance(result, bytes)


def test_png_bytes_do_not_contain_city_name_strings():
    """City names must not appear as literal text bytes in the PNG output.

    matplotlib rasterises annotations into pixels; this test guards against
    any future change that might embed city names in PNG text chunks.
    """
    today = BASE_DATE + timedelta(days=15)
    trips = [
        _make_trip("CDG", BASE_DATE + timedelta(days=i), 1500.0 + i * 20)
        for i in range(5)
    ] + [
        _make_trip("NRT", today - timedelta(days=4), 1600.0, selected=True),
        _make_trip("LHR", today - timedelta(days=3), 1400.0, selected=True),
        _make_trip("DXB", today - timedelta(days=2), 1300.0, selected=True),
        _make_trip("CDG", today - timedelta(days=1), 1500.0, selected=True),
        _make_trip("CDG", today, 1520.0, selected=True),
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "CDG", "Paris, France", 1520.0, today, session
        )
    assert result is not None
    # "Paris" must not appear as raw UTF-8 text in the PNG byte stream
    assert b"Paris" not in result
    assert b"Tokyo" not in result


# ── Mock-run filtering tests ──────────────────────────────────────────────────


def test_mock_trips_excluded_from_s1():
    """Series 1 must not include trips where is_mock=True.

    5 mock trips + 2 live trips for the same destination → only 2 live points
    counted, below the 3-point threshold, so the chart returns None.
    """
    today = BASE_DATE + timedelta(days=25)
    trips = [
        _make_trip("ORD", BASE_DATE + timedelta(days=i), 900.0 + i * 10, is_mock=True)
        for i in range(5)
    ] + [
        _make_trip("ORD", BASE_DATE + timedelta(days=10), 950.0),
        _make_trip("ORD", BASE_DATE + timedelta(days=11), 960.0),
    ]
    engine = _build_engine(trips)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "ORD", "Chicago, USA", 960.0, today, session
        )
    # Only 2 live S1 points, no live S2 → None
    assert result is None


def test_mock_trips_excluded_from_s2():
    """Series 2 must not include selected trips where is_mock=True.

    S1 has 4 live points (renders). S2 has 5 mock selected picks and 2 live
    selected picks — only the 2 live picks count, below the 3-point threshold,
    so S2 is omitted (chart still renders via S1 alone).
    """
    today = BASE_DATE + timedelta(days=25)
    s1_trips = [
        _make_trip("BOS", BASE_DATE + timedelta(days=i), 1100.0 + i * 10)
        for i in range(4)
    ]
    mock_selected = [
        _make_trip(
            "LAS", today - timedelta(days=5 + i), 700.0, selected=True, is_mock=True
        )
        for i in range(5)
    ]
    live_selected = [
        _make_trip("ATL", today - timedelta(days=2), 750.0, selected=True),
        _make_trip("MIA", today - timedelta(days=1), 800.0, selected=True),
    ]
    engine = _build_engine(s1_trips + mock_selected + live_selected)
    with Session(engine) as session:
        result = generate_price_history_chart(
            "BOS", "Boston, USA", 1130.0, today, session
        )
    # S1 renders (4 live points). S2 has only 2 live picks → omitted silently.
    assert result is not None
    assert result[:4] == b"\x89PNG"
