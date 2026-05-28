"""Migration 024: add trial_3d_claimed column to users table."""

from __future__ import annotations
import aiosqlite


async def apply(db: aiosqlite.Connection):
    cur = await db.execute("PRAGMA table_info(users)")
    columns = {row[1] for row in await cur.fetchall()}

    statements: list[str] = []

    if "trial_3d_claimed" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN trial_3d_claimed INTEGER NOT NULL DEFAULT 0")

    for stmt in statements:
        await db.execute(stmt)

    if statements:
        await db.commit()
