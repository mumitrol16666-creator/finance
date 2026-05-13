from __future__ import annotations
import aiosqlite
from app.db.repositories.accounts_repo import apply_balance_delta

async def create_tx(db: aiosqlite.Connection, user_id: int, ts_iso: str, tx_type: str, amount: int,
                    account_id: int, category_id: int | None, note: str | None, created_at: str,
                    related_tx_id: int | None = None) -> int:
    cur = await db.execute(
        "INSERT INTO transactions(user_id, ts, type, amount, account_id, category_id, note, related_tx_id, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (user_id, ts_iso, tx_type, amount, account_id, category_id, note, related_tx_id, created_at),
    )
    return int(cur.lastrowid)

async def apply_expense_income(db: aiosqlite.Connection, user_id: int, tx_id: int, amount: int, account_id: int):
    # update balance
    await apply_balance_delta(db, user_id, account_id, amount)

async def create_transfer(db: aiosqlite.Connection, user_id: int, ts_iso: str, from_acc: int, to_acc: int, amount: int, note: str | None, created_at: str):
    # from: -amount
    tx1 = await create_tx(db, user_id, ts_iso, "transfer", -amount, from_acc, None, note, created_at, None)
    # to: +amount
    tx2 = await create_tx(db, user_id, ts_iso, "transfer", amount, to_acc, None, note, created_at, tx1)
    # link back
    await db.execute("UPDATE transactions SET related_tx_id=? WHERE id=?", (tx2, tx1))
    # balances
    await apply_balance_delta(db, user_id, from_acc, -amount)
    await apply_balance_delta(db, user_id, to_acc, amount)
    return tx1, tx2

async def list_last(db: aiosqlite.Connection, user_id: int, limit: int = 10):
    cur = await db.execute(
        "SELECT t.id, t.ts, t.type, t.amount, a.name, t.note "
        "FROM transactions t JOIN accounts a ON a.id=t.account_id "
        "WHERE t.user_id=? ORDER BY t.id DESC LIMIT ?",
        (user_id, limit),
    )
    return await cur.fetchall()

async def delete_tx(db: aiosqlite.Connection, user_id: int, tx_id: int):
    # fetch
    cur = await db.execute(
        "SELECT id, type, amount, account_id, related_tx_id FROM transactions WHERE user_id=? AND id=?",
        (user_id, tx_id),
    )
    row = await cur.fetchone()
    if not row:
        return False, "not_found"
    _id, tx_type, amount, account_id, related = row
    if tx_type == "transfer":
        # delete both halves
        if related:
            # get related
            cur2 = await db.execute(
                "SELECT id, amount, account_id FROM transactions WHERE user_id=? AND id=?",
                (user_id, related),
            )
            r2 = await cur2.fetchone()
        else:
            r2 = None
        # revert balances
        await apply_balance_delta(db, user_id, account_id, -amount)
        if r2:
            rid, ramount, racc = r2
            await apply_balance_delta(db, user_id, racc, -ramount)
            await db.execute("DELETE FROM transactions WHERE user_id=? AND id IN (?,?)", (user_id, tx_id, rid))
        else:
            await db.execute("DELETE FROM transactions WHERE user_id=? AND id=?", (user_id, tx_id))
    else:
        await apply_balance_delta(db, user_id, account_id, -amount)
        await db.execute("DELETE FROM transactions WHERE user_id=? AND id=?", (user_id, tx_id))
    return True, "ok"
