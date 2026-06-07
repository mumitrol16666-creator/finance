import asyncio
import os
import sys

# Add parent directory to path so we can import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config.settings import settings
from app.db.connection import get_db
from app.db.migrate import run_migrations

async def main():
    print(f"Database path from settings: {settings.db_path}")
    print("Running migrations...")
    try:
        async with get_db() as db:
            await run_migrations(db)
            print("Migrations complete!")
            
            # Print the migrations that have been applied
            cur = await db.execute("SELECT id, applied_at FROM migrations ORDER BY applied_at")
            rows = await cur.fetchall()
            print("\nApplied migrations:")
            for row in rows:
                print(f" - {row[0]} (applied at {row[1]})")
                
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
