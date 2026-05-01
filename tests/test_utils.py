"""Tests for trip_a_day.utils — local timezone conversion helpers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest

from trip_a_day.utils import to_local_display, to_local_time_only


class TestToLocalDisplay:
    def test_utc_to_cst_winter(self):
        """UTC 11:00 → CST 05:00 (UTC-6) in winter."""
        dt = datetime(2026, 1, 15, 11, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = to_local_display(dt, "America/Chicago")
        assert result == "2026-01-15 05:00 CST"

    def test_utc_to_cdt_summer(self):
        """UTC 12:00 → CDT 07:00 (UTC-5) in summer."""
        dt = datetime(2026, 7, 4, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = to_local_display(dt, "America/Chicago")
        assert result == "2026-07-04 07:00 CDT"

    def test_naive_datetime_treated_as_utc(self):
        """Naive datetime (no tzinfo) is assumed UTC."""
        dt = datetime(2026, 1, 15, 11, 0, 0)  # no tzinfo
        result = to_local_display(dt, "America/Chicago")
        assert result == "2026-01-15 05:00 CST"

    def test_invalid_timezone_raises(self):
        """Invalid timezone string raises ZoneInfoNotFoundError."""
        dt = datetime(2026, 1, 15, 11, 0, 0, tzinfo=ZoneInfo("UTC"))
        with pytest.raises(ZoneInfoNotFoundError):
            to_local_display(dt, "Not/ATimezone")

    def test_utc_to_new_york_winter(self):
        """UTC 12:00 → EST 07:00 (UTC-5)."""
        dt = datetime(2026, 2, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = to_local_display(dt, "America/New_York")
        assert result == "2026-02-01 07:00 EST"

    def test_utc_to_london_summer(self):
        """UTC 12:00 → BST 13:00 (UTC+1) in British summer time."""
        dt = datetime(2026, 7, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = to_local_display(dt, "Europe/London")
        assert result == "2026-07-01 13:00 BST"

    def test_format_includes_date_and_abbr(self):
        """Result always has date, time, and tz abbreviation components."""
        dt = datetime(2026, 4, 26, 10, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = to_local_display(dt, "America/Chicago")
        parts = result.split()
        assert len(parts) == 3  # "YYYY-MM-DD", "HH:MM", "TZ"
        assert "-" in parts[0]
        assert ":" in parts[1]


class TestToLocalTimeOnly:
    def test_time_only_cst(self):
        """Returns HH:MM TZ without date portion."""
        dt = datetime(2026, 1, 15, 11, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = to_local_time_only(dt, "America/Chicago")
        assert result == "05:00 CST"

    def test_time_only_cdt_summer(self):
        dt = datetime(2026, 6, 15, 12, 30, 0, tzinfo=ZoneInfo("UTC"))
        result = to_local_time_only(dt, "America/Chicago")
        assert result == "07:30 CDT"

    def test_naive_datetime_treated_as_utc(self):
        dt = datetime(2026, 1, 15, 11, 0, 0)  # naive
        result = to_local_time_only(dt, "America/Chicago")
        assert result == "05:00 CST"

    def test_no_date_in_result(self):
        """Result contains only time and abbreviation — no date digits."""
        dt = datetime(2026, 4, 26, 7, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = to_local_time_only(dt, "America/Chicago")
        parts = result.split()
        assert len(parts) == 2  # "HH:MM" and "TZ"
        assert ":" in parts[0]
        assert "2026" not in result
