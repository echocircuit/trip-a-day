# trip-a-day

Determines the cheapest trip that can be booked each day. Runs once daily, finds the lowest-cost weeklong trip from your home airport, and emails you a cost breakdown with direct booking links.

---

## Current phase: Phase 8 — Hybrid Destination Input

**What works now:**

- `python main.py` — one-off run, finds and emails (or prints) today's cheapest trip
- `python scheduler.py` — keeps running and fires the pipeline automatically once per day at a configurable time (default 7:00 AM local)
- `streamlit run ui.py` — browser UI for managing preferences, exclusions, viewing trip history, and managing the destination pool
- Multi-airport search: set a radius in Preferences and the pipeline searches nearby airports too, adding IRS-rate driving cost, and picks the globally cheapest departure
- Monthly email limit: Resend sends are tracked per calendar month; approaching the limit adds a warning banner to outgoing emails; reaching it pauses sends until next month (Dashboard and Preferences show live usage)
- **Destinations page:** search and toggle any of the 302 seed airports on/off; add custom airports with live per-diem match preview; bulk-import from CSV (preview table shows matched/unmatched/error counts before committing)

---

## Prerequisites

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) — `brew install uv` (or see [uv docs](https://docs.astral.sh/uv/))
- Optional free API accounts (details below)

---

## API keys you'll need

| Service | What it's for | Sign up |
|---|---|---|
| [GSA API](https://api.data.gov/signup/) | US domestic lodging & meal estimates | Free — register at api.data.gov |
| [Resend](https://resend.com) | Daily email notification | Free up to 3,000 emails/month — optional, falls back to terminal output |

> **Flight data:** No API key required. Flights are fetched via `fast-flights`, which queries Google Flights directly.
>
> **Per diem rates:** Run `python scripts/update_rates.py` once after setup (requires `GSA_API_KEY`) to download and cache domestic and international per diem rates to `data/`. The committed `data/per_diem_rates.json` is current as of April 2026.

---

## Setup

```bash
# 1. Clone
git clone git@github.com:YOUR_USERNAME/trip-a-day.git
cd trip-a-day

# 2. Create virtual environment and install
uv venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
pip install -r requirements.txt

# 3. Install pre-commit hooks (runs ruff + unit tests on commit/push)
pre-commit install
pre-commit install --hook-type pre-push

# 4. Configure your environment
cp .env.example .env
# Edit .env and fill in your API keys (only Resend and GSA are needed)
```

**`.env` reference:**

```env
# Flight data — no key required (fast-flights queries Google Flights directly)

# Hotel + food estimates (domestic US) — register free at https://api.data.gov/signup/
GSA_API_KEY=your_key_here

# Email delivery — register free at https://resend.com (3,000 emails/month, no credit card)
RESEND_API_KEY=your_key_here
# Shared test sender (works without domain verification). Replace with your verified domain for production.
RESEND_FROM_EMAIL=onboarding@resend.dev

# Comma-separated list of recipient email addresses for the daily notification
NOTIFICATION_EMAILS=you@example.com,partner@example.com
```

---

## Running

### One-off run

```bash
python main.py
```

Finds today's cheapest trip and prints or emails it. The local SQLite database (`trip_of_the_day.db`) is created automatically on first run and seeded with default preferences.

### Browser UI

```bash
streamlit run ui.py
```

Opens at `http://localhost:8501`. Five pages:

| Page | What it does |
|---|---|
| **Dashboard** | Last run status, API usage, Trip of the Day card with booking links, Run Now button |
| **Preferences** | Edit all settings (home airport, trip length, travelers, notifications, scheduler time) |
| **Destinations** | Search and enable/disable the 302 seed airports; add custom airports; bulk CSV import |
| **Exclusion List** | Add destinations to skip, restore them, or clear all exclusions |
| **Trip History** | Paginated table of all past evaluated trip candidates |

### Automatic daily scheduling

```bash
python scheduler.py
```

Keeps running and fires the full pipeline once per calendar day at the time configured in **Preferences → Daily run time** (default 7:00 AM local). Keep this process alive or register it with your OS init system:

**macOS (launchd):** Create a plist in `~/Library/LaunchAgents/` that runs `python scheduler.py` at login.

**Linux (systemd):** Create a user service unit that `ExecStart`s `python scheduler.py`.

**Windows:** Use Task Scheduler to launch `python scheduler.py` at startup, or run it in the background with `pythonw scheduler.py`.

---

## Default preferences

| Preference | Default |
|---|---|
| Home airport | `HSV` (Huntsville, AL) |
| Trip length | 7 nights (±0 flex nights) |
| Advance booking | Departing 7–30 days from today (probes 3 dates across window) |
| Travelers | 2 adults, 2 children, 1 room |
| Flights | Direct only |
| Car rental | Included (estimated cost) |
| Nearby airport radius | 0 mi (disabled) |
| IRS mileage rate | $0.70/mile |
| Daily run time | 7:00 AM local |
| Notifications | Enabled |
| Monthly email limit | 3,000 (Resend free tier) |
| Email warning threshold | 90% |

All preferences are editable in the UI under **Preferences**.

---

## Refreshing per diem rate data

Per diem rates are cached in `data/per_diem_rates.json` and committed to the repo. Refresh them each October (when GSA publishes new fiscal year rates) or any time you want the latest international rates:

```bash
# Requires GSA_API_KEY in .env
python scripts/update_rates.py
```

If a specific city's food estimate looks wrong, you can manually override its rate in `data/per_diem_rates.json` — find the entry by `city` and edit `mie_usd` (USD per person per day). The pipeline reloads the file on each run. Note that State Dept M&IE rates are for government travelers and may overstate typical vacation food costs for expensive cities.

---

## Development

```bash
# Unit tests (fast, no API calls)
pytest tests/unit/

# Integration tests (makes real Google Flights calls — no key required)
pytest tests/integration/ -m integration -v

# Lint, format, type check
ruff check .
ruff format .
mypy src/
```

---

## Project structure

```
├── main.py                  # Entry point — one-off run
├── scheduler.py             # APScheduler daily runner
├── ui.py                    # Streamlit browser UI
├── src/trip_a_day/
│   ├── db.py                # SQLite schema and ORM (SQLAlchemy 2.x)
│   ├── preferences.py       # Read/write user preferences from DB
│   ├── fetcher.py           # fast-flights + per diem lookups + nearby airport scan
│   ├── selector.py          # 8 destination selection strategies
│   ├── filters.py           # Region allowlist/blocklist, favorite-radius, exclusion rules
│   ├── cache.py             # TTL-aware flight price cache
│   ├── window_search.py     # 3-probe advance booking window search
│   ├── costs.py             # Cost assembly (flight + hotel + car + food + transport)
│   ├── ranker.py            # Trip sorting and selection logic
│   ├── charts.py            # Price history chart (matplotlib PNG, base64-embedded in email)
│   ├── notifier.py          # Resend email or terminal output
│   └── destination_input.py # Phase 8: per-diem fuzzy matching, CSV parse/preview
├── car_rates.json           # Static regional car rental rate estimates
├── data/
│   ├── seed_airports.json   # 302 curated destination airports with lat/lon and region
│   └── per_diem_rates.json  # Merged GSA + State Dept per diem rates
├── scripts/
│   └── update_rates.py      # Refreshes data/ from GSA and State Dept APIs
├── .env.example             # Template for required environment variables
├── requirements.txt         # Pinned runtime dependencies
├── trip_of_the_day_spec.md  # Full project specification
└── tests/
    ├── unit/                # Fast tests — no API calls required
    └── integration/         # Live Google Flights tests (no key required)
```

---

## License

MIT — see [LICENSE](LICENSE).
