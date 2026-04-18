"""Entry point for the trip-a-day daily run.

Usage:
    python main.py

Reads preferences from the local SQLite DB, fetches candidates via Amadeus,
ranks them, stores results, and sends (or prints) the daily trip notification.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Load .env before any other imports that might read env vars
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

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
    get_cheapest_destinations,
    get_flight_offers,
    get_food_cost,
    get_hotel_offers,
    haversine_miles,
)
from trip_a_day.notifier import send_trip_notification
from trip_a_day.preferences import get, get_all, get_int
from trip_a_day.ranker import TripCandidate, rank_trips

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# HSV coordinates for distance calculation (hardcoded home airport for Phase 1)
_HSV_LAT = 34.6418
_HSV_LON = -86.7751


def _upsert_destination(
    session, iata: str, city: str, country: str, region: str, lat: float, lon: float
) -> None:
    existing = session.get(Destination, iata)
    if existing is None:
        session.add(
            Destination(
                iata_code=iata,
                city=city,
                country=country,
                region=region,
                latitude=lat,
                longitude=lon,
                excluded=False,
            )
        )
    else:
        # Update metadata if we have better info
        if city and city != iata:
            existing.city = city
        if country:
            existing.country = country
        if region:
            existing.region = region
        if lat:
            existing.latitude = lat
        if lon:
            existing.longitude = lon


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


def run() -> None:
    start_time = time.monotonic()
    run_date = date.today()

    logger.info("trip-a-day starting run for %s", run_date)

    init_db()

    with SessionFactory() as session:
        seed_preferences(session)
        session.commit()

        # Read preferences
        home_airport = get(session, "home_airport")
        trip_nights = get_int(session, "trip_length_nights")
        advance_days = get_int(session, "advance_days")
        num_adults = get_int(session, "num_adults")
        num_children = get_int(session, "num_children")
        min_stars = get_int(session, "min_hotel_stars")
        ranking_strategy = get(session, "ranking_strategy")

        departure_date = run_date + timedelta(days=advance_days)
        return_date = departure_date + timedelta(days=trip_nights)

        logger.info(
            "Searching from %s | depart %s → return %s | %d adults %d children",
            home_airport,
            departure_date,
            return_date,
            num_adults,
            num_children,
        )

        # Get top cheapest destinations
        raw_destinations = get_cheapest_destinations(
            origin_iata=home_airport,
            departure_date=departure_date,
            session=session,
            n=10,
        )
        session.commit()

        if not raw_destinations:
            logger.warning(
                "No destinations returned — check Amadeus credentials and sandbox data."
            )

        candidates: list[TripCandidate] = []
        amadeus_calls_start = get_api_calls_today(session, "amadeus")

        for dest in raw_destinations:
            iata = dest.destination
            logger.info("Evaluating %s …", iata)

            if _is_excluded(session, iata):
                logger.info("  Skipped — on exclusion list.")
                continue

            # Resolve airport metadata (city, country, coordinates)
            airport = get_airport_info(iata, session)
            if airport:
                city = airport.city.title()
                country = airport.country.title()
                region = airport.region
                lat, lon = airport.latitude, airport.longitude
            else:
                city = iata
                country = "Unknown"
                region = "Other"
                lat, lon = 0.0, 0.0

            _upsert_destination(session, iata, city, country, region, lat, lon)

            # Flight offers
            flight = get_flight_offers(
                origin=home_airport,
                destination=iata,
                depart_date=departure_date,
                return_date=return_date,
                adults=num_adults,
                children=num_children,
                session=session,
            )
            if flight is None:
                logger.info("  No flight found — skipping.")
                session.commit()
                continue

            # Hotel offers
            hotel = get_hotel_offers(
                city_code=iata,
                checkin=departure_date,
                checkout=return_date,
                adults=num_adults,
                session=session,
                min_stars=min_stars,
            )
            if hotel is None:
                logger.info("  No qualifying hotel found — skipping.")
                session.commit()
                continue

            # Food cost
            food = get_food_cost(
                city=city,
                country=country,
                region=region,
                days=trip_nights,
                people=num_adults + num_children,
                session=session,
            )

            # Build cost breakdown
            cost = build_cost_breakdown(
                flight_total=flight.price_total,
                hotel_total=hotel.price_total,
                car_region=region,
                food_total=food.total_cost,
                days=trip_nights,
            )

            # Calculate distance
            distance = (
                haversine_miles(_HSV_LAT, _HSV_LON, lat, lon)
                if lat != 0.0 or lon != 0.0
                else 0.0
            )

            car_url = (
                f"https://www.kayak.com/cars/{iata}/{departure_date.isoformat()}"
                f"/{return_date.isoformat()}"
            )

            candidate = TripCandidate(
                destination_iata=iata,
                city=city,
                country=country,
                region=region,
                departure_date=departure_date,
                return_date=return_date,
                cost=cost,
                distance_miles=distance,
                flight_booking_url=flight.booking_url,
                hotel_booking_url=hotel.booking_url,
                car_booking_url=car_url,
                raw_flight_data=flight.raw,
                raw_hotel_data=hotel.raw,
            )
            candidates.append(candidate)
            logger.info(
                "  Total: $%.2f (flight $%.2f | hotel $%.2f | car $%.2f | food $%.2f)",
                cost.total,
                cost.flights,
                cost.hotel,
                cost.car,
                cost.food,
            )

            session.commit()

        amadeus_calls_this_run = (
            get_api_calls_today(session, "amadeus") - amadeus_calls_start
        )
        duration = round(time.monotonic() - start_time, 1)

        if not candidates:
            logger.error("No valid trip candidates found. Logging failed run.")
            log = RunLog(
                run_at=datetime.now(UTC),
                status="failed",
                triggered_by="manual",
                destinations_evaluated=len(raw_destinations),
                error_message="No valid candidates after filtering",
                duration_seconds=duration,
                api_calls_amadeus=amadeus_calls_this_run,
            )
            session.add(log)
            session.commit()
            sys.exit(1)

        # Rank
        ranked = rank_trips(candidates, strategy=ranking_strategy)
        winner = ranked[0]

        logger.info(
            "\n🏆 Winner: %s, %s — $%.2f total",
            winner.city,
            winner.country,
            winner.cost.total,
        )

        # Store all candidates to DB
        trip_ids = _store_results(session, ranked, run_date)
        winner_trip_id = trip_ids[0]

        # Mark winner as notified after sending
        log = RunLog(
            run_at=datetime.now(UTC),
            status="success",
            triggered_by="manual",
            destinations_evaluated=len(candidates),
            winner_trip_id=winner_trip_id,
            duration_seconds=duration,
            api_calls_amadeus=amadeus_calls_this_run,
        )
        session.add(log)
        session.commit()

        # Send notification
        all_prefs = get_all(session)
        notified = send_trip_notification(winner, all_prefs)

        if notified:
            winner_row = session.get(Trip, winner_trip_id)
            if winner_row:
                winner_row.notified = True
            session.commit()

    logger.info(
        "Run complete in %.1fs. Evaluated %d candidates.", duration, len(candidates)
    )


if __name__ == "__main__":
    run()
