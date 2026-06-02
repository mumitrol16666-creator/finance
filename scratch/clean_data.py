import asyncio
import aiosqlite

async def main():
    db_path = './data/bot.db'
    user_id = 8092822438

    print(f"Connecting to database: {db_path}")
    async with aiosqlite.connect(db_path) as db:
        # Revoke Premium
        await db.execute("UPDATE users SET full_access=0 WHERE user_id=?", (user_id,))
        print("Revoked premium access.")
        
        # Delete fake transactions
        fake_notes = [
            'Зарплата первая часть',
            'Зарплата вторая часть',
            'Аренда квартиры',
            'Покупка одежды',
            'Подписки на сервисы',
            'Супермаркет и продукты',
            'Поездки на такси',
            'Кафе и кино'
        ]
        placeholders = ', '.join(['?'] * len(fake_notes))
        query = f"DELETE FROM transactions WHERE user_id=? AND note IN ({placeholders})"
        cur = await db.execute(query, [user_id] + fake_notes)
        print(f"Deleted {cur.rowcount} fake transactions.")

        # Delete recurring payments to clear ghost payments
        cur = await db.execute("DELETE FROM recurring_expenses WHERE user_id=?", (user_id,))
        print(f"Deleted {cur.rowcount} recurring expenses.")
        cur = await db.execute("DELETE FROM recurring_incomes WHERE user_id=?", (user_id,))
        print(f"Deleted {cur.rowcount} recurring incomes.")

        await db.commit()
        print("Done cleaning!")

if __name__ == "__main__":
    asyncio.run(main())
