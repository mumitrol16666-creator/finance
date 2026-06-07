import asyncio
import os
import sys
import aiosqlite

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.connection import get_db

async def run_tests():
    print("Starting verification tests...")
    
    async with get_db() as db:
        # Define test user credentials
        test_user_id = 9999999
        test_username = "test_verification_user_xyz"
        test_password_hash = "mock_hash"
        
        # Clean up any leftover test data
        await db.execute("DELETE FROM users WHERE id = ? OR username = ?", (test_user_id, test_username))
        await db.execute("DELETE FROM settings WHERE user_id = ?", (test_user_id,))
        await db.execute("DELETE FROM accounts WHERE user_id = ?", (test_user_id,))
        await db.commit()
        
        # Test 1: Insert user with defaults similar to registration
        print("\nTest 1: Testing Registration Defaults...")
        now_str = "2026-06-06T12:00:00"
        
        # Insert user
        cur = await db.execute(
            "INSERT INTO users (id, username, password_hash, display_name, onboarding_state, created_at, onboarded) "
            "VALUES (?, ?, ?, 'Test User', 'completed', ?, 1)",
            (test_user_id, test_username, test_password_hash, now_str)
        )
        
        # Insert settings
        await db.execute(
            "INSERT INTO settings (user_id, lang, currency, created_at, updated_at) VALUES (?, 'ru', 'KZT', ?, ?)",
            (test_user_id, now_str, now_str)
        )
        
        # Insert default account
        await db.execute(
            "INSERT INTO accounts (user_id, name, balance, starting_balance, currency, is_saving, is_archived, created_at, updated_at) "
            "VALUES (?, 'Основной', 0, 0, 'KZT', 0, 0, ?, ?)",
            (test_user_id, now_str, now_str)
        )
        await db.commit()
        
        # Verify
        cur = await db.execute("SELECT lang, currency FROM settings WHERE user_id = ?", (test_user_id,))
        settings_row = await cur.fetchone()
        print(f"Settings created: lang={settings_row[0]}, currency={settings_row[1]}")
        assert settings_row[0] == "ru"
        assert settings_row[1] == "KZT"
        
        cur = await db.execute("SELECT name, balance, currency FROM accounts WHERE user_id = ?", (test_user_id,))
        account_row = await cur.fetchone()
        print(f"Account created: name='{account_row[0]}', balance={account_row[1]}, currency='{account_row[2]}'")
        assert account_row[0] == "Основной"
        assert account_row[1] == 0
        assert account_row[2] == "KZT"
        print("Registration defaults test passed!")
        
        # Test 2: Verify all Admin Queries from admin.py
        print("\nTest 2: Verifying Admin SQL queries...")
        
        # admin_export_stats queries
        users_query = """
            SELECT 
                u.id, 
                u.full_access, 
                u.created_at,
                s.lang, 
                s.timezone,
                (SELECT COUNT(*) FROM accounts a WHERE a.user_id = u.id AND a.is_archived = 0) as accounts_count,
                (SELECT COUNT(*) FROM transactions t WHERE t.user_id = u.id AND t.deleted_at IS NULL) as tx_count,
                (SELECT COUNT(*) FROM debts d WHERE d.user_id = u.id AND d.closed_at IS NULL) as active_debts,
                u.telegram_id,
                u.username,
                u.display_name
            FROM users u
            LEFT JOIN settings s ON u.id = s.user_id
            ORDER BY u.created_at DESC
        """
        async with db.execute(users_query) as cursor:
            users = await cursor.fetchall()
            print(f"admin_export_stats users query returned {len(users)} users.")
            
        accounts_query = """
            SELECT 
                a.user_id, 
                a.name, 
                a.balance, 
                a.currency, 
                a.is_saving
            FROM accounts a
            WHERE a.is_archived = 0
            ORDER BY a.user_id, a.name
        """
        async with db.execute(accounts_query) as cursor:
            accounts = await cursor.fetchall()
            print(f"admin_export_stats accounts query returned {len(accounts)} accounts.")
            
        # admin_user_info query
        cur = await db.execute("SELECT id, telegram_id, username, display_name, created_at FROM users WHERE id = ? OR telegram_id = ?", (test_user_id, test_user_id))
        row = await cur.fetchone()
        assert row is not None
        print(f"admin_user_info query succeeded: db_user_id={row[0]}, telegram_id={row[1]}, username={row[2]}")
        
        # admin_grant_access update & check
        cur = await db.execute("SELECT id, telegram_id FROM users WHERE id = ? OR telegram_id = ?", (test_user_id, test_user_id))
        row = await cur.fetchone()
        db_user_id = row[0]
        
        from app.db.repositories.users_repo import grant_full_access
        await grant_full_access(db, db_user_id, days=10)
        await db.execute(
            "UPDATE settings SET trial_reminder_sent = 0, updated_at = ? WHERE user_id = ?",
            (now_str, db_user_id)
        )
        await db.commit()
        
        cur = await db.execute("SELECT full_access FROM users WHERE id = ?", (db_user_id,))
        full_access_val = (await cur.fetchone())[0]
        print(f"After grant: full_access={full_access_val}")
        assert full_access_val == 1
        
        # admin_revoke_access update & check
        await db.execute(
            "UPDATE users SET full_access = 0, mode = 'newbie' WHERE id = ?",
            (db_user_id,)
        )
        await db.commit()
        cur = await db.execute("SELECT full_access, mode FROM users WHERE id = ?", (db_user_id,))
        row = await cur.fetchone()
        print(f"After revoke: full_access={row[0]}, mode={row[1]}")
        assert row[0] == 0
        assert row[1] == "newbie"
        
        # admin_streak update & check
        streak_value = 5
        new_max = 5
        await db.execute(
            "UPDATE users SET current_streak = ?, max_streak = ?, last_activity_date = ? WHERE id = ?",
            (streak_value, new_max, now_str, db_user_id)
        )
        await db.commit()
        cur = await db.execute("SELECT current_streak, max_streak FROM users WHERE id = ?", (db_user_id,))
        row = await cur.fetchone()
        print(f"After streak: current_streak={row[0]}, max_streak={row[1]}")
        assert row[0] == 5
        assert row[1] == 5
        
        # admin_reports update & check
        from app.db.repositories.settings_repo import add_ai_reports_extra
        await add_ai_reports_extra(db, db_user_id, 3, now_str)
        await db.commit()
        cur = await db.execute("SELECT ai_reports_extra FROM settings WHERE user_id = ?", (db_user_id,))
        reports_extra = (await cur.fetchone())[0]
        print(f"After reports: ai_reports_extra={reports_extra}")
        assert reports_extra == 3
        
        # admin_delete query
        from app.db.repositories.reset_repo import delete_user_account
        await delete_user_account(db, db_user_id)
        cur = await db.execute("SELECT 1 FROM users WHERE id = ?", (db_user_id,))
        row = await cur.fetchone()
        print(f"After delete Test 2 User: user exists={row is not None}")
        assert row is None
        print("Admin queries test passed!")

        # Test 3: Verify atomic debt payments and undo behavior
        print("\nTest 3: Verifying atomic debt payments and undo logic...")
        # Create a new test user for Test 3
        test_user_id_3 = 9888888
        test_username_3 = "test_user_atomicity_3"
        await db.execute("DELETE FROM users WHERE id = ? OR username = ?", (test_user_id_3, test_username_3))
        await db.execute("DELETE FROM settings WHERE user_id = ?", (test_user_id_3,))
        await db.execute("DELETE FROM accounts WHERE user_id = ?", (test_user_id_3,))
        await db.execute("DELETE FROM debts WHERE user_id = ?", (test_user_id_3,))
        await db.execute("DELETE FROM transactions WHERE user_id = ?", (test_user_id_3,))
        await db.commit()

        # Insert user
        await db.execute(
            "INSERT INTO users (id, username, password_hash, display_name, onboarding_state, created_at, onboarded) "
            "VALUES (?, ?, ?, 'Test User 3', 'completed', ?, 1)",
            (test_user_id_3, test_username_3, test_password_hash, now_str)
        )
        # Insert settings
        await db.execute(
            "INSERT INTO settings (user_id, lang, currency, created_at, updated_at) VALUES (?, 'ru', 'KZT', ?, ?)",
            (test_user_id_3, now_str, now_str)
        )
        # Insert default account
        cur = await db.execute(
            "INSERT INTO accounts (user_id, name, balance, starting_balance, currency, is_saving, is_archived, created_at, updated_at) "
            "VALUES (?, 'Основной', 50000, 50000, 'KZT', 0, 0, ?, ?)",
            (test_user_id_3, now_str, now_str)
        )
        account_id = int(cur.lastrowid)

        # Insert a debt (direction='out', dtype='private', total_amount=20000, remaining_amount=20000)
        from app.db.repositories.debts_repo import add_debt, get_debt, apply_debt_payment
        debt_id = await add_debt(
            db=db,
            user_id=test_user_id_3,
            direction="out",
            dtype="private",
            title="Friend loan",
            payment_amount=5000,
            next_payment_date="2026-06-10",
            remaining_amount=20000,
        )

        # Verify initial remaining amount
        debt_row = await get_debt(db, test_user_id_3, debt_id)
        assert debt_row is not None
        rem_initial = debt_row[5] if not hasattr(debt_row, "keys") else debt_row["remaining_amount"]
        print(f"Initial remaining debt: {rem_initial}")

        # 3.1: Simulate a failure during a transaction and verify rollback works.
        await db.execute("BEGIN IMMEDIATE")
        try:
            from app.domain.services.accounting_service import add_expense
            await add_expense(db, test_user_id_3, 5000, account_id, None, "Rollback test", commit=False)
            await apply_debt_payment(db, test_user_id_3, debt_id, 5000, "2026-07-10", commit=False)
            # Force an intentional exception
            raise ValueError("Intentional error for rollback verification")
        except ValueError:
            await db.rollback()

        # Verify that NOTHING was committed:
        # Debt remaining should still be 20000, account balance should still be 50000, no transactions.
        cur = await db.execute("SELECT balance FROM accounts WHERE id = ?", (account_id,))
        bal = (await cur.fetchone())[0]
        print(f"Balance after rolled-back payment: {bal}")
        assert bal == 50000

        debt_row = await get_debt(db, test_user_id_3, debt_id)
        rem = debt_row[5] if not hasattr(debt_row, "keys") else debt_row["remaining_amount"]
        print(f"Debt remaining after rolled-back payment: {rem}")
        assert int(rem) == 20000

        # 3.2: Verify a successful atomic payment.
        await db.execute("BEGIN IMMEDIATE")
        try:
            await add_expense(db, test_user_id_3, 5000, account_id, None, "Success payment test", commit=False)
            await apply_debt_payment(db, test_user_id_3, debt_id, 5000, "2026-07-10", commit=False)
            await db.commit()
        except Exception:
            await db.rollback()
            raise

        # Verify that changes WERE committed:
        cur = await db.execute("SELECT balance FROM accounts WHERE id = ?", (account_id,))
        bal = (await cur.fetchone())[0]
        print(f"Balance after successful payment: {bal}")
        assert bal == 45000

        debt_row = await get_debt(db, test_user_id_3, debt_id)
        rem = debt_row[5] if not hasattr(debt_row, "keys") else debt_row["remaining_amount"]
        print(f"Debt remaining after successful payment: {rem}")
        assert int(rem) == 15000

        # 3.3: Verify undo functionality
        from app.db.repositories.tx_repo import list_last, delete_tx
        last_txs = await list_last(db, test_user_id_3, limit=1)
        assert len(last_txs) == 1
        tx_id = last_txs[0][0]
        print(f"Last transaction ID: {tx_id}")

        # Undo the transaction
        ok, msg = await delete_tx(db, test_user_id_3, tx_id)
        await db.commit()
        assert ok is True
        print(f"Undo result: ok={ok}, status={msg}")

        # Account balance should be reverted back to 50000
        cur = await db.execute("SELECT balance FROM accounts WHERE id = ?", (account_id,))
        bal = (await cur.fetchone())[0]
        print(f"Balance after undoing transaction: {bal}")
        assert bal == 50000

        # Clean up
        from app.db.repositories.reset_repo import delete_user_account
        await delete_user_account(db, test_user_id_3)
        print("Atomicity and undo tests passed!")

        print("\nAll verification tests completed successfully!")

if __name__ == '__main__':
    asyncio.run(run_tests())
