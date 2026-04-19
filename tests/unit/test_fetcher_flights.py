"""Unit tests for direct_only flight filtering in fetcher.py.

get_flights is mocked so these tests run without any API calls.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from trip_a_day.fetcher import get_flight_offers


def _make_flight(stops: int, price: str) -> SimpleNamespace:
    return SimpleNamespace(stops=stops, price=price, name="Test Airline")


def _mock_result(flights: list) -> SimpleNamespace:
    return SimpleNamespace(flights=flights)


@pytest.fixture()
def mock_session():
    """Minimal session stub — patch the names as imported into fetcher's namespace."""
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
