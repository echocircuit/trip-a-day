# Changelog

All notable changes to trip-a-day are documented here. Entries are high-level per-phase summaries.

---

## [v1.0.0] — 2026-05-03

**Pre-release review fixes:** Full diagnostic read of all source files; 2 must-fix and 5 should-fix items resolved.

- `build_hotel_url` / `build_car_url` now support `site="manual"` (previously raised `ValueError`, crashing Pass 2 for any user who had selected "Manual URL" in Booking Preferences). The `preferred_hotel_site_manual_url` and `preferred_car_site_manual_url` DB preferences are now consulted.
- `sys.exit(1)` → `sys.exit(0)` when Pass 2 yields no candidates — was killing the APScheduler process permanently.
- Removed `_window_pass1_for_departure()` dead code (~128 lines, orphaned by the parallelization refactor). Dead-code tests replaced with equivalent `_probe_dest_window` tests.
- `hotel_is_estimate` in `CostBreakdown` now correctly set to `True` by `build_cost_breakdown()` (all hotel costs are per-diem estimates).
- Removed `numpy` and `scipy` phantom dependencies from `pyproject.toml` (never imported; ~100 MB unnecessary install).
- `_email_limit_warning_html()` now logs exceptions instead of silently swallowing them.
- `DB_PATH` env var documented in `.env.example`.
- Pre-release review report written to `docs/v1_review_report.md`.

**Phase 9 release prep (2026-05-02):** README audit (scheduler instructions, launchd plist example, preferences table, fli library reference), CHANGELOG and CONTRIBUTING docs added, version bumped to 1.0.0. The spec was reviewed in full and Linux headless smoke testing moved to Section 14 Future Work. No functional changes.

---

## [Post-Phase 8 bug fixes & performance] — 2026-05-02

**Parallelized Pass 1** (`ThreadPoolExecutor`, 3 workers default) cuts a 15-destination run from ~70 min to ~20 min; WAL-mode SQLite prevents thread contention; random per-thread jitter staggers TLS connections. Added hard probe cap (7/destination), global run timeout (20 min), and travel-window seed defaulting to `enabled=False`. Performance preferences exposed in UI; Streamlit bound to all interfaces for local-network access.

**Counter fix:** `pass1_stats["live_calls"]` was under-counting because `record_api_call()` fired after a successful `get_flights()` — moved before the call so exceptions are counted. `live_calls_used` local counter updated to match.

---

## [Post-Phase 8 features] — 2026-05-01

**Timezone display:** new `utils.py` with `to_local_display` / `to_local_time_only` helpers; `timezone` preference (default `America/Chicago`); Dashboard timestamps converted to user-local time with abbreviation.

**Travel Windows:** `travel_windows` DB table with auto-expiry; pipeline runs window-mode first and falls back to the standard advance-booking window if no results; winning window name logged in `RunLog`; email shows a green card for window trips and an amber fallback notice; UI section in Preferences for full CRUD.

**Hotel deep-link fix:** `preferred_hotel_site` preference now correctly threaded through `get_hotel_offers()`; Google Hotels removed as an option (URL parameters silently ignored by their SPA).

**Chart cleanup:** both series look back 30 days; city-name annotations removed; Series 2 minimum raised to 3 points.

**Flight data mode promoted to DB preference:** `get_flight_data_mode()` checks DB → env var → "mock"; UI Preferences radio toggle takes effect without a restart.

---

## [Phase 8 — Hybrid Destination Input] — 2026-04-26

Added a **Destinations** page to the UI: searchable pool table with per-row enable/disable toggles; Add Custom Destination form with live per-diem fuzzy-match preview (`difflib.SequenceMatcher`); CSV bulk import with a preview table showing matched/unmatched/error counts before committing. Custom rows are flagged `is_custom=True` in the DB so seed refreshes never overwrite user-added data.

---

## [Post-Phase 7 polish] — 2026-04-23 to 2026-04-26

**`links.py`** centralised all booking URL construction (flight, hotel, car) with a `direct_only` flag that encodes `max_stops=0` in the Google Flights deep link when nonstop-only search is in effect. **CostBreakdown.total** became a computed `@property`. `min_hotel_stars` preference removed (meaningless with per-diem rates). Favourite locations switched from a lat/lon JSON pref to a `user_favorited` DB flag. **Trip** model gained `booked`, `booked_at`, `manually_logged` columns; email footer includes a "Mark as Booked" link; Trip History page gained per-row action panels (mark booked, favourite, exclude) and a "Log a Past Trip" form.

**Price history chart** (`charts.py`): dual-series matplotlib PNG embedded base64 in email — blue line shows destination price history with rolling average, green dashed line shows recent daily picks. Skipped when fewer than 3 data points. Rendered in Streamlit Trip History.

**fli library migration:** `fast-flights` replaced by `fli` (PyPI: `flights>=0.8.4`) after Google 401 auth breakage. `fast-flights==2.2` retained for `TFSData` URL building only. 3 of 302 seed airports absent from fli's Airport enum; gracefully skipped.

**Email usage tracking:** `EmailUsage` table; monthly hard limit (default 3,000); warning banner when approaching threshold; `email_blocked` flag on `RunLog`; usage indicator in Dashboard and Preferences.

**Pass 1 resilience:** `sys.exit(0)` instead of exit 1 on empty Pass 1 (prevents APScheduler crash); stale-cache fallback when all live calls fail; `pass1_diagnostics` JSON blob on `RunLog`.

---

## [Phase 7 — Multi-Airport Departure] — 2026-04-19

`get_nearby_airports()` scans enabled destinations within a configurable haversine radius of home; `main.py` loops over `[home_airport] + nearby_airports`, adding IRS-rate round-trip driving cost for each alternate; the global winner is the cheapest across all departure airports. `CostBreakdown` gained `transport_usd`; `TripCandidate` gained `departure_airport`. UI exposes `search_radius_miles` and `irs_mileage_rate`. Mock-mode amber banner added to email and Dashboard. Notifications settings section (sender indicator, `notifications_enabled` toggle, test email button).

---

## [Phase 6 — Region Filtering & Advanced Ranking] — 2026-04-18

Composable filter system in `filters.py`: region allowlist/blocklist, favourite-location radius, exclude-previously-selected (all-time or rolling window), exclude-booked. Filters applied to the full 302-airport pool before batch selection. Empty-pool fallback surfaces a warning in the email and Dashboard rather than silently skipping. Three ranking strategies: `cheapest_then_farthest` (default), `farthest_then_cheapest`, `random`.

---

## [Phase 5 — Architecture Improvements] — 2026-04-18

`FLIGHT_DATA_MODE=mock` default (reads `tests/fixtures/mock_flights.json`; prevents accidental live calls). `data/seed_airports.json` expanded from ~97 to 302 airports with real lat/lon, subregion, and price tier. `PriceCache` table with advance-window-aware TTL. Eight destination selection strategies in `selector.py`. Two-pass search: Pass 1 sweeps the daily batch cache-first with a live call cap; Pass 2 runs full night-variant search only for the top N candidates.

---

## [Phase 4 — Trip Length Flexibility] — 2026-04-18

`trip_length_flex_nights` preference: the pipeline evaluates all night-count variants within ±flex of the target and picks the cheapest. UI slider added.

---

## [Phase 3 — Traveler & Trip Configuration] — 2026-04-18

`direct_flights_only`, `car_rental_required`, `num_adults`, `num_children`, `num_rooms` preferences wired end-to-end through the pipeline and exposed in the UI.

---

## [Phase 2 — Scheduling & Streamlit UI] — 2026-04-18

`scheduler.py` (APScheduler BlockingScheduler) fires the pipeline daily at a configurable time. `ui.py` (Streamlit) provides Dashboard, Preferences, Exclusion List, and Trip History pages. "Run Now" button triggers an immediate manual run.

---

## [Phase 1b — Data Source Migration] — 2026-04-18

Replaced all unavailable Phase 1 data sources: Amadeus → `fli` (Google Flights via Chrome TLS mimicry); Numbeo → GSA CONUS per diem + State Dept Foreign per diem (committed to `data/per_diem_rates.json`); SendGrid → Resend. No functional regression; all unit tests pass without API keys.

---

## [Phase 1 — Proof of Concept] — 2026-04-18

Initial working pipeline: `main.py` fetches flight prices, assembles `CostBreakdown` (flight + hotel + car + food), ranks candidates by total cost, stores results in SQLite via SQLAlchemy 2.x ORM, and sends an HTML summary email via Resend (stdout fallback if no key). Home airport, trip length, and traveler counts configurable via `preferences` table.
