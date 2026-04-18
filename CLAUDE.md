# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`trip-a-day` (package: `trip_a_day`) is a Python CLI application that runs once daily, identifies the cheapest feasible weeklong trip bookable from a home airport, and delivers an HTML summary email. It fetches flight and hotel data from Amadeus, food cost estimates from Numbeo, and uses a static regional lookup for car rental costs. Results are stored in a local SQLite database.

**Spec reference:** `trip_of_the_day_spec.md` is the authoritative specification. Do not modify it. If a situation is not covered by the spec, stop and ask before deciding.

## Current phase

**Phase 1 — Proof of Concept.** CLI only (`python main.py`). No scheduling, no UI. See Section 12 of the spec.

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
pytest tests/unit/                      # must pass
python main.py                          # must run without unhandled exceptions
```
Fix any issues found and commit them. Then push and open a PR:
```bash
git push -u origin feature/<short-description>
gh pr create --title "<title>" --body "<summary>"
```

## Commands

```bash
pytest tests/unit/                           # fast unit tests (no API calls)
pytest tests/integration/ -m integration     # Amadeus sandbox tests (requires API keys)
pytest tests/unit/test_costs.py::test_foo    # single test
pytest --cov=src/trip_a_day                  # full suite with coverage
ruff check .                                 # lint
ruff format .                                # format
mypy src/                                    # type check
python main.py                               # run Phase 1 pipeline
```

## Architecture

**Module layout:** All application modules live in `src/trip_a_day/` (src-layout); `main.py` is at the project root and imports from `trip_a_day`. This differs from the spec's flat layout but preserves the established project structure.

**Data flow:**
```
main.py
  → fetcher.py   (Amadeus + Numbeo → typed dataclasses)
  → costs.py     (CostBreakdown assembly)
  → ranker.py    (TripCandidate sorting)
  → db.py        (SQLite storage via SQLAlchemy 2.x)
  → notifier.py  (SendGrid email or stdout fallback)
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
| Amadeus Python SDK for all Amadeus calls | Handles OAuth token refresh automatically |
| Distance falls back to 0.0 if coordinates unavailable | Ties are "extremely rare"; Phase 1 limitation, acceptable |
| Phase 1 evaluates top 10 destinations (not 20) | Rate limit safety; `n` param in `get_cheapest_destinations` |
| Numbeo food cost falls back to $50/person/day | Numbeo free tier requires registration; fallback makes dev possible without key |
| `TripCandidate` defined in `ranker.py` | Avoids circular imports; ranker is the primary consumer |
| Session passed into fetcher functions explicitly | Makes unit testing clean; avoids module-level state |
| `AMADEUS_ENV=test` locked during all Phase 1 development | Spec requirement; must never be changed to `production` during development phases |
| Placeholder `models.py` and `search.py` replaced | Superseded by spec's module responsibilities; `__init__.py` no longer imports from them |

## Key file map

| File | Purpose |
|---|---|
| `main.py` | Entry point; wires the full pipeline for a single run |
| `src/trip_a_day/db.py` | SQLAlchemy engine, ORM models, `init_db()`, `seed_preferences()` |
| `src/trip_a_day/preferences.py` | Typed get/set wrappers over the `preferences` table |
| `src/trip_a_day/fetcher.py` | All external API calls (Amadeus + Numbeo); returns typed dataclasses; checks api_usage before calling |
| `src/trip_a_day/costs.py` | `CostBreakdown` dataclass; `build_cost_breakdown()`; `lookup_car_cost()` |
| `src/trip_a_day/ranker.py` | `TripCandidate` dataclass; `rank_trips()` with pluggable strategy |
| `src/trip_a_day/notifier.py` | `send_trip_notification()` — SendGrid HTML email or stdout fallback |
| `car_rates.json` | Static regional daily car rental rate estimates (USD) |
| `trip_of_the_day_spec.md` | Authoritative specification — do not modify |
| `tests/unit/test_costs.py` | Cost calculation tests (no API calls) |
| `tests/unit/test_ranker.py` | Ranking and sorting tests (no API calls) |
| `tests/integration/test_fetcher.py` | Amadeus sandbox tests (`@pytest.mark.integration`) |

## Environment setup

```bash
# Requires Python 3.11+, uv
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
pip install -r requirements.txt   # Phase 1 runtime deps

# Copy and fill in your API keys
cp .env.example .env

# Run
python main.py
```

**Python version:** 3.11+ (tested on 3.14)
**Venv:** `.venv/` (existing) or `venv/`
**DB file:** `trip_of_the_day.db` (auto-created at project root on first run; gitignored)

## API notes

- **Amadeus:** Uses official `amadeus` Python SDK. Keys: `AMADEUS_API_KEY`, `AMADEUS_API_SECRET`. `AMADEUS_ENV=test` for ALL development — **never change to `production` during development phases.** Switching to production is documented in the spec as a single env var change; it must only happen when explicitly directed.
- **Numbeo:** `NUMBEO_API_KEY` optional. If missing, food cost falls back to $50/person/day estimate. All cost estimates are flagged in output.
- **SendGrid:** `SENDGRID_API_KEY` optional. If missing, `notifier.py` falls back to formatted stdout output.
- **Rate limits:** Amadeus free production tier: 2,000 calls/month. Phase 1 uses sandbox only. API usage is tracked in the `api_usage` table.

## Known issues / blockers

- Distance calculation falls back to 0.0 miles if Amadeus reference data returns no coordinates for a destination. Tie-breaking by distance is therefore unreliable in Phase 1.
- Numbeo free tier API availability is uncertain; fallback food cost ($50/person/day) may be inaccurate for some regions.
- Amadeus sandbox has limited destination and hotel data; some destinations will return no results and are silently skipped.
- Hotel search uses `adults` count only (not children) because Amadeus hotel API does not have a `children` parameter in the same way.
- `notification_emails` preference requires manual DB edit or `.env` variable in Phase 1 (no UI yet).
