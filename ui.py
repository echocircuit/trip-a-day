"""Streamlit web UI for trip-a-day.

Pages:
  Dashboard     — last run status, API usage, Trip of the Day card, Run Now button
  Preferences   — editable form for all user preferences
  Destinations  — manage destination pool (enable/disable, add custom, CSV import)
  Exclusion List — view / add / restore excluded destinations
  Trip History  — paginated table of all evaluated trip candidates

Usage:
    streamlit run ui.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import os

import streamlit as st
from sqlalchemy import desc

from trip_a_day.db import (
    ApiUsage,
    Destination,
    RunLog,
    SessionFactory,
    Trip,
    get_emails_sent_this_month,
    init_db,
    seed_preferences,
)
from trip_a_day.destination_input import (
    CsvImportPreview,
    fuzzy_match_per_diem,
    parse_destination_csv,
)
from trip_a_day.fetcher import get_airport_city
from trip_a_day.notifier import send_test_email
from trip_a_day.preferences import get_all, set_pref
from trip_a_day.selector import STRATEGY_LABELS

_PROJECT_ROOT = Path(__file__).resolve().parent

# ── one-time DB bootstrap ──────────────────────────────────────────────────────
init_db()
with SessionFactory() as _s:
    seed_preferences(_s)
    _s.commit()

# ── page config + navigation ───────────────────────────────────────────────────
st.set_page_config(page_title="trip-a-day", page_icon="✈️", layout="wide")
st.sidebar.title("✈️ trip-a-day")
_PAGE = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "Preferences", "Destinations", "Exclusion List", "Trip History"],
    label_visibility="collapsed",
)


# ── chart cache ───────────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def get_cached_chart(
    destination_iata: str,
    destination_name: str,
    today_cost: float,
    run_date_str: str,
) -> bytes | None:
    """Thin cached wrapper around generate_price_history_chart.

    run_date_str is a string so it is hashable for st.cache_data.
    """
    from trip_a_day.charts import generate_price_history_chart

    with SessionFactory() as session:
        return generate_price_history_chart(
            destination_iata=destination_iata,
            destination_name=destination_name,
            today_cost=today_cost,
            today_run_date=date.fromisoformat(run_date_str),
            db_session=session,
        )


# ── shared helpers ─────────────────────────────────────────────────────────────


def _run_now() -> None:
    """Invoke main.py as a subprocess and refresh the UI when done."""
    with st.spinner("Running trip search (~2 min)…"):
        result = subprocess.run(
            [sys.executable, str(_PROJECT_ROOT / "main.py")],
            capture_output=True,
            text=True,
            cwd=str(_PROJECT_ROOT),
        )
    if result.returncode == 0:
        st.success("Run complete!")
    else:
        st.error("Run failed.")
        with st.expander("Error output"):
            st.code((result.stderr or result.stdout or "No output.")[-3000:])
    st.rerun()


# ── Dashboard ──────────────────────────────────────────────────────────────────


def _is_mock_mode() -> bool:
    return os.environ.get("FLIGHT_DATA_MODE", "mock").lower().strip() == "mock"


def _dashboard() -> None:
    st.title("Dashboard")

    if _is_mock_mode():
        st.warning(
            "⚠️ Running in mock mode — flight prices are not real. "
            "Set `FLIGHT_DATA_MODE=live` in your `.env` to use live data.",
            icon=None,
        )

    with SessionFactory() as _s:
        _prefs = get_all(_s)
        _notifs_enabled = _prefs.get("notifications_enabled", "true") == "true"
        _home_airport = _prefs.get("home_airport", "HSV")
    if not _notifs_enabled:
        st.info("🔕 Notifications disabled — email will not be sent after runs.")

    with SessionFactory() as s:
        last_run: RunLog | None = s.query(RunLog).order_by(desc(RunLog.run_at)).first()
        winner: Trip | None = (
            s.get(Trip, last_run.winner_trip_id)
            if last_run and last_run.winner_trip_id
            else None
        )
        today = date.today()
        api_rows: list[ApiUsage] = (
            s.query(ApiUsage).filter(ApiUsage.usage_date == today).all()
        )
        dest: Destination | None = (
            s.get(Destination, winner.destination_iata) if winner else None
        )
        _email_sent_this_month = get_emails_sent_this_month(s)
        _email_limit_dash = int(_prefs.get("email_monthly_limit", "3000"))

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Last Run")
        if last_run:
            icons = {"success": "✅", "partial": "⚠️", "failed": "❌"}
            icon = icons.get(last_run.status, "❓")
            st.metric("Status", f"{icon} {last_run.status.capitalize()}")
            st.write(f"**When:** {last_run.run_at.strftime('%Y-%m-%d %H:%M')} UTC")
            st.write(f"**Triggered by:** {last_run.triggered_by}")
            if last_run.duration_seconds is not None:
                st.write(f"**Duration:** {last_run.duration_seconds:.1f}s")
            live_calls = last_run.api_calls_flights or 0
            cache_hits_val = getattr(last_run, "cache_hits_flights", 0) or 0
            excluded_val = getattr(last_run, "destinations_excluded", 0) or 0
            st.write(
                f"**Run summary:** {last_run.destinations_evaluated} destinations evaluated"
                f" — {live_calls} live API calls (this run), {cache_hits_val} cache hits"
                + (f", {excluded_val} excluded" if excluded_val else "")
            )
            if last_run.error_message:
                st.error(last_run.error_message)
            if getattr(last_run, "filter_fallback", False):
                st.warning(
                    "Filter fallback triggered — destination filters produced no "
                    "matches and the run used the unfiltered pool. "
                    "Consider relaxing your filters in Preferences."
                )
            exclusions_json = getattr(last_run, "invalid_data_exclusions", None)
            if exclusions_json:
                try:
                    exclusions = json.loads(exclusions_json)
                except Exception:
                    exclusions = []
                if exclusions:
                    st.warning(
                        f"⚠️ {len(exclusions)} destination(s) excluded due to invalid "
                        "cost data (e.g. $0 flight price from live API)."
                    )
                    with st.expander("Show excluded destinations"):
                        for ex in exclusions:
                            st.write(
                                f"- **{ex.get('city', '?')}** ({ex.get('iata', '?')}): "
                                f"{ex.get('reason', 'unknown reason')}"
                            )
        else:
            st.info("No runs yet. Click **Run Now** below to get started.")

    with col2:
        st.subheader("API Usage Today")
        st.caption("Cumulative calls across all runs today")
        if api_rows:
            for row in api_rows:
                label = row.api_name.replace("_", " ").title()
                used = row.calls_made
                if row.daily_limit:
                    pct = used / row.daily_limit
                    icon = "🔴" if pct >= 0.9 else ("🟡" if pct >= 0.8 else "🟢")
                    st.write(f"{icon} **{label}:** {used} / {row.daily_limit} today")
                    if pct >= 0.8:
                        st.warning(f"{label} at {pct:.0%} of daily limit.")
                else:
                    st.write(f"🟢 **{label}:** {used} calls today")
        else:
            st.write("No API calls recorded today.")

        st.caption("Monthly email usage")
        _email_pct = (
            _email_sent_this_month / _email_limit_dash if _email_limit_dash > 0 else 0.0
        )
        _warn_threshold = int(_prefs.get("email_warning_threshold_pct", "90")) / 100
        if _email_pct >= 1.0:
            st.error(
                f"📧 Limit reached — emails paused until next month"
                f" ({_email_sent_this_month:,}/{_email_limit_dash:,})"
            )
        elif _email_pct >= _warn_threshold:
            st.warning(
                f"📧 {_email_sent_this_month:,}/{_email_limit_dash:,} emails this month"
                f" — approaching limit ({_email_pct:.0%})"
            )
        else:
            st.write(
                f"📧 **Email:** {_email_sent_this_month:,}/{_email_limit_dash:,}"
                f" emails this month"
            )

    st.divider()
    st.subheader("Trip of the Day")

    if winner:
        city = dest.city if dest else winner.destination_iata
        country = dest.country if dest else ""
        nights = (winner.return_date - winner.departure_date).days

        st.markdown(f"### {city}, {country}")
        st.caption(
            f"Run date: {winner.run_date} · "
            f"Depart {winner.departure_date} → Return {winner.return_date} ({nights} nights)"
        )

        dep_iata = getattr(winner, "departure_iata", None)
        if dep_iata:
            dep_city = get_airport_city(dep_iata)
            dep_label = dep_iata if dep_city == dep_iata else f"{dep_city} ({dep_iata})"
            if dep_iata != _home_airport:
                dep_label += f"  ⚠️ Not your home airport ({_home_airport})"
            st.caption(f"Departing from: {dep_label}")

        c1, c2, c3, c4, c5 = st.columns(5)
        flights_label = "✈️ Flights" + (" ⚠️ mock" if _is_mock_mode() else "")
        c1.metric(flights_label, f"${winner.flight_cost_usd:,.0f}")
        c2.metric("🏨 Hotel *", f"${winner.hotel_cost_usd:,.0f}")
        c3.metric("🚗 Car *", f"${winner.car_cost_usd:,.0f}")
        c4.metric("🍽️ Food *", f"${winner.food_cost_usd:,.0f}")
        c5.metric("💰 Total", f"${winner.total_cost_usd:,.0f}")

        st.caption(
            "* Hotel and food are government per diem estimates (GSA / State Dept); "
            "car rental is a regional average. Only flight prices are live quotes."
        )

        chart_bytes = get_cached_chart(
            destination_iata=winner.destination_iata,
            destination_name=f"{city}, {country}",
            today_cost=winner.total_cost_usd,
            run_date_str=str(winner.run_date),
        )
        if chart_bytes:
            st.image(
                chart_bytes,
                caption="Price history and recent daily picks",
                use_container_width=True,
            )
        else:
            st.caption("📊 Not enough history yet to show price trends.")

        bc1, bc2, bc3 = st.columns(3)
        if winner.flight_booking_url:
            bc1.link_button("✈️ Book Flights", winner.flight_booking_url)
        if winner.hotel_booking_url:
            bc2.link_button("🏨 Book Hotel", winner.hotel_booking_url)
        if winner.car_booking_url:
            bc3.link_button("🚗 Find Car Rental", winner.car_booking_url)
    else:
        st.info("No trip results yet.")

    st.divider()
    if st.button("▶ Run Now", type="primary"):
        _run_now()


# ── Preferences ────────────────────────────────────────────────────────────────

_STRATEGIES = ["cheapest_then_farthest", "farthest_then_cheapest", "random"]

_ALL_REGIONS = [
    "Africa",
    "Caribbean",
    "Central Asia",
    "East Asia",
    "Eastern Europe",
    "Mexico / Central America",
    "Middle East",
    "North America",
    "Oceania",
    "South America",
    "South Asia",
    "Southeast Asia",
    "Western Europe",
]


def _preferences() -> None:
    st.title("Preferences")
    st.caption("Changes take effect on the next run.")

    with SessionFactory() as s:
        prefs = get_all(s)
        # Load destinations for favorite-city multiselect
        _all_dests_for_fav: list[Destination] = (
            s.query(Destination).order_by(Destination.city).all()
        )
        _fav_dest_labels = {
            d.iata_code: f"{d.city or d.iata_code}, {d.country or ''} ({d.iata_code})"
            for d in _all_dests_for_fav
        }
        _currently_favorited_iatas = [
            d.iata_code for d in _all_dests_for_fav if d.user_favorited
        ]

    def _int(key: str, default: int) -> int:
        try:
            return int(prefs.get(key, str(default)))
        except ValueError:
            return default

    def _bool(key: str, default: bool = True) -> bool:
        return prefs.get(key, "true" if default else "false").strip().lower() == "true"

    def _parse_json_pref(p: dict, key: str) -> list:
        try:
            val = json.loads(p.get(key, "[]"))
            return val if isinstance(val, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    # Read-only flight data mode indicator (env var, not a DB preference)
    mode = os.environ.get("FLIGHT_DATA_MODE", "mock").lower().strip()
    if mode == "mock":
        st.info(
            "**Flight data mode: mock** — Prices come from static fixtures, not Google Flights. "
            "Set `FLIGHT_DATA_MODE=live` in your `.env` to use live pricing. "
            "Mock mode is safe for development and testing.",
        )
    else:
        st.success(
            "**Flight data mode: live** — Prices are fetched from Google Flights in real time.",
        )

    with st.form("preferences_form"):
        st.subheader("Trip Configuration")
        home_airport = st.text_input(
            "Home Airport (IATA code)", value=prefs.get("home_airport", "HSV")
        )
        col1, col2 = st.columns(2)
        trip_nights = col1.number_input(
            "Trip length (nights)",
            min_value=1,
            max_value=30,
            value=_int("trip_length_nights", 7),
        )
        trip_flex = col2.number_input(
            "Flex (±nights)",
            min_value=0,
            max_value=7,
            value=_int("trip_length_flex_nights", 0),
            help="Search trip_length ± this many nights and pick the cheapest.",
        )

        st.markdown("**Booking Window**")
        st.caption(
            "The pipeline probes departure dates across this window and picks the "
            "cheapest date found. Earliest must be less than Latest."
        )
        win1, win2 = st.columns(2)
        advance_window_min = win1.number_input(
            "Earliest departure (days out)",
            min_value=1,
            max_value=364,
            value=_int("advance_window_min_days", 7),
            help="Minimum days from today to departure date.",
        )
        advance_window_max = win2.number_input(
            "Latest departure (days out)",
            min_value=2,
            max_value=365,
            value=_int("advance_window_max_days", 30),
            help="Maximum days from today to departure date.",
        )
        if advance_window_min >= advance_window_max:
            st.warning(
                "⚠️ Earliest departure must be less than Latest departure. "
                "Please adjust the booking window."
            )

        st.markdown("**Multi-Airport Departure**")
        st.caption(
            "When search radius > 0, the pipeline also searches from nearby airports "
            "and adds IRS-rate round-trip driving cost. Set to 0 to disable."
        )
        ma1, ma2 = st.columns(2)
        search_radius_miles = ma1.number_input(
            "Nearby airport search radius (miles, 0 = disabled)",
            min_value=0,
            max_value=500,
            value=_int("search_radius_miles", 0),
        )
        try:
            _irs_default = float(prefs.get("irs_mileage_rate", "0.70"))
        except ValueError:
            _irs_default = 0.70
        irs_mileage_rate = ma2.number_input(
            "IRS mileage rate ($/mile)",
            min_value=0.0,
            max_value=2.0,
            value=_irs_default,
            step=0.01,
            format="%.2f",
        )

        st.subheader("Travelers")
        ca, cb, cc = st.columns(3)
        num_adults = ca.number_input(
            "Adults", min_value=1, max_value=10, value=_int("num_adults", 2)
        )
        num_children = cb.number_input(
            "Children", min_value=0, max_value=10, value=_int("num_children", 2)
        )
        num_rooms = cc.number_input(
            "Rooms", min_value=1, max_value=10, value=_int("num_rooms", 1)
        )

        st.subheader("Filters")
        cx, cy = st.columns(2)
        direct_only = cx.checkbox(
            "Direct flights only", value=_bool("direct_flights_only")
        )
        car_required = cy.checkbox(
            "Car rental required", value=_bool("car_rental_required")
        )
        # min_hotel_stars intentionally absent: hotel costs use GSA per diem rates,
        # not live hotel search — star rating is meaningless here.

        st.subheader("Ranking")
        strategy_default = prefs.get("ranking_strategy", "cheapest_then_farthest")
        strategy_idx = (
            _STRATEGIES.index(strategy_default)
            if strategy_default in _STRATEGIES
            else 0
        )
        ranking_strategy = st.selectbox(
            "Ranking strategy", _STRATEGIES, index=strategy_idx
        )

        st.subheader("Destination Pool")
        daily_batch_size = st.number_input(
            "Daily batch size",
            min_value=1,
            max_value=100,
            value=_int("daily_batch_size", 15),
            help="Number of destinations evaluated each run.",
        )
        sel_strategy_keys = list(STRATEGY_LABELS.keys())
        sel_strategy_default = prefs.get(
            "destination_selection_strategy", "least_recently_queried"
        )
        sel_strategy_idx = (
            sel_strategy_keys.index(sel_strategy_default)
            if sel_strategy_default in sel_strategy_keys
            else 0
        )
        destination_selection_strategy = st.selectbox(
            "Destination selection strategy",
            sel_strategy_keys,
            index=sel_strategy_idx,
            format_func=lambda k: STRATEGY_LABELS[k],
        )
        cache_ttl_enabled = st.checkbox(
            "Enable price cache (avoid redundant API calls)",
            value=_bool("cache_ttl_enabled"),
        )
        max_live_calls = st.number_input(
            "Max live API calls per run",
            min_value=1,
            max_value=300,
            value=_int("max_live_calls_per_run", 40),
        )
        two_pass_count = st.number_input(
            "Two-pass candidate count (top N for night-variant search)",
            min_value=1,
            max_value=20,
            value=_int("two_pass_candidate_count", 5),
        )

        st.subheader("Filters")
        st.caption(
            "Filters narrow the destination pool before each run. "
            "If all filters combined produce no results, the run falls back to the "
            "unfiltered pool and you'll see a warning in the email and dashboard."
        )
        region_allowlist_val = st.multiselect(
            "Region allowlist (worldwide if empty)",
            _ALL_REGIONS,
            default=_parse_json_pref(prefs, "region_allowlist"),
        )
        region_blocklist_val = st.multiselect(
            "Region blocklist (takes precedence over allowlist)",
            _ALL_REGIONS,
            default=_parse_json_pref(prefs, "region_blocklist"),
        )
        st.markdown("**Favorite-location radius**")
        st.caption(
            "Select cities to use as favorites. Only destinations within the radius below "
            "will be considered when favorites are set. Selected cities are shown as chips."
        )
        fav_city_iatas = st.multiselect(
            "Favorite cities",
            options=list(_fav_dest_labels.keys()),
            default=_currently_favorited_iatas,
            format_func=lambda k: _fav_dest_labels.get(k, k),
            placeholder="Search by city or IATA code…",
        )
        fav_radius = st.number_input(
            "Favorite radius (miles, 0 = disabled)",
            min_value=0,
            max_value=10000,
            value=_int("favorite_radius_miles", 0),
        )
        exclude_selected = st.checkbox(
            "Exclude previously selected destinations",
            value=_bool("exclude_previously_selected", default=False),
        )
        exclude_selected_days = st.number_input(
            "Rolling window for exclusion (days, 0 = all-time)",
            min_value=0,
            max_value=3650,
            value=_int("exclude_previously_selected_days", 0),
            disabled=not exclude_selected,
        )
        exclude_booked = st.checkbox(
            "Exclude booked destinations",
            value=_bool("exclude_booked", default=False),
        )

        st.subheader("Booking Preferences")
        st.caption("Choose which booking site links are used in the daily email.")
        _hotel_sites = ["google_hotels", "booking_com", "expedia", "manual"]
        _hotel_site_labels = {
            "google_hotels": "Google Hotels",
            "booking_com": "Booking.com",
            "expedia": "Expedia",
            "manual": "Manual URL",
        }
        _car_sites = ["kayak", "expedia_cars", "manual"]
        _car_site_labels = {
            "kayak": "Kayak",
            "expedia_cars": "Expedia Cars",
            "manual": "Manual URL",
        }
        bk1, bk2 = st.columns(2)
        _hotel_site_default = prefs.get("preferred_hotel_site", "google_hotels")
        preferred_hotel_site = bk1.selectbox(
            "Hotel booking site",
            _hotel_sites,
            index=_hotel_sites.index(_hotel_site_default)
            if _hotel_site_default in _hotel_sites
            else 0,
            format_func=lambda k: _hotel_site_labels[k],
        )
        _car_site_default = prefs.get("preferred_car_site", "kayak")
        preferred_car_site = bk2.selectbox(
            "Car rental site",
            _car_sites,
            index=_car_sites.index(_car_site_default)
            if _car_site_default in _car_sites
            else 0,
            format_func=lambda k: _car_site_labels[k],
        )
        if preferred_hotel_site == "manual":
            preferred_hotel_manual_url = st.text_input(
                "Hotel base URL",
                value=prefs.get("preferred_hotel_site_manual_url", ""),
                help="This URL will be used as-is — no trip details will be added automatically.",
            )
        else:
            preferred_hotel_manual_url = prefs.get(
                "preferred_hotel_site_manual_url", ""
            )
        if preferred_car_site == "manual":
            preferred_car_manual_url = st.text_input(
                "Car rental base URL",
                value=prefs.get("preferred_car_site_manual_url", ""),
                help="This URL will be used as-is — no trip details will be added automatically.",
            )
        else:
            preferred_car_manual_url = prefs.get("preferred_car_site_manual_url", "")

        st.subheader("Notifications")
        _from_email = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")
        _is_test_sender = (
            not _from_email.strip() or "onboarding@resend.dev" in _from_email
        )
        if _is_test_sender:
            st.info(
                "📧 **Email sender: Resend shared test sender** (`onboarding@resend.dev`)  \n"
                "In test sender mode, emails can only be delivered to your verified Resend "
                "developer email address. To send to additional recipients, set up a custom "
                "verified domain and update `RESEND_FROM_EMAIL` in your `.env` file.  \n"
                "[→ Resend domain setup guide](https://resend.com/docs/dashboard/domains/introduction)"
            )
        else:
            st.success(f"📧 **Email sender:** {_from_email} (custom domain configured)")

        raw_emails = prefs.get("notification_emails", "[]")
        try:
            _parsed_emails = json.loads(raw_emails)
            emails_str = (
                ", ".join(_parsed_emails) if isinstance(_parsed_emails, list) else ""
            )
        except (json.JSONDecodeError, TypeError):
            emails_str = ""
        # Fall back to NOTIFICATION_EMAILS env var, mirroring notifier._parse_recipients
        if not emails_str:
            _env_emails = os.environ.get("NOTIFICATION_EMAILS", "")
            if _env_emails:
                emails_str = ", ".join(
                    e.strip() for e in _env_emails.split(",") if e.strip()
                )
        _emails_placeholder = "No email configured" if not emails_str else None
        if _is_test_sender:
            st.text_input(
                "Notification emails (read-only in test sender mode)",
                value=emails_str,
                placeholder=_emails_placeholder,
                disabled=True,
                help="Email recipients cannot be changed while using the shared test sender.",
            )
            notification_emails = emails_str
        else:
            notification_emails = st.text_input(
                "Notification emails (comma-separated)",
                value=emails_str,
                placeholder=_emails_placeholder or "you@example.com",
                help="Leave blank to print the trip to stdout instead of emailing.",
            )

        notifications_enabled_val = st.checkbox(
            "Disable notification emails",
            value=not _bool("notifications_enabled", default=True),
            help="When checked, runs complete normally but no email is sent. "
            "Useful during development to avoid consuming Resend's monthly limit.",
        )

        email_monthly_limit_val = st.number_input(
            "Monthly email limit",
            min_value=1,
            max_value=100_000,
            value=int(prefs.get("email_monthly_limit", "3000")),
            help="Resend free tier allows 3,000 emails/month. Emails stop sending once this limit is reached.",
        )
        email_warning_threshold_val = st.number_input(
            "Warning threshold (%)",
            min_value=1,
            max_value=100,
            value=int(prefs.get("email_warning_threshold_pct", "90")),
            help="A warning banner is added to outgoing emails when this percentage of the monthly limit is reached.",
        )

        st.subheader("Scheduler")
        raw_time = prefs.get("scheduled_run_time", "07:00")
        try:
            h, m = map(int, raw_time.split(":"))
            default_time: time = time(h, m)
        except ValueError:
            default_time = time(7, 0)
        run_time_val = st.time_input("Daily run time (local)", value=default_time)

        submitted = st.form_submit_button("Save Preferences", type="primary")

    if submitted:
        new_emails = [e.strip() for e in notification_emails.split(",") if e.strip()]
        with SessionFactory() as s:
            set_pref(s, "home_airport", home_airport.upper().strip())
            set_pref(s, "trip_length_nights", str(int(trip_nights)))
            set_pref(s, "trip_length_flex_nights", str(int(trip_flex)))
            set_pref(s, "advance_window_min_days", str(int(advance_window_min)))
            set_pref(s, "advance_window_max_days", str(int(advance_window_max)))
            set_pref(s, "search_radius_miles", str(int(search_radius_miles)))
            set_pref(s, "irs_mileage_rate", f"{float(irs_mileage_rate):.2f}")
            set_pref(s, "num_adults", str(int(num_adults)))
            set_pref(s, "num_children", str(int(num_children)))
            set_pref(s, "num_rooms", str(int(num_rooms)))
            set_pref(s, "direct_flights_only", "true" if direct_only else "false")
            set_pref(s, "car_rental_required", "true" if car_required else "false")
            set_pref(s, "ranking_strategy", ranking_strategy)
            set_pref(s, "daily_batch_size", str(int(daily_batch_size)))
            set_pref(
                s, "destination_selection_strategy", destination_selection_strategy
            )
            set_pref(s, "cache_ttl_enabled", "true" if cache_ttl_enabled else "false")
            set_pref(s, "max_live_calls_per_run", str(int(max_live_calls)))
            set_pref(s, "two_pass_candidate_count", str(int(two_pass_count)))
            set_pref(s, "region_allowlist", json.dumps(region_allowlist_val))
            set_pref(s, "region_blocklist", json.dumps(region_blocklist_val))
            set_pref(s, "favorite_radius_miles", str(int(fav_radius)))
            # Update user_favorited flag on all destinations to match multiselect
            selected_iatas = set(fav_city_iatas)
            for d in s.query(Destination).all():
                d.user_favorited = d.iata_code in selected_iatas
            set_pref(
                s,
                "exclude_previously_selected",
                "true" if exclude_selected else "false",
            )
            set_pref(
                s,
                "exclude_previously_selected_days",
                str(int(exclude_selected_days)),
            )
            set_pref(s, "exclude_booked", "true" if exclude_booked else "false")
            set_pref(s, "preferred_hotel_site", preferred_hotel_site)
            set_pref(s, "preferred_car_site", preferred_car_site)
            set_pref(s, "preferred_hotel_site_manual_url", preferred_hotel_manual_url)
            set_pref(s, "preferred_car_site_manual_url", preferred_car_manual_url)
            # Only update notification_emails when not in test sender mode
            _from_saved = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")
            if "onboarding@resend.dev" not in _from_saved and _from_saved.strip():
                set_pref(s, "notification_emails", json.dumps(new_emails))
            set_pref(
                s,
                "notifications_enabled",
                "false" if notifications_enabled_val else "true",
            )
            set_pref(s, "email_monthly_limit", str(int(email_monthly_limit_val)))
            set_pref(
                s, "email_warning_threshold_pct", str(int(email_warning_threshold_val))
            )
            set_pref(s, "scheduled_run_time", run_time_val.strftime("%H:%M"))
            s.commit()
        st.success("Preferences saved.")

    # Email usage indicator — outside the form (read-only, always current)
    st.subheader("Email Usage This Month")
    with SessionFactory() as _eu_s:
        _eu_sent = get_emails_sent_this_month(_eu_s)
        _eu_prefs = get_all(_eu_s)
    _eu_limit = int(_eu_prefs.get("email_monthly_limit", "3000"))
    _eu_warn_pct = int(_eu_prefs.get("email_warning_threshold_pct", "90")) / 100
    _eu_frac = min(_eu_sent / _eu_limit, 1.0) if _eu_limit > 0 else 0.0
    _eu_pct_int = int(_eu_frac * 100)
    if _eu_frac >= 1.0:
        st.error(
            f"📧 **{_eu_sent:,} / {_eu_limit:,} emails sent** — limit reached."
            " Emails will not be sent until next month."
        )
    elif _eu_frac >= _eu_warn_pct:
        st.warning(
            f"📧 **{_eu_sent:,} / {_eu_limit:,} emails sent** ({_eu_pct_int}% used)"
        )
    else:
        st.write(
            f"📧 **{_eu_sent:,} / {_eu_limit:,} emails sent** ({_eu_pct_int}% used)"
        )
    st.progress(_eu_frac)
    st.caption(
        f"At {int(_eu_warn_pct * 100)}% ({int(_eu_limit * _eu_warn_pct):,} emails),"
        " a warning banner is added to outgoing emails.  \n"
        f"At 100% ({_eu_limit:,} emails), emails stop sending until next month.  \n"
        "Counter resets on the 1st of each month."
    )

    # Test email button — outside the form so it sends without form submission
    st.subheader("Test Email")
    st.caption(
        "Send a test email to your configured recipients to verify Resend is set up correctly."
    )
    if st.button("📨 Send Test Email"):
        with SessionFactory() as _ts:
            _test_prefs = get_all(_ts)
            _ok, _msg = send_test_email(_test_prefs, db_session=_ts)
        if _ok:
            st.success(_msg)
        else:
            st.error(_msg)


# ── Destinations ──────────────────────────────────────────────────────────────


def _destinations() -> None:
    st.title("Destinations")
    st.caption(
        "Manage the pool of airports trip-a-day considers each day. "
        "Enable or disable individual destinations, add custom airports, or bulk-import from CSV."
    )

    # ── Section 1: Destination Pool ────────────────────────────────────────────
    st.subheader("Destination Pool")

    with SessionFactory() as s:
        all_dests: list[Destination] = (
            s.query(Destination).order_by(Destination.city).all()
        )
        dest_count = len(all_dests)
        enabled_count = sum(1 for d in all_dests if d.enabled)

    st.caption(
        f"{enabled_count} of {dest_count} destinations enabled. "
        "Toggle the **Enabled** checkbox on any row to include/exclude it from daily runs."
    )

    # Search / filter controls
    col_search, col_region, col_show = st.columns([3, 2, 2])
    with col_search:
        search_q = st.text_input(
            "Search city / IATA", placeholder="e.g. Paris or CDG", key="dest_search"
        )
    with col_region:
        with SessionFactory() as s:
            regions = sorted(
                {d.region for d in s.query(Destination).all() if d.region},
                key=str,
            )
        region_filter = st.selectbox(
            "Region", ["All regions", *regions], key="dest_region"
        )
    with col_show:
        show_filter = st.selectbox(
            "Show",
            ["All", "Enabled only", "Disabled only", "Custom only"],
            key="dest_show",
        )

    with SessionFactory() as s:
        query = s.query(Destination).order_by(Destination.city)
        if search_q:
            like = f"%{search_q}%"
            from sqlalchemy import or_

            query = query.filter(
                or_(
                    Destination.city.ilike(like),
                    Destination.iata_code.ilike(like),
                    Destination.country.ilike(like),
                )
            )
        if region_filter != "All regions":
            query = query.filter(Destination.region == region_filter)
        if show_filter == "Enabled only":
            query = query.filter(Destination.enabled.is_(True))
        elif show_filter == "Disabled only":
            query = query.filter(Destination.enabled.is_(False))
        elif show_filter == "Custom only":
            query = query.filter(Destination.is_custom.is_(True))
        filtered: list[Destination] = query.all()

        # Extract scalar values before session closes.
        table_rows = [
            {
                "IATA": d.iata_code,
                "City": d.city or "",
                "Country": d.country or "",
                "Region": d.region or "",
                "Custom": bool(d.is_custom),
                "Enabled": bool(d.enabled),
            }
            for d in filtered
        ]

    if not table_rows:
        st.info("No destinations match the current filter.")
    else:
        import pandas as pd

        df = pd.DataFrame(table_rows)
        edited = st.data_editor(
            df,
            column_config={
                "IATA": st.column_config.TextColumn(
                    "IATA", disabled=True, width="small"
                ),
                "City": st.column_config.TextColumn("City", disabled=True),
                "Country": st.column_config.TextColumn("Country", disabled=True),
                "Region": st.column_config.TextColumn("Region", disabled=True),
                "Custom": st.column_config.CheckboxColumn(
                    "Custom", disabled=True, width="small"
                ),
                "Enabled": st.column_config.CheckboxColumn("Enabled", width="small"),
            },
            hide_index=True,
            use_container_width=True,
            key="dest_pool_editor",
        )

        changed = df[df["Enabled"] != edited["Enabled"]]
        if not changed.empty:
            with SessionFactory() as s:
                for _, row in changed.iterrows():
                    dest = s.get(Destination, row["IATA"])
                    if dest is not None:
                        dest.enabled = bool(edited.loc[row.name, "Enabled"])
                s.commit()
            n = len(changed)
            st.success(f"Updated {n} destination(s).")
            st.rerun()

    # ── Section 2: Add Custom Destination ─────────────────────────────────────
    st.divider()
    st.subheader("Add Custom Destination")
    st.caption(
        "Add an airport that is not in the built-in list. "
        "Provide the IATA code and city name; the app will look up per-diem rates automatically."
    )

    with st.form("add_custom_dest_form"):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            new_iata = (
                st.text_input("IATA code *", max_chars=4, placeholder="e.g. NRT")
                .strip()
                .upper()
            )
        with fc2:
            new_city = st.text_input("City *", placeholder="e.g. Tokyo").strip()
        with fc3:
            new_country = st.text_input("Country", placeholder="e.g. Japan").strip()

        fc4, fc5 = st.columns(2)
        with fc4:
            new_region = st.text_input(
                "Region", placeholder="e.g. Asia Pacific"
            ).strip()
        with fc5:
            new_enabled = st.checkbox("Enable immediately", value=True)

        add_submitted = st.form_submit_button("Add Destination", type="primary")

    # Per diem preview — shown outside the form so it updates as the user types.
    if new_city:
        match = fuzzy_match_per_diem(new_city)
        if match:
            st.success(
                f"Per diem match: **{match.city}** ({match.state_or_country}) — "
                f"lodging ${match.lodging_usd:.0f}/night, M&IE ${match.mie_usd:.0f}/day "
                f"(similarity {match.score:.0%})"
            )
        else:
            st.warning(
                f"⚠️ No per diem match found for **{new_city}**. "
                "This destination will use the regional fallback rate when evaluated."
            )

    if add_submitted:
        errors: list[str] = []
        if not new_iata:
            errors.append("IATA code is required.")
        elif len(new_iata) < 2 or len(new_iata) > 4:
            errors.append("IATA code must be 2-4 characters.")
        if not new_city:
            errors.append("City name is required.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            with SessionFactory() as s:
                existing = s.get(Destination, new_iata)
                if existing is not None:
                    st.error(
                        f"IATA code **{new_iata}** already exists "
                        f"({'custom' if existing.is_custom else 'seed'} destination: "
                        f"{existing.city}, {existing.country}). "
                        "To change its settings, use the pool table above."
                    )
                else:
                    s.add(
                        Destination(
                            iata_code=new_iata,
                            city=new_city,
                            country=new_country or None,
                            region=new_region or None,
                            enabled=new_enabled,
                            is_custom=True,
                            excluded=False,
                            user_favorited=False,
                            user_booked=False,
                            query_count=0,
                            times_selected=0,
                        )
                    )
                    s.commit()
                    st.success(
                        f"✅ Added **{new_iata}** ({new_city}) to the destination pool."
                    )
                    st.rerun()

    # ── Section 3: CSV Bulk Import ─────────────────────────────────────────────
    st.divider()
    st.subheader("CSV Bulk Import")
    st.caption(
        "Upload a CSV file to add multiple destinations at once. "
        "Required column: **iata**. Optional: city, country, region."
    )

    with st.expander("CSV format example"):
        st.code(
            "iata,city,country,region\n"
            "NRT,Tokyo,Japan,Asia Pacific\n"
            "GRU,São Paulo,Brazil,South America\n"
            "CPT,Cape Town,South Africa,Africa",
            language="csv",
        )

    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], key="dest_csv_upload")

    if uploaded_file is not None:
        content = uploaded_file.read().decode("utf-8", errors="replace")
        preview: CsvImportPreview = parse_destination_csv(content)

        if preview.parse_error:
            st.error(f"Could not parse CSV: {preview.parse_error}")
        else:
            st.markdown(
                f"**Preview:** {preview.valid_count} valid rows "
                f"({preview.matched_count} with per-diem match, "
                f"{preview.unmatched_count} without), "
                f"{preview.error_count} error rows."
            )

            import pandas as pd

            preview_data = []
            for row in preview.rows:
                status = ""
                if row.error:
                    status = f"❌ {row.error}"
                elif row.has_per_diem:
                    pd_match = row.per_diem_match
                    status = f"✅ Per diem: {pd_match.city} (${pd_match.lodging_usd:.0f}/night)"  # type: ignore[union-attr]
                else:
                    status = "⚠️ No per diem match (will use fallback)"
                preview_data.append(
                    {
                        "IATA": row.iata,
                        "City": row.city,
                        "Country": row.country,
                        "Region": row.region,
                        "Status": status,
                    }
                )
            st.dataframe(
                pd.DataFrame(preview_data), hide_index=True, use_container_width=True
            )

            valid_rows = [r for r in preview.rows if r.is_valid]
            if valid_rows:
                if st.button(
                    f"Import {len(valid_rows)} destination(s)",
                    type="primary",
                    key="csv_import_confirm",
                ):
                    added = 0
                    skipped = 0
                    with SessionFactory() as s:
                        for row in valid_rows:
                            existing = s.get(Destination, row.iata)
                            if existing is not None:
                                skipped += 1
                                continue
                            s.add(
                                Destination(
                                    iata_code=row.iata,
                                    city=row.city or None,
                                    country=row.country or None,
                                    region=row.region or None,
                                    enabled=True,
                                    is_custom=True,
                                    excluded=False,
                                    user_favorited=False,
                                    user_booked=False,
                                    query_count=0,
                                    times_selected=0,
                                )
                            )
                            added += 1
                        s.commit()
                    msg = f"✅ Imported {added} destination(s)."
                    if skipped:
                        msg += f" Skipped {skipped} already-existing IATA code(s)."
                    st.success(msg)
                    st.rerun()
            else:
                st.info("No valid rows to import.")


# ── Exclusion List ─────────────────────────────────────────────────────────────


def _exclusion_list() -> None:
    st.title("Exclusion List")

    with SessionFactory() as s:
        excluded: list[Destination] = (
            s.query(Destination)
            .filter(Destination.excluded.is_(True))
            .order_by(desc(Destination.excluded_at))
            .all()
        )
        excluded_data = [
            {
                "iata": d.iata_code,
                "label": f"{d.city or d.iata_code}, {d.country or ''} ({d.iata_code})",
                "excluded_at": d.excluded_at.strftime("%Y-%m-%d")
                if d.excluded_at
                else "—",
                "note": d.exclusion_note or "",
            }
            for d in excluded
        ]
        available: list[Destination] = (
            s.query(Destination)
            .filter(Destination.excluded.is_(False))
            .order_by(Destination.city)
            .all()
        )
        dest_options = {
            f"{d.city or d.iata_code} ({d.iata_code})": d.iata_code for d in available
        }

    # Add exclusion
    st.subheader("Add Exclusion")
    if dest_options:
        with st.form("add_exclusion_form"):
            selected_label = st.selectbox("Destination", list(dest_options.keys()))
            note = st.text_input("Note (optional)")
            if st.form_submit_button("Exclude Destination"):
                iata = dest_options[selected_label]
                with SessionFactory() as s:
                    dest = s.get(Destination, iata)
                    if dest:
                        dest.excluded = True
                        dest.excluded_at = datetime.now(UTC)
                        dest.exclusion_note = note.strip() or None
                        s.commit()
                st.success(f"Excluded {selected_label}.")
                st.rerun()
    else:
        st.info("No evaluated destinations available to exclude yet.")

    # Current exclusions
    st.subheader(f"Currently Excluded ({len(excluded_data)})")
    if not excluded_data:
        st.info("No destinations are currently excluded.")
    else:
        for row in excluded_data:
            c1, c2 = st.columns([5, 1])
            with c1:
                note_str = f" — _{row['note']}_" if row["note"] else ""
                st.write(
                    f"**{row['label']}**  ·  excluded {row['excluded_at']}{note_str}"
                )
            with c2:
                if st.button("Restore", key=f"restore_{row['iata']}"):
                    with SessionFactory() as s:
                        d = s.get(Destination, row["iata"])
                        if d:
                            d.excluded = False
                            d.excluded_at = None
                            d.exclusion_note = None
                            s.commit()
                    st.rerun()

        st.divider()
        if st.button("Clear All Exclusions", type="secondary"):
            with SessionFactory() as s:
                for row in excluded_data:
                    d = s.get(Destination, row["iata"])
                    if d:
                        d.excluded = False
                        d.excluded_at = None
                        d.exclusion_note = None
                s.commit()
            st.success("All exclusions cleared.")
            st.rerun()


# ── Trip History ───────────────────────────────────────────────────────────────

_PAGE_SIZE = 50


def _trip_history() -> None:
    st.title("Trip History")

    # ── Handle ?action=mark_booked&trip_id=N from email footer link ───────────
    params = st.query_params
    if params.get("action") == "mark_booked":
        raw_id = params.get("trip_id", "")
        try:
            email_trip_id = int(raw_id)
        except (ValueError, TypeError):
            email_trip_id = None
        if email_trip_id is not None:
            with SessionFactory() as s:
                trip_row = s.get(Trip, email_trip_id)
                if trip_row and not trip_row.booked:
                    d = s.get(Destination, trip_row.destination_iata)
                    label = (
                        f"{d.city}, {d.country} ({trip_row.destination_iata})"
                        if d
                        else trip_row.destination_iata
                    )
                    st.success(
                        f"✅ Ready to mark **{label}** (Trip #{email_trip_id}) as booked."
                    )
                    if st.button("Confirm — Mark as Booked", key="email_confirm_book"):
                        trip_row.booked = True
                        trip_row.booked_at = datetime.now(UTC)
                        dest = s.get(Destination, trip_row.destination_iata)
                        if dest:
                            dest.user_booked = True
                        s.commit()
                        st.query_params.clear()
                        st.success("Marked as booked!")
                        st.rerun()
                elif trip_row and trip_row.booked:
                    st.info(f"Trip #{email_trip_id} is already marked as booked.")
                    st.query_params.clear()
                else:
                    st.warning(f"Trip #{email_trip_id} not found.")
                    st.query_params.clear()
            st.divider()

    with SessionFactory() as s:
        total = s.query(Trip).count()

    if total == 0:
        st.info("No trip history yet.")
        _log_past_trip_section()
        return

    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page_num = int(
        st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
    )
    offset = (page_num - 1) * _PAGE_SIZE

    with SessionFactory() as s:
        trips: list[Trip] = (
            s.query(Trip)
            .order_by(desc(Trip.run_date), Trip.rank)
            .offset(offset)
            .limit(_PAGE_SIZE)
            .all()
        )
        trip_data: list[tuple[Trip, str, str]] = []
        for t in trips:
            d = s.get(Destination, t.destination_iata)
            city = d.city if d else t.destination_iata
            country = d.country if d else ""
            trip_data.append((t, city, country))

    rows = []
    for t, city, country in trip_data:
        booked_icon = "✅" if t.booked else ("✈️" if t.selected else "")
        dep_iata = getattr(t, "departure_iata", None)
        if dep_iata:
            dep_city = get_airport_city(dep_iata)
            dep_col = dep_iata if dep_city == dep_iata else f"{dep_city} ({dep_iata})"
        else:
            dep_col = "—"
        rows.append(
            {
                "ID": t.id,
                "Date": str(t.run_date),
                "Destination": f"{city}, {country}",
                "Departs": dep_col,
                "Rank": t.rank if t.rank is not None else "—",
                "Status": booked_icon,
                "Flights": f"${t.flight_cost_usd:,.0f}",
                "Hotel": f"${t.hotel_cost_usd:,.0f}",
                "Car": f"${t.car_cost_usd:,.0f}",
                "Food": f"${t.food_cost_usd:,.0f}",
                "Total": f"${t.total_cost_usd:,.0f}",
                "Manual": "📝" if t.manually_logged else "",
            }
        )

    lo = offset + 1
    hi = min(offset + _PAGE_SIZE, total)
    st.caption(
        f"Showing {lo}-{hi} of {total} trips  |  Page {page_num} of {total_pages}"
        "  ·  ✅ = booked  ✈️ = selected  📝 = manually logged"
    )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # ── Action panel: pick a trip by ID ───────────────────────────────────────
    st.divider()
    st.subheader("Trip Actions")
    trip_ids = [t.id for t, _, _ in trip_data]
    selected_id = st.selectbox(
        "Select trip",
        options=trip_ids,
        format_func=lambda tid: next(
            (
                f"#{tid} — {city}, {country} ({t.run_date!s})"
                for t, city, country in trip_data
                if t.id == tid
            ),
            str(tid),
        ),
        index=None,
        placeholder="Choose a trip to act on…",
        key="action_trip_select",
    )

    if selected_id is not None:
        with SessionFactory() as s:
            action_trip = s.get(Trip, selected_id)
            action_dest = (
                s.get(Destination, action_trip.destination_iata)
                if action_trip
                else None
            )
            is_booked = action_trip.booked if action_trip else False
            is_favorited = action_dest.user_favorited if action_dest else False
            is_excluded = action_dest.excluded if action_dest else False
            dest_label = (
                f"{action_dest.city}, {action_dest.country}"
                if action_dest
                else (action_trip.destination_iata if action_trip else "?")
            )
            action_dep_iata = (
                getattr(action_trip, "departure_iata", None) if action_trip else None
            )
            # Extract primitives for chart (must be inside session context)
            chart_iata = action_trip.destination_iata if action_trip else None
            chart_run_date_str = str(action_trip.run_date) if action_trip else None
            chart_cost = action_trip.total_cost_usd if action_trip else None

        if action_dep_iata:
            dep_city = get_airport_city(action_dep_iata)
            dep_detail = (
                action_dep_iata
                if dep_city == action_dep_iata
                else f"{dep_city} ({action_dep_iata})"
            )
            st.caption(f"Departing from: {dep_detail}")
        else:
            st.caption("Departing from: —")

        col1, col2, col3 = st.columns(3)
        with col1:
            if is_booked:
                st.success(f"✅ {dest_label} already booked")
                if st.button("Unmark as Booked", key="action_unbook"):
                    with SessionFactory() as s:
                        t2 = s.get(Trip, selected_id)
                        if t2:
                            t2.booked = False
                            t2.booked_at = None
                        d2 = s.get(Destination, t2.destination_iata) if t2 else None
                        if d2:
                            d2.user_booked = False
                        s.commit()
                    st.rerun()
            else:
                if st.button("✅ Mark as Booked", key="action_book"):
                    with SessionFactory() as s:
                        t2 = s.get(Trip, selected_id)
                        if t2:
                            t2.booked = True
                            t2.booked_at = datetime.now(UTC)
                        d2 = s.get(Destination, t2.destination_iata) if t2 else None
                        if d2:
                            d2.user_booked = True
                        s.commit()
                    st.success(f"✅ {dest_label} marked as booked!")
                    st.rerun()

        with col2:
            fav_label = (
                "★ Unfavorite destination" if is_favorited else "☆ Favorite destination"
            )
            if st.button(fav_label, key="action_fav"):
                with SessionFactory() as s:
                    d2 = (
                        s.get(Destination, action_dest.iata_code)
                        if action_dest
                        else None
                    )
                    if d2:
                        d2.user_favorited = not is_favorited
                        s.commit()
                st.rerun()

        with col3:
            excl_label = (
                "↩ Restore destination" if is_excluded else "🚫 Exclude destination"
            )
            if st.button(excl_label, key="action_excl"):
                with SessionFactory() as s:
                    d2 = (
                        s.get(Destination, action_dest.iata_code)
                        if action_dest
                        else None
                    )
                    if d2:
                        if is_excluded:
                            d2.excluded = False
                            d2.excluded_at = None
                            d2.exclusion_note = None
                        else:
                            d2.excluded = True
                            d2.excluded_at = datetime.now(UTC)
                            d2.exclusion_note = "Excluded from Trip History"
                        s.commit()
                st.rerun()

        # ── Price history chart for selected trip ─────────────────────────────
        if chart_iata and chart_run_date_str is not None and chart_cost is not None:
            st.subheader("Price History")
            history_chart = get_cached_chart(
                destination_iata=chart_iata,
                destination_name=dest_label,
                today_cost=chart_cost,
                run_date_str=chart_run_date_str,
            )
            if history_chart:
                st.image(
                    history_chart,
                    caption="Price history and recent daily picks",
                    use_container_width=True,
                )
            else:
                st.caption("📊 Not enough history yet to show price trends.")

    # ── Log a Past Trip ───────────────────────────────────────────────────────
    st.divider()
    _log_past_trip_section()

    # ── Mark Destination as Booked (bulk) ─────────────────────────────────────
    st.divider()
    st.subheader("Mark Destination as Booked")
    st.caption(
        "Mark a destination as booked to optionally exclude it from future picks "
        "(toggle 'Exclude booked destinations' in Preferences → Filters)."
    )
    with SessionFactory() as s:
        all_dests: list[Destination] = (
            s.query(Destination).order_by(Destination.iata_code).all()
        )
        booked_iatas = {d.iata_code for d in all_dests if d.user_booked}
        dest_labels = {
            d.iata_code: f"{d.city or d.iata_code}, {d.country or ''} ({d.iata_code})"
            for d in all_dests
        }

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Book a destination**")
        book_iata = st.selectbox(
            "Destination",
            options=[i for i in dest_labels if i not in booked_iatas],
            format_func=lambda k: dest_labels[k],
            key="book_dest_select",
            index=None,
            placeholder="Select a destination…",
        )
        if st.button("Mark as Booked", key="bulk_book_btn") and book_iata:
            with SessionFactory() as s:
                d = s.get(Destination, book_iata)
                if d:
                    d.user_booked = True
                    s.commit()
            st.success(f"{dest_labels[book_iata]} marked as booked.")
            st.rerun()

    with col_b:
        st.markdown("**Currently booked**")
        if booked_iatas:
            unbook_iata = st.selectbox(
                "Booked destination",
                options=sorted(booked_iatas),
                format_func=lambda k: dest_labels.get(k, k),
                key="unbook_dest_select",
            )
            if st.button("Unmark as Booked", key="bulk_unbook_btn") and unbook_iata:
                with SessionFactory() as s:
                    d = s.get(Destination, unbook_iata)
                    if d:
                        d.user_booked = False
                        s.commit()
                st.success(f"{dest_labels.get(unbook_iata, unbook_iata)} unmarked.")
                st.rerun()
        else:
            st.info("No destinations currently marked as booked.")


def _log_past_trip_section() -> None:
    """Form to manually log a past trip (booked=True, manually_logged=True)."""
    st.subheader("📝 Log a Past Trip")
    st.caption("Record a trip you've already taken or booked outside of trip-a-day.")

    with SessionFactory() as s:
        all_dests: list[Destination] = (
            s.query(Destination).order_by(Destination.city).all()
        )
    dest_options = [d.iata_code for d in all_dests]
    dest_fmt = {
        d.iata_code: f"{d.city or d.iata_code}, {d.country or ''} ({d.iata_code})"
        for d in all_dests
    }

    with st.form("log_past_trip_form"):
        log_iata = st.selectbox(
            "Destination",
            options=dest_options,
            format_func=lambda k: dest_fmt.get(k, k),
            index=None,
            placeholder="Search by city or IATA…",
            key="log_dest_select",
        )
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            log_depart = st.date_input("Departure date", value=None, key="log_depart")
        with col_d2:
            log_return = st.date_input("Return date", value=None, key="log_return")
        log_flights = st.number_input(
            "Flight cost (USD, optional)",
            min_value=0.0,
            value=0.0,
            step=10.0,
            key="log_flights",
        )
        st.text_area("Notes (optional)", key="log_notes", height=80)
        submitted = st.form_submit_button("Log Trip")

    if submitted:
        if not log_iata:
            st.error("Please select a destination.")
        elif not log_depart or not log_return:
            st.error("Please select both departure and return dates.")
        elif log_return <= log_depart:
            st.error("Return date must be after departure date.")
        else:
            with SessionFactory() as s:
                nights = (log_return - log_depart).days
                new_trip = Trip(
                    run_date=date.today(),
                    destination_iata=log_iata,
                    departure_date=log_depart,
                    return_date=log_return,
                    flight_cost_usd=log_flights,
                    hotel_cost_usd=0.0,
                    car_cost_usd=0.0,
                    food_cost_usd=0.0,
                    total_cost_usd=log_flights,
                    distance_miles=0.0,
                    rank=None,
                    selected=False,
                    notified=False,
                    car_cost_is_estimate=False,
                    booked=True,
                    booked_at=datetime.now(UTC),
                    manually_logged=True,
                )
                s.add(new_trip)
                dest = s.get(Destination, log_iata)
                if dest:
                    dest.user_booked = True
                s.commit()
            label = dest_fmt.get(log_iata, log_iata)
            st.success(
                f"✅ Logged {nights}-night trip to {label} "
                f"({log_depart} → {log_return})."
            )
            st.rerun()


# ── routing ────────────────────────────────────────────────────────────────────

if _PAGE == "Dashboard":
    _dashboard()
elif _PAGE == "Preferences":
    _preferences()
elif _PAGE == "Destinations":
    _destinations()
elif _PAGE == "Exclusion List":
    _exclusion_list()
elif _PAGE == "Trip History":
    _trip_history()
