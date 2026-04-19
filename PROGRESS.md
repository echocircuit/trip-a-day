# Implementation Progress

## Current Phase: Phase 6 — Region Filtering + Post-Phase 6 Fixes
## Status: Complete (merged)
## Last updated: 2026-04-19 — hotel pricing fixes, mock mode fix, num_rooms preference, 97 unit tests passing

### Phase 1 Checklist

- [x] Read and understood `trip_of_the_day_spec.md` in full (2026-04-18)
- [x] Created `CLAUDE.md` with architecture decisions and file map (2026-04-18)
- [x] Created `PROGRESS.md` with Phase 1 checklist (2026-04-18)
- [x] Updated `.gitignore` with expanded spec list (Section 13) (2026-04-18)
- [x] Created `.env.example` with all required env vars (2026-04-18)
- [x] Created `car_rates.json` with global regional estimates (2026-04-18)
- [x] Created `requirements.txt` with pinned Phase 1 deps (2026-04-18)
- [x] Created `src/trip_a_day/db.py` — SQLAlchemy ORM + init_db + seed_preferences (2026-04-18)
- [x] Created `src/trip_a_day/preferences.py` — typed get/set wrappers (2026-04-18)
- [x] Created `src/trip_a_day/fetcher.py` — Amadeus + Numbeo API calls (2026-04-18)
- [x] Created `src/trip_a_day/costs.py` — CostBreakdown + car rate lookup (2026-04-18)
- [x] Created `src/trip_a_day/ranker.py` — TripCandidate + rank_trips (2026-04-18)
- [x] Created `src/trip_a_day/notifier.py` — SendGrid HTML email + stdout fallback (2026-04-18)
- [x] Updated `src/trip_a_day/__init__.py` — removed placeholder imports (2026-04-18)
- [x] Removed placeholder `models.py` and `search.py` (2026-04-18)
- [x] Created `main.py` — full pipeline entry point (2026-04-18)
- [x] Created `tests/unit/test_costs.py` — cost calculation tests (2026-04-18)
- [x] Created `tests/unit/test_ranker.py` — ranking logic tests (2026-04-18)
- [x] Created `tests/integration/test_fetcher.py` — Amadeus sandbox tests (2026-04-18)
- [x] Run full test suite — 21 unit tests pass (2026-04-18)
- [x] Run `ruff check .` and `mypy src/` — both clean (2026-04-18)
- [x] Commit all work in logical chunks with conventional commit messages (2026-04-18)

### Phase 1b Checklist — Complete

- [x] Replaced Amadeus calls with fast-flights + seed_airports.json (2026-04-18)
- [x] Replaced Numbeo calls with GSA + State Dept per diem lookups (2026-04-18)
- [x] Replaced SendGrid with Resend (2026-04-18)
- [x] Added `data/seed_airports.json` (96 airports) and `data/per_diem_rates.json` (1,377 locations) (2026-04-18)
- [x] Added `scripts/update_rates.py` (refresh each October) (2026-04-18)
- [x] Updated run_log columns: api_calls_flights, api_calls_gsa (2026-04-18)
- [x] All 30 unit tests pass; ruff + mypy clean; python main.py live run verified (2026-04-18)

### Phase 2 Checklist — Complete

- [x] Add APScheduler 3.11.2 + Streamlit 1.56.0 to requirements.txt (2026-04-18)
- [x] Add `scheduled_run_time` preference (default "07:00") to db.py defaults (2026-04-18)
- [x] Update `main.py` — add `triggered_by` parameter to `run()` (2026-04-18)
- [x] Created `scheduler.py` — APScheduler BlockingScheduler, configurable run time (2026-04-18)
- [x] Created `ui.py` — Streamlit: Dashboard, Preferences, Exclusion List, Trip History (2026-04-18)
- [x] Updated notifier.py — hotel/food/car now labelled as estimates; unified footnote (2026-04-18)
- [x] All 30 unit tests pass; ruff + mypy clean (2026-04-18)
- [x] PR merged (2026-04-18)

### Phase 3 Checklist — Complete

- [x] Add `direct_only` parameter to `get_cheapest_destinations` and `get_flight_offers` in fetcher.py (2026-04-18)
- [x] Add `car_required` parameter to `build_cost_breakdown` in costs.py (2026-04-18)
- [x] Wire `direct_flights_only` and `car_rental_required` prefs into main.py pipeline (2026-04-18)
- [x] Add unit tests: `TestBuildCostBreakdownNoCarRental` (4 tests) + `TestDirectOnlyFiltering` (5 tests) (2026-04-18)
- [x] All 39 unit tests pass; ruff + mypy clean (2026-04-18)
- [x] PR merged (2026-04-18)

### Phase 4 Checklist — Complete

- [x] Add `trip_length_flex_nights` preference (default "0") to db.py (2026-04-18)
- [x] Add `_build_night_variants(target, flex)` helper to main.py (2026-04-18)
- [x] Refactor main.py destination loop to try all variants, keep cheapest (2026-04-18)
- [x] Expose `trip_length_flex_nights` input in Preferences UI (2026-04-18)
- [x] Add unit tests for `_build_night_variants` (8 tests) — 47 total pass (2026-04-18)
- [x] PR merged (2026-04-18)

### Phase 5 Checklist — Complete (merged)

- [x] Add `FLIGHT_DATA_MODE=mock` env var; mock path reads `tests/fixtures/mock_flights.json` (2026-04-18)
- [x] Create `tests/fixtures/mock_flights.json` with 40 HSV routes (2026-04-18)
- [x] Expand `data/seed_airports.json` from 97 → 302 airports with lat/lon, subregion, price tier (2026-04-18)
- [x] Add new `Destination` columns + `PriceCache` table to `db.py`; idempotent `_migrate_schema()` (2026-04-18)
- [x] Update `fetcher.py`: mock/live branching in `get_flight_offers`; DB-first `get_airport_info` (2026-04-18)
- [x] Create `src/trip_a_day/cache.py` — TTL logic, `get_cached_flight`, `store_flight_cache` (2026-04-18)
- [x] Create `src/trip_a_day/selector.py` — 8 selection strategies, `select_daily_batch()` (2026-04-18)
- [x] Update `ui.py` — "Destination Pool" section with 5 new Phase 5 preferences (2026-04-18)
- [x] Refactor `main.py` — two-pass search, cache integration, price history updates, live call cap (2026-04-18)
- [x] Add `tests/unit/test_selector.py` (18 tests) and `tests/unit/test_cache.py` (15 tests) (2026-04-18)
- [x] All 80 unit tests pass; ruff + mypy clean (2026-04-18)
- [x] PR merged (2026-04-18)

### Phase 6 Checklist — Complete (merged)

- [x] Create `src/trip_a_day/filters.py` — `apply_destination_filters()` with region allowlist/blocklist, favorite-location radius, exclude-previously-selected, exclude-booked (2026-04-18)
- [x] Add Phase 6 preferences to `db.py` defaults: `region_allowlist`, `region_blocklist`, `favorite_locations`, `favorite_radius_miles`, `exclude_previously_selected`, `exclude_previously_selected_days`, `exclude_booked` (2026-04-18)
- [x] Add `user_booked` column to `Destination` via `_migrate_schema()` (2026-04-18)
- [x] Wire `apply_destination_filters()` into `main.py` pipeline; log filter fallback (2026-04-18)
- [x] Update `ui.py` — Filters section with allowlist/blocklist multiselect, favorite-radius, exclusion toggles; Trip History section with Mark as Booked (2026-04-18)
- [x] Add `RunLog.filter_fallback` column; show warning in UI dashboard when triggered (2026-04-18)
- [x] Add `tests/unit/test_filters.py` (16 tests) — all 96 unit tests pass; ruff + mypy clean (2026-04-18)
- [x] PR merged (2026-04-18)

### Post-Phase 6 Fixes (2026-04-19)

- [x] Fix 9 US airport city names in `seed_airports.json` to match GSA per diem table (IAD, JFK, DEN, BOS, MSP, PHX, TPA, IND, SJC) — was silently returning $150/night regional fallback instead of actual GSA rates (2026-04-19)
- [x] Fix `_lookup_per_diem` domestic fallback: use national domestic average instead of state-code match that could never fire (2026-04-19)
- [x] Fix `_synthetic_flight_result` `stops=1` → `stops=0`; mock mode now works for any home airport, not just HSV (2026-04-19)
- [x] Add `num_rooms` preference (default: 1); remove `ceil(adults/2)` room calculation from `get_hotel_offers`; expose in UI (2026-04-19)
- [x] Add `test_domestic_national_average_fallback` test; update `test_domestic_does_not_match_international` (2026-04-19)
- [x] All 97 unit tests pass; ruff + mypy clean (2026-04-19)

### Decisions Made This Phase

- src-layout preserved: spec modules in `src/trip_a_day/`, `main.py` at project root
- SQLAlchemy 2.x mapped_column style (not 1.x declarative)
- Amadeus Python SDK used (not raw requests) for automatic OAuth token handling
- Top 10 destinations evaluated per run (spec says 20, reduced for rate limit safety)
- Distance defaults to 0.0 if airport coordinates unavailable from Amadeus reference data
- Numbeo food cost falls back to $50/person/day if NUMBEO_API_KEY not set
- `TripCandidate` defined in `ranker.py` to avoid circular imports
- `AMADEUS_ENV=test` locked for all Phase 1 development per spec requirement
- Phase 2: "Run Now" in UI uses `subprocess.run(main.py)` to avoid sys.exit leaking into Streamlit
- Phase 2: APScheduler 3.x BlockingScheduler chosen over 4.x for simpler sync API
- Phase 2: `scheduled_run_time` stored as "HH:MM" string preference; defaults to "07:00"
- Phase 3: `direct_only` defaults to `True`; when False, direct flights are still preferred over connecting
- Phase 3: Mock `trip_a_day.fetcher.get_api_calls_today` (not the db module) — name bound at import time
- Phase 3: `car_required=False` sets car=0.0 and car_is_estimate=False (no lookup at all)
- Phase 5: `FLIGHT_DATA_MODE=mock` default — prevents accidental live API calls during development
- Phase 5: `SimpleNamespace` mimics fast-flights result objects in mock mode (no library dependency)
- Phase 5: Live call cap applies to Pass 1 only; Pass 2 (top N) always gets full variant search
- Phase 5: `round_robin_offset` and `region_cycle_index` stored as preferences for cross-run persistence
- Phase 5: Cache TTL is advance-window-aware: prices change faster near departure

### Decisions Made in Phase 6 / Fixes

- `filters.py` is a pure function module (`apply_destination_filters` takes batch + session + prefs dict); no side effects, easy to unit test
- Filter fallback (empty pool → unfiltered run) logged in `RunLog.filter_fallback` and surfaced as a warning in the UI dashboard and email
- Booked destinations tracked in `Destination.user_booked`; exclusion from the pool is opt-in via `exclude_booked` preference
- City names in `seed_airports.json` must exactly match GSA per diem `city` field (case-insensitive) for the exact-match lookup to hit; any mismatch silently falls through to the $150 North America fallback
- `_lookup_per_diem` domestic fallback now uses a national average (~$140/night) rather than $0; the state-level fallback is impossible without state codes in seed data
- `num_rooms` preference replaces the silent `ceil(adults/2)` formula so users can control hotel room count directly

### Blockers / Open Questions

- None currently.

### Next Action

Begin Phase 7. Branch: `git checkout main && git pull && git checkout -b feature/phase-7-<description>`.
