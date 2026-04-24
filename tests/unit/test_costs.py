"""Unit tests for costs.py — no API calls, no DB required."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trip_a_day.costs import (
    CostBreakdown,
    build_cost_breakdown,
    is_valid_cost_breakdown,
    lookup_car_cost,
)

_SAMPLE_RATES = {
    "North America": {"daily_rate_usd": 65},
    "Western Europe": {"daily_rate_usd": 70},
    "Southeast Asia": {"daily_rate_usd": 35},
    "Other": {"daily_rate_usd": 50},
}


@pytest.fixture(autouse=True)
def mock_car_rates(tmp_path: Path):
    """Replace car_rates.json with a controlled test fixture."""
    rates_file = tmp_path / "car_rates.json"
    rates_file.write_text(json.dumps(_SAMPLE_RATES))
    import trip_a_day.costs as costs_module

    original_path = costs_module._CAR_RATES_PATH
    original_cache = costs_module._car_rates
    costs_module._CAR_RATES_PATH = rates_file
    costs_module._car_rates = None  # force reload
    yield
    costs_module._CAR_RATES_PATH = original_path
    costs_module._car_rates = original_cache


class TestLookupCarCost:
    def test_known_region(self):
        cost = lookup_car_cost("North America", 7)
        assert cost == 65 * 7

    def test_another_known_region(self):
        cost = lookup_car_cost("Western Europe", 7)
        assert cost == 70 * 7

    def test_falls_back_to_other_for_unknown_region(self):
        cost = lookup_car_cost("Narnia", 5)
        assert cost == 50 * 5  # "Other" fallback

    def test_zero_days(self):
        assert lookup_car_cost("North America", 0) == 0

    def test_result_is_rounded_to_two_decimals(self):
        # 35 * 3 = 105.00 — exact, but ensure float precision is handled
        cost = lookup_car_cost("Southeast Asia", 3)
        assert cost == 35 * 3


class TestBuildCostBreakdown:
    def test_total_is_sum_of_components(self):
        bd = build_cost_breakdown(
            flight_total=500.00,
            hotel_total=700.00,
            car_region="North America",
            food_total=300.00,
            days=7,
        )
        car = lookup_car_cost("North America", 7)
        assert bd.total == round(500.00 + 700.00 + car + 300.00, 2)

    def test_car_is_always_flagged_as_estimate(self):
        bd = build_cost_breakdown(
            flight_total=100.0,
            hotel_total=200.0,
            car_region="North America",
            food_total=150.0,
            days=7,
        )
        assert bd.car_is_estimate is True

    def test_components_stored_separately(self):
        bd = build_cost_breakdown(
            flight_total=400.0,
            hotel_total=600.0,
            car_region="Western Europe",
            food_total=250.0,
            days=7,
        )
        assert bd.flights == 400.0
        assert bd.hotel == 600.0
        assert bd.food == 250.0
        assert bd.car == lookup_car_cost("Western Europe", 7)

    def test_total_equals_sum(self):
        bd = build_cost_breakdown(
            flight_total=123.45,
            hotel_total=678.90,
            car_region="Southeast Asia",
            food_total=111.11,
            days=5,
        )
        expected = round(
            123.45 + 678.90 + lookup_car_cost("Southeast Asia", 5) + 111.11, 2
        )
        assert bd.total == expected

    def test_returns_cost_breakdown_type(self):
        bd = build_cost_breakdown(
            flight_total=0.0,
            hotel_total=0.0,
            car_region="Other",
            food_total=0.0,
            days=1,
        )
        assert isinstance(bd, CostBreakdown)


class TestBuildCostBreakdownNoCarRental:
    def test_car_cost_is_zero_when_not_required(self):
        bd = build_cost_breakdown(
            flight_total=500.0,
            hotel_total=700.0,
            car_region="North America",
            food_total=300.0,
            days=7,
            car_required=False,
        )
        assert bd.car == 0.0

    def test_car_is_not_flagged_as_estimate_when_not_required(self):
        bd = build_cost_breakdown(
            flight_total=100.0,
            hotel_total=200.0,
            car_region="North America",
            food_total=150.0,
            days=7,
            car_required=False,
        )
        assert bd.car_is_estimate is False

    def test_total_excludes_car_when_not_required(self):
        bd = build_cost_breakdown(
            flight_total=500.0,
            hotel_total=700.0,
            car_region="North America",
            food_total=300.0,
            days=7,
            car_required=False,
        )
        assert bd.total == round(500.0 + 700.0 + 300.0, 2)

    def test_other_components_unaffected(self):
        bd = build_cost_breakdown(
            flight_total=400.0,
            hotel_total=600.0,
            car_region="Western Europe",
            food_total=250.0,
            days=7,
            car_required=False,
        )
        assert bd.flights == 400.0
        assert bd.hotel == 600.0
        assert bd.food == 250.0


def _valid_cost(**overrides) -> CostBreakdown:
    """Construct a valid CostBreakdown, optionally overriding fields."""
    defaults = dict(
        flights=500.0,
        hotel=700.0,
        car=200.0,
        food=150.0,
        car_is_estimate=True,
    )
    defaults.update(overrides)
    return CostBreakdown(**defaults)


class TestIsValidCostBreakdown:
    def test_valid_breakdown_returns_true(self):
        ok, reason = is_valid_cost_breakdown(_valid_cost())
        assert ok is True
        assert reason == ""

    def test_flight_cost_zero_is_invalid(self):
        ok, reason = is_valid_cost_breakdown(_valid_cost(flights=0.0))
        assert ok is False
        assert "flight" in reason.lower()

    def test_flight_cost_negative_is_invalid(self):
        ok, reason = is_valid_cost_breakdown(_valid_cost(flights=-1.0))
        assert ok is False
        assert "flight" in reason.lower()

    def test_hotel_cost_negative_is_invalid(self):
        ok, reason = is_valid_cost_breakdown(_valid_cost(hotel=-1.0))
        assert ok is False
        assert "hotel" in reason.lower()

    def test_hotel_cost_zero_is_valid(self):
        # Per-diem estimates can legitimately be $0 for some destinations.
        ok, _ = is_valid_cost_breakdown(_valid_cost(hotel=0.0))
        assert ok is True

    def test_car_cost_zero_is_valid(self):
        ok, _ = is_valid_cost_breakdown(_valid_cost(car=0.0, car_is_estimate=False))
        assert ok is True

    def test_food_cost_zero_is_valid(self):
        ok, _ = is_valid_cost_breakdown(_valid_cost(food=0.0))
        assert ok is True

    def test_nan_flight_cost_is_invalid(self):
        import math

        ok, reason = is_valid_cost_breakdown(_valid_cost(flights=math.nan))
        assert ok is False
        assert "flight" in reason.lower()

    def test_inf_flight_cost_is_invalid(self):
        import math

        ok, reason = is_valid_cost_breakdown(_valid_cost(flights=math.inf))
        assert ok is False
        assert "flight" in reason.lower()

    def test_valid_with_transport_usd(self):
        cost = _valid_cost(transport_usd=120.0)
        ok, _ = is_valid_cost_breakdown(cost)
        assert ok is True
