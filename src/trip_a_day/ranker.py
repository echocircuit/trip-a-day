"""Trip candidate data model and ranking logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trip_a_day.costs import CostBreakdown


@dataclass
class TripCandidate:
    """A fully-assembled trip candidate ready for ranking."""

    destination_iata: str
    city: str
    country: str
    region: str
    departure_date: date
    return_date: date
    cost: CostBreakdown
    distance_miles: float
    flight_booking_url: str
    hotel_booking_url: str
    car_booking_url: str
    raw_flight_data: str
    raw_hotel_data: str
    departure_airport: str = ""
    stale_cache: bool = False


def rank_trips(
    candidates: list[TripCandidate],
    strategy: str = "cheapest_then_farthest",
) -> list[TripCandidate]:
    """Sort *candidates* by *strategy* and return the sorted list.

    Phase 1 strategy — ``cheapest_then_farthest``:
    Primary: total cost ascending.
    Tiebreaker: distance_miles descending (farthest wins on exact penny tie).

    The strategy string is accepted as a parameter so future strategies can be
    added without changing this function's interface.
    """
    if not candidates:
        return []

    if strategy == "cheapest_then_farthest":
        return sorted(
            candidates,
            key=lambda t: (t.cost.total, -t.distance_miles),
        )

    if strategy == "farthest_then_cheapest":
        return sorted(
            candidates,
            key=lambda t: (-t.distance_miles, t.cost.total),
        )

    if strategy == "random":
        import random

        shuffled = list(candidates)
        random.shuffle(shuffled)
        return shuffled

    # Unknown strategy — fall back to cheapest_then_farthest and log a warning
    import logging

    logging.getLogger(__name__).warning(
        "Unknown ranking strategy '%s'; falling back to cheapest_then_farthest.",
        strategy,
    )
    return sorted(candidates, key=lambda t: (t.cost.total, -t.distance_miles))
