import asyncio
from app.db.connection import get_db
from app.db.migrate import run_migrations

async def main():
    async with get_db() as db:
        await run_migrations(db)
    print("Migrations completed successfully!")

if __name__ == "__main__":
    asyncio.run(main())
