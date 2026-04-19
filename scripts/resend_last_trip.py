"""Re-send the notification for the most recent winning trip without re-running the query.

Usage:
    python scripts/resend_last_trip.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_PROJECT_ROOT / ".env")

from sqlalchemy.orm import Session  # noqa: E402

from trip_a_day.costs import CostBreakdown  # noqa: E402
from trip_a_day.db import Destination, SessionFactory, Trip, init_db  # noqa: E402
from trip_a_day.notifier import send_trip_notification  # noqa: E402
from trip_a_day.preferences import get_all  # noqa: E402
from trip_a_day.ranker import TripCandidate  # noqa: E402


def _get_winner(session: Session) -> Trip | None:
    return session.query(Trip).filter(Trip.rank == 1).order_by(Trip.id.desc()).first()


def main() -> None:
    init_db()
    with SessionFactory() as session:
        trip_row = _get_winner(session)
        if trip_row is None:
            print(
                "No ranked trip found in DB. Run python main.py first.", file=sys.stderr
            )
            sys.exit(1)

        dest = session.get(Destination, trip_row.destination_iata)
        city = (
            dest.city or trip_row.destination_iata
            if dest
            else trip_row.destination_iata
        )
        country = dest.country or "Unknown" if dest else "Unknown"
        region = dest.region or "Other" if dest else "Other"

        candidate = TripCandidate(
            destination_iata=trip_row.destination_iata,
            city=city,
            country=country,
            region=region,
            departure_date=trip_row.departure_date,
            return_date=trip_row.return_date,
            cost=CostBreakdown(
                flights=trip_row.flight_cost_usd,
                hotel=trip_row.hotel_cost_usd,
                car=trip_row.car_cost_usd,
                food=trip_row.food_cost_usd,
                total=trip_row.total_cost_usd,
                car_is_estimate=bool(trip_row.car_cost_is_estimate),
            ),
            distance_miles=trip_row.distance_miles or 0.0,
            flight_booking_url=trip_row.flight_booking_url or "",
            hotel_booking_url=trip_row.hotel_booking_url or "",
            car_booking_url=trip_row.car_booking_url or "",
            raw_flight_data=trip_row.raw_flight_data or "{}",
            raw_hotel_data=trip_row.raw_hotel_data or "{}",
        )

        prefs = get_all(session)
        print(f"Re-sending notification for {city}, {country} (trip id {trip_row.id})…")
        ok = send_trip_notification(candidate, prefs)
        if ok:
            print("Done.")
        else:
            print("Delivery failed — check logs above.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
