"""Streamlit web UI for trip-a-day.

Pages:
  Dashboard     — last run status, API usage, Trip of the Day card, Run Now button
  Preferences   — editable form for all user preferences
  Exclusion List — view / add / restore excluded destinations
  Trip History  — paginated table of all evaluated trip candidates

Usage:
    streamlit run ui.py
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from datetime import UTC, date, datetime, time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import streamlit as st
from sqlalchemy import desc

from trip_a_day.db import (
    ApiUsage,
    Destination,
    RunLog,
    SessionFactory,
    Trip,
    init_db,
    seed_preferences,
)
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
    ["Dashboard", "Preferences", "Exclusion List", "Trip History"],
    label_visibility="collapsed",
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


def _dashboard() -> None:
    st.title("Dashboard")

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

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Last Run")
        if last_run:
            icons = {"success": "✅", "partial": "⚠️", "failed": "❌"}
            icon = icons.get(last_run.status, "❓")
            st.metric("Status", f"{icon} {last_run.status.capitalize()}")
            st.write(f"**When:** {last_run.run_at.strftime('%Y-%m-%d %H:%M')} UTC")
            st.write(f"**Triggered by:** {last_run.triggered_by}")
            st.write(f"**Candidates evaluated:** {last_run.destinations_evaluated}")
            if last_run.duration_seconds is not None:
                st.write(f"**Duration:** {last_run.duration_seconds:.1f}s")
            if last_run.error_message:
                st.error(last_run.error_message)
            if getattr(last_run, "filter_fallback", False):
                st.warning(
                    "Filter fallback triggered — destination filters produced no "
                    "matches and the run used the unfiltered pool. "
                    "Consider relaxing your filters in Preferences."
                )
        else:
            st.info("No runs yet. Click **Run Now** below to get started.")

    with col2:
        st.subheader("API Usage Today")
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

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("✈️ Flights", f"${winner.flight_cost_usd:,.0f}")
        c2.metric("🏨 Hotel *", f"${winner.hotel_cost_usd:,.0f}")
        c3.metric("🚗 Car *", f"${winner.car_cost_usd:,.0f}")
        c4.metric("🍽️ Food *", f"${winner.food_cost_usd:,.0f}")
        c5.metric("💰 Total", f"${winner.total_cost_usd:,.0f}")

        st.caption(
            "* Hotel and food are government per diem estimates (GSA / State Dept); "
            "car rental is a regional average. Only flight prices are live quotes."
        )

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

    with st.form("preferences_form"):
        st.subheader("Trip Configuration")
        home_airport = st.text_input(
            "Home Airport (IATA code)", value=prefs.get("home_airport", "HSV")
        )
        col1, col2, col3 = st.columns(3)
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
        advance_days = col3.number_input(
            "Days ahead to search",
            min_value=1,
            max_value=365,
            value=_int("advance_days", 7),
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
        cx, cy, cz = st.columns(3)
        direct_only = cx.checkbox(
            "Direct flights only", value=_bool("direct_flights_only")
        )
        car_required = cy.checkbox(
            "Car rental required", value=_bool("car_rental_required")
        )
        min_stars = cz.number_input(
            "Min hotel stars",
            min_value=1,
            max_value=5,
            value=_int("min_hotel_stars", 4),
        )

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
            "Enter one location per line as `lat,lon` (e.g. `48.8566,2.3522` for Paris). "
            "Only destinations within the radius below will be considered."
        )
        raw_locs = _parse_json_pref(prefs, "favorite_locations")
        fav_locs_text = st.text_area(
            "Favorite locations (lat,lon — one per line)",
            value="\n".join(
                f"{loc['lat']},{loc['lon']}"
                for loc in raw_locs
                if isinstance(loc, dict)
            ),
            height=80,
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

        st.subheader("Notifications")
        raw_emails = prefs.get("notification_emails", "[]")
        try:
            parsed = json.loads(raw_emails)
            emails_str = ", ".join(parsed) if isinstance(parsed, list) else ""
        except (json.JSONDecodeError, TypeError):
            emails_str = ""
        notification_emails = st.text_input(
            "Notification emails (comma-separated)",
            value=emails_str,
            help="Leave blank to print the trip to stdout instead of emailing.",
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
            set_pref(s, "advance_days", str(int(advance_days)))
            set_pref(s, "num_adults", str(int(num_adults)))
            set_pref(s, "num_children", str(int(num_children)))
            set_pref(s, "num_rooms", str(int(num_rooms)))
            set_pref(s, "direct_flights_only", "true" if direct_only else "false")
            set_pref(s, "car_rental_required", "true" if car_required else "false")
            set_pref(s, "min_hotel_stars", str(int(min_stars)))
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
            # Parse fav_locs_text: "lat,lon" lines -> [{"lat":..., "lon":...}]
            parsed_locs = []
            for line in fav_locs_text.splitlines():
                parts = line.strip().split(",")
                if len(parts) == 2:
                    with contextlib.suppress(ValueError):
                        parsed_locs.append(
                            {"lat": float(parts[0]), "lon": float(parts[1])}
                        )
            set_pref(s, "favorite_locations", json.dumps(parsed_locs))
            set_pref(s, "favorite_radius_miles", str(int(fav_radius)))
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
            set_pref(s, "notification_emails", json.dumps(new_emails))
            set_pref(s, "scheduled_run_time", run_time_val.strftime("%H:%M"))
            s.commit()
        st.success("Preferences saved.")


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

    with SessionFactory() as s:
        total = s.query(Trip).count()

    if total == 0:
        st.info("No trip history yet.")
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
        rows = []
        for t in trips:
            d = s.get(Destination, t.destination_iata)
            city = d.city if d else t.destination_iata
            country = d.country if d else ""
            rows.append(
                {
                    "Date": str(t.run_date),
                    "Destination": f"{city}, {country}",
                    "Rank": t.rank if t.rank is not None else "—",
                    "Selected": "🏆" if t.selected else "",
                    "Flights": f"${t.flight_cost_usd:,.0f}",
                    "Hotel": f"${t.hotel_cost_usd:,.0f}",
                    "Car": f"${t.car_cost_usd:,.0f}",
                    "Food": f"${t.food_cost_usd:,.0f}",
                    "Total": f"${t.total_cost_usd:,.0f}",
                }
            )

    lo = offset + 1
    hi = min(offset + _PAGE_SIZE, total)
    st.caption(
        f"Showing {lo}-{hi} of {total} trips  -  Page {page_num} of {total_pages}"
    )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    # ── Mark as Booked ────────────────────────────────────────────────────────
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
        if st.button("Mark as Booked") and book_iata:
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
            if st.button("Unmark as Booked") and unbook_iata:
                with SessionFactory() as s:
                    d = s.get(Destination, unbook_iata)
                    if d:
                        d.user_booked = False
                        s.commit()
                st.success(f"{dest_labels.get(unbook_iata, unbook_iata)} unmarked.")
                st.rerun()
        else:
            st.info("No destinations currently marked as booked.")


# ── routing ────────────────────────────────────────────────────────────────────

if _PAGE == "Dashboard":
    _dashboard()
elif _PAGE == "Preferences":
    _preferences()
elif _PAGE == "Exclusion List":
    _exclusion_list()
elif _PAGE == "Trip History":
    _trip_history()
