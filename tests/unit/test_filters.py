"""Unit tests for the Phase 6 composable filter chain (filters.py)."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trip_a_day.db import Base, Destination, Trip
from trip_a_day.filters import apply_destination_filters


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'filter_test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as s:
        yield s


def _dest(
    iata: str,
    region: str = "North America",
    lat: float = 30.0,
    lon: float = -90.0,
    user_booked: bool = False,
) -> Destination:
    return Destination(
        iata_code=iata,
        city=iata,
        country="Test",
        region=region,
        latitude=lat,
        longitude=lon,
        enabled=True,
        excluded=False,
        user_booked=user_booked,
    )


def _prefs(**kwargs) -> dict[str, str]:
    defaults = {
        "region_allowlist": "[]",
        "region_blocklist": "[]",
        "favorite_radius_miles": "0",
        "exclude_previously_selected": "false",
        "exclude_previously_selected_days": "0",
        "exclude_booked": "false",
    }
    defaults.update({k: str(v) for k, v in kwargs.items()})
    return defaults


# ── No filters active ────────────────────────────────────────────────────────


def test_no_filters_returns_pool_unchanged(session):
    pool = [_dest("AAA"), _dest("BBB")]
    result, fallback = apply_destination_filters(pool, session, _prefs())
    assert result == pool
    assert fallback is False


# ── Region allowlist ─────────────────────────────────────────────────────────


def test_allowlist_keeps_matching_regions(session):
    pool = [_dest("NA1", "North America"), _dest("EU1", "Western Europe")]
    result, fallback = apply_destination_filters(
        pool, session, _prefs(region_allowlist=json.dumps(["North America"]))
    )
    assert len(result) == 1
    assert result[0].iata_code == "NA1"
    assert fallback is False


def test_allowlist_empty_means_worldwide(session):
    pool = [_dest("NA1", "North America"), _dest("EU1", "Western Europe")]
    result, _ = apply_destination_filters(pool, session, _prefs(region_allowlist="[]"))
    assert len(result) == 2


# ── Region blocklist ─────────────────────────────────────────────────────────


def test_blocklist_removes_matching_regions(session):
    pool = [_dest("NA1", "North America"), _dest("EU1", "Western Europe")]
    result, _ = apply_destination_filters(
        pool, session, _prefs(region_blocklist=json.dumps(["Western Europe"]))
    )
    assert len(result) == 1
    assert result[0].iata_code == "NA1"


def test_blocklist_takes_precedence_over_allowlist(session):
    pool = [_dest("EU1", "Western Europe")]
    result, fallback = apply_destination_filters(
        pool,
        session,
        _prefs(
            region_allowlist=json.dumps(["Western Europe"]),
            region_blocklist=json.dumps(["Western Europe"]),
        ),
    )
    # Allowlist passes EU1, then blocklist removes it → empty → fallback
    assert fallback is True
    assert result == pool  # returns unfiltered on fallback


# ── Favorite radius ───────────────────────────────────────────────────────────


def test_favorite_radius_zero_passes_all(session):
    # Radius 0 → filter disabled regardless of favorited destinations
    paris = _dest("PAR", lat=48.8566, lon=2.3522)
    paris.user_favorited = True
    session.add(paris)
    pool = [_dest("AAA", lat=40.0, lon=-74.0)]
    result, _ = apply_destination_filters(
        pool,
        session,
        _prefs(favorite_radius_miles="0"),
    )
    assert result == pool


def test_favorite_radius_keeps_nearby(session):
    # Anchor: Paris (user_favorited=True); CDG ~14 mi, JFK far
    paris = _dest("PAR", lat=48.8566, lon=2.3522)
    paris.user_favorited = True
    session.add(paris)
    session.flush()

    pool = [
        _dest("CDG", lat=49.0097, lon=2.5479),  # Charles de Gaulle — ~14 mi from Paris
        _dest("JFK", lat=40.6413, lon=-73.7781),  # New York — far
    ]
    result, _ = apply_destination_filters(
        pool,
        session,
        _prefs(favorite_radius_miles="50"),
    )
    iatas = {d.iata_code for d in result}
    assert "CDG" in iatas
    assert "JFK" not in iatas


def test_favorite_radius_no_locations_passes_all(session):
    # No favorited destinations → filter is a no-op even with radius set
    pool = [_dest("AAA"), _dest("BBB")]
    result, _ = apply_destination_filters(
        pool,
        session,
        _prefs(favorite_radius_miles="500"),
    )
    assert result == pool


# ── Exclude previously selected ──────────────────────────────────────────────


def _add_selected_trip(session, iata: str, run_date: date) -> None:
    session.add(
        Trip(
            run_date=run_date,
            destination_iata=iata,
            departure_date=run_date + timedelta(days=7),
            return_date=run_date + timedelta(days=14),
            flight_cost_usd=400.0,
            hotel_cost_usd=700.0,
            car_cost_usd=300.0,
            food_cost_usd=500.0,
            total_cost_usd=1900.0,
            selected=True,
        )
    )
    session.flush()


def test_exclude_previously_selected_all_time(session):
    _add_selected_trip(session, "JFK", date.today() - timedelta(days=60))
    pool = [_dest("JFK"), _dest("LAX")]
    result, fallback = apply_destination_filters(
        pool, session, _prefs(exclude_previously_selected="true")
    )
    iatas = {d.iata_code for d in result}
    assert "JFK" not in iatas
    assert "LAX" in iatas
    assert fallback is False


def test_exclude_previously_selected_rolling_window_recent(session):
    _add_selected_trip(session, "JFK", date.today() - timedelta(days=5))
    pool = [_dest("JFK"), _dest("LAX")]
    # 30-day window: JFK was picked 5 days ago → excluded
    result, _ = apply_destination_filters(
        pool,
        session,
        _prefs(
            exclude_previously_selected="true", exclude_previously_selected_days="30"
        ),
    )
    assert all(d.iata_code != "JFK" for d in result)


def test_exclude_previously_selected_rolling_window_old(session):
    _add_selected_trip(session, "JFK", date.today() - timedelta(days=60))
    pool = [_dest("JFK"), _dest("LAX")]
    # 30-day window: JFK was picked 60 days ago → NOT excluded
    result, _ = apply_destination_filters(
        pool,
        session,
        _prefs(
            exclude_previously_selected="true", exclude_previously_selected_days="30"
        ),
    )
    assert any(d.iata_code == "JFK" for d in result)


def test_exclude_previously_selected_false_skips_filter(session):
    _add_selected_trip(session, "JFK", date.today())
    pool = [_dest("JFK")]
    result, _ = apply_destination_filters(
        pool, session, _prefs(exclude_previously_selected="false")
    )
    assert result == pool


# ── Exclude booked ────────────────────────────────────────────────────────────


def test_exclude_booked_removes_booked_destinations(session):
    pool = [_dest("JFK", user_booked=True), _dest("LAX", user_booked=False)]
    result, fallback = apply_destination_filters(
        pool, session, _prefs(exclude_booked="true")
    )
    assert len(result) == 1
    assert result[0].iata_code == "LAX"
    assert fallback is False


def test_exclude_booked_false_keeps_booked(session):
    pool = [_dest("JFK", user_booked=True)]
    result, _ = apply_destination_filters(pool, session, _prefs(exclude_booked="false"))
    assert result == pool


# ── Fallback on empty result ──────────────────────────────────────────────────


def test_fallback_returns_original_pool_when_filters_empty_pool(session):
    pool = [_dest("NA1", "North America")]
    result, fallback = apply_destination_filters(
        pool,
        session,
        _prefs(region_allowlist=json.dumps(["Western Europe"])),
    )
    assert fallback is True
    assert result == pool  # unfiltered pool returned


def test_no_fallback_when_filters_leave_items(session):
    pool = [_dest("NA1", "North America"), _dest("EU1", "Western Europe")]
    result, fallback = apply_destination_filters(
        pool,
        session,
        _prefs(region_allowlist=json.dumps(["North America"])),
    )
    assert fallback is False
    assert len(result) == 1
