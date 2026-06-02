import asyncio
import os
import sys
import tempfile
import aiosqlite

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

async def setup_test_db(db_path):
    async with aiosqlite.connect(db_path) as db:
        # Create a simplified set of tables to simulate our schema
        await db.execute("CREATE TABLE users (user_id INTEGER PRIMARY KEY, created_at TEXT)")
        await db.execute("CREATE TABLE settings (user_id INTEGER PRIMARY KEY, lang TEXT)")
        await db.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, name TEXT, balance INTEGER)")
        await db.execute("CREATE TABLE debts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, title TEXT)")
        await db.execute("CREATE TABLE debt_notify_log (id INTEGER PRIMARY KEY AUTOINCREMENT, debt_id INTEGER, info TEXT)")
        await db.execute("CREATE TABLE transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER)")
        await db.commit()

async def populate_mock_user(db_path, user_id):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT INTO users VALUES (?, '2026-05-31')", (user_id,))
        await db.execute("INSERT INTO settings VALUES (?, 'ru')", (user_id,))
        await db.execute("INSERT INTO accounts (user_id, name, balance) VALUES (?, 'Kaspi', 50000)", (user_id,))
        
        # Debt and notification log
        await db.execute("INSERT INTO debts (id, user_id, title) VALUES (10, ?, 'Rent')", (user_id,))
        await db.execute("INSERT INTO debt_notify_log (debt_id, info) VALUES (10, 'reminded_once')")
        
        await db.execute("INSERT INTO transactions (user_id, amount) VALUES (?, 1000)", (user_id,))
        await db.commit()

async def simulate_deletion(db, target_id):
    tables_with_user_id = [
        "users", "settings", "accounts", "debts", "transactions"
    ]
    
    # 1. Delete dependent rows (debt_notify_log linked to debts)
    await db.execute(
        "DELETE FROM debt_notify_log WHERE debt_id IN (SELECT id FROM debts WHERE user_id = ?)",
        (target_id,)
    )
    
    # 2. Delete from all tables containing user_id
    for table in tables_with_user_id:
        await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (target_id,))
    await db.commit()

async def test_admin_delete():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
        
    try:
        await setup_test_db(db_path)
        user_id = 999
        await populate_mock_user(db_path, user_id)
        
        # Verify data is populated
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM users WHERE user_id=?", (user_id,))
            assert (await cur.fetchone())[0] == 1
            
            cur = await db.execute("SELECT COUNT(*) FROM debt_notify_log")
            assert (await cur.fetchone())[0] == 1
            
            # Execute deletion
            await simulate_deletion(db, user_id)
            
            # Verify clean up
            cur = await db.execute("SELECT COUNT(*) FROM users WHERE user_id=?", (user_id,))
            assert (await cur.fetchone())[0] == 0
            
            cur = await db.execute("SELECT COUNT(*) FROM settings WHERE user_id=?", (user_id,))
            assert (await cur.fetchone())[0] == 0
            
            cur = await db.execute("SELECT COUNT(*) FROM accounts WHERE user_id=?", (user_id,))
            assert (await cur.fetchone())[0] == 0
            
            cur = await db.execute("SELECT COUNT(*) FROM debts WHERE user_id=?", (user_id,))
            assert (await cur.fetchone())[0] == 0
            
            cur = await db.execute("SELECT COUNT(*) FROM debt_notify_log")
            assert (await cur.fetchone())[0] == 0
            
            cur = await db.execute("SELECT COUNT(*) FROM transactions WHERE user_id=?", (user_id,))
            assert (await cur.fetchone())[0] == 0
            
            print("✅ User deletion test passed successfully!")
            
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

if __name__ == "__main__":
    asyncio.run(test_admin_delete())
