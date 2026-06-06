import aiosqlite
import calendar
from datetime import datetime, timezone, timedelta
from loguru import logger

def add_months(sourcedate: datetime, months: int) -> datetime:
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return datetime(
        year, month, day,
        sourcedate.hour, sourcedate.minute, sourcedate.second,
        tzinfo=sourcedate.tzinfo
    )

def add_years(sourcedate: datetime, years: int) -> datetime:
    try:
        return sourcedate.replace(year=sourcedate.year + years)
    except ValueError:
        # Handle leap year Feb 29
        return sourcedate + (datetime(sourcedate.year + years, 3, 1) - datetime(sourcedate.year, 3, 1))

async def ensure_deposit_category(db: aiosqlite.Connection, user_id: int) -> int:
    cur = await db.execute(
        "SELECT id FROM categories WHERE user_id=? AND kind='income' AND name='Проценты по депозиту' LIMIT 1",
        (user_id,)
    )
    row = await cur.fetchone()
    if row:
        return int(row[0])
    cur = await db.execute(
        "INSERT INTO categories(user_id, name, emoji, kind, is_archived, created_at, updated_at) "
        "VALUES(?, 'Проценты по депозиту', '📈', 'income', 0, ?, ?)",
        (user_id, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
    )
    return int(cur.lastrowid)

async def accrue_deposit_interests(db: aiosqlite.Connection, user_id: int) -> None:
    # Get all active deposit accounts for user
    cur = await db.execute(
        "SELECT id, name, balance, interest_rate, accrual_period, last_interest_accrued_at, created_at "
        "FROM accounts WHERE user_id=? AND acc_type='deposit' AND is_archived=0",
        (user_id,)
    )
    accounts = await cur.fetchall()
    if not accounts:
        return

    now = datetime.now(timezone.utc)
    category_id = None

    for acc in accounts:
        acc_id, name, balance, rate, period, last_accrued, created_at = acc
        if not rate or rate <= 0:
            continue

        # Parse start date of accrual
        start_str = last_accrued if last_accrued else created_at
        try:
            # strip timezone info Z if present and parse
            dt_str = start_str.replace("Z", "+00:00")
            start_dt = datetime.fromisoformat(dt_str)
        except Exception as e:
            logger.error(f"Failed to parse date {start_str} for account {acc_id}: {e}")
            continue

        # Compounding loop
        current_dt = start_dt
        current_balance = balance
        updated = False

        while True:
            # Calculate next target date
            if period == 'month':
                next_dt = add_months(current_dt, 1)
            else:  # year
                next_dt = add_years(current_dt, 1)

            # If next date is in the future relative to now, stop
            if next_dt > now:
                break

            # Calculate interest amount
            if period == 'month':
                interest = int(round(current_balance * (rate / 12) / 100))
            else:
                interest = int(round(current_balance * rate / 100))

            next_dt_str = next_dt.isoformat()

            if interest > 0:
                if category_id is None:
                    category_id = await ensure_deposit_category(db, user_id)

                # 1. Create systemic transaction
                await db.execute(
                    "INSERT INTO transactions(user_id, ts, type, amount, account_id, category_id, note, created_at) "
                    "VALUES(?, ?, 'income', ?, ?, ?, ?, ?)",
                    (user_id, next_dt_str, interest, acc_id, category_id, "Проценты по депозиту", next_dt_str)
                )

                # 2. Update account balance (compound)
                await db.execute(
                    "UPDATE accounts SET balance = balance + ?, updated_at = ? WHERE id = ?",
                    (interest, next_dt_str, acc_id)
                )
                current_balance += interest

            current_dt = next_dt
            updated = True

        if updated:
            # Save final last_interest_accrued_at
            await db.execute(
                "UPDATE accounts SET last_interest_accrued_at = ?, updated_at = ? WHERE id = ?",
                (current_dt.isoformat(), now.isoformat(), acc_id)
            )
            await db.commit()
            logger.info(f"Accrued compounding interest for deposit account '{name}' (ID: {acc_id}) up to {current_dt.isoformat()}")
