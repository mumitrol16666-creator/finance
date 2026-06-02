import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent.resolve()))

import asyncio
import aiosqlite
from datetime import datetime, timedelta, timezone
from app.config.settings import settings
from app.db.repositories.users_repo import grant_full_access

async def main():
    db_path = settings.db_path
    user_id = 8092822438
    
    print(f"Connecting to database: {db_path}")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        
        # Check if user exists
        cur = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        exists = await cur.fetchone()
        if not exists:
            print(f"Error: User {user_id} not found in the users table! Please start the bot or log in as this user first.")
            return
            
        # 1. Grant premium access for 60 days
        print("Granting Full Access for 60 days...")
        await grant_full_access(db, user_id, days=60)
        
        # 2. Get accounts for user
        cur = await db.execute("SELECT id FROM accounts WHERE user_id = ?", (user_id,))
        accounts = [row[0] for row in await cur.fetchall()]
        if not accounts:
            print("Error: No accounts found for the user. Cannot associate transactions.")
            return
            
        # Use first available account or Kaspi Pay if named so
        cur = await db.execute("SELECT id FROM accounts WHERE user_id = ? AND name LIKE '%Kaspi%'", (user_id,))
        kaspi_row = await cur.fetchone()
        main_account = kaspi_row[0] if kaspi_row else accounts[0]
        other_account = accounts[1] if len(accounts) > 1 else main_account
        
        # 3. Clean up existing transactions for this user
        print("Deleting existing transactions...")
        await db.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
        
        # 4. Generate mock transactions for the past 30 days
        print("Generating mock transaction sequence...")
        base_date = datetime.now(timezone.utc)
        
        transactions = []
        
        # Income (total 400,000):
        # Day -28: 250,000
        date_inc1 = (base_date - timedelta(days=28)).isoformat()
        transactions.append((user_id, date_inc1, "income", 250000, main_account, 396, "Зарплата первая часть", date_inc1))
        
        # Day -14: 150,000
        date_inc2 = (base_date - timedelta(days=14)).isoformat()
        transactions.append((user_id, date_inc2, "income", 150000, main_account, 396, "Зарплата вторая часть", date_inc2))
        
        # Expenses (total 400,000):
        # Day -29: Rent - 120,000
        date_rent = (base_date - timedelta(days=29)).isoformat()
        transactions.append((user_id, date_rent, "expense", -120000, other_account, 389, "Аренда квартиры", date_rent))
        
        # Day -25: Clothes - 30,000
        date_clothes = (base_date - timedelta(days=25)).isoformat()
        transactions.append((user_id, date_clothes, "expense", -30000, main_account, 393, "Покупка одежды", date_clothes))
        
        # Day -20: Subscriptions - 10,000
        date_subs = (base_date - timedelta(days=20)).isoformat()
        transactions.append((user_id, date_subs, "expense", -10000, main_account, 390, "Подписки на сервисы", date_subs))
        
        # Daily Food (30 days): 6,000 each day (30 * 6,000 = 180,000)
        for i in range(30):
            day_offset = 30 - i
            tx_time = (base_date - timedelta(days=day_offset, hours=2)).isoformat()
            transactions.append((user_id, tx_time, "expense", -6000, main_account, 387, "Супермаркет и продукты", tx_time))
            
        # Daily Transport (15 transactions): 2,000 each (15 * 2,000 = 30,000)
        for i in range(15):
            day_offset = 30 - (i * 2)
            tx_time = (base_date - timedelta(days=day_offset, hours=4)).isoformat()
            transactions.append((user_id, tx_time, "expense", -2000, main_account, 388, "Поездки на такси", tx_time))
            
        # Weekends Entertainment (4 weekends): 7,500 each (4 * 7,500 = 30,000)
        for i in range(4):
            day_offset = 27 - (i * 7)
            tx_time = (base_date - timedelta(days=day_offset, hours=6)).isoformat()
            transactions.append((user_id, tx_time, "expense", -7500, main_account, 391, "Кафе и кино", tx_time))
            
        # Insert
        await db.executemany(
            """
            INSERT INTO transactions (user_id, ts, type, amount, account_id, category_id, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            transactions
        )
        print(f"Inserted {len(transactions)} mock transactions.")
        
        # Commit
        await db.commit()
        print("Done! Database successfully populated.")

if __name__ == "__main__":
    asyncio.run(main())
