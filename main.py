"""Entry point for the trip-a-day daily run.

Usage:
    python main.py

Reads preferences from the local SQLite DB, selects a destination batch via
the configured strategy, runs a two-pass flight search (Pass 1: broad cache-
first sweep; Pass 2: full variant search for the top N candidates), ranks
results, stores them, and sends (or prints) the daily trip notification.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Load .env before any other imports that might read env vars
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from trip_a_day.cache import get_cached_flight, store_flight_cache
from trip_a_day.costs import build_cost_breakdown
from trip_a_day.db import (
    Destination,
    RunLog,
    SessionFactory,
    Trip,
    get_api_calls_today,
    init_db,
    seed_preferences,
)
from trip_a_day.fetcher import (
    get_airport_info,
    get_flight_offers,
    get_food_cost,
    get_hotel_offers,
    haversine_miles,
)
from trip_a_day.notifier import send_trip_notification
from trip_a_day.preferences import get, get_all, get_bool, get_int
from trip_a_day.ranker import TripCandidate, rank_trips
from trip_a_day.selector import select_daily_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# HSV coordinates — fallback if home airport has no coordinates in DB.
_HSV_LAT = 34.6418
_HSV_LON = -86.7751


def _build_night_variants(target: int, flex: int) -> list[int]:
    """Return unique night counts [target-flex … target+flex], all >= 1."""
    seen: set[int] = set()
    result: list[int] = []
    for delta in range(-flex, flex + 1):
        n = max(1, target + delta)
        if n not in seen:
            seen.add(n)
            result.append(n)
    return result


def _is_excluded(session, iata: str) -> bool:
    dest = session.get(Destination, iata)
    return dest is not None and dest.excluded


def _store_results(
    session, candidates: list[TripCandidate], run_date: date
) -> list[int]:
    trip_ids: list[int] = []
    for rank, candidate in enumerate(candidates, start=1):
        db_trip = Trip(
            run_date=run_date,
            destination_iata=candidate.destination_iata,
            departure_date=candidate.departure_date,
            return_date=candidate.return_date,
            flight_cost_usd=candidate.cost.flights,
            hotel_cost_usd=candidate.cost.hotel,
            car_cost_usd=candidate.cost.car,
            food_cost_usd=candidate.cost.food,
            total_cost_usd=candidate.cost.total,
            distance_miles=candidate.distance_miles,
            flight_booking_url=candidate.flight_booking_url,
            hotel_booking_url=candidate.hotel_booking_url,
            car_booking_url=candidate.car_booking_url,
            raw_flight_data=candidate.raw_flight_data,
            raw_hotel_data=candidate.raw_hotel_data,
            rank=rank,
            selected=(rank == 1),
            notified=False,
            car_cost_is_estimate=candidate.cost.car_is_estimate,
        )
        session.add(db_trip)
        session.flush()
        trip_ids.append(db_trip.id)
    return trip_ids


def run(triggered_by: str = "manual") -> None:
    start_time = time.monotonic()
    run_date = date.today()

    logger.info(
        "trip-a-day starting run for %s (triggered_by=%s)", run_date, triggered_by
    )

    init_db()

    with SessionFactory() as session:
        seed_preferences(session)
        session.commit()

        # ── Read preferences ──────────────────────────────────────────────────
        home_airport = get(session, "home_airport")
        trip_nights = get_int(session, "trip_length_nights")
        trip_flex = get_int(session, "trip_length_flex_nights")
        advance_days = get_int(session, "advance_days")
        num_adults = get_int(session, "num_adults")
        num_children = get_int(session, "num_children")
        min_stars = get_int(session, "min_hotel_stars")
        ranking_strategy = get(session, "ranking_strategy")
        direct_flights_only = get_bool(session, "direct_flights_only")
        car_rental_required = get_bool(session, "car_rental_required")
        # Phase 5 pool prefs
        daily_batch_size = get_int(session, "daily_batch_size")
        selection_strategy = get(session, "destination_selection_strategy")
        cache_ttl_enabled = get_bool(session, "cache_ttl_enabled")
        max_live_calls = get_int(session, "max_live_calls_per_run")
        two_pass_count = get_int(session, "two_pass_candidate_count")

        departure_date = run_date + timedelta(days=advance_days)
        night_variants = _build_night_variants(trip_nights, trip_flex)
        base_return = departure_date + timedelta(days=trip_nights)
        is_mock = os.environ.get("FLIGHT_DATA_MODE", "mock") == "mock"

        logger.info(
            "Searching from %s | depart %s | nights %s | %d adults %d children | mode=%s",
            home_airport,
            departure_date,
            night_variants,
            num_adults,
            num_children,
            "mock" if is_mock else "live",
        )

        # Resolve home airport coordinates
        home_info = get_airport_info(home_airport, session)
        home_lat = home_info.latitude if home_info and home_info.latitude else _HSV_LAT
        home_lon = (
            home_info.longitude if home_info and home_info.longitude else _HSV_LON
        )

        # ── Select daily batch ────────────────────────────────────────────────
        batch = select_daily_batch(selection_strategy, daily_batch_size, session)
        session.commit()
        logger.info(
            "Batch: %d destinations via strategy '%s'", len(batch), selection_strategy
        )

        # ── Pass 1: quick price estimate per destination ──────────────────────
        flights_calls_start = get_api_calls_today(session, "google_flights")
        live_calls_made = 0
        now_utc = datetime.now(UTC)

        # iata -> estimated base-night flight price
        pass1_prices: dict[str, float] = {}

        for dest in batch:
            iata = dest.iata_code

            if _is_excluded(session, iata):
                continue

            # Cache check
            hit = None
            if cache_ttl_enabled:
                hit = get_cached_flight(
                    session,
                    home_airport,
                    iata,
                    departure_date,
                    base_return,
                    num_adults,
                    num_children,
                )

            if hit is not None:
                pass1_prices[iata] = hit.price_usd
                logger.info("  [cache] %s — $%.0f", iata, hit.price_usd)
            else:
                # Respect live call cap (mock calls are free)
                if not is_mock and live_calls_made >= max_live_calls:
                    logger.info("  [skip]  %s — live call cap reached", iata)
                    continue

                flight = get_flight_offers(
                    origin=home_airport,
                    destination=iata,
                    depart_date=departure_date,
                    return_date=base_return,
                    adults=num_adults,
                    children=num_children,
                    session=session,
                    direct_only=direct_flights_only,
                )
                if not is_mock:
                    live_calls_made += 1

                if flight is None:
                    continue

                pass1_prices[iata] = flight.price_total

                if cache_ttl_enabled:
                    store_flight_cache(
                        session,
                        home_airport,
                        iata,
                        departure_date,
                        base_return,
                        num_adults,
                        num_children,
                        flight.price_total,
                        None,
                        None,
                        advance_days,
                        is_mock,
                    )

                logger.info("  [live]  %s — $%.0f", iata, flight.price_total)

            # Update destination query tracking
            dest.last_queried_at = now_utc
            dest.last_known_price_usd = pass1_prices.get(iata)
            dest.last_known_price_date = run_date
            dest.query_count = (dest.query_count or 0) + 1

        session.commit()

        if not pass1_prices:
            logger.error("Pass 1 returned no prices — check connectivity or pool.")
            duration = round(time.monotonic() - start_time, 1)
            session.add(
                RunLog(
                    run_at=datetime.now(UTC),
                    status="failed",
                    triggered_by=triggered_by,
                    destinations_evaluated=0,
                    error_message="Pass 1 returned no prices",
                    duration_seconds=duration,
                    api_calls_flights=live_calls_made,
                )
            )
            session.commit()
            sys.exit(1)

        # Sort by estimated flight price; Pass 2 narrows to top N.
        top_iatas = sorted(pass1_prices, key=lambda k: pass1_prices[k])[:two_pass_count]
        logger.info(
            "Pass 1 complete — top %d: %s",
            len(top_iatas),
            ", ".join(f"{k}(${pass1_prices[k]:.0f})" for k in top_iatas),
        )

        # ── Pass 2: full variant search for top N ─────────────────────────────
        candidates: list[TripCandidate] = []

        for iata in top_iatas:
            logger.info("Pass 2 — evaluating %s …", iata)

            airport = get_airport_info(iata, session)
            if airport:
                city = airport.city.title()
                country = airport.country.title()
                region = airport.region
                lat, lon = airport.latitude or 0.0, airport.longitude or 0.0
            else:
                city = iata
                country = "Unknown"
                region = "Other"
                lat, lon = 0.0, 0.0

            distance = (
                haversine_miles(home_lat, home_lon, lat, lon)
                if lat != 0.0 or lon != 0.0
                else 0.0
            )

            best: TripCandidate | None = None
            for nights in night_variants:
                return_date_v = departure_date + timedelta(days=nights)

                flight = get_flight_offers(
                    origin=home_airport,
                    destination=iata,
                    depart_date=departure_date,
                    return_date=return_date_v,
                    adults=num_adults,
                    children=num_children,
                    session=session,
                    direct_only=direct_flights_only,
                )
                if flight is None:
                    logger.info("  No flight for %d nights — skipping variant.", nights)
                    continue

                hotel = get_hotel_offers(
                    city_code=iata,
                    checkin=departure_date,
                    checkout=return_date_v,
                    adults=num_adults,
                    session=session,
                    min_stars=min_stars,
                )
                if hotel is None:
                    logger.info(
                        "  No qualifying hotel for %d nights — skipping variant.",
                        nights,
                    )
                    continue

                food = get_food_cost(
                    city=city,
                    country=country,
                    region=region,
                    days=nights,
                    people=num_adults + num_children,
                    session=session,
                )
                cost = build_cost_breakdown(
                    flight_total=flight.price_total,
                    hotel_total=hotel.price_total,
                    car_region=region,
                    food_total=food.total_cost,
                    days=nights,
                    car_required=car_rental_required,
                )

                if best is None or cost.total < best.cost.total:
                    car_url = (
                        f"https://www.kayak.com/cars/{iata}"
                        f"/{departure_date.isoformat()}/{return_date_v.isoformat()}"
                    )
                    best = TripCandidate(
                        destination_iata=iata,
                        city=city,
                        country=country,
                        region=region,
                        departure_date=departure_date,
                        return_date=return_date_v,
                        cost=cost,
                        distance_miles=distance,
                        flight_booking_url=flight.booking_url,
                        hotel_booking_url=hotel.booking_url,
                        car_booking_url=car_url,
                        raw_flight_data=flight.raw,
                        raw_hotel_data=hotel.raw,
                    )

            if best is None:
                logger.info("  No complete trip found across all variants — skipping.")
                session.commit()
                continue

            candidates.append(best)
            nights_won = (best.return_date - best.departure_date).days
            logger.info(
                "  Best: %d nights — $%.2f (flight $%.2f | hotel $%.2f | car $%.2f | food $%.2f)",
                nights_won,
                best.cost.total,
                best.cost.flights,
                best.cost.hotel,
                best.cost.car,
                best.cost.food,
            )
            session.commit()

        flights_calls_this_run = (
            get_api_calls_today(session, "google_flights") - flights_calls_start
        )
        duration = round(time.monotonic() - start_time, 1)

        if not candidates:
            logger.error("No valid trip candidates found. Logging failed run.")
            session.add(
                RunLog(
                    run_at=datetime.now(UTC),
                    status="failed",
                    triggered_by=triggered_by,
                    destinations_evaluated=len(pass1_prices),
                    error_message="No valid candidates after Pass 2",
                    duration_seconds=duration,
                    api_calls_flights=flights_calls_this_run,
                )
            )
            session.commit()
            sys.exit(1)

        # ── Rank and store ────────────────────────────────────────────────────
        ranked = rank_trips(candidates, strategy=ranking_strategy)
        winner = ranked[0]

        logger.info(
            "\n🏆 Winner: %s, %s — $%.2f total",
            winner.city,
            winner.country,
            winner.cost.total,
        )

        trip_ids = _store_results(session, ranked, run_date)
        winner_trip_id = trip_ids[0]

        # Update winner destination stats
        winner_dest = session.get(Destination, winner.destination_iata)
        if winner_dest is not None:
            winner_dest.times_selected = (winner_dest.times_selected or 0) + 1
            n = winner_dest.query_count or 1
            old_avg = winner_dest.avg_price_usd or winner.cost.total
            winner_dest.avg_price_usd = (old_avg * (n - 1) + winner.cost.total) / n

        session.add(
            RunLog(
                run_at=datetime.now(UTC),
                status="success",
                triggered_by=triggered_by,
                destinations_evaluated=len(candidates),
                winner_trip_id=winner_trip_id,
                duration_seconds=duration,
                api_calls_flights=flights_calls_this_run,
            )
        )
        session.commit()

        # ── Notify ────────────────────────────────────────────────────────────
        all_prefs = get_all(session)
        notified = send_trip_notification(winner, all_prefs)

        if notified:
            winner_row = session.get(Trip, winner_trip_id)
            if winner_row:
                winner_row.notified = True
            session.commit()

    logger.info(
        "Run complete in %.1fs. Evaluated %d Pass-2 candidates.",
        duration,
        len(candidates),
    )


if __name__ == "__main__":
    run()
