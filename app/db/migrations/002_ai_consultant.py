from __future__ import annotations

import aiosqlite


async def apply(db: aiosqlite.Connection) -> None:
    cur = await db.execute("PRAGMA table_info(settings)")
    rows = await cur.fetchall()
    columns = {row[1] for row in rows}

    statements: list[str] = []

    if "financial_goal_text" not in columns:
        statements.append("ALTER TABLE settings ADD COLUMN financial_goal_text TEXT")

    if "financial_goal_amount" not in columns:
        statements.append("ALTER TABLE settings ADD COLUMN financial_goal_amount INTEGER")

    if "financial_goal_deadline" not in columns:
        statements.append("ALTER TABLE settings ADD COLUMN financial_goal_deadline TEXT")

    if "ai_reports_used_month" not in columns:
        statements.append(
            "ALTER TABLE settings ADD COLUMN ai_reports_used_month INTEGER NOT NULL DEFAULT 0"
        )

    if "ai_reports_month" not in columns:
        statements.append("ALTER TABLE settings ADD COLUMN ai_reports_month TEXT")

    for sql in statements:
        await db.execute(sql)

    await db.commit()
