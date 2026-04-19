"""Unit tests for get_nearby_airports (fetcher.py)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trip_a_day.db import Base, Destination
from trip_a_day.fetcher import get_nearby_airports


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'nearby_test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as s:
        yield s


def _add_airport(
    session,
    iata: str,
    city: str,
    lat: float,
    lon: float,
    enabled: bool = True,
) -> Destination:
    d = Destination(
        iata_code=iata,
        city=city,
        country="United States",
        region="North America",
        latitude=lat,
        longitude=lon,
        enabled=enabled,
        excluded=False,
    )
    session.add(d)
    session.flush()
    return d


# Real approximate coordinates:
# HSV (Huntsville, AL):  34.6418, -86.7751
# BHM (Birmingham, AL):  33.5629, -86.7535  — ~73 mi from HSV
# ATL (Atlanta, GA):     33.6407, -84.4277  — ~167 mi from HSV
# JFK (New York, NY):    40.6413, -73.7781  — ~930 mi from HSV


class TestGetNearbyAirports:
    def test_radius_zero_returns_empty(self, session):
        _add_airport(session, "HSV", "Huntsville", 34.6418, -86.7751)
        _add_airport(session, "BHM", "Birmingham", 33.5629, -86.7535)
        result = get_nearby_airports("HSV", 0, session)
        assert result == []

    def test_negative_radius_returns_empty(self, session):
        _add_airport(session, "HSV", "Huntsville", 34.6418, -86.7751)
        _add_airport(session, "BHM", "Birmingham", 33.5629, -86.7535)
        result = get_nearby_airports("HSV", -50, session)
        assert result == []

    def test_home_airport_excluded_from_results(self, session):
        _add_airport(session, "HSV", "Huntsville", 34.6418, -86.7751)
        _add_airport(session, "BHM", "Birmingham", 33.5629, -86.7535)
        result = get_nearby_airports("HSV", 500, session)
        iatas = [a.iata for a in result]
        assert "HSV" not in iatas

    def test_nearby_airport_within_radius_returned(self, session):
        _add_airport(session, "HSV", "Huntsville", 34.6418, -86.7751)
        _add_airport(session, "BHM", "Birmingham", 33.5629, -86.7535)  # ~73 mi
        result = get_nearby_airports("HSV", 100, session)
        iatas = [a.iata for a in result]
        assert "BHM" in iatas

    def test_airport_beyond_radius_excluded(self, session):
        _add_airport(session, "HSV", "Huntsville", 34.6418, -86.7751)
        _add_airport(session, "BHM", "Birmingham", 33.5629, -86.7535)  # ~73 mi
        _add_airport(session, "JFK", "New York", 40.6413, -73.7781)  # ~930 mi
        result = get_nearby_airports("HSV", 100, session)
        iatas = [a.iata for a in result]
        assert "BHM" in iatas
        assert "JFK" not in iatas

    def test_radius_500_returns_bhm_and_atl(self, session):
        _add_airport(session, "HSV", "Huntsville", 34.6418, -86.7751)
        _add_airport(session, "BHM", "Birmingham", 33.5629, -86.7535)  # ~73 mi
        _add_airport(session, "ATL", "Atlanta", 33.6407, -84.4277)  # ~167 mi
        _add_airport(session, "JFK", "New York", 40.6413, -73.7781)  # ~930 mi
        result = get_nearby_airports("HSV", 500, session)
        iatas = [a.iata for a in result]
        assert "BHM" in iatas
        assert "ATL" in iatas
        assert "JFK" not in iatas

    def test_disabled_airport_excluded(self, session):
        _add_airport(session, "HSV", "Huntsville", 34.6418, -86.7751)
        _add_airport(session, "BHM", "Birmingham", 33.5629, -86.7535, enabled=False)
        result = get_nearby_airports("HSV", 500, session)
        iatas = [a.iata for a in result]
        assert "BHM" not in iatas

    def test_returns_airport_info_objects(self, session):
        _add_airport(session, "HSV", "Huntsville", 34.6418, -86.7751)
        _add_airport(session, "BHM", "Birmingham", 33.5629, -86.7535)
        result = get_nearby_airports("HSV", 100, session)
        assert len(result) == 1
        airport = result[0]
        assert airport.iata == "BHM"
        assert airport.city == "Birmingham"
        assert airport.latitude == pytest.approx(33.5629, abs=0.001)

    def test_home_not_in_db_returns_empty(self, session):
        _add_airport(session, "BHM", "Birmingham", 33.5629, -86.7535)
        result = get_nearby_airports("UNKNOWN", 500, session)
        assert result == []
