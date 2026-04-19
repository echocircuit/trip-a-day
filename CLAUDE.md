# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`trip-a-day` (package: `trip_a_day`) is a Python CLI application that runs once daily, identifies the cheapest feasible weeklong trip bookable from a home airport, and delivers an HTML summary email. It fetches flight prices via `fast-flights` (Google Flights, no key required), lodging and meal estimates from cached GSA/State Dept per diem rates, and uses a static regional lookup for car rental costs. Results are stored in a local SQLite database.

**Spec reference:** `trip_of_the_day_spec.md` is the authoritative specification. Do not modify it. If a situation is not covered by the spec, stop and ask before deciding.

## Current phase

**Phase 1b — Complete.** Data sources migrated: Amadeus → fast-flights + seed airports, Numbeo → GSA/State Dept per diem, SendGrid → Resend. End-to-end pipeline verified live. All 30 unit tests pass.

**Next: Phase 2.** Read Section 12 of the spec for Phase 2 scope before starting. Begin with `git checkout main && git pull && git checkout -b feature/phase-2-<description>`.

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
pytest tests/unit/                      # must pass (30 tests, no API calls)
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
pytest tests/integration/ -m integration     # live Google Flights tests (no key required)
pytest tests/unit/test_costs.py::test_foo    # single test
pytest --cov=src/trip_a_day                  # full suite with coverage
ruff check .                                 # lint
ruff format .                                # format
mypy src/                                    # type check
python main.py                               # run full pipeline (~2 min)
python scripts/update_rates.py               # refresh per diem data (run each October)
```

## Architecture

**Module layout:** All application modules live in `src/trip_a_day/` (src-layout); `main.py` is at the project root and imports from `trip_a_day`.

**Data flow:**
```
main.py
  → fetcher.py   (fast-flights + per diem rates → typed dataclasses)
  → costs.py     (CostBreakdown assembly)
  → ranker.py    (TripCandidate sorting)
  → db.py        (SQLite storage via SQLAlchemy 2.x)
  → notifier.py  (Resend email or stdout fallback)
```

**Key types:**
- `CostBreakdown` (defined in `costs.py`) — flight, hotel, car, food, total, car_is_estimate
- `TripCandidate` (defined in `ranker.py`) — full trip candidate with cost and metadata
- Fetcher dataclasses (defined in `fetcher.py`): `FlightDestination`, `FlightOffer`, `HotelOffer`, `FoodEstimate`, `AirportInfo`
- SQLAlchemy ORM models (defined in `db.py`): `Preference`, `Destination`, `Trip`, `RunLog`, `ApiUsage`

**Database:** `trip_of_the_day.db` at the project root. Path derived from `db.py` location using `pathlib.Path(__file__).resolve().parents[2]`.

## Architecture decisions

| Decision | Rationale |
|---|---|
| Modules in `src/trip_a_day/` not project root | Preserves established src-layout; `python -m trip_a_day` works cleanly |
| SQLAlchemy 2.x mapped_column style | Modern API; type-safe; consistent with Python 3.11+ |
| fast-flights for all flight data | No API key, no account; reverse-engineers Google Flights protobuf endpoint |
| Destination discovery via seed_airports.json | 96 curated airports replace Amadeus "anywhere" search; updated manually |
| Per diem rates for lodging + food estimates | GSA (domestic) + State Dept (international); cached in data/; refresh each October |
| `_DATA_DIR = Path(__file__).resolve().parents[2] / "data"` | parents[2] from src/trip_a_day/ navigates to project root |
| Distance falls back to 0.0 (seed airports have no coordinates) | Phase 1b limitation; tie-breaking by distance unreliable |
| `TripCandidate` defined in `ranker.py` | Avoids circular imports; ranker is the primary consumer |
| Session passed into fetcher functions explicitly | Makes unit testing clean; avoids module-level state |
| NOTIFICATION_EMAILS env var checked when DB pref is empty list | DB default is `"[]"`; env var is the practical Phase 1b config path |

## Key file map

| File | Purpose |
|---|---|
| `main.py` | Entry point; wires the full pipeline for a single run |
| `src/trip_a_day/db.py` | SQLAlchemy engine, ORM models, `init_db()`, `seed_preferences()` |
| `src/trip_a_day/preferences.py` | Typed get/set wrappers over the `preferences` table |
| `src/trip_a_day/fetcher.py` | fast-flights calls + per diem lookups; returns typed dataclasses |
| `src/trip_a_day/costs.py` | `CostBreakdown` dataclass; `build_cost_breakdown()`; `lookup_car_cost()` |
| `src/trip_a_day/ranker.py` | `TripCandidate` dataclass; `rank_trips()` with pluggable strategy |
| `src/trip_a_day/notifier.py` | `send_trip_notification()` — Resend HTML email or stdout fallback |
| `car_rates.json` | Static regional daily car rental rate estimates (USD) |
| `data/seed_airports.json` | 96 curated destination airports (replaces Amadeus anywhere search) |
| `data/per_diem_rates.json` | Merged GSA + State Dept per diem rates (1,377 locations) |
| `scripts/update_rates.py` | Refreshes data/ from live GSA API and State Dept XLS |
| `trip_of_the_day_spec.md` | Authoritative specification — do not modify |
| `tests/unit/test_costs.py` | Cost calculation tests (no API calls) |
| `tests/unit/test_ranker.py` | Ranking and sorting tests (no API calls) |
| `tests/unit/test_fetcher_perdiem.py` | Per diem lookup fallback chain tests (no API calls) |
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

- **fast-flights:** No API key required. Queries Google Flights via internal protobuf endpoint. Soft limit: 300 calls/day (self-enforced, tracked in `api_usage`). Full sweep of 95 seed airports takes ~2 minutes.
- **GSA per diem:** `GSA_API_KEY` required only to run `scripts/update_rates.py`. The committed `data/per_diem_rates.json` covers 1,377 locations and is good until October 2026.
- **Resend:** `RESEND_API_KEY` optional. If missing, `notifier.py` falls back to formatted stdout output. Set `NOTIFICATION_EMAILS` in `.env` (comma-separated) — this is the practical config path since the DB default is an empty list.

## Known issues / limitations

- Distance calculation always returns 0.0 miles (seed airports have no lat/lon). Tie-breaking by distance is unreliable until coordinates are added to seed_airports.json.
- Per diem lodging is a government rate (typically 3-star level); actual 4-star costs may be higher. This is noted in the hotel booking note.
- `notification_emails` preference requires `.env` variable or manual DB edit in Phase 1b (no UI yet).
- Google Flights occasionally fails for specific routes (returns no data); those destinations are silently skipped.
