"""Tests for links.py URL builders — no DB or env vars required."""

from __future__ import annotations

import base64
import re
from datetime import date

import pytest

from trip_a_day.links import build_car_url, build_flight_url, build_hotel_url

_DEPART = date(2026, 6, 15)
_RETURN = date(2026, 6, 22)
_CHECKIN = date(2026, 6, 15)
_CHECKOUT = date(2026, 6, 22)


def _decode_tfs(url: str) -> str:
    """Extract and base64-decode the tfs= parameter from a Google Flights URL."""
    m = re.search(r"[?&]tfs=([^&]+)", url)
    assert m, f"No tfs= parameter found in URL: {url}"
    b64 = m.group(1)
    raw = base64.b64decode(b64 + "==")  # pad to be safe
    return raw.decode("latin-1")


class TestBuildFlightUrl:
    def test_returns_nonempty_string(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert url and isinstance(url, str)

    def test_contains_google_flights_domain(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert "google.com/travel/flights" in url

    def test_uses_tfs_parameter(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert "tfs=" in url

    def test_old_flt_fragment_not_used(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert "#flt=" not in url

    def test_tfs_contains_origin(self):
        decoded = _decode_tfs(build_flight_url("HSV", "CDG", _DEPART, _RETURN))
        assert "HSV" in decoded

    def test_tfs_contains_destination(self):
        decoded = _decode_tfs(build_flight_url("HSV", "CDG", _DEPART, _RETURN))
        assert "CDG" in decoded

    def test_tfs_contains_depart_date(self):
        decoded = _decode_tfs(build_flight_url("HSV", "CDG", _DEPART, _RETURN))
        assert "2026-06-15" in decoded

    def test_tfs_contains_return_date(self):
        decoded = _decode_tfs(build_flight_url("HSV", "CDG", _DEPART, _RETURN))
        assert "2026-06-22" in decoded

    def test_url_includes_hl_en(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert "hl=en" in url

    def test_url_includes_curr_usd(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        assert "curr=USD" in url

    def test_different_airports_produce_different_urls(self):
        url1 = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        url2 = build_flight_url("HSV", "NRT", _DEPART, _RETURN)
        assert url1 != url2

    def test_different_dates_produce_different_urls(self):
        url1 = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        url2 = build_flight_url("HSV", "CDG", date(2026, 7, 1), date(2026, 7, 8))
        assert url1 != url2

    def test_adults_and_children_default_accepted(self):
        url = build_flight_url("HSV", "CDG", _DEPART, _RETURN, adults=2, children=2)
        assert url and isinstance(url, str)

    def test_tfs_changes_with_passenger_count(self):
        url1 = build_flight_url("HSV", "CDG", _DEPART, _RETURN, adults=1, children=0)
        url2 = build_flight_url("HSV", "CDG", _DEPART, _RETURN, adults=2, children=2)
        assert url1 != url2

    def test_direct_only_true_produces_different_url_than_false(self):
        """direct_only=True encodes max_stops=0; URL must differ from default."""
        url_direct = build_flight_url("HSV", "CDG", _DEPART, _RETURN, direct_only=True)
        url_any = build_flight_url("HSV", "CDG", _DEPART, _RETURN, direct_only=False)
        assert url_direct != url_any

    def test_direct_only_false_is_default(self):
        """direct_only defaults to False; explicit False and default must produce same URL."""
        url_default = build_flight_url("HSV", "CDG", _DEPART, _RETURN)
        url_explicit = build_flight_url(
            "HSV", "CDG", _DEPART, _RETURN, direct_only=False
        )
        assert url_default == url_explicit

    def test_passenger_count_2_adults_differs_from_1(self):
        """Passenger count is embedded in tfs; 2-adult URL must differ from 1-adult URL."""
        url1 = build_flight_url("HSV", "CDG", _DEPART, _RETURN, adults=1, children=0)
        url2 = build_flight_url("HSV", "CDG", _DEPART, _RETURN, adults=2, children=0)
        assert url1 != url2


_CHECKIN_OCT = date(2026, 10, 5)
_CHECKOUT_OCT = date(2026, 10, 9)


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
        assert "check_in_date=2026-06-15" in url
        assert "check_out_date=2026-06-22" in url

    def test_google_hotels_checkin_iso_format(self):
        """Google Hotels requires check_in_date/check_out_date params in YYYY-MM-DD format."""
        url = build_hotel_url(
            "Tokyo", "Japan", _CHECKIN_OCT, _CHECKOUT_OCT, 1, 0, 1, "google_hotels"
        )
        assert "check_in_date=2026-10-05" in url
        assert "check_out_date=2026-10-09" in url

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

    def test_booking_com_split_date_params_no_leading_zeros(self):
        """Booking.com requires split year/month/day params without leading zeros."""
        url = build_hotel_url(
            "Tokyo", "Japan", _CHECKIN_OCT, _CHECKOUT_OCT, 1, 0, 1, "booking_com"
        )
        assert "checkin_year=2026" in url
        assert "checkin_month=10" in url
        assert "checkin_monthday=5" in url  # no leading zero
        assert "checkout_year=2026" in url
        assert "checkout_month=10" in url
        assert "checkout_monthday=9" in url  # no leading zero

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

    def test_expedia_mm_dd_yyyy_format(self):
        """Expedia requires MM/DD/YYYY for startDate and endDate."""
        url = build_hotel_url(
            "Tokyo", "Japan", _CHECKIN_OCT, _CHECKOUT_OCT, 1, 0, 1, "expedia"
        )
        assert "startDate=10/05/2026" in url
        assert "endDate=10/09/2026" in url

    def test_checkout_date_present_in_all_sites(self):
        """Checkout date must appear in every supported site's URL."""
        for site in ("google_hotels", "booking_com", "expedia"):
            url = build_hotel_url(
                "Tokyo", "Japan", _CHECKIN_OCT, _CHECKOUT_OCT, 1, 0, 1, site
            )
            # Each site encodes checkout differently; verify 2026 and 9 both appear
            assert "2026" in url, f"{site}: year missing from checkout"
            if site == "google_hotels":
                assert "check_out_date=2026-10-09" in url
            elif site == "booking_com":
                assert "checkout_monthday=9" in url
            elif site == "expedia":
                assert "endDate=10/09/2026" in url

    def test_date_object_and_iso_string_produce_same_result(self):
        """Passing a date object should produce identical output to parsing an ISO string."""
        from datetime import date as dt

        checkin_obj = dt(2026, 10, 5)
        url_obj = build_hotel_url(
            "Tokyo", "Japan", checkin_obj, dt(2026, 10, 9), 1, 0, 1, "google_hotels"
        )
        url_iso = build_hotel_url(
            "Tokyo",
            "Japan",
            dt.fromisoformat("2026-10-05"),
            dt.fromisoformat("2026-10-09"),
            1,
            0,
            1,
            "google_hotels",
        )
        assert url_obj == url_iso

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
