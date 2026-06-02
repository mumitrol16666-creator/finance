import asyncio
import aiosqlite
from app.db.migrate import run_migrations
from app.db.repositories.users_repo import is_eligible_for_trial_3d, mark_trial_3d_claimed

async def test():
    # 1. Run migrations first to ensure database is migrated
    db_path = "finance_bot.db" # local test db
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        print("Running migrations...")
        await run_migrations(db)
        print("Migrations complete!")

        # Setup test table state for a dummy user (user_id = 999999)
        await db.execute("DELETE FROM users WHERE user_id = 999999")
        await db.execute(
            """
            INSERT INTO users (user_id, created_at, onboarded, current_streak, max_streak, full_access_until) 
            VALUES (999999, '2026-05-28T00:00:00Z', 1, 0, 0, NULL)
            """
        )
        await db.commit()

        # Helper to set user fields
        async def update_user(streak=0, max_streak=0, full_access_until=None, trial_claimed=0):
            await db.execute(
                """
                UPDATE users 
                SET current_streak = ?, max_streak = ?, full_access_until = ?, trial_3d_claimed = ?
                WHERE user_id = 999999
                """,
                (streak, max_streak, full_access_until, trial_claimed)
            )
            await db.commit()

        # Case 1: new user, 0 streak, no premium -> False
        await update_user(streak=0, max_streak=0)
        res = await is_eligible_for_trial_3d(db, 999999)
        print(f"Test 1 (streak=0): expected=False, actual={res}")

        # Case 2: streak = 5, no premium -> True
        await update_user(streak=5, max_streak=5)
        res = await is_eligible_for_trial_3d(db, 999999)
        print(f"Test 2 (streak=5): expected=True, actual={res}")

        # Case 3: streak = 5, but full_access_until is not NULL (previously had trial/premium) -> False
        await update_user(streak=5, max_streak=5, full_access_until='2026-05-28')
        res = await is_eligible_for_trial_3d(db, 999999)
        print(f"Test 3 (premium was active): expected=False, actual={res}")

        # Case 4: streak = 2, max_streak = 6, no premium -> True (generous check based on max streak)
        await update_user(streak=2, max_streak=6, full_access_until=None)
        res = await is_eligible_for_trial_3d(db, 999999)
        print(f"Test 4 (max_streak=6): expected=True, actual={res}")

        # Case 5: streak = 5, trial claimed -> False
        await update_user(streak=5, max_streak=5, trial_claimed=1)
        res = await is_eligible_for_trial_3d(db, 999999)
        print(f"Test 5 (trial claimed): expected=False, actual={res}")

        # Case 6: claim trial
        await update_user(streak=5, max_streak=5, trial_claimed=0)
        await mark_trial_3d_claimed(db, 999999)
        res = await is_eligible_for_trial_3d(db, 999999)
        print(f"Test 6 (claimed now): expected=False, actual={res}")

        # Clean up
        await db.execute("DELETE FROM users WHERE user_id = 999999")
        await db.commit()

if __name__ == "__main__":
    asyncio.run(test())
