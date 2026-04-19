# trip-a-day

Determines the cheapest trip that can be booked each day. Runs once daily, finds the lowest-cost weeklong trip from your home airport, and emails you a cost breakdown with direct booking links.

---

## Current phase: Phase 1b — Data Source Migration complete

**What works now:** Run `python main.py` manually to get a trip recommendation printed to the terminal (or emailed if Resend is configured). No scheduling, no UI yet.

**What's coming:** Phase 2 adds a daily scheduler and a Streamlit browser UI for managing preferences and exclusions.

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

```bash
# One-off run — finds today's cheapest trip and prints/emails it
python main.py
```

On the first run, the local SQLite database (`trip_of_the_day.db`) is created automatically and seeded with default preferences:

| Preference | Default |
|---|---|
| Home airport | `HSV` (Huntsville, AL) |
| Trip length | 7 nights |
| Advance booking | Departing 7 days from today |
| Travelers | 2 adults, 2 children |
| Flights | Direct only |
| Hotels | 4 stars and up |
| Car rental | Included (estimated cost) |

To change the home airport or any other preference before Phase 2 (UI) is available, edit the database directly:

```bash
sqlite3 trip_of_the_day.db "UPDATE preferences SET value='ATL' WHERE key='home_airport';"
```

**Without Resend:** Notification is printed to the terminal instead of emailed.

---

## Refreshing per diem rate data

Per diem rates are cached in `data/per_diem_rates.json` and committed to the repo. Refresh them each October (when GSA publishes new fiscal year rates) or any time you want the latest international rates:

```bash
# Requires GSA_API_KEY in .env
python scripts/update_rates.py
```

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
├── main.py                  # Entry point — run this
├── src/trip_a_day/
│   ├── db.py                # SQLite schema and ORM (SQLAlchemy 2.x)
│   ├── preferences.py       # Read/write user preferences from DB
│   ├── fetcher.py           # fast-flights + per diem rate lookups
│   ├── costs.py             # Cost assembly (flight + hotel + car + food)
│   ├── ranker.py            # Trip sorting and selection logic
│   └── notifier.py          # Resend email or terminal output
├── car_rates.json           # Static regional car rental rate estimates
├── data/
│   ├── seed_airports.json   # 96 curated destination airports
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
