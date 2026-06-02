import asyncio
import aiosqlite
import sys

async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        db = await aiosqlite.connect("app/data/bot.db")
        db.row_factory = aiosqlite.Row
        
        cur = await db.execute("SELECT user_id, nudge_enabled, nudge_last_sent_at, daily_report_enabled, daily_report_last_sent_date, updated_at FROM settings")
        rows = await cur.fetchall()
        
        print(f"{'user_id':<12} | {'nudge_en':<8} | {'nudge_last':<22} | {'daily_en':<8} | {'daily_last':<10} | {'updated_at':<25}")
        print("-" * 95)
        for r in rows:
            print(f"{r['user_id']:<12} | {r['nudge_enabled']:<8} | {str(r['nudge_last_sent_at'])[:22]:<22} | {r['daily_report_enabled']:<8} | {str(r['daily_report_last_sent_date']):<10} | {str(r['updated_at'])[:25]:<25}")
            
        await db.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
