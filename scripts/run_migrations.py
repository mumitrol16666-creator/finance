import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.connection import get_db
from app.db.migrate import run_migrations


async def main() -> None:
    async with get_db() as db:
        await run_migrations(db)


if __name__ == "__main__":
    asyncio.run(main())
