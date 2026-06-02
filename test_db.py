import asyncio
import os
import sys

# add parent directory to path so we can import app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.repositories.categories_repo import create_category
from app.db.connection import get_db

async def main():
    try:
        async with get_db() as db:
            print("Connected to DB successfully")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    asyncio.run(main())
