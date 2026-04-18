"""SQLAlchemy ORM models, engine setup, and database initialization."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB = _PROJECT_ROOT / "trip_of_the_day.db"
DB_PATH = Path(os.environ.get("DB_PATH", str(_DEFAULT_DB)))


def _engine():
    return create_engine(f"sqlite:///{DB_PATH}", echo=False)


engine = _engine()
SessionFactory: sessionmaker[Session] = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class Preference(Base):
    __tablename__ = "preferences"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )


class Destination(Base):
    __tablename__ = "destinations"

    iata_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exclusion_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False)
    destination_iata: Mapped[str] = mapped_column(String(10), nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    flight_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    hotel_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    car_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    food_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    distance_miles: Mapped[float] = mapped_column(Float, default=0.0)
    flight_booking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    hotel_booking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    car_booking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_flight_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_hotel_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    car_cost_is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)


class RunLog(Base):
    __tablename__ = "run_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(20), default="manual")
    destinations_evaluated: Mapped[int] = mapped_column(Integer, default=0)
    winner_trip_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    api_calls_amadeus: Mapped[int] = mapped_column(Integer, default=0)
    api_calls_numbeo: Mapped[int] = mapped_column(Integer, default=0)


class ApiUsage(Base):
    __tablename__ = "api_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_name: Mapped[str] = mapped_column(String(50), nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    calls_made: Mapped[int] = mapped_column(Integer, default=0)
    daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    monthly_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)


_PREFERENCE_DEFAULTS: dict[str, str] = {
    "home_airport": "HSV",
    "trip_length_nights": "7",
    "advance_days": "7",
    "num_adults": "2",
    "num_children": "2",
    "direct_flights_only": "true",
    "min_hotel_stars": "4",
    "car_rental_required": "true",
    "notification_emails": "[]",
    "ranking_strategy": "cheapest_then_farthest",
    "search_radius_miles": "0",
    "region_filter": "null",
}


def init_db() -> None:
    """Create all tables if they do not exist. Safe to call on every startup."""
    Base.metadata.create_all(engine)


def seed_preferences(session: Session) -> None:
    """Insert default preference values if not already present."""
    now = datetime.now(UTC)
    for key, value in _PREFERENCE_DEFAULTS.items():
        existing = session.get(Preference, key)
        if existing is None:
            session.add(Preference(key=key, value=value, updated_at=now))
    session.flush()


def record_api_call(session: Session, api_name: str) -> None:
    """Increment the call counter for *api_name* on today's date."""
    today = date.today()
    row = (
        session.query(ApiUsage)
        .filter(ApiUsage.api_name == api_name, ApiUsage.usage_date == today)
        .first()
    )
    if row is None:
        limits = {
            "amadeus": (None, 2000),
            "numbeo": (None, None),
            "sendgrid": (100, None),
        }
        daily, monthly = limits.get(api_name, (None, None))
        row = ApiUsage(
            api_name=api_name,
            usage_date=today,
            calls_made=0,
            daily_limit=daily,
            monthly_limit=monthly,
        )
        session.add(row)
        session.flush()
    row.calls_made += 1


def get_api_calls_today(session: Session, api_name: str) -> int:
    """Return today's call count for *api_name*."""
    today = date.today()
    row = (
        session.query(ApiUsage)
        .filter(ApiUsage.api_name == api_name, ApiUsage.usage_date == today)
        .first()
    )
    return row.calls_made if row else 0
