import sqlite3
import asyncio
import aiosqlite
from app.domain.services.access_service import get_menu_context, get_user_context
from app.domain.time_utils import today_in_user_tz

async def test():
    db = await aiosqlite.connect("data/bot.db")
    db.row_factory = aiosqlite.Row
    
    user_id = 6856090314
    
    variant, progress_level, _full_access, expiration_date = await get_menu_context(db, user_id)
    print("variant:", variant)
    print("progress_level:", progress_level)
    print("_full_access:", _full_access)
    print("expiration_date:", expiration_date)
    
    ctx = await get_user_context(db, user_id)
    print("ctx.mode:", ctx.mode)
    print("ctx.full_access:", ctx.full_access)
    print("ctx.expiration_date:", ctx.expiration_date)
    
    today = await today_in_user_tz(db, user_id)
    print("today in user tz:", today)
    
    if expiration_date:
        from datetime import date as _date
        exp = _date.fromisoformat(expiration_date)
        days_left = (exp - today).days
        print("days_left:", days_left)
        
    await db.close()

if __name__ == "__main__":
    asyncio.run(test())
