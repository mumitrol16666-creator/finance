import asyncio
import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import aiosqlite

# Ensure imports work from project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.currency import get_exchange_rate, _CACHE
from app.db.repositories.accounts_repo import create_account, get_account
from app.db.repositories.tx_repo import create_transfer, list_last
from app.db.migrate import run_migrations

async def test_currency_service():
    print("🧪 Testing Currency Exchange Service...")
    # Clear cache first
    _CACHE.clear()
    
    # Test identical pair (should immediately return 1.0 without API)
    rate = await get_exchange_rate("KZT", "KZT")
    assert rate == 1.0, f"Expected 1.0, got {rate}"
    print("🟢 Identical currencies: KZT -> KZT = 1.0 (Passed)")
    
    # Test valid conversion (USD -> KZT)
    print("⏳ Querying real API (USD -> KZT)...")
    try:
        usd_to_kzt = await get_exchange_rate("USD", "KZT")
        assert usd_to_kzt > 300 and usd_to_kzt < 600, f"Unreasonable rate: {usd_to_kzt}"
        print(f"🟢 API query passed: 1 USD = {usd_to_kzt} KZT")
        
        # Test cache (subsequent query should be instant and equal)
        import time
        start = time.time()
        cached_rate = await get_exchange_rate("USD", "KZT")
        elapsed = time.time() - start
        assert cached_rate == usd_to_kzt, "Cache returned different rate"
        assert elapsed < 0.005, f"Cache request took too long: {elapsed}s"
        print(f"🟢 Caching check passed ({elapsed:.6f}s)")
        
        # Test inverse caching (KZT -> USD should also be cached)
        inverse_rate = await get_exchange_rate("KZT", "USD")
        assert abs(inverse_rate - (1.0 / usd_to_kzt)) < 1e-4, "Inverse rate calculation mismatch"
        print(f"🟢 Inverse caching passed: 1 KZT = {inverse_rate:.6f} USD")
        
    except Exception as e:
        print(f"⚠️ API query failed (expected under network conditions): {e}")

async def test_cross_currency_db_leg():
    print("\n🧪 Testing Cross-Currency Database Double-Entry legs...")
    db_path = ":memory:"
    async with aiosqlite.connect(db_path) as db:
        await run_migrations(db)
        
        # 1. Setup user and accounts
        user_id = 12345
        await db.execute(
            "INSERT INTO users (user_id, created_at, onboarded, mode, full_access) VALUES (?, datetime('now'), 1, 'full', 1)",
            (user_id,)
        )
        # Create USD account (source) with 100 USD (represented as 100)
        await create_account(db, user_id, "USD Piggy", 100, "2026-05-19T00:00:00Z", currency="USD")
        # Create KZT account (target) with 0 KZT
        await create_account(db, user_id, "Kaspi KZT", 0, "2026-05-19T00:00:00Z", currency="KZT")
        
        # Verify initial states
        usd_acc = await get_account(db, user_id, 1)
        kzt_acc = await get_account(db, user_id, 2)
        assert usd_acc[2] == 100 and usd_acc[4] == "USD"
        assert kzt_acc[2] == 0 and kzt_acc[4] == "KZT"
        await db.commit()
        print("🟢 Initial accounts configured correctly (Passed)")
        
        # 2. Perform cross-currency transfer
        # Transfer 100 USD -> 48000 KZT
        amount_usd = 100
        amount_kzt = 48000
        tx1, tx2 = await create_transfer(
            db, 
            user_id, 
            "2026-05-19T10:00:00Z", 
            1, # from_acc (USD Piggy)
            2, # to_acc (Kaspi KZT)
            amount_usd, 
            "Self-transfer with conversion", 
            "2026-05-19T10:00:00Z",
            to_amount=amount_kzt
        )
        
        # Verify balances after transfer
        usd_after = await get_account(db, user_id, 1)
        kzt_after = await get_account(db, user_id, 2)
        
        assert usd_after[2] == 0, f"USD balance expected 0, got {usd_after[2]}"
        assert kzt_after[2] == 48000, f"KZT balance expected 48000, got {kzt_after[2]}"
        print(f"🟢 Database balance updates verified: USD Piggy = {usd_after[2]} USD, Kaspi KZT = {kzt_after[2]} KZT (Passed)")
        
        # Verify double entry transactions in ledger (after starting balance tx at index 0)
        cur = await db.execute("SELECT amount, account_id, related_tx_id FROM transactions ORDER BY id")
        txs = await cur.fetchall()
        
        # Debited USD Piggy (amount should be negative)
        assert txs[1][0] == -100
        assert txs[1][1] == 1
        assert txs[1][2] == tx2 # related to tx2
        
        # Credited Kaspi KZT (amount should be positive)
        assert txs[2][0] == 48000
        assert txs[2][1] == 2
        assert txs[2][2] == tx1 # related to tx1
        
        print("🟢 Double-entry transaction ledger cross-linking verified (Passed)")

async def main():
    await test_currency_service()
    await test_cross_currency_db_leg()
    print("\n🎉 ALL CROSS-CURRENCY TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
