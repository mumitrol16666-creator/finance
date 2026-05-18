import asyncio
import aiosqlite
from app.db.migrate import run_migrations

async def main():
    db = await aiosqlite.connect("C:/FinanceBot/data/bot.db")
    await run_migrations(db)
    
    # Check settings columns now
    cur = await db.execute("PRAGMA table_info(settings)")
    print("UPDATED DB SETTINGS COLUMNS:")
    for row in await cur.fetchall():
        print(row[1])
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
