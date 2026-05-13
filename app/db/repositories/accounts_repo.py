from __future__ import annotations
import aiosqlite


async def count_accounts(db: aiosqlite.Connection, user_id: int) -> int:
    cur = await db.execute("SELECT COUNT(*) FROM accounts WHERE user_id=? AND is_archived=0", (user_id,))
    (cnt,) = await cur.fetchone()
    return int(cnt)


async def list_accounts(db: aiosqlite.Connection, user_id: int, include_archived: bool = False):
    q = "SELECT id, name, balance, is_archived FROM accounts WHERE user_id=?"
    if not include_archived:
        q += " AND is_archived=0"
    q += " ORDER BY is_archived, id"
    cur = await db.execute(q, (user_id,))
    return await cur.fetchall()


async def list_archived_accounts(db: aiosqlite.Connection, user_id: int):
    cur = await db.execute(
        "SELECT id, name, balance, is_archived FROM accounts WHERE user_id=? AND is_archived=1 ORDER BY id",
        (user_id,),
    )
    return await cur.fetchall()


async def get_account(db: aiosqlite.Connection, user_id: int, account_id: int):
    cur = await db.execute(
        "SELECT id, name, balance, is_archived FROM accounts WHERE user_id=? AND id=?",
        (user_id, account_id),
    )
    return await cur.fetchone()


async def get_account_by_name(db: aiosqlite.Connection, user_id: int, name: str):
    cur = await db.execute(
        "SELECT id, name, balance, is_archived FROM accounts WHERE user_id=? AND lower(name)=lower(?) LIMIT 1",
        (user_id, name),
    )
    return await cur.fetchone()


async def has_active_account_with_name(db: aiosqlite.Connection, user_id: int, name: str, exclude_account_id: int | None = None) -> bool:
    q = "SELECT 1 FROM accounts WHERE user_id=? AND is_archived=0 AND lower(name)=lower(?)"
    params: list[object] = [user_id, name]
    if exclude_account_id is not None:
        q += " AND id<>?"
        params.append(exclude_account_id)
    q += " LIMIT 1"
    cur = await db.execute(q, tuple(params))
    return await cur.fetchone() is not None


async def create_account(db: aiosqlite.Connection, user_id: int, name: str, balance: int, ts: str):
    existing = await get_account_by_name(db, user_id, name)
    if existing:
        acc_id, _name, _balance, is_archived = existing
        if int(is_archived or 0) == 1:
            await db.execute(
                "UPDATE accounts SET balance=?, is_archived=0, updated_at=? WHERE user_id=? AND id=?",
                (balance, ts, user_id, acc_id),
            )
            return acc_id, 'restored'
        raise ValueError('active_name_exists')

    cur = await db.execute(
        "INSERT INTO accounts(user_id, name, balance, is_archived, created_at, updated_at) VALUES(?,?,?,0,?,?)",
        (user_id, name, balance, ts, ts),
    )
    return cur.lastrowid, 'created'


async def rename_account(db: aiosqlite.Connection, user_id: int, account_id: int, new_name: str, ts: str):
    if await has_active_account_with_name(db, user_id, new_name, exclude_account_id=account_id):
        raise ValueError('active_name_exists')
    await db.execute(
        "UPDATE accounts SET name=?, updated_at=? WHERE user_id=? AND id=?",
        (new_name, ts, user_id, account_id),
    )


async def archive_account(db: aiosqlite.Connection, user_id: int, account_id: int, ts: str):
    await db.execute(
        "UPDATE accounts SET is_archived=1, updated_at=? WHERE user_id=? AND id=?",
        (ts, user_id, account_id),
    )


async def restore_account(db: aiosqlite.Connection, user_id: int, account_id: int, ts: str):
    acc = await get_account(db, user_id, account_id)
    if not acc:
        raise ValueError('account_not_found')
    _acc_id, name, _balance, _is_archived = acc
    if await has_active_account_with_name(db, user_id, str(name), exclude_account_id=account_id):
        raise ValueError('active_name_exists')
    await db.execute(
        "UPDATE accounts SET is_archived=0, updated_at=? WHERE user_id=? AND id=?",
        (ts, user_id, account_id),
    )


async def account_has_transactions(db: aiosqlite.Connection, user_id: int, account_id: int) -> bool:
    cur = await db.execute(
        "SELECT 1 FROM transactions WHERE user_id=? AND account_id=? LIMIT 1",
        (user_id, account_id),
    )
    return await cur.fetchone() is not None


async def delete_account_permanently(db: aiosqlite.Connection, user_id: int, account_id: int):
    await db.execute(
        "DELETE FROM accounts WHERE user_id=? AND id=? AND is_archived=1",
        (user_id, account_id),
    )


async def apply_balance_delta(db: aiosqlite.Connection, user_id: int, account_id: int, delta: int):
    await db.execute(
        "UPDATE accounts SET balance = balance + ? WHERE user_id=? AND id=?",
        (delta, user_id, account_id),
    )


async def set_account_balance(db: aiosqlite.Connection, user_id: int, account_id: int, new_balance: int, ts: str):
    await db.execute(
        "UPDATE accounts SET balance=?, updated_at=? WHERE user_id=? AND id=?",
        (new_balance, ts, user_id, account_id),
    )
