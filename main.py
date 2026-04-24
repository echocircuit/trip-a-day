"""Entry point for the trip-a-day daily run.

Usage:
    python main.py

Reads preferences from the local SQLite DB, selects a destination batch via
the configured strategy, runs a two-pass flight search (Pass 1: broad cache-
first sweep; Pass 2: full variant search for the top N candidates), ranks
results, stores them, and sends (or prints) the daily trip notification.
"""

from __future__ import annotations

import json
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
from trip_a_day.costs import build_cost_breakdown, is_valid_cost_breakdown
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
    get_nearby_airports,
    haversine_miles,
)
from trip_a_day.filters import apply_destination_filters
from trip_a_day.links import build_car_url
from trip_a_day.notifier import send_trip_notification
from trip_a_day.preferences import get, get_all, get_bool, get_int, get_or
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
        num_rooms = get_int(session, "num_rooms")
        preferred_car_site = get_or(session, "preferred_car_site", "kayak")
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

        # ── Apply destination filters to full pool before batch selection ──────
        all_prefs = get_all(session)
        full_pool: list[Destination] = (
            session.query(Destination)
            .filter(Destination.enabled.is_(True), Destination.excluded.is_(False))
            .all()
        )
        eligible_pool, filter_fallback = apply_destination_filters(
            full_pool, session, all_prefs
        )
        if filter_fallback:
            logger.warning(
                "All filters combined produced an empty pool — running unfiltered."
            )
        else:
            logger.info(
                "After filters: %d / %d destinations eligible.",
                len(eligible_pool),
                len(full_pool),
            )

        # ── Select daily batch from eligible pool ─────────────────────────────
        batch = select_daily_batch(
            selection_strategy, daily_batch_size, session, pool=eligible_pool
        )
        session.commit()
        logger.info(
            "Batch: %d destinations via strategy '%s'", len(batch), selection_strategy
        )

        # ── Phase 7: resolve departure airports ──────────────────────────────
        search_radius_miles = get_int(session, "search_radius_miles")
        irs_mileage_rate = float(get_or(session, "irs_mileage_rate", "0.70"))

        if search_radius_miles > 0:
            nearby_airports = get_nearby_airports(
                home_airport, float(search_radius_miles), session
            )
            logger.info(
                "Multi-airport: %d nearby airport(s) within %d mi of %s: %s",
                len(nearby_airports),
                search_radius_miles,
                home_airport,
                [a.iata for a in nearby_airports],
            )
        else:
            nearby_airports = []

        departure_iatas = [home_airport] + [a.iata for a in nearby_airports]

        # ── Two-pass search across all departure airports ─────────────────────
        flights_calls_start = get_api_calls_today(session, "google_flights")
        live_calls_made = 0
        now_utc = datetime.now(UTC)
        all_candidates: list[TripCandidate] = []
        any_pass1_prices = False
        # Tracks destinations skipped due to invalid cost data (e.g. $0 flight).
        invalid_exclusions: list[dict[str, str]] = []

        for dep_iata in departure_iatas:
            # Round-trip IRS-rate driving cost from home to this departure airport
            if dep_iata == home_airport:
                transport_usd = 0.0
            else:
                dep_info = get_airport_info(dep_iata, session)
                if dep_info and dep_info.latitude and dep_info.longitude:
                    dep_dist = haversine_miles(
                        home_lat, home_lon, dep_info.latitude, dep_info.longitude
                    )
                    transport_usd = round(dep_dist * 2 * irs_mileage_rate, 2)
                else:
                    transport_usd = 0.0

            logger.info(
                "--- Searching from %s (transport cost: $%.2f) ---",
                dep_iata,
                transport_usd,
            )

            # ── Pass 1: quick price estimate per destination ──────────────────
            pass1_prices: dict[str, float] = {}

            for dest in batch:
                iata = dest.iata_code

                if _is_excluded(session, iata):
                    continue

                hit = None
                if cache_ttl_enabled:
                    hit = get_cached_flight(
                        session,
                        dep_iata,
                        iata,
                        departure_date,
                        base_return,
                        num_adults,
                        num_children,
                    )

                # Reject cached $0 prices: re-query live rather than trusting
                # a stale invalid entry (e.g. OAK 2026-04-20, is_mock=False).
                if hit is not None and hit.price_usd <= 0:
                    logger.warning(
                        "  [cache] %s→%s cached price is $%.0f (invalid) — re-querying",
                        dep_iata,
                        iata,
                        hit.price_usd,
                    )
                    hit = None

                if hit is not None:
                    pass1_prices[iata] = hit.price_usd
                    logger.info(
                        "  [cache] %s→%s — $%.0f", dep_iata, iata, hit.price_usd
                    )
                else:
                    if not is_mock and live_calls_made >= max_live_calls:
                        logger.info("  [skip]  %s — live call cap reached", iata)
                        continue

                    flight = get_flight_offers(
                        origin=dep_iata,
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
                            dep_iata,
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

                    logger.info(
                        "  [live]  %s→%s — $%.0f", dep_iata, iata, flight.price_total
                    )

                # Only track destination stats against the home airport
                # to avoid inflating query_count for multi-airport runs.
                if dep_iata == home_airport:
                    dest.last_queried_at = now_utc
                    dest.last_known_price_usd = pass1_prices.get(iata)
                    dest.last_known_price_date = run_date
                    dest.query_count = (dest.query_count or 0) + 1

            session.commit()

            if not pass1_prices:
                logger.warning(
                    "Pass 1 from %s returned no prices — skipping this departure airport.",
                    dep_iata,
                )
                continue

            any_pass1_prices = True
            top_iatas = sorted(pass1_prices, key=lambda k: pass1_prices[k])[
                :two_pass_count
            ]
            logger.info(
                "Pass 1 from %s — top %d: %s",
                dep_iata,
                len(top_iatas),
                ", ".join(f"{k}(${pass1_prices[k]:.0f})" for k in top_iatas),
            )

            # ── Pass 2: full variant search for top N ─────────────────────────
            for iata in top_iatas:
                logger.info("Pass 2 — %s→%s …", dep_iata, iata)

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
                        origin=dep_iata,
                        destination=iata,
                        depart_date=departure_date,
                        return_date=return_date_v,
                        adults=num_adults,
                        children=num_children,
                        session=session,
                        direct_only=direct_flights_only,
                    )
                    if flight is None:
                        logger.info(
                            "  No flight %s→%s for %d nights — skipping variant.",
                            dep_iata,
                            iata,
                            nights,
                        )
                        continue

                    hotel = get_hotel_offers(
                        city_code=iata,
                        checkin=departure_date,
                        checkout=return_date_v,
                        adults=num_adults,
                        session=session,
                        num_rooms=num_rooms,
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
                        transport_usd=transport_usd,
                    )

                    valid, reason = is_valid_cost_breakdown(cost)
                    if not valid:
                        logger.warning(
                            "Excluding %s (%s): %s — skipping this destination",
                            city,
                            iata,
                            reason,
                        )
                        invalid_exclusions.append(
                            {"iata": iata, "city": city, "reason": reason}
                        )
                        continue

                    if best is None or cost.total < best.cost.total:
                        car_url = build_car_url(
                            iata,
                            city,
                            departure_date,
                            return_date_v,
                            preferred_car_site,
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
                            departure_airport=dep_iata,
                        )

                if best is None:
                    logger.info(
                        "  No complete trip found for %s→%s — skipping.", dep_iata, iata
                    )
                    session.commit()
                    continue

                all_candidates.append(best)
                nights_won = (best.return_date - best.departure_date).days
                logger.info(
                    "  Best %s→%s: %d nights — $%.2f"
                    " (flight $%.2f | hotel $%.2f | car $%.2f"
                    " | food $%.2f | transport $%.2f)",
                    dep_iata,
                    iata,
                    nights_won,
                    best.cost.total,
                    best.cost.flights,
                    best.cost.hotel,
                    best.cost.car,
                    best.cost.food,
                    best.cost.transport_usd,
                )
                session.commit()

        flights_calls_this_run = (
            get_api_calls_today(session, "google_flights") - flights_calls_start
        )
        duration = round(time.monotonic() - start_time, 1)

        if not any_pass1_prices:
            logger.error(
                "Pass 1 returned no prices from any departure airport"
                " — check connectivity or pool."
            )
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

        if not all_candidates:
            logger.error("No valid trip candidates found. Logging failed run.")
            session.add(
                RunLog(
                    run_at=datetime.now(UTC),
                    status="failed",
                    triggered_by=triggered_by,
                    destinations_evaluated=0,
                    error_message="No valid candidates after Pass 2",
                    duration_seconds=duration,
                    api_calls_flights=flights_calls_this_run,
                )
            )
            session.commit()
            sys.exit(1)

        # ── Rank and store ────────────────────────────────────────────────────
        ranked = rank_trips(all_candidates, strategy=ranking_strategy)
        winner = ranked[0]

        dep_note = (
            f" (departing from {winner.departure_airport})"
            if winner.departure_airport and winner.departure_airport != home_airport
            else ""
        )
        logger.info(
            "\n🏆 Winner: %s, %s — $%.2f total%s",
            winner.city,
            winner.country,
            winner.cost.total,
            dep_note,
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

        exclusions_json = json.dumps(invalid_exclusions) if invalid_exclusions else None
        if invalid_exclusions:
            logger.warning(
                "%d destination(s) excluded due to invalid cost data: %s",
                len(invalid_exclusions),
                ", ".join(f"{e['city']} ({e['iata']})" for e in invalid_exclusions),
            )
        session.add(
            RunLog(
                run_at=datetime.now(UTC),
                status="success",
                triggered_by=triggered_by,
                destinations_evaluated=len(all_candidates),
                winner_trip_id=winner_trip_id,
                duration_seconds=duration,
                api_calls_flights=flights_calls_this_run,
                filter_fallback=filter_fallback,
                invalid_data_exclusions=exclusions_json,
            )
        )
        session.commit()

        # ── Notify ────────────────────────────────────────────────────────────
        notifications_enabled = (
            get_or(session, "notifications_enabled", "true") == "true"
        )
        if not notifications_enabled:
            logger.info("Notifications disabled — skipping email.")
        else:
            notified = send_trip_notification(
                winner,
                all_prefs,
                filter_fallback=filter_fallback,
                is_mock=is_mock,
                home_airport=home_airport,
                trip_id=winner_trip_id,
            )
            if notified:
                winner_row = session.get(Trip, winner_trip_id)
                if winner_row:
                    winner_row.notified = True
                session.commit()

    logger.info(
        "Run complete in %.1fs. Evaluated %d Pass-2 candidates.",
        duration,
        len(all_candidates),
    )


if __name__ == "__main__":
    run()
