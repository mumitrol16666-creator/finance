from __future__ import annotations

import aiosqlite

from app.db.repositories.accounts_repo import apply_balance_delta


async def _get_owned_account(db: aiosqlite.Connection, user_id: int, account_id: int):
    cur = await db.execute(
        "SELECT id, currency, is_archived FROM accounts WHERE user_id=? AND id=?",
        (user_id, account_id),
    )
    return await cur.fetchone()


async def _category_belongs_to_user(db: aiosqlite.Connection, user_id: int, category_id: int) -> bool:
    cur = await db.execute(
        "SELECT 1 FROM categories WHERE user_id=? AND id=? LIMIT 1",
        (user_id, category_id),
    )
    return await cur.fetchone() is not None


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
        "SELECT t.id, t.ts, t.type, t.amount, "
        "       (CASE WHEN t.type='transfer' AND dest_a.name IS NOT NULL "
        "             THEN a.name || ' ➡️ ' || dest_a.name "
        "             ELSE a.name END) as account_name, "
        "       t.note "
        "FROM transactions t "
        "JOIN accounts a ON a.id=t.account_id "
        "LEFT JOIN transactions dest_t ON dest_t.id=t.related_tx_id AND t.type='transfer' "
        "LEFT JOIN accounts dest_a ON dest_a.id=dest_t.account_id "
        "WHERE t.user_id=? AND t.deleted_at IS NULL AND (t.type != 'transfer' OR t.amount < 0) "
        "ORDER BY t.id DESC LIMIT ?",
        (user_id, limit),
    )
    return await cur.fetchall()


async def delete_tx(db: aiosqlite.Connection, user_id: int, tx_id: int):
    # Lock before reading the ledger row. Otherwise two concurrent requests can
    # both observe the same active transaction and revert its balance twice.
    await db.execute("BEGIN IMMEDIATE")
    try:
        cur = await db.execute(
            "SELECT id, type, amount, account_id, related_tx_id FROM transactions "
            "WHERE user_id=? AND id=? AND deleted_at IS NULL",
            (user_id, tx_id),
        )
        row = await cur.fetchone()
        if not row:
            await db.rollback()
            return False, "not_found"

        _id, tx_type, amount, account_id, related = row

        from datetime import datetime, timezone
        deleted_at = datetime.now(timezone.utc).isoformat()

        if tx_type == "transfer":
            if related:
                cur2 = await db.execute(
                    "SELECT id, amount, account_id FROM transactions "
                    "WHERE user_id=? AND id=? AND deleted_at IS NULL",
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
                    "UPDATE transactions SET deleted_at=? WHERE user_id=? AND id IN (?,?) AND deleted_at IS NULL",
                    (deleted_at, user_id, tx_id, rid),
                )
                await _audit_log(db, user_id, tx_id, "delete", deleted_at, related_id=rid)
                await _audit_log(db, user_id, rid, "delete", deleted_at, related_id=tx_id)
            else:
                await db.execute(
                    "UPDATE transactions SET deleted_at=? WHERE user_id=? AND id=? AND deleted_at IS NULL",
                    (deleted_at, user_id, tx_id),
                )
                await _audit_log(db, user_id, tx_id, "delete", deleted_at)
        else:
            await apply_balance_delta(db, user_id, account_id, -amount)
            await db.execute(
                "UPDATE transactions SET deleted_at=? WHERE user_id=? AND id=? AND deleted_at IS NULL",
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
    """Updates a transaction and shifts balances atomically.

    The write lock is acquired before reading the current ledger state so two
    concurrent edits cannot both calculate deltas from the same stale row.
    For FX transfers, changing the source amount preserves the original
    destination/source ratio instead of replacing both sides with the same
    nominal number.
    """
    if new_amount is not None and int(new_amount) <= 0:
        return False

    await db.execute("BEGIN IMMEDIATE")
    try:
        cur = await db.execute(
            "SELECT id, type, amount, account_id, category_id, note, related_tx_id "
            "FROM transactions WHERE user_id=? AND id=? AND deleted_at IS NULL",
            (user_id, tx_id),
        )
        row = await cur.fetchone()
        if not row:
            await db.rollback()
            return False

        tx_id, ttype, amount, account_id, category_id, note, related_tx_id = row

        if new_category_id is not None and new_category_id != -1:
            if not await _category_belongs_to_user(db, user_id, int(new_category_id)):
                await db.rollback()
                return False

        if ttype == "transfer":
            if not related_tx_id:
                await db.rollback()
                return False

            cur2 = await db.execute(
                "SELECT id, amount, account_id FROM transactions "
                "WHERE user_id=? AND id=? AND deleted_at IS NULL",
                (user_id, related_tx_id),
            )
            r2 = await cur2.fetchone()
            if not r2:
                await db.rollback()
                return False

            if amount < 0:
                p_tx_id, p_amount, p_acc_id = tx_id, int(amount), int(account_id)
                r_tx_id, r_amount, r_acc_id = int(r2[0]), int(r2[1]), int(r2[2])
            else:
                p_tx_id, p_amount, p_acc_id = int(r2[0]), int(r2[1]), int(r2[2])
                r_tx_id, r_amount, r_acc_id = tx_id, int(amount), int(account_id)

            if p_amount >= 0 or r_amount <= 0:
                await db.rollback()
                return False

            p_account = await _get_owned_account(db, user_id, p_acc_id)
            r_account = await _get_owned_account(db, user_id, r_acc_id)
            if not p_account or not r_account:
                await db.rollback()
                return False

            target_p_acc_id = p_acc_id
            target_r_acc_id = r_acc_id

            if new_account_id is not None:
                new_p_account = await _get_owned_account(db, user_id, int(new_account_id))
                if not new_p_account or int(new_p_account[2] or 0) == 1:
                    await db.rollback()
                    return False
                if str(new_p_account[1]) != str(p_account[1]):
                    await db.rollback()
                    return False
                target_p_acc_id = int(new_account_id)

            if new_to_account_id is not None:
                new_r_account = await _get_owned_account(db, user_id, int(new_to_account_id))
                if not new_r_account or int(new_r_account[2] or 0) == 1:
                    await db.rollback()
                    return False
                if str(new_r_account[1]) != str(r_account[1]):
                    await db.rollback()
                    return False
                target_r_acc_id = int(new_to_account_id)

            if target_p_acc_id == target_r_acc_id:
                await db.rollback()
                return False

            if new_note is not None:
                await db.execute(
                    "UPDATE transactions SET note=? WHERE user_id=? AND id IN (?,?)",
                    (new_note, user_id, p_tx_id, r_tx_id),
                )

            new_p_amount = p_amount
            new_r_amount = r_amount
            if new_amount is not None:
                old_source = abs(int(p_amount))
                if old_source <= 0:
                    await db.rollback()
                    return False
                ratio = int(r_amount) / old_source
                new_p_amount = -int(new_amount)
                new_r_amount = max(1, int(round(int(new_amount) * ratio)))

            # First remove the old transfer effect from the original accounts.
            await apply_balance_delta(db, user_id, p_acc_id, -p_amount)
            await apply_balance_delta(db, user_id, r_acc_id, -r_amount)

            # Then apply the updated transfer once to the validated target accounts.
            await apply_balance_delta(db, user_id, target_p_acc_id, new_p_amount)
            await apply_balance_delta(db, user_id, target_r_acc_id, new_r_amount)

            await db.execute(
                "UPDATE transactions SET amount=?, account_id=? WHERE user_id=? AND id=?",
                (new_p_amount, target_p_acc_id, user_id, p_tx_id),
            )
            await db.execute(
                "UPDATE transactions SET amount=?, account_id=? WHERE user_id=? AND id=?",
                (new_r_amount, target_r_acc_id, user_id, r_tx_id),
            )

        else:
            target_acc = int(account_id)
            if new_account_id is not None:
                account = await _get_owned_account(db, user_id, int(new_account_id))
                if not account or int(account[2] or 0) == 1:
                    await db.rollback()
                    return False
                target_acc = int(new_account_id)

            if new_note is not None:
                await db.execute(
                    "UPDATE transactions SET note=? WHERE user_id=? AND id=?",
                    (new_note, user_id, tx_id),
                )

            if new_category_id is not None:
                # If set to -1, we store None (uncategorized)
                cat_val = None if new_category_id == -1 else int(new_category_id)
                await db.execute(
                    "UPDATE transactions SET category_id=? WHERE user_id=? AND id=?",
                    (cat_val, user_id, tx_id),
                )

            target_amount = int(amount)
            if new_amount is not None:
                if ttype == "expense":
                    target_amount = -int(new_amount)
                elif ttype in {"income", "starting_balance", "adjustment"}:
                    target_amount = int(new_amount)
                else:
                    await db.rollback()
                    return False

            if target_acc != int(account_id):
                await apply_balance_delta(db, user_id, int(account_id), -int(amount))
                await apply_balance_delta(db, user_id, target_acc, target_amount)
                await db.execute(
                    "UPDATE transactions SET account_id=?, amount=? WHERE user_id=? AND id=?",
                    (target_acc, target_amount, user_id, tx_id),
                )
            elif target_amount != int(amount):
                delta = target_amount - int(amount)
                await apply_balance_delta(db, user_id, int(account_id), delta)
                await db.execute(
                    "UPDATE transactions SET amount=? WHERE user_id=? AND id=?",
                    (target_amount, user_id, tx_id),
                )

        await db.commit()
    except Exception:
        await db.rollback()
        raise

    from app.domain.services.ai_event_worker import trigger_background_ai_analysis
    await trigger_background_ai_analysis(user_id)
    return True
