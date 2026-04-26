"""Price history chart generation for notification emails."""

from __future__ import annotations

import io
import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def generate_price_history_chart(
    destination_iata: str,
    destination_name: str,
    today_cost: float,
    today_run_date: date,
    db_session: Session,
) -> bytes | None:
    """Return PNG image bytes, or None if insufficient data for both series.

    Series 1: historical prices for this destination (all recorded history).
    Series 2: recent daily Trip of the Day costs for the past 7 days.
    Returns None when Series 1 < 3 points AND Series 2 < 2 points.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
        import matplotlib.ticker as mticker
    except ImportError:
        logger.warning("matplotlib not available; skipping price history chart.")
        return None

    try:
        from sqlalchemy import func

        from trip_a_day.db import Destination, Trip

        # Series 1: full price history for this destination
        s1_rows = (
            db_session.query(
                Trip.run_date,
                func.min(Trip.total_cost_usd).label("total_cost_usd"),
            )
            .filter(Trip.destination_iata == destination_iata)
            .group_by(Trip.run_date)
            .order_by(Trip.run_date)
            .all()
        )

        # Series 2: recent daily Trip of the Day (selected winner, past 7 days)
        seven_days_ago = today_run_date - timedelta(days=7)
        s2_rows = (
            db_session.query(
                Trip.run_date,
                Trip.total_cost_usd,
                Trip.destination_iata,
                Destination.city,
            )
            .join(
                Destination,
                Trip.destination_iata == Destination.iata_code,
                isouter=True,
            )
            .filter(
                Trip.selected == True,  # noqa: E712
                Trip.run_date >= seven_days_ago,
            )
            .order_by(Trip.run_date)
            .all()
        )

        s1_dates = [row.run_date for row in s1_rows]
        s1_costs = [row.total_cost_usd for row in s1_rows]
        s2_dates = [row.run_date for row in s2_rows]
        s2_costs = [row.total_cost_usd for row in s2_rows]
        s2_cities = [row.city or row.destination_iata for row in s2_rows]

        has_s1 = len(s1_dates) >= 3
        has_s2 = len(s2_dates) >= 2

        if not has_s1 and not has_s2:
            return None

        def _to_dt(d: date) -> datetime:
            return datetime(d.year, d.month, d.day)

        # 600x330 px at 150 dpi — slightly taller than v1 for two series + annotations
        fig, ax = plt.subplots(figsize=(4.0, 2.2), dpi=150)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        if has_s1:
            plot_dates_s1 = [_to_dt(d) for d in s1_dates]
            x_s1: list[float] = list(mdates.date2num(plot_dates_s1))

            # Rolling average: 7-point window if ≥7 points, else all-time mean flat line
            n = len(s1_costs)
            if n < 7:
                avg = sum(s1_costs) / n
                rolling = [avg] * n
            else:
                rolling = []
                for i in range(n):
                    start = max(0, i - 6)
                    chunk = s1_costs[start : i + 1]
                    rolling.append(sum(chunk) / len(chunk))

            city_label = destination_name.split(",")[0].strip()
            ax.plot(
                x_s1,
                s1_costs,
                color="#1a6496",
                linewidth=1.5,
                marker="o",
                markersize=3,
                label=f"{city_label} price history",
            )
            ax.plot(
                x_s1,
                rolling,
                color="#999999",
                linewidth=1.0,
                linestyle=":",
                label="Rolling avg",
            )

            # Today's highlighted point on Series 1
            today_idx = next(
                (i for i, d in enumerate(s1_dates) if d == today_run_date),
                len(s1_dates) - 1,
            )
            today_x_s1: float = x_s1[today_idx]
            ax.plot(
                today_x_s1,
                s1_costs[today_idx],
                "o",
                color="#e67e22",
                markersize=7,
                zorder=5,
            )
            ax.axvline(
                today_x_s1,
                color="#e67e22",
                linestyle="--",
                linewidth=0.8,
                alpha=0.7,
                label="Today",
            )

        if has_s2:
            plot_dates_s2 = [_to_dt(d) for d in s2_dates]
            x_s2: list[float] = list(mdates.date2num(plot_dates_s2))

            ax.plot(
                x_s2,
                s2_costs,
                color="#27ae60",
                linewidth=1.5,
                linestyle="--",
                marker="s",
                markersize=3,
                label="Recent daily picks",
            )

            # Annotate each green point with a short city name
            for xi, yi, city in zip(x_s2, s2_costs, s2_cities, strict=False):
                short = city.split(",")[0][:10] if city else "?"
                ax.annotate(
                    short,
                    (xi, yi),
                    textcoords="offset points",
                    xytext=(0, 5),
                    fontsize=4,
                    ha="center",
                    color="#27ae60",
                )

        # X-axis: derive range from whichever series are present
        all_dates = s1_dates + s2_dates
        if all_dates:
            date_range = (
                (max(all_dates) - min(all_dates)).days if len(all_dates) > 1 else 0
            )
            fmt = "%b %d" if date_range <= 60 else "%b '%y"
            ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
            plt.setp(
                ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=6
            )

        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax.tick_params(axis="y", labelsize=6)

        title_note = "" if has_s1 else " (limited history)"
        ax.set_title(
            f"Price History — {destination_name}{title_note}", fontsize=8, pad=4
        )
        ax.legend(fontsize=5, loc="best", framealpha=0.5)
        ax.grid(axis="y", linestyle=":", alpha=0.3, color="#cccccc")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        plt.tight_layout(pad=0.4)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except Exception as exc:
        logger.warning("Chart generation failed: %s", exc)
        return None
