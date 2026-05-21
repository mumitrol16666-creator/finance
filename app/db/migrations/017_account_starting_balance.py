from __future__ import annotations
import aiosqlite


async def _column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    cur = await db.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    return any(row[1] == column for row in rows)


async def apply(db: aiosqlite.Connection) -> None:
    # 1. Add column if not exists
    if not await _column_exists(db, "accounts", "starting_balance"):
        await db.execute("ALTER TABLE accounts ADD COLUMN starting_balance INTEGER NOT NULL DEFAULT 0")

    # 2. Reconcile existing accounts
    cur = await db.execute("SELECT id, user_id, balance, created_at FROM accounts")
    accounts = await cur.fetchall()

    for acc in accounts:
        acc_id, user_id, balance, created_at = acc

        # Check if starting_balance transaction already exists
        cur_tx = await db.execute(
            "SELECT id, amount FROM transactions WHERE account_id=? AND type='starting_balance' AND deleted_at IS NULL LIMIT 1",
            (acc_id,),
        )
        tx_row = await cur_tx.fetchone()

        if tx_row:
            tx_id, tx_amount = tx_row
            # Just ensure starting_balance matches
            await db.execute(
                "UPDATE accounts SET starting_balance=? WHERE id=?",
                (tx_amount, acc_id),
            )
        else:
            # Calculate sum of other transactions
            cur_sum = await db.execute(
                "SELECT SUM(amount) FROM transactions WHERE account_id=? AND deleted_at IS NULL",
                (acc_id,),
            )
            (tx_sum,) = await cur_sum.fetchone()
            tx_sum = int(tx_sum or 0)

            # starting_balance + tx_sum = balance  => starting_balance = balance - tx_sum
            starting_bal = balance - tx_sum

            await db.execute(
                "UPDATE accounts SET starting_balance=? WHERE id=?",
                (starting_bal, acc_id),
            )

            if starting_bal != 0:
                cur_lang = await db.execute("SELECT lang FROM settings WHERE user_id=? LIMIT 1", (user_id,))
                lang_row = await cur_lang.fetchone()
                lang = lang_row[0] if lang_row else 'ru'
                
                note = {
                    "ru": "Стартовый баланс",
                    "en": "Starting balance",
                    "kk": "Бастапқы баланс",
                }.get(lang, "Стартовый баланс")

                await db.execute(
                    "INSERT INTO transactions(user_id, ts, type, amount, account_id, category_id, note, created_at) "
                    "VALUES(?,?,?,?,?,NULL,?,?)",
                    (user_id, created_at, "starting_balance", starting_bal, acc_id, note, created_at),
                )

    await db.commit()
