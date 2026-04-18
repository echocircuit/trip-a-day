# trip-a-day

Determines the cheapest trip that can be booked each day. Runs once daily, finds the lowest-cost weeklong trip from your home airport, and emails you a cost breakdown with direct booking links.

---

## Current phase: Phase 1 — Proof of Concept

**What works now:** Run `python main.py` manually to get a trip recommendation printed to the terminal (or emailed if SendGrid is configured). No scheduling, no UI yet.

**What's coming:** Phase 2 adds a daily scheduler and a Streamlit browser UI for managing preferences and exclusions.

---

## Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) — `brew install uv` (or see [uv docs](https://docs.astral.sh/uv/))
- Free API accounts (details below)

---

## API keys you'll need

| Service | What it's for | Sign up |
|---|---|---|
| [Amadeus for Developers](https://developers.amadeus.com) | Flights and hotels | Free self-service — no credit card |
| [SendGrid](https://sendgrid.com) | Daily email notification | Free up to 100 emails/day — optional, falls back to terminal output |
| [Numbeo](https://www.numbeo.com/api/) | Food cost estimates | Free tier — optional, falls back to regional estimates |

> **Amadeus note:** After signing up, create an app in the Amadeus dashboard. You'll get a `Client ID` (`AMADEUS_API_KEY`) and `Client Secret` (`AMADEUS_API_SECRET`). All Phase 1 development uses the **sandbox** environment — do not change `AMADEUS_ENV` to `production`.

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
# Edit .env and fill in your API keys
```

**`.env` reference:**

```env
AMADEUS_API_KEY=your_client_id_here
AMADEUS_API_SECRET=your_client_secret_here
AMADEUS_ENV=test                       # leave as "test" during Phase 1
SENDGRID_API_KEY=your_key_here         # optional — omit to use terminal output
SENDGRID_FROM_EMAIL=you@example.com    # required if using SendGrid
NUMBEO_API_KEY=your_key_here           # optional — omits for regional fallback estimates
NOTIFICATION_EMAILS=you@example.com,partner@example.com  # comma-separated
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

**Without any API keys:** The run will find no Amadeus destinations and exit. Add at minimum `AMADEUS_API_KEY` and `AMADEUS_API_SECRET` to get results.

**Without SendGrid:** Notification is printed to the terminal instead of emailed.

**Without Numbeo:** Food costs are estimated using regional averages ($20–$60/person/day).

---

## Development

```bash
# Unit tests (fast, no API calls)
pytest tests/unit/

# Integration tests (requires Amadeus sandbox keys)
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
│   ├── fetcher.py           # Amadeus + Numbeo API calls
│   ├── costs.py             # Cost assembly (flight + hotel + car + food)
│   ├── ranker.py            # Trip sorting and selection logic
│   └── notifier.py          # SendGrid email or terminal output
├── car_rates.json           # Static regional car rental rate estimates
├── .env.example             # Template for required environment variables
├── requirements.txt         # Pinned runtime dependencies
├── trip_of_the_day_spec.md  # Full project specification
└── tests/
    ├── unit/                # Fast tests — no API calls required
    └── integration/         # Amadeus sandbox tests
```

---

## License

MIT — see [LICENSE](LICENSE).
