from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def _safe_tz(tz_name: str):
    try:
        return ZoneInfo(tz_name or "UTC"), (tz_name or "UTC")
    except Exception:
        return timezone.utc, "UTC"


def day_bounds_utc(tz_name: str, now_utc: datetime | None = None) -> tuple[datetime, datetime, str, str]:
    now_utc = now_utc or utcnow()
    tz, tz_norm = _safe_tz(tz_name)
    local_now = now_utc.astimezone(tz)
    d = local_now.date()

    local_start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc), d.isoformat(), tz_norm


def week_bounds_utc(tz_name: str, now_utc: datetime | None = None) -> tuple[datetime, datetime, str, str]:
    now_utc = now_utc or utcnow()
    tz, tz_norm = _safe_tz(tz_name)
    local_now = now_utc.astimezone(tz)
    d = local_now.date()

    monday = d - timedelta(days=d.weekday())
    local_start = datetime(monday.year, monday.month, monday.day, 0, 0, 0, tzinfo=tz)
    local_end = local_start + timedelta(days=7)
    label = f"{monday.isoformat()}..{(monday + timedelta(days=6)).isoformat()}"
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc), label, tz_norm


def month_bounds_utc(tz_name: str, now_utc: datetime | None = None) -> tuple[datetime, datetime, str, str]:
    now_utc = now_utc or utcnow()
    tz, tz_norm = _safe_tz(tz_name)
    local_now = now_utc.astimezone(tz)

    y, m = local_now.year, local_now.month
    local_start = datetime(y, m, 1, 0, 0, 0, tzinfo=tz)

    if m == 12:
        ny, nm = y + 1, 1
    else:
        ny, nm = y, m + 1
    local_end = datetime(ny, nm, 1, 0, 0, 0, tzinfo=tz)

    label = f"{y:04d}-{m:02d}"
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc), label, tz_norm


async def report_period(db: aiosqlite.Connection, user_id: int, start: datetime, end: datetime):
    cur = await db.execute(
        "SELECT "
        "SUM(CASE WHEN type='income' THEN amount ELSE 0 END) as income, "
        "SUM(CASE WHEN type='expense' THEN -amount ELSE 0 END) as expense, "
        "COUNT(*) as cnt "
        "FROM transactions WHERE user_id=? AND ts>=? AND ts<?",
        (user_id, iso(start), iso(end)),
    )
    row = await cur.fetchone()
    income = int(row[0] or 0)
    expense = int(row[1] or 0)
    cnt = int(row[2] or 0)
    return income, expense, cnt


async def report_by_category(
    db: aiosqlite.Connection,
    user_id: int,
    start: datetime,
    end: datetime,
    kind: str = "expense",
    limit: int = 10,
):
    if kind == "expense":
        sign_expr = "-t.amount"
        where_type = "expense"
    else:
        sign_expr = "t.amount"
        where_type = "income"

    cur = await db.execute(
        f"SELECT c.name, c.emoji, SUM({sign_expr}) as total "
        "FROM transactions t LEFT JOIN categories c ON c.id=t.category_id "
        "WHERE t.user_id=? AND t.type=? AND t.ts>=? AND t.ts<? "
        "GROUP BY c.name, c.emoji ORDER BY total DESC LIMIT ?",
        (user_id, where_type, iso(start), iso(end), limit),
    )
    return await cur.fetchall()
