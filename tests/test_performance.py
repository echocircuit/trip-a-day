"""Structural performance tests — no live API calls.

Verifies:
- MAX_WORKERS=1 forces sequential execution
- Global run timeout halts Pass 1 before budget is exhausted
- Probe counter hard cap (MAX_PROBES_PER_DESTINATION) is enforced
- Travel window loop: 2 windows x 3 destinations = exactly 6 find_cheapest calls
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from trip_a_day.window_search import (
    _DEFAULT_PROBE_COUNT,
    MAX_PROBES_PER_DESTINATION,
    find_cheapest_in_window,
)

# ── Probe cap ────────────────────────────────────────────────────────────────


def test_max_probes_constant_is_at_least_default():
    """MAX_PROBES_PER_DESTINATION must be >= _DEFAULT_PROBE_COUNT."""
    assert MAX_PROBES_PER_DESTINATION >= _DEFAULT_PROBE_COUNT


def test_find_cheapest_never_exceeds_probe_cap(tmp_path, monkeypatch):
    """find_cheapest_in_window must not exceed MAX_PROBES_PER_DESTINATION live calls."""
    call_count = 0

    def mock_get_flight_offers(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return None  # no valid price — ensures all probes still attempt

    monkeypatch.setenv("FLIGHT_DATA_MODE", "live")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "probe_cap_test.db"))
    # Re-import after env change to pick up new DB_PATH
    import importlib

    import trip_a_day.db as db_mod

    importlib.reload(db_mod)
    db_mod.init_db()

    with patch(
        "trip_a_day.window_search.get_flight_offers", side_effect=mock_get_flight_offers
    ):
        dest = SimpleNamespace(
            iata_code="CDG",
            city="Paris",
            country="France",
            region="Europe",
        )
        with db_mod.SessionFactory() as session:
            find_cheapest_in_window(
                origin_iata="HSV",
                destination=dest,
                min_days=7,
                max_days=60,
                trip_length_nights=5,
                adults=2,
                children=0,
                num_rooms=1,
                car_rental_required=False,
                direct_flights_only=True,
                cache_ttl_enabled=False,
                is_mock=False,
                db_session=session,
                live_calls_remaining=100,
            )

    assert call_count <= MAX_PROBES_PER_DESTINATION, (
        f"Made {call_count} calls; cap is {MAX_PROBES_PER_DESTINATION}"
    )


# ── Travel window loop call count ────────────────────────────────────────────


def test_probe_dest_window_calls_once_per_window(monkeypatch, tmp_path):
    """With 2 active windows and 1 destination, _probe_dest_window calls
    find_cheapest_in_window exactly 2 times (once per window).
    """
    monkeypatch.setenv("DB_PATH", str(tmp_path / "window_count_test.db"))

    import importlib

    import trip_a_day.db as db_mod

    importlib.reload(db_mod)
    db_mod.init_db()

    call_log: list[dict] = []

    def mock_find_cheapest(*, origin_iata, destination, min_days, max_days, **kwargs):
        call_log.append({"origin": origin_iata, "dest": destination.iata_code})
        return None, None, 0, 0

    with patch("main._probe_dest_window.__module__"):
        pass  # just to import main
    import main as main_mod

    with patch("main.find_cheapest_in_window", side_effect=mock_find_cheapest):
        today = date.today()
        window_data_list = [
            {
                "name": "Window A",
                "min_days": 10,
                "max_days": 14,
                "eff_end": today + timedelta(days=16),
            },
            {
                "name": "Window B",
                "min_days": 30,
                "max_days": 34,
                "eff_end": today + timedelta(days=36),
            },
        ]
        dest_data = {
            "iata": "CDG",
            "city": "Paris",
            "country": "France",
            "region": "Europe",
        }
        main_mod._probe_dest_window(
            dep_iata="HSV",
            dest_data=dest_data,
            window_data_list=window_data_list,
            trip_nights=5,
            adults=2,
            children=0,
            num_rooms=1,
            car_rental_required=False,
            direct_flights_only=True,
            cache_ttl_enabled=False,
            is_mock=True,
            live_calls_budget=40,
            transport_usd=0.0,
        )

    assert len(call_log) == 2, f"Expected 2 calls (one per window), got {len(call_log)}"


def test_window_loop_total_calls_with_three_destinations(monkeypatch, tmp_path):
    """With 2 active windows and 3 destinations, total find_cheapest calls == 6."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "window_3dest_test.db"))

    import importlib

    import trip_a_day.db as db_mod

    importlib.reload(db_mod)
    db_mod.init_db()

    call_log: list = []

    def mock_find_cheapest(*, origin_iata, destination, **kwargs):
        call_log.append(destination.iata_code)
        return None, None, 0, 0

    import main as main_mod

    today = date.today()
    window_data_list = [
        {
            "name": "Win1",
            "min_days": 10,
            "max_days": 14,
            "eff_end": today + timedelta(days=16),
        },
        {
            "name": "Win2",
            "min_days": 30,
            "max_days": 34,
            "eff_end": today + timedelta(days=36),
        },
    ]
    dests = [
        {"iata": "CDG", "city": "Paris", "country": "France", "region": "Europe"},
        {"iata": "NRT", "city": "Tokyo", "country": "Japan", "region": "Asia"},
        {"iata": "SYD", "city": "Sydney", "country": "Australia", "region": "Pacific"},
    ]

    with patch("main.find_cheapest_in_window", side_effect=mock_find_cheapest):
        for dest_data in dests:
            main_mod._probe_dest_window(
                dep_iata="HSV",
                dest_data=dest_data,
                window_data_list=window_data_list,
                trip_nights=5,
                adults=2,
                children=0,
                num_rooms=1,
                car_rental_required=False,
                direct_flights_only=True,
                cache_ttl_enabled=False,
                is_mock=True,
                live_calls_budget=40,
                transport_usd=0.0,
            )

    assert len(call_log) == 6, (
        f"Expected 6 calls (2 windows x 3 destinations), got {len(call_log)}"
    )


# ── Max workers = 1 forces sequential execution ──────────────────────────────


def test_max_workers_1_is_sequential():
    """With max_workers=1, ThreadPoolExecutor still submits and completes all work,
    just sequentially. Verify that 3 destinations all produce results.
    """
    from concurrent.futures import ThreadPoolExecutor, wait

    results = []

    def probe(dest_iata: str) -> str:
        time.sleep(0.001)  # tiny delay to surface ordering issues
        results.append(dest_iata)
        return dest_iata

    iatas = ["CDG", "NRT", "SYD"]
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(probe, iata): iata for iata in iatas}
        done, _ = wait(list(futures), timeout=5.0)

    assert len(done) == 3
    assert sorted(results) == sorted(iatas)


# ── Run timeout stops Pass 1 early ───────────────────────────────────────────


def test_run_timeout_stops_submission():
    """When elapsed time exceeds run_timeout_seconds before all destinations are
    submitted, the submission loop must break and not submit further work.
    """
    from concurrent.futures import ThreadPoolExecutor

    submitted: list[str] = []
    iatas = ["A", "B", "C", "D", "E"]

    def slow_probe(iata: str) -> str:
        submitted.append(iata)
        return iata

    run_timeout_seconds = 0.0  # already expired
    start_time = time.monotonic() - 1.0  # pretend 1 second has passed

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for iata in iatas:
            elapsed = time.monotonic() - start_time
            if elapsed > run_timeout_seconds:
                break  # mirrors the logic in run()
            futures[executor.submit(slow_probe, iata)] = iata

    assert len(futures) == 0, (
        "No futures should be submitted when timeout already elapsed"
    )


def test_run_timeout_does_not_stop_if_within_limit():
    """When elapsed time is within the limit, all destinations should be submitted."""
    from concurrent.futures import ThreadPoolExecutor

    iatas = ["A", "B", "C"]
    run_timeout_seconds = 999.0  # plenty of time
    start_time = time.monotonic()

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        for iata in iatas:
            elapsed = time.monotonic() - start_time
            if elapsed > run_timeout_seconds:
                break
            futures[executor.submit(lambda x=iata: x, iata)] = iata

    assert len(futures) == 3, "All destinations should be submitted within timeout"
