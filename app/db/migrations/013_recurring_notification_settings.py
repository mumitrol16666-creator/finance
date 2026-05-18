from __future__ import annotations

import aiosqlite


async def _ensure_column(db: aiosqlite.Connection, table: str, column_name: str, sql_type: str) -> None:
    cur = await db.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    columns = {row[1] for row in rows}

    if column_name not in columns:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {sql_type}")


async def apply(db: aiosqlite.Connection) -> None:
    await _ensure_column(db, "settings", "recurring_inc_enabled", "INTEGER NOT NULL DEFAULT 1")
    await _ensure_column(db, "settings", "recurring_inc_days", "INTEGER NOT NULL DEFAULT 0")
    await _ensure_column(db, "settings", "recurring_exp_enabled", "INTEGER NOT NULL DEFAULT 1")
    await _ensure_column(db, "settings", "recurring_exp_days", "INTEGER NOT NULL DEFAULT 1")
    await db.commit()
