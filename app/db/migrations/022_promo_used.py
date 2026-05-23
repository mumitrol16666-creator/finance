"""Migration 022: add promo_used column to users table."""

from __future__ import annotations
import aiosqlite


async def apply(db: aiosqlite.Connection):
    cur = await db.execute("PRAGMA table_info(users)")
    columns = {row[1] for row in await cur.fetchall()}

    statements: list[str] = []

    if "promo_used" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN promo_used INTEGER NOT NULL DEFAULT 0")

    for stmt in statements:
        await db.execute(stmt)

    if statements:
        await db.commit()
