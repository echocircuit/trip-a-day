"""Tests for links.py URL builders — no DB or env vars required."""

from __future__ import annotations

from datetime import date

import pytest

from trip_a_day.links import build_car_url, build_flight_url, build_hotel_url

_DEPART = date(2026, 6, 15)
_RETURN = date(2026, 6, 22)
_CHECKIN = date(2026, 6, 15)
_CHECKOUT = date(2026, 6, 22)


class TestBuildFlightUrl:
    def test_returns_nonempty_string(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert url and isinstance(url, str)

    def test_contains_google_flights_domain(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert "google.com/flights" in url

    def test_contains_origin_and_destination(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert "HSV" in url
        assert "CDG" in url

    def test_contains_dates(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert "2026-06-15" in url
        assert "2026-06-22" in url

    def test_no_airline_iata_omits_airline_param(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert ";a:" not in url

    def test_airline_iata_appended_when_provided(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN, airline_iata="DL")
        assert ";a:DL" in url

    def test_hash_is_literal_not_encoded(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert "#flt=" in url
        assert "%23" not in url

    def test_asterisk_is_literal_not_encoded(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert "*" in url
        assert "%2A" not in url

    def test_airline_omitted_when_none(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN, airline_iata=None)
        assert ";a:" not in url

    def test_airline_omitted_when_empty_string(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN, airline_iata="")
        assert ";a:" not in url

    def test_airline_omitted_when_not_two_chars(self):
        url = build_flight_url(
            "HSV",
            "CDG",
            _DEPART,
            _RETURN,
            airline_iata="American Airlines operated by Skywest",
        )
        assert ";a:" not in url

    def test_airline_omitted_when_three_chars(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN, airline_iata="DAL")
        assert ";a:" not in url

    def test_alphanumeric_two_char_airline_accepted(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN, airline_iata="B6")
        assert ";a:B6" in url

    def test_airline_normalized_to_uppercase(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN, airline_iata="dl")
        assert ";a:DL" in url


class TestBuildHotelUrl:
    def test_google_hotels_returns_nonempty(self):
        url = build_hotel_url(
            "Paris", "France", _CHECKIN, _CHECKOUT, 2, 2, 1, "google_hotels"
        )
        assert url and isinstance(url, str)

    def test_google_hotels_contains_expected_params(self):
        url = build_hotel_url(
            "Paris", "France", _CHECKIN, _CHECKOUT, 2, 2, 1, "google_hotels"
        )
        assert "google.com/travel/hotels" in url
        assert "checkin=2026-06-15" in url
        assert "checkout=2026-06-22" in url

    def test_booking_com_returns_nonempty(self):
        url = build_hotel_url(
            "Paris", "France", _CHECKIN, _CHECKOUT, 2, 2, 1, "booking_com"
        )
        assert url and isinstance(url, str)

    def test_booking_com_contains_expected_params(self):
        url = build_hotel_url(
            "Paris", "France", _CHECKIN, _CHECKOUT, 2, 2, 1, "booking_com"
        )
        assert "booking.com/searchresults" in url
        assert "group_adults=2" in url
        assert "no_rooms=1" in url

    def test_expedia_returns_nonempty(self):
        url = build_hotel_url(
            "Paris", "France", _CHECKIN, _CHECKOUT, 2, 2, 1, "expedia"
        )
        assert url and isinstance(url, str)

    def test_expedia_uses_slash_date_format(self):
        url = build_hotel_url(
            "Paris", "France", _CHECKIN, _CHECKOUT, 2, 2, 1, "expedia"
        )
        assert "expedia.com/Hotel-Search" in url
        assert "06/15/2026" in url

    def test_unknown_site_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown hotel site"):
            build_hotel_url(
                "Paris", "France", _CHECKIN, _CHECKOUT, 2, 2, 1, "unknown_site"
            )


class TestBuildCarUrl:
    def test_kayak_returns_nonempty(self):
        url = build_car_url("CDG", "Paris", _DEPART, _RETURN, "kayak")
        assert url and isinstance(url, str)

    def test_kayak_contains_iata_and_dates(self):
        url = build_car_url("CDG", "Paris", _DEPART, _RETURN, "kayak")
        assert "kayak.com/cars/CDG" in url
        assert "2026-06-15" in url
        assert "2026-06-22" in url

    def test_expedia_cars_returns_nonempty(self):
        url = build_car_url("CDG", "Paris", _DEPART, _RETURN, "expedia_cars")
        assert url and isinstance(url, str)

    def test_expedia_cars_uses_slash_date_format(self):
        url = build_car_url("CDG", "Paris", _DEPART, _RETURN, "expedia_cars")
        assert "expedia.com/carsearch" in url
        assert "06/15/2026" in url

    def test_unknown_site_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown car site"):
            build_car_url("CDG", "Paris", _DEPART, _RETURN, "unknown_site")
