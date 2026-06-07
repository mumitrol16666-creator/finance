import asyncio
import aiosqlite

async def main():
    async with aiosqlite.connect("C:/FinanceBot/data/bot.db") as db:
        db.row_factory = aiosqlite.Row
        lines = []
        lines.append("--- ACCOUNTS ---")
        cur = await db.execute("SELECT id, user_id, name, balance, is_archived, currency, is_saving FROM accounts")
        accounts = await cur.fetchall()
        for acc in accounts:
            lines.append(repr(dict(acc)))
            
        lines.append("\n--- LAST TRANSACTIONS ---")
        cur = await db.execute("SELECT id, user_id, ts, type, amount, account_id, related_tx_id, note FROM transactions ORDER BY id DESC LIMIT 25")
        txs = await cur.fetchall()
        for tx in txs:
            lines.append(repr(dict(tx)))
            
        with open("scratch/db_dump.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print("Success! Written to scratch/db_dump.txt")

if __name__ == "__main__":
    asyncio.run(main())
