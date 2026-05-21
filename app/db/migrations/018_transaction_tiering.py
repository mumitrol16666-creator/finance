"""Migration 018: Transaction Tiering.

Adds a `tier` column to the `transactions` table to classify each transaction
into one of three tiers:
  - 'routine'    — everyday operational expenses (food, transport, etc.)
  - 'obligation' — fixed contractual payments (rent, subscriptions, loans)
  - 'anomaly'    — rare high-amplitude capital expenditures / investments

Also creates a partial index for efficient CDBR (Clean Daily Burn Rate)
queries that filter by tier and date range.
"""
from __future__ import annotations

import aiosqlite


async def _column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    cur = await db.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    return any(str(row[1]) == column for row in rows)


async def apply(db: aiosqlite.Connection) -> None:
    # 1. Add tier column (default 'routine' for backward compatibility)
    if not await _column_exists(db, "transactions", "tier"):
        await db.execute(
            "ALTER TABLE transactions ADD COLUMN tier TEXT NOT NULL DEFAULT 'routine'"
        )

    # 2. Create partial index for fast CDBR queries:
    #    SELECT ... WHERE user_id=? AND tier='routine' AND ts>=? AND ts<? AND deleted_at IS NULL
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_tx_user_tier_ts "
        "ON transactions(user_id, tier, ts) WHERE deleted_at IS NULL"
    )

    # 3. Back-classify existing recurring/obligation transactions.
    #    Mark transactions whose category names match known obligation patterns.
    #    This is a best-effort heuristic for historical data.
    obligation_keywords = [
        '%арен%', '%ипот%', '%кредит%', '%коммун%', '%жкх%',
        '%подписк%', '%страхов%', '%netflix%', '%spotify%', '%icloud%',
        '%internet%', '%интернет%', '%связь%', '%mobile%', '%телефон%',
        '%youtube%', '%yandex%', '%яндекс%', '%apple%', '%google%',
        '%gym%', '%фитнес%', '%садик%', '%школ%', '%налог%',
        '%лифт%', '%парковк%', '%охрана%', '%домофон%',
    ]

    # Build a single UPDATE with OR'd LIKE conditions
    like_clauses = " OR ".join(
        f"LOWER(c.name) LIKE '{kw}'" for kw in obligation_keywords
    )

    await db.execute(
        f"""
        UPDATE transactions
        SET tier = 'obligation'
        WHERE id IN (
            SELECT t.id
            FROM transactions t
            JOIN categories c ON c.id = t.category_id
            WHERE t.tier = 'routine'
              AND t.type = 'expense'
              AND t.deleted_at IS NULL
              AND ({like_clauses})
        )
        """
    )

    await db.commit()
