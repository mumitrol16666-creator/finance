from __future__ import annotations

import aiosqlite


RECURRING_EXPENSES_SQL = """
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
"""

RECURRING_INCOMES_SQL = """
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
"""


async def _ensure_column(db: aiosqlite.Connection, table: str, column_name: str, sql_type: str) -> None:
    cur = await db.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    columns = {row[1] for row in rows}

    if column_name not in columns:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {sql_type}")


async def apply(db: aiosqlite.Connection) -> None:
    await db.executescript(RECURRING_EXPENSES_SQL)
    await db.executescript(RECURRING_INCOMES_SQL)

    await _ensure_column(db, "recurring_expenses", "last_reminded_on", "TEXT")
    await _ensure_column(db, "recurring_incomes", "last_reminded_on", "TEXT")

    await db.commit()
