import asyncio
import sys
import os
import io
import aiosqlite
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Ensure imports work from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Monkeypatch the background AI analysis worker before imports to prevent database file conflicts
import app.domain.services.ai_event_worker
async def dummy_trigger(user_id):
    pass
app.domain.services.ai_event_worker.trigger_background_ai_analysis = dummy_trigger

from app.db.migrate import run_migrations
from app.db.repositories.accounts_repo import create_account
from app.db.repositories.tx_repo import create_tx
from app.domain.services.financial_analysis_engine import calculate_financial_metrics

async def main():
    print("🧪 Running transaction tiering and financial metrics integration test...")
    db_path = ":memory:"
    async with aiosqlite.connect(db_path) as db:
        await run_migrations(db)
        
        # 1. Setup user and settings (base currency KZT)
        user_id = 99999
        await db.execute(
            "INSERT INTO users (user_id, created_at, onboarded, mode, full_access) VALUES (?, datetime('now'), 1, 'full', 1)",
            (user_id,)
        )
        await db.execute(
            "INSERT INTO settings (user_id, currency, timezone, daily_report_enabled, created_at, updated_at) VALUES (?, 'KZT', 'Asia/Almaty', 1, datetime('now'), datetime('now'))",
            (user_id,)
        )
        
        # 2. Create accounts:
        # Kaspi KZT (Liquid): 30,000 KZT
        await create_account(db, user_id, "Kaspi KZT", 30000, "2026-05-21T00:00:00Z", currency="KZT", is_saving=0)
        # Halyk USD (Liquid): 100.00 USD (which is 10000 cents). Let's assume rate USD->KZT = 471.68, so 47,168 KZT.
        await create_account(db, user_id, "Halyk USD", 10000, "2026-05-21T00:00:00Z", currency="USD", is_saving=0)
        # Saving account: 50,000 KZT
        await create_account(db, user_id, "Kaspi Deposit", 50000, "2026-05-21T00:00:00Z", currency="KZT", is_saving=1)
        
        # Total Liquid: 30,000 (Kaspi KZT) + 47,168 (Halyk USD converted) = 77,168 KZT (approx)
        # Total Savings: 50,000 KZT
        # Total overall balance: 127,168 KZT
        
        await db.commit()
        
        # 3. Create transactions in the past to calculate CDBR:
        # We need routine, obligation, anomaly expenses.
        # Use a timestamp 1 hour ago so it's in the past relative to execution time.
        ts_now = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        
        # Routine: 10 transactions of 1,500 KZT = 15,000 KZT total. CDBR should be 15,000 / 30 = 500 KZT/day
        for i in range(10):
            await create_tx(db, user_id, ts_now, "expense", -1500, 1, None, f"Groceries {i}", ts_now, tier="routine")
            
        # Obligation: 1 transaction of 30,000 KZT (Rent) = 30,000 KZT total. Avg obligation per day = 30,000 / 30 = 1,000 KZT/day
        await create_tx(db, user_id, ts_now, "expense", -30000, 1, None, "Rent", ts_now, tier="obligation")
        
        # Anomaly: 1 transaction of 60,000 KZT (Laptop/phone replacement) = 60,000 KZT total
        await create_tx(db, user_id, ts_now, "expense", -60000, 1, None, "Laptop repair", ts_now, tier="anomaly")
        
        await db.commit()
        
        # 4. Calculate metrics
        metrics = await calculate_financial_metrics(db, user_id, "Asia/Almaty")
        
        print("\n--- TEST METRICS OUTPUT ---")
        import pprint
        pprint.pprint(metrics)
        
        # Assertions:
        # Check CDBR (routine expenses only):
        cdbr = metrics["cdbr"]
        assert cdbr["cdbr"] == 500, f"Expected CDBR = 500, got {cdbr['cdbr']}"
        assert cdbr["routine_total"] == 15000
        assert cdbr["obligation_total"] == 30000
        assert cdbr["anomaly_total"] == 60000
        
        # Check converted balances:
        balances = metrics["balances"]
        assert balances["base_currency"] == "KZT"
        
        # Check that operational runway excludes savings
        # Daily burn total = CDBR + obligation_daily = 500 + 1000 = 1500 KZT/day.
        # Liquid balance = Kaspi KZT (30000) + Halyk USD (100 USD * 471.68 = 47168 KZT) = 77168 KZT
        # Runway operational days = 77168 / 1500 = 51 days
        # Full balance = Liquid (77168) + Savings (50000) = 127168 KZT
        # Runway full days = 127168 / 1500 = 84 days
        
        runway_op = metrics["runway_operational"]
        runway_full = metrics["runway_full"]
        
        print("Operational Runway days:", runway_op["runway_operational_days"])
        print("Full Runway days:", runway_full["runway_full_days"])
        
        assert runway_op["runway_operational_days"] == 51, f"Expected 51, got {runway_op['runway_operational_days']}"
        assert runway_full["runway_full_days"] == 84, f"Expected 84, got {runway_full['runway_full_days']}"
        
        print("\n🟢 All transaction tiering & metrics logic is 100% CORRECT!")

if __name__ == "__main__":
    asyncio.run(main())
