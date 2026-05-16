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
    # Atomic: all 5 writes must succeed or none, otherwise balances vs ledger diverge.
    await db.execute("BEGIN IMMEDIATE")
    try:
        tx1 = await create_tx(db, user_id, ts_iso, "transfer", -amount, from_acc, None, note, created_at, None)
        tx2 = await create_tx(db, user_id, ts_iso, "transfer", amount, to_acc, None, note, created_at, tx1)
        await db.execute("UPDATE transactions SET related_tx_id=? WHERE id=?", (tx2, tx1))
        await apply_balance_delta(db, user_id, from_acc, -amount)
        await apply_balance_delta(db, user_id, to_acc, amount)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return tx1, tx2

async def list_last(db: aiosqlite.Connection, user_id: int, limit: int = 10):
    cur = await db.execute(
        "SELECT t.id, t.ts, t.type, t.amount, a.name, t.note "
        "FROM transactions t JOIN accounts a ON a.id=t.account_id "
        "WHERE t.user_id=? AND t.deleted_at IS NULL "
        "ORDER BY t.id DESC LIMIT ?",
        (user_id, limit),
    )
    return await cur.fetchall()

async def delete_tx(db: aiosqlite.Connection, user_id: int, tx_id: int):
    cur = await db.execute(
        "SELECT id, type, amount, account_id, related_tx_id FROM transactions WHERE user_id=? AND id=? AND deleted_at IS NULL",
        (user_id, tx_id),
    )
    row = await cur.fetchone()
    if not row:
        return False, "not_found"
    _id, tx_type, amount, account_id, related = row

    # Atomic: balance revert + ledger soft-delete must be all-or-nothing.
    from datetime import datetime, timezone
    deleted_at = datetime.now(timezone.utc).isoformat()

    await db.execute("BEGIN IMMEDIATE")
    try:
        if tx_type == "transfer":
            if related:
                cur2 = await db.execute(
                    "SELECT id, amount, account_id FROM transactions WHERE user_id=? AND id=? AND deleted_at IS NULL",
                    (user_id, related),
                )
                r2 = await cur2.fetchone()
            else:
                r2 = None
            await apply_balance_delta(db, user_id, account_id, -amount)
            if r2:
                rid, ramount, racc = r2
                await apply_balance_delta(db, user_id, racc, -ramount)
                await db.execute(
                    "UPDATE transactions SET deleted_at=? WHERE user_id=? AND id IN (?,?)",
                    (deleted_at, user_id, tx_id, rid),
                )
                await _audit_log(db, user_id, tx_id, "delete", deleted_at, related_id=rid)
                await _audit_log(db, user_id, rid, "delete", deleted_at, related_id=tx_id)
            else:
                await db.execute(
                    "UPDATE transactions SET deleted_at=? WHERE user_id=? AND id=?",
                    (deleted_at, user_id, tx_id),
                )
                await _audit_log(db, user_id, tx_id, "delete", deleted_at)
        else:
            await apply_balance_delta(db, user_id, account_id, -amount)
            await db.execute(
                "UPDATE transactions SET deleted_at=? WHERE user_id=? AND id=?",
                (deleted_at, user_id, tx_id),
            )
            await _audit_log(db, user_id, tx_id, "delete", deleted_at)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return True, "ok"


async def _audit_log(
    db: aiosqlite.Connection,
    user_id: int,
    tx_id: int,
    action: str,
    at: str,
    related_id: int | None = None,
) -> None:
    """Best-effort write to tx_audit (table is created by migration 011)."""
    try:
        await db.execute(
            "INSERT INTO tx_audit(user_id, tx_id, action, at, related_id) VALUES(?,?,?,?,?)",
            (user_id, tx_id, action, at, related_id),
        )
    except Exception:
        # Migration not yet applied or table missing — don't block the user.
        pass
