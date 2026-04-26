"""Tests for monthly email limit enforcement (notifier.py + db.py helpers)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from trip_a_day.db import (
    Base,
    EmailUsage,
    Preference,
    RunLog,
    get_emails_sent_this_month,
    record_email_sent,
    seed_preferences,
)
from trip_a_day.notifier import (
    _check_email_limit,
    _email_limit_warning_html,
    get_monthly_email_usage,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        seed_preferences(session)
        session.commit()
        yield session


def _set_pref(session: Session, key: str, value: str) -> None:
    row = session.get(Preference, key)
    if row is None:
        session.add(Preference(key=key, value=value, updated_at=datetime.now(UTC)))
    else:
        row.value = value
    session.flush()


def _set_email_sent(session: Session, count: int) -> None:
    """Directly insert/update the current-month EmailUsage row."""
    from datetime import date

    month = date.today().strftime("%Y-%m")
    row = session.query(EmailUsage).filter_by(month=month).first()
    if row is None:
        row = EmailUsage(month=month, emails_sent=count)
        session.add(row)
        session.flush()
    else:
        row.emails_sent = count
    session.flush()


# ── get_emails_sent_this_month ────────────────────────────────────────────────


def test_get_emails_sent_returns_zero_when_no_row(db_session):
    assert get_emails_sent_this_month(db_session) == 0


def test_get_emails_sent_returns_count_when_row_exists(db_session):
    _set_email_sent(db_session, 42)
    assert get_emails_sent_this_month(db_session) == 42


# ── record_email_sent ─────────────────────────────────────────────────────────


def test_record_email_sent_increments_from_zero(db_session):
    record_email_sent(db_session)
    assert get_emails_sent_this_month(db_session) == 1


def test_record_email_sent_increments_existing(db_session):
    _set_email_sent(db_session, 10)
    record_email_sent(db_session)
    assert get_emails_sent_this_month(db_session) == 11


def test_record_email_sent_updates_last_sent_at(db_session):
    from datetime import date

    record_email_sent(db_session)
    month = date.today().strftime("%Y-%m")
    row = db_session.query(EmailUsage).filter_by(month=month).first()
    assert row is not None
    assert row.last_sent_at is not None


# ── get_monthly_email_usage ───────────────────────────────────────────────────


def test_get_monthly_email_usage_returns_sent_and_limit(db_session):
    _set_email_sent(db_session, 5)
    _set_pref(db_session, "email_monthly_limit", "100")
    sent, limit = get_monthly_email_usage(db_session)
    assert sent == 5
    assert limit == 100


def test_get_monthly_email_usage_default_limit(db_session):
    _, limit = get_monthly_email_usage(db_session)
    assert limit == 3000


# ── _check_email_limit ────────────────────────────────────────────────────────


def test_check_email_limit_allows_when_below_limit(db_session):
    _set_email_sent(db_session, 0)
    _set_pref(db_session, "email_monthly_limit", "10")
    can_send, reason = _check_email_limit(db_session)
    assert can_send is True
    assert reason == ""


def test_check_email_limit_blocks_when_at_limit(db_session):
    _set_pref(db_session, "email_monthly_limit", "10")
    _set_email_sent(db_session, 10)
    can_send, reason = _check_email_limit(db_session)
    assert can_send is False
    assert "10/10" in reason


def test_check_email_limit_blocks_when_over_limit(db_session):
    _set_pref(db_session, "email_monthly_limit", "5")
    _set_email_sent(db_session, 7)
    can_send, reason = _check_email_limit(db_session)
    assert can_send is False
    assert "7/5" in reason


def test_check_email_limit_allows_one_below_limit(db_session):
    _set_pref(db_session, "email_monthly_limit", "10")
    _set_email_sent(db_session, 9)
    can_send, _ = _check_email_limit(db_session)
    assert can_send is True


# ── warning banner ────────────────────────────────────────────────────────────


def test_warning_banner_absent_when_below_threshold(db_session):
    _set_pref(db_session, "email_monthly_limit", "100")
    _set_pref(db_session, "email_warning_threshold_pct", "90")
    _set_email_sent(db_session, 50)  # 50% — well below 90%
    html = _email_limit_warning_html(db_session)
    assert html == ""


def test_warning_banner_present_when_at_threshold(db_session):
    _set_pref(db_session, "email_monthly_limit", "100")
    _set_pref(db_session, "email_warning_threshold_pct", "90")
    _set_email_sent(db_session, 90)  # exactly at 90%
    html = _email_limit_warning_html(db_session)
    assert "Email limit warning" in html
    assert "90" in html


def test_warning_banner_present_when_above_threshold(db_session):
    _set_pref(db_session, "email_monthly_limit", "100")
    _set_pref(db_session, "email_warning_threshold_pct", "90")
    _set_email_sent(db_session, 95)
    html = _email_limit_warning_html(db_session)
    assert "Email limit warning" in html


def test_warning_banner_absent_when_no_session():
    html = _email_limit_warning_html(None)
    assert html == ""


# ── blocked send recorded in RunLog ──────────────────────────────────────────


def test_blocked_send_recorded_in_run_log(db_session, monkeypatch):
    """send_trip_notification records email_blocked=True in the most recent RunLog."""
    import datetime

    from trip_a_day.notifier import send_trip_notification

    # Add a RunLog row to simulate a completed run
    run_log = RunLog(
        run_at=datetime.datetime.now(UTC),
        status="success",
        triggered_by="test",
    )
    db_session.add(run_log)
    db_session.commit()

    # Set limit to 0 so every send is blocked
    _set_pref(db_session, "email_monthly_limit", "0")
    _set_pref(db_session, "notifications_enabled", "true")

    # Build a minimal TripCandidate
    from datetime import date

    from trip_a_day.costs import CostBreakdown
    from trip_a_day.ranker import TripCandidate

    cost = CostBreakdown(flights=100, hotel=50, car=20, food=30, car_is_estimate=False)
    trip = TripCandidate(
        destination_iata="CDG",
        city="Paris",
        country="France",
        region="Europe",
        departure_date=date(2026, 7, 1),
        return_date=date(2026, 7, 8),
        cost=cost,
        distance_miles=4500,
        flight_booking_url="https://example.com",
        hotel_booking_url="https://example.com",
        car_booking_url="https://example.com",
        raw_flight_data="{}",
        raw_hotel_data="{}",
    )

    # Provide RESEND_API_KEY so we reach the limit check (not the no-key fallback)
    monkeypatch.setenv("RESEND_API_KEY", "re_test_fake_key")

    result = send_trip_notification(
        trip,
        {"notification_emails": '["test@example.com"]'},
        db_session=db_session,
    )

    assert result is False

    # _record_run_log_blocked marks the row dirty in the session (not yet committed).
    # Access the attribute directly; do NOT refresh (refresh re-loads from DB).
    assert run_log.email_blocked is True
    assert run_log.email_blocked_reason is not None
    assert "limit" in run_log.email_blocked_reason.lower()
