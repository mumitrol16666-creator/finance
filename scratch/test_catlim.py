import asyncio
import os
import sys

os.environ["DB_PATH"] = r"c:\FinanceBot\data\bot.db"
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.connection import get_db
from app.db.repositories.categories_repo import list_categories
from app.db.repositories.budgets_repo import month_limits_status_map, month_spent_map, month_key

async def main():
    user_id = 6856090314  # Admin ID or common test ID
    async with get_db() as db:
        try:
            print("1. Testing list_categories('expense'):")
            cats = await list_categories(db, user_id, "expense")
            print(f"Success! Found {len(cats)} expense categories.")
            
            print("2. Testing list_categories('income'):")
            cats_inc = await list_categories(db, user_id, "income")
            print(f"Success! Found {len(cats_inc)} income categories.")
            
            print("3. Testing month_spent_map:")
            m_key = month_key()
            s_map = await month_spent_map(db, user_id, m_key)
            print(f"Success! Spent map: {s_map}")
            
            print("4. Testing month_limits_status_map:")
            l_map = await month_limits_status_map(db, user_id, m_key)
            print(f"Success! Limits status map: {l_map}")
            
            print("All DB functions executed successfully without errors!")
        except Exception as e:
            print(f"FAILED with error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
