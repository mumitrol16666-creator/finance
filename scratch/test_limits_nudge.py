import asyncio
import sys
import os
from datetime import datetime as real_datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

sys.stdout.reconfigure(encoding='utf-8')
sys.path.append('C:\\FinanceBot')
os.environ['DB_PATH'] = 'C:/FinanceBot/data/bot.db'

from app.scheduler.notify_scheduler import tick_notify
from app.handlers.common import nudge_limits_enough

# Define mock current time: UTC 2026-05-30 07:00:05 (Local 12:00:05 in Asia/Aqtobe UTC+5)
mock_now = real_datetime(2026, 5, 30, 7, 0, 5, tzinfo=timezone.utc)

class MockDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return mock_now.astimezone(tz)
        return mock_now

    @classmethod
    def fromisoformat(cls, date_string):
        return real_datetime.fromisoformat(date_string)

    @classmethod
    def strptime(cls, date_string, format_string):
        return real_datetime.strptime(date_string, format_string)

async def run_test():
    import sqlite3
    conn = sqlite3.connect('C:/FinanceBot/data/bot.db')
    cur = conn.cursor()

    # Clean up any leftover dummy user data
    cur.execute("DELETE FROM users WHERE user_id = 99999")
    cur.execute("DELETE FROM settings WHERE user_id = 99999")
    cur.execute("DELETE FROM categories WHERE user_id = 99999")
    cur.execute("DELETE FROM budgets WHERE user_id = 99999")
    conn.commit()

    # 1. Insert dummy user, settings, and categories
    cur.execute("INSERT INTO users (user_id, created_at) VALUES (99999, '2026-05-30T00:00:00')")
    cur.execute(
        """
        INSERT INTO settings (
            user_id, currency, timezone, lang, 
            nudge_enabled, nudge_interval_min, nudge_last_sent_at, 
            daily_report_enabled, daily_report_time, daily_report_last_sent_date, daily_report_pre_last_sent_date,
            debts_enabled, debts_days_before, 
            recurring_inc_enabled, recurring_inc_days, recurring_exp_enabled, recurring_exp_days,
            limits_nudge_last_sent_date, created_at, updated_at
        ) VALUES (
            99999, 'KZT', 'Asia/Aqtobe', 'ru', 
            1, 180, '2026-05-29T12:00:00', 
            0, '21:00', NULL, NULL,
            0, 3,
            0, 0, 0, 0,
            NULL, '2026-05-30T00:00:00', '2026-05-30T00:00:00'
        )
        """
    )
    # Active expense categories
    cur.execute("INSERT INTO categories (user_id, name, emoji, kind, is_archived, created_at, updated_at) VALUES (99999, 'Еда', '🍔', 'expense', 0, '2026-05-30T00:00:00', '2026-05-30T00:00:00')")
    cur.execute("INSERT INTO categories (user_id, name, emoji, kind, is_archived, created_at, updated_at) VALUES (99999, 'Транспорт', '🚗', 'expense', 0, '2026-05-30T00:00:00', '2026-05-30T00:00:00')")
    cur.execute("INSERT INTO categories (user_id, name, emoji, kind, is_archived, created_at, updated_at) VALUES (99999, 'Дом', '🏠', 'expense', 0, '2026-05-30T00:00:00', '2026-05-30T00:00:00')")
    conn.commit()

    # Get the generated category IDs
    cur.execute("SELECT id, name FROM categories WHERE user_id = 99999")
    cats = cur.fetchall()
    cat_map = {name: cid for cid, name in cats}
    print(f"Test categories created: {cat_map}")

    # Mock list_notify_targets to return ONLY our dummy user target tuple
    # Columns: user_id, currency, tz_name, lang, daily_enabled, hhmm, last_sent, pre_last_sent,
    #          nudge_enabled, nudge_interval_min, nudge_last_sent_at, debts_enabled, debts_days_before,
    #          inc_enabled, inc_days, exp_enabled, exp_days
    dummy_target = (
        99999,          # user_id
        'KZT',          # currency
        'Asia/Aqtobe',  # tz_name
        'ru',           # lang
        0,              # daily_enabled
        '21:00',        # hhmm
        None,           # last_sent
        None,           # pre_last_sent
        1,              # nudge_enabled
        180,            # nudge_interval_min
        '2026-05-29T12:00:00', # nudge_last_sent_at
        0,              # debts_enabled
        3,              # debts_days_before
        0,              # inc_enabled
        0,              # inc_days
        0,              # exp_enabled
        0,              # exp_days
    )

    # --- Scenario A: 0 limits set ---
    print("\n--- Running Scenario A: 0 limits set ---")
    mock_bot = AsyncMock()
    with patch('app.scheduler.notify_scheduler.datetime', MockDatetime), \
         patch('app.scheduler.notify_scheduler.list_notify_targets', AsyncMock(return_value=[dummy_target])):
        
        await tick_notify(mock_bot)

    print(f"Number of send_message calls: {len(mock_bot.send_message.call_args_list)}")
    if mock_bot.send_message.call_args_list:
        args, kwargs = mock_bot.send_message.call_args_list[0]
        print(f"Sent to: {args[0]}")
        print(f"Text:\n{args[1]}")
        print(f"Reply Markup Buttons:")
        for row in kwargs.get('reply_markup').inline_keyboard:
            for btn in row:
                print(f"  [{btn.text}] -> Callback: {btn.callback_data}")

    # Check that limits_nudge_last_sent_date was set in DB
    cur.execute("SELECT limits_nudge_last_sent_date FROM settings WHERE user_id = 99999")
    val_date = cur.fetchone()[0]
    print(f"After Scenario A, limits_nudge_last_sent_date in DB: {val_date}")
    
    # Reset last sent date and add partial limits
    cur.execute("UPDATE settings SET limits_nudge_last_sent_date = NULL WHERE user_id = 99999")
    conn.commit()

    # --- Scenario B: Partial limits set (Food 🍔 and Transport 🚗) ---
    print("\n--- Running Scenario B: Partial limits set ---")
    cur_month = "2026-05"
    cur.execute("INSERT INTO budgets (user_id, month, category_id, limit_amount, created_at, updated_at) VALUES (99999, ?, ?, 50000, '2026-05-30T00:00:00', '2026-05-30T00:00:00')", (cur_month, cat_map['Еда']))
    cur.execute("INSERT INTO budgets (user_id, month, category_id, limit_amount, created_at, updated_at) VALUES (99999, ?, ?, 20000, '2026-05-30T00:00:00', '2026-05-30T00:00:00')", (cur_month, cat_map['Транспорт']))
    conn.commit()

    mock_bot = AsyncMock()
    with patch('app.scheduler.notify_scheduler.datetime', MockDatetime), \
         patch('app.scheduler.notify_scheduler.list_notify_targets', AsyncMock(return_value=[dummy_target])):

        await tick_notify(mock_bot)

    print(f"Number of send_message calls: {len(mock_bot.send_message.call_args_list)}")
    if mock_bot.send_message.call_args_list:
        args, kwargs = mock_bot.send_message.call_args_list[0]
        print(f"Sent to: {args[0]}")
        print(f"Text:\n{args[1]}")
        print(f"Reply Markup Buttons:")
        for row in kwargs.get('reply_markup').inline_keyboard:
            for btn in row:
                print(f"  [{btn.text}] -> Callback: {btn.callback_data}")

    # Clean up test rows
    cur.execute("DELETE FROM users WHERE user_id = 99999")
    cur.execute("DELETE FROM settings WHERE user_id = 99999")
    cur.execute("DELETE FROM categories WHERE user_id = 99999")
    cur.execute("DELETE FROM budgets WHERE user_id = 99999")
    conn.commit()
    conn.close()
    print("\n--- Test finished and database cleaned ---")

if __name__ == '__main__':
    asyncio.run(run_test())
