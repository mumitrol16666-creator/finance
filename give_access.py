import asyncio
import aiosqlite
from app.db.repositories.users_repo import grant_full_access

async def main():
    try:
        async with aiosqlite.connect("data/bot.db") as db:
            await grant_full_access(db, 6856090314, days=1) # 1 day
            await db.commit()
        print("✅ Полный доступ успешно выдан пользователю 6856090314!")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
