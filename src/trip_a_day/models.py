"""Data models for trip-a-day."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Trip:
    """A single bookable trip option.

    Prices are stored in whole cents to avoid float rounding.
    """

    origin: str
    destination: str
    depart_date: date
    return_date: date
    price_cents: int
    provider: str

    @property
    def price(self) -> float:
        return self.price_cents / 100
