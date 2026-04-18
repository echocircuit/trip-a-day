"""External API calls: Amadeus (flights + hotels) and Numbeo (food costs).

All public functions return typed dataclasses — never raw API response dicts.
All calls check api_usage before executing and increment it after success.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import requests
from amadeus import Client, ResponseError
from sqlalchemy.orm import Session

from trip_a_day.db import get_api_calls_today, record_api_call

logger = logging.getLogger(__name__)

# Maps ISO-3166-1 alpha-2 country code → world region (matches car_rates.json keys)
_COUNTRY_TO_REGION: dict[str, str] = {
    # North America
    "US": "North America",
    "CA": "North America",
    # Mexico / Central America
    "MX": "Mexico / Central America",
    "GT": "Mexico / Central America",
    "BZ": "Mexico / Central America",
    "SV": "Mexico / Central America",
    "HN": "Mexico / Central America",
    "NI": "Mexico / Central America",
    "CR": "Mexico / Central America",
    "PA": "Mexico / Central America",
    # Caribbean
    "CU": "Caribbean",
    "JM": "Caribbean",
    "HT": "Caribbean",
    "DO": "Caribbean",
    "PR": "Caribbean",
    "TT": "Caribbean",
    "BB": "Caribbean",
    "BS": "Caribbean",
    "LC": "Caribbean",
    "VC": "Caribbean",
    "GD": "Caribbean",
    "AG": "Caribbean",
    "KN": "Caribbean",
    "DM": "Caribbean",
    "AI": "Caribbean",
    "VG": "Caribbean",
    "VI": "Caribbean",
    "AW": "Caribbean",
    "CW": "Caribbean",
    "TC": "Caribbean",
    "KY": "Caribbean",
    "BM": "Caribbean",
    "MQ": "Caribbean",
    "GP": "Caribbean",
    # South America
    "CO": "South America",
    "VE": "South America",
    "GY": "South America",
    "SR": "South America",
    "BR": "South America",
    "EC": "South America",
    "PE": "South America",
    "BO": "South America",
    "PY": "South America",
    "CL": "South America",
    "AR": "South America",
    "UY": "South America",
    # Western Europe
    "GB": "Western Europe",
    "IE": "Western Europe",
    "FR": "Western Europe",
    "BE": "Western Europe",
    "NL": "Western Europe",
    "LU": "Western Europe",
    "DE": "Western Europe",
    "AT": "Western Europe",
    "CH": "Western Europe",
    "ES": "Western Europe",
    "PT": "Western Europe",
    "IT": "Western Europe",
    "GR": "Western Europe",
    "MT": "Western Europe",
    "CY": "Western Europe",
    "IS": "Western Europe",
    "NO": "Western Europe",
    "SE": "Western Europe",
    "FI": "Western Europe",
    "DK": "Western Europe",
    "AD": "Western Europe",
    "MC": "Western Europe",
    "SM": "Western Europe",
    # Eastern Europe
    "PL": "Eastern Europe",
    "CZ": "Eastern Europe",
    "SK": "Eastern Europe",
    "HU": "Eastern Europe",
    "SI": "Eastern Europe",
    "HR": "Eastern Europe",
    "BA": "Eastern Europe",
    "RS": "Eastern Europe",
    "ME": "Eastern Europe",
    "AL": "Eastern Europe",
    "MK": "Eastern Europe",
    "BG": "Eastern Europe",
    "RO": "Eastern Europe",
    "MD": "Eastern Europe",
    "UA": "Eastern Europe",
    "BY": "Eastern Europe",
    "LT": "Eastern Europe",
    "LV": "Eastern Europe",
    "EE": "Eastern Europe",
    "RU": "Eastern Europe",
    # Middle East
    "TR": "Middle East",
    "IL": "Middle East",
    "JO": "Middle East",
    "LB": "Middle East",
    "IQ": "Middle East",
    "KW": "Middle East",
    "SA": "Middle East",
    "AE": "Middle East",
    "QA": "Middle East",
    "BH": "Middle East",
    "OM": "Middle East",
    "EG": "Middle East",
    # Africa
    "MA": "Africa",
    "DZ": "Africa",
    "TN": "Africa",
    "NG": "Africa",
    "GH": "Africa",
    "KE": "Africa",
    "TZ": "Africa",
    "ET": "Africa",
    "ZA": "Africa",
    "SN": "Africa",
    "CM": "Africa",
    "MG": "Africa",
    "MZ": "Africa",
    "ZW": "Africa",
    "ZM": "Africa",
    "RW": "Africa",
    # South Asia
    "IN": "South Asia",
    "PK": "South Asia",
    "BD": "South Asia",
    "NP": "South Asia",
    "LK": "South Asia",
    "MV": "South Asia",
    # Southeast Asia
    "TH": "Southeast Asia",
    "VN": "Southeast Asia",
    "ID": "Southeast Asia",
    "MY": "Southeast Asia",
    "PH": "Southeast Asia",
    "SG": "Southeast Asia",
    "KH": "Southeast Asia",
    "MM": "Southeast Asia",
    "LA": "Southeast Asia",
    "BN": "Southeast Asia",
    # East Asia
    "JP": "East Asia",
    "KR": "East Asia",
    "CN": "East Asia",
    "TW": "East Asia",
    "HK": "East Asia",
    "MO": "East Asia",
    "MN": "East Asia",
    # Central Asia
    "KZ": "Central Asia",
    "UZ": "Central Asia",
    "KG": "Central Asia",
    "TJ": "Central Asia",
    "TM": "Central Asia",
    # Oceania
    "AU": "Oceania",
    "NZ": "Oceania",
    "PG": "Oceania",
    "FJ": "Oceania",
    "SB": "Oceania",
    "VU": "Oceania",
}

# Food cost fallback rates (USD per person per day) by region
_FOOD_FALLBACK: dict[str, float] = {
    "North America": 60.0,
    "Mexico / Central America": 30.0,
    "Caribbean": 45.0,
    "South America": 35.0,
    "Western Europe": 55.0,
    "Eastern Europe": 35.0,
    "Middle East": 40.0,
    "Africa": 30.0,
    "South Asia": 20.0,
    "Southeast Asia": 25.0,
    "East Asia": 45.0,
    "Central Asia": 25.0,
    "Oceania": 60.0,
    "Other": 50.0,
}

# Amadeus monthly call limit (free production tier)
_AMADEUS_MONTHLY_LIMIT = 2000


@dataclass
class FlightDestination:
    """A cheap destination returned by Amadeus Flight Inspiration Search."""

    origin: str
    destination: str
    departure_date: date
    return_date: date
    price_total: float
    links: dict[str, str] = field(default_factory=dict)


@dataclass
class FlightOffer:
    """Cheapest flight offer from Amadeus Flight Offers Search."""

    origin: str
    destination: str
    departure_date: date
    return_date: date
    price_total: float
    booking_url: str
    raw: str  # JSON blob for DB storage


@dataclass
class HotelOffer:
    """Cheapest qualifying hotel offer from Amadeus Hotel Offers Search."""

    hotel_id: str
    hotel_name: str
    city_code: str
    check_in: date
    check_out: date
    price_total: float
    booking_url: str
    raw: str  # JSON blob for DB storage


@dataclass
class FoodEstimate:
    """Estimated food cost for a trip."""

    city: str
    country: str
    cost_per_person_per_day: float
    total_cost: float
    source: str  # "numbeo" or "fallback"


@dataclass
class AirportInfo:
    """Basic airport/city metadata from Amadeus Reference Data."""

    iata: str
    city: str
    country: str
    country_code: str
    region: str
    latitude: float
    longitude: float


_amadeus_client: Client | None = None


def _get_amadeus() -> Client:
    global _amadeus_client
    if _amadeus_client is None:
        _amadeus_client = Client(
            client_id=os.environ["AMADEUS_API_KEY"],
            client_secret=os.environ["AMADEUS_API_SECRET"],
            hostname=os.environ.get("AMADEUS_ENV", "test"),
        )
    return _amadeus_client


def _check_amadeus_limit(session: Session) -> bool:
    """Return True if we can make another Amadeus call; False if limit exceeded."""
    # Monthly limit check (daily tracking approximated from db)
    today_calls = get_api_calls_today(session, "amadeus")
    # Conservative daily budget: monthly_limit / 30
    daily_budget = _AMADEUS_MONTHLY_LIMIT // 30
    if today_calls >= daily_budget:
        logger.warning(
            "Amadeus daily budget of %d calls reached (%d made today). Skipping.",
            daily_budget,
            today_calls,
        )
        return False
    return True


def get_cheapest_destinations(
    origin_iata: str,
    departure_date: date,
    session: Session,
    n: int = 10,
) -> list[FlightDestination]:
    """Call Amadeus Flight Inspiration Search and return up to *n* destinations."""
    if not _check_amadeus_limit(session):
        return []

    try:
        amadeus = _get_amadeus()
        response = amadeus.shopping.flight_destinations.get(
            origin=origin_iata,
            departureDate=departure_date.isoformat(),
            oneWay=False,
            nonStop=True,
        )
        record_api_call(session, "amadeus")
    except ResponseError as exc:
        logger.error("Amadeus Flight Inspiration Search failed: %s", exc)
        return []
    except KeyError:
        logger.warning(
            "AMADEUS_API_KEY or AMADEUS_API_SECRET not set — skipping fetch."
        )
        return []

    results: list[FlightDestination] = []
    for item in (response.data or [])[:n]:
        try:
            depart = date.fromisoformat(item["departureDate"])
            ret = date.fromisoformat(item["returnDate"])
            price = float(item["price"]["total"])
            results.append(
                FlightDestination(
                    origin=item["origin"],
                    destination=item["destination"],
                    departure_date=depart,
                    return_date=ret,
                    price_total=price,
                    links=item.get("links", {}),
                )
            )
        except (KeyError, ValueError) as exc:
            logger.debug("Skipping malformed destination item: %s", exc)

    return results


def get_flight_offers(
    origin: str,
    destination: str,
    depart_date: date,
    return_date: date,
    adults: int,
    children: int,
    session: Session,
) -> FlightOffer | None:
    """Return the cheapest nonstop flight offer, or None if unavailable."""
    if not _check_amadeus_limit(session):
        return None

    try:
        amadeus = _get_amadeus()
        kwargs: dict[str, Any] = dict(
            originLocationCode=origin,
            destinationLocationCode=destination,
            departureDate=depart_date.isoformat(),
            returnDate=return_date.isoformat(),
            adults=adults,
            nonStop=True,
            max=1,
            currencyCode="USD",
        )
        if children > 0:
            kwargs["children"] = children
        response = amadeus.shopping.flight_offers_search.get(**kwargs)
        record_api_call(session, "amadeus")
    except ResponseError as exc:
        logger.debug("Flight Offers Search %s→%s failed: %s", origin, destination, exc)
        return None
    except KeyError:
        return None

    data = response.data or []
    if not data:
        return None

    offer = data[0]
    try:
        price = float(offer["price"]["grandTotal"])
    except (KeyError, ValueError):
        return None

    booking_url = (
        offer.get("links", {}).get("flightOffers")
        or f"https://www.google.com/flights?hl=en#flt={origin}.{destination}.{depart_date.isoformat()}"
    )

    return FlightOffer(
        origin=origin,
        destination=destination,
        departure_date=depart_date,
        return_date=return_date,
        price_total=price,
        booking_url=booking_url,
        raw=json.dumps(offer),
    )


def get_hotel_offers(
    city_code: str,
    checkin: date,
    checkout: date,
    adults: int,
    session: Session,
    min_stars: int = 4,
) -> HotelOffer | None:
    """Return the cheapest hotel offer meeting *min_stars* in *city_code*, or None."""
    if not _check_amadeus_limit(session):
        return None

    # Step 1: Get hotel IDs for the city
    try:
        amadeus = _get_amadeus()
        hotel_list_response = amadeus.reference_data.locations.hotels.by_city.get(
            cityCode=city_code,
            ratings=[r for r in range(min_stars, 6)],
        )
        record_api_call(session, "amadeus")
    except ResponseError as exc:
        logger.debug("Hotel List for %s failed: %s", city_code, exc)
        return None
    except KeyError:
        return None

    hotel_data = hotel_list_response.data or []
    if not hotel_data:
        logger.debug("No %d-star hotels found in %s", min_stars, city_code)
        return None

    hotel_ids = [h["hotelId"] for h in hotel_data[:20] if "hotelId" in h]
    if not hotel_ids:
        return None

    # Step 2: Get pricing for those hotels
    if not _check_amadeus_limit(session):
        return None

    try:
        offers_response = amadeus.shopping.hotel_offers_search.get(
            hotelIds=hotel_ids,
            checkInDate=checkin.isoformat(),
            checkOutDate=checkout.isoformat(),
            adults=adults,
            roomQuantity=1,
            currency="USD",
            bestRateOnly=True,
        )
        record_api_call(session, "amadeus")
    except ResponseError as exc:
        logger.debug("Hotel Offers Search for %s failed: %s", city_code, exc)
        return None
    except KeyError:
        return None

    offers = offers_response.data or []
    if not offers:
        return None

    # Find the cheapest available offer
    best: dict | None = None
    best_price = float("inf")
    for h in offers:
        for offer in h.get("offers", []):
            try:
                price = float(offer["price"]["total"])
                if price < best_price:
                    best_price = price
                    best = h
            except (KeyError, ValueError):
                continue

    if best is None:
        return None

    hotel_name = best.get("hotel", {}).get("name", "Unknown Hotel")
    hotel_id = best.get("hotel", {}).get("hotelId", "")
    booking_url = f"https://www.booking.com/searchresults.html?ss={city_code}&checkin={checkin.isoformat()}&checkout={checkout.isoformat()}"

    return HotelOffer(
        hotel_id=hotel_id,
        hotel_name=hotel_name,
        city_code=city_code,
        check_in=checkin,
        check_out=checkout,
        price_total=round(best_price, 2),
        booking_url=booking_url,
        raw=json.dumps(best),
    )


def get_airport_info(iata: str, session: Session) -> AirportInfo | None:
    """Return airport metadata (city, country, coordinates) from Amadeus Reference Data."""
    if not _check_amadeus_limit(session):
        return None

    try:
        amadeus = _get_amadeus()
        response = amadeus.reference_data.locations.get(
            keyword=iata,
            subType="AIRPORT",
        )
        record_api_call(session, "amadeus")
    except ResponseError as exc:
        logger.debug("Airport info for %s failed: %s", iata, exc)
        return None
    except KeyError:
        return None

    for loc in response.data or []:
        if loc.get("iataCode") == iata:
            geo = loc.get("geoCode", {})
            address = loc.get("address", {})
            country_code = address.get("countryCode", "")
            region = _COUNTRY_TO_REGION.get(country_code, "Other")
            return AirportInfo(
                iata=iata,
                city=address.get("cityName", iata),
                country=address.get("countryName", "Unknown"),
                country_code=country_code,
                region=region,
                latitude=float(geo.get("latitude", 0.0)),
                longitude=float(geo.get("longitude", 0.0)),
            )
    return None


def get_food_cost(
    city: str,
    country: str,
    region: str,
    days: int,
    people: int,
    session: Session,
) -> FoodEstimate:
    """Estimate food cost via Numbeo API, falling back to regional defaults."""
    numbeo_key = os.environ.get("NUMBEO_API_KEY", "")
    if numbeo_key:
        estimate = _fetch_numbeo_food(city, country, days, people, numbeo_key, session)
        if estimate is not None:
            return estimate

    # Fallback: use regional estimate
    per_person_per_day = _FOOD_FALLBACK.get(region, 50.0)
    total = round(per_person_per_day * people * days, 2)
    logger.debug(
        "Using fallback food cost for %s: $%.2f/person/day", region, per_person_per_day
    )
    return FoodEstimate(
        city=city,
        country=country,
        cost_per_person_per_day=per_person_per_day,
        total_cost=total,
        source="fallback",
    )


def _fetch_numbeo_food(
    city: str,
    country: str,
    days: int,
    people: int,
    api_key: str,
    session: Session,
) -> FoodEstimate | None:
    """Try to get meal costs from Numbeo. Returns None on any failure."""
    query = f"{city}, {country}"
    try:
        resp = requests.get(
            "https://www.numbeo.com/api/city_prices",
            params={"api_key": api_key, "query": query, "currency": "USD"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        record_api_call(session, "numbeo")
    except Exception as exc:
        logger.debug("Numbeo request for %s failed: %s", query, exc)
        return None

    # Item IDs: 1 = Meal inexpensive restaurant, 2 = Meal for 2 mid-range
    prices: dict[int, float] = {}
    for item in data.get("prices", []):
        item_id = item.get("item_id")
        avg = item.get("average_price")
        if item_id in (1, 2) and avg:
            prices[item_id] = float(avg)

    if not prices:
        return None

    # Estimate: 2 inexpensive meals + 1 mid-range dinner per person per day
    inexpensive = prices.get(1, 0.0)
    midrange_for_two = prices.get(2, 0.0)
    per_person_per_day = inexpensive * 2 + (midrange_for_two / 2)

    if per_person_per_day <= 0:
        return None

    total = round(per_person_per_day * people * days, 2)
    return FoodEstimate(
        city=city,
        country=country,
        cost_per_person_per_day=round(per_person_per_day, 2),
        total_cost=total,
        source="numbeo",
    )


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in miles between two lat/lon points."""
    import math

    r = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return round(2 * r * math.asin(math.sqrt(a)), 1)
