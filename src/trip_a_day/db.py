"""SQLAlchemy ORM models, engine setup, and database initialization."""

from __future__ import annotations

import json
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
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB = _PROJECT_ROOT / "trip_of_the_day.db"
DB_PATH = Path(os.environ.get("DB_PATH", str(_DEFAULT_DB)))

_SEED_AIRPORTS_PATH = _PROJECT_ROOT / "data" / "seed_airports.json"


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
    country_code: Mapped[str | None] = mapped_column(String(5), nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    subregion: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    typical_price_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exclusion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Phase 5 pool tracking columns
    last_queried_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_known_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_known_price_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    times_selected: Mapped[int] = mapped_column(Integer, default=0)
    avg_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    user_favorited: Mapped[bool] = mapped_column(Boolean, default=False)
    user_booked: Mapped[bool] = mapped_column(Boolean, default=False)


class PriceCache(Base):
    """Cached flight prices to avoid redundant live API calls."""

    __tablename__ = "price_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    destination_iata: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_iata: Mapped[str] = mapped_column(String(10), nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    return_date: Mapped[date] = mapped_column(Date, nullable=False)
    adults: Mapped[int] = mapped_column(Integer, nullable=False)
    children: Mapped[int] = mapped_column(Integer, nullable=False)
    price_usd: Mapped[float] = mapped_column(Float, nullable=False)
    airline: Mapped[str | None] = mapped_column(String, nullable=True)
    stops: Mapped[int | None] = mapped_column(Integer, nullable=True)
    queried_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)


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
    api_calls_flights: Mapped[int] = mapped_column(Integer, default=0)
    api_calls_gsa: Mapped[int] = mapped_column(Integer, default=0)
    filter_fallback: Mapped[bool] = mapped_column(Boolean, default=False)


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
    "trip_length_flex_nights": "0",
    "advance_days": "7",
    "num_adults": "2",
    "num_children": "2",
    "num_rooms": "1",
    "direct_flights_only": "true",
    "min_hotel_stars": "4",
    "car_rental_required": "true",
    "notification_emails": "[]",
    "ranking_strategy": "cheapest_then_farthest",
    "search_radius_miles": "0",
    "region_filter": "null",
    "scheduled_run_time": "07:00",
    # Phase 5 destination pool preferences
    "daily_batch_size": "15",
    "destination_selection_strategy": "least_recently_queried",
    "cache_ttl_enabled": "true",
    "max_live_calls_per_run": "40",
    "two_pass_candidate_count": "5",
    # Internal strategy state (not user-facing)
    "round_robin_offset": "0",
    "region_cycle_index": "0",
    # Phase 6 filter preferences
    "region_allowlist": "[]",
    "region_blocklist": "[]",
    "favorite_locations": "[]",
    "favorite_radius_miles": "0",
    "exclude_previously_selected": "false",
    "exclude_previously_selected_days": "0",
    "exclude_booked": "false",
    # Phase 7 (pre-work)
    "notifications_enabled": "true",
    # Phase 7 — multi-airport departure
    "irs_mileage_rate": "0.70",
}

# Destination columns added via ALTER TABLE migration (idempotent).
_DESTINATION_NEW_COLUMNS: list[tuple[str, str]] = [
    ("country_code", "TEXT"),
    ("subregion", "TEXT"),
    ("typical_price_tier", "TEXT"),
    ("last_queried_at", "DATETIME"),
    ("last_known_price_usd", "REAL"),
    ("last_known_price_date", "DATE"),
    ("query_count", "INTEGER DEFAULT 0"),
    ("times_selected", "INTEGER DEFAULT 0"),
    ("avg_price_usd", "REAL"),
    ("enabled", "BOOLEAN DEFAULT 1"),
    ("user_favorited", "BOOLEAN DEFAULT 0"),
    # Phase 6
    ("user_booked", "BOOLEAN DEFAULT 0"),
]

# run_log columns added via ALTER TABLE migration (idempotent).
_RUN_LOG_NEW_COLUMNS: list[tuple[str, str]] = [
    ("filter_fallback", "BOOLEAN DEFAULT 0"),
]


def _migrate_schema() -> None:
    """Add any new columns to existing tables via ALTER TABLE (idempotent)."""
    with engine.connect() as conn:
        dest_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(destinations)"))
        }
        for col_name, col_def in _DESTINATION_NEW_COLUMNS:
            if col_name not in dest_cols:
                conn.execute(
                    text(f"ALTER TABLE destinations ADD COLUMN {col_name} {col_def}")
                )
        run_log_cols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(run_log)"))
        }
        for col_name, col_def in _RUN_LOG_NEW_COLUMNS:
            if col_name not in run_log_cols:
                conn.execute(
                    text(f"ALTER TABLE run_log ADD COLUMN {col_name} {col_def}")
                )
        conn.commit()


def init_db() -> None:
    """Create all tables if they do not exist and run schema migrations."""
    Base.metadata.create_all(engine)
    _migrate_schema()
    _seed_destinations()


def seed_preferences(session: Session) -> None:
    """Insert default preference values if not already present."""
    now = datetime.now(UTC)
    for key, value in _PREFERENCE_DEFAULTS.items():
        existing = session.get(Preference, key)
        if existing is None:
            session.add(Preference(key=key, value=value, updated_at=now))
    session.flush()


def _seed_destinations() -> None:
    """Upsert all airports from seed_airports.json into the destinations table.

    Idempotent: new airports are inserted; existing ones get metadata refreshed
    (lat/lon, country_code, subregion, typical_price_tier) without touching
    user-controlled fields like excluded, enabled, user_favorited.
    """
    if not _SEED_AIRPORTS_PATH.exists():
        return
    airports = json.loads(_SEED_AIRPORTS_PATH.read_text(encoding="utf-8"))

    with SessionFactory() as session:
        for ap in airports:
            iata = ap["iata"]
            existing = session.get(Destination, iata)
            if existing is None:
                session.add(
                    Destination(
                        iata_code=iata,
                        city=ap.get("city"),
                        country=ap.get("country"),
                        country_code=ap.get("country_code"),
                        region=ap.get("region"),
                        subregion=ap.get("subregion"),
                        latitude=ap.get("latitude", 0.0),
                        longitude=ap.get("longitude", 0.0),
                        typical_price_tier=ap.get("typical_price_tier"),
                        excluded=False,
                        enabled=True,
                        user_favorited=False,
                        user_booked=False,
                        query_count=0,
                        times_selected=0,
                    )
                )
            else:
                # Refresh metadata without touching user-controlled fields.
                existing.city = ap.get("city") or existing.city
                existing.country = ap.get("country") or existing.country
                existing.country_code = ap.get("country_code") or existing.country_code
                existing.region = ap.get("region") or existing.region
                existing.subregion = ap.get("subregion") or existing.subregion
                existing.typical_price_tier = (
                    ap.get("typical_price_tier") or existing.typical_price_tier
                )
                # Only fill in coordinates if they were missing (0.0).
                if ap.get("latitude") and (
                    existing.latitude is None or existing.latitude == 0.0
                ):
                    existing.latitude = ap["latitude"]
                if ap.get("longitude") and (
                    existing.longitude is None or existing.longitude == 0.0
                ):
                    existing.longitude = ap["longitude"]
        session.commit()


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
            "google_flights": (300, None),
            "gsa": (None, None),
            "resend": (100, 3000),
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
