"""Phase 8 — Hybrid Destination Input helpers.

Provides per-diem fuzzy matching and CSV parsing for the Destinations UI page.
"""

from __future__ import annotations

import csv
import difflib
import io
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any

_DATA_DIR = pathlib.Path(__file__).resolve().parents[2] / "data"
_PER_DIEM_PATH = _DATA_DIR / "per_diem_rates.json"

# Loaded once per process; reset in tests via _reset_per_diem_cache().
_per_diem_cache: list[dict[str, Any]] | None = None


def _load_per_diem() -> list[dict[str, Any]]:
    global _per_diem_cache
    if _per_diem_cache is None:
        if _PER_DIEM_PATH.exists():
            _per_diem_cache = json.loads(_PER_DIEM_PATH.read_text(encoding="utf-8"))
        else:
            _per_diem_cache = []
    return _per_diem_cache


def _reset_per_diem_cache() -> None:
    """For use in tests only."""
    global _per_diem_cache
    _per_diem_cache = None


@dataclass
class PerDiemMatch:
    city: str
    state_or_country: str
    lodging_usd: float
    mie_usd: float
    is_domestic: bool
    score: float  # 0.0-1.0 similarity score


def fuzzy_match_per_diem(query: str, cutoff: float = 0.6) -> PerDiemMatch | None:
    """Return the best per-diem match for *query* city name, or None if below cutoff.

    Uses difflib.SequenceMatcher for stdlib-only fuzzy matching.
    """
    rates = _load_per_diem()
    if not rates:
        return None

    query_lower = query.strip().lower()
    best_score = 0.0
    best_entry: dict[str, Any] | None = None

    for entry in rates:
        city = entry.get("city", "")
        score = difflib.SequenceMatcher(None, query_lower, city.lower()).ratio()
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_score < cutoff or best_entry is None:
        return None

    return PerDiemMatch(
        city=best_entry["city"],
        state_or_country=best_entry.get("state_or_country", ""),
        lodging_usd=float(best_entry.get("lodging_usd", 0)),
        mie_usd=float(best_entry.get("mie_usd", 0)),
        is_domestic=bool(best_entry.get("is_domestic", False)),
        score=best_score,
    )


@dataclass
class CsvRow:
    """A single row from a destination CSV import."""

    iata: str
    city: str
    country: str
    region: str
    per_diem_match: PerDiemMatch | None = None
    error: str = ""

    @property
    def is_valid(self) -> bool:
        return bool(self.iata and not self.error)

    @property
    def has_per_diem(self) -> bool:
        return self.per_diem_match is not None


@dataclass
class CsvImportPreview:
    rows: list[CsvRow] = field(default_factory=list)
    parse_error: str = ""

    @property
    def valid_count(self) -> int:
        return sum(1 for r in self.rows if r.is_valid)

    @property
    def matched_count(self) -> int:
        return sum(1 for r in self.rows if r.is_valid and r.has_per_diem)

    @property
    def unmatched_count(self) -> int:
        return sum(1 for r in self.rows if r.is_valid and not r.has_per_diem)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.rows if not r.is_valid)


# Expected CSV columns (case-insensitive). country and region are optional.
_REQUIRED_COLS = {"iata"}
_OPTIONAL_COLS = {"city", "country", "region"}


def parse_destination_csv(content: str) -> CsvImportPreview:
    """Parse a CSV string into a CsvImportPreview.

    Required column: iata
    Optional columns: city, country, region

    Rows with a missing/empty IATA are marked as errors. Per diem fuzzy
    matching is run against the city name for each valid row.
    """
    preview = CsvImportPreview()
    try:
        reader = csv.DictReader(io.StringIO(content.strip()))
    except Exception as exc:
        preview.parse_error = f"Could not parse CSV: {exc}"
        return preview

    if reader.fieldnames is None:
        preview.parse_error = "CSV has no header row."
        return preview

    headers_lower = {h.lower().strip() for h in reader.fieldnames if h}
    missing = _REQUIRED_COLS - headers_lower
    if missing:
        preview.parse_error = (
            f"CSV is missing required column(s): {', '.join(sorted(missing))}"
        )
        return preview

    # Build a mapping from lowercase header → actual header name in the file.
    col_map = {h.lower().strip(): h for h in (reader.fieldnames or []) if h}

    for i, raw_row in enumerate(reader, start=2):
        iata = (raw_row.get(col_map.get("iata", ""), "") or "").strip().upper()
        city = (raw_row.get(col_map.get("city", ""), "") or "").strip()
        country = (raw_row.get(col_map.get("country", ""), "") or "").strip()
        region = (raw_row.get(col_map.get("region", ""), "") or "").strip()

        if not iata:
            preview.rows.append(
                CsvRow(
                    iata="",
                    city=city,
                    country=country,
                    region=region,
                    error=f"Row {i}: IATA code is empty",
                )
            )
            continue

        if len(iata) < 2 or len(iata) > 4:
            preview.rows.append(
                CsvRow(
                    iata=iata,
                    city=city,
                    country=country,
                    region=region,
                    error=f"Row {i}: IATA '{iata}' must be 2-4 characters",
                )
            )
            continue

        per_diem = fuzzy_match_per_diem(city) if city else None
        preview.rows.append(
            CsvRow(
                iata=iata,
                city=city,
                country=country,
                region=region,
                per_diem_match=per_diem,
            )
        )

    return preview
