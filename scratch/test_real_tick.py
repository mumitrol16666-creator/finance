import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

sys.path.append('C:\\FinanceBot')

# Set env var DB_PATH to make sure it loads the right database
os.environ['DB_PATH'] = 'C:/FinanceBot/data/bot.db'

from app.scheduler.notify_scheduler import tick_notify

async def run_test():
    # User 6856090314 has timezone Asia/Aqtobe (UTC+5), report time 20:00.
    # At 20:00:05 Asia/Aqtobe, the UTC time is 15:00:05 UTC.
    # We mock datetime.now to return 15:00:05 UTC.
    mock_now = datetime(2026, 5, 28, 15, 0, 5, tzinfo=timezone.utc)
    
    # We need to temporarily clear daily_report_last_sent_date for User 6856090314 in the DB,
    # so that the scheduler actually tries to send the report today (otherwise it might say already sent if we don't clear it).
    import sqlite3
    conn = sqlite3.connect('C:/FinanceBot/data/bot.db')
    cur = conn.cursor()
    cur.execute("UPDATE settings SET daily_report_last_sent_date = NULL WHERE user_id = 6856090314")
    conn.commit()
    conn.close()

    mock_bot = AsyncMock()

    print("Running tick_notify with mocked time...")
    with patch('app.scheduler.notify_scheduler.datetime') as mock_datetime:
        # datetime.now(timezone.utc) should return mock_now
        # datetime.fromisoformat should work normally
        mock_datetime.now.side_effect = lambda tz=None: mock_now.astimezone(tz) if tz else mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat
        mock_datetime.strptime = datetime.strptime
        
        try:
            await tick_notify(mock_bot)
            print("tick_notify finished.")
        except Exception as e:
            print(f"Exception raised in tick_notify: {e}")
            import traceback
            traceback.print_exc()
            return

    # Check what calls were made to mock_bot.send_message
    print(f"Number of send_message calls: {len(mock_bot.send_message.call_args_list)}")
    for i, call in enumerate(mock_bot.send_message.call_args_list):
        args, kwargs = call
        uid = args[0]
        text = args[1]
        print(f"\nCall {i+1} to User {uid}:")
        print(f"kwargs: {kwargs}")
        print(f"Text content:\n{text}\n")

if __name__ == '__main__':
    asyncio.run(run_test())
