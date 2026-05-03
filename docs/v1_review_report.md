# v1.0 Pre-Release Technical Review

**Date:** 2026-05-02
**Branch:** `feature/phase-9-polish`
**Baseline:** 354 tests passing, 0 failures
**Scope:** All source files read diagnostically before any code changes were made.

---

## 1. Spec Divergence

The spec (`trip_of_the_day_spec.md`) is authoritative but has drifted from the implementation across several phases. These are documentation gaps in the spec — the *code* is correct in each case.

| Section | Spec says | Reality |
|---|---|---|
| §4.1 Flight provider | `from fast_flights import get_flights` | `fli` (`flights>=0.8.4`) is used for all flight search; `fast-flights==2.2` retained only for `TFSData` URL encoding in `links.py` |
| §5.1 Preferences | `min_hotel_stars` listed as a stored preference | Removed (meaningless with per-diem rates); not in `_PREFERENCE_DEFAULTS` or UI |
| §5.3 `trips` table | `id, destination_iata, run_date, …` (7 columns) | Actual table has 13 columns; missing from spec: `booked`, `booked_at`, `manually_logged`, `departure_iata`, `stale_cache`, `is_mock` |
| §5.4 `run_log` table | 9 columns | Actual table has 16 columns; missing from spec: `cache_hits_flights`, `destinations_excluded`, `filter_fallback`, `invalid_data_exclusions`, `pass1_diagnostics`, `email_blocked`, `email_blocked_reason`, `travel_window_name` |
| §6 Module list | Lists `main.py`, `db.py`, `preferences.py`, `fetcher.py`, `costs.py`, `ranker.py`, `notifier.py` | 7 additional modules missing: `selector.py`, `filters.py`, `cache.py`, `window_search.py`, `destination_input.py`, `utils.py`, `links.py` |
| §11 Env vars | Lists `TEQUILA_API_KEY` | Tequila was an early candidate data source that was never implemented; the env var is never read anywhere in the codebase |

**Impact:** Low — the spec is explicitly read-only and used only as an authoritative design reference. Users follow README/CONTRIBUTING, not the spec directly.

---

## 2. Test Coverage Gaps

**Baseline:** 354 tests, all passing.

### Dead test code (3 tests against unreachable production code)

`TestWindowPass1ForDeparture` in [`tests/test_travel_windows.py:118`](tests/test_travel_windows.py) has 5 test methods that import and exercise `_window_pass1_for_departure()` from `main.py`. This function is dead code (see §3). The tests pass because the function still exists — they are testing unreachable code paths, not live behavior. When the dead code is removed, these 5 tests will need to be replaced or deleted.

### Unexercised failure path (crash on "manual" URL site)

[`links.py:126`](src/trip_a_day/links.py) raises `ValueError("Unknown hotel site: 'manual'")` and [`links.py:156`](src/trip_a_day/links.py) raises `ValueError("Unknown car site: 'manual'")` when the `"manual"` option is selected in the UI. No test in `tests/test_links.py` covers this case. The crash path is therefore undetected by CI.

### `_connectivity_ok()` in main.py

The pre-flight connectivity check (`_connectivity_ok()` in `main.py`) has no dedicated unit test. It is always bypassed in mock mode (which is what the test suite uses), so its behavior on network failure is untested.

### `_probe_dest_window()` / `_probe_dest_normal()`

The actual thread-entry functions for parallel Pass 1 are tested only indirectly via `test_performance.py` with mocked `find_cheapest_in_window`. Internal branching (exception paths, partial count accumulation) is exercised only through the broader smoke tests.

---

## 3. Code Quality and Consistency

### Must Fix

**`build_hotel_url()` and `build_car_url()` crash on `site="manual"` (links.py:126, 156)**

Both functions raise `ValueError` for the `"manual"` site option. Two DB preferences (`preferred_hotel_site_manual_url`, `preferred_car_site_manual_url`) exist specifically to support manual URL overrides, but they are stored in the DB and exposed in the UI without ever being read by these functions. If a user selects "Manual URL" in the Booking Preferences section and saves, the next pipeline run will crash during Pass 2 when `build_hotel_url(site="manual", ...)` is called. The fix is straightforward: read the corresponding `_manual_url` preference from the DB session and return it when `site == "manual"`.

**`sys.exit(1)` at main.py:1296 kills APScheduler**

The "No valid candidates after Pass 2" exit at `main.py:1296` uses `sys.exit(1)`. The same issue was already found and fixed for Pass 1 failure (line 1278 uses `sys.exit(0)`). `sys.exit(1)` inside an APScheduler job terminates the entire scheduler process, requiring manual restart. Should be `sys.exit(0)`.

### Should Fix

**`_window_pass1_for_departure()` is dead code (main.py:516–644)**

This ~128-line function was the original sequential window search helper. When Pass 1 was parallelized (the `_probe_dest_window()` / `_probe_dest_normal()` thread-entry functions), `_window_pass1_for_departure()` was replaced but not removed. It is never called from `run()`. It will not be reached in any production execution path. Removing it eliminates ~128 lines of maintenance burden and the 5 misleading tests that exercise it.

**`hotel_is_estimate` is always `False` in `CostBreakdown`**

`CostBreakdown` declares `hotel_is_estimate: bool = False` ([`costs.py:36`](src/trip_a_day/costs.py)). `build_cost_breakdown()` never sets it to `True`, even though every hotel cost in the pipeline comes from GSA/State Dept per diem estimates. The field was clearly intended to flag estimate-based costs (analogous to `car_is_estimate`) so callers and the UI can show a caveat. The fix is a one-liner: pass `hotel_is_estimate=True` unconditionally from `build_cost_breakdown()`.

**`numpy` and `scipy` phantom dependencies in `pyproject.toml`**

`pyproject.toml:16–17` declares `numpy>=1.26` and `scipy>=1.12` in `[project.dependencies]`. Neither package is imported anywhere in `src/`, `main.py`, `scheduler.py`, `ui.py`, or `scripts/`. They are large packages (~50MB installed each) that add significant install time and disk usage for new users without providing any functionality. They should be removed.

**Silent exception in `_email_limit_warning_html()` (notifier.py:192)**

```python
except Exception:
    return ""
```

A bare `except Exception:` with no logging means any failure in the email limit check (DB connection error, missing `EmailUsage` table, etc.) is silently swallowed. The warning banner simply disappears. At minimum, the exception should be logged at WARNING level so the silence is intentional and diagnosable.

### Could Fix (minor)

**`_logger_tw` naming inconsistency (main.py)**

`_logger_tw = logging.getLogger("travel_windows")` uses a flat logger name. Python convention for module-level loggers is `logging.getLogger(__name__)` or at least a qualified name like `"main.travel_windows"`. The flat name works but is inconsistent with how the other loggers in the codebase are configured.

---

## 4. Performance Concerns

No significant new concerns found. The parallelization implementation is sound:

- WAL mode correctly enabled on engine creation with 30s busy timeout
- `_extract_dest_data()` correctly converts ORM objects to plain dicts before thread submission (avoids `DetachedInstanceError`)
- Random jitter (0–2s) staggers TLS handshakes — reasonable
- `MAX_PROBES_PER_DESTINATION = 7` hard cap in `window_search.py` prevents unbounded API call growth
- `@st.cache_data(ttl=300)` for chart rendering is appropriate
- Multiple `session.commit()` calls inside the Pass 2 inner loop are negligible for typical batch sizes (≤5 candidates)

Module-level lazy caches for `_seed_airports`, `_per_diem_rates`, and `_mock_flights` in `fetcher.py` are efficient — loaded once per process, not per call.

---

## 5. Security and Data Handling

No critical issues found.

- All secrets (Resend API key, GSA API key) flow through environment variables / `.env` file. `.gitignore` correctly excludes `.env`, `*.db`, `*.db-shm`, `*.db-wal`, and `.streamlit/secrets.toml`.
- SQLAlchemy ORM is used throughout — no raw string interpolation into SQL queries, no SQL injection surface.
- `NOTIFICATION_EMAILS` is parsed via `ast.literal_eval` in `notifier.py` (not `eval`) — safe for the stored JSON string format.
- No user-controlled data flows into shell commands.
- All file paths are anchored to `Path(__file__).resolve().parents[N]` — no path traversal risks.

**Note — Streamlit bound to `0.0.0.0` (`.streamlit/config.toml`):** This is intentional and documented (local network access for tablets/phones). There is no authentication. Acceptable for a single-user local tool, but worth noting explicitly in the README for users who run this on a shared machine or cloud VM.

**Note — `DB_PATH` env var undocumented:** `db.py:25` reads `os.environ.get("DB_PATH", str(_DEFAULT_DB))`, allowing the database path to be overridden via environment variable. This is not mentioned in `.env.example` or the README. It is not a security risk, but a user who moves the repo or uses a non-default DB location has no documentation for how to configure it.

---

## 6. Documentation and Setup

Documentation is generally in good shape after the Phase 9 doc sweep. Two gaps:

**`DB_PATH` not in `.env.example` or README**

The env var `DB_PATH` exists as an undocumented escape hatch in `db.py:25`. Adding a commented-out line to `.env.example` (e.g., `# DB_PATH=./trip_of_the_day.db  # Override default DB location`) costs nothing and prevents confusion for users who hit issues with the default path.

**`openpyxl` in `requirements.txt` vs. `xlrd` in `scripts/update_rates.py`**

`requirements.txt` lists both `openpyxl==3.1.5` and (implicitly) `xlrd==2.0.2` via `scripts/update_rates.py`'s imports. `xlrd` handles `.xls` (legacy format); `openpyxl` handles `.xlsx`. The State Dept source file is `.xls`, so `xlrd` is required. `openpyxl` appears to be an unused holdover from when `.xlsx` support was anticipated. Worth confirming and removing `openpyxl` if it is not actually needed.

---

## 7. Open Issues and Known Limitations

These are pre-existing known gaps, documented here for completeness.

- **3 seed airports silently skipped:** REP (Siem Reap), PNH (Phnom Penh), FRU (Bishkek) are absent from fli's Airport enum. `_airport()` raises `ValueError` which `get_flight_offers()` catches and skips. The destinations remain in the pool and show in the Destinations UI, but will never produce a trip. Documented in CLAUDE.md but not surfaced to users in the UI.
- **Per diem rates are government rates:** The GSA/State Dept M&IE rates are calibrated for government travelers and may overstate typical vacation food costs in expensive cities. Noted in README but worth keeping as a known limitation.
- **`hotel_is_estimate` semantic gap:** Covered under §3 as a Should Fix, but also a known limitation — the UI cannot currently distinguish estimate-based hotel costs from prices sourced via a live API, even though all hotel costs are estimates.
- **`preferred_hotel_site_manual_url` / `preferred_car_site_manual_url` never used:** These preferences are exposed in the UI and stored in the DB, but selecting "Manual URL" crashes the pipeline (the Must Fix in §3). Until that fix is applied, these two preference fields are effectively broken.

---

## 8. Summary and Recommended Fix Order

### Must Fix — 2 items

These block correct operation for users who encounter the trigger conditions.

| # | Item | File | Notes |
|---|---|---|---|
| M1 | `build_hotel_url` / `build_car_url` crash on `site="manual"` | `links.py:79`, `links.py:129` | Add `"manual"` branch that reads `preferred_hotel_site_manual_url` / `preferred_car_site_manual_url` from DB; add test for each |
| M2 | `sys.exit(1)` → `sys.exit(0)` for "No valid candidates after Pass 2" | `main.py:1296` | Same fix as was applied to Pass 1 failure (line 1278) |

### Should Fix — 5 items

These are correctness issues, misleading contracts, or unnecessary bloat.

| # | Item | File | Notes |
|---|---|---|---|
| S1 | Remove `_window_pass1_for_departure()` dead code | `main.py:516–644` | Also remove or replace the 5 tests in `TestWindowPass1ForDeparture`; update CLAUDE.md test count |
| S2 | Set `hotel_is_estimate=True` in `build_cost_breakdown()` | `costs.py` | Every hotel cost is a per-diem estimate; the field exists for this purpose |
| S3 | Remove `numpy` and `scipy` from `[project.dependencies]` | `pyproject.toml:16–17` | Never imported; large unnecessary install |
| S4 | Log exception in `_email_limit_warning_html()` | `notifier.py:192` | `except Exception:` → `except Exception as exc: logger.warning(...)` |
| S5 | Add `DB_PATH` to `.env.example` as a commented-out line | `.env.example` | Documentation only; no code change needed |

### Could Fix — 2 items

Minor quality improvements; defer if time is short.

| # | Item | File | Notes |
|---|---|---|---|
| C1 | Fix `_logger_tw` logger name | `main.py` | `"travel_windows"` → `f"{__name__}.travel_windows"` for consistency |
| C2 | Audit `openpyxl` vs `xlrd` in `requirements.txt` | `requirements.txt` | Confirm whether `openpyxl` is actually used; remove if not |

### Spec-only fixes

The spec is read-only per CLAUDE.md. Spec divergences documented in §1 are informational only — no code changes needed.

---

*Total items: 2 Must Fix, 5 Should Fix, 2 Could Fix.*
