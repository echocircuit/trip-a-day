"""Tests for travel window logic: model properties, auto-expiry, pipeline integration,
and notifier rendering.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from trip_a_day.costs import CostBreakdown
from trip_a_day.db import TravelWindow
from trip_a_day.notifier import (
    _build_html,
    _build_plain,
    _travel_window_html,
    _travel_window_plain,
)
from trip_a_day.ranker import TripCandidate

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_window(
    *,
    name: str = "Test Window",
    earliest: date = date(2026, 10, 1),
    latest: date = date(2026, 10, 10),
    buffer_start: int = 0,
    buffer_end: int = 0,
    enabled: bool = True,
) -> TravelWindow:
    tw = TravelWindow()
    tw.name = name
    tw.earliest_departure = earliest
    tw.latest_return = latest
    tw.buffer_days_start = buffer_start
    tw.buffer_days_end = buffer_end
    tw.enabled = enabled
    tw.created_at = datetime(2026, 1, 1)
    tw.notes = None
    return tw


def _make_trip(
    iata: str = "CDG",
    departure: date = date(2026, 10, 4),
    ret: date = date(2026, 10, 11),
) -> TripCandidate:
    cost = CostBreakdown(
        flights=600.0,
        hotel=700.0,
        car=200.0,
        food=150.0,
        car_is_estimate=True,
    )
    return TripCandidate(
        destination_iata=iata,
        city="Paris",
        country="France",
        region="Western Europe",
        departure_date=departure,
        return_date=ret,
        cost=cost,
        distance_miles=4500.0,
        flight_booking_url="https://example.com/flights",
        hotel_booking_url="https://example.com/hotel",
        car_booking_url="https://example.com/car",
        raw_flight_data="{}",
        raw_hotel_data="{}",
        departure_airport="HSV",
    )


# ── TravelWindow model properties ─────────────────────────────────────────────


class TestTravelWindowEffectiveDates:
    def test_effective_start_no_buffer(self):
        tw = _make_window(earliest=date(2026, 10, 5))
        assert tw.effective_start == date(2026, 10, 5)

    def test_effective_end_no_buffer(self):
        tw = _make_window(latest=date(2026, 10, 12))
        assert tw.effective_end == date(2026, 10, 12)

    def test_effective_start_with_buffer(self):
        tw = _make_window(earliest=date(2026, 10, 5), buffer_start=3)
        assert tw.effective_start == date(2026, 10, 2)

    def test_effective_end_with_buffer(self):
        tw = _make_window(latest=date(2026, 10, 12), buffer_end=2)
        assert tw.effective_end == date(2026, 10, 14)

    def test_both_buffers(self):
        tw = _make_window(
            earliest=date(2026, 10, 5),
            latest=date(2026, 10, 12),
            buffer_start=3,
            buffer_end=2,
        )
        assert tw.effective_start == date(2026, 10, 2)
        assert tw.effective_end == date(2026, 10, 14)

    def test_zero_buffers_explicit(self):
        tw = _make_window(
            earliest=date(2026, 10, 5),
            latest=date(2026, 10, 12),
            buffer_start=0,
            buffer_end=0,
        )
        assert tw.effective_start == date(2026, 10, 5)
        assert tw.effective_end == date(2026, 10, 12)


# ── _window_pass1_for_departure ───────────────────────────────────────────────


class TestWindowPass1ForDeparture:
    """Tests for the _window_pass1_for_departure() helper in main.py."""

    def _call(
        self,
        active_windows,
        batch,
        trip_nights=7,
        is_mock=True,
        find_window_return=None,
    ):
        """Helper that calls _window_pass1_for_departure with controlled mocks."""
        from main import _window_pass1_for_departure

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        # _is_excluded always returns False (destination not excluded)
        with (
            patch("main._is_excluded", return_value=False),
            patch("main.find_cheapest_in_window", return_value=find_window_return),
        ):
            return _window_pass1_for_departure(
                session=mock_session,
                dep_iata="HSV",
                batch=batch,
                active_windows=active_windows,
                trip_nights=trip_nights,
                num_adults=2,
                num_children=0,
                num_rooms=1,
                car_rental_required=False,
                direct_flights_only=False,
                cache_ttl_enabled=True,
                is_mock=is_mock,
                max_live_calls=40,
                live_calls_made_so_far=0,
                transport_usd=0.0,
            )

    def _make_dest(self, iata: str = "CDG") -> MagicMock:
        d = MagicMock()
        d.iata_code = iata
        return d

    def test_window_too_short_for_trip_skipped(self):
        """Window with range smaller than trip_nights yields no results."""
        # Window: Oct 5 to Oct 7 → only 2 effective days → can't fit 7-night trip
        tw = _make_window(
            earliest=date(2026, 10, 5),
            latest=date(2026, 10, 7),
        )
        dest = self._make_dest()
        results, _calls, _hits, iata_map = self._call(
            active_windows=[tw],
            batch=[dest],
            trip_nights=7,
            find_window_return=(None, None, 0, 0),
        )
        assert results == []
        assert iata_map == {}

    def test_no_price_returned_skipped(self):
        """Destination skipped when find_cheapest_in_window returns cost=None."""
        tw = _make_window(earliest=date(2026, 10, 1), latest=date(2026, 10, 15))
        dest = self._make_dest("NRT")
        results, _, _, iata_map = self._call(
            active_windows=[tw],
            batch=[dest],
            find_window_return=(None, None, 1, 0),
        )
        assert results == []
        assert "NRT" not in iata_map

    def test_valid_result_included(self):
        """Destination included when find_cheapest_in_window returns a valid cost."""
        from trip_a_day.costs import CostBreakdown

        tw = _make_window(earliest=date(2026, 10, 1), latest=date(2026, 10, 15))
        dest = self._make_dest("NRT")
        cost = CostBreakdown(
            flights=500.0, hotel=700.0, car=200.0, food=150.0, car_is_estimate=True
        )
        best_date = date(2026, 10, 4)
        results, _, _, iata_map = self._call(
            active_windows=[tw],
            batch=[dest],
            find_window_return=(cost, best_date, 1, 0),
        )
        assert len(results) == 1
        _dest, _total, _date = results[0]
        assert _dest.iata_code == "NRT"
        assert _total == cost.total
        assert "NRT" in iata_map
        assert iata_map["NRT"] == "Test Window"

    def test_best_result_kept_across_multiple_windows(self):
        """When two windows both cover a destination, keep the cheaper result."""
        from trip_a_day.costs import CostBreakdown

        tw1 = _make_window(
            name="Cheap Window",
            earliest=date(2026, 10, 1),
            latest=date(2026, 10, 12),
        )
        tw2 = _make_window(
            name="Expensive Window",
            earliest=date(2026, 11, 1),
            latest=date(2026, 11, 12),
        )
        dest = self._make_dest("NRT")

        cheap_cost = CostBreakdown(
            flights=400.0, hotel=700.0, car=200.0, food=150.0, car_is_estimate=True
        )
        expensive_cost = CostBreakdown(
            flights=900.0, hotel=700.0, car=200.0, food=150.0, car_is_estimate=True
        )
        # Alternate between cheap and expensive depending on call count
        call_count = {"n": 0}

        def _side_effect(**kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return (cheap_cost, date(2026, 10, 4), 1, 0)
            return (expensive_cost, date(2026, 11, 4), 1, 0)

        from main import _window_pass1_for_departure

        mock_session = MagicMock()
        with (
            patch("main._is_excluded", return_value=False),
            patch("main.find_cheapest_in_window", side_effect=_side_effect),
        ):
            results, _, _, iata_map = _window_pass1_for_departure(
                session=mock_session,
                dep_iata="HSV",
                batch=[dest],
                active_windows=[tw1, tw2],
                trip_nights=7,
                num_adults=2,
                num_children=0,
                num_rooms=1,
                car_rental_required=False,
                direct_flights_only=False,
                cache_ttl_enabled=True,
                is_mock=True,
                max_live_calls=40,
                live_calls_made_so_far=0,
                transport_usd=0.0,
            )

        assert len(results) == 1
        _dest, _total, _ = results[0]
        assert abs(_total - cheap_cost.total) < 0.01
        assert iata_map["NRT"] == "Cheap Window"

    def test_exception_in_find_cheapest_skips_destination(self):
        """Exception from find_cheapest_in_window causes destination to be skipped."""
        tw = _make_window(earliest=date(2026, 10, 1), latest=date(2026, 10, 15))
        dest = self._make_dest("BCN")

        from main import _window_pass1_for_departure

        mock_session = MagicMock()
        with (
            patch("main._is_excluded", return_value=False),
            patch("main.find_cheapest_in_window", side_effect=RuntimeError("API down")),
        ):
            results, _, _, iata_map = _window_pass1_for_departure(
                session=mock_session,
                dep_iata="HSV",
                batch=[dest],
                active_windows=[tw],
                trip_nights=7,
                num_adults=2,
                num_children=0,
                num_rooms=1,
                car_rental_required=False,
                direct_flights_only=False,
                cache_ttl_enabled=True,
                is_mock=True,
                max_live_calls=40,
                live_calls_made_so_far=0,
                transport_usd=0.0,
            )

        assert results == []
        assert iata_map == {}


# ── _travel_window_html helper ────────────────────────────────────────────────


class TestTravelWindowHtml:
    def test_green_card_with_window_name(self):
        trip = _make_trip(departure=date(2026, 10, 4), ret=date(2026, 10, 11))
        html = _travel_window_html(trip, "Fall Break 2026", False)
        assert "Fall Break 2026" in html
        assert "Travel window" in html
        assert "#43a047" in html  # green border

    def test_green_card_shows_depart_and_return(self):
        trip = _make_trip(departure=date(2026, 10, 4), ret=date(2026, 10, 11))
        html = _travel_window_html(trip, "Fall Break 2026", False)
        assert "Oct 4" in html
        assert "Oct 11" in html

    def test_amber_fallback_notice_when_window_fallback_used(self):
        trip = _make_trip()
        html = _travel_window_html(trip, None, True)
        assert "No trip found" in html
        assert "#f9a825" in html  # amber border

    def test_empty_string_when_no_window_and_no_fallback(self):
        trip = _make_trip()
        html = _travel_window_html(trip, None, False)
        assert html == ""

    def test_fallback_takes_priority_over_window_name(self):
        """fallback flag takes precedence even if a name is provided."""
        trip = _make_trip()
        html = _travel_window_html(trip, "Fall Break 2026", True)
        assert "No trip found" in html
        assert "Fall Break 2026" not in html


# ── _travel_window_plain helper ───────────────────────────────────────────────


class TestTravelWindowPlain:
    def test_plain_with_window_name(self):
        trip = _make_trip(departure=date(2026, 10, 4), ret=date(2026, 10, 11))
        plain = _travel_window_plain(trip, "Fall Break 2026", False)
        assert "Fall Break 2026" in plain
        assert "Travel window" in plain
        assert "Oct 4" in plain
        assert "Oct 11" in plain

    def test_plain_fallback_notice(self):
        trip = _make_trip()
        plain = _travel_window_plain(trip, None, True)
        assert "No trip found" in plain
        assert "standard advance booking" in plain

    def test_plain_empty_when_no_window_no_fallback(self):
        trip = _make_trip()
        plain = _travel_window_plain(trip, None, False)
        assert plain == ""


# ── send_trip_notification accepts new params ─────────────────────────────────


class TestNotifierAcceptsWindowParams:
    """Verify send_trip_notification does not raise when passed window params."""

    def test_travel_window_name_accepted(self):
        from trip_a_day.notifier import send_trip_notification

        trip = _make_trip()
        prefs: dict[str, str] = {}  # no API key → stdout fallback
        # Should not raise — prints to stdout
        result = send_trip_notification(
            trip,
            prefs,
            travel_window_name="Fall Break 2026",
            window_fallback_used=False,
        )
        assert result is True  # stdout fallback always returns True

    def test_window_fallback_used_accepted(self):
        from trip_a_day.notifier import send_trip_notification

        trip = _make_trip()
        prefs: dict[str, str] = {}
        result = send_trip_notification(
            trip,
            prefs,
            travel_window_name=None,
            window_fallback_used=True,
        )
        assert result is True

    def test_defaults_unchanged_without_window_params(self):
        """Callers that don't pass window params still work (default None/False)."""
        from trip_a_day.notifier import send_trip_notification

        trip = _make_trip()
        prefs: dict[str, str] = {}
        result = send_trip_notification(trip, prefs)
        assert result is True


# ── build_html / build_plain thread-through ───────────────────────────────────


class TestBuildHtmlWindowSection:
    def test_window_section_in_html_with_name(self):
        trip = _make_trip(departure=date(2026, 10, 4), ret=date(2026, 10, 11))
        html = _build_html(trip, travel_window_name="Fall Break 2026")
        assert "Fall Break 2026" in html

    def test_window_fallback_banner_in_html(self):
        trip = _make_trip()
        html = _build_html(trip, window_fallback_used=True)
        assert "No trip found" in html

    def test_no_window_section_by_default(self):
        trip = _make_trip()
        html = _build_html(trip)
        assert "Travel window" not in html
        assert "No trip found" not in html


class TestBuildPlainWindowSection:
    def test_window_section_in_plain_with_name(self):
        trip = _make_trip(departure=date(2026, 10, 4), ret=date(2026, 10, 11))
        plain = _build_plain(trip, travel_window_name="Fall Break 2026")
        assert "Fall Break 2026" in plain

    def test_window_fallback_notice_in_plain(self):
        trip = _make_trip()
        plain = _build_plain(trip, window_fallback_used=True)
        assert "No trip found" in plain

    def test_no_window_section_by_default(self):
        trip = _make_trip()
        plain = _build_plain(trip)
        assert "Travel window" not in plain
