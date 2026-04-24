"""Basic instantiation smoke tests — no DB or env vars required."""

from __future__ import annotations


def test_cost_breakdown_instantiation():
    from trip_a_day.costs import CostBreakdown

    cb = CostBreakdown(
        flights=100.0,
        hotel=200.0,
        car=50.0,
        food=75.0,
        car_is_estimate=True,
        hotel_is_estimate=True,
    )
    assert cb.total == 425.0


def test_preferences_default_keys_exist():
    from trip_a_day.db import DEFAULT_PREFERENCES

    required_keys = [
        "home_airport",
        "trip_length_nights",
        "advance_days",
        "num_adults",
        "num_children",
        "direct_flights_only",
        "car_rental_required",
        "notification_emails",
        "notifications_enabled",
        "ranking_strategy",
        "daily_batch_size",
        "destination_selection_strategy",
    ]
    for key in required_keys:
        assert key in DEFAULT_PREFERENCES, f"Missing required preference key: {key}"
