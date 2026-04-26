# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`trip-a-day` (package: `trip_a_day`) is a Python CLI application that runs once daily, identifies the cheapest feasible weeklong trip bookable from a home airport, and delivers an HTML summary email. It fetches flight prices via `fast-flights` (Google Flights, no key required), lodging and meal estimates from cached GSA/State Dept per diem rates, and uses a static regional lookup for car rental costs. Results are stored in a local SQLite database.

**Spec reference:** `trip_of_the_day_spec.md` is the authoritative specification. Do not modify it. If a situation is not covered by the spec, stop and ask before deciding.

## Documentation Requirements

**Docs are updated in the same commit as the code they describe — never deferred.**

If you are about to commit code-only and any of the files below are stale, fix the docs first and include them in the same commit.

### What to keep current

| File | What to update |
|---|---|
| `CLAUDE.md` | Architecture decisions table (add a row for each new design choice), Key file map (add new modules and test files), Key types (reflect field changes), test count in the end-of-phase checklist |
| `PROGRESS.md` | "Next Action" line after every logical unit of work; phase checklist (mark items done as you go, not in bulk at the end); add a new phase checklist section before starting that phase |
| `README.md` | Module list in Project structure, Default preferences table, feature flags, any user-facing behavior change |

### Triggers — update docs in the same commit when you:

- Add a new module (`src/trip_a_day/*.py`) → add it to the Key file map in `CLAUDE.md` and Project structure in `README.md`
- Add or rename a preference or env var → update the Architecture decisions table in `CLAUDE.md` and the Default preferences table in `README.md`
- Change a public type (`CostBreakdown`, `TripCandidate`, etc.) → update Key types in `CLAUDE.md`
- Add a new test file → add it to the Key file map in `CLAUDE.md` and update the test count
- Make a behavioral change visible to the user → update `README.md` "What works now"
- Complete a logical unit of work → update "Next Action" in `PROGRESS.md`

### Spec (`trip_of_the_day_spec.md`)

Read-only. Do not edit it. The only permitted change is updating a phase completion marker — and only when explicitly instructed to do so.

### End-of-phase doc sweep

The final commit of each phase must be a doc sweep that confirms all three files above are current. Check: phase header, test count, all new modules/preferences/types reflected, "Next Action" pointing to the next phase.

## Current phase

**Phase 7 — Complete.** Multi-airport departure: haversine radius search for nearby airports, IRS-rate round-trip transport cost, global candidate ranking across all departure airports. 253 tests passing (169 unit + 29 links + 10 imports + 2 smoke + 12 charts + 8 pass1-resilience + 7 api-counter + 16 email-limits) — includes advance booking window rework, price history chart (dual-series), bug-fix sessions, and email usage tracking feature (see below).

**Phase 7b removed (user decision):** Phase 7b (real transit cost via routing API) was dropped because it adds external API dependencies (Rome2rio or Google Maps Distance Matrix) that complicate new-user setup without sufficient value over the IRS mileage estimate already implemented in Phase 7a.

**Phase 7 additions (2026-04-19):**
- `get_nearby_airports(home_iata, radius_miles, session)` in `fetcher.py`: haversine scan of enabled destinations within `search_radius_miles` of home.
- `main.py` two-pass pipeline loops over `[home_airport] + nearby_airports`; computes `transport_usd = haversine × 2 × irs_mileage_rate` per nearby airport; accumulates candidates globally; winner is globally cheapest.
- `CostBreakdown` gains `transport_usd: float = 0.0`; `build_cost_breakdown` accepts it as kwarg.
- `TripCandidate` gains `departure_airport: str = ""`; notifier shows departure airport notice when winner departs from a non-home airport.
- `ui.py` exposes `search_radius_miles` and `irs_mileage_rate` in Trip Configuration.
- `db.py` adds `irs_mileage_rate` default (`"0.70"`) and `notifications_enabled` default (`"true"`).
- Mock data banner in email and Streamlit UI (amber notice when `FLIGHT_DATA_MODE=mock`).
- Notifications settings in UI: Resend sender mode indicator, `notifications_enabled` toggle, test email button. `main.py` checks `notifications_enabled` before sending.

**Post-Phase-7 polish (2026-04-23):**
- `src/trip_a_day/links.py`: centralised URL builders (`build_flight_url`, `build_hotel_url`, `build_car_url`). `fetcher.py` and `main.py` now import from here instead of building URLs inline.
- `CostBreakdown.total` changed to computed `@property` (sum of components + transport_usd); `hotel_is_estimate: bool = False` field added.
- `DEFAULT_PREFERENCES` public alias added to `db.py` for use in tests.
- `min_hotel_stars` preference removed (meaningless with per-diem rates); documented in `CLAUDE.md` and `db.py`.
- `preferred_hotel_site`, `preferred_car_site`, `preferred_hotel_site_manual_url`, `preferred_car_site_manual_url` preferences added to `db.py`; exposed in UI Booking Preferences section.
- Favorite locations UI: replaced lat/lon textarea with city multiselect backed by `user_favorited` DB flag; `filters.py` `_filter_favorite_radius` reads DB instead of JSON pref.
- `Trip` model: `booked`, `booked_at`, `manually_logged` columns added with idempotent migration.
- Email footer: "✅ Mark as Booked" link via `_mark_booked_link_html/plain` helpers; `main.py` passes `trip_id` to notifier.
- Trip History UI: URL query param handler for `?action=mark_booked&trip_id=N`; per-row action panel (mark booked, favorite, exclude/restore); "Log a Past Trip" form; Status column (✅/✈️/📝).
- `tests/test_imports.py`, `tests/test_smoke.py`, `tests/test_links.py` added (29 new tests; 155 total).

**Post-Phase 6 fixes (2026-04-19):**
- Fixed 9 US airport city names in `data/seed_airports.json` to match GSA per diem table entries (e.g. IAD `"Washington DC"` → `"District of Columbia"`, restoring the $276/night GSA rate instead of the $150 North America fallback).
- Fixed `_lookup_per_diem` domestic fallback: now computes a national domestic average when no exact city match is found, replacing a state-code match that could never fire (per diem stores 2-letter state codes, not "United States").
- Fixed `_synthetic_flight_result` `stops=1` → `stops=0` so mock mode works for any home airport (previously any home airport other than HSV caused "Pass 1 returned no prices" because all synthetic flights were filtered by `direct_only=True`).
- Added `num_rooms` preference (default: 1) and removed the silent `rooms = ceil(adults/2)` calculation from `get_hotel_offers`. Exposed in UI Travelers section alongside Adults and Children.
- Fixed filter architecture: `apply_destination_filters` now runs on the full 302-airport pool *before* `select_daily_batch`, not on the already-selected batch. Previously a North America blocklist would reject the entire (all-NA) batch and trigger a spurious filter-fallback warning.

**Launch UI:** `streamlit run ui.py`
**Launch scheduler:** `python scheduler.py` (daily at time in `scheduled_run_time` pref, default 07:00 local)

**Next: Phase 8.** Begin with `git checkout main && git pull && git checkout -b feature/phase-8-<description>`.

## Development workflow

**Start of a phase** (if not already on a feature branch):
```bash
git checkout main && git pull
git checkout -b feature/<short-description>   # e.g. feature/phase-2-scheduling
```

**During a phase:** commit logical units of work as you go (one module, one test suite, one config change per commit). Use conventional prefixes from CONTRIBUTING.md.

**End of a phase:** before pushing, verify everything works locally:
```bash
ruff check . && ruff format --check .   # must pass clean
mypy src/                               # must pass clean
pytest tests/unit/                      # must pass (no API calls)
pytest tests/test_imports.py tests/test_smoke.py -v  # all import smoke tests pass
python main.py                          # full live run — takes ~2 min (sweeps 95 airports)
```
Fix any issues found and commit them. Then push and open a PR:
```bash
git push -u origin feature/<short-description>
gh pr create --title "<title>" --body "<summary>"
```

## Commands

```bash
pytest tests/unit/                           # fast unit tests (no API calls)
pytest                                       # all fast tests (212 — integration excluded by default)
pytest tests/integration/ -m integration     # live Google Flights tests (no key required; slow)
pytest tests/unit/test_costs.py::test_foo    # single test
pytest --cov=src/trip_a_day                  # full suite with coverage
ruff check .                                 # lint
ruff format .                                # format
mypy src/                                    # type check
python main.py                               # run full pipeline (~2 min, mock mode by default)
FLIGHT_DATA_MODE=live python main.py         # run with live Google Flights
python scripts/update_rates.py               # refresh per diem data (run each October)
```

## Architecture

**Module layout:** All application modules live in `src/trip_a_day/` (src-layout); `main.py` is at the project root and imports from `trip_a_day`.

**Data flow:**
```
main.py
  → filters.py   (apply region allowlist/blocklist, favorite-radius, exclusion rules to full pool)
  → selector.py  (select daily batch from eligible pool, 8 strategies)
  → fetcher.py   (fast-flights [mock/live] + per diem rates → typed dataclasses)
  → cache.py     (TTL-aware price cache, check before live call)
  → costs.py     (CostBreakdown assembly)
  → ranker.py    (TripCandidate sorting)
  → db.py        (SQLite storage via SQLAlchemy 2.x)
  → notifier.py  (Resend email or stdout fallback)
```

**Key types:**
- `CostBreakdown` (defined in `costs.py`) — flight, hotel, car, food, transport_usd, car_is_estimate, hotel_is_estimate; `total` is a computed `@property`
- `TripCandidate` (defined in `ranker.py`) — full trip candidate with cost and metadata; `stale_cache: bool = False` marks trips built from expired cache data
- Fetcher dataclasses (defined in `fetcher.py`): `FlightOffer`, `HotelOffer`, `FoodEstimate`, `AirportInfo`
- SQLAlchemy ORM models (defined in `db.py`): `Preference`, `Destination`, `Trip` (`stale_cache BOOLEAN`), `RunLog` (`pass1_diagnostics TEXT`, `email_blocked BOOLEAN`, `email_blocked_reason TEXT`), `ApiUsage`, `PriceCache`, `EmailUsage` (monthly email counter)

**Database:** `trip_of_the_day.db` at the project root. Path derived from `db.py` location using `pathlib.Path(__file__).resolve().parents[2]`.

## Architecture decisions

| Decision | Rationale |
|---|---|
| Modules in `src/trip_a_day/` not project root | Preserves established src-layout; `python -m trip_a_day` works cleanly |
| SQLAlchemy 2.x mapped_column style | Modern API; type-safe; consistent with Python 3.11+ |
| fast-flights for all flight data | No API key, no account; reverse-engineers Google Flights protobuf endpoint |
| Destination discovery via seed_airports.json | 302 curated airports (expanded in Phase 5) with real lat/lon, region, subregion, price tier |
| Per diem rates for lodging + food estimates | GSA (domestic) + State Dept (international); cached in data/; refresh each October |
| `_DATA_DIR = Path(__file__).resolve().parents[2] / "data"` | parents[2] from src/trip_a_day/ navigates to project root |
| `TripCandidate` defined in `ranker.py` | Avoids circular imports; ranker is the primary consumer |
| Session passed into fetcher functions explicitly | Makes unit testing clean; avoids module-level state |
| NOTIFICATION_EMAILS env var checked when DB pref is empty list | DB default is `"[]"`; env var is the practical Phase 1b config path |
| `FLIGHT_DATA_MODE=mock` default | Allows full pipeline runs without touching Google Flights; mock_flights.json provides fixture data |
| Two-pass search: Pass 1 selects batch, Pass 2 runs top N | Limits live API calls to `max_live_calls_per_run`; TTL cache avoids redundant lookups |
| `PriceCache` table with advance-window TTL | 0–30d→2d, 31–90d→5d, 91–180d→4d, 181d+→2d; prices change faster near departure |
| 8 destination selection strategies in selector.py | Covers common exploration patterns; strategy state (round_robin_offset, region_cycle_index) persisted in preferences table |
| `num_rooms` preference (default 1) replaces `ceil(adults/2)` | Silent formula obscured hotel costs; explicit preference lets users control it directly |
| City names in seed_airports.json match GSA per diem table | Exact-match lookup in `_lookup_per_diem` requires the city string to match; mismatches fell through to $150 regional fallback silently |
| Domestic per diem fallback uses national average | State-code fallback can't fire without state codes in seed data; national average is more accurate than $150 for any domestic city miss |
| Filters applied to full pool before `select_daily_batch` | Applying filters after selection meant a NA blocklist would reject the entire NA-heavy batch and trigger fallback; filtering first ensures the batch is drawn from the eligible set |
| Multi-airport: shared destination batch, per-airport flight lookups | Re-running the same batch from each departure airport avoids double-counting destination query stats; only home airport updates `query_count`/`last_queried_at` |
| Transport cost = `haversine × 2 × irs_mileage_rate` | Round-trip driving estimate; IRS rate is the standard US reimbursement rate and a reasonable proxy for marginal driving cost |
| `get_nearby_airports` skipped entirely when `search_radius_miles == 0` | Early-exit avoids a DB scan for the common case; function still correctly returns `[]` for `radius <= 0` if called directly |
| `CostBreakdown.total` is a computed `@property` | Prevents stale totals if individual fields change after construction; callers can't pass a wrong value |
| `links.py` centralises all booking URL construction | `fetcher.py` and `main.py` both needed flight/hotel/car URLs; one place to update when URL patterns change |
| `min_hotel_stars` preference removed | Hotel costs come from GSA per diem rates, not live hotel search — star rating filtering is meaningless in this context |
| Favorite locations read from `user_favorited` DB flag, not JSON pref | JSON list required storing lat/lon manually; DB flag lets users select cities by name and keeps favourites in sync with the destination table |
| Mark-as-booked URL uses `http://localhost:8501/` | trip-a-day is a local-only app; no public URL to configure. Streamlit reads `?action=mark_booked&trip_id=N` query params on page load |
| Import smoke tests use `importlib` + `hasattr` | Direct `from module import Symbol` gets stripped by ruff as "unused import"; importlib pattern keeps assertions while avoiding the lint error |
| `departure_airport` on `TripCandidate` | Lets the notifier and UI display which airport the winner departs from without re-deriving it from cost |
| `notifications_enabled` preference | Allows disabling email without removing API keys; checked in `main.py` after the pipeline completes |
| `departure_iata` on `Trip` DB model | `TripCandidate.departure_airport` was never persisted; adding nullable column lets the UI and history table show which airport each trip departs from; NULL for backfilled rows shows as "—" |
| M&IE sanity check bounds = dataset ±20% | Per diem dataset range is $1-$287 (2026); ±20% buffer ($0.80-$344.40) catches corruption without false-positives on legitimate extremes like Calgary ($169). Warning only — destination is not excluded. |
| `RunLog.destinations_evaluated` = `len(batch)` | Previously stored `len(all_candidates)` (Pass-2 winners, max 5); now stores the Pass-1 batch size (15 by default) so "destinations evaluated" has the user-expected meaning |
| `RunLog.cache_hits_flights` + `destinations_excluded` | Separate integer columns so the run summary can be shown without parsing the JSON `invalid_data_exclusions` blob |
| `build_flight_url` uses `?tfs=` protobuf format | The old `#flt=` URL fragment stopped working ~2020 when Google migrated to Base64-encoded protobuf parameters. `TFSData.from_interface()` from fast-flights generates the correct encoding; origin, destination, and ISO dates are embedded in the blob and verifiable by base64-decoding |
| `advance_days` replaced by `advance_window_min_days` / `advance_window_max_days` | Single fixed lookahead couldn't find the cheapest date in a window; two bounds let `find_cheapest_in_window` probe across the range. `advance_days` kept as a dormant default for backwards-compat with old DB rows. |
| `find_cheapest_in_window` uses 3 evenly-spaced probes | 3 probes cover the window cheaply (~6 API calls/destination); adaptive triangulation is deferred since 3 probes already catch most price variation across a 7-30 day window |
| `find_cheapest_in_window` returns `(cost, date, live_calls, cache_hits)` | Caller (main.py) needs to accumulate both counters for RunLog; returning them avoids a shared mutable counter |
| `charts.py` generates chart as PNG bytes, base64-embedded in email | External image URLs are blocked by most email clients; inline base64 is the only reliable way to include images in HTML email |
| Chart skipped (returns None) when fewer than 3 data points | A single point or two can't show a meaningful trend; 3 is the minimum for a readable line with any direction |
| Rolling average: 7-point window or all-time mean | If total history < 7 points, a rolling window would collapse to the same value; flat all-time mean is clearer than a rolling window of 1–6 points |
| `matplotlib.use("Agg")` called before pyplot import inside function | Lazy import inside the function avoids startup overhead and allows graceful fallback if matplotlib is absent; Agg is the only backend that works without a display |
| mypy override `ignore_errors = true` for `matplotlib.*` | matplotlib's bundled type stubs have known inaccuracies with datetime arguments in `plot()`; suppressing errors project-wide for that namespace avoids noisy ignores on every call site |
| `generate_price_history_chart` takes `today_run_date: date` not `date.today()` | Callers (notifier uses today; UI Trip History uses the trip's historical run_date) need to control the reference date; internal `date.today()` also made unit tests non-deterministic |
| Series 2 query uses `selected=True` only (no `rank=1`) | `selected=True` is set only for the daily winner; `rank` can be NULL for manually logged trips; using `selected` alone handles both cases without test setup complexity |
| Series 2 omitted (not an error) when < 2 points | First few days of running won't have 7 days of picks; degrading gracefully avoids a blank chart for new installs |
| `get_cached_chart` wrapper in `ui.py` uses `@st.cache_data(ttl=300)` | DB query + matplotlib render are both expensive on every widget interaction; 5-minute TTL balances freshness with performance; all args are primitives (hashable) |
| Trip History chart uses the selected trip's `run_date` as `today_run_date` | Lets the user look back at any past pick and see what the Series 2 context looked like at that time, not today's context |
| Chart primitives extracted inside session context manager | Avoids `DetachedInstanceError` risk; all needed values are scalar columns, but explicit extraction makes the lifetime clear |
| `record_api_call()` called BEFORE `get_flights()` in live branch | Ensures every *attempted* call increments `api_usage`, even when `get_flights()` raises. Previously called after success only; exceptions caused api_usage to under-count vs the in-memory `live_calls_made` counter (the "40 vs 7" Dashboard discrepancy on 2026-04-25) |
| `sys.exit(0)` (not 1) when Pass 1 yields no prices | `sys.exit(1)` inside an APScheduler job kills the scheduler process permanently; exit 0 lets the scheduler survive and retry the next day |
| `_stale_cache_fallback()` in main.py | When all live calls fail, query `PriceCache` for any future-dated entries in the batch and build `TripCandidate` objects with `stale_cache=True`; provides a degraded-but-better-than-nothing result instead of a failure email |
| `pass1_diagnostics` JSON blob on `RunLog` | Stores a breakdown of Pass 1 results (valid, no_price, budget_exhausted, cache_hits, live_calls, stale_cache_used) for post-hoc debugging; written on both success and failure paths |
| `notification_emails` UI field falls back to `NOTIFICATION_EMAILS` env var | DB default is `"[]"`; env var is the practical config path. UI must mirror `notifier._parse_recipients`'s fallback so the field shows the live address, not an empty box |
| `build_flight_url` accepts `direct_only` parameter; passes `max_stops=0` when True | Without the nonstop filter in the deep link, Google Flights showed cheaper connecting flights when `direct_only=True` was in effect during the price query. Encoding `max_stops=0` in the tfs protobuf pre-filters the results page to match what was actually searched |
| `stale_cache` BOOLEAN on `Trip` | Marks trips built from expired `PriceCache` data so the UI and history table can surface a caveat; NULL/False for all normal trips |
| Exception in `find_cheapest_in_window` → WARNING + skip, not abort | An unhandled exception in window search (e.g. malformed data) should not abort the entire run; logging at WARNING and skipping that destination allows the remaining batch to proceed |
| `EmailUsage` table keyed by `YYYY-MM` string | Each new month gets a fresh row automatically; no cleanup needed; `get_emails_sent_this_month` returns 0 if no row exists yet (no send has occurred) |
| Monthly limit check runs before `resend.Emails.send()` in all three `send_*` functions | Prevents silent over-limit sends regardless of which code path triggers the email; test emails and no-results alerts both respect the limit |
| `_record_run_log_blocked` queries most recent `RunLog` by `id DESC` | The RunLog row is committed before `send_trip_notification` is called; querying by id DESC within the same session (identity map) returns the same Python object; no separate run_log_id parameter needed |
| `record_email_sent` called only on `email.get("id")` success | Ensures the counter only increments when Resend confirms delivery; API errors (rate limit, network) do not inflate the count |
| `email_monthly_limit` and `email_warning_threshold_pct` stored as preferences | User can override the Resend free-tier defaults (3,000/month, 90% threshold) without code changes; UI exposes both inputs in Notifications section |

## Key file map

| File | Purpose |
|---|---|
| `main.py` | Entry point; three-pass pipeline (filter pool → select batch → Pass 1 window search → Pass 2 flex-length variants → rank globally → notify) |
| `src/trip_a_day/db.py` | SQLAlchemy engine, ORM models, `init_db()`, `seed_preferences()`, `_seed_destinations()` |
| `src/trip_a_day/preferences.py` | Typed get/set wrappers over the `preferences` table |
| `src/trip_a_day/fetcher.py` | fast-flights (mock or live) + per diem lookups; returns typed dataclasses |
| `src/trip_a_day/selector.py` | 8 destination selection strategies; `select_daily_batch()` public interface |
| `src/trip_a_day/filters.py` | Phase 6 destination filters: region allowlist/blocklist, favorite-radius, exclusion rules |
| `src/trip_a_day/cache.py` | TTL-aware flight price cache: `get_cached_flight()`, `store_flight_cache()` |
| `src/trip_a_day/costs.py` | `CostBreakdown` dataclass; `build_cost_breakdown()`; `lookup_car_cost()` |
| `src/trip_a_day/ranker.py` | `TripCandidate` dataclass; `rank_trips()` with pluggable strategy |
| `src/trip_a_day/notifier.py` | `send_trip_notification()` — Resend HTML email or stdout fallback; `send_test_email()`; `send_no_results_notification()` — ⚠️ alert with diagnostics when Pass 1 returns no prices |
| `src/trip_a_day/charts.py` | `generate_price_history_chart(destination_iata, destination_name, today_cost, today_run_date, db_session)` — dual-series matplotlib PNG (blue: destination history; green dashed: recent daily picks); embedded as base64 in email and rendered in Streamlit UI |
| `src/trip_a_day/links.py` | URL builders: `build_flight_url`, `build_hotel_url`, `build_car_url` |
| `src/trip_a_day/window_search.py` | `find_cheapest_in_window()` — 3-probe adaptive triangulation across the advance booking window; cache-first, budget-aware |
| `car_rates.json` | Static regional daily car rental rate estimates (USD) |
| `data/seed_airports.json` | 302 curated destination airports with lat/lon, region, subregion, price tier |
| `data/per_diem_rates.json` | Merged GSA + State Dept per diem rates (1,377 locations) |
| `tests/fixtures/mock_flights.json` | Mock flight data (40 routes) used when `FLIGHT_DATA_MODE=mock` |
| `scripts/update_rates.py` | Refreshes data/ from live GSA API and State Dept XLS |
| `trip_of_the_day_spec.md` | Authoritative specification — do not modify |
| `tests/unit/test_costs.py` | Cost calculation tests |
| `tests/unit/test_ranker.py` | Ranking and sorting tests |
| `tests/unit/test_selector.py` | All 8 destination selection strategies + pool parameter tests (in-memory DB) |
| `tests/unit/test_cache.py` | TTL logic, cache hit/miss, is_mock flag |
| `tests/unit/test_fetcher_perdiem.py` | Per diem lookup fallback chain tests (7 tests incl. domestic national-average fallback) |
| `tests/unit/test_fetcher_flights.py` | direct_only filtering tests; cheapest-by-price selection; deep link encodes direct_only (8 tests) |
| `tests/unit/test_filters.py` | Region allowlist/blocklist, favorite-radius, exclusion rule tests (16 tests) |
| `tests/unit/test_fetcher_nearby.py` | `get_nearby_airports` haversine radius tests (9 tests) |
| `tests/unit/test_costs_transport.py` | `transport_usd` field on `CostBreakdown` (6 tests) |
| `tests/unit/test_multi_airport.py` | Multi-airport pipeline smoke tests (2 tests) |
| `tests/test_links.py` | URL builder tests for all three `links.py` functions (29 tests) |
| `tests/test_imports.py` | importlib-based public symbol existence checks for all 10 modules (10 tests) |
| `tests/test_smoke.py` | `CostBreakdown` instantiation + `DEFAULT_PREFERENCES` key coverage (2 tests) |
| `tests/unit/test_notifier_departure.py` | Departure airport line in HTML and plain text email (12 tests) |
| `tests/unit/test_window_search.py` | `_probe_dates` and `find_cheapest_in_window` unit tests — budget, cache, and probe-selection (17 tests) |
| `tests/test_charts.py` | Chart generation edge cases: None for <3 pts, PNG bytes + magic bytes for ≥3, edge costs, 7-point window; Series 2 degradation and dual-series rendering (12 tests) |
| `tests/test_pass1_resilience.py` | Pass 1 failure modes: graceful exit, stale cache fallback, exception skipping, diagnostics JSON (8 tests) |
| `tests/test_api_counter.py` | API counter consistency: mock/live modes, exception path counting, window search double-count prevention (7 tests) |
| `tests/test_notifier_limits.py` | Monthly email limit enforcement: get/record helpers, _check_email_limit, warning banner, RunLog blocking (16 tests) |
| `tests/integration/test_fetcher.py` | Live Google Flights tests (`@pytest.mark.integration`, no key required) |

## Environment setup

```bash
# Requires Python 3.11+, uv
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pip install -r requirements.txt

# Copy and fill in your API keys
cp .env.example .env

# Run
python main.py
```

**Python version:** 3.12+ (tested on 3.14)
**Venv:** `.venv/`
**DB file:** `trip_of_the_day.db` (auto-created at project root on first run; gitignored)

## API notes

- **FLIGHT_DATA_MODE:** Set to `mock` (default) or `live` in `.env`. Mock reads `tests/fixtures/mock_flights.json`; live calls Google Flights. Tests that patch `get_flights` should set `FLIGHT_DATA_MODE=live` via monkeypatch.
- **fast-flights:** No API key required. Queries Google Flights via internal protobuf endpoint. Soft limit: 300 calls/day (self-enforced, tracked in `api_usage`). `max_live_calls_per_run` (default 40) caps per-run live calls.
- **GSA per diem:** `GSA_API_KEY` required only to run `scripts/update_rates.py`. The committed `data/per_diem_rates.json` covers 1,377 locations and is good until October 2026.
- **Resend:** `RESEND_API_KEY` optional. If missing, `notifier.py` falls back to formatted stdout output. Set `NOTIFICATION_EMAILS` in `.env` (comma-separated) — this is the practical config path since the DB default is an empty list.

## Known issues / limitations

- Per diem lodging is a government rate (typically 3-star level); actual 4-star costs may be higher. This is noted in the hotel booking note.
- Google Flights occasionally fails for specific routes (returns no data); those destinations are silently skipped.
- Mock flight prices are static fixtures; they don't reflect real market prices or trends.
- **Live mode playwright 401 (2026-04-24):** `FLIGHT_DATA_MODE=live` runs can fail with `playwright.tech 401` errors from the fast-flights library, resulting in "Pass 1 returned no prices." This is a transient auth issue in fast-flights' playwright dependency — not a bug in trip-a-day code. HTTP requests to google.com return 200, but price extraction fails. Workaround: retry the run; mock mode is unaffected.

## Branch Convention

Each phase gets its own branch: `feature/phase-5`, `feature/phase-6`, etc.
Branch is created from `main` at the start of the phase.
All commits for a phase go on that branch.
Phase is merged to `main` only when complete and all tests pass.
Never commit directly to `main`.
If a session starts and no phase branch exists yet, create it before writing any code.

## Interrupted Session Recovery

If a Claude Code session ends unexpectedly mid-phase:
1. Start a new session
2. Run: `git status`, `git branch -a`, `git log --oneline -10`
3. If on a detached HEAD or wrong branch: do NOT commit anything yet — sort the branch first
4. Read `CLAUDE.md`, then `PROGRESS.md`
5. Resume from the "Next Action" line in `PROGRESS.md` exactly
6. If "Next Action" is ambiguous, read the last commit message for context
7. Never cherry-pick unless explicitly instructed to do so
8. If in doubt about branch state, ask before proceeding
