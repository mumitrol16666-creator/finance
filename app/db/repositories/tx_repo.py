from __future__ import annotations
import aiosqlite
from app.db.repositories.accounts_repo import apply_balance_delta

async def create_tx(db: aiosqlite.Connection, user_id: int, ts_iso: str, tx_type: str, amount: int,
                    account_id: int, category_id: int | None, note: str | None, created_at: str,
                    related_tx_id: int | None = None, tier: str = 'routine') -> int:
    cur = await db.execute(
        "INSERT INTO transactions(user_id, ts, type, amount, account_id, category_id, note, related_tx_id, created_at, tier) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (user_id, ts_iso, tx_type, amount, account_id, category_id, note, related_tx_id, created_at, tier),
    )
    tx_id = int(cur.lastrowid)
    from app.domain.services.ai_event_worker import trigger_background_ai_analysis
    await trigger_background_ai_analysis(user_id)
    return tx_id

async def apply_expense_income(db: aiosqlite.Connection, user_id: int, tx_id: int, amount: int, account_id: int):
    # update balance
    await apply_balance_delta(db, user_id, account_id, amount)

async def create_transfer(db: aiosqlite.Connection, user_id: int, ts_iso: str, from_acc: int, to_acc: int, amount: int, note: str | None, created_at: str, to_amount: int | None = None):
    # Atomic: all 5 writes must succeed or none, otherwise balances vs ledger diverge.
    actual_to_amount = to_amount if to_amount is not None else amount
    await db.execute("BEGIN IMMEDIATE")
    try:
        tx1 = await create_tx(db, user_id, ts_iso, "transfer", -amount, from_acc, None, note, created_at, None)
        tx2 = await create_tx(db, user_id, ts_iso, "transfer", actual_to_amount, to_acc, None, note, created_at, tx1)
        await db.execute("UPDATE transactions SET related_tx_id=? WHERE id=?", (tx2, tx1))
        await apply_balance_delta(db, user_id, from_acc, -amount)
        await apply_balance_delta(db, user_id, to_acc, actual_to_amount)
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
    from app.domain.services.ai_event_worker import trigger_background_ai_analysis
    await trigger_background_ai_analysis(user_id)
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


async def get_expenses_for_period(
    db: aiosqlite.Connection, user_id: int, start_iso: str, end_iso: str
) -> list[tuple[int, str, str]]:
    """Returns a list of tuples: (amount, category_name, category_emoji)
    for all expenses in the given period.
    """
    cur = await db.execute(
        """
        SELECT t.amount, COALESCE(c.name, 'Без категории') as category_name, COALESCE(c.emoji, '') as category_emoji
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.user_id = ? AND t.type = 'expense' AND t.ts >= ? AND t.ts < ? AND t.deleted_at IS NULL
        """,
        (user_id, start_iso, end_iso),
    )
    rows = await cur.fetchall()
    return [(-row[0], row[1], row[2]) for row in rows]


async def get_last_active_tx(db: aiosqlite.Connection, user_id: int) -> dict | None:
    """Returns the last active transaction with account and category details."""
    cur = await db.execute(
        "SELECT t.id, t.ts, t.type, t.amount, t.account_id, t.category_id, t.note, t.related_tx_id, "
        "       a.name as account_name, a.currency, c.name as category_name, c.emoji as category_emoji "
        "FROM transactions t "
        "JOIN accounts a ON a.id = t.account_id "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "WHERE t.user_id = ? AND t.deleted_at IS NULL "
        "ORDER BY t.id DESC LIMIT 1",
        (user_id,)
    )
    row = await cur.fetchone()
    if not row:
        return None

    tx_id, ts, ttype, amount, account_id, category_id, note, related_tx_id, acc_name, currency, cat_name, cat_emoji = row
    if ttype == "transfer" and related_tx_id:
        cur2 = await db.execute(
            "SELECT t.id, t.amount, t.account_id, a.name, a.currency "
            "FROM transactions t JOIN accounts a ON a.id = t.account_id "
            "WHERE t.id = ? AND t.deleted_at IS NULL",
            (related_tx_id,)
        )
        r2 = await cur2.fetchone()
        if r2:
            rid, ramount, racc_id, racc_name, rcurrency = r2
            if amount < 0:
                return {
                    "id": tx_id,
                    "ts": ts,
                    "type": "transfer",
                    "from_account_id": account_id,
                    "from_account_name": acc_name,
                    "from_currency": currency,
                    "to_account_id": racc_id,
                    "to_account_name": racc_name,
                    "to_currency": rcurrency,
                    "amount": abs(amount),
                    "note": note,
                    "primary_id": tx_id,
                    "related_id": rid,
                }
            else:
                return {
                    "id": rid,
                    "ts": ts,
                    "type": "transfer",
                    "from_account_id": racc_id,
                    "from_account_name": racc_name,
                    "from_currency": rcurrency,
                    "to_account_id": account_id,
                    "to_account_name": acc_name,
                    "to_currency": currency,
                    "amount": abs(ramount),
                    "note": note,
                    "primary_id": rid,
                    "related_id": tx_id,
                }

    return {
        "id": tx_id,
        "ts": ts,
        "type": ttype,
        "amount": amount,
        "account_id": account_id,
        "account_name": acc_name,
        "currency": currency,
        "category_id": category_id,
        "category_name": cat_name,
        "category_emoji": cat_emoji,
        "note": note,
    }


async def update_tx(db: aiosqlite.Connection, user_id: int, tx_id: int, *,
                    new_amount: int | None = None,
                    new_category_id: int | None = None,
                    new_note: str | None = None,
                    new_account_id: int | None = None,
                    new_to_account_id: int | None = None) -> bool:
    """Updates transaction and shifts balances accordingly."""
    cur = await db.execute(
        "SELECT id, type, amount, account_id, category_id, note, related_tx_id "
        "FROM transactions WHERE user_id=? AND id=? AND deleted_at IS NULL",
        (user_id, tx_id),
    )
    row = await cur.fetchone()
    if not row:
        return False

    tx_id, ttype, amount, account_id, category_id, note, related_tx_id = row

    await db.execute("BEGIN IMMEDIATE")
    try:
        if ttype == "transfer":
            if related_tx_id:
                cur2 = await db.execute(
                    "SELECT id, amount, account_id FROM transactions WHERE user_id=? AND id=? AND deleted_at IS NULL",
                    (user_id, related_tx_id),
                )
                r2 = await cur2.fetchone()
            else:
                r2 = None

            if amount < 0:
                p_tx_id, p_amount, p_acc_id = tx_id, amount, account_id
                r_tx_id, r_amount, r_acc_id = (r2[0], r2[1], r2[2]) if r2 else (None, None, None)
            else:
                p_tx_id, p_amount, p_acc_id = (r2[0], r2[1], r2[2]) if r2 else (None, None, None)
                r_tx_id, r_amount, r_acc_id = tx_id, amount, account_id

            if new_note is not None:
                await db.execute("UPDATE transactions SET note=? WHERE id=?", (new_note, tx_id))
                if related_tx_id:
                    await db.execute("UPDATE transactions SET note=? WHERE id=?", (new_note, related_tx_id))

            if new_amount is not None:
                new_p_amount = -new_amount
                new_r_amount = new_amount

                if p_tx_id:
                    p_delta = new_p_amount - p_amount
                    await apply_balance_delta(db, user_id, p_acc_id, p_delta)
                    await db.execute("UPDATE transactions SET amount=? WHERE id=?", (new_p_amount, p_tx_id))
                    p_amount = new_p_amount

                if r_tx_id:
                    r_delta = new_r_amount - r_amount
                    await apply_balance_delta(db, user_id, r_acc_id, r_delta)
                    await db.execute("UPDATE transactions SET amount=? WHERE id=?", (new_r_amount, r_tx_id))
                    r_amount = new_r_amount

            if new_account_id is not None and p_tx_id and new_account_id != p_acc_id:
                await apply_balance_delta(db, user_id, p_acc_id, -p_amount)
                await apply_balance_delta(db, user_id, new_account_id, p_amount)
                await db.execute("UPDATE transactions SET account_id=? WHERE id=?", (new_account_id, p_tx_id))
                p_acc_id = new_account_id

            if new_to_account_id is not None and r_tx_id and new_to_account_id != r_acc_id:
                await apply_balance_delta(db, user_id, r_acc_id, -r_amount)
                await apply_balance_delta(db, user_id, new_to_account_id, r_amount)
                await db.execute("UPDATE transactions SET account_id=? WHERE id=?", (new_to_account_id, r_tx_id))
                r_acc_id = new_to_account_id

        else:
            if new_note is not None:
                await db.execute("UPDATE transactions SET note=? WHERE id=?", (new_note, tx_id))

            if new_category_id is not None:
                # If set to -1, we store None (uncategorized)
                cat_val = None if new_category_id == -1 else new_category_id
                await db.execute("UPDATE transactions SET category_id=? WHERE id=?", (cat_val, tx_id))

            target_amount = amount
            if new_amount is not None:
                if ttype == "expense":
                    target_amount = -new_amount
                else:
                    target_amount = new_amount

            target_acc = account_id
            if new_account_id is not None:
                target_acc = new_account_id

            if target_acc != account_id:
                await apply_balance_delta(db, user_id, account_id, -amount)
                await apply_balance_delta(db, user_id, target_acc, target_amount)
                await db.execute("UPDATE transactions SET account_id=?, amount=? WHERE id=?", (target_acc, target_amount, tx_id))
            elif target_amount != amount:
                delta = target_amount - amount
                await apply_balance_delta(db, user_id, account_id, delta)
                await db.execute("UPDATE transactions SET amount=? WHERE id=?", (target_amount, tx_id))

        await db.commit()
    except Exception:
        await db.rollback()
        raise

    from app.domain.services.ai_event_worker import trigger_background_ai_analysis
    await trigger_background_ai_analysis(user_id)
    return True


