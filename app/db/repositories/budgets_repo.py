from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite


def month_key(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return f"{dt.year:04d}-{dt.month:02d}"


def next_month_key(month: str) -> str:
    y, m = int(month[:4]), int(month[5:7])
    if m == 12:
        return f"{y + 1:04d}-01"
    return f"{y:04d}-{m + 1:02d}"


def month_bounds(month: str) -> tuple[str, str]:
    start = f"{month}-01T00:00:00+00:00"
    end = f"{next_month_key(month)}-01T00:00:00+00:00"
    return start, end


async def get_category_budget(
    db: aiosqlite.Connection,
    user_id: int,
    month: str,
    category_id: int,
) -> int | None:
    cur = await db.execute(
        """
        SELECT limit_amount
        FROM budgets
        WHERE user_id=? AND month=? AND category_id=?
        LIMIT 1
        """,
        (user_id, month, category_id),
    )
    row = await cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None


async def upsert_budget(
    db: aiosqlite.Connection,
    user_id: int,
    month: str,
    category_id: int,
    amount: int,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        INSERT INTO budgets(user_id, month, category_id, limit_amount, created_at, updated_at)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(user_id, month, category_id) DO UPDATE SET
            limit_amount=excluded.limit_amount,
            updated_at=excluded.updated_at
        """,
        (user_id, month, category_id, int(amount), now, now),
    )


async def month_spent_by_category(
    db: aiosqlite.Connection,
    user_id: int,
    month: str,
    category_id: int,
) -> int:
    start, end = month_bounds(month)

    # Для расходов amount хранится отрицательным.
    # SUM(-amount) возвращает положительную сумму потраченного.
    cur = await db.execute(
        """
        SELECT COALESCE(SUM(-amount), 0)
        FROM transactions
        WHERE user_id=?
          AND type='expense'
          AND category_id=?
          AND ts>=?
          AND ts<?
        """,
        (user_id, category_id, start, end),
    )
    row = await cur.fetchone()
    return int(row[0] or 0)


async def month_budgets_map(
    db: aiosqlite.Connection,
    user_id: int,
    month: str,
) -> dict[int, int]:
    cur = await db.execute(
        """
        SELECT category_id, limit_amount
        FROM budgets
        WHERE user_id=? AND month=?
        """,
        (user_id, month),
    )
    rows = await cur.fetchall()
    return {
        int(category_id): int(limit_amount)
        for category_id, limit_amount in rows
        if category_id is not None and limit_amount is not None
    }


async def month_spent_map(
    db: aiosqlite.Connection,
    user_id: int,
    month: str,
) -> dict[int, int]:
    start, end = month_bounds(month)

    cur = await db.execute(
        """
        SELECT category_id, COALESCE(SUM(-amount), 0) AS spent
        FROM transactions
        WHERE user_id=?
          AND type='expense'
          AND ts>=?
          AND ts<?
          AND category_id IS NOT NULL
        GROUP BY category_id
        """,
        (user_id, start, end),
    )
    rows = await cur.fetchall()
    return {
        int(category_id): int(spent or 0)
        for category_id, spent in rows
        if category_id is not None
    }


async def month_limits_status_map(
    db: aiosqlite.Connection,
    user_id: int,
    month: str,
) -> dict[int, dict[str, int | str]]:
    """
    Возвращает карту статусов лимитов по категориям месяца.

    Формат:
    {
        category_id: {
            "limit": 5200,
            "spent": 2000,
            "left": 3200,
            "state": "ok" | "warn" | "over"
        }
    }

    state:
    - ok   : остаток > 20% лимита
    - warn : остаток <= 20% лимита, но еще не ушли в минус
    - over : перерасход
    """
    budgets = await month_budgets_map(db, user_id, month)
    spent = await month_spent_map(db, user_id, month)

    result: dict[int, dict[str, int | str]] = {}

    for category_id, limit_amount in budgets.items():
        spent_amount = int(spent.get(category_id, 0))
        left_amount = int(limit_amount) - spent_amount

        if left_amount < 0:
            state = "over"
        elif int(limit_amount) > 0 and left_amount <= int(limit_amount) * 0.2:
            state = "warn"
        else:
            state = "ok"

        result[int(category_id)] = {
            "limit": int(limit_amount),
            "spent": spent_amount,
            "left": left_amount,
            "state": state,
        }

    return result


async def get_category_limit_status(
    db: aiosqlite.Connection,
    user_id: int,
    month: str,
    category_id: int,
) -> dict[str, int | str] | None:
    limit_amount = await get_category_budget(db, user_id, month, category_id)
    if limit_amount is None:
        return None

    spent_amount = await month_spent_by_category(db, user_id, month, category_id)
    left_amount = int(limit_amount) - spent_amount

    if left_amount < 0:
        state = "over"
    elif int(limit_amount) > 0 and left_amount <= int(limit_amount) * 0.2:
        state = "warn"
    else:
        state = "ok"

    return {
        "limit": int(limit_amount),
        "spent": spent_amount,
        "left": left_amount,
        "state": state,
    }