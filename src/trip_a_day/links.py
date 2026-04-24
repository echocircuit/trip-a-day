"""Deep-link URL builders for flight, hotel, and car rental booking sites.

All URL construction lives here. notifier.py and main.py call these functions;
they never build booking URLs directly.

URL patterns verified 2026-04-24:
  google_flights : ✓ tfs= protobuf format — origin, destination, and dates
                     embedded in Base64 protobuf; pre-fills correctly in browser
  google_hotels  : ✓  (Google Travel Hotels search with checkin/checkout params)
  booking_com    : ✓  (Booking.com searchresults with split date params)
  expedia_hotels : ✓  (Expedia Hotel-Search with MM/DD/YYYY dates)
  kayak          : ✓  (Kayak /cars/{IATA}/{date-10h}/{date-10h} pattern)
  expedia_cars   : ✓  (Expedia carsearch with MM/DD/YYYY dates)

Google Flights note: The old #flt= URL fragment format stopped working around
2020 when Google migrated to Base64-encoded protobuf ?tfs= parameters. The tfs=
value encodes origin, destination, dates, and passenger counts inside a protobuf
binary; airport codes and ISO dates are verifiable by base64-decoding the blob.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import quote_plus

from fast_flights import FlightData, Passengers, TFSData


def build_flight_url(
    origin: str,
    destination: str,
    depart_date: date,
    return_date: date,
    adults: int = 1,
    children: int = 0,
) -> str:
    """Return a Google Flights deep link for the given round-trip.

    Uses the ?tfs= protobuf format — the only format Google Flights currently
    supports for pre-filled deep links. The tfs= value is Base64-encoded and
    embeds origin, destination, dates, and passenger counts.
    """
    tfs = TFSData.from_interface(
        flight_data=[
            FlightData(
                date=depart_date.isoformat(),
                from_airport=origin,
                to_airport=destination,
            ),
            FlightData(
                date=return_date.isoformat(),
                from_airport=destination,
                to_airport=origin,
            ),
        ],
        trip="round-trip",
        passengers=Passengers(adults=adults, children=children),
        seat="economy",
    )
    b64 = tfs.as_b64().decode()
    return f"https://www.google.com/travel/flights?tfs={b64}&hl=en&curr=USD"


def build_hotel_url(
    city: str,
    country: str,
    checkin: date,
    checkout: date,
    adults: int,
    children: int,
    rooms: int,
    site: str,
) -> str:
    """Return a hotel search URL for *site*.

    Supported sites: google_hotels, booking_com, expedia, manual.
    Raises ValueError for unknown *site* identifiers.
    """
    city_enc = quote_plus(city)
    country_enc = quote_plus(country)

    if site == "google_hotels":
        return (
            f"https://www.google.com/travel/hotels?q=hotels+in+{city_enc}"
            f"&checkin={checkin.isoformat()}"
            f"&checkout={checkout.isoformat()}"
            f"&guests={adults}"
        )

    if site == "booking_com":
        return (
            f"https://www.booking.com/searchresults.html"
            f"?ss={city_enc},+{country_enc}"
            f"&checkin_year={checkin.year}"
            f"&checkin_month={checkin.month}"
            f"&checkin_monthday={checkin.day}"
            f"&checkout_year={checkout.year}"
            f"&checkout_month={checkout.month}"
            f"&checkout_monthday={checkout.day}"
            f"&group_adults={adults}"
            f"&group_children={children}"
            f"&no_rooms={rooms}"
            f"&selected_currency=USD"
            f"&order=price"
        )

    if site == "expedia":
        ci = f"{checkin.month:02d}/{checkin.day:02d}/{checkin.year}"
        co = f"{checkout.month:02d}/{checkout.day:02d}/{checkout.year}"
        return (
            f"https://www.expedia.com/Hotel-Search"
            f"?destination={city_enc}+{country_enc}"
            f"&startDate={ci}"
            f"&endDate={co}"
            f"&adults={adults}"
            f"&children={children}"
        )

    raise ValueError(f"Unknown hotel site: {site!r}")


def build_car_url(
    destination_iata: str,
    city: str,
    pickup_date: date,
    return_date: date,
    site: str,
) -> str:
    """Return a car rental search URL for *site*.

    Supported sites: kayak, expedia_cars, manual.
    Raises ValueError for unknown *site* identifiers.
    """
    city_enc = quote_plus(city)
    pickup_str = pickup_date.isoformat()
    return_str = return_date.isoformat()

    if site == "kayak":
        return (
            f"https://www.kayak.com/cars/{destination_iata}"
            f"/{pickup_str}-10h/{return_str}-10h"
        )

    if site == "expedia_cars":
        pi = f"{pickup_date.month:02d}/{pickup_date.day:02d}/{pickup_date.year}"
        ri = f"{return_date.month:02d}/{return_date.day:02d}/{return_date.year}"
        return f"https://www.expedia.com/carsearch?locn={city_enc}&d1={pi}&d2={ri}"

    raise ValueError(f"Unknown car site: {site!r}")
