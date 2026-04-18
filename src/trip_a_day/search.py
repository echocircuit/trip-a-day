"""Trip search and cheapest-trip selection."""

from __future__ import annotations

from collections.abc import Iterable

from trip_a_day.models import Trip


def find_cheapest_trip(trips: Iterable[Trip]) -> Trip | None:
    """Return the cheapest trip in ``trips``, or ``None`` if empty.

    Ties are broken by the iteration order of the input.
    """
    return min(trips, key=lambda t: t.price_cents, default=None)
