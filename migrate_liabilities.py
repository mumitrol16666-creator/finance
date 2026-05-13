from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite


DB_PATH = Path("data/bot.db")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def map_kind(direction: str | None, dtype: str | None) -> str | None:
    direction = (direction or "").strip().lower()
    dtype = (dtype or "").strip().lower()

    if direction == "out" and dtype == "private":
        return "private_out"
    if direction == "in" and dtype == "private":
        return "private_in"
    if direction == "out" and dtype == "bank":
        return "loan"

    return None


async def table_exists(db: aiosqlite.Connection, table_name: str) -> bool:
    cur = await db.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (table_name,),
    )
    row = await cur.fetchone()
    return row is not None


async def column_exists(db: aiosqlite.Connection, table_name: str, column_name: str) -> bool:
    cur = await db.execute(f"PRAGMA table_info({table_name})")
    rows = await cur.fetchall()
    return any(str(row[1]) == column_name for row in rows)


async def create_liability_tables(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS liabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,

            kind TEXT NOT NULL CHECK (
                kind IN ('private_out', 'private_in', 'loan', 'credit_card')
            ),

            status TEXT NOT NULL DEFAULT 'active' CHECK (
                status IN ('active', 'closed', 'archived')
            ),

            title TEXT NOT NULL,
            creditor_name TEXT,
            debtor_name TEXT,
            issuer_name TEXT,
            product_name TEXT,

            currency TEXT NOT NULL DEFAULT 'KZT',

            total_amount INTEGER,
            remaining_amount INTEGER,

            payment_amount INTEGER,
            min_payment_amount INTEGER,

            credit_limit INTEGER,
            used_amount INTEGER,
            available_amount INTEGER,

            next_payment_date TEXT,
            statement_date TEXT,
            grace_until TEXT,
            started_at TEXT,
            closed_at TEXT,

            note TEXT,

            source_debt_id INTEGER,

            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS liability_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            liability_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,

            event_type TEXT NOT NULL CHECK (
                event_type IN (
                    'created',
                    'payment',
                    'receipt',
                    'charge',
                    'purchase',
                    'manual_adjust',
                    'limit_change',
                    'statement',
                    'closed'
                )
            ),

            amount INTEGER,
            account_id INTEGER,
            transaction_id INTEGER,

            event_date TEXT NOT NULL,
            note TEXT,

            created_at TEXT NOT NULL,

            FOREIGN KEY (liability_id) REFERENCES liabilities(id)
        )
        """
    )

    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_liabilities_user_status
        ON liabilities(user_id, status)
        """
    )

    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_liabilities_user_kind_status
        ON liabilities(user_id, kind, status)
        """
    )

    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_liabilities_next_payment
        ON liabilities(user_id, next_payment_date)
        """
    )

    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_liability_events_liability_date
        ON liability_events(liability_id, event_date)
        """
    )

    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_liability_events_user_date
        ON liability_events(user_id, event_date)
        """
    )


async def liabilities_already_migrated(db: aiosqlite.Connection) -> bool:
    if not await table_exists(db, "liabilities"):
        return False

    if not await column_exists(db, "liabilities", "source_debt_id"):
        return False

    cur = await db.execute(
        """
        SELECT 1
        FROM liabilities
        WHERE source_debt_id IS NOT NULL
        LIMIT 1
        """
    )
    row = await cur.fetchone()
    return row is not None


async def fetch_debts_rows(db: aiosqlite.Connection) -> list[aiosqlite.Row]:
    cur = await db.execute("PRAGMA table_info(debts)")
    cols_info = await cur.fetchall()
    if not cols_info:
        return []

    cols = {str(row[1]) for row in cols_info}

    select_cols: list[str] = []
    required = [
        "id",
        "user_id",
        "title",
        "payment_amount",
        "next_payment_date",
        "remaining_amount",
        "dtype",
        "direction",
        "is_active",
        "created_at",
        "updated_at",
        "note",
    ]

    for name in required:
        if name in cols:
            select_cols.append(name)
        else:
            select_cols.append(f"NULL AS {name}")

    sql = f"""
        SELECT {", ".join(select_cols)}
        FROM debts
    """
    cur = await db.execute(sql)
    return await cur.fetchall()


async def migrate_debts_to_liabilities(db: aiosqlite.Connection) -> dict[str, int]:
    moved = 0
    skipped = 0

    if not await table_exists(db, "debts"):
        return {"moved": 0, "skipped": 0}

    rows = await fetch_debts_rows(db)

    for row in rows:
        debt_id = row["id"]
        user_id = row["user_id"]
        title = row["title"]
        payment_amount = row["payment_amount"]
        next_payment_date = row["next_payment_date"]
        remaining_amount = row["remaining_amount"]
        dtype = row["dtype"]
        direction = row["direction"]
        is_active = row["is_active"]
        created_at = row["created_at"]
        updated_at = row["updated_at"]
        note = row["note"]

        kind = map_kind(direction, dtype)
        if not kind:
            skipped += 1
            continue

        # защита от повторной миграции одной и той же записи
        cur = await db.execute(
            """
            SELECT id
            FROM liabilities
            WHERE source_debt_id = ?
            LIMIT 1
            """,
            (debt_id,),
        )
        already = await cur.fetchone()
        if already:
            continue

        created_at = created_at or now_iso()
        updated_at = updated_at or created_at

        status = "active" if int(is_active or 0) == 1 else "closed"

        title = str(title or "").strip() or f"Обязательство #{debt_id}"
        remaining_amount = int(remaining_amount or 0)
        payment_amount = int(payment_amount or 0) if payment_amount is not None else None

        creditor_name = None
        debtor_name = None
        issuer_name = None
        product_name = None

        if kind == "loan":
            issuer_name = title
        elif kind == "private_out":
            creditor_name = title
        elif kind == "private_in":
            debtor_name = title

        cur = await db.execute(
            """
            INSERT INTO liabilities (
                user_id,
                kind,
                status,
                title,
                creditor_name,
                debtor_name,
                issuer_name,
                product_name,
                currency,
                total_amount,
                remaining_amount,
                payment_amount,
                min_payment_amount,
                credit_limit,
                used_amount,
                available_amount,
                next_payment_date,
                statement_date,
                grace_until,
                started_at,
                closed_at,
                note,
                source_debt_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                kind,
                status,
                title,
                creditor_name,
                debtor_name,
                issuer_name,
                product_name,
                "KZT",
                remaining_amount,
                remaining_amount,
                payment_amount,
                None,
                None,
                None,
                None,
                next_payment_date,
                None,
                None,
                created_at,
                None if status == "active" else updated_at,
                note or "Migrated from debts",
                debt_id,
                created_at,
                updated_at,
            ),
        )
        liability_id = cur.lastrowid

        await db.execute(
            """
            INSERT INTO liability_events (
                liability_id,
                user_id,
                event_type,
                amount,
                account_id,
                transaction_id,
                event_date,
                note,
                created_at
            )
            VALUES (?, ?, 'created', ?, NULL, NULL, ?, ?, ?)
            """,
            (
                liability_id,
                user_id,
                remaining_amount,
                created_at,
                "Migrated from debts",
                created_at,
            ),
        )

        moved += 1

    return {"moved": moved, "skipped": skipped}


async def run() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH}")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        try:
            await db.execute("BEGIN")

            await create_liability_tables(db)
            result = await migrate_debts_to_liabilities(db)

            await db.commit()
        except Exception:
            await db.rollback()
            raise

    print("Migration complete")
    print(f"Moved: {result['moved']}")
    print(f"Skipped: {result['skipped']}")


if __name__ == "__main__":
    asyncio.run(run())