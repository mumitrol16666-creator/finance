from __future__ import annotations

import time
import asyncio
import aiosqlite
from pathlib import Path
from contextlib import asynccontextmanager
from loguru import logger
from app.config.settings import settings

DB_SEMAPHORE = asyncio.Semaphore(10)


async def open_db(db_path: str) -> aiosqlite.Connection:
    """Opens a single raw connection. Used primarily for migrations and startup checks."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row

    await db.execute("PRAGMA foreign_keys = ON;")
    await db.execute("PRAGMA journal_mode = WAL;")
    await db.execute("PRAGMA busy_timeout = 10000;")
    await db.execute("PRAGMA synchronous = NORMAL;")

    return db


@asynccontextmanager
async def get_db():
    """
    Context manager for short-lived SQLite database connections.
    Ensures connection is configured with proper PRAGMAs and closed cleanly.
    Bounded by DB_SEMAPHORE to prevent connection explosion.
    Measures session duration and logs warnings for sessions held over 0.3s.
    """
    async with DB_SEMAPHORE:
        db_path = settings.db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        start_time = time.perf_counter()
        db = await aiosqlite.connect(db_path)
        db.row_factory = aiosqlite.Row
        try:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute("PRAGMA busy_timeout = 10000;")
            await db.execute("PRAGMA synchronous = NORMAL;")
            yield db
        finally:
            await db.close()
            duration = time.perf_counter() - start_time
            if duration > 0.3:
                logger.warning(f"Database connection held for {duration:.3f}s")


@asynccontextmanager
async def transaction():
    """
    Helper context manager for write transactions.
    Automatically commits changes if the block completes successfully.
    """
    async with get_db() as db:
        yield db
        await db.commit()