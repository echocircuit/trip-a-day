"""Entry point for the trip-a-day daily run.

Usage:
    python main.py

Reads preferences from the local SQLite DB, selects a destination batch via
the configured strategy, then runs a three-pass flight search:

  Pass 1 — Window search: for each destination, find_cheapest_in_window probes
            3 departure dates spread across [advance_window_min_days,
            advance_window_max_days] and returns the cheapest valid cost.
  Pass 2 — Flex length: for the top N candidates from Pass 1, try ±flex
            night variants at the best departure date, keep cheapest per dest.
  Final  — Rank all Pass 2 results globally and pick the winner.

Results are stored in a local SQLite database and the daily notification is
sent (or printed to stdout if no RESEND_API_KEY is configured).
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# Load .env before any other imports that might read env vars
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from trip_a_day.costs import build_cost_breakdown, is_valid_cost_breakdown
from trip_a_day.db import (
    Destination,
    PriceCache,
    RunLog,
    SessionFactory,
    TravelWindow,
    Trip,
    get_api_calls_today,
    init_db,
    seed_preferences,
)
from trip_a_day.fetcher import (
    get_airport_info,
    get_flight_data_mode,
    get_flight_offers,
    get_food_cost,
    get_hotel_offers,
    get_nearby_airports,
    haversine_miles,
)
from trip_a_day.filters import apply_destination_filters
from trip_a_day.links import build_car_url, build_flight_url
from trip_a_day.notifier import send_no_results_notification, send_trip_notification
from trip_a_day.preferences import get, get_all, get_bool, get_int, get_or
from trip_a_day.ranker import TripCandidate, rank_trips
from trip_a_day.selector import select_daily_batch
from trip_a_day.window_search import find_cheapest_in_window

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
            departure_iata=candidate.departure_airport or None,
            stale_cache=candidate.stale_cache,
        )
        session.add(db_trip)
        session.flush()
        trip_ids.append(db_trip.id)
    return trip_ids


def _connectivity_ok(session, is_mock: bool) -> bool:
    """Make one test call to Google Flights (HSV→ATL) to verify live API access.

    Skipped entirely in mock mode. Logs a WARNING on failure but never aborts
    the run — cached prices may still be usable even when live calls are broken.
    """
    if is_mock:
        return True
    test_date = date.today() + timedelta(days=7)
    result = get_flight_offers(
        origin="HSV",
        destination="ATL",
        depart_date=test_date,
        return_date=test_date + timedelta(days=7),
        adults=1,
        children=0,
        session=session,
        direct_only=False,
        is_mock=False,
    )
    if result is None:
        logger.warning(
            "Connectivity pre-check: test call HSV→ATL returned no result"
            " — live Google Flights API may be degraded or blocked."
        )
        return False
    logger.info(
        "Connectivity pre-check: OK (HSV→ATL ≈ $%.0f on %s).",
        result.price_total,
        test_date,
    )
    return True


def _stale_cache_fallback(
    session,
    batch: list,
    dep_iata: str,
    transport_usd: float,
    home_lat: float,
    home_lon: float,
    num_adults: int,
    num_children: int,
    num_rooms: int,
    car_rental_required: bool,
    trip_nights: int,
    preferred_car_site: str,
    preferred_hotel_site: str = "google_hotels",
) -> list[TripCandidate]:
    """Build TripCandidates from stale (possibly TTL-expired) cached prices.

    Used as a last resort when all live API calls fail. Returns an empty list
    if no usable cached prices exist for any destination in the batch.
    """
    today = date.today()
    candidates: list[TripCandidate] = []

    for dest in batch:
        iata = dest.iata_code
        cached = (
            session.query(PriceCache)
            .filter(
                PriceCache.origin_iata == dep_iata,
                PriceCache.destination_iata == iata,
                PriceCache.departure_date >= today,
            )
            .order_by(PriceCache.queried_at.desc())
            .first()
        )
        if cached is None or cached.price_usd <= 0:
            continue

        nights = (cached.return_date - cached.departure_date).days
        if nights <= 0:
            continue

        airport = get_airport_info(iata, session)
        if airport:
            city = airport.city.title()
            country = airport.country.title()
            region = airport.region
            lat, lon = airport.latitude or 0.0, airport.longitude or 0.0
        else:
            city, country, region = iata, "Unknown", "Other"
            lat, lon = 0.0, 0.0

        hotel = get_hotel_offers(
            city_code=iata,
            checkin=cached.departure_date,
            checkout=cached.return_date,
            adults=num_adults,
            session=session,
            num_rooms=num_rooms,
            hotel_site=preferred_hotel_site,
        )
        if hotel is None:
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
            flight_total=cached.price_usd,
            hotel_total=hotel.price_total,
            car_region=region,
            food_total=food.total_cost,
            days=nights,
            car_required=car_rental_required,
            transport_usd=transport_usd,
        )
        valid, _ = is_valid_cost_breakdown(cost)
        if not valid:
            continue

        distance = (
            haversine_miles(home_lat, home_lon, lat, lon)
            if lat != 0.0 or lon != 0.0
            else 0.0
        )
        flight_url = build_flight_url(
            dep_iata,
            iata,
            cached.departure_date,
            cached.return_date,
            adults=num_adults,
            children=num_children,
        )
        car_url = build_car_url(
            iata,
            city,
            cached.departure_date,
            cached.return_date,
            preferred_car_site,
        )
        candidates.append(
            TripCandidate(
                destination_iata=iata,
                city=city,
                country=country,
                region=region,
                departure_date=cached.departure_date,
                return_date=cached.return_date,
                cost=cost,
                distance_miles=distance,
                flight_booking_url=flight_url,
                hotel_booking_url=hotel.booking_url,
                car_booking_url=car_url,
                raw_flight_data=json.dumps(
                    {
                        "source": "stale_cache",
                        "price_usd": cached.price_usd,
                        "cached_at": str(cached.queried_at),
                    }
                ),
                raw_hotel_data=hotel.raw,
                departure_airport=dep_iata,
                stale_cache=True,
            )
        )

    if candidates:
        logger.warning(
            "Stale cache fallback: using %d cached price(s) from price_cache"
            " (TTL may be expired — prices may be outdated).",
            len(candidates),
        )
    return candidates


_logger_tw = logging.getLogger("travel_windows")


def _window_pass1_for_departure(
    *,
    session,
    dep_iata: str,
    batch: list,
    active_windows: list,
    trip_nights: int,
    num_adults: int,
    num_children: int,
    num_rooms: int,
    car_rental_required: bool,
    direct_flights_only: bool,
    cache_ttl_enabled: bool,
    is_mock: bool,
    max_live_calls: int,
    live_calls_made_so_far: int,
    transport_usd: float,
) -> tuple[list, int, int, dict[str, str]]:
    """Run window-based Pass 1 for a single departure airport across all active windows.

    For each (window, destination) pair:
      - Converts window effective dates to min_days/max_days from today
      - Calls find_cheapest_in_window
      - Verifies the return date fits within effective_end
      - Keeps the best result per destination (lowest total cost across all windows)

    Returns:
        (pass1_results, live_calls_used, cache_hits_used, iata_to_window_name)
        pass1_results: list of (Destination, cost_total, best_departure_date)
        iata_to_window_name: maps destination IATA → name of the window that produced the result
    """
    today = date.today()
    # Best result per destination across all windows: iata -> (cost, best_date, window_name)
    best_per_dest: dict[str, tuple[float, date, str]] = {}
    live_calls_used = 0
    cache_hits_used = 0

    for tw in active_windows:
        eff_start = tw.effective_start
        eff_end = tw.effective_end
        min_days_tw = max(0, (eff_start - today).days)
        # Latest sensible departure: must leave enough nights before window closes
        max_days_tw = (eff_end - timedelta(days=trip_nights) - today).days

        if max_days_tw < min_days_tw:
            _logger_tw.info(
                '"%s" effective range too short for %d-night trip — skipping departure '
                "from %s.",
                tw.name,
                trip_nights,
                dep_iata,
            )
            continue

        for dest in batch:
            iata = dest.iata_code
            if _is_excluded(session, iata):
                continue

            live_budget = max_live_calls - live_calls_made_so_far - live_calls_used
            if live_budget <= 0 and not is_mock:
                continue

            try:
                cost, best_date, calls_used, hits_used = find_cheapest_in_window(
                    origin_iata=dep_iata,
                    destination=dest,
                    min_days=min_days_tw,
                    max_days=max_days_tw,
                    trip_length_nights=trip_nights,
                    adults=num_adults,
                    children=num_children,
                    num_rooms=num_rooms,
                    car_rental_required=car_rental_required,
                    direct_flights_only=direct_flights_only,
                    cache_ttl_enabled=cache_ttl_enabled,
                    is_mock=is_mock,
                    db_session=session,
                    live_calls_remaining=live_budget,
                    transport_usd=transport_usd,
                )
            except Exception as exc:
                logger.warning(
                    "  [P1/win] %s→%s (%s) — exception: %s: %s",
                    dep_iata,
                    iata,
                    tw.name,
                    type(exc).__name__,
                    exc,
                )
                continue

            live_calls_used += calls_used
            cache_hits_used += hits_used

            if cost is None or best_date is None:
                continue

            # Verify return date fits within this window's effective_end
            return_date_check = best_date + timedelta(days=trip_nights)
            if return_date_check > eff_end:
                logger.debug(
                    "  [P1/win] %s→%s (%s): return %s > window end %s — excluded",
                    dep_iata,
                    iata,
                    tw.name,
                    return_date_check,
                    eff_end,
                )
                continue

            # Keep the cheapest result across all windows for this destination
            existing = best_per_dest.get(iata)
            if existing is None or cost.total < existing[0]:
                best_per_dest[iata] = (cost.total, best_date, tw.name)

    # Convert to (Destination, cost_total, best_date) format expected by Pass 2
    pass1_results: list[tuple] = []
    iata_to_window: dict[str, str] = {}
    for dest in batch:
        iata = dest.iata_code
        if iata in best_per_dest:
            total, best_date, window_name = best_per_dest[iata]
            pass1_results.append((dest, total, best_date))
            iata_to_window[iata] = window_name

    return pass1_results, live_calls_used, cache_hits_used, iata_to_window


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
        advance_window_min = get_int(session, "advance_window_min_days")
        advance_window_max = get_int(session, "advance_window_max_days")
        num_adults = get_int(session, "num_adults")
        num_children = get_int(session, "num_children")
        num_rooms = get_int(session, "num_rooms")
        preferred_hotel_site = get_or(session, "preferred_hotel_site", "google_hotels")
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

        night_variants = _build_night_variants(trip_nights, trip_flex)
        is_mock = get_flight_data_mode(session) == "mock"

        logger.info(
            "Searching from %s | window %d-%d days out | nights %s"
            " | %d adults %d children | mode=%s",
            home_airport,
            advance_window_min,
            advance_window_max,
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

        # ── Connectivity pre-check (live mode only) ──────────────────────────
        _connectivity_ok(session, is_mock)

        # ── Travel window detection and auto-expiry ───────────────────────────
        _all_tw: list[TravelWindow] = (
            session.query(TravelWindow).filter(TravelWindow.enabled.is_(True)).all()
        )
        active_windows: list[TravelWindow] = []
        for _tw in _all_tw:
            if _tw.effective_end < run_date:
                _tw.enabled = False
                _logger_tw.info('"%s" has passed — automatically disabled.', _tw.name)
            else:
                active_windows.append(_tw)
        if len(active_windows) < len(_all_tw):
            session.flush()
        if active_windows:
            _logger_tw.info(
                "Active travel windows: %s",
                ", ".join(f'"{w.name}"' for w in active_windows),
            )

        use_window_mode = bool(active_windows)
        window_fallback_used = False
        _iata_to_window: dict[str, str] = {}  # dest IATA → window name

        # ── Main search (two passes max: window mode then normal fallback) ────
        flights_calls_start = get_api_calls_today(session, "google_flights")
        live_calls_made = 0
        cache_hits = 0
        now_utc = datetime.now(UTC)
        all_candidates: list[TripCandidate] = []
        any_pass1_prices = False
        invalid_exclusions: list[dict[str, str]] = []
        pass1_stats: dict[str, int] = {
            "valid": 0,
            "no_price": 0,
            "budget_exhausted": 0,
            "cache_hits": 0,
            "live_calls": 0,
        }

        for _search_pass in range(2):
            if _search_pass == 1:
                # Second pass only fires when window mode found nothing.
                if not use_window_mode or any_pass1_prices:
                    break
                logger.warning(
                    "No trips found within active travel windows — "
                    "falling back to normal advance window search."
                )
                window_fallback_used = True
                use_window_mode = False
                _iata_to_window = {}
                all_candidates = []
                any_pass1_prices = False
                invalid_exclusions = []
                pass1_stats = {
                    "valid": 0,
                    "no_price": 0,
                    "budget_exhausted": 0,
                    "cache_hits": 0,
                    "live_calls": 0,
                }

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
                    "--- Pass 1 from %s (transport cost: $%.2f) ---",
                    dep_iata,
                    transport_usd,
                )

                # ── Pass 1 ──────────────────────────────────────────────────────
                if use_window_mode:
                    # Window-based: probe each active window, keep cheapest per dest.
                    pass1_results, _tw_calls, _tw_hits, _tw_iata_map = (
                        _window_pass1_for_departure(
                            session=session,
                            dep_iata=dep_iata,
                            batch=batch,
                            active_windows=active_windows,
                            trip_nights=trip_nights,
                            num_adults=num_adults,
                            num_children=num_children,
                            num_rooms=num_rooms,
                            car_rental_required=car_rental_required,
                            direct_flights_only=direct_flights_only,
                            cache_ttl_enabled=cache_ttl_enabled,
                            is_mock=is_mock,
                            max_live_calls=max_live_calls,
                            live_calls_made_so_far=live_calls_made,
                            transport_usd=transport_usd,
                        )
                    )
                    live_calls_made += _tw_calls
                    cache_hits += _tw_hits
                    pass1_stats["cache_hits"] += _tw_hits
                    pass1_stats["live_calls"] += _tw_calls
                    if pass1_results:
                        pass1_stats["valid"] += len(pass1_results)
                        _iata_to_window.update(_tw_iata_map)
                        for _d, _c, _dt in pass1_results:
                            logger.info(
                                "  [P1/win] %s→%s — $%.0f (depart %s, window: %s)",
                                dep_iata,
                                _d.iata_code,
                                _c,
                                _dt,
                                _tw_iata_map.get(_d.iata_code, "?"),
                            )
                    else:
                        pass1_stats["no_price"] += len(batch)

                    # Update destination stats (home airport only).
                    if dep_iata == home_airport:
                        for _d, _c, _dt in pass1_results:
                            _d.last_queried_at = now_utc
                            _d.last_known_price_usd = _c
                            _d.last_known_price_date = run_date
                            _d.query_count = (_d.query_count or 0) + 1

                else:
                    # Normal Pass 1: probe departure dates across the advance window.
                    pass1_results = []

                    for dest in batch:
                        iata = dest.iata_code

                        if _is_excluded(session, iata):
                            continue

                        live_budget = max_live_calls - live_calls_made
                        if live_budget <= 0 and not is_mock:
                            pass1_stats["budget_exhausted"] += 1
                            logger.debug(
                                "  [P1] %s→%s — live call budget exhausted, skipping",
                                dep_iata,
                                iata,
                            )
                            continue

                        try:
                            cost, best_date, calls_used, hits_used = (
                                find_cheapest_in_window(
                                    origin_iata=dep_iata,
                                    destination=dest,
                                    min_days=advance_window_min,
                                    max_days=advance_window_max,
                                    trip_length_nights=trip_nights,
                                    adults=num_adults,
                                    children=num_children,
                                    num_rooms=num_rooms,
                                    car_rental_required=car_rental_required,
                                    direct_flights_only=direct_flights_only,
                                    cache_ttl_enabled=cache_ttl_enabled,
                                    is_mock=is_mock,
                                    db_session=session,
                                    live_calls_remaining=live_budget,
                                    transport_usd=transport_usd,
                                )
                            )
                        except Exception as exc:
                            logger.warning(
                                "  [P1] %s→%s — unhandled exception in window search:"
                                " %s: %s",
                                dep_iata,
                                iata,
                                type(exc).__name__,
                                exc,
                            )
                            pass1_stats["no_price"] += 1
                            continue
                        live_calls_made += calls_used
                        cache_hits += hits_used
                        pass1_stats["cache_hits"] += hits_used
                        pass1_stats["live_calls"] += calls_used

                        if cost is None or best_date is None:
                            pass1_stats["no_price"] += 1
                            logger.info(
                                "  [P1] %s→%s — no valid price found", dep_iata, iata
                            )
                            continue

                        pass1_stats["valid"] += 1
                        pass1_results.append((dest, cost.total, best_date))
                        logger.info(
                            "  [P1] %s→%s — $%.0f (depart %s)",
                            dep_iata,
                            iata,
                            cost.total,
                            best_date,
                        )

                        # Only track destination stats against the home airport.
                        if dep_iata == home_airport:
                            dest.last_queried_at = now_utc
                            dest.last_known_price_usd = cost.total
                            dest.last_known_price_date = run_date
                            dest.query_count = (dest.query_count or 0) + 1

                session.commit()

                if not pass1_results:
                    logger.warning(
                        "Pass 1 from %s returned no prices — skipping this departure "
                        "airport.",
                        dep_iata,
                    )
                    continue

                any_pass1_prices = True

                # Sort Pass 1 results by total cost, take top N
                pass1_results.sort(key=lambda t: t[1])
                top_pass1 = pass1_results[:two_pass_count]
                logger.info(
                    "Pass 1 from %s — top %d: %s",
                    dep_iata,
                    len(top_pass1),
                    ", ".join(
                        f"{d.iata_code}(${c:.0f}, {dt})" for d, c, dt in top_pass1
                    ),
                )

                # ── Pass 2: flex-length at the best departure date ────────────
                logger.info("--- Pass 2 (flex-length) from %s ---", dep_iata)

                for dest, _, best_depart_date in top_pass1:
                    iata = dest.iata_code
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

                    best_candidate: TripCandidate | None = None
                    for nights in night_variants:
                        return_date_v = best_depart_date + timedelta(days=nights)

                        flight = get_flight_offers(
                            origin=dep_iata,
                            destination=iata,
                            depart_date=best_depart_date,
                            return_date=return_date_v,
                            adults=num_adults,
                            children=num_children,
                            session=session,
                            direct_only=direct_flights_only,
                            is_mock=is_mock,
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
                            checkin=best_depart_date,
                            checkout=return_date_v,
                            adults=num_adults,
                            session=session,
                            num_rooms=num_rooms,
                            hotel_site=preferred_hotel_site,
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
                                "Excluding %s (%s): %s — skipping this variant",
                                city,
                                iata,
                                reason,
                            )
                            invalid_exclusions.append(
                                {"iata": iata, "city": city, "reason": reason}
                            )
                            continue

                        if (
                            best_candidate is None
                            or cost.total < best_candidate.cost.total
                        ):
                            car_url = build_car_url(
                                iata,
                                city,
                                best_depart_date,
                                return_date_v,
                                preferred_car_site,
                            )
                            booking_url = build_flight_url(
                                dep_iata,
                                iata,
                                best_depart_date,
                                return_date_v,
                                adults=num_adults,
                                children=num_children,
                            )
                            best_candidate = TripCandidate(
                                destination_iata=iata,
                                city=city,
                                country=country,
                                region=region,
                                departure_date=best_depart_date,
                                return_date=return_date_v,
                                cost=cost,
                                distance_miles=distance,
                                flight_booking_url=booking_url,
                                hotel_booking_url=hotel.booking_url,
                                car_booking_url=car_url,
                                raw_flight_data=flight.raw,
                                raw_hotel_data=hotel.raw,
                                departure_airport=dep_iata,
                            )

                    if best_candidate is None:
                        logger.info(
                            "  No complete trip found for %s→%s — skipping.",
                            dep_iata,
                            iata,
                        )
                        session.commit()
                        continue

                    all_candidates.append(best_candidate)
                    nights_won = (
                        best_candidate.return_date - best_candidate.departure_date
                    ).days
                    logger.info(
                        "  Best %s→%s: %d nights (depart %s) — $%.2f"
                        " (flight $%.2f | hotel $%.2f | car $%.2f"
                        " | food $%.2f | transport $%.2f)",
                        dep_iata,
                        iata,
                        nights_won,
                        best_candidate.departure_date,
                        best_candidate.cost.total,
                        best_candidate.cost.flights,
                        best_candidate.cost.hotel,
                        best_candidate.cost.car,
                        best_candidate.cost.food,
                        best_candidate.cost.transport_usd,
                    )
                    session.commit()
            # end: for dep_iata in departure_iatas
        # end: for _search_pass in range(2)

        flights_calls_this_run = (
            get_api_calls_today(session, "google_flights") - flights_calls_start
        )
        duration = round(time.monotonic() - start_time, 1)

        if not any_pass1_prices:
            logger.error(
                "Pass 1 complete: 0 valid prices from %d destinations.\n"
                "  Cache hits: %d\n"
                "  Live calls attempted: %d\n"
                "  Returned None (no flights/no valid price): %d\n"
                "  Budget exhausted before call: %d\n"
                "Check Google Flights connectivity and the logs above for WARNING-level"
                " exception details.",
                len(batch),
                pass1_stats["cache_hits"],
                pass1_stats["live_calls"],
                pass1_stats["no_price"],
                pass1_stats["budget_exhausted"],
            )

            # Try stale cache as a last resort before giving up.
            stale_candidates = _stale_cache_fallback(
                session=session,
                batch=batch,
                dep_iata=home_airport,
                transport_usd=0.0,
                home_lat=home_lat,
                home_lon=home_lon,
                num_adults=num_adults,
                num_children=num_children,
                num_rooms=num_rooms,
                car_rental_required=car_rental_required,
                trip_nights=trip_nights,
                preferred_car_site=preferred_car_site,
                preferred_hotel_site=preferred_hotel_site,
            )
            if stale_candidates:
                pass1_stats["stale_cache_used"] = 1
                all_candidates = stale_candidates
            else:
                # No stale cache either — send alert and exit cleanly.
                notifications_enabled_early = (
                    all_prefs.get("notifications_enabled", "true") == "true"
                )
                if notifications_enabled_early:
                    send_no_results_notification(all_prefs, run_date, pass1_stats)
                session.add(
                    RunLog(
                        run_at=datetime.now(UTC),
                        status="failed",
                        triggered_by=triggered_by,
                        destinations_evaluated=len(batch),
                        error_message="Pass 1 returned no prices",
                        duration_seconds=duration,
                        api_calls_flights=flights_calls_this_run,
                        cache_hits_flights=cache_hits,
                        destinations_excluded=len(invalid_exclusions),
                        pass1_diagnostics=json.dumps(pass1_stats),
                    )
                )
                session.commit()
                sys.exit(0)

        if not all_candidates:
            logger.error("No valid trip candidates found. Logging failed run.")
            session.add(
                RunLog(
                    run_at=datetime.now(UTC),
                    status="failed",
                    triggered_by=triggered_by,
                    destinations_evaluated=len(batch),
                    error_message="No valid candidates after Pass 2",
                    duration_seconds=duration,
                    api_calls_flights=flights_calls_this_run,
                    cache_hits_flights=cache_hits,
                    destinations_excluded=len(invalid_exclusions),
                )
            )
            session.commit()
            sys.exit(1)

        # ── Rank and store ────────────────────────────────────────────────────
        ranked = rank_trips(all_candidates, strategy=ranking_strategy)
        winner = ranked[0]

        # Determine which travel window produced the winner (None in normal mode).
        winning_window_name: str | None = (
            _iata_to_window.get(winner.destination_iata)
            if not window_fallback_used
            else None
        )
        if winning_window_name:
            _logger_tw.info('Winner came from travel window: "%s"', winning_window_name)

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
        run_summary = (
            f"Run complete: {len(batch)} destinations evaluated, "
            f"{flights_calls_this_run} live API calls, "
            f"{cache_hits} cache hits, "
            f"{len(invalid_exclusions)} excluded (invalid data)"
        )
        logger.info(run_summary)

        stale_cache_in_use = pass1_stats.get("stale_cache_used", 0) == 1
        if stale_cache_in_use:
            logger.warning(
                "Run succeeded using STALE cached prices — results may be outdated."
            )

        session.add(
            RunLog(
                run_at=datetime.now(UTC),
                status="success",
                triggered_by=triggered_by,
                destinations_evaluated=len(batch),
                winner_trip_id=winner_trip_id,
                duration_seconds=duration,
                api_calls_flights=flights_calls_this_run,
                cache_hits_flights=cache_hits,
                destinations_excluded=len(invalid_exclusions),
                filter_fallback=filter_fallback,
                invalid_data_exclusions=exclusions_json,
                pass1_diagnostics=json.dumps(pass1_stats),
                travel_window_name=winning_window_name,
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
                db_session=session,
                travel_window_name=winning_window_name,
                window_fallback_used=window_fallback_used,
            )
            if notified:
                winner_row = session.get(Trip, winner_trip_id)
                if winner_row:
                    winner_row.notified = True
                session.commit()

    logger.info("Finished in %.1fs.", duration)


if __name__ == "__main__":
    run()
