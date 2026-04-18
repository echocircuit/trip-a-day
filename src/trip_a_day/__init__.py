"""trip_a_day — determines the cheapest trip that can be booked each day."""

from trip_a_day.models import Trip
from trip_a_day.search import find_cheapest_trip

__version__ = "0.1.0"

__all__ = ["Trip", "__version__", "find_cheapest_trip"]
