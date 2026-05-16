import sqlite3
import asyncio
import aiosqlite
import os

DB_PATH = r'c:\FinanceBot\data\bot.db'

async def check_db():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: DB not found at {DB_PATH}")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        print("--- Table: settings ---")
        async with db.execute("PRAGMA table_info(settings)") as cursor:
            columns = await cursor.fetchall()
            if not columns:
                print("Table 'settings' NOT FOUND!")
            for col in columns:
                print(f"Column: {col['name']} ({col['type']})")
        
        print("\n--- Sample Notification Settings ---")
        try:
            async with db.execute("SELECT user_id, recurring_inc_enabled, recurring_inc_days, recurring_exp_enabled, recurring_exp_days, debts_enabled, debts_days_before FROM settings LIMIT 3") as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    print(dict(row))
        except Exception as e:
            print(f"Error reading settings: {e}")

        print("\n--- Table: recurring_expenses (due check) ---")
        try:
            async with db.execute("SELECT id, title, next_run_date FROM recurring_expenses LIMIT 3") as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    print(dict(row))
        except Exception as e:
            print(f"Error reading recurring_expenses: {e}")

        print("\n--- Table: debts (due check) ---")
        try:
            async with db.execute("SELECT id, title, next_payment_date FROM debts WHERE is_active=1 LIMIT 3") as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    print(dict(row))
        except Exception as e:
            print(f"Error reading debts: {e}")

if __name__ == "__main__":
    asyncio.run(check_db())
