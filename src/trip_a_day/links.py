"""Deep-link URL builders for flight, hotel, and car rental booking sites.

All URL construction lives here. notifier.py and main.py call these functions;
they never build booking URLs directly.

URL patterns verified 2026-04-24:
  google_flights : ✓ origin, destination, and dates pre-filled correctly
  google_hotels  : ✓  (Google Travel Hotels search with checkin/checkout params)
  booking_com    : ✓  (Booking.com searchresults with split date params)
  expedia_hotels : ✓  (Expedia Hotel-Search with MM/DD/YYYY dates)
  kayak          : ✓  (Kayak /cars/{IATA}/{date-10h}/{date-10h} pattern)
  expedia_cars   : ✓  (Expedia carsearch with MM/DD/YYYY dates)
"""

from __future__ import annotations

from datetime import date
from urllib.parse import quote_plus


def _valid_airline_iata(code: str | None) -> str | None:
    """Return *code* if it is a valid 2-character airline IATA code, else None.

    Airline IATA codes are exactly 2 alphanumeric characters (e.g. "AA", "B6").
    Anything longer (e.g. a full airline name from the fast-flights library) would
    corrupt the Google Flights #flt= fragment and prevent pre-filling.
    """
    if not code:
        return None
    code = code.strip().upper()
    if len(code) == 2 and code.isalnum():
        return code
    return None


def build_flight_url(
    origin: str,
    destination: str,
    depart_date: date,
    return_date: date,
    airline_iata: str | None = None,
) -> str:
    """Return a Google Flights deep link for the given round-trip.

    The # and * in the fragment must remain literal — do not URL-encode them.
    Format: https://www.google.com/flights?hl=en#flt={orig}.{dest}.{dep}*{dest}.{orig}.{ret};c:USD;e:1;sd:1;t:f

    Appends ;a:{code} only when *airline_iata* is a valid 2-char IATA code.
    A malformed airline code in the fragment causes Google Flights JS to fail
    parsing the entire #flt= value, showing no pre-filled search.
    """
    d = depart_date.isoformat()
    r = return_date.isoformat()
    params = ";c:USD;e:1;sd:1;t:f"
    valid_airline = _valid_airline_iata(airline_iata)
    if valid_airline:
        params += f";a:{valid_airline}"
    return (
        f"https://www.google.com/flights?hl=en"
        f"#flt={origin}.{destination}.{d}*{destination}.{origin}.{r}{params}"
    )


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
