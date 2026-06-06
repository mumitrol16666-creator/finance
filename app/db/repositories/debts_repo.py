from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import aiosqlite

DATE_FMT = "%Y-%m-%d"


def _calc_status(next_payment_date: str | None, is_active: int = 1, today: date | None = None) -> str:
    if not is_active:
        return "closed"

    if not next_payment_date:
        return "active"

    try:
        due = datetime.strptime(next_payment_date, DATE_FMT).date()
    except Exception:
        return "active"

    if today is None:
        today = date.today()

    if due < today:
        return "overdue"
    if due == today:
        return "due_today"
    return "active"


def _row_get(row, key: str, index: int):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "keys"):
        return row[key]
    return row[index]


async def refresh_debt_status(
    db: aiosqlite.Connection,
    debt_id: int,
    *,
    commit: bool = False,
) -> None:
    cur = await db.execute(
        """
        SELECT next_payment_date, is_active, user_id
        FROM debts
        WHERE id = ?
        """,
        (debt_id,),
    )
    row = await cur.fetchone()
    if not row:
        return

    next_payment_date = _row_get(row, "next_payment_date", 0)
    is_active = int(_row_get(row, "is_active", 1) or 0)
    user_id = int(_row_get(row, "user_id", 2) or 0)
    from app.domain.time_utils import today_in_user_tz
    today = await today_in_user_tz(db, user_id) if user_id else None
    status = _calc_status(next_payment_date, is_active, today=today)

    await db.execute(
        """
        UPDATE debts
        SET status = ?,
            updated_at = datetime('now')
        WHERE id = ?
        """,
        (status, debt_id),
    )

    if commit:
        await db.commit()


async def refresh_all_debt_statuses(
    db: aiosqlite.Connection,
    user_id: int,
    *,
    commit: bool = False,
) -> None:
    from app.domain.time_utils import today_in_user_tz
    today = await today_in_user_tz(db, user_id)
    cur = await db.execute(
        """
        SELECT id, next_payment_date, is_active
        FROM debts
        WHERE user_id = ?
        """,
        (user_id,),
    )
    rows = await cur.fetchall()

    updates: list[tuple[str, int]] = []

    for row in rows:
        debt_id = int(_row_get(row, "id", 0))
        next_payment_date = _row_get(row, "next_payment_date", 1)
        is_active = int(_row_get(row, "is_active", 2) or 0)
        status = _calc_status(next_payment_date, is_active, today=today)
        updates.append((status, debt_id))

    if updates:
        await db.executemany(
            """
            UPDATE debts
            SET status = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            updates,
        )

    if commit:
        await db.commit()


async def add_debt(
    db: aiosqlite.Connection,
    user_id: int,
    direction: str,   # 'out' / 'in'
    dtype: str,       # 'bank' / 'private'
    title: str,
    payment_amount: Optional[int],
    next_payment_date: Optional[str],  # YYYY-MM-DD
    remaining_amount: Optional[int],
) -> int:
    status = _calc_status(next_payment_date, 1)

    cur = await db.execute(
        """
        INSERT INTO debts (
            user_id,
            direction,
            dtype,
            title,
            total_amount,
            payment_amount,
            next_payment_date,
            remaining_amount,
            is_active,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, datetime('now'), datetime('now'))
        """,
        (
            user_id,
            direction,
            dtype,
            title,
            remaining_amount, # total_amount = starting remaining_amount
            payment_amount,
            next_payment_date,
            remaining_amount,
            status,
        ),
    )
    await db.commit()
    return int(cur.lastrowid)


async def list_active_debts(
    db: aiosqlite.Connection,
    user_id: int,
    direction: Optional[str] = None,
):
    await refresh_all_debt_statuses(db, user_id, commit=True)

    sql = """
        SELECT
            id,
            title,
            payment_amount,
            next_payment_date,
            remaining_amount,
            total_amount,
            dtype,
            direction,
            is_active,
            status
        FROM debts
        WHERE user_id = ? AND is_active = 1
    """
    args: list = [user_id]

    if direction:
        sql += " AND direction = ?"
        args.append(direction)

    sql += """
        ORDER BY
            CASE
                WHEN status = 'overdue' THEN 0
                WHEN status = 'due_today' THEN 1
                ELSE 2
            END,
            CASE
                WHEN next_payment_date IS NULL OR next_payment_date = '' THEN 1
                ELSE 0
            END,
            next_payment_date ASC,
            id DESC
    """

    cur = await db.execute(sql, tuple(args))
    return await cur.fetchall()


async def get_debt(
    db: aiosqlite.Connection,
    user_id: int,
    debt_id: int,
):
    cur = await db.execute(
        """
        SELECT *
        FROM debts
        WHERE id = ? AND user_id = ?
        """,
        (debt_id, user_id),
    )
    row = await cur.fetchone()

    if not row:
        return None

    next_payment_date = _row_get(row, "next_payment_date", 3)
    is_active = int(_row_get(row, "is_active", 7) or 0)

    status = _calc_status(next_payment_date, is_active)

    await db.execute(
        "UPDATE debts SET status=? WHERE id=?",
        (status, debt_id),
    )

    await db.commit()

    return row


async def count_active_debts(
    db: aiosqlite.Connection,
    user_id: int,
    direction: Optional[str] = None,
) -> int:
    if direction:
        cur = await db.execute(
            """
            SELECT COUNT(*)
            FROM debts
            WHERE user_id = ? AND is_active = 1 AND direction = ?
            """,
            (user_id, direction),
        )
    else:
        cur = await db.execute(
            """
            SELECT COUNT(*)
            FROM debts
            WHERE user_id = ? AND is_active = 1
            """,
            (user_id,),
        )

    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def debts_summary(
    db: aiosqlite.Connection,
    user_id: int,
):
    await refresh_all_debt_statuses(db, user_id, commit=True)

    cur = await db.execute(
        """
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN direction = 'out' AND is_active = 1
                    THEN COALESCE(remaining_amount, 0)
                    ELSE 0
                END
            ), 0) AS out_sum,

            COALESCE(SUM(
                CASE
                    WHEN direction = 'in' AND is_active = 1
                    THEN COALESCE(remaining_amount, 0)
                    ELSE 0
                END
            ), 0) AS in_sum,

            COALESCE(SUM(
                CASE
                    WHEN direction = 'out' AND is_active = 1
                    THEN 1
                    ELSE 0
                END
            ), 0) AS out_count,

            COALESCE(SUM(
                CASE
                    WHEN direction = 'in' AND is_active = 1
                    THEN 1
                    ELSE 0
                END
            ), 0) AS in_count,

            COALESCE(SUM(
                CASE
                    WHEN direction = 'out' AND is_active = 1 AND status = 'overdue'
                    THEN 1
                    ELSE 0
                END
            ), 0) AS overdue_out_count,

            COALESCE(SUM(
                CASE
                    WHEN direction = 'out' AND is_active = 1 AND status = 'due_today'
                    THEN 1
                    ELSE 0
                END
            ), 0) AS due_today_out_count
        FROM debts
        WHERE user_id = ?
        """,
        (user_id,),
    )
    return await cur.fetchone()


async def update_debt_fields(
    db: aiosqlite.Connection,
    user_id: int,
    debt_id: int,
    *,
    title: str | None = None,
    payment_amount: int | None = None,
    next_payment_date: str | None = None,
    remaining_amount: int | None = None,
) -> None:
    sets: list[str] = []
    args: list = []

    if title is not None:
        sets.append("title = ?")
        args.append(title)

    if payment_amount is not None:
        sets.append("payment_amount = ?")
        args.append(payment_amount)

    if next_payment_date is not None:
        sets.append("next_payment_date = ?")
        args.append(next_payment_date)

    if remaining_amount is not None:
        sets.append("remaining_amount = ?")
        args.append(remaining_amount)

    if not sets:
        return

    sets.append("updated_at = datetime('now')")
    args.extend([debt_id, user_id])

    sql = f"""
        UPDATE debts
        SET {', '.join(sets)}
        WHERE id = ? AND user_id = ?
    """
    await db.execute(sql, tuple(args))
    await refresh_debt_status(db, debt_id)
    await db.commit()


async def close_debt(
    db: aiosqlite.Connection,
    user_id: int,
    debt_id: int,
) -> None:
    await db.execute(
        """
        UPDATE debts
        SET is_active = 0,
            status = 'closed',
            remaining_amount = 0,
            updated_at = datetime('now')
        WHERE id = ? AND user_id = ?
        """,
        (debt_id, user_id),
    )
    await db.commit()


async def apply_debt_payment(
    db: aiosqlite.Connection,
    user_id: int,
    debt_id: int,
    payment_amount: int,
    next_payment_date: Optional[str],
    commit: bool = True,
) -> None:
    cur = await db.execute(
        """
        SELECT remaining_amount, is_active
        FROM debts
        WHERE id = ? AND user_id = ?
        """,
        (debt_id, user_id),
    )
    row = await cur.fetchone()
    if not row:
        return

    current_remaining = _row_get(row, "remaining_amount", 0)
    is_active = int(_row_get(row, "is_active", 1) or 0)

    if not is_active:
        return

    amount = max(0, int(payment_amount or 0))

    if current_remaining is None:
        new_remaining = None
    else:
        new_remaining = max(0, int(current_remaining) - amount)

    if new_remaining is not None and new_remaining <= 0:
        await db.execute(
            """
            UPDATE debts
            SET remaining_amount = 0,
                next_payment_date = ?,
                is_active = 0,
                status = 'closed',
                updated_at = datetime('now')
            WHERE id = ? AND user_id = ?
            """,
            (next_payment_date, debt_id, user_id),
        )
        if commit:
            await db.commit()
        return

    await db.execute(
        """
        UPDATE debts
        SET remaining_amount = ?,
            next_payment_date = ?,
            updated_at = datetime('now')
        WHERE id = ? AND user_id = ?
        """,
        (new_remaining, next_payment_date, debt_id, user_id),
    )
    await refresh_debt_status(db, debt_id)
    if commit:
        await db.commit()

async def list_due_debts_for_reminders(db: aiosqlite.Connection, user_id: int):
    cur = await db.execute(
        """
        SELECT id, title, payment_amount, next_payment_date, remaining_amount, dtype, direction, is_active
        FROM debts
        WHERE user_id = ? AND is_active = 1 AND next_payment_date IS NOT NULL AND next_payment_date != ''
        ORDER BY next_payment_date ASC
        """,
        (user_id,),
    )
    return await cur.fetchall()


async def debt_reminder_already_sent(db: aiosqlite.Connection, user_id: int, debt_id: int, reminder_kind: str, local_date: str) -> bool:
    cur = await db.execute(
        "SELECT 1 FROM debt_reminder_log WHERE user_id=? AND debt_id=? AND reminder_kind=? AND local_date=? LIMIT 1",
        (user_id, debt_id, reminder_kind, local_date),
    )
    return (await cur.fetchone()) is not None


async def mark_debt_reminder_sent(db: aiosqlite.Connection, user_id: int, debt_id: int, reminder_kind: str, local_date: str):
    await db.execute(
        "INSERT OR IGNORE INTO debt_reminder_log(user_id, debt_id, reminder_kind, local_date) VALUES(?, ?, ?, ?)",
        (user_id, debt_id, reminder_kind, local_date),
    )
