"""APScheduler daily runner for trip-a-day.

Usage:
    python scheduler.py

Reads the 'scheduled_run_time' preference (HH:MM, local time; default 07:00)
and fires the full trip pipeline once per calendar day at that time.
Keep this process running in the foreground or register it with your OS
init system (launchd on macOS, systemd on Linux, Task Scheduler on Windows).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import main as _main
from apscheduler.schedulers.blocking import BlockingScheduler

from trip_a_day.db import SessionFactory, init_db, seed_preferences
from trip_a_day.preferences import get_or

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scheduler")


def _scheduled_run() -> None:
    logger.info("Scheduler triggered — starting daily run.")
    try:
        _main.run(triggered_by="scheduler")
    except SystemExit as exc:
        logger.error("Daily run exited with code %s.", exc.code)
    except Exception as exc:
        logger.error("Daily run raised an unexpected error: %s", exc, exc_info=True)


def main() -> None:
    init_db()
    with SessionFactory() as session:
        seed_preferences(session)
        session.commit()
        run_time = get_or(session, "scheduled_run_time", "07:00")

    try:
        hour, minute = (int(p) for p in run_time.split(":"))
    except ValueError:
        logger.error(
            "Invalid scheduled_run_time preference '%s'; expected HH:MM format.",
            run_time,
        )
        sys.exit(1)

    scheduler = BlockingScheduler()
    scheduler.add_job(_scheduled_run, "cron", hour=hour, minute=minute)
    logger.info(
        "Scheduler started — daily run at %02d:%02d local time.  Press Ctrl+C to stop.",
        hour,
        minute,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
