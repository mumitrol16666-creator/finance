"""User-timezone-aware datetime helpers — single source of truth.

The bot has a per-user ``settings.timezone`` (IANA name, default ``Asia/Aqtobe``)
but historically many call sites used ``datetime.now()`` or ``date.today()``,
which read the *server* timezone. That meant "month start" for budgets, daily
reports, and AI context could disagree near midnight or month boundaries.

These helpers are the only correct way to get "now in the user's timezone".
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9 — should never happen on supported runtimes.
    ZoneInfo = None  # type: ignore[assignment]

import aiosqlite

DEFAULT_TZ = "Asia/Aqtobe"


def _zone(tz_name: Optional[str]):
    name = (tz_name or DEFAULT_TZ).strip()
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        try:
            return ZoneInfo(DEFAULT_TZ)
        except Exception:
            return timezone.utc


async def _get_tz(db: aiosqlite.Connection, user_id: int) -> str:
    cur = await db.execute("SELECT timezone FROM settings WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    return (str(row[0]) if row and row[0] else DEFAULT_TZ)


async def now_in_user_tz(db: aiosqlite.Connection, user_id: int) -> datetime:
    """Return aware ``datetime`` for the user's current local time."""
    tz_name = await _get_tz(db, user_id)
    return datetime.now(timezone.utc).astimezone(_zone(tz_name))


async def today_in_user_tz(db: aiosqlite.Connection, user_id: int) -> date:
    return (await now_in_user_tz(db, user_id)).date()


async def user_month_key(db: aiosqlite.Connection, user_id: int) -> str:
    """Return ``YYYY-MM`` for the user's local month."""
    return (await now_in_user_tz(db, user_id)).strftime("%Y-%m")


def to_user_tz(dt: datetime, tz_name: Optional[str]) -> datetime:
    """Convert an aware ``datetime`` into the user's local zone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_zone(tz_name))


def utcnow() -> datetime:
    """Aware UTC ``now()`` — use this instead of the deprecated ``datetime.utcnow()``."""
    return datetime.now(timezone.utc)
