import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "integrity-test-token")
os.environ.setdefault("SECRET_KEY", "integrity-test-secret-key-32-characters-min")

from app.config.settings import settings
from app.db.connection import open_db
from app.db.migrate import run_migrations
from app.services.deposit_service import accrue_deposit_interests


async def check() -> None:
    fd, path_str = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    path = Path(path_str)
    settings.db_path = str(path)

    db = await open_db(str(path))
    try:
        await run_migrations(db)
        created = "2026-08-01T00:00:00+00:00"
        await db.execute(
            "INSERT INTO users(id, telegram_id, username, password_hash, display_name, "
            "onboarding_state, created_at, onboarded, mode, full_access) "
            "VALUES(1, 1, 'deposit_test', 'LEGACY_PLACEHOLDER', 'Deposit Test', "
            "'completed', ?, 1, 'full', 1)",
            (created,),
        )
        await db.execute(
            "INSERT INTO settings(user_id, currency, timezone, lang, created_at, updated_at) "
            "VALUES(1, 'KZT', 'Asia/Aqtobe', 'ru', ?, ?)",
            (created, created),
        )
        cur = await db.execute(
            "INSERT INTO accounts(user_id, name, balance, starting_balance, currency, "
            "is_saving, is_archived, acc_type, interest_rate, accrual_period, "
            "last_interest_accrued_at, created_at, updated_at) "
            "VALUES(1, 'Deposit', 120000, 120000, 'KZT', 0, 0, 'deposit', 12.0, "
            "'month', NULL, ?, ?)",
            (created, created),
        )
        account_id = int(cur.lastrowid)
        await db.commit()
    finally:
        await db.close()

    async def run_one() -> None:
        conn = await open_db(str(path))
        try:
            await accrue_deposit_interests(conn, 1)
        finally:
            await conn.close()

    await asyncio.gather(run_one(), run_one())

    db = await open_db(str(path))
    try:
        cur = await db.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM transactions "
            "WHERE user_id=1 AND account_id=? AND note='Проценты по депозиту'",
            (account_id,),
        )
        count, total_interest = await cur.fetchone()
        cur = await db.execute("SELECT balance FROM accounts WHERE id=?", (account_id,))
        balance = int((await cur.fetchone())[0])

        # 2026-08-01 -> one monthly accrual is due on 2026-09-01.
        assert int(count) == 1, (count, total_interest, balance)
        assert int(total_interest) == 1200, (count, total_interest, balance)
        assert balance == 121200, (count, total_interest, balance)
    finally:
        await db.close()

    for suffix in ("", "-wal", "-shm"):
        Path(f"{path}{suffix}").unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(check())
    print("Deposit accrual concurrency check OK")
