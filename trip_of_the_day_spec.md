# Trip of the Day — Project Specification

**Version:** 1.1
**Date:** 2026-04-17
**Language:** Python
**Status:** Pre-implementation

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Guiding Principles](#2-guiding-principles)
3. [Architecture Overview](#3-architecture-overview)
4. [Data Sources](#4-data-sources)
5. [Data Model](#5-data-model)
6. [Module Structure](#6-module-structure)
7. [Cost Model](#7-cost-model)
8. [Ranking & Scoring Logic](#8-ranking--scoring-logic)
9. [Notification System](#9-notification-system)
10. [User Interface](#10-user-interface)
11. [Configuration & Preferences](#11-configuration--preferences)
12. [Phased Implementation Plan](#12-phased-implementation-plan)
13. [Open Source Considerations](#13-open-source-considerations)
14. [Future Considerations (Post-Spec)](#14-future-considerations-post-spec)

---

## 1. Project Overview

**Trip of the Day** is a Python application that runs once daily, identifies the cheapest feasible weeklong trip bookable from the user's home airport, and delivers a notification email summarizing the best option along with direct links to book flights, hotels, and a rental car.

The app is designed as a personal, open source tool. Each user runs their own local instance with their own API keys and their own local database. There is no shared server, no cloud dependency, and no user data leaves the local machine (except outbound API queries and the daily email).

### Core User Story

> Every morning I receive an email describing the cheapest trip I could book today — departing anywhere from a week to up to a year in advance (configurable) — including estimated total cost broken down by flight, hotel, car, and food, with links to book each component. If I'm not interested in that destination, I click a button to exclude it from future results. I can view and manage my preferences and exclusion list from a simple desktop interface.

---

## 2. Guiding Principles

- **Free first.** No paid APIs are required in any planned phase. Paid alternatives are documented as optional upgrades.
- **On-demand and scheduled.** The app supports both manual on-demand execution and automatic daily scheduling. These are equivalent code paths — the scheduler simply calls the same entry point as a manual run.
- **API rate limit awareness.** The app tracks API call counts per day and per month and surfaces warnings in the UI and logs when approaching limits. On-demand runs count against the same limits as scheduled runs.
- **One query per day (default).** The app is not a real-time search tool. It runs once daily by default and stores results. API rate limits are a non-concern at normal usage levels, but the rate limit tracking system ensures users are informed if usage patterns change.
- **Modular by design.** Each concern (data fetching, cost calculation, ranking, notification, UI) lives in its own module so any component can be swapped without touching the rest.
- **Preferences over hardcoding.** Any value the user might reasonably want to change is stored as a preference, not a constant — even values that aren't yet exposed in the UI.
- **PoC-first phasing.** Each phase should produce a working, testable artifact before the next phase begins. No phase should require a prior phase to be refactored to proceed.
- **Architecture headroom.** The schema and module interfaces are designed to accommodate the full roadmap without requiring breaking changes as features are added.
- **Cross-platform portability.** The app is developed on macOS (VS Code) but must run without modification on Windows and Linux. All file paths use `pathlib.Path`, all line endings are LF-normalized in the repo, and OS-specific setup steps are documented separately in the README.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit UI (ui.py)                │
│  Preferences │ Exclusion List │ Trip History │ Run   │
└────────────────────────┬────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │   Scheduler / Main   │
              │    (scheduler.py)    │
              └──────────┬──────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
┌───────▼──────┐ ┌───────▼──────┐ ┌──────▼───────┐
│ Data Fetcher │ │ Cost Engine  │ │   Ranker     │
│ (fetcher.py) │ │ (costs.py)   │ │ (ranker.py)  │
└───────┬──────┘ └───────┬──────┘ └──────┬───────┘
        │                │               │
        │         ┌──────▼───────────────▼──────┐
        │         │      Database (db.py)         │
        │         │      SQLite via SQLAlchemy    │
        │         └───────────────────────────────┘
        │
┌───────▼──────────────────────────┐
│  External APIs                    │
│  - Amadeus (flights + hotels)     │
│  - Numbeo (food / cost of living) │
│  - Car cost table (local, static) │
└───────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │   Notifier           │
              │   (notifier.py)      │
              │   SendGrid email     │
              └─────────────────────┘
```

---

## 4. Data Sources

### 4.1 Amadeus for Developers (Flights + Hotels)

- **URL:** https://developers.amadeus.com
- **Account type:** Free self-service tier (no credit card required)
- **Relevant APIs:**
  - `Flight Offers Search` — returns cheapest available flights between two airports on given dates
  - `Flight Inspiration Search` — returns cheapest destinations from a given origin (key for destination discovery)
  - `Hotel List` + `Hotel Offers Search` — returns hotel options with pricing at a destination city
- **Sandbox vs. Production:** Amadeus provides a sandbox environment with realistic synthetic data. Development and testing happen entirely in sandbox. Switching to production is a single environment variable change (`AMADEUS_ENV=production`).
- **Rate limits:** Free production tier allows 2,000 API calls/month. At 1 run/day with ~5–10 API calls per run, monthly usage will be well under 400 calls. Well within limits.
- **Open source key handling:** Users register their own free Amadeus account and add `AMADEUS_API_KEY` and `AMADEUS_API_SECRET` to their local `.env` file. Keys are never committed to the repository.

### 4.2 Numbeo API (Food / Cost of Living)

- **URL:** https://www.numbeo.com/api/
- **Account type:** Free tier available
- **Usage:** Query cost-of-living index and meal cost estimates by city. Used to estimate daily food spend for a given destination.
- **Key handling:** Same `.env` pattern as Amadeus.

### 4.3 Rental Car Costs (Static Lookup Table — Phase 1)

- No viable free real-time rental car API exists at this time.
- Phase 1 uses a static regional lookup table (JSON or SQLite table) mapping world regions to an estimated daily rental rate in USD.
- The table will be bundled with the repo and can be manually updated.
- Clearly labeled as "estimated" in all output.
- **Future:** Replace with a real API (e.g., via RapidAPI car rental endpoints) once a suitable free or low-cost option is identified.

### 4.4 Optional / Future Data Sources

| Source | Purpose | Notes |
|--------|---------|-------|
| SerpApi | Google Flights/Hotels scraping | ~$50/mo, best data quality |
| Booking.com Affiliate API | Hotels | Requires affiliate approval |
| Rome2rio API | Multi-modal transport costs | Useful for airport-to-home leg |
| Google Places API | Points of interest, destination scoring | Free tier available |

---

## 5. Data Model

All tables are managed via SQLAlchemy ORM with a local SQLite database (`trip_of_the_day.db`). The database is initialized automatically on first run via a schema migration script.

### 5.1 `preferences`

Stores all user-configurable settings as key-value pairs. This allows new preferences to be added in future phases without schema migrations.

| Column | Type | Description |
|--------|------|-------------|
| `key` | TEXT PRIMARY KEY | Preference name (e.g., `home_airport`) |
| `value` | TEXT | Preference value (serialized as string or JSON) |
| `updated_at` | DATETIME | Last modified timestamp |

**Default preference keys (Phase 1):**

| Key | Default Value | Description |
|-----|--------------|-------------|
| `home_airport` | `HSV` | IATA code of departure airport |
| `trip_length_nights` | `7` | Duration of trip in nights |
| `advance_days` | `7` | How many days ahead to search for departure (min 7, max 365) |
| `num_adults` | `2` | Number of adult travelers |
| `num_children` | `2` | Number of child travelers |
| `direct_flights_only` | `true` | Require nonstop flights |
| `min_hotel_stars` | `4` | Minimum hotel star rating |
| `car_rental_required` | `true` | Include rental car in trip estimate |
| `notification_emails` | `"[]"` | JSON array of recipient email addresses for daily notification |
| `ranking_strategy` | `cheapest_then_farthest` | Primary sort strategy |
| `search_radius_miles` | `0` | Radius around home for alternate airports (0 = home only) |
| `region_filter` | `null` | JSON list of allowed regions, null = worldwide |

### 5.2 `destinations`

Stores all destination candidates ever considered, with metadata for ranking and filtering.

| Column | Type | Description |
|--------|------|-------------|
| `iata_code` | TEXT PRIMARY KEY | Airport IATA code |
| `city` | TEXT | City name |
| `country` | TEXT | Country name |
| `region` | TEXT | World region (e.g., `Western Europe`, `Southeast Asia`) |
| `latitude` | REAL | For distance calculations |
| `longitude` | REAL | For distance calculations |
| `excluded` | BOOLEAN | Whether user has excluded this destination |
| `excluded_at` | DATETIME | When exclusion was set |
| `exclusion_note` | TEXT | Optional user note on why excluded |

### 5.3 `trips`

Stores each daily trip result. One record per day per candidate destination evaluated.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PRIMARY KEY |  |
| `run_date` | DATE | Date this result was generated |
| `destination_iata` | TEXT | FK → `destinations.iata_code` |
| `departure_date` | DATE | Outbound flight date |
| `return_date` | DATE | Return flight date |
| `flight_cost_usd` | REAL | Round-trip flight cost (all travelers) |
| `hotel_cost_usd` | REAL | Total hotel cost (all nights, all rooms) |
| `car_cost_usd` | REAL | Total rental car cost (estimated or real) |
| `food_cost_usd` | REAL | Estimated food cost (all travelers, all days) |
| `total_cost_usd` | REAL | Sum of all above |
| `distance_miles` | REAL | Great-circle distance from home airport |
| `flight_booking_url` | TEXT | Direct link to book flights |
| `hotel_booking_url` | TEXT | Direct link to book hotel |
| `car_booking_url` | TEXT | Direct link to book car (or search page) |
| `raw_flight_data` | TEXT | JSON blob of raw Amadeus flight response |
| `raw_hotel_data` | TEXT | JSON blob of raw Amadeus hotel response |
| `rank` | INTEGER | Final rank among candidates for that day (1 = best) |
| `selected` | BOOLEAN | Whether this was the trip-of-the-day (rank = 1) |
| `notified` | BOOLEAN | Whether email was sent for this trip |
| `car_cost_is_estimate` | BOOLEAN | True if car cost came from lookup table |

### 5.4 `run_log`

Tracks each daily execution for debugging and history.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PRIMARY KEY |  |
| `run_at` | DATETIME | When the run started |
| `status` | TEXT | `success`, `partial`, `failed` |
| `triggered_by` | TEXT | `scheduler` or `manual` |
| `destinations_evaluated` | INTEGER | How many destinations were scored |
| `winner_trip_id` | INTEGER | FK → `trips.id` |
| `error_message` | TEXT | If failed, error details |
| `duration_seconds` | REAL | Total runtime |
| `api_calls_amadeus` | INTEGER | Amadeus API calls made this run |
| `api_calls_numbeo` | INTEGER | Numbeo API calls made this run |

### 5.5 `api_usage`

Tracks cumulative API usage for rate limit monitoring. One row per API per calendar day.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PRIMARY KEY |  |
| `api_name` | TEXT | `amadeus`, `numbeo`, `sendgrid` |
| `usage_date` | DATE | Calendar date |
| `calls_made` | INTEGER | Total calls made on this date |
| `daily_limit` | INTEGER | Known daily limit for this API (configurable) |
| `monthly_limit` | INTEGER | Known monthly limit for this API (configurable) |

**Rate limit behavior:**
- Before each API call, `fetcher.py` checks the current daily and monthly counts against known limits
- If a call would exceed a daily limit, it is skipped and a warning is logged
- The UI Dashboard displays current usage vs. limits for each API
- On-demand (manual) runs count against the same limits as scheduled runs
- Limits are stored as configurable preferences so users can update them if their API tier changes

---

## 6. Module Structure

```
trip_of_the_day/
├── main.py                  # Entry point; triggers daily run manually or via scheduler
├── scheduler.py             # APScheduler configuration; runs daily at configured time
├── fetcher.py               # All external API calls (Amadeus, Numbeo)
├── costs.py                 # Cost assembly; combines flight + hotel + car + food into CostBreakdown
├── ranker.py                # Sorts and selects the best trip from candidates
├── notifier.py              # Email composition and delivery via SendGrid
├── db.py                    # SQLAlchemy setup, ORM models, DB initialization
├── preferences.py           # Read/write preference helpers
├── ui.py                    # Streamlit UI (preferences editor, history, exclusion list)
├── car_rates.json           # Static regional car rental rate table
├── .env.example             # Template showing required environment variables
├── .gitignore               # Excludes .env, *.db, __pycache__, etc.
├── requirements.txt         # Pinned dependencies
├── README.md                # Setup and usage guide
└── tests/
    ├── test_costs.py
    ├── test_ranker.py
    ├── test_fetcher.py      # Uses Amadeus sandbox; no mocking needed for basic tests
    └── test_db.py
```

### Module Responsibilities

**`fetcher.py`**
- `get_cheapest_destinations(origin_iata, date, n=20)` — calls Amadeus Flight Inspiration Search
- `get_flight_offers(origin, destination, depart_date, return_date, adults, children)` — calls Amadeus Flight Offers Search
- `get_hotel_offers(city_code, checkin, checkout, adults, rooms)` — calls Amadeus Hotel Search
- `get_food_cost(city, country, days, people)` — calls Numbeo; returns estimated food spend
- All functions return typed dataclasses, never raw API responses directly
- All functions check `api_usage` table before executing; skip and warn if daily/monthly limit would be exceeded
- All successful calls increment the `api_usage` counter for that API and date

**`costs.py`**
- `CostBreakdown` dataclass: `{flights, hotel, car, food, total, car_is_estimate}`
- `build_cost_breakdown(flight_offer, hotel_offer, car_region, food_estimate)` — assembles and sums
- `lookup_car_cost(region, days)` — reads `car_rates.json`, returns estimate

**`ranker.py`**
- `rank_trips(candidates: List[TripCandidate], strategy: str)` — returns sorted list
- Phase 1 strategy: sort ascending by `total_cost_usd`, break exact ties by `distance_miles` descending
- Strategy is passed in as a string so new strategies can be added without changing the ranker's interface

**`notifier.py`**
- `send_trip_notification(trip: Trip, prefs: Preferences)` — single public function
- Reads `notification_emails` preference (JSON list); sends to all configured addresses
- Composes HTML email with trip summary, cost breakdown table, booking links
- Delivers via SendGrid API
- If SendGrid key is missing, falls back to plain-text stdout (useful during development)

**`db.py`**
- SQLAlchemy engine and session factory
- ORM class definitions matching the data model above
- `init_db()` — creates tables if not present; safe to call on every startup
- `seed_preferences()` — inserts default preference values if not already present

**`preferences.py`**
- `get(key)`, `set(key, value)`, `get_all()` — thin wrappers over the `preferences` table
- Type coercion helpers (string storage → typed return values)

**`ui.py`** (Streamlit)
- Page: **Dashboard** — last trip result, run status, "Run Now" button
- Page: **Preferences** — editable form for all preference keys
- Page: **Exclusion List** — table of excluded destinations with restore button
- Page: **Trip History** — searchable log of all past daily results

---

## 7. Cost Model

### Formula

```
total_cost = flight_cost + hotel_cost + car_cost + food_cost
```

All costs are denominated in USD. All costs represent the full trip for all travelers.

### Component Definitions

| Component | Scope | Source | Notes |
|-----------|-------|--------|-------|
| `flight_cost` | Round-trip, all passengers | Amadeus Flight Offers | Lowest available nonstop fare |
| `hotel_cost` | All nights, all rooms needed | Amadeus Hotel Offers | Lowest available 4-star+ rate |
| `car_cost` | All days, one vehicle | Static table (Phase 1) | Flagged as estimate |
| `food_cost` | All days, all travelers | Numbeo city data | Based on mid-range restaurant cost × meals × people |

### Storage

Costs are stored **per component** in the `trips` table (never just the total). This enables future features like per-category filtering, user-weighted priority scoring, and "cheapest flights regardless of hotel" queries without any schema changes.

### Estimation Transparency

Any component that uses an estimate rather than a live quote is flagged in both the database (`car_cost_is_estimate`) and in the notification email, so the user knows what's real vs. approximate.

---

## 8. Ranking & Scoring Logic

### Phase 1 Strategy: `cheapest_then_farthest`

1. Sort all valid candidates ascending by `total_cost_usd`
2. On exact penny tie (extremely rare): sort descending by `distance_miles`
3. The candidate at rank 1 is the Trip of the Day

### Validity Filter (applied before ranking)

A candidate is excluded from ranking if:
- Its destination city is on the user's exclusion list
- No hotel meeting the minimum star rating was found
- No nonstop flight was found (when `direct_flights_only = true`)
- Any required cost component could not be retrieved

### Future Ranking Strategies (architecture accommodates these already)

- `farthest_then_cheapest` — maximize distance, use price as tiebreaker
- `cheapest_within_region` — filter to user-preferred regions first
- `exclude_previously_selected` — remove destinations that have already been Trip of the Day
- `random` — random selection from valid candidates for variety
- `weighted` — user-defined weights per cost category
- `favorite_proximity` — prioritize destinations near user-favorited locations

---

## 9. Notification System

### Delivery: SendGrid

- Python library: `sendgrid`
- Requires `SENDGRID_API_KEY` in `.env`
- Free tier: 100 emails/day (more than sufficient)
- Users of the open source project register their own free SendGrid account

### Email Content (Phase 1)

**Subject:** `✈️ Trip of the Day: [City, Country] — $[total] for [n] nights`

**Body (HTML):**
- Destination name, country, and region
- Departure and return dates
- Cost breakdown table (flights / hotel / car / food / total)
- Estimate flags where applicable
- Distance from home airport
- Three booking links: flights, hotel, rental car search
- Footer: "Not interested? [Exclude this destination]" (links to UI exclusion page)

### Fallback

If `SENDGRID_API_KEY` is not set, `notifier.py` prints a formatted plain-text version of the trip to stdout. This makes local development and testing possible without any email configuration.

---

## 10. User Interface

### Framework: Streamlit

Streamlit runs as a local web server accessible at `http://localhost:8501` in any browser. It requires no separate frontend build step — it is pure Python.

Launch command:
```bash
streamlit run ui.py
```

### Pages

#### Dashboard
- Last run status (date, duration, number of candidates evaluated, triggered by scheduler or manual)
- API usage panel: calls used today and this month vs. limits for each API; warning badge if >80% consumed
- Trip of the Day card: destination, dates, cost breakdown, booking links
- "Run Now" button (triggers immediate manual run; respects API rate limits and warns if limits are close)
- Link to full trip history

#### Preferences
- Editable fields for all preferences listed in Section 5.1
- "Save" button writes to the `preferences` table
- Changes take effect on the next run

#### Exclusion List
- Table of all excluded destinations (city, country, date excluded, optional note)
- "Restore" button per row to remove exclusion
- "Clear All" button to reset the entire exclusion list

#### Trip History
- Paginated table of all past daily results
- Columns: date, destination, total cost, rank, selected (was it trip of the day?)
- Expandable row to see full cost breakdown

---

## 11. Configuration & Preferences

### Environment Variables (`.env` file, never committed)

```env
AMADEUS_API_KEY=your_key_here
AMADEUS_API_SECRET=your_secret_here
AMADEUS_ENV=test                    # Set to "production" when ready
SENDGRID_API_KEY=your_key_here
NOTIFICATION_EMAILS=you@example.com,partner@example.com   # Comma-separated list
```

### `.env.example` (committed to repo)

```env
AMADEUS_API_KEY=
AMADEUS_API_SECRET=
AMADEUS_ENV=test
SENDGRID_API_KEY=
NOTIFICATION_EMAILS=    # One or more comma-separated email addresses
```

### User Preferences (stored in DB)

All values in Section 5.1 are stored in the `preferences` table and editable via the UI. Preferences are initialized with defaults on first run.

---

## 12. Phased Implementation Plan

### Phase 1: Proof of Concept

**Goal:** End-to-end working pipeline. Run manually. Produces a real trip recommendation and sends an email.

**Scope:**
- Home airport: HSV (hardcoded for PoC, then moved to preference)
- Trip length: 7 nights, departing 7 days from today
- Travelers: 2 adults, 2 children
- Flights: direct only
- Hotels: 4 stars and up
- Car: required (static estimate)
- Food: Numbeo estimate
- Data source: Amadeus sandbox → Amadeus production
- Destinations: top 20 cheapest from Amadeus Flight Inspiration Search
- Ranking: cheapest total cost, ties by distance
- Notification: SendGrid HTML email
- Exclusion list: stored in DB, respected in ranking (no UI yet — manual DB edit or CLI flag)
- UI: none (CLI only, `python main.py` to trigger a run)
- Scheduling: none (manual execution)

**Deliverables:**
- `main.py`, `fetcher.py`, `costs.py`, `ranker.py`, `notifier.py`, `db.py`, `preferences.py`
- `car_rates.json` with global regional estimates
- `.env.example`, `requirements.txt`, `README.md` with setup instructions
- Basic test suite covering cost calculation and ranking logic

**Success criteria:** Running `python main.py` produces a ranked trip, stores results to SQLite, and sends a correctly formatted email to the configured address.

---

### Phase 2: Scheduling + Basic UI

**Goal:** App runs automatically once per day and has a minimal UI for managing preferences and exclusions.

**Scope:**
- APScheduler integration; configurable run time (default 7:00 AM local)
- Streamlit UI with Dashboard, Preferences, and Exclusion List pages
- All Phase 1 preferences exposed and editable in UI
- "Run Now" button in UI
- Exclusion list manageable via UI (no longer requires manual DB edit)
- `home_airport` preference editable (no longer hardcoded)
- Trip History page (basic version)

**Deliverables:**
- `scheduler.py`, `ui.py`
- Updated `preferences.py` to support all editable fields
- Updated `README.md` with UI launch instructions

**Success criteria:** App runs daily without manual intervention. User can exclude destinations and edit preferences through the browser interface.

---

### Phase 3: Traveler & Trip Configuration

**Goal:** Full control over trip parameters.

**Scope:**
- Editable: number of adults, number of children
- Editable: trip length in nights (exact)
- Editable: advance booking window in days (how far ahead to search)
- Editable: direct flights only toggle
- Editable: minimum hotel star rating
- Editable: car rental required toggle
- All new preferences stored in DB and reflected in all cost calculations

**Success criteria:** User can configure a solo 5-night trip or a family 10-night trip from the UI and get correct cost estimates for the specified configuration.

---

### Phase 4: Trip Length Flexibility

**Goal:** Allow fuzzy trip length to find better deals.

**Scope:**
- `trip_length_nights` becomes a target with optional `trip_length_flex_nights` range
- App searches departure dates ± flex days around the target window
- Cheapest result within the flexible window wins
- UI updated to expose flex setting

**Success criteria:** With `trip_length_nights=7` and `trip_length_flex_nights=2`, the app correctly evaluates 5, 6, 7, 8, and 9-night variants and picks the cheapest.

---

### Phase 5: Multi-Airport Departure

**Goal:** Find cheaper trips by considering nearby departure airports.

**Scope:**
- `search_radius_miles` preference: if > 0, find all airports within that radius of home
- For each nearby airport, calculate transportation cost to that airport:
  - **Phase 5a:** Flat estimate using the current IRS standard mileage reimbursement rate (the federal government rate for personal vehicle use, updated annually and publicly available) applied to the driving distance. This is a well-understood, defensible estimate with no API dependency.
  - **Phase 5b:** Real transit cost via a routing API (e.g., Rome2rio or Google Maps Distance Matrix) for users who want more precision or who might take a shuttle/rideshare instead of driving
- Add transportation cost to total for any trip departing from a non-home airport
- Best trip selected across all departure airports
- Email indicates which departure airport the trip uses and the estimated transport cost to reach it

**Success criteria:** With `search_radius_miles=150`, the app considers BHM (Birmingham) and potentially ATL as alternate departure points and correctly factors in the mileage-based transport cost.

---

### Phase 6: Region Filtering & Advanced Ranking

**Goal:** User can precisely control which destinations are considered using composable filters and choose ranking strategies.

**Scope:**

**Filter system (all filters composable; applied in order before ranking):**
- `region_allowlist` — JSON list of allowed regions; worldwide if empty
- `region_blocklist` — JSON list of blocked regions; takes precedence over allowlist
- Allowlist and blocklist can be combined (e.g., "Europe only, but not Eastern Europe")
- `favorite_locations` — JSON list of user-favorited cities or coordinates
- `favorite_radius_miles` — if set, only include destinations within this radius of any favorited location (enables "trips near places I love" mode)
- `exclude_previously_selected` — boolean; if true, exclude any destination that has ever been the Trip of the Day (maximizes variety across daily picks)
- `exclude_previously_selected_days` — optional rolling window in days instead of all-time (e.g., exclude picks from the last 90 days)
- `exclude_booked` — boolean; if true, exclude destinations the user has marked as booked (see Section 14 for booking status tracking)
- All filters can be combined in any logical combination
- Filter configuration is exposed in the Preferences UI page

**Empty-result protection:**
- Before finalizing ranking, check if the filtered candidate pool is empty
- If empty: surface a **warning** in both the UI (banner on Dashboard) and in the daily email ("No destinations matched your current filters — showing unfiltered results instead" or "No results — consider relaxing your filters")
- Never silently send an empty result or skip the daily notification without explanation

**Ranking strategies (selectable in UI):**
- `cheapest_then_farthest` (default) — ascending cost, ties by distance
- `farthest_then_cheapest` — maximize distance, use price as tiebreaker
- `random` — random selection from valid filtered candidates
- `weighted` — user-defined weights per cost category (future sub-phase)

**Success criteria:** User can configure "Europe and Asia only, but not Eastern Europe, within 500 miles of Paris or Tokyo, excluding past picks" and the app correctly filters candidates, warns if the pool is empty, and falls back gracefully.

---

### Phase 7: Destination Pool Expansion

**Goal:** Expand how candidate destinations are discovered beyond Amadeus Flight Inspiration.

**Scope:**
- Option to supplement with curated destination lists (e.g., user-maintained CSV of desired cities)
- Option to enable/disable specific data sources per run
- Improve destination metadata (points of interest count, safety index, climate data)

**Success criteria:** User can add custom destinations to the candidate pool and the app treats them equally alongside API-sourced candidates.

---

## 13. Open Source Considerations

### Repository Structure Best Practices

- **`.gitignore`** must include:
  - Environment & secrets: `.env`
  - Database: `*.db`, `*.db-shm`, `*.db-wal`
  - Python: `__pycache__/`, `.pytest_cache/`, `*.pyc`, `*.pyo`, `dist/`, `*.egg-info/`, `.venv/`, `venv/`
  - macOS: `.DS_Store`, `._*`
  - Windows: `Thumbs.db`, `desktop.ini`
  - VS Code: `.vscode/` (except optionally `.vscode/extensions.json` for recommended extensions)
  - Linux: `*~`
- **`.env.example`** provides a template with all required keys, blank values
- **`README.md`** must include: prerequisites, setup steps, how to get each API key, how to run, how to launch the UI

### API Key Handling

Every user of this project registers their own accounts with:
- Amadeus for Developers (free)
- SendGrid (free, up to 100 emails/day)
- Numbeo (free)

No keys are ever committed to the repository. This is documented explicitly in the README and enforced by `.gitignore`.

### Development Environment

- **Primary development platform:** macOS, VS Code
- **Target runtime platforms:** macOS, Windows 10/11, Linux (including headless server environments)
- **Python version:** 3.11+ (required for all platforms)
- **Path handling:** All file paths constructed using `pathlib.Path` — never string concatenation — to ensure cross-platform compatibility
- **Line endings:** Repository enforces LF line endings via `.gitattributes` to prevent Windows CRLF issues
- **Scheduling note:** APScheduler works consistently across all platforms. On Windows, the app must be running (as a foreground process or Windows Service) for scheduled runs to fire — it does not register with Task Scheduler automatically. On macOS, a `launchd` plist can be provided. On Linux, a systemd unit file or crontab entry can be provided. The README will include setup instructions for all three.
- **VS Code:** A `.vscode/extensions.json` file will be committed recommending Python, Pylance, and Streamlit-relevant extensions.

### Database Portability

Each user's `trip_of_the_day.db` file is local to their machine. It is excluded from the repository. The schema is version-controlled via `db.py`, which runs `init_db()` on startup to create any missing tables. This means cloning the repo and running the app produces a correctly initialized database automatically.

### Dependency Management

`requirements.txt` pins all dependencies to specific versions for reproducibility. A `setup.py` or `pyproject.toml` may be added in a later phase if distribution becomes a goal.

---

## 14. Future Considerations (Post-Spec)

These items are explicitly out of scope for all current phases but should not be architecturally foreclosed:

- **Traveler rescaling estimates** — From any saved or historical trip result, allow the user to input a different traveler count (e.g., reduce from 4 to 2) and instantly see a recalculated cost estimate. Flights and meals scale proportionally; hotel scales slightly (one room vs. two); car stays flat. Clearly labeled as a rough estimate to help the user evaluate a trip before clicking through to book, without re-running the full query.
- **Trip favorites and saved trips** — Allow users to "favorite" or "save" any trip from the history, marking it for later reference. Saved trips would have their own UI page and could be used to trigger a cost refresh (see below).
- **Trip cost refresh** — From any saved or historical trip result, allow the user to input new dates and/or a different traveler configuration and re-run the cost query for that specific destination. This lets a user revisit a great destination they weren't ready to book at the time without waiting for it to come up again in the daily run.
- **Booked trip tracking** — User can mark a trip as booked. Booked destinations can optionally be excluded from future daily picks (see Phase 6). Booked trips stored for personal travel history and analytics.
- **Min/max total cost thresholds** — filter out trips below a "too cheap to be real" floor or above a budget ceiling
- **User-defined cost weighting** — let users weight flight/hotel/car/food differently in the ranking score
- **Multiple daily candidates** — email the top 3 instead of just the top 1
- **Push notifications** — mobile push via Pushover or Pushbullet as an alternative to email
- **Shared household mode** — run on a local server (e.g., Raspberry Pi) for multiple family members; each recipient in the `notification_emails` list sees the same daily result
- **Direct booking integration** — explicitly ruled out; use affiliate links only
- **Visa and entry requirement data** — surface basic travel advisory info alongside the trip
- **Weather data integration** — include destination weather forecast in the notification
- **Trip scoring beyond cost** — incorporate safety index, traveler ratings, climate suitability
