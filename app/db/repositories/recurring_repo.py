from __future__ import annotations

import calendar
from datetime import date, datetime

import aiosqlite


CREATE_SQL = '''
CREATE TABLE IF NOT EXISTS recurring_expenses (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          INTEGER NOT NULL,
  title            TEXT    NOT NULL,
  amount           INTEGER NOT NULL,
  category_id      INTEGER NOT NULL,
  account_id       INTEGER NOT NULL,
  day_of_month     INTEGER NOT NULL,
  comment          TEXT,
  next_run_date    TEXT    NOT NULL,
  last_paid_at     TEXT,
  last_reminded_on TEXT,
  is_archived      INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT    NOT NULL,
  updated_at       TEXT    NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT,
  FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_recurring_expenses_user_arch ON recurring_expenses(user_id, is_archived, next_run_date);

CREATE TABLE IF NOT EXISTS recurring_incomes (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id          INTEGER NOT NULL,
  title            TEXT    NOT NULL,
  amount           INTEGER NOT NULL,
  category_id      INTEGER NOT NULL,
  account_id       INTEGER NOT NULL,
  day_of_month     INTEGER NOT NULL,
  comment          TEXT,
  next_run_date    TEXT    NOT NULL,
  last_received_at TEXT,
  last_reminded_on TEXT,
  is_archived      INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT    NOT NULL,
  updated_at       TEXT    NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT,
  FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_recurring_incomes_user_arch ON recurring_incomes(user_id, is_archived, next_run_date);
'''


def _safe_day(year: int, month: int, day: int) -> int:
    last = calendar.monthrange(year, month)[1]
    return max(1, min(day, last))


def calc_next_run_after(day_of_month: int, anchor: date) -> str:
    d = int(day_of_month)
    year = anchor.year + (1 if anchor.month == 12 else 0)
    month = 1 if anchor.month == 12 else anchor.month + 1
    next_day = _safe_day(year, month, d)
    return date(year, month, next_day).isoformat()


def calc_next_run_date(day_of_month: int, today: date | None = None) -> str:
    today = today or date.today()
    d = int(day_of_month)
    current_day = _safe_day(today.year, today.month, d)
    if today.day <= current_day:
        return date(today.year, today.month, current_day).isoformat()
    return calc_next_run_after(d, today)


async def ensure_schema(db: aiosqlite.Connection) -> None:
    await db.executescript(CREATE_SQL)
    for table in ("recurring_expenses", "recurring_incomes"):
        try:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN last_reminded_on TEXT")
        except Exception:
            pass


async def _create_item(db, table, user_id, title, amount, category_id, account_id, day_of_month, comment, ts):
    next_run = calc_next_run_date(int(day_of_month))
    cur = await db.execute(
        f"""
        INSERT INTO {table}(
            user_id, title, amount, category_id, account_id, day_of_month,
            comment, next_run_date, created_at, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (user_id, title.strip(), int(amount), int(category_id), int(account_id), int(day_of_month), (comment or None), next_run, ts, ts),
    )
    return int(cur.lastrowid)


async def create_recurring_expense(db, user_id, title, amount, category_id, account_id, day_of_month, comment, ts):
    return await _create_item(db, 'recurring_expenses', user_id, title, amount, category_id, account_id, day_of_month, comment, ts)


async def create_recurring_income(db, user_id, title, amount, category_id, account_id, day_of_month, comment, ts):
    return await _create_item(db, 'recurring_incomes', user_id, title, amount, category_id, account_id, day_of_month, comment, ts)


async def _list_items(db, table, user_id, archived=False):
    cur = await db.execute(
        f"""
        SELECT r.id, r.title, r.amount, r.day_of_month, r.comment, r.next_run_date,
               c.name AS category_name,
               a.name AS account_name,
               r.is_archived
        FROM {table} r
        JOIN categories c ON c.id = r.category_id
        JOIN accounts a ON a.id = r.account_id
        WHERE r.user_id=? AND r.is_archived=?
        ORDER BY date(r.next_run_date), r.id
        """,
        (user_id, 1 if archived else 0),
    )
    return await cur.fetchall()


async def list_recurring_expenses(db, user_id, archived=False):
    return await _list_items(db, 'recurring_expenses', user_id, archived)


async def list_recurring_incomes(db, user_id, archived=False):
    return await _list_items(db, 'recurring_incomes', user_id, archived)


async def _get_item(db, table, user_id, recurring_id):
    extra_ts = 'last_paid_at' if table == 'recurring_expenses' else 'last_received_at'
    cur = await db.execute(
        f"""
        SELECT r.id, r.title, r.amount, r.category_id, r.account_id, r.day_of_month,
               r.comment, r.next_run_date, r.{extra_ts}, r.last_reminded_on, r.is_archived,
               c.name AS category_name,
               a.name AS account_name
        FROM {table} r
        JOIN categories c ON c.id = r.category_id
        JOIN accounts a ON a.id = r.account_id
        WHERE r.user_id=? AND r.id=?
        LIMIT 1
        """,
        (user_id, recurring_id),
    )
    return await cur.fetchone()


async def get_recurring_expense(db, user_id, recurring_id):
    return await _get_item(db, 'recurring_expenses', user_id, recurring_id)


async def get_recurring_income(db, user_id, recurring_id):
    return await _get_item(db, 'recurring_incomes', user_id, recurring_id)


async def _set_archived(db, table, user_id, recurring_id, archived, ts):
    await db.execute(
        f"UPDATE {table} SET is_archived=?, updated_at=? WHERE user_id=? AND id=?",
        (1 if archived else 0, ts, user_id, recurring_id),
    )


async def archive_recurring_expense(db, user_id, recurring_id, ts):
    await _set_archived(db, 'recurring_expenses', user_id, recurring_id, True, ts)


async def restore_recurring_expense(db, user_id, recurring_id, ts):
    await _set_archived(db, 'recurring_expenses', user_id, recurring_id, False, ts)


async def archive_recurring_income(db, user_id, recurring_id, ts):
    await _set_archived(db, 'recurring_incomes', user_id, recurring_id, True, ts)


async def restore_recurring_income(db, user_id, recurring_id, ts):
    await _set_archived(db, 'recurring_incomes', user_id, recurring_id, False, ts)


async def _mark_done(db, table, user_id, recurring_id, ts):
    row = await _get_item(db, table, user_id, recurring_id)
    if not row:
        return None
    try:
        anchor = datetime.fromisoformat(str(ts)).date()
    except Exception:
        anchor = date.today()
    next_run = calc_next_run_after(int(row['day_of_month']), anchor)
    done_col = 'last_paid_at' if table == 'recurring_expenses' else 'last_received_at'
    await db.execute(
        f"UPDATE {table} SET {done_col}=?, next_run_date=?, updated_at=? WHERE user_id=? AND id=?",
        (ts, next_run, ts, user_id, recurring_id),
    )
    return row


async def mark_recurring_paid(db, user_id, recurring_id, ts):
    return await _mark_done(db, 'recurring_expenses', user_id, recurring_id, ts)


async def mark_recurring_received(db, user_id, recurring_id, ts):
    return await _mark_done(db, 'recurring_incomes', user_id, recurring_id, ts)


async def skip_recurring_income(db, user_id, recurring_id, ts):
    row = await _get_item(db, 'recurring_incomes', user_id, recurring_id)
    if not row:
        return None
    try:
        anchor = datetime.fromisoformat(str(ts)).date()
    except Exception:
        anchor = date.today()
    next_run = calc_next_run_after(int(row['day_of_month']), anchor)
    await db.execute(
        "UPDATE recurring_incomes SET next_run_date=?, updated_at=? WHERE user_id=? AND id=?",
        (next_run, ts, user_id, recurring_id),
    )
    return row


async def _list_due_items(db, table, user_id, local_date, days_ahead=3):
    extra_ts = 'last_paid_at' if table == 'recurring_expenses' else 'last_received_at'
    cur = await db.execute(
        f"""
        SELECT r.id, r.title, r.amount, r.day_of_month, r.comment, r.next_run_date,
               r.{extra_ts}, r.last_reminded_on,
               c.name AS category_name,
               a.name AS account_name
        FROM {table} r
        JOIN categories c ON c.id = r.category_id
        JOIN accounts a ON a.id = r.account_id
        WHERE r.user_id=?
          AND r.is_archived=0
          AND date(r.next_run_date) <= date(?, '+' || ? || ' day')
        ORDER BY date(r.next_run_date), r.id
        """,
        (user_id, local_date, int(days_ahead)),
    )
    return await cur.fetchall()


async def list_due_recurring_expenses(db, user_id, local_date, days_ahead=3):
    return await _list_due_items(db, 'recurring_expenses', user_id, local_date, days_ahead)


async def list_due_recurring_incomes(db, user_id, local_date, days_ahead=3):
    return await _list_due_items(db, 'recurring_incomes', user_id, local_date, days_ahead)


async def _mark_reminded(db, table, user_id, recurring_id, local_date):
    await db.execute(
        f"UPDATE {table} SET last_reminded_on=?, updated_at=? WHERE user_id=? AND id=?",
        (local_date, datetime.utcnow().isoformat(), user_id, recurring_id),
    )


async def mark_recurring_reminded(db, user_id, recurring_id, local_date):
    await _mark_reminded(db, 'recurring_expenses', user_id, recurring_id, local_date)


async def mark_recurring_income_reminded(db, user_id, recurring_id, local_date):
    await _mark_reminded(db, 'recurring_incomes', user_id, recurring_id, local_date)


async def _due_before_month_end(db, table, user_id, local_today, local_month_end):
    cur = await db.execute(
        f"""
        SELECT id, title, amount, category_id, account_id, day_of_month, comment, next_run_date
        FROM {table}
        WHERE user_id=?
          AND is_archived=0
          AND date(next_run_date) >= date(?)
          AND date(next_run_date) < date(?)
        ORDER BY date(next_run_date), id
        """,
        (user_id, local_today, local_month_end),
    )
    return await cur.fetchall()


async def recurring_due_before_month_end(db, user_id, local_today, local_month_end):
    return await _due_before_month_end(db, 'recurring_expenses', user_id, local_today, local_month_end)


async def recurring_income_due_before_month_end(db, user_id, local_today, local_month_end):
    return await _due_before_month_end(db, 'recurring_incomes', user_id, local_today, local_month_end)
