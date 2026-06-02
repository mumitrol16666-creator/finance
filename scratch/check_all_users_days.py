import sqlite3
import asyncio
import aiosqlite
from app.domain.services.access_service import get_menu_context
from app.domain.time_utils import today_in_user_tz

async def check_all():
    db = await aiosqlite.connect("data/bot.db")
    db.row_factory = aiosqlite.Row
    
    cur = await db.execute("SELECT user_id FROM users")
    rows = await cur.fetchall()
    
    for r in rows:
        uid = r['user_id']
        variant, progress_level, _full_access, expiration_date = await get_menu_context(db, uid)
        today = await today_in_user_tz(db, uid)
        days_left = None
        if expiration_date:
            from datetime import date as _date
            try:
                exp = _date.fromisoformat(expiration_date)
                days_left = (exp - today).days
            except Exception:
                pass
        print(f"UID: {uid} | variant: {variant} | full: {_full_access} | exp: {expiration_date} | days_left: {days_left}")
        
    await db.close()

if __name__ == "__main__":
    asyncio.run(check_all())
