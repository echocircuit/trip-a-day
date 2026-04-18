"""Typed read/write helpers for the preferences table."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from trip_a_day.db import Preference


def get(session: Session, key: str) -> str:
    """Return the raw string value for *key*, raising KeyError if missing."""
    row = session.get(Preference, key)
    if row is None or row.value is None:
        raise KeyError(f"Preference '{key}' not found")
    return row.value


def get_or(session: Session, key: str, default: str) -> str:
    """Return the raw string value for *key*, or *default* if missing."""
    try:
        return get(session, key)
    except KeyError:
        return default


def get_int(session: Session, key: str) -> int:
    return int(get(session, key))


def get_bool(session: Session, key: str) -> bool:
    return get(session, key).strip().lower() == "true"


def get_json(session: Session, key: str) -> Any:
    val = get(session, key)
    return json.loads(val)


def set_pref(session: Session, key: str, value: str) -> None:
    """Write *value* for *key*, creating the row if it does not exist."""
    row = session.get(Preference, key)
    if row is None:
        session.add(Preference(key=key, value=value, updated_at=datetime.utcnow()))
    else:
        row.value = value
        row.updated_at = datetime.utcnow()
    session.flush()


def get_all(session: Session) -> dict[str, str]:
    """Return all preferences as a plain dict (raw string values)."""
    rows = session.query(Preference).all()
    return {r.key: r.value or "" for r in rows}
