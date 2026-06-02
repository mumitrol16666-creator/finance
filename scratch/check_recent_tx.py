import asyncio
import aiosqlite
import sys

async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    db = await aiosqlite.connect("data/bot.db")
    db.row_factory = aiosqlite.Row
    
    cur = await db.execute("SELECT COUNT(*) FROM transactions")
    (total_tx,) = await cur.fetchone()
    
    cur = await db.execute("SELECT MAX(ts) FROM transactions")
    (max_ts,) = await cur.fetchone()
    
    print(f"Total transactions: {total_tx}")
    print(f"Latest transaction timestamp: {max_ts}")
    
    # Let's count by user
    cur = await db.execute("SELECT user_id, COUNT(*) as cnt, MAX(ts) as max_t FROM transactions GROUP BY user_id")
    rows = await cur.fetchall()
    for r in rows:
        print(f"User {r['user_id']}: {r['cnt']} transactions, latest at {r['max_t']}")
        
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
