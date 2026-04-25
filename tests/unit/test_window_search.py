"""Unit tests for window_search._probe_dates and find_cheapest_in_window.

All tests run without network access or a real database.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from trip_a_day.fetcher import FlightOffer, FoodEstimate, HotelOffer
from trip_a_day.window_search import _probe_dates, find_cheapest_in_window

# ---------------------------------------------------------------------------
# _probe_dates
# ---------------------------------------------------------------------------


TODAY = date(2026, 4, 24)


def test_probe_dates_three_probes():
    """3 probes across a 23-day window land at day 7, 18, and 30."""
    probes = _probe_dates(TODAY, min_days=7, max_days=30, n=3)
    assert len(probes) == 3
    assert probes[0] == TODAY + timedelta(days=7)
    assert probes[-1] == TODAY + timedelta(days=30)


def test_probe_dates_span_is_exact():
    """First probe is today+min_days, last probe is today+max_days."""
    probes = _probe_dates(TODAY, min_days=10, max_days=60, n=5)
    assert probes[0] == TODAY + timedelta(days=10)
    assert probes[-1] == TODAY + timedelta(days=60)


def test_probe_dates_equal_min_max_returns_one():
    """When min_days == max_days, returns exactly one date regardless of n."""
    probes = _probe_dates(TODAY, min_days=14, max_days=14, n=5)
    assert probes == [TODAY + timedelta(days=14)]


def test_probe_dates_min_greater_than_max_returns_min():
    """When min_days > max_days, returns min_days date (same guard as equal)."""
    probes = _probe_dates(TODAY, min_days=20, max_days=10, n=3)
    assert probes == [TODAY + timedelta(days=20)]


def test_probe_dates_n_one_returns_midpoint():
    """n=1 returns the midpoint of the window."""
    probes = _probe_dates(TODAY, min_days=0, max_days=30, n=1)
    assert len(probes) == 1
    assert probes[0] == TODAY + timedelta(days=15)


def test_probe_dates_no_duplicates():
    """All returned dates are unique even for small spans with many probes."""
    probes = _probe_dates(TODAY, min_days=7, max_days=8, n=10)
    assert len(probes) == len(set(probes))


def test_probe_dates_n_two_returns_endpoints():
    """n=2 returns exactly the first and last dates of the window."""
    probes = _probe_dates(TODAY, min_days=7, max_days=30, n=2)
    assert len(probes) == 2
    assert probes[0] == TODAY + timedelta(days=7)
    assert probes[1] == TODAY + timedelta(days=30)


# ---------------------------------------------------------------------------
# Helpers for find_cheapest_in_window tests
# ---------------------------------------------------------------------------


def _fake_dest(iata: str = "JFK") -> SimpleNamespace:
    return SimpleNamespace(
        iata_code=iata,
        city="New York",
        country="United States",
        region="North America",
    )


def _fake_flight(price: float = 400.0, depart: date | None = None) -> FlightOffer:
    d = depart or (date.today() + timedelta(days=14))
    return FlightOffer(
        origin="HSV",
        destination="JFK",
        departure_date=d,
        return_date=d + timedelta(days=7),
        price_total=price,
        booking_url="https://example.com/flight",
        raw="{}",
    )


def _fake_hotel(depart: date | None = None) -> HotelOffer:
    d = depart or (date.today() + timedelta(days=14))
    return HotelOffer(
        hotel_id="H001",
        hotel_name="Test Hotel",
        city_code="JFK",
        check_in=d,
        check_out=d + timedelta(days=7),
        price_total=700.0,
        booking_url="https://example.com/hotel",
        raw="{}",
    )


def _fake_food() -> FoodEstimate:
    return FoodEstimate(
        city="New York",
        country="United States",
        cost_per_person_per_day=50.0,
        total_cost=350.0,
        source="fallback",
    )


def _call_find(
    dest=None,
    min_days: int = 7,
    max_days: int = 30,
    live_calls_remaining: int = 10,
    cache_ttl_enabled: bool = False,
    is_mock: bool = True,
    transport_usd: float = 0.0,
):
    """Thin wrapper so tests don't have to repeat all the boilerplate kwargs."""
    return find_cheapest_in_window(
        origin_iata="HSV",
        destination=dest or _fake_dest(),
        min_days=min_days,
        max_days=max_days,
        trip_length_nights=7,
        adults=2,
        children=0,
        num_rooms=1,
        car_rental_required=True,
        direct_flights_only=True,
        cache_ttl_enabled=cache_ttl_enabled,
        is_mock=is_mock,
        db_session=MagicMock(),
        live_calls_remaining=live_calls_remaining,
        transport_usd=transport_usd,
    )


# ---------------------------------------------------------------------------
# find_cheapest_in_window — basic behaviour
# ---------------------------------------------------------------------------


def test_returns_none_when_no_flight():
    """Returns (None, None, 0, 0) when every probe has no flight offer."""
    with (
        patch(
            "trip_a_day.window_search.get_flight_offers",
            return_value=None,
        ),
        patch(
            "trip_a_day.window_search.get_hotel_offers",
            return_value=_fake_hotel(),
        ),
        patch(
            "trip_a_day.window_search.get_food_cost",
            return_value=_fake_food(),
        ),
    ):
        cost, best_date, _live, cache_hits = _call_find()

    assert cost is None
    assert best_date is None
    assert cache_hits == 0


def test_returns_none_when_no_hotel():
    """Returns (None, None, _, 0) when hotel lookup fails for every probe."""
    with (
        patch(
            "trip_a_day.window_search.get_flight_offers",
            return_value=_fake_flight(),
        ),
        patch(
            "trip_a_day.window_search.get_hotel_offers",
            return_value=None,
        ),
        patch(
            "trip_a_day.window_search.get_food_cost",
            return_value=_fake_food(),
        ),
    ):
        cost, best_date, _, _ = _call_find()

    assert cost is None
    assert best_date is None


def test_returns_valid_cost_when_flight_and_hotel_available():
    """Returns a CostBreakdown with a positive total when both flight and hotel work."""
    with (
        patch(
            "trip_a_day.window_search.get_flight_offers",
            return_value=_fake_flight(price=400.0),
        ),
        patch(
            "trip_a_day.window_search.get_hotel_offers",
            return_value=_fake_hotel(),
        ),
        patch(
            "trip_a_day.window_search.get_food_cost",
            return_value=_fake_food(),
        ),
    ):
        cost, best_date, _, _ = _call_find()

    assert cost is not None
    assert cost.flights == 400.0
    assert cost.total > 0
    assert best_date is not None


def test_selects_cheapest_probe_date():
    """When probes return different prices, the date with the lowest total is selected."""
    call_count = [0]

    def _flight_side_effect(**kwargs):
        call_count[0] += 1
        # First probe is most expensive, second is cheapest, third is mid.
        prices = {1: 900.0, 2: 200.0, 3: 600.0}
        return _fake_flight(price=prices.get(call_count[0], 500.0))

    with (
        patch(
            "trip_a_day.window_search.get_flight_offers",
            side_effect=_flight_side_effect,
        ),
        patch(
            "trip_a_day.window_search.get_hotel_offers",
            return_value=_fake_hotel(),
        ),
        patch(
            "trip_a_day.window_search.get_food_cost",
            return_value=_fake_food(),
        ),
    ):
        cost, _, _, _ = _call_find(min_days=7, max_days=30)

    assert cost is not None
    assert cost.flights == 200.0  # probe 2 was cheapest


def test_transport_usd_included_in_total():
    """transport_usd is added to the returned CostBreakdown total."""
    with (
        patch(
            "trip_a_day.window_search.get_flight_offers",
            return_value=_fake_flight(price=400.0),
        ),
        patch(
            "trip_a_day.window_search.get_hotel_offers",
            return_value=_fake_hotel(),
        ),
        patch(
            "trip_a_day.window_search.get_food_cost",
            return_value=_fake_food(),
        ),
    ):
        cost_no_transport, _, _, _ = _call_find(transport_usd=0.0)
        cost_with_transport, _, _, _ = _call_find(transport_usd=100.0)

    assert cost_no_transport is not None
    assert cost_with_transport is not None
    assert cost_with_transport.transport_usd == 100.0
    assert abs(cost_with_transport.total - cost_no_transport.total - 100.0) < 0.01


# ---------------------------------------------------------------------------
# find_cheapest_in_window — call budget
# ---------------------------------------------------------------------------


def test_live_call_budget_zero_returns_none():
    """When live_calls_remaining=0 and cache is empty, returns no result."""
    with (
        patch(
            "trip_a_day.window_search.get_flight_offers",
            return_value=_fake_flight(),
        ) as mock_flights,
        patch(
            "trip_a_day.window_search.get_hotel_offers",
            return_value=_fake_hotel(),
        ),
        patch(
            "trip_a_day.window_search.get_food_cost",
            return_value=_fake_food(),
        ),
    ):
        cost, _, _, _ = _call_find(live_calls_remaining=0, is_mock=False)

    assert cost is None  # no live calls available, no cache, so nothing found
    mock_flights.assert_not_called()


def test_live_calls_counted_correctly():
    """live_calls_used increments only for live mode calls, not mock mode."""
    with (
        patch(
            "trip_a_day.window_search.get_flight_offers",
            return_value=_fake_flight(),
        ),
        patch(
            "trip_a_day.window_search.get_hotel_offers",
            return_value=_fake_hotel(),
        ),
        patch(
            "trip_a_day.window_search.get_food_cost",
            return_value=_fake_food(),
        ),
    ):
        # In mock mode, live_calls_used should always be 0
        _, _, live_calls_mock, _ = _call_find(is_mock=True)
        assert live_calls_mock == 0

        # In live mode, live_calls_used should equal probes that fired
        _, _, live_calls_live, _ = _call_find(is_mock=False, live_calls_remaining=10)
        assert live_calls_live > 0


def test_stops_probing_when_budget_exhausted():
    """With live_calls_remaining=1, only one live call is made."""
    call_count = [0]

    def _flight_side_effect(**kwargs):
        call_count[0] += 1
        return _fake_flight()

    with (
        patch(
            "trip_a_day.window_search.get_flight_offers",
            side_effect=_flight_side_effect,
        ),
        patch(
            "trip_a_day.window_search.get_hotel_offers",
            return_value=_fake_hotel(),
        ),
        patch(
            "trip_a_day.window_search.get_food_cost",
            return_value=_fake_food(),
        ),
    ):
        _call_find(is_mock=False, live_calls_remaining=1)

    # Only 1 live call should have been made (budget exhausted after first probe)
    assert call_count[0] == 1


# ---------------------------------------------------------------------------
# find_cheapest_in_window — cache behaviour
# ---------------------------------------------------------------------------


def _fake_cache_entry(price: float = 350.0) -> SimpleNamespace:
    return SimpleNamespace(price_usd=price)


def test_cache_hit_skips_live_call():
    """A cache hit is used instead of a live flight call; live_calls_used stays 0."""
    with (
        patch(
            "trip_a_day.window_search.get_cached_flight",
            return_value=_fake_cache_entry(350.0),
        ),
        patch(
            "trip_a_day.window_search.get_flight_offers",
            return_value=_fake_flight(),
        ) as mock_live,
        patch(
            "trip_a_day.window_search.get_hotel_offers",
            return_value=_fake_hotel(),
        ),
        patch(
            "trip_a_day.window_search.get_food_cost",
            return_value=_fake_food(),
        ),
    ):
        cost, _, live_calls, cache_hits = _call_find(
            cache_ttl_enabled=True, is_mock=False, live_calls_remaining=10
        )

    # All 3 probes hit cache, so no live call
    mock_live.assert_not_called()
    assert live_calls == 0
    assert cache_hits == 3
    assert cost is not None
    assert cost.flights == 350.0


def test_zero_price_cache_entry_is_rejected():
    """A cached price of $0 is treated as invalid and triggers a live re-query."""
    with (
        patch(
            "trip_a_day.window_search.get_cached_flight",
            return_value=_fake_cache_entry(price=0.0),
        ),
        patch(
            "trip_a_day.window_search.get_flight_offers",
            return_value=_fake_flight(price=400.0),
        ) as mock_live,
        patch(
            "trip_a_day.window_search.get_hotel_offers",
            return_value=_fake_hotel(),
        ),
        patch(
            "trip_a_day.window_search.get_food_cost",
            return_value=_fake_food(),
        ),
    ):
        # is_mock=True so live_calls_used stays 0 but get_flight_offers IS called
        cost, _, _, _ = _call_find(cache_ttl_enabled=True, is_mock=True)

    # $0 cache entries should have been rejected and live call made
    assert mock_live.call_count > 0
    assert cost is not None
    assert cost.flights == 400.0
