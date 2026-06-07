import asyncio
import os
import sys

# Add parent directory to path so we can import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.connection import get_db

async def main():
    async with get_db() as db:
        # Show table description
        cur = await db.execute("PRAGMA table_info(users)")
        cols = await cur.fetchall()
        print("Columns in users:")
        for col in cols:
            print(f" - {col[1]} ({col[2]})")
            
        print("\nSome user records (up to 10):")
        cur = await db.execute("SELECT id, telegram_id, username, password_hash, display_name, onboarding_state FROM users LIMIT 10")
        rows = await cur.fetchall()
        for row in rows:
            print(f" ID: {row[0]} | TG: {row[1]} | Username: {row[2]} | PassHash: {row[3]} | Name: {row[4]} | State: {row[5]}")

if __name__ == '__main__':
    asyncio.run(main())
