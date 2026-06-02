import asyncio
import aiosqlite
import sys
from datetime import datetime, timezone, timedelta
from loguru import logger
from unittest.mock import AsyncMock

sys.stdout.reconfigure(encoding='utf-8')

# Mock tick_notify logic with print statements
async def test_simulated_tick(user_id, hour, minute):
    # local time hour and minute
    # Let's say user has timezone Asia/Aqtobe (UTC+5)
    # So UTC time is (hour - 5)
    dt_utc = datetime(2026, 5, 28, hour - 5, minute, 0, tzinfo=timezone.utc)
    print(f"Simulating time: Local={hour:02d}:{minute:02d} (UTC={dt_utc})")
    
    # Let's import safe_tz, list_notify_targets, etc.
    from app.scheduler.notify_scheduler import _safe_tz, _parse_hhmm, _in_window, _build_daily_text
    from app.db.connection import get_db
    
    async with get_db() as db:
        cur = await db.execute("SELECT user_id, currency, timezone, daily_report_enabled, daily_report_time, daily_report_last_sent_date, daily_report_pre_last_sent_date FROM settings WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row:
            print("User not found")
            return
            
        uid, currency, tz_name, daily_enabled, hhmm, last_sent, pre_last_sent = row
        print(f"User {uid}: timezone={tz_name}, daily_enabled={daily_enabled}, daily_report_time={hhmm}")
        
        tz, tz_norm = _safe_tz(str(tz_name or "UTC"))
        local_now = dt_utc.astimezone(tz)
        print(f"  local_now: {local_now}")
        
        # Suppress check
        is_quiet = local_now.hour >= 22 or local_now.hour < 8
        print(f"  Is quiet hour? (local_now.hour >= 22 or < 8): {is_quiet}")
        
        if is_quiet:
            print("  -> SKIPPED (QUIET HOURS)")
            return
            
        local_date = local_now.date().isoformat()
        rep_h, rep_m = _parse_hhmm(str(hhmm or "21:00"))
        report_local = local_now.replace(hour=rep_h, minute=rep_m, second=0, microsecond=0)
        
        window = timedelta(seconds=70)
        in_win = _in_window(local_now, report_local, window)
        print(f"  report_local: {report_local}")
        print(f"  in window? {in_win}")
        
        if (last_sent or "") != local_date and in_win:
            print("  -> SENDING REPORT!")
        else:
            print("  -> NOT SENDING (already sent or not in window)")

async def main():
    import sys
    sys.path.append('C:\\FinanceBot')
    # Test for User 1097719119 (daily_report_time = 22:00)
    print("=== Testing user with report at 22:00 ===")
    await test_simulated_tick(1097719119, 22, 0)
    
    # Test for User 6856090314 (daily_report_time = 20:00)
    print("\n=== Testing user with report at 20:00 ===")
    await test_simulated_tick(6856090314, 20, 0)

if __name__ == '__main__':
    asyncio.run(main())
