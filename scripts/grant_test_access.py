import asyncio
import aiosqlite
from app.db.repositories.users_repo import grant_full_access

async def main():
    db = await aiosqlite.connect('C:/FinanceBot/data/bot.db')
    await grant_full_access(db, 6856090314, days=4)
    await db.commit()
    await db.close()
    print('Access granted for 4 days')

if __name__ == '__main__':
    asyncio.run(main())
