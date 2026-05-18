import asyncio
import aiosqlite
from app.db.repositories.users_repo import grant_full_access

async def main():
    db = await aiosqlite.connect("app/data/bot.db")
    db.row_factory = aiosqlite.Row
    
    # Configure busy timeout to resolve locks dynamically
    await db.execute("PRAGMA busy_timeout = 10000")
    
    # Grant premium full_access to all users in the DB
    cur = await db.execute("SELECT user_id FROM users")
    rows = await cur.fetchall()
    
    for r in rows:
        user_id = r["user_id"]
        await grant_full_access(db, user_id, 365)
        print(f"Granted 365 days of Premium to User ID: {user_id}")
        
    # Safely clear the free trial counts if the table exists
    try:
        await db.execute("CREATE TABLE IF NOT EXISTS user_free_trial (user_id INTEGER PRIMARY KEY, premium_exports_used INTEGER NOT NULL DEFAULT 0)")
        await db.execute("DELETE FROM user_free_trial")
        await db.commit()
        print("Successfully reset all user free trials!")
    except Exception as e:
        print("Could not reset trials:", e)
        
    await db.commit()
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
