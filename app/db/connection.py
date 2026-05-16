from __future__ import annotations

from pathlib import Path
import aiosqlite


async def open_db(db_path: str) -> aiosqlite.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row

    await db.execute("PRAGMA foreign_keys = ON;")
    await db.execute("PRAGMA journal_mode = WAL;")
    # Wait up to 5 seconds when another writer holds the lock instead of failing with
    # "database is locked"; critical because polling + APScheduler share one connection.
    await db.execute("PRAGMA busy_timeout = 5000;")
    # WAL + NORMAL is the recommended durability/perf sweet spot for app DBs.
    await db.execute("PRAGMA synchronous = NORMAL;")

    return db