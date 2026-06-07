import asyncio
import os
import sys

os.environ["DB_PATH"] = r"c:\FinanceBot\data\bot.db"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.connection import get_db
from app.handlers.settings_categories_limits import _build_category_rows

async def main():
    user_id = 6856090314  # Admin ID or common test ID
    async with get_db() as db:
        try:
            print("Testing _build_category_rows for expense:")
            cats, month, rows = await _build_category_rows(db, user_id, "ru", kind="expense")
            print(f"Success! Found {len(cats)} categories. Rows:")
            for r in rows:
                print(r)
            
            print("\nTesting _build_category_rows for income:")
            cats_inc, month_inc, rows_inc = await _build_category_rows(db, user_id, "ru", kind="income")
            print(f"Success! Found {len(cats_inc)} categories. Rows:")
            for r in rows_inc:
                print(r)
        except Exception as e:
            print(f"FAILED with error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
