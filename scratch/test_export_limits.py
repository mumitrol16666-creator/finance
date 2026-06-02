import asyncio
import os
import sys
import tempfile
import aiosqlite
from datetime import datetime, timezone

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

async def init_db(db_path):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS export_logs (
                user_id INTEGER,
                exported_at TEXT
            )
        """)
        await db.commit()

async def simulate_export_check(db, user_id):
    now = datetime.now(timezone.utc)
    month_start = f"{now.year:04d}-{now.month:02d}-01T00:00:00+00:00"
    if now.month == 12:
        month_end = f"{now.year + 1:04d}-01-01T00:00:00+00:00"
    else:
        month_end = f"{now.year:04d}-{now.month + 1:02d}-01T00:00:00+00:00"

    cur_limit = await db.execute(
        "SELECT COUNT(*) FROM export_logs WHERE user_id=? AND exported_at >= ? AND exported_at < ?",
        (user_id, month_start, month_end)
    )
    (export_count,) = await cur_limit.fetchone()

    MAX_MONTHLY_EXPORTS = 20
    if export_count >= MAX_MONTHLY_EXPORTS:
        return False, f"Blocked: {export_count} exports used"
    
    # Simulate logging the export
    await db.execute("INSERT INTO export_logs (user_id, exported_at) VALUES (?, ?)", (user_id, now.isoformat()))
    await db.commit()
    return True, "Allowed"

async def test_limits():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    
    try:
        await init_db(db_path)
        
        async with aiosqlite.connect(db_path) as db:
            user_id = 123
            
            # Export 1 to 20 should succeed
            for i in range(20):
                allowed, msg = await simulate_export_check(db, user_id)
                assert allowed, f"Export {i+1} should have been allowed"
            
            # 21st export should be blocked
            allowed, msg = await simulate_export_check(db, user_id)
            assert not allowed, "21st export should be blocked"
            print("Block Message:", msg)
            assert "Blocked" in msg, "Failed to block 21st export"
            
            print("✅ Export limits test passed successfully!")
            
    finally:
        if os.path.exists(db_path):
            os.remove(db_path)

if __name__ == "__main__":
    asyncio.run(test_limits())
