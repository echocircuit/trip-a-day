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
- [x] Create `src/trip_a_day/window_search.py` — `find_cheapest_in_window()` with 3-probe adaptive triangulation (2026-04-24)
- [x] Restructure `main.py` to three-pass pipeline: Pass 1 window search per destination, Pass 2 flex-length for top N, final ranking (2026-04-24)
- [x] Add `tests/unit/test_window_search.py` — 17 tests for `_probe_dates` and `find_cheapest_in_window` (2026-04-24)
- [x] Update `tests/test_imports.py` to cover `window_search.find_cheapest_in_window`; 10 import tests now (2026-04-24)
- [x] Update `tests/test_smoke.py` to cover new preference keys `advance_window_min_days`, `advance_window_max_days` (2026-04-24)
- [x] Doc sweep: CLAUDE.md (new module, new arch decisions, updated test count 149→166 unit, 9→10 imports), README.md (module list, preference table) (2026-04-24)

### Price History Chart (2026-04-25) — branch: feature/price-history-chart

- [x] Add `matplotlib>=3.8` to `requirements.txt` (2026-04-25)
- [x] Create `src/trip_a_day/charts.py` — `generate_price_history_chart()` with 3-probe min threshold, 7-point rolling avg, orange "Today" highlight (2026-04-25)
- [x] Add mypy override for `matplotlib.*` in `pyproject.toml` (2026-04-25)

- [x] Update `notifier.py`: `db_session` parameter on `send_trip_notification` and `_build_html`; `_price_history_section_html` helper embeds chart or shows fallback message (2026-04-25)
- [x] Update `main.py`: pass `db_session=session` to `send_trip_notification` (2026-04-25)

- [x] Create `tests/test_charts.py` — 8 tests: None for <3 pts, PNG bytes for ≥3 pts, valid PNG magic, edge cases (higher/lower/identical costs), 7-point rolling window path (2026-04-25)
- [x] 212 tests passing (204 existing + 8 chart tests)

- [x] Update `trip_of_the_day_spec.md`: `charts.py` in Section 6 module list; per-component chart extension in Section 14 Future Considerations (2026-04-25)
- [x] Update `CLAUDE.md`: test count 195→212, `charts.py` in key file map and arch decisions, `test_charts.py` in key file map (2026-04-25)
- [x] Update `README.md`: `charts.py` in project structure module list (2026-04-25)

### Bug-Fix Session: Pass 1 resilience + API counter (2026-04-25)

Branch: `feature/bug-fixes-pass1-api-counter` (worktree: hopeful-burnell-94a7ac)

Root causes confirmed:
- **Bug 1:** `sys.exit(1)` on empty Pass 1 crashed APScheduler permanently. Silent exception swallowing in `get_flight_offers` (logged at DEBUG, not WARNING) hid the real cause.
- **Bug 2:** `record_api_call()` was only called after a *successful* `get_flights()` call. Exceptions bypassed it, making `api_usage` under-count while the in-memory counter tracked all attempts.

Fixes implemented:
- [x] `fetcher.py`: move `record_api_call` before `get_flights()`, upgrade exception log to WARNING
- [x] `db.py`: add `pass1_diagnostics TEXT` to `RunLog`, `stale_cache BOOLEAN` to `Trip`; `_migrate_schema` entries updated
- [x] `ranker.py`: `TripCandidate.stale_cache: bool = False`
- [x] `notifier.py`: `send_no_results_notification()` added
- [x] `main.py`: graceful Pass 1 degrade (`sys.exit(0)`), stale-cache fallback, connectivity pre-check, try-except around window search, `pass1_diagnostics` written to `RunLog`
- [x] `ui.py`: clarify "live API calls (this run)" vs cumulative api_usage label
- [x] `tests/test_pass1_resilience.py`: 8 new tests
- [x] `tests/test_api_counter.py`: 7 new tests
- [x] `tests/unit/test_main_smoke.py`: updated `test_run_exits_0_when_no_destinations` assertion (was 1, now 0)
- [x] All ruff lint + format issues fixed (235 tests passing)

Commits 1–3 made on 2026-04-25. Commit 4 (docs) in progress.

### Bug-Fix Session: Email field + flight deep link (2026-04-25)

Branch: `feature/bug-fixes-email-field-flight-pricing`

Root causes confirmed:
- **Bug 1 (email field empty):** `ui.py` read `notification_emails` from the DB only. When emails are configured via the `NOTIFICATION_EMAILS` env var (the practical config path per CLAUDE.md), the DB value is `"[]"` and `emails_str` resolves to `""`. Fix: mirror `notifier._parse_recipients` — fall back to `NOTIFICATION_EMAILS` env var when DB value is empty; show "No email configured" placeholder when both are empty.
- **Bug 2 (deep link shows cheaper flights):** `build_flight_url` in `links.py` did not pass a nonstop filter to `TFSData.from_interface`. When `direct_flights_only=True`, we queried only nonstop flights (e.g. $350) but the deep link opened Google Flights without the nonstop filter, showing cheaper connecting flights ($250). Fix: add `direct_only: bool = False` parameter to `build_flight_url`; pass `max_stops=0` when `True`; thread `direct_only` through from `get_flight_offers`.

Note: Flight selection was already correct (uses `min()` by price, not `flights[0]` / `is_best`). Price representation is total-for-all-passengers (Google Flights returns total when N passengers are queried). Passenger count was already correctly encoded in the deep link.

Fixes implemented:
- [x] `ui.py`: fall back to `NOTIFICATION_EMAILS` env var when DB value empty; add placeholder text when neither is set (2026-04-25)
- [x] `links.py`: `build_flight_url` gains `direct_only: bool = False`; passes `max_stops=0` to `TFSData.from_interface` when True (2026-04-25)
- [x] `fetcher.py`: `get_flight_offers` passes `direct_only=direct_only` to `build_flight_url` (2026-04-25)
- [x] `tests/unit/test_fetcher_flights.py`: 3 new tests — cheapest nonstop selected not first, connecting excluded before price sort, deep link differs with direct_only (2026-04-25)
- [x] `tests/test_links.py`: 3 new tests — direct_only URL differs, direct_only=False is default, 2-adult URL differs from 1-adult (2026-04-25)
- [x] 218 tests passing; ruff + mypy clean (2026-04-25)

### Chart Enhancement: Second Series + Streamlit UI (2026-04-25) — branch: feature/chart-second-series-ui

- [x] `generate_price_history_chart` gains `today_run_date: date` parameter; removes internal `date.today()` so callers control the reference date (2026-04-25)
- [x] Series 2 — green dashed line: past 7 days of `selected=True` daily winners from the trips table; each point annotated with short city name (2026-04-25)
- [x] Degradation rules: Series 2 omitted when < 2 points; Series 1 omitted when < 3 points; both absent → return None (2026-04-25)
- [x] Rolling avg line style changed to dotted (`:`) to separate it visually from the new dashed (`--`) Series 2 (2026-04-25)
- [x] `notifier.py`: passes `date.today()` as `today_run_date`; adds two-series footnote below chart in HTML email (2026-04-25)
- [x] `tests/test_charts.py`: all 8 existing tests updated for new signature; 4 new tests (Series 2 degradation + dual-series rendering); 12 total (2026-04-25)
- [x] `ui.py`: `get_cached_chart()` wrapper with `@st.cache_data(ttl=300)` (2026-04-25)
- [x] Dashboard "Trip of the Day" card: chart shown below cost metrics, above booking buttons (2026-04-25)
- [x] Trip History action panel: chart shown for selected trip using that trip's `run_date` (2026-04-25)
- [x] 237 tests passing; ruff + format clean (2026-04-25)

### Pre-push Hook + Test Suite Fixes (2026-04-26) — branch: fix/pre-push-hook-slow-tests

- [x] Root cause 1: `.pre-commit-config.yaml` entry `entry: .venv/bin/pytest` used a relative path; fails in git worktrees where `.venv` only exists in the main repo root.
- [x] Root cause 2: `pyproject.toml` `addopts` ran all `testpaths = ["tests"]` tests by default, including integration tests that make real Google Flights network calls (60 s+ per run, potentially infinite hang via Playwright 401).
- [x] Fix 1: Created `scripts/run_unit_tests.sh` — resolves `.venv` via `git rev-parse --git-common-dir` (always points to main repo's `.git`); updated `.pre-commit-config.yaml` entry to `bash scripts/run_unit_tests.sh`.
- [x] Fix 2: Added `--ignore=tests/integration` to `addopts` in `pyproject.toml`. Default `pytest` now runs 237 fast tests in ~1.4 s; `pytest tests/integration/ -m integration` still works (explicit paths override `--ignore`).
- [x] Updated `CLAUDE.md` Commands section to reflect new `pytest` behavior.
- [x] 237 tests pass; ruff + mypy clean.

### Email Usage Tracking (2026-04-26) — branch: feature/email-usage-tracking

- [x] Add `EmailUsage` ORM model (monthly email counter) to `db.py` (2026-04-26)
- [x] Add `get_emails_sent_this_month` and `record_email_sent` helpers to `db.py` (2026-04-26)
- [x] Add `email_monthly_limit` (3000) and `email_warning_threshold_pct` (90) preferences (2026-04-26)
- [x] Add `email_blocked` and `email_blocked_reason` columns to `RunLog` ORM + migration (2026-04-26)
- [x] Add `get_monthly_email_usage(db_session)` to `notifier.py` (2026-04-26)
- [x] Thread `db_session` through `_send_via_resend`; call `record_email_sent` on success (2026-04-26)
- [x] Pre-send limit check with hard cutoff and RunLog recording (2026-04-26)
- [x] Warning banner in email when usage >= threshold (2026-04-26)
- [x] Email usage indicator in Dashboard and Notifications UI (2026-04-26)
- [x] `tests/test_notifier_limits.py` — full coverage (16 tests, 253 total) (2026-04-26)
- [x] Spec and doc update — trip_of_the_day_spec.md, CLAUDE.md, README.md (2026-04-26)

### Flight Library Migration: fast-flights → fli (2026-04-26) — branch: feature/fix-flight-library-fli

Root cause confirmed:
- `fast-flights` `get_flights()` began returning `401 {"error":"no token provided"}` from Google's internal endpoint. The library's `primp`/Playwright-based HTTP stack could no longer authenticate. All live flight searches failed; `FLIGHT_DATA_MODE=live` runs produced "Pass 1 returned no prices."

Migration:
- [x] Diagnose fast-flights 401 failure — root cause documented in fetcher.py comment (2026-04-26)
- [x] Install `flights>=0.8.4` (PyPI: `fli`) — uses `curl_cffi` with Chrome impersonation; no Playwright (2026-04-26)
- [x] Replace `from fast_flights import FlightData, Passengers, get_flights` with fli imports in `fetcher.py`; add `_airport()` helper and module-level `get_flights()` wrapper (2026-04-26)
- [x] Retain `fast-flights==2.2` in `requirements.txt` solely for `links.py` `TFSData` URL building (pure protobuf, no API calls, not broken) (2026-04-26)
- [x] Verify mock mode unchanged — `FLIGHT_DATA_MODE=mock` path uses `SimpleNamespace` fixtures, fli never called (2026-04-26)
- [x] Update `tests/unit/test_fetcher_flights.py`: add `TestAirportHelper` (4 tests) and `TestUnsupportedAirportGracefulSkip` (2 tests) (2026-04-26)
- [x] Update `CLAUDE.md`: architecture decisions, API notes, known issues (2026-04-26)
- [x] Live run verified: 15 destinations, 45 API calls, winner Austin $5,202 — no 401 errors (2026-04-26)
- [x] 267 tests passing; ruff + mypy clean (2026-04-26)

Decisions:
- fli Airport enum supports 7,835 airports; 3 seed airports absent (REP, PNH, FRU — Cambodia and Kyrgyzstan); these gracefully return None from `get_flight_offers`
- `get_flights` kept as the module-level function name so all test patches targeting `trip_a_day.fetcher.get_flights` continue to work unchanged
- fli returns total price for all passengers (verified: 1 adult=$764, 2 adults=$1,607, 4 adults=$3,213 for JFK→LHR)
- Some international routes return 0 results (CDG) or timeout at ~30s (MEX); both are gracefully handled as None → excluded from candidates

### Phase 8 Checklist — Complete (2026-04-26)

- [x] Create feature branch `feature/phase-8-hybrid-destination-input` from main (2026-04-26)
- [x] Add `is_custom: bool = False` to `Destination` model + migration entry (2026-04-26)
- [x] Update `_seed_destinations()` to skip metadata refresh for `is_custom=True` rows (2026-04-26)
- [x] Create `src/trip_a_day/destination_input.py`: `fuzzy_match_per_diem` (difflib), `parse_destination_csv`, `PerDiemMatch`, `CsvRow`, `CsvImportPreview` dataclasses (2026-04-26)
- [x] Add **Destinations** page to `ui.py`: searchable pool table + enable/disable toggle via `st.data_editor`, Add Custom Destination form with live per-diem preview, CSV bulk import with preview table + confirm (2026-04-26)
- [x] Add `test_destination_input_imports` to `tests/test_imports.py` (2026-04-26)
- [x] Create `tests/unit/test_destination_input.py` (21 tests: fuzzy matching + CSV parsing) (2026-04-26)
- [x] 275 tests pass; ruff + mypy clean (2026-04-26)
- [x] Doc sweep: CLAUDE.md (test count 253→275, new module + test file, new arch decisions), PROGRESS.md (Phase 8 checklist), README.md (current phase, Destinations page in UI table, module list) (2026-04-26)

### Decisions Made in Phase 8

- `is_custom` flag on `Destination` protects user-added rows from being overwritten by seed updates
- `fuzzy_match_per_diem` uses Python stdlib `difflib.SequenceMatcher` — no added dependency
- Per-diem preview rendered outside the `st.form` block so it updates live as the user types
- CSV import skips (not errors) existing IATA codes — idempotent re-import of overlapping files
- Destinations page separated from Preferences (different operational purpose, keeps Preferences page readable)

### Feature Branch: Timezone Display + Travel Windows (2026-04-30–2026-05-01)

Branch: `feature/timezone-and-travel-windows`

#### Part 1 — Timezone Display

- [x] Create `src/trip_a_day/utils.py`: `to_local_display(dt, tz_str)` and `to_local_time_only(dt, tz_str)` helpers (zoneinfo.ZoneInfo, UTC assumption for naive datetimes) (2026-04-30)
- [x] Add `timezone` preference (default `America/Chicago`) to `db.py` `_PREFERENCE_DEFAULTS` (2026-04-30)
- [x] Update `ui.py` Dashboard: convert `last_run.run_at` to user local time via `to_local_display`; add "Display" subheader + timezone text input with ZoneInfoNotFoundError validation; save block deferred when tz invalid (2026-04-30)
- [x] Create `tests/test_utils.py` (11 tests): CST/CDT/EST/BST conversions, naive-as-UTC, invalid tz raises, format shape, time-only format (2026-04-30)
- [x] Commit: `feat: display local time in UI with timezone abbreviation; add timezone preference` (2026-04-30)

#### Part 2 — Travel Windows

- [x] Add `TravelWindow` ORM model to `db.py` (8 columns + `effective_start`/`effective_end` computed properties); add `travel_window_name TEXT` to `RunLog` + `_RUN_LOG_NEW_COLUMNS` migration; add `_seed_travel_windows()` seeder; update `init_db()` (2026-04-30)
- [x] Commit: `feat: add travel_windows table with effective date computation and auto-expiry` (2026-04-30)
- [x] Add `_window_pass1_for_departure()` helper to `main.py`; integrate window-based Pass 1 with two-pass retry (window → fallback); auto-expire past windows; track `winning_window_name` and write to RunLog (2026-04-30)
- [x] Commit: `feat: integrate travel window search into daily run pipeline with fallback logic` (2026-04-30)
- [x] Add Travel Windows management section to `ui.py` Preferences: pool table with enable/disable/delete, add form with date pickers + buffer inputs + notes, live effective-range preview with validation (2026-04-30)
- [x] Commit: `feat: add Travel Windows management UI with live preview in Preferences page` (2026-04-30)
- [x] Update `notifier.py`: `send_trip_notification` gains `travel_window_name` + `window_fallback_used` params; `_travel_window_html/plain` helpers; `_build_html/_build_plain` thread them through; `main.py` passes new params; `ui.py` Dashboard shows active windows + last-run window context (2026-05-01)
- [x] Commit: `feat: show active travel window context in email and Dashboard` (2026-05-01)
- [x] Create `tests/test_travel_windows.py` (28 tests): model properties, `_window_pass1_for_departure` logic, `_travel_window_html/plain` helpers, notifier signature, `_build_html/_build_plain` thread-through (2026-05-01)
- [x] Commit: `test: add full test coverage for travel window logic and edge cases` (2026-05-01)
- [x] Update `trip_of_the_day_spec.md`: status line, Section 5.7 `travel_windows` schema, Post-Phase-8 section in Section 12 (2026-05-01)
- [x] Commit: `docs: update spec with travel_windows data model and phase notes` (2026-05-01)
- [x] Update `CLAUDE.md` and `PROGRESS.md` (this file); update test count (320) (2026-05-01)
- [x] Commit: `docs: update CLAUDE.md and PROGRESS.md after timezone display and travel windows session` (2026-05-01)

#### Result: 320 tests passing (290 prior + 11 utils + 28 travel windows - existing count adjustment)

### Fix Session: Hotel Links, Chart Cleanup, Flight Mode Toggle (2026-05-01)

Branch: `feature/hotel-links-chart-cleanup`

#### Fix 1 — Hotel Deep Link Date Formatting

Root cause: `fetcher.py` hardcoded `site="google_hotels"` in `build_hotel_url()`, ignoring the `preferred_hotel_site` DB preference. Users who configured Booking.com or Expedia always got a Google Hotels URL.

- [x] Add `hotel_site: str = "google_hotels"` parameter to `get_hotel_offers()` in `fetcher.py` (2026-05-01)
- [x] Read `preferred_hotel_site` in `main.py` and pass through to both `get_hotel_offers()` call sites (`_stale_cache_fallback` and Pass 2 loop) (2026-05-01)
- [x] Add verification comment to `links.py` docstring documenting date format per site (2026-05-01)
- [x] Add 5 new tests to `tests/test_links.py`: ISO format for Google Hotels, split params for Booking.com, MM/DD/YYYY for Expedia, checkout date in all sites, date-object == iso-string (34 total) (2026-05-01)

#### Fix 2 — Price History Chart Cleanup

- [x] Extend Series 1 lookback from all-time to past 30 calendar days (2026-05-01)
- [x] Extend Series 2 lookback from 7 days to 30 days; raise minimum threshold from 2 → 3 points (2026-05-01)
- [x] Remove city-name `annotate()` calls from Series 2 and drop the `Destination` join from the S2 query (2026-05-01)
- [x] Update `tests/test_charts.py`: fix existing tests for 30-day constraint; add 5 new tests (30-day boundary, S2-filters, both-below-3, no-city-name-bytes) (17 total) (2026-05-01)

#### Fix 3 — Promote FLIGHT_DATA_MODE to DB Preference

- [x] Add `"flight_data_mode": "mock"` to `_PREFERENCE_DEFAULTS` in `db.py` (2026-05-01)
- [x] Add `get_flight_data_mode(db_session)` to `fetcher.py` — DB priority > env var > "mock" (2026-05-01)
- [x] Replace `os.environ.get("FLIGHT_DATA_MODE", "mock")` in `main.py` with `get_flight_data_mode(session)` (2026-05-01)
- [x] Update `ui.py`: `_is_mock_mode()` uses `get_flight_data_mode()`; replace read-only indicator in Preferences with a radio toggle inside the form; dashboard banner directs to Preferences (2026-05-01)
- [x] Create `tests/test_settings.py` with 8 tests covering DB > env priority, fallback chain, seeded default (2026-05-01)
- [x] 346 tests passing; ruff + mypy clean (2026-05-01)

### Performance Fix Session (2026-05-02) — branch: feature/performance-fix

Root cause confirmed: sequential fli calls (~49 s each) × 90 total calls (2 active travel windows × 15 dests × 3 probes) = 70-min run. Secondary: `pass1_stats["live_calls"]` diagnostic mismatch with `api_calls_flights` (not yet traced to a single cause; `api_calls_flights` via `api_usage` is now the authoritative counter).

- [x] `db.py`: enable WAL mode + 30 s busy timeout on engine; add performance preferences (`max_concurrent_flight_queries=3`, `flight_query_timeout_seconds=10`, `run_timeout_minutes=20`); change travel window seed to `enabled=False` (2026-05-02)
- [x] `window_search.py`: add `MAX_PROBES_PER_DESTINATION = 7` hard cap (2026-05-02)
- [x] `main.py`: add imports (`random`, `concurrent.futures.{ThreadPoolExecutor,wait}`, `SimpleNamespace`); add `_JITTER_MAX_SECONDS = 2.0` constant; add `_extract_dest_data`, `_probe_dest_window`, `_probe_dest_normal` thread-entry helpers; read `max_workers` + `run_timeout_seconds` in `run()`; replace sequential Pass 1 block with parallelized `ThreadPoolExecutor` version (both window-mode and normal-mode paths) (2026-05-02)
- [x] `ui.py`: add Performance section (parallel queries, per-request timeout, run timeout) to Preferences form (2026-05-02)
- [x] `.streamlit/config.toml`: bind to `0.0.0.0:8501` for local network access; add `secrets.toml` to `.gitignore` (2026-05-02)
- [x] `tests/test_performance.py`: 7 tests covering probe cap, window call-count correctness, max_workers=1 sequential behavior, run timeout guard (2026-05-02)
- [x] 350 tests passing; ruff + mypy clean; mock run completes in 0.2 s (2026-05-02)

### Next Action

Open PR `feature/performance-fix` → `main`. After merge, begin Phase 9 (Polish, Hardening, and 1.0 Release Prep).
