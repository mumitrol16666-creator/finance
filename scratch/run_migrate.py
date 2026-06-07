import asyncio
from app.db.migrate import run_migrations
from app.db.connection import get_db

async def main():
    async with get_db() as db:
        await run_migrations(db)
    print("Done migrating!")

if __name__ == "__main__":
    asyncio.run(main())
