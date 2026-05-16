from __future__ import annotations
import aiosqlite
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import sqlite3


from app.db.repositories.settings_repo import get_timezone

def _iso(dt: datetime) -> str:
    return dt.isoformat()

async def _ensure_limits_tables(db: aiosqlite.Connection):
    await db.execute("""
    CREATE TABLE IF NOT EXISTS user_limits (
      user_id     INTEGER PRIMARY KEY,
      daily_limit INTEGER,
      created_at  TEXT NOT NULL,
      updated_at  TEXT NOT NULL
    );
    """)
    await db.execute("""
    CREATE TABLE IF NOT EXISTS category_limits (
      user_id     INTEGER NOT NULL,
      category_id INTEGER NOT NULL,
      daily_limit INTEGER,
      created_at  TEXT NOT NULL,
      updated_at  TEXT NOT NULL,
      PRIMARY KEY (user_id, category_id)
    );
    """)

async def _day_range_utc(db: aiosqlite.Connection, user_id: int, day_local: datetime | None = None) -> tuple[str,str]:
    tz_name = await get_timezone(db, user_id)
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    now_local = (day_local or datetime.now(timezone.utc).astimezone(tz))
    start_local = datetime(now_local.year, now_local.month, now_local.day, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return _iso(start_utc), _iso(end_utc)

async def _week_range_utc(db: aiosqlite.Connection, user_id: int, offset_weeks: int = 0) -> tuple[str,str]:
    tz_name = await get_timezone(db, user_id)
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    now_local = datetime.now(timezone.utc).astimezone(tz)
    # Monday = 0
    monday = now_local - timedelta(days=now_local.weekday())
    monday = datetime(monday.year, monday.month, monday.day, tzinfo=tz) + timedelta(weeks=offset_weeks)
    end = monday + timedelta(days=7)
    return _iso(monday.astimezone(timezone.utc)), _iso(end.astimezone(timezone.utc))

async def get_daily_limit(db: aiosqlite.Connection, user_id: int) -> int | None:
    try:
        cur = await db.execute("SELECT daily_limit FROM user_limits WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except sqlite3.OperationalError:
        # таблицы нет -> просто считаем, что лимит не задан
        return None

async def set_daily_limit(db: aiosqlite.Connection, user_id: int, amount: int):
    await _ensure_limits_tables(db)
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO user_limits(user_id, daily_limit, created_at, updated_at) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET daily_limit=excluded.daily_limit, updated_at=excluded.updated_at",
        (user_id, amount, now, now),
    )


async def get_category_daily_limit(db: aiosqlite.Connection, user_id: int, category_id: int) -> int | None:
    try:
        cur = await db.execute(
            "SELECT daily_limit FROM category_limits WHERE user_id=? AND category_id=?",
            (user_id, category_id),
        )
        row = await cur.fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except sqlite3.OperationalError:
        return None

async def set_category_daily_limit(db: aiosqlite.Connection, user_id: int, category_id: int, amount: int):
    await _ensure_limits_tables(db)
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT INTO category_limits(user_id, category_id, daily_limit, created_at, updated_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(user_id, category_id) DO UPDATE SET daily_limit=excluded.daily_limit, updated_at=excluded.updated_at",
        (user_id, category_id, amount, now, now),
    )

async def today_expense_total(db: aiosqlite.Connection, user_id: int) -> int:
    start, end = await _day_range_utc(db, user_id)
    cur = await db.execute(
        "SELECT COALESCE(SUM(-amount),0) FROM transactions WHERE user_id=? AND type='expense' AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, start, end),
    )
    row = await cur.fetchone()
    return int(row[0] or 0)

async def today_expense_total_by_category(db: aiosqlite.Connection, user_id: int, category_id: int) -> int:
    start, end = await _day_range_utc(db, user_id)
    cur = await db.execute(
        "SELECT COALESCE(SUM(-amount),0) FROM transactions WHERE user_id=? AND type='expense' AND category_id=? AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, category_id, start, end),
    )
    row = await cur.fetchone()
    return int(row[0] or 0)

async def week_expense_total(db: aiosqlite.Connection, user_id: int, offset_weeks: int = 0) -> int:
    start, end = await _week_range_utc(db, user_id, offset_weeks=offset_weeks)
    cur = await db.execute(
        "SELECT COALESCE(SUM(-amount),0) FROM transactions WHERE user_id=? AND type='expense' AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, start, end),
    )
    row = await cur.fetchone()
    return int(row[0] or 0)
