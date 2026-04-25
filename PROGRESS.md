# Implementation Progress

## Current Phase: Phase 7 — Multi-Airport Departure
## Status: Complete (PR #21 open, pending merge)
## Last updated: 2026-04-23 — 155 unit tests passing; post-Phase-7 polish complete

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
- [x] Fix filter architecture: `apply_destination_filters` now runs on full 302-airport pool before `select_daily_batch`, not on the already-selected batch; add 4 pool-parameter tests to `test_selector.py` (2026-04-19)
- [x] All 101 unit tests pass; ruff + mypy clean (2026-04-19)

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
- Filters must run on the full pool before batch selection; applying them post-selection caused the NA-heavy default batch to be entirely rejected, triggering a spurious fallback

### Phase 7 Checklist — Complete (PR #21 open)

- [x] Add `get_nearby_airports(home_iata, radius_miles, session)` to `fetcher.py` — haversine scan of enabled destinations (2026-04-19)
- [x] Add `get_airport_city(iata)` to `fetcher.py` — JSON-only lookup for use by notifier (2026-04-19)
- [x] Add `transport_usd: float = 0.0` to `CostBreakdown` and `build_cost_breakdown` in `costs.py` (2026-04-19)
- [x] Add `departure_airport: str = ""` to `TripCandidate` in `ranker.py` (2026-04-19)
- [x] Add `irs_mileage_rate` preference default (`"0.70"`) to `db.py` (2026-04-19)
- [x] Add `notifications_enabled` preference default (`"true"`) to `db.py` (2026-04-19)
- [x] Refactor `main.py` two-pass pipeline: loop over `[home_airport] + nearby_airports`; compute transport_usd per airport; global candidate pool; `notifications_enabled` check before email (2026-04-19)
- [x] Update `notifier.py`: departure airport notice when winner != home airport; `send_test_email()` helper; mock data amber banner (2026-04-19)
- [x] Update `ui.py`: `search_radius_miles` + `irs_mileage_rate` in Trip Configuration; mock mode banner on Dashboard; Notifications section with sender mode, toggle, test email button (2026-04-19)
- [x] Add `tests/unit/test_fetcher_nearby.py` (9 tests) (2026-04-19)
- [x] Add `tests/unit/test_costs_transport.py` (6 tests) (2026-04-19)
- [x] Add `tests/unit/test_multi_airport.py` (2 tests) (2026-04-19)
- [x] All 118 unit tests pass; ruff + mypy clean (2026-04-19)
- [x] PR #21 opened (2026-04-19)

### Decisions Made in Phase 7

- Shared destination batch across all departure airports; only home airport updates `query_count`/`last_queried_at` to avoid inflation
- Transport cost formula: `haversine(home, dep_airport) × 2 × irs_mileage_rate` (round-trip driving estimate)
- `get_nearby_airports` skipped entirely in `main.py` when `search_radius_miles == 0` (early-exit; function still handles `radius <= 0` correctly if called directly)
- `notifications_enabled` checked after pipeline completes; allows disabling email without removing API keys
- `send_test_email()` added to `notifier.py` so UI can trigger a test without running the full pipeline

### Post-Phase-7 Polish (2026-04-23)

- [x] P0: Verified `send_test_email` and `get_nearby_airports` already importable (no-op)
- [x] P1: `tests/test_imports.py` — importlib-based public symbol checks for all 9 modules
- [x] P1: `tests/test_smoke.py` — CostBreakdown computed total, DEFAULT_PREFERENCES keys
- [x] Spec: Phase 7b removed; Phase 8 rewritten as "Hybrid Destination Input"; Phase 9 added ("1.0 Release Prep")
- [x] UI: Replaced lat/lon favorite-locations textarea with city-based multiselect; filters.py now reads `user_favorited` DB flag
- [x] UI: Removed `min_hotel_stars` (meaningless with per-diem rates); added Booking Preferences section (hotel/car site selectors + manual URL option)
- [x] `src/trip_a_day/links.py`: centralised `build_flight_url`, `build_hotel_url`, `build_car_url`; tests in `tests/test_links.py` (18 tests)
- [x] Mock data banner in HTML/plain email + Dashboard amber warning already implemented in earlier commits
- [x] `CostBreakdown.total` changed to computed `@property`; `hotel_is_estimate` field added; `DEFAULT_PREFERENCES` public alias added to `db.py`
- [x] `Trip` model: `booked`, `booked_at`, `manually_logged` columns with idempotent migration
- [x] Email footer: `_mark_booked_link_html/plain` helpers; main.py passes `trip_id` to notifier
- [x] Trip History UI: ?action=mark_booked query param handler; per-row action panel (mark booked, favorite, exclude); "Log a Past Trip" form; Status column (✅/✈️/📝)
- [x] 155 unit + smoke + links tests passing; ruff + mypy clean

### Decisions Made in Post-Phase-7 Polish

- `CostBreakdown.total` is now a `@property` (sum of components + transport_usd) rather than an explicit field; prevents stale totals
- `_filter_favorite_radius` now takes `session` parameter and reads `user_favorited` from DB rather than a JSON pref; the pref key is retained in defaults for backwards compat but ignored by the filter
- Import smoke tests use `importlib.import_module` + `hasattr` to avoid ruff removing "unused" imports
- `min_hotel_stars` removed from defaults and UI; hotel costs come from GSA per diem — star rating is meaningless
- `links.py` has no `trip_a_day.*` imports, so no circular dependency risk
- Mark-as-booked URL uses `http://localhost:8501/` (local-only app; no public URL to configure)

### Blockers / Open Questions

- None currently.

### Housekeeping verified (2026-04-24)

- 194/194 tests pass (`pytest -v`): 149 unit + 26 links + 9 imports + 2 smoke + 8 integration
- Mock pipeline runs cleanly end-to-end; winner stored with `departure_iata=HSV` ✓
- Flight booking URL pre-fills correctly: `#flt=HSV.PUJ.2026-06-05*PUJ.HSV.2026-06-10` ✓
- No $0 flight costs appeared in results (guardrail working) ✓
- Live mode hit playwright.tech 401 from fast-flights library (transient, not our code); documented in CLAUDE.md Known Issues
- Email delivered to configured address with departure airport and mock data banner ✓

### Advance Booking Window Rework (2026-04-24) — branch: feature/advance-booking-window

- [x] Add `advance_window_min_days` (default 7) and `advance_window_max_days` (default 30) to `db.py` defaults; keep `advance_days` for backwards-compat (2026-04-24)
- [x] Update `ui.py`: replace single "Days ahead to search" input with two sliders ("Earliest departure" / "Latest departure") and min<max validation warning (2026-04-24)
- [ ] Create `src/trip_a_day/window_search.py` — `find_cheapest_in_window()` with 3-probe adaptive triangulation
- [ ] Restructure `main.py` to three-pass pipeline: Pass 1 window search per destination, Pass 2 flex-length for top N, final ranking
- [ ] Add `tests/unit/test_window_search.py` import and smoke coverage
- [ ] Update `tests/test_imports.py` and `tests/test_smoke.py` for new module + prefs
- [ ] Doc sweep: CLAUDE.md, PROGRESS.md, README.md

### Next Action

Continue advance booking window rework: implement `window_search.py` next.
