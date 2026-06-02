import asyncio
from app.db.connection import get_db
from app.db.migrate import run_migrations

async def run():
    async with get_db() as db:
        await run_migrations(db)

if __name__ == "__main__":
    asyncio.run(run())
