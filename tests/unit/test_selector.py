"""Unit tests for destination selection strategies (selector.py)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trip_a_day.db import Base, Destination
from trip_a_day.selector import STRATEGIES, STRATEGY_LABELS, select_daily_batch

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'selector_test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as s:
        yield s


def _add_dest(
    session,
    iata: str,
    region: str = "North America",
    *,
    enabled: bool = True,
    excluded: bool = False,
    last_queried_at: datetime | None = None,
    query_count: int = 0,
    user_favorited: bool = False,
) -> Destination:
    d = Destination(
        iata_code=iata,
        city=iata,
        country="Test",
        region=region,
        enabled=enabled,
        excluded=excluded,
        last_queried_at=last_queried_at,
        query_count=query_count,
        user_favorited=user_favorited,
    )
    session.add(d)
    session.flush()
    return d


# ── Metadata ──────────────────────────────────────────────────────────────────


def test_strategy_labels_covers_all_strategies():
    assert set(STRATEGIES) == set(STRATEGY_LABELS.keys())


def test_select_daily_batch_unknown_strategy_falls_back_to_lrq(session):
    _add_dest(session, "AAA")
    result = select_daily_batch("nonexistent_strategy", 5, session)
    assert len(result) == 1
    assert result[0].iata_code == "AAA"


# ── Pool filtering ────────────────────────────────────────────────────────────


def test_disabled_destinations_excluded_from_pool(session):
    _add_dest(session, "AAA", enabled=True)
    _add_dest(session, "BBB", enabled=False)
    result = select_daily_batch("least_recently_queried", 10, session)
    iatas = {d.iata_code for d in result}
    assert "AAA" in iatas
    assert "BBB" not in iatas


def test_excluded_destinations_excluded_from_pool(session):
    _add_dest(session, "AAA", excluded=False)
    _add_dest(session, "BBB", excluded=True)
    result = select_daily_batch("least_recently_queried", 10, session)
    iatas = {d.iata_code for d in result}
    assert "AAA" in iatas
    assert "BBB" not in iatas


def test_empty_pool_returns_empty_list(session):
    result = select_daily_batch("random", 5, session)
    assert result == []


# ── least_recently_queried ────────────────────────────────────────────────────


def test_lrq_nulls_come_first(session):
    now = datetime.now(UTC)
    _add_dest(session, "OLD", last_queried_at=now)
    _add_dest(session, "NEW", last_queried_at=None)
    result = select_daily_batch("least_recently_queried", 2, session)
    assert result[0].iata_code == "NEW"


def test_lrq_respects_batch_size(session):
    for i in range(10):
        _add_dest(session, f"A{i:02d}")
    result = select_daily_batch("least_recently_queried", 3, session)
    assert len(result) == 3


# ── random ────────────────────────────────────────────────────────────────────


def test_random_returns_correct_count(session):
    for i in range(5):
        _add_dest(session, f"R{i}")
    result = select_daily_batch("random", 3, session)
    assert len(result) == 3
    assert len({d.iata_code for d in result}) == 3


def test_random_never_exceeds_pool_size(session):
    _add_dest(session, "X01")
    _add_dest(session, "X02")
    result = select_daily_batch("random", 10, session)
    assert len(result) == 2


# ── round_robin ───────────────────────────────────────────────────────────────


def test_round_robin_advances_offset(session):
    for code in ["AAA", "BBB", "CCC"]:
        _add_dest(session, code)

    first = {d.iata_code for d in select_daily_batch("round_robin", 1, session)}
    session.commit()
    second = {d.iata_code for d in select_daily_batch("round_robin", 1, session)}
    session.commit()
    # Two consecutive single-item batches must pick different destinations.
    assert first != second


def test_round_robin_wraps_around(session):
    for code in ["AAA", "BBB"]:
        _add_dest(session, code)

    all_seen: set[str] = set()
    for _ in range(4):
        batch = select_daily_batch("round_robin", 1, session)
        all_seen.update(d.iata_code for d in batch)
        session.commit()

    assert all_seen == {"AAA", "BBB"}


# ── maximize_short_term_region_variety ────────────────────────────────────────


def test_short_term_variety_picks_from_multiple_regions(session):
    for i in range(3):
        _add_dest(session, f"NA{i}", region="North America")
    for i in range(3):
        _add_dest(session, f"EU{i}", region="Western Europe")

    result = select_daily_batch("maximize_short_term_region_variety", 2, session)
    regions = {d.region for d in result}
    assert len(regions) == 2


# ── maximize_long_term_region_variety ────────────────────────────────────────


def test_long_term_variety_returns_correct_count(session):
    for i in range(5):
        _add_dest(session, f"LT{i}", region="South America")
    result = select_daily_batch("maximize_long_term_region_variety", 3, session)
    assert len(result) == 3


# ── cycle_through_regions ─────────────────────────────────────────────────────


def test_cycle_through_regions_advances_region(session):
    for i in range(2):
        _add_dest(session, f"NA{i}", region="North America")
    for i in range(2):
        _add_dest(session, f"EU{i}", region="Western Europe")

    first_batch = select_daily_batch("cycle_through_regions", 5, session)
    first_region = first_batch[0].region
    session.commit()
    second_batch = select_daily_batch("cycle_through_regions", 5, session)
    second_region = second_batch[0].region
    assert first_region != second_region


# ── proportional_by_region ───────────────────────────────────────────────────


def test_proportional_by_region_correct_total(session):
    for i in range(6):
        _add_dest(session, f"NA{i}", region="North America")
    for i in range(4):
        _add_dest(session, f"EU{i}", region="Western Europe")
    result = select_daily_batch("proportional_by_region", 5, session)
    assert len(result) == 5


def test_proportional_by_region_both_regions_represented(session):
    for i in range(6):
        _add_dest(session, f"NA{i}", region="North America")
    for i in range(4):
        _add_dest(session, f"EU{i}", region="Western Europe")
    result = select_daily_batch("proportional_by_region", 10, session)
    regions = {d.region for d in result}
    assert "North America" in regions
    assert "Western Europe" in regions


# ── favorites_first ───────────────────────────────────────────────────────────


def test_favorites_first_puts_favorites_at_top(session):
    _add_dest(session, "FAV", user_favorited=True)
    _add_dest(session, "REG")
    result = select_daily_batch("favorites_first", 2, session)
    assert result[0].iata_code == "FAV"


def test_favorites_first_fills_with_lrq(session):
    _add_dest(session, "FAV", user_favorited=True)
    now = datetime.now(UTC)
    _add_dest(session, "OLD", user_favorited=False, last_queried_at=now)
    _add_dest(session, "NEW", user_favorited=False, last_queried_at=None)
    result = select_daily_batch("favorites_first", 3, session)
    iatas = [d.iata_code for d in result]
    assert iatas[0] == "FAV"
    assert "NEW" in iatas
    assert "OLD" in iatas


# ── pool parameter (pre-filtered pool passed in) ──────────────────────────────


def test_pool_parameter_draws_from_pool_not_db(session):
    """When pool is provided, strategy ignores DB and draws from pool only."""
    _add_dest(session, "DB1", region="North America")
    _add_dest(session, "DB2", region="North America")
    # Pool contains only one destination not in DB
    pool_dest = Destination(
        iata_code="POOL",
        city="Pool City",
        country="Test",
        region="Western Europe",
        enabled=True,
        excluded=False,
    )
    result = select_daily_batch("least_recently_queried", 5, session, pool=[pool_dest])
    assert len(result) == 1
    assert result[0].iata_code == "POOL"


def test_pool_parameter_blocklist_scenario(session):
    """Simulates the blocklist bug: with NA blocklist, batch must not contain NA."""
    # DB has 10 NA destinations + 3 European ones
    for i in range(10):
        _add_dest(session, f"NA{i:02d}", region="North America")
    eu1 = _add_dest(session, "EU1", region="Western Europe")
    eu2 = _add_dest(session, "EU2", region="Western Europe")
    eu3 = _add_dest(session, "EU3", region="Eastern Europe")

    # Simulate apply_destination_filters removing NA from pool
    eligible_pool = [eu1, eu2, eu3]
    result = select_daily_batch(
        "least_recently_queried", 5, session, pool=eligible_pool
    )
    regions = {d.region for d in result}
    assert "North America" not in regions
    assert len(result) == 3  # only 3 eligible destinations


def test_pool_parameter_empty_returns_empty(session):
    _add_dest(session, "DB1")
    result = select_daily_batch("least_recently_queried", 5, session, pool=[])
    assert result == []


def test_all_strategies_respect_pool_parameter(session):
    """Smoke test: every strategy returns only pool destinations."""
    _add_dest(session, "DB1", region="North America")
    pool_dest = _add_dest(session, "EU1", region="Western Europe")

    for strategy in STRATEGIES:
        result = select_daily_batch(strategy, 5, session, pool=[pool_dest])
        iatas = {d.iata_code for d in result}
        assert "DB1" not in iatas, f"Strategy {strategy!r} leaked DB dest outside pool"
        session.commit()  # round_robin / cycle_through_regions update offset prefs
