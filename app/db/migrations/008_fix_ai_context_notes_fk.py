from __future__ import annotations

import aiosqlite


async def apply(db: aiosqlite.Connection) -> None:
    cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_context_notes'")
    exists = await cur.fetchone()
    if not exists:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_context_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                note_type TEXT NOT NULL,
                period_kind TEXT NOT NULL DEFAULT 'month',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_context_notes_user_type_period ON ai_context_notes(user_id, note_type, period_kind, id DESC)"
        )
        return

    fk_cur = await db.execute("PRAGMA foreign_key_list(ai_context_notes)")
    fk_rows = await fk_cur.fetchall()
    target_ok = any((row[2] == 'users' and row[4] == 'user_id') for row in fk_rows)
    if target_ok:
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_context_notes_user_type_period ON ai_context_notes(user_id, note_type, period_kind, id DESC)"
        )
        return

    await db.execute("PRAGMA foreign_keys = OFF")
    try:
        await db.execute("ALTER TABLE ai_context_notes RENAME TO ai_context_notes__old")
        await db.execute(
            """
            CREATE TABLE ai_context_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                note_type TEXT NOT NULL,
                period_kind TEXT NOT NULL DEFAULT 'month',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
            """
        )
        await db.execute(
            """
            INSERT INTO ai_context_notes(id, user_id, note_type, period_kind, content, created_at, updated_at)
            SELECT id, user_id, note_type, period_kind, content, created_at, updated_at
            FROM ai_context_notes__old
            """
        )
        await db.execute("DROP TABLE ai_context_notes__old")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_context_notes_user_type_period ON ai_context_notes(user_id, note_type, period_kind, id DESC)"
        )
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
