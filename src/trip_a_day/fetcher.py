"""External data fetching: fli (Google Flights) and per diem rate lookups.

All public functions return typed dataclasses — never raw response dicts.
Flight calls track usage in api_usage. Per diem and seed lookups are local and free.

# Flight library history
# fast-flights (PyPI: fast-flights, v2.2): used Phase 1-5, deprecated April 2026.
#   Root cause of failure: Google 401 "no token provided" — their internal auth endpoint
#   changed and fast-flights' playwright/impersonation dependency can no longer obtain
#   a valid token.
#   Diagnosis: AssertionError: 401 Result: {"error":"no token provided"} on every live
#   call. All destinations were failing (not route-specific). Confirmed 2026-04-26:
#     from fast_flights import FlightData, Passengers, get_flights
#     get_flights([FlightData(date="2026-06-15", from_airport="HSV", to_airport="LHR"),
#                  FlightData(date="2026-06-22", from_airport="LHR", to_airport="HSV")],
#                 trip="round-trip", seat="economy", passengers=Passengers(adults=2, children=2),
#                 fetch_mode="fallback")
#     => "Impersonate 'chrome_126' does not exist, using 'random'"
#     => AssertionError: 401 Result: {"error":"no token provided"}
#
# fli (PyPI: flights, v0.8.4+): replacement, April 2026.
#   Uses primp to mimic Chrome's TLS handshake for direct internal API access.
#   Price field is total for all passengers (not per-person).
#   Duration field is int (minutes, round-trip total).
#   7,835 airports in Airport enum; 3 of 302 seed airports absent: REP, PNH, FRU.
#   These are excluded gracefully via ValueError from _airport() -> None from get_flight_offers.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fli.models import (  # type: ignore[import]
    Airport,
    FlightSearchFilters,
    FlightSegment,
    MaxStops,
    PassengerInfo,
    SeatType,
    SortBy,
)
from fli.search import SearchFlights  # type: ignore[import]
from sqlalchemy.orm import Session

from trip_a_day.db import get_api_calls_today, record_api_call
from trip_a_day.links import build_flight_url, build_hotel_url
from trip_a_day.preferences import get_or

logger = logging.getLogger(__name__)


def get_flight_data_mode(db_session: Session) -> str:
    """Resolve flight data mode with DB preference taking priority over env var.

    Priority: DB preference → FLIGHT_DATA_MODE env var → "mock".
    This lets the UI toggle take effect without restarting Streamlit.
    """
    db_value = get_or(db_session, "flight_data_mode", "")
    if db_value in ("mock", "live"):
        return db_value
    env_value = os.environ.get("FLIGHT_DATA_MODE", "mock").lower().strip()
    return env_value if env_value in ("mock", "live") else "mock"


_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_SEED_AIRPORTS_PATH = _DATA_DIR / "seed_airports.json"
_PER_DIEM_PATH = _DATA_DIR / "per_diem_rates.json"
_MOCK_FLIGHTS_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "mock_flights.json"
)

# Lazy-loaded caches
_seed_airports: list[dict] | None = None
_per_diem_rates: list[dict] | None = None
_mock_flights: dict | None = None

# Approximate USD/mile rate used to synthesise prices for unknown route pairs.
_SYNTHETIC_PRICE_PER_MILE = 0.18
_SYNTHETIC_MIN_PRICE = 150.0

# Soft daily limit for Google Flights calls (self-limiting, not enforced by Google)
_GOOGLE_FLIGHTS_DAILY_SOFT_LIMIT = 300

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

# Regional MIE fallback rates when per diem lookup finds nothing (USD/person/day)
_MIE_FALLBACK: dict[str, float] = {
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

# Regional lodging fallback (USD/night) — used when per diem has no match
_LODGING_FALLBACK: dict[str, float] = {
    "North America": 150.0,
    "Mexico / Central America": 80.0,
    "Caribbean": 120.0,
    "South America": 90.0,
    "Western Europe": 160.0,
    "Eastern Europe": 90.0,
    "Middle East": 130.0,
    "Africa": 100.0,
    "South Asia": 60.0,
    "Southeast Asia": 70.0,
    "East Asia": 140.0,
    "Central Asia": 70.0,
    "Oceania": 160.0,
    "Other": 100.0,
}


# ---------------------------------------------------------------------------
# Dataclasses (public API — signatures must not change)
# ---------------------------------------------------------------------------


@dataclass
class FlightOffer:
    """Cheapest flight offer for a specific route."""

    origin: str
    destination: str
    departure_date: date
    return_date: date
    price_total: float
    booking_url: str
    raw: str  # JSON blob for DB storage


@dataclass
class HotelOffer:
    """Per diem lodging estimate for a destination."""

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
    source: (
        str  # "per_diem_exact", "per_diem_country", "per_diem_regional", or "fallback"
    )


@dataclass
class AirportInfo:
    """Airport/city metadata from seed_airports.json."""

    iata: str
    city: str
    country: str
    country_code: str
    region: str
    latitude: float
    longitude: float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_seed_airports() -> list[dict]:
    global _seed_airports
    if _seed_airports is None:
        _seed_airports = json.loads(_SEED_AIRPORTS_PATH.read_text(encoding="utf-8"))
    return _seed_airports


def _load_per_diem() -> list[dict]:
    global _per_diem_rates
    if _per_diem_rates is None:
        _per_diem_rates = json.loads(_PER_DIEM_PATH.read_text(encoding="utf-8"))
    return _per_diem_rates


def _load_mock_flights() -> dict:
    global _mock_flights
    if _mock_flights is None:
        _mock_flights = json.loads(_MOCK_FLIGHTS_PATH.read_text(encoding="utf-8"))
    return _mock_flights


def _synthetic_flight_result(origin: str, destination: str) -> Any:
    """Return a SimpleNamespace mimicking a flight result for an unknown route pair.

    Generates a plausible price based on haversine distance so the
    rest of the pipeline always has data to work with in mock mode.
    Logs a debug message so callers know the fallback fired.
    """
    airports = _load_seed_airports()
    orig = next((a for a in airports if a["iata"] == origin), None)
    dest = next((a for a in airports if a["iata"] == destination), None)

    if orig and dest and orig.get("latitude") and dest.get("latitude"):
        dist = haversine_miles(
            orig["latitude"],
            orig["longitude"],
            dest["latitude"],
            dest["longitude"],
        )
    else:
        dist = 2000.0  # fallback if coordinates missing

    price = max(_SYNTHETIC_MIN_PRICE, round(dist * _SYNTHETIC_PRICE_PER_MILE, 0))
    logger.debug(
        "Mock flight: no fixture for %s→%s; synthesising $%.0f (%.0f mi)",
        origin,
        destination,
        price,
        dist,
    )
    flight = SimpleNamespace(
        name="Synthetic Air",
        price=f"${price:.0f}",
        stops=0,
        departure_time="08:00 AM",
        arrival_time="06:00 PM",
        duration="10h 00m",
        is_best=True,
    )
    return SimpleNamespace(flights=[flight])


def _mock_flight_result(origin: str, destination: str) -> Any:
    """Return a mock flight result from the fixture or a synthetic fallback."""
    data = _load_mock_flights()
    key = f"{origin}-{destination}"
    entry = data.get(key)
    if entry is None:
        return _synthetic_flight_result(origin, destination)

    flights = []
    for f in entry.get("flights", []):
        flights.append(
            SimpleNamespace(
                name=f.get("name", ""),
                price=f"${f['price']}"
                if isinstance(f["price"], (int, float))
                else f["price"],
                stops=f.get("stops", 0),
                departure_time=f.get("departure_time", ""),
                arrival_time=f.get("arrival_time", ""),
                duration=f.get("duration", ""),
                is_best=f.get("is_best", False),
            )
        )

    if not flights:
        return SimpleNamespace(flights=[])
    return SimpleNamespace(flights=flights)


def _parse_price(price_str: str) -> float | None:
    """Parse a price string like '$1,234' into a float."""
    try:
        return float(price_str.replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _airport(iata_code: str) -> Airport:
    """Return the fli Airport enum member for *iata_code*.

    Raises ValueError if the code is absent from the fli Airport enum (7,835 airports).
    Known absent codes from the 302-airport seed: REP, PNH, FRU.
    Callers should catch ValueError and skip the destination gracefully.
    """
    try:
        return Airport[iata_code]
    except KeyError as exc:
        raise ValueError(
            f"Airport {iata_code!r} is not supported by fli (not in Airport enum)"
        ) from exc


def get_flights(
    origin: str,
    destination: str,
    depart_date: date,
    return_date: date,
    adults: int,
    children: int,
) -> Any:
    """Query Google Flights via fli for a round-trip economy search.

    Returns a SimpleNamespace with a .flights attribute (list of SimpleNamespace
    objects with .stops, .price (string "$NNN"), and .name fields) so callers can
    use the same filtering logic regardless of data source.

    Price in each result is the TOTAL for all passengers combined (not per-person).
    Raises ValueError if either airport is absent from the fli Airport enum.
    """
    orig_airport = _airport(origin)
    dest_airport = _airport(destination)

    filters = FlightSearchFilters(
        passenger_info=PassengerInfo(adults=adults, children=children),
        flight_segments=[
            FlightSegment(
                departure_airport=[[orig_airport, 0]],
                arrival_airport=[[dest_airport, 0]],
                travel_date=depart_date.isoformat(),
            ),
            FlightSegment(
                departure_airport=[[dest_airport, 0]],
                arrival_airport=[[orig_airport, 0]],
                travel_date=return_date.isoformat(),
            ),
        ],
        seat_type=SeatType.ECONOMY,
        stops=MaxStops.ANY,
        sort_by=SortBy.CHEAPEST,
    )

    fli_results = SearchFlights().search(filters)
    if not fli_results:
        return SimpleNamespace(flights=[])

    flights = []
    for r in fli_results:
        airline_name = r.legs[0].airline.value if r.legs else "Unknown"
        flights.append(
            SimpleNamespace(
                name=airline_name,
                price=f"${r.price:.0f}",
                stops=r.stops,
                departure_time="",
                arrival_time="",
                duration=str(r.duration),
                is_best=False,
            )
        )
    return SimpleNamespace(flights=flights)


def _check_soft_limit(session: Session) -> bool:
    """Log a warning if today's Google Flights call count is approaching the soft limit."""
    today_calls = get_api_calls_today(session, "google_flights")
    if today_calls >= _GOOGLE_FLIGHTS_DAILY_SOFT_LIMIT:
        logger.warning(
            "Google Flights soft limit of %d calls/day reached (%d made today). "
            "Skipping further calls to avoid abuse.",
            _GOOGLE_FLIGHTS_DAILY_SOFT_LIMIT,
            today_calls,
        )
        return False
    return True


def _lookup_per_diem(
    city: str, country: str, is_domestic: bool
) -> tuple[float, float, str]:
    """Return (lodging_usd, mie_usd, source_label) using fuzzy fallback chain."""
    rates = _load_per_diem()

    city_upper = city.strip().upper()
    country_upper = country.strip().upper()

    # Exact city match
    for r in rates:
        if r.get("is_domestic") == is_domestic and r["city"].upper() == city_upper:
            return float(r["lodging_usd"]), float(r["mie_usd"]), "per_diem_exact"

    # Country-level average for international; national average for domestic.
    # Domestic per diem records store state abbreviations in state_or_country (e.g. "CA",
    # "DC"), not "United States", so we can't do a state-level average without a state code.
    # Fall back to the national domestic average instead.
    if is_domestic:
        matches = [r for r in rates if r.get("is_domestic")]
    else:
        matches = [
            r
            for r in rates
            if not r.get("is_domestic")
            and r["state_or_country"].upper() == country_upper
        ]
    if matches:
        avg_lodging = sum(r["lodging_usd"] for r in matches) / len(matches)
        avg_mie = sum(r["mie_usd"] for r in matches) / len(matches)
        return round(avg_lodging, 2), round(avg_mie, 2), "per_diem_country"

    return 0.0, 0.0, "fallback"


def get_flight_offers(
    origin: str,
    destination: str,
    depart_date: date,
    return_date: date,
    adults: int,
    children: int,
    session: Session,
    direct_only: bool = True,
    is_mock: bool = False,
) -> FlightOffer | None:
    """Return the cheapest qualifying flight for the exact route, or None if unavailable.

    When *direct_only* is True, only nonstop flights are considered; the function
    returns None if no direct option exists. When False, connecting flights are
    accepted as a fallback when no direct flight is available.

    Pass is_mock=True to use fixture data instead of calling Google Flights.
    """
    if not _check_soft_limit(session):
        return None

    try:
        if is_mock:
            ff_result = _mock_flight_result(origin, destination)
        else:
            # Count the attempt before calling — ensures api_usage tracks all live
            # attempts regardless of whether get_flights() throws or returns empty.
            record_api_call(session, "google_flights")
            try:
                ff_result = get_flights(
                    origin, destination, depart_date, return_date, adults, children
                )
            except ValueError as exc:
                # Airport not in fli enum — skip gracefully (REP, PNH, FRU not supported)
                logger.warning(
                    "Google Flights query %s->%s skipped: %s",
                    origin,
                    destination,
                    exc,
                )
                return None
            except Exception as exc:
                logger.warning(
                    "Google Flights query %s->%s failed: %s: %s",
                    origin,
                    destination,
                    type(exc).__name__,
                    exc,
                )
                return None
    except Exception as exc:
        logger.warning(
            "Unexpected error in get_flight_offers %s->%s: %s: %s",
            origin,
            destination,
            type(exc).__name__,
            exc,
        )
        return None

    if not ff_result or not ff_result.flights:
        return None

    direct = [f for f in ff_result.flights if f.stops == 0]
    candidates = direct if direct_only else (direct or ff_result.flights)
    prices = [(_parse_price(f.price), f) for f in candidates]
    # Reject price=0 explicitly: Google Flights occasionally returns "$0" for
    # routes it cannot price (not a free ticket). Accepting 0.0 caused OAK to
    # win on 2026-04-20 with is_mock=False — live data, $0 flight, $2890 total.
    valid = [(p, f) for p, f in prices if p is not None and p > 0]
    if not valid:
        return None

    price, best_flight = min(valid, key=lambda x: x[0])
    booking_url = build_flight_url(
        origin,
        destination,
        depart_date,
        return_date,
        adults=adults,
        children=children,
        direct_only=direct_only,
    )
    raw = json.dumps(
        {
            "name": best_flight.name,
            "price": best_flight.price,
            "stops": best_flight.stops,
        }
    )

    return FlightOffer(
        origin=origin,
        destination=destination,
        departure_date=depart_date,
        return_date=return_date,
        price_total=price,  # type: ignore[arg-type]
        booking_url=booking_url,
        raw=raw,
    )


def get_hotel_offers(
    city_code: str,
    checkin: date,
    checkout: date,
    adults: int,
    session: Session,
    num_rooms: int = 1,
    hotel_site: str = "google_hotels",
) -> HotelOffer | None:
    """Return a per diem lodging estimate for the destination. Always returns an estimate.

    min_stars is intentionally absent: hotel costs use GSA per diem rates, not live
    hotel search — star rating is meaningless in this context.
    """
    info = get_airport_info(city_code, session)
    city = info.city if info else city_code
    country = info.country if info else "Unknown"
    region = info.region if info else "Other"
    is_domestic = country == "United States"

    nights = (checkout - checkin).days
    rooms = max(1, num_rooms)

    lodging_per_night, _, source = _lookup_per_diem(city, country, is_domestic)

    if lodging_per_night == 0.0:
        lodging_per_night = _LODGING_FALLBACK.get(region, 100.0)
        source = "fallback"

    total = round(lodging_per_night * nights * rooms, 2)
    booking_url = build_hotel_url(
        city,
        country,
        checkin,
        checkout,
        adults,
        children=0,
        rooms=rooms,
        site=hotel_site,
    )

    note = (
        "Per diem lodging estimate (govt rate, typically 3-star; "
        "actual 4-star costs may be higher). "
        f"Source: {source}."
    )

    return HotelOffer(
        hotel_id=f"per_diem_{city_code}",
        hotel_name=f"{city} (per diem estimate)",
        city_code=city_code,
        check_in=checkin,
        check_out=checkout,
        price_total=total,
        booking_url=booking_url,
        raw=json.dumps(
            {
                "source": source,
                "lodging_per_night": lodging_per_night,
                "nights": nights,
                "rooms": rooms,
                "note": note,
            }
        ),
    )


def get_airport_info(iata: str, session: Session) -> AirportInfo | None:
    """Return airport metadata from the DB (seeded from seed_airports.json).

    Falls back to the in-memory JSON list for airports not yet in the DB.
    """
    from trip_a_day.db import Destination  # avoid circular import at module level

    dest = session.get(Destination, iata)
    if dest is not None:
        return AirportInfo(
            iata=iata,
            city=dest.city or iata,
            country=dest.country or "Unknown",
            country_code=dest.country_code or "",
            region=dest.region or "Other",
            latitude=dest.latitude or 0.0,
            longitude=dest.longitude or 0.0,
        )

    # Fallback: check in-memory JSON (e.g. before first init_db seed)
    airports = _load_seed_airports()
    airport = next((a for a in airports if a["iata"] == iata), None)
    if airport is None:
        return None
    return AirportInfo(
        iata=iata,
        city=airport["city"],
        country=airport["country"],
        country_code=airport.get("country_code", ""),
        region=airport.get("region", "Other"),
        latitude=airport.get("latitude", 0.0),
        longitude=airport.get("longitude", 0.0),
    )


def get_food_cost(
    city: str,
    country: str,
    region: str,
    days: int,
    people: int,
    session: Session,
) -> FoodEstimate:
    """Estimate food cost via per diem M&IE rates with regional fallback."""
    is_domestic = country == "United States"
    _, mie_per_day, source = _lookup_per_diem(city, country, is_domestic)

    if mie_per_day == 0.0:
        mie_per_day = _MIE_FALLBACK.get(region, 50.0)
        source = "fallback"

    # Dataset bounds (2026 per_diem_rates.json): min $1 (Antarctica), max $287
    # (Maracaibo, Venezuela). Warn outside that range +-20% to catch corruption
    # without false-positives on legitimate extremes like Calgary ($169).
    mie_floor = 0.8  # 1 * 0.80
    mie_ceiling = 344.4  # 287 * 1.20
    if not (mie_floor <= mie_per_day <= mie_ceiling):
        logger.warning(
            "Unusual food cost estimate for %s: $%.0f/person/day -- verify per diem data.",
            city,
            mie_per_day,
        )

    total = round(mie_per_day * people * days, 2)
    return FoodEstimate(
        city=city,
        country=country,
        cost_per_person_per_day=mie_per_day,
        total_cost=total,
        source=source,
    )


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in miles between two lat/lon points."""
    r = 3958.8  # Earth radius in miles
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return round(2 * r * math.asin(math.sqrt(a)), 1)


def get_airport_city(iata: str) -> str:
    """Return the city name for *iata* from the seed JSON, or the IATA code if not found."""
    airports = _load_seed_airports()
    airport = next((a for a in airports if a["iata"] == iata), None)
    return airport["city"] if airport else iata


def get_nearby_airports(
    home_iata: str, radius_miles: float, session: Session
) -> list[AirportInfo]:
    """Return airports within *radius_miles* of *home_iata*, excluding home itself.

    Performs a haversine scan over all enabled Destination rows in the DB.
    Returns an empty list when *radius_miles* <= 0 or home coordinates are missing.
    """
    from trip_a_day.db import Destination  # avoid circular import at module level

    if radius_miles <= 0:
        return []

    home = get_airport_info(home_iata, session)
    if home is None or not home.latitude or not home.longitude:
        return []

    destinations = (
        session.query(Destination).filter(Destination.enabled.is_(True)).all()
    )
    nearby: list[AirportInfo] = []
    for dest in destinations:
        if dest.iata_code == home_iata:
            continue
        if not dest.latitude or not dest.longitude:
            continue
        dist = haversine_miles(
            home.latitude, home.longitude, dest.latitude, dest.longitude
        )
        if dist <= radius_miles:
            nearby.append(
                AirportInfo(
                    iata=dest.iata_code,
                    city=dest.city or dest.iata_code,
                    country=dest.country or "Unknown",
                    country_code=dest.country_code or "",
                    region=dest.region or "Other",
                    latitude=dest.latitude,
                    longitude=dest.longitude,
                )
            )
    return nearby
