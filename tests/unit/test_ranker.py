"""Unit tests for ranker.py — no API calls, no DB required."""

from __future__ import annotations

from datetime import date

from trip_a_day.costs import CostBreakdown
from trip_a_day.ranker import TripCandidate, rank_trips


def _make_cost(total: float) -> CostBreakdown:
    return CostBreakdown(
        flights=total * 0.5,
        hotel=total * 0.3,
        car=total * 0.1,
        food=total * 0.1,
        car_is_estimate=True,
    )


def _make_candidate(
    iata: str,
    total: float,
    distance: float = 500.0,
    city: str = "Test City",
) -> TripCandidate:
    return TripCandidate(
        destination_iata=iata,
        city=city,
        country="Testland",
        region="Other",
        departure_date=date(2026, 5, 1),
        return_date=date(2026, 5, 8),
        cost=_make_cost(total),
        distance_miles=distance,
        flight_booking_url="https://example.com/flights",
        hotel_booking_url="https://example.com/hotel",
        car_booking_url="https://example.com/car",
        raw_flight_data="{}",
        raw_hotel_data="{}",
    )


class TestRankTripsCheapestThenFarthest:
    def test_cheapest_is_first(self):
        candidates = [
            _make_candidate("EXP", 2000.0),
            _make_candidate("CHE", 1000.0),
            _make_candidate("MID", 1500.0),
        ]
        ranked = rank_trips(candidates, "cheapest_then_farthest")
        assert ranked[0].destination_iata == "CHE"
        assert ranked[1].destination_iata == "MID"
        assert ranked[2].destination_iata == "EXP"

    def test_tie_broken_by_distance_descending(self):
        # Same price, different distances — farthest should win
        near = _make_candidate("NEAR", 1000.0, distance=300.0)
        far = _make_candidate("FAR", 1000.0, distance=3000.0)
        ranked = rank_trips([near, far], "cheapest_then_farthest")
        assert ranked[0].destination_iata == "FAR"
        assert ranked[1].destination_iata == "NEAR"

    def test_single_candidate_returns_list_of_one(self):
        c = _make_candidate("ONE", 999.0)
        ranked = rank_trips([c], "cheapest_then_farthest")
        assert len(ranked) == 1
        assert ranked[0].destination_iata == "ONE"

    def test_empty_input_returns_empty(self):
        assert rank_trips([], "cheapest_then_farthest") == []

    def test_preserves_all_candidates(self):
        candidates = [_make_candidate(f"D{i}", float(i * 100)) for i in range(5)]
        ranked = rank_trips(candidates, "cheapest_then_farthest")
        assert len(ranked) == 5

    def test_order_is_ascending_by_total(self):
        candidates = [
            _make_candidate("D3", 3000.0),
            _make_candidate("D1", 1000.0),
            _make_candidate("D2", 2000.0),
        ]
        ranked = rank_trips(candidates, "cheapest_then_farthest")
        totals = [c.cost.total for c in ranked]
        assert totals == sorted(totals)


class TestRankTripsFarthestThenCheapest:
    def test_farthest_is_first(self):
        candidates = [
            _make_candidate("NEAR", 1000.0, distance=500.0),
            _make_candidate("FAR", 5000.0, distance=5000.0),
            _make_candidate("MID", 2000.0, distance=2000.0),
        ]
        ranked = rank_trips(candidates, "farthest_then_cheapest")
        assert ranked[0].destination_iata == "FAR"

    def test_tie_broken_by_price_ascending(self):
        cheap_far = _make_candidate("CHEAP", 500.0, distance=5000.0)
        expensive_far = _make_candidate("PRICEY", 9000.0, distance=5000.0)
        ranked = rank_trips([expensive_far, cheap_far], "farthest_then_cheapest")
        assert ranked[0].destination_iata == "CHEAP"


class TestRankTripsUnknownStrategy:
    def test_unknown_strategy_falls_back_to_cheapest(self):
        candidates = [
            _make_candidate("EXP", 3000.0),
            _make_candidate("CHE", 1000.0),
        ]
        ranked = rank_trips(candidates, "nonexistent_strategy")
        assert ranked[0].destination_iata == "CHE"


class TestRankTripsRandom:
    def test_random_returns_all_candidates(self):
        candidates = [_make_candidate(f"D{i}", float(i * 100)) for i in range(10)]
        ranked = rank_trips(candidates, "random")
        assert len(ranked) == 10
        assert set(c.destination_iata for c in ranked) == set(
            c.destination_iata for c in candidates
        )
