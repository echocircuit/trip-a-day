"""Fetch and merge GSA CONUS and State Dept foreign per diem rates.

Writes three files to data/:
  gsa_per_diem.json        — raw GSA CONUS lodging + M&IE by city/state
  state_dept_per_diem.json — parsed State Dept international rates
  per_diem_rates.json      — merged unified lookup used by fetcher.py

Run once on setup, then again each October when GSA updates for the new
fiscal year.

Usage:
    python scripts/update_rates.py

Requires:
    GSA_API_KEY in environment (or .env file at project root)
    openpyxl (pip install openpyxl)
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DATA_DIR = _PROJECT_ROOT / "data"

load_dotenv(_PROJECT_ROOT / ".env")

GSA_API_KEY = os.environ.get("GSA_API_KEY", "")
GSA_BASE = "https://api.gsa.gov/travel/perdiem/v2"
FISCAL_YEAR = (
    datetime.now(UTC).year
    if datetime.now(UTC).month >= 10
    else datetime.now(UTC).year - 1
)


# ---------------------------------------------------------------------------
# GSA CONUS
# ---------------------------------------------------------------------------


def _fetch_gsa_rates(year: int) -> list[dict]:
    # Response is a flat list; each item has City, State, Meals, and per-month lodging keys
    url = f"{GSA_BASE}/rates/conus/lodging/{year}"
    resp = requests.get(url, headers={"x-api-key": GSA_API_KEY}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("rates", [])


def build_gsa_records() -> list[dict]:
    print(f"Fetching GSA CONUS rates for fiscal year {FISCAL_YEAR}…")
    rows = _fetch_gsa_rates(FISCAL_YEAR)

    month_keys = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    records: list[dict] = []

    for row in rows:
        city = (row.get("City") or "").strip()
        state = (row.get("State") or "").strip()
        if not city or not state or city == "Standard Rate":
            continue

        monthly_values = []
        for mk in month_keys:
            v = row.get(mk)
            if v is not None:
                with contextlib.suppress(ValueError, TypeError):
                    monthly_values.append(int(v))
        if not monthly_values:
            continue
        lodging = max(monthly_values)

        mie = 0
        with contextlib.suppress(ValueError, TypeError):
            mie = int(row.get("Meals") or 0)

        records.append(
            {
                "city": city,
                "state_or_country": state,
                "is_domestic": True,
                "lodging_usd": lodging,
                "mie_usd": mie,
                "effective_date": f"FY{FISCAL_YEAR}",
                "source": "gsa",
            }
        )

    print(f"  GSA: {len(records)} domestic locations loaded.")
    return records


# ---------------------------------------------------------------------------
# State Department XLS
# ---------------------------------------------------------------------------


def _state_dept_xls_url(year: int, month: int) -> str:
    month_name = datetime(year, month, 1).strftime("%B").lower()
    return f"https://aoprals.state.gov/content/documents/{month_name}{year}pd.xls"


def _download_xls(year: int, month: int) -> bytes:
    url = _state_dept_xls_url(year, month)
    print(f"  Trying {url} …")
    resp = requests.get(url, timeout=30)
    if resp.status_code == 200:
        return resp.content
    return b""


def _get_xls_bytes() -> bytes:
    now = datetime.now(UTC)
    # Try current month, then previous month
    for delta in (0, -1, -2):
        month = ((now.month - 1 + delta) % 12) + 1
        year = now.year + ((now.month - 1 + delta) // 12)
        data = _download_xls(year, month)
        if data:
            return data
    raise RuntimeError(
        "Could not download State Dept per diem XLS for current or previous 2 months."
    )


def build_state_dept_records() -> list[dict]:
    import xlrd  # type: ignore[import]

    print("Fetching State Dept foreign per diem XLS…")
    xls_bytes = _get_xls_bytes()

    tmp_path = _DATA_DIR / "_tmp_state_dept.xls"
    tmp_path.write_bytes(xls_bytes)

    try:
        wb = xlrd.open_workbook(str(tmp_path))
        ws = wb.sheet_by_index(0)
        records: list[dict] = []
        header_row_idx: int | None = None

        for row_idx in range(ws.nrows):
            row = ws.row_values(row_idx)
            # Detect header row: column B (index 1) contains "Location" or "City"
            if header_row_idx is None:
                b = str(row[1] if len(row) > 1 else "").strip().upper()
                if b in ("LOCATION", "CITY"):
                    header_row_idx = row_idx
                continue

            if len(row) < 7:
                continue

            country = str(row[0] or "").strip()
            city = str(row[1] or "").strip()
            if not country or not city or city.upper() in ("LOCATION", "CITY"):
                continue

            try:
                lodging = float(row[5])  # column F
                mie = float(row[6])  # column G
            except (TypeError, ValueError):
                continue

            records.append(
                {
                    "city": city,
                    "state_or_country": country,
                    "is_domestic": False,
                    "lodging_usd": int(lodging),
                    "mie_usd": int(mie),
                    "effective_date": datetime.now(UTC).strftime("%Y-%m"),
                    "source": "state_dept",
                }
            )

        print(f"  State Dept: {len(records)} international locations loaded.")
        return records

    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Merge + write
# ---------------------------------------------------------------------------


def merge_and_write(gsa: list[dict], state_dept: list[dict]) -> None:
    merged = gsa + state_dept

    _DATA_DIR.mkdir(exist_ok=True)

    gsa_path = _DATA_DIR / "gsa_per_diem.json"
    state_path = _DATA_DIR / "state_dept_per_diem.json"
    merged_path = _DATA_DIR / "per_diem_rates.json"

    gsa_path.write_text(json.dumps(gsa, indent=2), encoding="utf-8")
    state_path.write_text(json.dumps(state_dept, indent=2), encoding="utf-8")
    merged_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")

    print(
        f"\nWrote {len(gsa)} domestic + {len(state_dept)} international = {len(merged)} total records."
    )
    print(f"  {gsa_path.relative_to(_PROJECT_ROOT)}")
    print(f"  {state_path.relative_to(_PROJECT_ROOT)}")
    print(f"  {merged_path.relative_to(_PROJECT_ROOT)}")


def main() -> None:
    if not GSA_API_KEY:
        print(
            "ERROR: GSA_API_KEY not set. Add it to .env or set as environment variable.",
            file=sys.stderr,
        )
        sys.exit(1)

    gsa_records = build_gsa_records()
    state_dept_records = build_state_dept_records()
    merge_and_write(gsa_records, state_dept_records)
    print("\nDone. Run again each October when GSA publishes new fiscal year rates.")


if __name__ == "__main__":
    main()
