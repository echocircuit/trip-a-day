"""Tests for _migrate_preferences() — data migrations that fix stale preference values."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from trip_a_day.db import Base, Preference, _migrate_preferences, seed_preferences
from trip_a_day.preferences import get_or


def _make_session(seed: bool = True) -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    if seed:
        seed_preferences(session)
        session.commit()
    return session


# ---------------------------------------------------------------------------
# google_hotels → booking_com migration
# ---------------------------------------------------------------------------


def test_google_hotels_migrated_to_booking_com():
    """Existing DB rows with google_hotels are updated to booking_com on migration."""
    session = _make_session(seed=False)
    session.add(Preference(key="preferred_hotel_site", value="google_hotels"))
    session.commit()

    _migrate_preferences(session)
    session.flush()

    pref = session.get(Preference, "preferred_hotel_site")
    assert pref is not None
    assert pref.value == "booking_com"


def test_booking_com_untouched_by_migration():
    """Rows already set to booking_com are not modified."""
    session = _make_session(seed=False)
    session.add(Preference(key="preferred_hotel_site", value="booking_com"))
    session.commit()

    _migrate_preferences(session)
    session.flush()

    pref = session.get(Preference, "preferred_hotel_site")
    assert pref is not None
    assert pref.value == "booking_com"


def test_expedia_untouched_by_migration():
    """Users who explicitly chose expedia are not changed."""
    session = _make_session(seed=False)
    session.add(Preference(key="preferred_hotel_site", value="expedia"))
    session.commit()

    _migrate_preferences(session)
    session.flush()

    pref = session.get(Preference, "preferred_hotel_site")
    assert pref is not None
    assert pref.value == "expedia"


def test_migration_no_op_when_preference_absent():
    """_migrate_preferences() runs cleanly even when the preference row doesn't exist."""
    session = _make_session(seed=False)
    _migrate_preferences(session)  # must not raise


def test_seeded_default_is_booking_com():
    """seed_preferences() now defaults preferred_hotel_site to booking_com."""
    session = _make_session(seed=True)
    assert get_or(session, "preferred_hotel_site", "") == "booking_com"


def test_migration_is_idempotent():
    """Running _migrate_preferences() twice does not error and leaves value correct."""
    session = _make_session(seed=False)
    session.add(Preference(key="preferred_hotel_site", value="google_hotels"))
    session.commit()

    _migrate_preferences(session)
    _migrate_preferences(session)
    session.flush()

    pref = session.get(Preference, "preferred_hotel_site")
    assert pref is not None
    assert pref.value == "booking_com"
