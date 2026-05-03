"""Tests for travel window logic: model properties, auto-expiry, pipeline integration,
and notifier rendering.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

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


# ── _probe_dest_window ────────────────────────────────────────────────────────


def _make_window_data(
    name: str,
    min_days: int,
    max_days: int,
    eff_end_offset: int,
) -> dict:
    """Return a window_data dict as produced by run() before thread submission."""
    from datetime import timedelta

    today = date.today()
    return {
        "name": name,
        "min_days": min_days,
        "max_days": max_days,
        "eff_end": today + timedelta(days=eff_end_offset),
    }


def _call_probe_dest_window(window_data_list, find_return, trip_nights=7):
    """Call _probe_dest_window with standard args and a mocked find_cheapest."""
    import main as main_mod

    dest_data = {"iata": "NRT", "city": "Tokyo", "country": "Japan", "region": "Asia"}
    with patch("main.find_cheapest_in_window", return_value=find_return):
        return main_mod._probe_dest_window(
            dep_iata="HSV",
            dest_data=dest_data,
            window_data_list=window_data_list,
            trip_nights=trip_nights,
            adults=2,
            children=0,
            num_rooms=1,
            car_rental_required=False,
            direct_flights_only=False,
            cache_ttl_enabled=True,
            is_mock=True,
            live_calls_budget=40,
            transport_usd=0.0,
        )


class TestProbeDestWindow:
    """Tests for _probe_dest_window — the actual parallel Pass 1 thread entry point."""

    def test_no_price_returned_yields_none_cost(self):
        """find_cheapest returns (None, None, 0, 0) → cost is None in result."""
        wd = [_make_window_data("Win", 7, 30, 40)]
        iata, cost, best_date, _calls, _hits, window_name = _call_probe_dest_window(
            wd, (None, None, 0, 0)
        )
        assert iata == "NRT"
        assert cost is None
        assert best_date is None
        assert window_name is None

    def test_valid_result_returned(self):
        """When find_cheapest returns a valid cost, it propagates to the caller."""
        wd = [_make_window_data("Fall Break", 7, 30, 40)]
        from datetime import timedelta

        probe_date = date.today() + timedelta(days=14)
        cost = CostBreakdown(
            flights=500.0, hotel=700.0, car=200.0, food=150.0, car_is_estimate=True
        )
        _iata, got_cost, got_date, _calls, _hits, window_name = _call_probe_dest_window(
            wd, (cost, probe_date, 1, 0)
        )
        assert got_cost is not None
        assert abs(got_cost.total - cost.total) < 0.01
        assert got_date == probe_date
        assert window_name == "Fall Break"

    def test_picks_cheaper_of_two_windows(self):
        """With two windows, _probe_dest_window keeps the cheaper result."""
        cheap_cost = CostBreakdown(
            flights=400.0, hotel=700.0, car=200.0, food=150.0, car_is_estimate=True
        )
        expensive_cost = CostBreakdown(
            flights=900.0, hotel=700.0, car=200.0, food=150.0, car_is_estimate=True
        )
        call_count = {"n": 0}

        def _side_effect(**kwargs):
            call_count["n"] += 1
            from datetime import timedelta

            d = date.today() + timedelta(days=14 if call_count["n"] == 1 else 35)
            return (
                (cheap_cost, d, 1, 0)
                if call_count["n"] == 1
                else (expensive_cost, d, 1, 0)
            )

        import main as main_mod

        wd = [
            _make_window_data("Cheap Window", 7, 20, 25),
            _make_window_data("Expensive Window", 28, 42, 50),
        ]
        dest_data = {
            "iata": "NRT",
            "city": "Tokyo",
            "country": "Japan",
            "region": "Asia",
        }
        with patch("main.find_cheapest_in_window", side_effect=_side_effect):
            _, got_cost, _, _, _, window_name = main_mod._probe_dest_window(
                dep_iata="HSV",
                dest_data=dest_data,
                window_data_list=wd,
                trip_nights=7,
                adults=2,
                children=0,
                num_rooms=1,
                car_rental_required=False,
                direct_flights_only=False,
                cache_ttl_enabled=True,
                is_mock=True,
                live_calls_budget=40,
                transport_usd=0.0,
            )

        assert abs(got_cost.total - cheap_cost.total) < 0.01
        assert window_name == "Cheap Window"

    def test_exception_in_find_cheapest_yields_none_cost(self):
        """An exception in find_cheapest_in_window is caught; cost is None."""
        import main as main_mod

        wd = [_make_window_data("Win", 7, 30, 40)]
        dest_data = {
            "iata": "BCN",
            "city": "Barcelona",
            "country": "Spain",
            "region": "Europe",
        }
        with patch(
            "main.find_cheapest_in_window", side_effect=RuntimeError("API down")
        ):
            _iata, cost, _, _, _, window_name = main_mod._probe_dest_window(
                dep_iata="HSV",
                dest_data=dest_data,
                window_data_list=wd,
                trip_nights=7,
                adults=2,
                children=0,
                num_rooms=1,
                car_rental_required=False,
                direct_flights_only=False,
                cache_ttl_enabled=True,
                is_mock=True,
                live_calls_budget=40,
                transport_usd=0.0,
            )

        assert cost is None
        assert window_name is None


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
