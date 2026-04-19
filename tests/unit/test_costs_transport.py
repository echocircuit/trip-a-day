"""Unit tests for transport_usd in CostBreakdown and build_cost_breakdown."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trip_a_day.costs import CostBreakdown, build_cost_breakdown, lookup_car_cost

_SAMPLE_RATES = {
    "North America": {"daily_rate_usd": 65},
    "Other": {"daily_rate_usd": 50},
}


@pytest.fixture(autouse=True)
def mock_car_rates(tmp_path: Path):
    rates_file = tmp_path / "car_rates.json"
    rates_file.write_text(json.dumps(_SAMPLE_RATES))
    import trip_a_day.costs as costs_module

    original_path = costs_module._CAR_RATES_PATH
    original_cache = costs_module._car_rates
    costs_module._CAR_RATES_PATH = rates_file
    costs_module._car_rates = None
    yield
    costs_module._CAR_RATES_PATH = original_path
    costs_module._car_rates = original_cache


class TestTransportUsd:
    def test_default_transport_is_zero(self):
        bd = build_cost_breakdown(
            flight_total=500.0,
            hotel_total=700.0,
            car_region="North America",
            food_total=300.0,
            days=7,
        )
        assert bd.transport_usd == 0.0

    def test_transport_included_in_total(self):
        bd = build_cost_breakdown(
            flight_total=500.0,
            hotel_total=700.0,
            car_region="North America",
            food_total=300.0,
            days=7,
            transport_usd=100.0,
        )
        car = lookup_car_cost("North America", 7)
        expected = round(500.0 + 700.0 + car + 300.0 + 100.0, 2)
        assert bd.total == expected

    def test_transport_stored_on_breakdown(self):
        bd = build_cost_breakdown(
            flight_total=400.0,
            hotel_total=600.0,
            car_region="North America",
            food_total=200.0,
            days=7,
            transport_usd=119.0,
        )
        assert bd.transport_usd == 119.0

    def test_transport_zero_does_not_change_existing_total(self):
        bd_without = build_cost_breakdown(
            flight_total=500.0,
            hotel_total=700.0,
            car_region="North America",
            food_total=300.0,
            days=7,
            transport_usd=0.0,
        )
        bd_default = build_cost_breakdown(
            flight_total=500.0,
            hotel_total=700.0,
            car_region="North America",
            food_total=300.0,
            days=7,
        )
        assert bd_without.total == bd_default.total

    def test_transport_rounded_to_two_decimals(self):
        bd = build_cost_breakdown(
            flight_total=100.0,
            hotel_total=200.0,
            car_region="Other",
            food_total=50.0,
            days=3,
            transport_usd=33.333,
        )
        assert bd.transport_usd == round(33.333, 2)

    def test_cost_breakdown_default_transport_field(self):
        bd = CostBreakdown(
            flights=100.0,
            hotel=200.0,
            car=50.0,
            food=75.0,
            total=425.0,
            car_is_estimate=True,
        )
        assert bd.transport_usd == 0.0
