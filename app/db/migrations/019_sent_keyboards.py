"""Migration 019: Sent Keyboards.

Creates the `sent_keyboards` table to track sent messages containing inline keyboards
for TTL cleanup.
"""
from __future__ import annotations
import aiosqlite


async def apply(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS sent_keyboards (
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            sent_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, message_id)
        )
        """
    )
    await db.commit()
