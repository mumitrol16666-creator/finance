"""Migration 025: add limits_nudge_last_sent_date column to settings table."""

from __future__ import annotations
import aiosqlite


async def apply(db: aiosqlite.Connection):
    cur = await db.execute("PRAGMA table_info(settings)")
    columns = {row[1] for row in await cur.fetchall()}

    statements: list[str] = []

    if "limits_nudge_last_sent_date" not in columns:
        statements.append("ALTER TABLE settings ADD COLUMN limits_nudge_last_sent_date TEXT")

    for stmt in statements:
        await db.execute(stmt)

    if statements:
        await db.commit()
