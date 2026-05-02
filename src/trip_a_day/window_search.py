"""Adaptive booking-window search: find the cheapest departure date in a window.

find_cheapest_in_window probes N dates spread across [min_days, max_days] from
today, checks the cache first for each, then makes a live call if budget allows.
Returns the CostBreakdown with the lowest total among all valid probes, plus how
many live calls were consumed.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from trip_a_day.cache import get_cached_flight, store_flight_cache
from trip_a_day.costs import (
    CostBreakdown,
    build_cost_breakdown,
    is_valid_cost_breakdown,
)
from trip_a_day.fetcher import get_flight_offers, get_food_cost, get_hotel_offers

logger = logging.getLogger(__name__)

# Number of departure dates to probe across the booking window on the first pass.
_DEFAULT_PROBE_COUNT = 3

# Hard upper bound on probes per destination regardless of probe_count argument,
# to prevent runaway calls if probe_count is ever increased.
MAX_PROBES_PER_DESTINATION = 7


def _probe_dates(today: date, min_days: int, max_days: int, n: int) -> list[date]:
    """Return n dates spread evenly across [today+min_days, today+max_days].

    When n == 1, returns just the midpoint. When min_days == max_days, returns
    a single date regardless of n.
    """
    if min_days >= max_days:
        return [today + timedelta(days=min_days)]
    span = max_days - min_days
    if n <= 1:
        mid = min_days + span // 2
        return [today + timedelta(days=mid)]
    dates: list[date] = []
    for i in range(n):
        offset = min_days + round(span * i / (n - 1))
        d = today + timedelta(days=offset)
        if d not in dates:
            dates.append(d)
    return dates


def find_cheapest_in_window(
    origin_iata: str,
    destination,  # Destination ORM object (has .iata_code, .city, .country, .region)
    min_days: int,
    max_days: int,
    trip_length_nights: int,
    adults: int,
    children: int,
    num_rooms: int,
    car_rental_required: bool,
    direct_flights_only: bool,
    cache_ttl_enabled: bool,
    is_mock: bool,
    db_session: Session,
    live_calls_remaining: int,
    transport_usd: float = 0.0,
) -> tuple[CostBreakdown | None, date | None, int, int]:
    """Probe departure dates across the booking window and return the cheapest valid trip.

    Returns (best_cost_breakdown, best_departure_date, live_calls_used, cache_hits_used).
    best_cost_breakdown is None if no valid result was found.
    """
    today = date.today()
    probe_count = min(_DEFAULT_PROBE_COUNT, MAX_PROBES_PER_DESTINATION)
    probes = _probe_dates(today, min_days, max_days, probe_count)

    iata = destination.iata_code
    city = (destination.city or iata).title()
    country = (destination.country or "Unknown").title()
    region = destination.region or "Other"

    best_cost: CostBreakdown | None = None
    best_date: date | None = None
    live_calls_used = 0
    cache_hits_used = 0

    for depart_date in probes:
        return_date = depart_date + timedelta(days=trip_length_nights)
        advance_days = (depart_date - today).days

        # Cache check first
        cached = None
        if cache_ttl_enabled:
            cached = get_cached_flight(
                db_session,
                origin_iata,
                iata,
                depart_date,
                return_date,
                adults,
                children,
            )
            if cached is not None and cached.price_usd <= 0:
                logger.debug(
                    "  [window] %s→%s %s cached price $%.0f invalid — re-querying",
                    origin_iata,
                    iata,
                    depart_date,
                    cached.price_usd,
                )
                cached = None

        if cached is not None:
            flight_price = cached.price_usd
            cache_hits_used += 1
            logger.debug(
                "  [window/cache] %s→%s %s — $%.0f",
                origin_iata,
                iata,
                depart_date,
                flight_price,
            )
        else:
            if live_calls_remaining - live_calls_used <= 0:
                logger.debug(
                    "  [window] %s→%s %s — live call cap reached, skipping probe",
                    origin_iata,
                    iata,
                    depart_date,
                )
                continue

            flight_offer = get_flight_offers(
                origin=origin_iata,
                destination=iata,
                depart_date=depart_date,
                return_date=return_date,
                adults=adults,
                children=children,
                session=db_session,
                direct_only=direct_flights_only,
                is_mock=is_mock,
            )
            if not is_mock:
                live_calls_used += 1

            if flight_offer is None:
                logger.debug(
                    "  [window] %s→%s %s — no flight result",
                    origin_iata,
                    iata,
                    depart_date,
                )
                continue

            flight_price = flight_offer.price_total

            if cache_ttl_enabled:
                store_flight_cache(
                    db_session,
                    origin_iata,
                    iata,
                    depart_date,
                    return_date,
                    adults,
                    children,
                    flight_price,
                    None,
                    None,
                    advance_days,
                    is_mock,
                )

            logger.debug(
                "  [window/live] %s→%s %s — $%.0f",
                origin_iata,
                iata,
                depart_date,
                flight_price,
            )

        # Build cost breakdown for this probe date
        hotel = get_hotel_offers(
            city_code=iata,
            checkin=depart_date,
            checkout=return_date,
            adults=adults,
            session=db_session,
            num_rooms=num_rooms,
        )
        if hotel is None:
            logger.debug("  [window] %s %s — no hotel result", iata, depart_date)
            continue

        food = get_food_cost(
            city=city,
            country=country,
            region=region,
            days=trip_length_nights,
            people=adults + children,
            session=db_session,
        )

        cost = build_cost_breakdown(
            flight_total=flight_price,
            hotel_total=hotel.price_total,
            car_region=region,
            food_total=food.total_cost,
            days=trip_length_nights,
            car_required=car_rental_required,
            transport_usd=transport_usd,
        )

        valid, reason = is_valid_cost_breakdown(cost)
        if not valid:
            logger.debug(
                "  [window] %s %s — invalid cost: %s", iata, depart_date, reason
            )
            continue

        if best_cost is None or cost.total < best_cost.total:
            best_cost = cost
            best_date = depart_date

    return best_cost, best_date, live_calls_used, cache_hits_used
