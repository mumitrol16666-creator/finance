import sqlite3
import asyncio
import aiosqlite
from app.domain.services.access_service import get_user_context, get_available_features_from_context

async def check_user_access():
    db = await aiosqlite.connect("data/bot.db")
    db.row_factory = aiosqlite.Row
    
    uid = 8092822438
    ctx = await get_user_context(db, uid)
    features = get_available_features_from_context(ctx)
    
    print(f"UID: {uid}")
    print(f"ctx.mode: {ctx.mode}")
    print(f"ctx.full_access: {ctx.full_access}")
    print(f"ctx.expiration_date: {ctx.expiration_date}")
    print(f"ctx.progress_level: {ctx.progress_level}")
    print(f"Features: {features}")
    print(f"Is 'reports' in features: {'reports' in features}")
    
    await db.close()

if __name__ == "__main__":
    asyncio.run(check_user_access())
