import aiosqlite
import calendar
from datetime import datetime, timezone
from loguru import logger


def add_months(sourcedate: datetime, months: int) -> datetime:
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return datetime(
        year,
        month,
        day,
        sourcedate.hour,
        sourcedate.minute,
        sourcedate.second,
        tzinfo=sourcedate.tzinfo,
    )


def add_years(sourcedate: datetime, years: int) -> datetime:
    try:
        return sourcedate.replace(year=sourcedate.year + years)
    except ValueError:
        # Handle leap year Feb 29.
        return sourcedate + (
            datetime(sourcedate.year + years, 3, 1)
            - datetime(sourcedate.year, 3, 1)
        )


async def ensure_deposit_category(db: aiosqlite.Connection, user_id: int) -> int:
    cur = await db.execute(
        "SELECT id FROM categories WHERE user_id=? AND kind='income' "
        "AND name='Проценты по депозиту' LIMIT 1",
        (user_id,),
    )
    row = await cur.fetchone()
    if row:
        return int(row[0])

    now = datetime.now(timezone.utc).isoformat()
    cur = await db.execute(
        "INSERT INTO categories(user_id, name, emoji, kind, is_archived, created_at, updated_at) "
        "VALUES(?, 'Проценты по депозиту', '📈', 'income', 0, ?, ?)",
        (user_id, now, now),
    )
    return int(cur.lastrowid)


async def accrue_deposit_interests(db: aiosqlite.Connection, user_id: int) -> None:
    """Accrue all due deposit interest exactly once per serialized write pass.

    The previous implementation read ``last_interest_accrued_at`` before taking a
    write lock. Two concurrent dashboard/account requests could therefore both
    calculate the same due periods and both post the interest. ``BEGIN IMMEDIATE``
    is intentionally acquired before reading deposit state so the second caller
    observes the marker written by the first caller.
    """
    await db.execute("BEGIN IMMEDIATE")
    try:
        cur = await db.execute(
            "SELECT id, name, balance, interest_rate, accrual_period, "
            "last_interest_accrued_at, created_at "
            "FROM accounts WHERE user_id=? AND acc_type='deposit' AND is_archived=0",
            (user_id,),
        )
        accounts = await cur.fetchall()
        if not accounts:
            await db.commit()
            return

        now = datetime.now(timezone.utc)
        category_id = None

        for acc in accounts:
            acc_id, name, balance, rate, period, last_accrued, created_at = acc
            if not rate or rate <= 0:
                continue

            start_str = last_accrued if last_accrued else created_at
            try:
                dt_str = start_str.replace("Z", "+00:00")
                start_dt = datetime.fromisoformat(dt_str)
            except Exception as exc:
                logger.error(
                    f"Failed to parse date {start_str} for account {acc_id}: {exc}"
                )
                continue

            current_dt = start_dt
            current_balance = int(balance or 0)
            updated = False

            while True:
                if period == "month":
                    next_dt = add_months(current_dt, 1)
                else:
                    next_dt = add_years(current_dt, 1)

                if next_dt > now:
                    break

                if period == "month":
                    interest = int(round(current_balance * (rate / 12) / 100))
                else:
                    interest = int(round(current_balance * rate / 100))

                next_dt_str = next_dt.isoformat()
                if interest > 0:
                    if category_id is None:
                        category_id = await ensure_deposit_category(db, user_id)

                    await db.execute(
                        "INSERT INTO transactions(user_id, ts, type, amount, account_id, "
                        "category_id, note, created_at) "
                        "VALUES(?, ?, 'income', ?, ?, ?, ?, ?)",
                        (
                            user_id,
                            next_dt_str,
                            interest,
                            acc_id,
                            category_id,
                            "Проценты по депозиту",
                            next_dt_str,
                        ),
                    )
                    await db.execute(
                        "UPDATE accounts SET balance = balance + ?, updated_at = ? "
                        "WHERE id = ? AND user_id = ?",
                        (interest, next_dt_str, acc_id, user_id),
                    )
                    current_balance += interest

                current_dt = next_dt
                updated = True

            if updated:
                await db.execute(
                    "UPDATE accounts SET last_interest_accrued_at = ?, updated_at = ? "
                    "WHERE id = ? AND user_id = ?",
                    (current_dt.isoformat(), now.isoformat(), acc_id, user_id),
                )
                logger.info(
                    f"Accrued compounding interest for deposit account '{name}' "
                    f"(ID: {acc_id}) up to {current_dt.isoformat()}"
                )

        await db.commit()
    except Exception:
        await db.rollback()
        raise
