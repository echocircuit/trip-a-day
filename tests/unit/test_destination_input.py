"""Tests for src/trip_a_day/destination_input.py -- Phase 8 helper module."""

from __future__ import annotations

import trip_a_day.destination_input as mod
from trip_a_day.destination_input import (
    CsvImportPreview,
    CsvRow,
    PerDiemMatch,
    _reset_per_diem_cache,
    fuzzy_match_per_diem,
    parse_destination_csv,
)

# ── fuzzy_match_per_diem ──────────────────────────────────────────────────────


class TestFuzzyMatchPerDiem:
    def test_exact_match_returns_result(self):
        match = fuzzy_match_per_diem("Birmingham")
        assert match is not None
        assert isinstance(match, PerDiemMatch)
        assert match.city == "Birmingham"
        assert match.score == 1.0

    def test_near_match_returns_result(self):
        # "Huntsvile" (typo) should still match "Huntsville"
        match = fuzzy_match_per_diem("Huntsvile")
        assert match is not None
        assert "huntsville" in match.city.lower()

    def test_no_match_below_cutoff_returns_none(self):
        # Gibberish should return None
        match = fuzzy_match_per_diem("zzzzzyyyxxxx", cutoff=0.6)
        assert match is None

    def test_result_has_lodging_and_mie(self):
        match = fuzzy_match_per_diem("New York City")
        assert match is not None
        assert match.lodging_usd > 0
        assert match.mie_usd > 0

    def test_empty_per_diem_data_returns_none(self, monkeypatch):
        monkeypatch.setattr(mod, "_per_diem_cache", [])
        result = fuzzy_match_per_diem("Paris")
        assert result is None
        # Restore
        _reset_per_diem_cache()

    def test_custom_cutoff_accepted(self):
        # With a very high cutoff, only exact matches pass.
        # "New York" is close but not exact to "New York City"; with cutoff=0.99 it may fail.
        match_low = fuzzy_match_per_diem("New York", cutoff=0.3)
        assert match_low is not None
        match_high = fuzzy_match_per_diem("zy", cutoff=0.99)
        assert match_high is None


# ── parse_destination_csv ─────────────────────────────────────────────────────


class TestParseCsv:
    def test_valid_minimal_csv(self):
        content = "iata\nNRT\nLAX"
        preview = parse_destination_csv(content)
        assert preview.parse_error == ""
        assert preview.valid_count == 2

    def test_valid_full_columns(self):
        content = "iata,city,country,region\nNRT,Tokyo,Japan,Asia Pacific"
        preview = parse_destination_csv(content)
        assert preview.parse_error == ""
        assert len(preview.rows) == 1
        row = preview.rows[0]
        assert row.iata == "NRT"
        assert row.city == "Tokyo"
        assert row.country == "Japan"
        assert row.region == "Asia Pacific"

    def test_iata_uppercased(self):
        content = "iata,city\nnrt,Tokyo"
        preview = parse_destination_csv(content)
        assert preview.rows[0].iata == "NRT"

    def test_missing_iata_column_returns_parse_error(self):
        content = "city,country\nTokyo,Japan"
        preview = parse_destination_csv(content)
        assert preview.parse_error != ""
        assert "iata" in preview.parse_error.lower()

    def test_empty_iata_row_is_error(self):
        content = "iata,city\n,Tokyo"
        preview = parse_destination_csv(content)
        row = preview.rows[0]
        assert not row.is_valid
        assert row.error != ""

    def test_iata_too_long_is_error(self):
        content = "iata,city\nTOOLONG,Tokyo"
        preview = parse_destination_csv(content)
        assert not preview.rows[0].is_valid

    def test_iata_one_char_is_error(self):
        content = "iata,city\nX,Tokyo"
        preview = parse_destination_csv(content)
        assert not preview.rows[0].is_valid

    def test_per_diem_match_on_known_city(self):
        content = "iata,city\nBHM,Birmingham"
        preview = parse_destination_csv(content)
        row = preview.rows[0]
        assert row.is_valid
        assert row.has_per_diem

    def test_per_diem_no_match_on_gibberish_city(self):
        content = "iata,city\nXXX,Zzzzyyy"
        preview = parse_destination_csv(content)
        row = preview.rows[0]
        assert row.is_valid
        assert not row.has_per_diem

    def test_preview_counts(self):
        content = "iata,city\nBHM,Birmingham\nXXX,Zzzzyyy\n,empty"
        preview = parse_destination_csv(content)
        assert preview.valid_count == 2
        assert preview.error_count == 1

    def test_matched_and_unmatched_counts(self):
        content = "iata,city\nBHM,Birmingham\nXXX,Zzzzyyy"
        preview = parse_destination_csv(content)
        assert preview.matched_count == 1
        assert preview.unmatched_count == 1

    def test_empty_content_no_crash(self):
        preview = parse_destination_csv("")
        # Either parse_error set or zero rows — should not raise.
        assert isinstance(preview, CsvImportPreview)

    def test_header_only_no_rows(self):
        content = "iata,city,country"
        preview = parse_destination_csv(content)
        assert preview.parse_error == ""
        assert preview.valid_count == 0

    def test_case_insensitive_column_names(self):
        content = "IATA,City,Country\nNRT,Tokyo,Japan"
        preview = parse_destination_csv(content)
        assert preview.parse_error == ""
        assert preview.rows[0].iata == "NRT"

    def test_csv_row_is_valid_property(self):
        valid = CsvRow(iata="NRT", city="Tokyo", country="Japan", region="")
        valid_no_city = CsvRow(iata="NRT", city="", country="", region="")
        invalid = CsvRow(
            iata="", city="Tokyo", country="Japan", region="", error="missing IATA"
        )
        assert valid.is_valid
        assert valid_no_city.is_valid
        assert not invalid.is_valid
