"""Price history chart generation for notification emails."""

from __future__ import annotations

import io
import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def generate_price_history_chart(
    destination_iata: str,
    destination_name: str,
    today_cost: float,
    db_session: Session,
) -> bytes | None:
    """Return PNG image bytes, or None if insufficient history.

    Caller is responsible for base64-encoding for email embedding.
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

        from trip_a_day.db import Trip

        rows = (
            db_session.query(
                Trip.run_date,
                func.min(Trip.total_cost_usd).label("total_cost_usd"),
            )
            .filter(Trip.destination_iata == destination_iata)
            .group_by(Trip.run_date)
            .order_by(Trip.run_date)
            .all()
        )

        if len(rows) < 3:
            return None

        raw_dates = [row.run_date for row in rows]
        costs = [row.total_cost_usd for row in rows]

        # Convert date → datetime for matplotlib date axis
        plot_dates = [datetime(d.year, d.month, d.day) for d in raw_dates]

        # Rolling average: 7-point window if ≥7 points, else all-time mean flat line
        n = len(costs)
        if n < 7:
            avg = sum(costs) / n
            rolling = [avg] * n
        else:
            rolling = []
            for i in range(n):
                start = max(0, i - 6)
                chunk = costs[start : i + 1]
                rolling.append(sum(chunk) / len(chunk))

        # Find today's highlight index
        today = date.today()
        today_idx = next(
            (i for i, d in enumerate(raw_dates) if d == today),
            len(raw_dates) - 1,
        )

        # Convert to float (matplotlib internal date format) to satisfy mypy
        x_vals: list[float] = list(mdates.date2num(plot_dates))
        today_x: float = x_vals[today_idx]

        # 600x250 px at 150 dpi -> figsize=(4.0, 1.667)
        fig, ax = plt.subplots(figsize=(4.0, 1.667), dpi=150)
        fig.patch.set_facecolor("white")
        ax.set_facecolor("white")

        ax.plot(
            x_vals,
            costs,
            color="#1a6496",
            linewidth=1.5,
            marker="o",
            markersize=3,
            label="Total cost",
        )
        ax.plot(
            x_vals,
            rolling,
            color="#999999",
            linewidth=1.0,
            linestyle="--",
            label="Rolling avg",
        )
        # Today's highlighted point
        ax.plot(
            today_x,
            costs[today_idx],
            "o",
            color="#e67e22",
            markersize=7,
            zorder=5,
        )
        ax.axvline(
            today_x,
            color="#e67e22",
            linestyle="--",
            linewidth=0.8,
            alpha=0.7,
            label="Today",
        )

        # X-axis: compact format for short spans, year suffix for long ones
        date_range = (raw_dates[-1] - raw_dates[0]).days if len(raw_dates) > 1 else 0
        fmt = "%b %d" if date_range <= 60 else "%b '%y"
        ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right", fontsize=6)

        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))
        ax.tick_params(axis="y", labelsize=6)

        ax.set_title(f"Price History — {destination_name}", fontsize=8, pad=4)
        ax.legend(fontsize=6, loc="upper right", framealpha=0.5)
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
