# trip-a-day

Determines the cheapest trip that can be booked each day. Runs once daily, finds the lowest-cost weeklong trip from your home airport, and emails you a cost breakdown with direct booking links.

---

## v1.0.0

**What works now:**

- `python main.py` — one-off run, finds and emails (or prints) today's cheapest trip
- `python scheduler.py` — keeps running and fires the pipeline automatically once per day at a configurable time (default 7:00 AM local)
- `streamlit run ui.py` — browser UI for managing preferences, exclusions, viewing trip history, and managing the destination pool
- Multi-airport search: set a radius in Preferences and the pipeline searches nearby airports too, adding IRS-rate driving cost, and picks the globally cheapest departure
- Monthly email limit: Resend sends are tracked per calendar month; approaching the limit adds a warning banner to outgoing emails; reaching it pauses sends until next month (Dashboard and Preferences show live usage)
- **Destinations page:** search and toggle any of the 302 seed airports on/off; add custom airports with live per-diem match preview; bulk-import from CSV (preview table shows matched/unmatched/error counts before committing)
- **Travel Windows:** define named date ranges (e.g. "Fall Break 2026") and the pipeline searches those windows first before falling back to the standard advance-booking window; windows auto-expire when they pass
- **Timezone display:** Dashboard timestamps shown in your local timezone (configurable in Preferences)
- **Parallel flight queries:** Pass 1 runs up to 3 concurrent Google Flights lookups by default, cutting typical run time from ~70 min to ~20 min for a full 15-destination batch; configurable in Preferences
- **Flight data mode toggle:** switch between mock and live flight data from the Preferences UI — no restart required

---

## Prerequisites

- Python 3.12+
- [`uv`](https://github.com/astral-sh/uv) — `brew install uv` (or see [uv docs](https://docs.astral.sh/uv/))
- Optional free API accounts (details below)

---

## API keys you'll need

| Service | What it's for | Sign up |
|---|---|---|
| [Resend](https://resend.com) | Daily email notification | Free up to 3,000 emails/month — optional, falls back to terminal output |
| [GSA API](https://api.data.gov/signup/) | Refresh US per diem rates (optional) | Free — only needed to run `scripts/update_rates.py` each October |

> **Flight data:** No API key required. Flights are fetched via `fli`, which queries Google Flights directly using Chrome TLS mimicry (`curl_cffi`).
>
> **Per diem rates:** `data/per_diem_rates.json` is committed to the repo and current as of April 2026 — no setup step required. Run `python scripts/update_rates.py` each October (requires `GSA_API_KEY`) to pull the latest GSA fiscal-year rates.

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
# Edit .env: set RESEND_API_KEY and NOTIFICATION_EMAILS to enable email delivery.
# FLIGHT_DATA_MODE=mock (the default) requires no other keys — run main.py immediately.
```

**`.env` reference:**

```env
# Flight data — no key required (fli queries Google Flights directly)
# FLIGHT_DATA_MODE fallback: set to "live" here to override the DB default ("mock").
# The UI Preferences page is the primary way to change this — no restart needed.
FLIGHT_DATA_MODE=mock

# Per diem rates refresh — only needed when running scripts/update_rates.py (each October)
# The committed data/per_diem_rates.json is used at runtime; no key required for daily runs.
GSA_API_KEY=

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

Opens at `http://localhost:8501`. Also accessible from other devices on your local network at `http://<your-machine-ip>:8501`. Five pages:

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

Keeps running and fires the full pipeline once per calendar day at the time configured in **Preferences → Daily run time** (default 7:00 AM local). Keep this process alive or register it with your OS init system.

#### macOS (launchd) — recommended

Save the file below as `~/Library/LaunchAgents/com.tripaday.scheduler.plist`, replacing `/path/to/trip-a-day` with the absolute path to this repository:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key>
    <string>com.tripaday.scheduler</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/trip-a-day/.venv/bin/python</string>
        <string>/path/to/trip-a-day/scheduler.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/path/to/trip-a-day</string>
    <key>StandardOutPath</key>
    <string>/tmp/tripaday.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/tripaday.err</string>
</dict></plist>
```

Then load it:

```bash
# Load (starts immediately and on every login)
launchctl load ~/Library/LaunchAgents/com.tripaday.scheduler.plist

# Verify it's registered
launchctl list | grep tripaday

# Stop and unload
launchctl unload ~/Library/LaunchAgents/com.tripaday.scheduler.plist
```

The scheduler loads your `.env` file automatically — no need to embed API keys in the plist. Logs go to `/tmp/tripaday.log` and `/tmp/tripaday.err`.

#### Linux (systemd)

Create `~/.config/systemd/user/tripaday.service`:

```ini
[Unit]
Description=trip-a-day scheduler

[Service]
ExecStart=/path/to/trip-a-day/.venv/bin/python /path/to/trip-a-day/scheduler.py
WorkingDirectory=/path/to/trip-a-day
Restart=on-failure

[Install]
WantedBy=default.target
```

Then enable it:

```bash
systemctl --user enable --now tripaday
```

#### Windows

Use Task Scheduler to launch `python scheduler.py` at login (set **Start in** to the repo directory), or run it in a background console with `pythonw scheduler.py`.

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
| Timezone | `America/Chicago` (any IANA tz string) |
| Flight data mode | `mock` — change to `live` in Preferences UI or `.env` |
| Parallel flight queries | 3 concurrent workers |
| Run timeout | 20 minutes |
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
│   ├── fetcher.py           # fli + per diem lookups + nearby airport scan
│   ├── selector.py          # 8 destination selection strategies
│   ├── filters.py           # Region allowlist/blocklist, favorite-radius, exclusion rules
│   ├── cache.py             # TTL-aware flight price cache
│   ├── window_search.py     # 3-probe advance booking window search
│   ├── costs.py             # Cost assembly (flight + hotel + car + food + transport)
│   ├── ranker.py            # Trip sorting and selection logic
│   ├── charts.py            # Price history chart (matplotlib PNG, base64-embedded in email)
│   ├── links.py             # Booking URL builders (flight, hotel, car)
│   ├── notifier.py          # Resend email or terminal output
│   ├── utils.py             # Timezone conversion helpers
│   └── destination_input.py # Per-diem fuzzy matching, CSV parse/preview
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
