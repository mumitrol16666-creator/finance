"""Migration 020: add onboarding interview profile fields to settings."""

from __future__ import annotations
import aiosqlite


async def apply(db: aiosqlite.Connection):
    cur = await db.execute("PRAGMA table_info(settings)")
    columns = {row[1] for row in await cur.fetchall()}

    statements: list[str] = []

    if "onboarding_archetype" not in columns:
        statements.append("ALTER TABLE settings ADD COLUMN onboarding_archetype TEXT")

    if "onboarding_main_goal" not in columns:
        statements.append("ALTER TABLE settings ADD COLUMN onboarding_main_goal TEXT")

    if "onboarding_daily_limit" not in columns:
        statements.append("ALTER TABLE settings ADD COLUMN onboarding_daily_limit INTEGER")

    if "onboarding_interview_done" not in columns:
        statements.append("ALTER TABLE settings ADD COLUMN onboarding_interview_done INTEGER NOT NULL DEFAULT 0")

    for stmt in statements:
        await db.execute(stmt)

    if statements:
        await db.commit()
