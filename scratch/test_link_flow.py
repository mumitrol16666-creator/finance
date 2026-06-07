import asyncio
import os
import sys

os.environ["DB_PATH"] = r"c:\FinanceBot\data\bot.db"

# Add parent directory to path so we can import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.connection import get_db
from app.domain.auth import hash_password, verify_password

async def main():
    username = "app_user_test_link"
    password = "MySecurePassword123!"
    hashed = hash_password(password)
    
    print(f"Hashed password: {hashed}")
    verified = verify_password(password, hashed)
    print(f"Verified locally: {verified}")
    
    async with get_db() as db:
        # Clean up if exists
        await db.execute("DELETE FROM users WHERE username = ?", (username,))
        await db.commit()
        
        # 1. Register through app logic
        cur = await db.execute(
            "INSERT INTO users (username, password_hash, display_name, onboarding_state, created_at, onboarded) "
            "VALUES (?, ?, ?, 'completed', '2026-06-06T00:00:00', 1)",
            (username, hashed, "App User",)
        )
        app_user_id = cur.lastrowid
        await db.commit()
        print(f"Registered user in DB with ID: {app_user_id}")
        
        # 2. Simulate Telegram linking
        # Telegram user enters password
        entered_password = password
        
        cur_link = await db.execute("SELECT id, password_hash FROM users WHERE LOWER(username) = ?", (username,))
        row = await cur_link.fetchone()
        if not row:
            print("User not found!")
            return
            
        found_id, db_hash = row[0], row[1]
        print(f"Found user in DB: ID={found_id}, Hash={db_hash}")
        
        match = verify_password(entered_password, db_hash)
        print(f"Password verified against DB hash: {match}")

if __name__ == '__main__':
    asyncio.run(main())
