import asyncio
import aiosqlite

async def check():
    db = await aiosqlite.connect("data/bot.db")
    async with db.execute("SELECT id, name, emoji, kind FROM categories LIMIT 20") as cur:
        cats = await cur.fetchall()
        print("Raw categories in database:")
        for c in cats:
            hex_val = c[1].encode('utf-8').hex() if c[1] else ""
            emoji_hex = c[2].encode('utf-8').hex() if c[2] else ""
            # Safely encode name to ascii ignoring non-ascii
            name_ascii = c[1].encode('ascii', 'ignore').decode('ascii') if c[1] else ""
            print(f"ID: {c[0]}, Name hex: {hex_val}, Emoji hex: {emoji_hex}, Kind: {c[3]}")
    await db.close()

asyncio.run(check())
