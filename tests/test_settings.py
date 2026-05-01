"""Tests for get_flight_data_mode() — DB preference takes priority over env var."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from trip_a_day.db import Base, seed_preferences
from trip_a_day.fetcher import get_flight_data_mode
from trip_a_day.preferences import set_pref


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    seed_preferences(session)
    session.commit()
    return session


def test_db_mock_overrides_live_env(monkeypatch):
    """DB preference 'mock' wins over FLIGHT_DATA_MODE=live env var."""
    monkeypatch.setenv("FLIGHT_DATA_MODE", "live")
    session = _make_session()
    set_pref(session, "flight_data_mode", "mock")
    session.commit()
    assert get_flight_data_mode(session) == "mock"


def test_db_live_overrides_mock_env(monkeypatch):
    """DB preference 'live' wins over FLIGHT_DATA_MODE=mock env var."""
    monkeypatch.setenv("FLIGHT_DATA_MODE", "mock")
    session = _make_session()
    set_pref(session, "flight_data_mode", "live")
    session.commit()
    assert get_flight_data_mode(session) == "live"


def test_env_mock_used_when_db_absent(monkeypatch):
    """When DB has no flight_data_mode row, env var is used."""
    monkeypatch.setenv("FLIGHT_DATA_MODE", "mock")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    # Do NOT call seed_preferences — preference row does not exist
    with Session(engine) as session:
        assert get_flight_data_mode(session) == "mock"


def test_env_live_used_when_db_absent(monkeypatch):
    """When DB has no flight_data_mode row, env var 'live' is used."""
    monkeypatch.setenv("FLIGHT_DATA_MODE", "live")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert get_flight_data_mode(session) == "live"


def test_default_mock_when_both_absent(monkeypatch):
    """When neither DB nor env var is set, default is 'mock'."""
    monkeypatch.delenv("FLIGHT_DATA_MODE", raising=False)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert get_flight_data_mode(session) == "mock"


def test_invalid_db_value_falls_back_to_env(monkeypatch):
    """Invalid DB value (not 'mock'/'live') falls through to env var."""
    monkeypatch.setenv("FLIGHT_DATA_MODE", "live")
    session = _make_session()
    set_pref(session, "flight_data_mode", "invalid_value")
    session.commit()
    assert get_flight_data_mode(session) == "live"


def test_invalid_env_value_defaults_to_mock(monkeypatch):
    """Invalid env var and absent DB preference → 'mock'."""
    monkeypatch.setenv("FLIGHT_DATA_MODE", "garbage")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        assert get_flight_data_mode(session) == "mock"


def test_seeded_default_is_mock():
    """seed_preferences inserts 'mock' as the default flight_data_mode."""
    session = _make_session()
    assert get_flight_data_mode(session) == "mock"
