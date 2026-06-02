import asyncio
import os
import sys
import tempfile
import aiosqlite

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.repositories.budgets_repo import upsert_budget, month_budgets_map, month_spent_map
from app.scheduler.daily_report import _build_weekly_progress_bar

async def init_test_db(db_path):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                emoji TEXT,
                kind TEXT,
                is_archived INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                account_id INTEGER,
                category_id INTEGER,
                type TEXT,
                note TEXT,
                ts TEXT,
                tier TEXT,
                deleted_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                user_id INTEGER,
                month TEXT,
                category_id INTEGER,
                limit_amount INTEGER,
                created_at TEXT,
                updated_at TEXT,
                PRIMARY KEY (user_id, month, category_id)
            )
        """)
        await db.commit()

async def test_weekly_progress_bar(db_path):
    print("--- Testing Weekly Progress Bar ---")
    async with aiosqlite.connect(db_path) as db:
        user_id = 999
        # Tuesday of 2026-05-26
        # Let's add some transactions
        # Monday (25th): tracked
        # Tuesday (26th): tracked
        # Wednesday (27th): future/not yet tracked (if today is 26th)
        await db.execute("DELETE FROM transactions WHERE user_id=?", (user_id,))
        await db.execute(
            "INSERT INTO transactions (user_id, amount, account_id, category_id, type, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, -1000, 1, 1, 'expense', '2026-05-25T12:00:00+00:00')
        )
        await db.execute(
            "INSERT INTO transactions (user_id, amount, account_id, category_id, type, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, -2000, 1, 1, 'expense', '2026-05-26T14:00:00+00:00')
        )
        await db.commit()

        # Build progress bar with today as Tuesday 2026-05-26
        bar_ru = await _build_weekly_progress_bar(db, user_id, "Asia/Aqtobe", "2026-05-26", "ru")
        bar_en = await _build_weekly_progress_bar(db, user_id, "Asia/Aqtobe", "2026-05-26", "en")
        
        print("RU:", bar_ru)
        print("EN:", bar_en)
        
        assert "🔥|🔥|⬜|⬜|⬜|⬜|⬜" in bar_ru, "Failed progress bar items check"
        assert "(2 из 7 дней заполнено)" in bar_ru, "Failed count check RU"
        assert "(2 of 7 days tracked)" in bar_en, "Failed count check EN"
        print("✅ Progress bar checks passed!")

async def test_budget_reallocation(db_path):
    print("--- Testing Budget Reallocation Logic ---")
    async with aiosqlite.connect(db_path) as db:
        user_id = 999
        month = "2026-05"
        
        # Clear tables
        await db.execute("DELETE FROM budgets WHERE user_id=?", (user_id,))
        await db.execute("DELETE FROM transactions WHERE user_id=?", (user_id,))
        await db.execute("DELETE FROM categories WHERE user_id=?", (user_id,))
        
        # Insert categories
        await db.execute("INSERT INTO categories (id, user_id, name, emoji, kind) VALUES (1, ?, 'Еда', '🍔', 'expense')", (user_id,))
        await db.execute("INSERT INTO categories (id, user_id, name, emoji, kind) VALUES (2, ?, 'Транспорт', '🚕', 'expense')", (user_id,))
        
        # Insert limits (budget): Category 1 (Food) budget=5000, Category 2 (Transport) budget=3000
        await upsert_budget(db, user_id, month, 1, 5000)
        await upsert_budget(db, user_id, month, 2, 3000)
        
        # Spent: Category 1 (Food) spent 6500 (overrun = 1500)
        await db.execute(
            "INSERT INTO transactions (user_id, amount, account_id, category_id, type, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, -6500, 1, 1, 'expense', '2026-05-15T12:00:00+00:00')
        )
        # Spent: Category 2 (Transport) spent 1000 (surplus = 2000)
        await db.execute(
            "INSERT INTO transactions (user_id, amount, account_id, category_id, type, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, -1000, 1, 2, 'expense', '2026-05-16T12:00:00+00:00')
        )
        await db.commit()

        # Let's perform calculation like in the budget reallocator
        budgets = await month_budgets_map(db, user_id, month)
        spent = await month_spent_map(db, user_id, month)
        
        print("Budgets Map:", budgets)
        print("Spent Map:", spent)
        
        overruns = {cid: (spent.get(cid, 0) - lim) for cid, lim in budgets.items() if spent.get(cid, 0) > lim}
        surpluses = {cid: (lim - spent.get(cid, 0)) for cid, lim in budgets.items() if lim > spent.get(cid, 0)}
        
        print("Overruns:", overruns)
        print("Surpluses:", surpluses)
        
        assert len(overruns) > 0, "No overrun calculated"
        assert len(surpluses) > 0, "No surplus calculated"
        
        cat_to_id = max(overruns, key=overruns.get)
        overrun = overruns[cat_to_id]
        
        cat_from_id = max(surpluses, key=surpluses.get)
        surplus = surpluses[cat_from_id]
        
        transfer_amount = min(overrun, surplus)
        print(f"Transfer suggestion: Move {transfer_amount} from Category {cat_from_id} to Category {cat_to_id}")
        
        assert cat_to_id == 1, "Expected Food (1) to be overrun target"
        assert cat_from_id == 2, "Expected Transport (2) to be surplus source"
        assert transfer_amount == 1500, f"Expected transfer amount to be 1500 (min of 1500 overrun and 2000 surplus), got {transfer_amount}"
        
        # Apply transfer
        new_lim_from = max(0, budgets[cat_from_id] - transfer_amount)
        new_lim_to = budgets[cat_to_id] + transfer_amount
        
        await upsert_budget(db, user_id, month, cat_from_id, new_lim_from)
        await upsert_budget(db, user_id, month, cat_to_id, new_lim_to)
        await db.commit()
        
        updated_budgets = await month_budgets_map(db, user_id, month)
        print("Updated Budgets:", updated_budgets)
        
        assert updated_budgets[1] == 6500, "Food budget did not increase to 6500"
        assert updated_budgets[2] == 1500, "Transport budget did not decrease to 1500"
        print("✅ Budget reallocation checks passed!")

async def main():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    try:
        await init_test_db(db_path)
        await test_weekly_progress_bar(db_path)
        await test_budget_reallocation(db_path)
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

if __name__ == "__main__":
    asyncio.run(main())
