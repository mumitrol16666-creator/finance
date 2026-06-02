import sqlite3
import asyncio
import aiosqlite

async def list_users():
    db = await aiosqlite.connect("data/bot.db")
    db.row_factory = aiosqlite.Row
    
    cur = await db.execute("SELECT * FROM users")
    rows = await cur.fetchall()
    
    for r in rows:
        print(f"ID: {r['user_id']} | Mode: {r['mode']} | Full: {r['full_access']} | Until: {r['full_access_until']} | Onboarded: {r['onboarded']}")
        
    await db.close()

if __name__ == "__main__":
    asyncio.run(list_users())
