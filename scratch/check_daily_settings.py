import asyncio
import aiosqlite
import sys

async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    db = await aiosqlite.connect("data/bot.db")
    db.row_factory = aiosqlite.Row
    
    cur = await db.execute("SELECT * FROM settings")
    rows = await cur.fetchall()
    
    print(f"{'user_id':<12} | {'lang':<4} | {'timezone':<15} | {'daily_en':<8} | {'time':<5} | {'last_sent':<10} | {'pre_last':<10}")
    print("-" * 80)
    for r in rows:
        print(f"{r['user_id']:<12} | {r['lang']:<4} | {r['timezone']:<15} | {r['daily_report_enabled']:<8} | {r['daily_report_time']:<5} | {str(r['daily_report_last_sent_date']):<10} | {str(r['daily_report_pre_last_sent_date']):<10}")
        
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
