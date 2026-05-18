import asyncio
import aiosqlite

async def check():
    db = await aiosqlite.connect("data/bot.db")
    async with db.execute("SELECT user_id, lang, currency, timezone FROM settings") as cur:
        rows = await cur.fetchall()
        print("Settings Table:")
        for r in rows:
            print(f"User ID: {r[0]}, Lang: {r[1]}, Currency: {r[2]}, Timezone: {r[3]}")
            
    if rows:
        async with db.execute("SELECT id, name, emoji, kind FROM categories WHERE user_id = ?", (rows[0][0],)) as cur:
            cats = await cur.fetchall()
            print("\nCategories for first user:")
            for c in cats:
                print(f"ID: {c[0]}, Name: {c[1]}, Emoji: {c[2]}, Kind: {c[3]}")
    await db.close()

asyncio.run(check())
