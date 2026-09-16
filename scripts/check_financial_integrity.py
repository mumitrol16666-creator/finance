import asyncio
import io
import os
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

from app.config.settings import settings
from app.db.connection import open_db
from app.db.migrate import run_migrations
from app.db.repositories.tx_repo import delete_tx, update_tx
from app.domain.auth import hash_password
import app.domain.services.ai_event_worker as ai_event_worker


async def _noop_ai_analysis(user_id: int) -> None:
    return None


async def _seed_db(path: Path) -> dict[str, int]:
    now = "2026-09-16T00:00:00+00:00"
    db = await open_db(str(path))
    try:
        with redirect_stdout(io.StringIO()):
            await run_migrations(db)

        await db.execute(
            "INSERT INTO users(id,telegram_id,username,password_hash,display_name,onboarding_state,"
            "created_at,onboarded,mode,full_access) VALUES(1,1,'integrity',?,'Integrity','completed',?,1,'full',1)",
            (hash_password("password"), now),
        )
        await db.execute(
            "INSERT INTO users(id,telegram_id,username,password_hash,display_name,onboarding_state,"
            "created_at,onboarded,mode,full_access) VALUES(2,2,'other',?,'Other','completed',?,1,'full',1)",
            (hash_password("password"), now),
        )
        await db.execute(
            "INSERT INTO settings(user_id,currency,timezone,lang,created_at,updated_at) "
            "VALUES(1,'KZT','Asia/Aqtobe','ru',?,?)",
            (now, now),
        )
        await db.execute(
            "INSERT INTO settings(user_id,currency,timezone,lang,created_at,updated_at) "
            "VALUES(2,'KZT','Asia/Aqtobe','ru',?,?)",
            (now, now),
        )

        main = await db.execute(
            "INSERT INTO accounts(user_id,name,balance,starting_balance,currency,is_archived,created_at,updated_at) "
            "VALUES(1,'Main',100000,100000,'KZT',0,?,?)",
            (now, now),
        )
        second = await db.execute(
            "INSERT INTO accounts(user_id,name,balance,starting_balance,currency,is_archived,created_at,updated_at) "
            "VALUES(1,'Second',50000,50000,'KZT',0,?,?)",
            (now, now),
        )
        usd = await db.execute(
            "INSERT INTO accounts(user_id,name,balance,starting_balance,currency,is_archived,created_at,updated_at) "
            "VALUES(1,'USD',1000,1000,'USD',0,?,?)",
            (now, now),
        )
        kzt = await db.execute(
            "INSERT INTO accounts(user_id,name,balance,starting_balance,currency,is_archived,created_at,updated_at) "
            "VALUES(1,'KZT FX',0,0,'KZT',0,?,?)",
            (now, now),
        )
        other = await db.execute(
            "INSERT INTO accounts(user_id,name,balance,starting_balance,currency,is_archived,created_at,updated_at) "
            "VALUES(2,'Other',50000,50000,'KZT',0,?,?)",
            (now, now),
        )
        category = await db.execute(
            "INSERT INTO categories(user_id,name,emoji,kind,is_archived,created_at,updated_at) "
            "VALUES(1,'Test','T','expense',0,?,?)",
            (now, now),
        )
        await db.commit()
        return {
            "main": int(main.lastrowid),
            "second": int(second.lastrowid),
            "usd": int(usd.lastrowid),
            "kzt": int(kzt.lastrowid),
            "other": int(other.lastrowid),
            "category": int(category.lastrowid),
        }
    finally:
        await db.close()


async def _insert_expense(path: Path, account_id: int, category_id: int, amount: int) -> int:
    now = "2026-09-16T01:00:00+00:00"
    db = await open_db(str(path))
    try:
        cur = await db.execute(
            "INSERT INTO transactions(user_id,ts,type,amount,account_id,category_id,note,created_at) "
            "VALUES(1,?,'expense',?,?,?,?,?)",
            (now, -amount, account_id, category_id, "test", now),
        )
        await db.execute(
            "UPDATE accounts SET balance=balance-? WHERE user_id=1 AND id=?",
            (amount, account_id),
        )
        await db.commit()
        return int(cur.lastrowid)
    finally:
        await db.close()


async def _balance(path: Path, account_id: int) -> int:
    db = await open_db(str(path))
    try:
        row = await (await db.execute(
            "SELECT balance FROM accounts WHERE id=?",
            (account_id,),
        )).fetchone()
        return int(row[0])
    finally:
        await db.close()


async def check() -> None:
    # Transaction mutations trigger AI recomputation after commit. Disable it in
    # this deterministic integrity check so only ledger invariants are tested.
    ai_event_worker.trigger_background_ai_analysis = _noop_ai_analysis

    fd, path_str = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    path = Path(path_str)
    settings.db_path = str(path)

    try:
        ids = await _seed_db(path)

        # 1. Two concurrent deletes must revert the balance exactly once.
        tx_id = await _insert_expense(path, ids["main"], ids["category"], 1000)
        db1 = await open_db(str(path))
        db2 = await open_db(str(path))
        try:
            results = await asyncio.gather(
                delete_tx(db1, 1, tx_id),
                delete_tx(db2, 1, tx_id),
            )
        finally:
            await db1.close()
            await db2.close()
        assert sorted(result[0] for result in results) == [False, True]
        assert await _balance(path, ids["main"]) == 100000

        # 2. Two concurrent edits from 1000 -> 2000 must apply one net delta.
        tx_id = await _insert_expense(path, ids["main"], ids["category"], 1000)
        db1 = await open_db(str(path))
        db2 = await open_db(str(path))
        try:
            results = await asyncio.gather(
                update_tx(db1, 1, tx_id, new_amount=2000),
                update_tx(db2, 1, tx_id, new_amount=2000),
            )
        finally:
            await db1.close()
            await db2.close()
        assert results == [True, True]
        assert await _balance(path, ids["main"]) == 98000

        # 3. Negative edit amounts are rejected and do not change the balance.
        db = await open_db(str(path))
        try:
            ok = await update_tx(db, 1, tx_id, new_amount=-500)
        finally:
            await db.close()
        assert ok is False
        assert await _balance(path, ids["main"]) == 98000

        # 4. A transaction cannot be moved onto another user's account.
        db = await open_db(str(path))
        try:
            ok = await update_tx(db, 1, tx_id, new_account_id=ids["other"])
        finally:
            await db.close()
        assert ok is False
        assert await _balance(path, ids["main"]) == 98000
        assert await _balance(path, ids["other"]) == 50000

        # 5. Transactions linked to debt history cannot be edited/deleted through
        # the generic transaction API; otherwise debt balance and payment history
        # would diverge from the account ledger.
        now = "2026-09-16T01:30:00+00:00"
        db = await open_db(str(path))
        try:
            debt = await db.execute(
                "INSERT INTO debts(user_id,direction,dtype,title,total_amount,remaining_amount,payment_amount,"
                "next_payment_date,status,is_active,created_at,updated_at) "
                "VALUES(1,'out','private','Linked debt',5000,3000,2000,'2026-10-01','active',1,?,?)",
                (now, now),
            )
            debt_id = int(debt.lastrowid)
            await db.execute(
                "INSERT INTO debt_payments(debt_id,user_id,tx_id,account_id,amount,payment_date,created_at) "
                "VALUES(?,?,?,?,?,date('now'),datetime('now'))",
                (debt_id, 1, tx_id, ids["main"], 2000),
            )
            await db.commit()
        finally:
            await db.close()

        db = await open_db(str(path))
        try:
            deleted, reason = await delete_tx(db, 1, tx_id)
        finally:
            await db.close()
        assert deleted is False and reason == "linked_debt_payment"
        assert await _balance(path, ids["main"]) == 98000

        db = await open_db(str(path))
        try:
            ok = await update_tx(db, 1, tx_id, new_amount=2500)
        finally:
            await db.close()
        assert ok is False
        assert await _balance(path, ids["main"]) == 98000

        # 6. FX edits preserve the original conversion ratio.
        now = "2026-09-16T02:00:00+00:00"
        db = await open_db(str(path))
        try:
            source = await db.execute(
                "INSERT INTO transactions(user_id,ts,type,amount,account_id,category_id,note,created_at) "
                "VALUES(1,?,'transfer',-100,?,NULL,'fx',?)",
                (now, ids["usd"], now),
            )
            source_id = int(source.lastrowid)
            target = await db.execute(
                "INSERT INTO transactions(user_id,ts,type,amount,account_id,category_id,note,related_tx_id,created_at) "
                "VALUES(1,?,'transfer',45000,?,NULL,'fx',?,?)",
                (now, ids["kzt"], source_id, now),
            )
            target_id = int(target.lastrowid)
            await db.execute(
                "UPDATE transactions SET related_tx_id=? WHERE id=?",
                (target_id, source_id),
            )
            await db.execute("UPDATE accounts SET balance=balance-100 WHERE id=?", (ids["usd"],))
            await db.execute("UPDATE accounts SET balance=balance+45000 WHERE id=?", (ids["kzt"],))
            await db.commit()
        finally:
            await db.close()

        db = await open_db(str(path))
        try:
            ok = await update_tx(db, 1, source_id, new_amount=200)
        finally:
            await db.close()
        assert ok is True

        db = await open_db(str(path))
        try:
            rows = await (await db.execute(
                "SELECT amount,account_id FROM transactions WHERE id IN (?,?) ORDER BY amount",
                (source_id, target_id),
            )).fetchall()
        finally:
            await db.close()
        assert [int(row[0]) for row in rows] == [-200, 90000]
        assert await _balance(path, ids["usd"]) == 800
        assert await _balance(path, ids["kzt"]) == 90000

    finally:
        await asyncio.sleep(0)
        for suffix in ("", "-wal", "-shm"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(check())
    print("Financial integrity checks OK")
