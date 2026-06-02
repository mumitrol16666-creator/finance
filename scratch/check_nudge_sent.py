import asyncio
import aiosqlite
import sys

async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    db = await aiosqlite.connect("data/bot.db")
    db.row_factory = aiosqlite.Row
    
    cur = await db.execute("SELECT user_id, nudge_enabled, nudge_last_sent_at, updated_at FROM settings")
    rows = await cur.fetchall()
    
    print(f"{'user_id':<12} | {'nudge_en':<8} | {'nudge_last_sent_at':<25} | {'updated_at':<25}")
    print("-" * 80)
    for r in rows:
        print(f"{r['user_id']:<12} | {r['nudge_enabled']:<8} | {str(r['nudge_last_sent_at']):<25} | {str(r['updated_at']):<25}")
        
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
