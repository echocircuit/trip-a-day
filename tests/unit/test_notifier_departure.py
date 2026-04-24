"""Tests for departure-airport display in notifier.py HTML and plain text."""

from __future__ import annotations

from datetime import date

from trip_a_day.costs import CostBreakdown
from trip_a_day.notifier import _build_html, _build_plain
from trip_a_day.ranker import TripCandidate

_DEPART = date(2026, 6, 15)
_RETURN = date(2026, 6, 22)


def _make_trip(
    departure_airport: str = "", transport_usd: float = 0.0
) -> TripCandidate:
    cost = CostBreakdown(
        flights=800.0,
        hotel=700.0,
        car=200.0,
        food=150.0,
        car_is_estimate=True,
        transport_usd=transport_usd,
    )
    return TripCandidate(
        destination_iata="CDG",
        city="Paris",
        country="France",
        region="Western Europe",
        departure_date=_DEPART,
        return_date=_RETURN,
        cost=cost,
        distance_miles=4500.0,
        flight_booking_url="https://example.com/flights",
        hotel_booking_url="https://example.com/hotel",
        car_booking_url="https://example.com/car",
        raw_flight_data="{}",
        raw_hotel_data="{}",
        departure_airport=departure_airport,
    )


class TestDepLineHtml:
    def test_home_airport_shows_departing_from(self):
        html = _build_html(_make_trip("HSV"), home_airport="HSV")
        assert "Departing from:" in html

    def test_home_airport_no_warning(self):
        html = _build_html(_make_trip("HSV"), home_airport="HSV")
        assert "Not your home airport" not in html

    def test_non_home_airport_shows_warning(self):
        html = _build_html(_make_trip("BHM", transport_usd=30.0), home_airport="HSV")
        assert "Not your home airport" in html
        assert "HSV" in html

    def test_non_home_airport_shows_iata(self):
        html = _build_html(_make_trip("BHM", transport_usd=30.0), home_airport="HSV")
        assert "BHM" in html

    def test_no_departure_airport_omits_line(self):
        html = _build_html(_make_trip(""), home_airport="HSV")
        assert "Departing from:" not in html

    def test_transport_cost_banner_present_for_non_home(self):
        html = _build_html(_make_trip("BHM", transport_usd=30.0), home_airport="HSV")
        assert "IRS mileage estimate" in html

    def test_transport_cost_banner_absent_for_home(self):
        html = _build_html(_make_trip("HSV"), home_airport="HSV")
        assert "IRS mileage estimate" not in html


class TestDepLinePlain:
    def test_home_airport_shows_departing_from(self):
        plain = _build_plain(_make_trip("HSV"), home_airport="HSV")
        assert "Departing from:" in plain

    def test_home_airport_no_warning(self):
        plain = _build_plain(_make_trip("HSV"), home_airport="HSV")
        assert "Not your home airport" not in plain

    def test_non_home_airport_shows_warning(self):
        plain = _build_plain(_make_trip("BHM", transport_usd=30.0), home_airport="HSV")
        assert "Not your home airport" in plain
        assert "HSV" in plain

    def test_non_home_airport_shows_transport_cost(self):
        plain = _build_plain(_make_trip("BHM", transport_usd=30.0), home_airport="HSV")
        assert "$30" in plain
        assert "transport" in plain

    def test_no_departure_airport_omits_line(self):
        plain = _build_plain(_make_trip(""), home_airport="HSV")
        assert "Departing from:" not in plain
