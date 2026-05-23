"""Migration 021: add trial_reminder_sent column to settings."""

from __future__ import annotations
import aiosqlite


async def apply(db: aiosqlite.Connection):
    cur = await db.execute("PRAGMA table_info(settings)")
    columns = {row[1] for row in await cur.fetchall()}

    statements: list[str] = []

    if "trial_reminder_sent" not in columns:
        statements.append("ALTER TABLE settings ADD COLUMN trial_reminder_sent INTEGER NOT NULL DEFAULT 0")

    for stmt in statements:
        await db.execute(stmt)

    if statements:
        await db.commit()
