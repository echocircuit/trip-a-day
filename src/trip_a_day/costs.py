"""Cost assembly: CostBreakdown dataclass and car rate lookup."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

_CAR_RATES_PATH = Path(__file__).resolve().parents[2] / "car_rates.json"
_car_rates: dict[str, dict] | None = None


def _load_car_rates() -> dict[str, dict]:
    global _car_rates
    if _car_rates is None:
        with _CAR_RATES_PATH.open() as f:
            _car_rates = json.load(f)
    return _car_rates


@dataclass
class CostBreakdown:
    """Full cost estimate for a single trip candidate.

    All amounts are USD, covering all travelers for the full trip duration.
    transport_usd is the round-trip IRS-rate driving cost to reach a nearby departure airport.
    total is computed from the component fields so it always stays in sync.
    """

    flights: float
    hotel: float
    car: float
    food: float
    car_is_estimate: bool
    hotel_is_estimate: bool = False
    transport_usd: float = 0.0

    @property
    def total(self) -> float:
        return round(
            self.flights + self.hotel + self.car + self.food + self.transport_usd, 2
        )


def is_valid_cost_breakdown(cost: CostBreakdown) -> tuple[bool, str]:
    """Validate a CostBreakdown for basic data quality requirements.

    Returns (True, "") for a valid breakdown or (False, human-readable reason).

    Root cause this guards against: Google Flights occasionally returns a "$0"
    price string which _parse_price converts to 0.0. The p is not None filter
    in get_flight_offers passes it through, resulting in a FlightOffer with
    price_total=0.0 that silently wins the ranking (e.g. OAK on 2026-04-20,
    is_mock=False, cache entry confirmed as live data).
    """
    if cost.flights is None or not math.isfinite(cost.flights) or cost.flights <= 0:
        return False, f"invalid flight cost ({cost.flights})"
    if cost.hotel is None or not math.isfinite(cost.hotel) or cost.hotel < 0:
        return False, f"invalid hotel cost ({cost.hotel})"
    if cost.car is None or not math.isfinite(cost.car) or cost.car < 0:
        return False, f"invalid car cost ({cost.car})"
    if cost.food is None or not math.isfinite(cost.food) or cost.food < 0:
        return False, f"invalid food cost ({cost.food})"
    # total is a computed property, but verify it matches within floating-point tolerance
    expected = round(
        cost.flights + cost.hotel + cost.car + cost.food + cost.transport_usd, 2
    )
    if abs(cost.total - expected) > 0.02:
        return False, f"total mismatch: expected {expected:.2f}, got {cost.total:.2f}"
    return True, ""


def lookup_car_cost(region: str, days: int) -> float:
    """Return estimated total car rental cost for *region* over *days*.

    Falls back to the "Other" region if *region* is not in the table.
    """
    rates = _load_car_rates()
    entry = rates.get(region) or rates.get("Other", {"daily_rate_usd": 50})
    daily: float = entry["daily_rate_usd"]
    return round(daily * days, 2)


def build_cost_breakdown(
    flight_total: float,
    hotel_total: float,
    car_region: str,
    food_total: float,
    days: int,
    car_required: bool = True,
    transport_usd: float = 0.0,
) -> CostBreakdown:
    """Assemble a CostBreakdown from pre-computed component costs.

    When *car_required* is True, car cost is looked up from car_rates.json and
    flagged as an estimate. When False, car cost is $0 and not flagged.
    *transport_usd* is the round-trip IRS-rate driving cost to a nearby departure airport.
    """
    if car_required:
        car = lookup_car_cost(car_region, days)
        car_is_estimate = True
    else:
        car = 0.0
        car_is_estimate = False
    return CostBreakdown(
        flights=round(flight_total, 2),
        hotel=round(hotel_total, 2),
        car=car,
        food=round(food_total, 2),
        car_is_estimate=car_is_estimate,
        transport_usd=round(transport_usd, 2),
    )
