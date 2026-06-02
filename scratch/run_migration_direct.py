import asyncio
from app.config.settings import settings
from app.db.migrate import run_migrations
from app.db.connection import open_db

async def main():
    db = await open_db(settings.db_path)
    await run_migrations(db)
    await db.close()
    print("Migrations run successfully!")

asyncio.run(main())
