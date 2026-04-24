"""Import smoke tests — verify every public symbol from every module exists.

Uses importlib so ruff does not strip "unused" imports.
Must pass with no environment variables or database present.
"""

from __future__ import annotations

import importlib


def _attrs(module_path: str, *names: str) -> None:
    mod = importlib.import_module(module_path)
    missing = [n for n in names if not hasattr(mod, n)]
    assert not missing, f"{module_path} is missing: {missing}"


def test_db_imports():
    _attrs(
        "trip_a_day.db",
        "Base",
        "DEFAULT_PREFERENCES",
        "Preference",
        "Destination",
        "Trip",
        "PriceCache",
        "RunLog",
        "ApiUsage",
        "SessionFactory",
        "init_db",
        "seed_preferences",
        "record_api_call",
        "get_api_calls_today",
    )


def test_preferences_imports():
    _attrs(
        "trip_a_day.preferences",
        "get",
        "get_or",
        "get_int",
        "get_bool",
        "get_json",
        "set_pref",
    )


def test_costs_imports():
    _attrs(
        "trip_a_day.costs",
        "CostBreakdown",
        "lookup_car_cost",
        "build_cost_breakdown",
    )


def test_ranker_imports():
    _attrs("trip_a_day.ranker", "TripCandidate", "rank_trips")


def test_fetcher_imports():
    _attrs(
        "trip_a_day.fetcher",
        "AirportInfo",
        "FlightOffer",
        "HotelOffer",
        "FoodEstimate",
        "get_flight_offers",
        "get_hotel_offers",
        "get_food_cost",
        "get_airport_info",
        "get_airport_city",
        "get_nearby_airports",
        "haversine_miles",
    )


def test_selector_imports():
    _attrs(
        "trip_a_day.selector",
        "STRATEGY_LABELS",
        "STRATEGIES",
        "select_daily_batch",
    )


def test_filters_imports():
    _attrs("trip_a_day.filters", "apply_destination_filters")


def test_cache_imports():
    _attrs(
        "trip_a_day.cache",
        "get_cache_ttl_days",
        "get_cached_flight",
        "store_flight_cache",
    )


def test_notifier_imports():
    _attrs("trip_a_day.notifier", "send_trip_notification", "send_test_email")
