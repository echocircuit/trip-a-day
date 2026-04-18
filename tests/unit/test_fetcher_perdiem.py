"""Unit tests for per diem lookup and fallback chain in fetcher.py.

All tests run without network access — they patch the in-memory rate cache.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

SAMPLE_RATES = [
    {
        "city": "London",
        "state_or_country": "United Kingdom",
        "is_domestic": False,
        "lodging_usd": 200,
        "mie_usd": 80,
        "source": "state_dept",
    },
    {
        "city": "Manchester",
        "state_or_country": "United Kingdom",
        "is_domestic": False,
        "lodging_usd": 150,
        "mie_usd": 60,
        "source": "state_dept",
    },
    {
        "city": "New York",
        "state_or_country": "NY",
        "is_domestic": True,
        "lodging_usd": 350,
        "mie_usd": 100,
        "source": "gsa",
    },
]


def _patch_rates(rates=SAMPLE_RATES):
    return patch("trip_a_day.fetcher._load_per_diem", return_value=rates)


def test_exact_city_match_international():
    from trip_a_day.fetcher import _lookup_per_diem

    with _patch_rates():
        lodging, mie, source = _lookup_per_diem("London", "United Kingdom", False)

    assert lodging == 200.0
    assert mie == 80.0
    assert source == "per_diem_exact"


def test_exact_city_match_domestic():
    from trip_a_day.fetcher import _lookup_per_diem

    with _patch_rates():
        lodging, mie, source = _lookup_per_diem("New York", "NY", True)

    assert lodging == 350.0
    assert mie == 100.0
    assert source == "per_diem_exact"


def test_country_average_fallback():
    """When city is unknown, average across all cities in that country."""
    from trip_a_day.fetcher import _lookup_per_diem

    with _patch_rates():
        lodging, mie, source = _lookup_per_diem("Bristol", "United Kingdom", False)

    assert lodging == pytest.approx(175.0)
    assert mie == pytest.approx(70.0)
    assert source == "per_diem_country"


def test_regional_fallback_when_no_country_data():
    """When country has no per diem entries, _lookup_per_diem returns fallback sentinel."""
    from trip_a_day.fetcher import _lookup_per_diem

    with _patch_rates([]):  # empty rates — no matches possible
        lodging, mie, source = _lookup_per_diem("Nairobi", "Kenya", False)

    assert lodging == 0.0
    assert mie == 0.0
    assert source == "fallback"


def test_case_insensitive_city_match():
    from trip_a_day.fetcher import _lookup_per_diem

    with _patch_rates():
        _lodging, _mie, source = _lookup_per_diem("LONDON", "United Kingdom", False)

    assert source == "per_diem_exact"


def test_domestic_does_not_match_international():
    """is_domestic flag must match — domestic query won't return international record."""
    from trip_a_day.fetcher import _lookup_per_diem

    with _patch_rates():
        # London is international (is_domestic=False); querying as domestic should miss
        _lodging, _mie, source = _lookup_per_diem("London", "United Kingdom", True)

    assert source == "fallback"
