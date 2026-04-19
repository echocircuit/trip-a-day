# Implementation Progress

## Current Phase: Phase 4 — Trip Length Flexibility
## Status: In Progress (PR open)
## Last updated: 2026-04-18 — trip_length_flex_nights preference added; flex-window search loop in main.py; 47 unit tests passing

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

### Phase 4 Checklist — In Progress (PR open)

- [x] Add `trip_length_flex_nights` preference (default "0") to db.py (2026-04-18)
- [x] Add `_build_night_variants(target, flex)` helper to main.py (2026-04-18)
- [x] Refactor main.py destination loop to try all variants, keep cheapest (2026-04-18)
- [x] Expose `trip_length_flex_nights` input in Preferences UI (2026-04-18)
- [x] Add unit tests for `_build_night_variants` (8 tests) — 47 total pass (2026-04-18)
- [ ] PR merged

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

### Blockers / Open Questions

- None currently.

### Next Action

Merge Phase 3 PR, then begin Phase 4.
