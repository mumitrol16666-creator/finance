import asyncio
import sys
from app.db.connection import open_db


async def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "bot.db"
    db = await open_db(db_path)
    await db.close()
    print(f"OK: migrations applied to {db_path}")


if __name__ == "__main__":
    asyncio.run(main())
