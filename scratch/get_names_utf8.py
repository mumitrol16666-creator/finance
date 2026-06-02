import sqlite3
import asyncio
import aiosqlite
import sys
from aiogram import Bot
from app.config.settings import settings

async def get_names():
    # Force utf-8 printing
    sys.stdout.reconfigure(encoding='utf-8')
    
    bot = Bot(token=settings.bot_token)
    db = await aiosqlite.connect("data/bot.db")
    db.row_factory = aiosqlite.Row
    
    cur = await db.execute("SELECT user_id, full_access, mode FROM users")
    rows = await cur.fetchall()
    
    for r in rows:
        uid = r['user_id']
        try:
            chat = await bot.get_chat(uid)
            name = chat.first_name or ""
            last = chat.last_name or ""
            full_name = f"{name} {last}".strip()
            username = chat.username or ""
            print(f"UID: {uid} | Name: {full_name} | Username: @{username} | Full: {r['full_access']} | Mode: {r['mode']}")
        except Exception as e:
            print(f"UID: {uid} | Error: {e}")
            
    await db.close()
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(get_names())
