from __future__ import annotations

import aiosqlite

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS planned_transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  amount INTEGER NOT NULL,
  category_id INTEGER NOT NULL,
  account_id INTEGER NOT NULL,
  planned_date TEXT NOT NULL,
  comment TEXT,
  is_required INTEGER NOT NULL DEFAULT 1,
  last_reminded_on TEXT,
  is_archived INTEGER NOT NULL DEFAULT 0,
  done_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
  FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT,
  FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_planned_user_arch_date ON planned_transactions(user_id, is_archived, planned_date);
"""

async def ensure_schema(db: aiosqlite.Connection):
    await db.executescript(CREATE_SQL)
    for sql in (
        "ALTER TABLE planned_transactions ADD COLUMN is_required INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE planned_transactions ADD COLUMN last_reminded_on TEXT",
    ):
        try:
            await db.execute(sql)
        except Exception:
            pass

SELECT_BASE = """SELECT p.id,p.kind,p.title,p.amount,p.category_id,p.account_id,p.planned_date,p.comment,p.is_required,p.last_reminded_on,p.is_archived,c.name as category_name,a.name as account_name
        FROM planned_transactions p
        JOIN categories c ON c.id=p.category_id
        JOIN accounts a ON a.id=p.account_id
"""

async def create_planned(db, user_id:int, kind:str, title:str, amount:int, category_id:int, account_id:int, planned_date:str, comment:str|None, ts:str, is_required:int=1):
    await ensure_schema(db)
    cur = await db.execute(
        """INSERT INTO planned_transactions(user_id,kind,title,amount,category_id,account_id,planned_date,comment,is_required,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (user_id, kind, title.strip(), int(amount), int(category_id), int(account_id), planned_date, comment or None, int(is_required), ts, ts),
    )
    return int(cur.lastrowid)

async def list_planned(db, user_id:int, archived:bool=False):
    await ensure_schema(db)
    cur = await db.execute(
        SELECT_BASE + " WHERE p.user_id=? AND p.is_archived=? ORDER BY date(p.planned_date), p.id",
        (user_id, 1 if archived else 0),
    )
    return await cur.fetchall()

async def get_planned(db, user_id:int, planned_id:int):
    await ensure_schema(db)
    cur = await db.execute(SELECT_BASE + " WHERE p.user_id=? AND p.id=? LIMIT 1", (user_id, planned_id))
    return await cur.fetchone()

async def set_planned_archived(db, user_id:int, planned_id:int, archived:bool, ts:str):
    await ensure_schema(db)
    await db.execute("UPDATE planned_transactions SET is_archived=?, updated_at=? WHERE user_id=? AND id=?", (1 if archived else 0, ts, user_id, planned_id))

async def mark_planned_done(db, user_id:int, planned_id:int, ts:str):
    await ensure_schema(db)
    row = await get_planned(db, user_id, planned_id)
    if not row:
        return None
    await db.execute("UPDATE planned_transactions SET done_at=?, is_archived=1, updated_at=? WHERE user_id=? AND id=?", (ts, ts, user_id, planned_id))
    return row

async def update_planned_date(db, user_id:int, planned_id:int, planned_date:str, ts:str):
    await ensure_schema(db)
    await db.execute("UPDATE planned_transactions SET planned_date=?, updated_at=? WHERE user_id=? AND id=?", (planned_date, ts, user_id, planned_id))

async def mark_planned_reminded(db, user_id:int, planned_id:int, local_date:str):
    await ensure_schema(db)
    await db.execute("UPDATE planned_transactions SET last_reminded_on=? WHERE user_id=? AND id=?", (local_date, user_id, planned_id))

async def list_due_planned(db, user_id:int, local_date:str, days_ahead:int=3):
    await ensure_schema(db)
    cur = await db.execute(
        SELECT_BASE + " WHERE p.user_id=? AND p.is_archived=0 AND date(p.planned_date) >= date(?) AND date(p.planned_date) <= date(?, '+' || ? || ' day') ORDER BY date(p.planned_date), p.id",
        (user_id, local_date, local_date, int(days_ahead)),
    )
    return await cur.fetchall()

async def planned_before_month_end(db, user_id:int, local_today:str, local_month_end:str):
    await ensure_schema(db)
    cur = await db.execute(
        """SELECT id, kind, title, amount, category_id, account_id, planned_date, comment, is_required
        FROM planned_transactions
        WHERE user_id=? AND is_archived=0
          AND date(planned_date) >= date(?)
          AND date(planned_date) < date(?)
        ORDER BY date(planned_date), id""",
        (user_id, local_today, local_month_end),
    )
    return await cur.fetchall()
