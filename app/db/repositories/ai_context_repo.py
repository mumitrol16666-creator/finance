from __future__ import annotations

import aiosqlite


async def save_ai_context_note(
    db: aiosqlite.Connection,
    user_id: int,
    *,
    note_type: str,
    period_kind: str,
    content: str,
    created_at: str,
) -> None:
    cur = await db.execute(
        "SELECT id FROM ai_context_notes WHERE user_id=? AND note_type=? AND period_kind=? ORDER BY id DESC LIMIT 1",
        (user_id, note_type, period_kind),
    )
    row = await cur.fetchone()
    if row:
        await db.execute(
            "UPDATE ai_context_notes SET content=?, updated_at=? WHERE id=?",
            (content, created_at, int(row[0])),
        )
    else:
        await db.execute(
            "INSERT INTO ai_context_notes(user_id, note_type, period_kind, content, created_at, updated_at) VALUES(?,?,?,?,?,?)",
            (user_id, note_type, period_kind, content, created_at, created_at),
        )


async def get_latest_ai_context_note(
    db: aiosqlite.Connection,
    user_id: int,
    *,
    note_type: str,
    period_kind: str | None = None,
):
    if period_kind is None:
        cur = await db.execute(
            "SELECT id, user_id, note_type, period_kind, content, created_at, updated_at FROM ai_context_notes WHERE user_id=? AND note_type=? ORDER BY id DESC LIMIT 1",
            (user_id, note_type),
        )
    else:
        cur = await db.execute(
            "SELECT id, user_id, note_type, period_kind, content, created_at, updated_at FROM ai_context_notes WHERE user_id=? AND note_type=? AND period_kind=? ORDER BY id DESC LIMIT 1",
            (user_id, note_type, period_kind),
        )
    row = await cur.fetchone()
    if not row:
        return None
    return {
        "id": int(row[0]),
        "user_id": int(row[1]),
        "note_type": str(row[2]),
        "period_kind": str(row[3]),
        "content": str(row[4] or ""),
        "created_at": str(row[5] or ""),
        "updated_at": str(row[6] or ""),
    }
