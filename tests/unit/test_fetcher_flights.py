"""Unit tests for fli-based flight fetching in fetcher.py.

get_flights is mocked so these tests run without any API calls.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from trip_a_day.fetcher import _airport, get_flight_offers


def _make_flight(stops: int, price: str) -> SimpleNamespace:
    return SimpleNamespace(stops=stops, price=price, name="Test Airline")


def _mock_result(flights: list) -> SimpleNamespace:
    return SimpleNamespace(flights=flights)


@pytest.fixture()
def mock_session(monkeypatch):
    """Minimal session stub — forces live code path so get_flights patches apply."""
    monkeypatch.setenv("FLIGHT_DATA_MODE", "live")
    session = object()  # DB functions are patched; session value is irrelevant
    with (
        patch("trip_a_day.fetcher.get_api_calls_today", return_value=0),
        patch("trip_a_day.fetcher.record_api_call"),
    ):
        yield session


DEPART = date(2026, 6, 1)
RETURN = date(2026, 6, 8)


class TestDirectOnlyFiltering:
    def test_direct_only_true_returns_direct_flight(self, mock_session):
        direct = _make_flight(stops=0, price="$500")
        connecting = _make_flight(stops=1, price="$300")
        with patch(
            "trip_a_day.fetcher.get_flights",
            return_value=_mock_result([direct, connecting]),
        ):
            offer = get_flight_offers(
                "HSV", "LHR", DEPART, RETURN, 2, 0, mock_session, direct_only=True
            )
        assert offer is not None
        assert offer.price_total == 500.0

    def test_direct_only_true_returns_none_when_only_connecting(self, mock_session):
        connecting = _make_flight(stops=1, price="$300")
        with patch(
            "trip_a_day.fetcher.get_flights", return_value=_mock_result([connecting])
        ):
            offer = get_flight_offers(
                "HSV", "LHR", DEPART, RETURN, 2, 0, mock_session, direct_only=True
            )
        assert offer is None

    def test_direct_only_false_accepts_connecting_when_no_direct(self, mock_session):
        connecting = _make_flight(stops=1, price="$300")
        with patch(
            "trip_a_day.fetcher.get_flights", return_value=_mock_result([connecting])
        ):
            offer = get_flight_offers(
                "HSV", "LHR", DEPART, RETURN, 2, 0, mock_session, direct_only=False
            )
        assert offer is not None
        assert offer.price_total == 300.0

    def test_direct_only_false_still_prefers_direct(self, mock_session):
        direct = _make_flight(stops=0, price="$500")
        connecting = _make_flight(stops=1, price="$300")
        with patch(
            "trip_a_day.fetcher.get_flights",
            return_value=_mock_result([direct, connecting]),
        ):
            offer = get_flight_offers(
                "HSV", "LHR", DEPART, RETURN, 2, 0, mock_session, direct_only=False
            )
        assert offer is not None
        assert offer.price_total == 500.0

    def test_default_is_direct_only(self, mock_session):
        connecting = _make_flight(stops=1, price="$300")
        with patch(
            "trip_a_day.fetcher.get_flights", return_value=_mock_result([connecting])
        ):
            offer = get_flight_offers("HSV", "LHR", DEPART, RETURN, 2, 0, mock_session)
        assert offer is None

    def test_cheapest_nonstop_selected_not_first(self, mock_session):
        """When multiple nonstop flights exist, select by price not list position."""
        expensive = _make_flight(stops=0, price="$600")
        cheaper = _make_flight(stops=0, price="$400")
        cheapest = _make_flight(stops=0, price="$350")
        with patch(
            "trip_a_day.fetcher.get_flights",
            return_value=_mock_result([expensive, cheaper, cheapest]),
        ):
            offer = get_flight_offers(
                "HSV", "LHR", DEPART, RETURN, 1, 0, mock_session, direct_only=True
            )
        assert offer is not None
        assert offer.price_total == 350.0

    def test_direct_only_excludes_connecting_before_price_sort(self, mock_session):
        """Connecting flights are excluded even when they are cheaper than nonstop."""
        nonstop_expensive = _make_flight(stops=0, price="$800")
        connecting_cheap = _make_flight(stops=1, price="$200")
        with patch(
            "trip_a_day.fetcher.get_flights",
            return_value=_mock_result([nonstop_expensive, connecting_cheap]),
        ):
            offer = get_flight_offers(
                "HSV", "LHR", DEPART, RETURN, 1, 0, mock_session, direct_only=True
            )
        assert offer is not None
        assert offer.price_total == 800.0

    def test_deep_link_encodes_direct_only(self, mock_session):
        """booking_url differs between direct_only=True and direct_only=False."""
        direct_flight = _make_flight(stops=0, price="$400")
        with patch(
            "trip_a_day.fetcher.get_flights",
            return_value=_mock_result([direct_flight]),
        ):
            offer_direct = get_flight_offers(
                "HSV", "LHR", DEPART, RETURN, 1, 0, mock_session, direct_only=True
            )
            offer_any = get_flight_offers(
                "HSV", "LHR", DEPART, RETURN, 1, 0, mock_session, direct_only=False
            )
        assert offer_direct is not None
        assert offer_any is not None
        assert offer_direct.booking_url != offer_any.booking_url


class TestAirportHelper:
    def test_known_iata_returns_enum(self):
        """_airport('HSV') returns the Airport enum member for Huntsville."""
        from fli.models import Airport

        result = _airport("HSV")
        assert result is Airport.HSV

    def test_known_iata_lhr(self):
        from fli.models import Airport

        assert _airport("LHR") is Airport.LHR

    def test_unknown_iata_raises_value_error(self):
        """_airport raises ValueError for IATA codes absent from the fli enum."""
        with pytest.raises(ValueError, match="ZZZ"):
            _airport("ZZZ")

    def test_seed_absent_codes_raise(self):
        """REP, PNH, FRU are the three seed airports absent from fli; all raise."""
        for code in ("REP", "PNH", "FRU"):
            with pytest.raises(ValueError):
                _airport(code)


class TestUnsupportedAirportGracefulSkip:
    def test_unsupported_destination_returns_none(self, mock_session):
        """get_flight_offers returns None (not raises) for airports outside fli enum."""
        with patch(
            "trip_a_day.fetcher.get_flights",
            side_effect=ValueError("Airport 'ZZZ' is not supported by fli"),
        ):
            offer = get_flight_offers(
                "HSV", "ZZZ", DEPART, RETURN, 2, 0, mock_session, direct_only=True
            )
        assert offer is None

    def test_unsupported_origin_returns_none(self, mock_session):
        """ValueError from _airport() in origin position also returns None."""
        with patch(
            "trip_a_day.fetcher.get_flights",
            side_effect=ValueError("Airport 'FRU' is not supported by fli"),
        ):
            offer = get_flight_offers(
                "FRU", "LHR", DEPART, RETURN, 2, 0, mock_session, direct_only=True
            )
        assert offer is None
