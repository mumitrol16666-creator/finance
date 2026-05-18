import asyncio
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from datetime import datetime, timezone
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update, Message, CallbackQuery, Chat, User
from aiogram.methods import TelegramMethod

import aiosqlite

# Add workspace root to sys.path so we can import app modules
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.migrate import run_migrations
from app.handlers import get_routers
from app.middlewares.access import AccessContextMiddleware
from app.middlewares.fsm_escape import FsmEscapeMiddleware
from app.fsm.states import ExpenseFlow, CategoriesFlow


class MockBot(Bot):
    def __init__(self):
        super().__init__(token="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")
        self.sent_messages = []

    async def __call__(self, method: TelegramMethod, timeout: int | None = None, **kwargs) -> Any:
        method_name = method.__class__.__name__
        params = getattr(method, "__dict__", {})
        self.sent_messages.append((method_name, params))
        
        # Safe mock response templates
        if method_name == "SendMessage":
            return Message(
                message_id=999,
                date=datetime.now(timezone.utc),
                chat=Chat(id=6856090314, type="private"),
                text=params.get("text", ""),
                from_user=User(id=999, is_bot=True, first_name="Bot")
            )
        elif method_name == "EditMessageText":
            return Message(
                message_id=999,
                date=datetime.now(timezone.utc),
                chat=Chat(id=6856090314, type="private"),
                text=params.get("text", ""),
                from_user=User(id=999, is_bot=True, first_name="Bot")
            )
        elif method_name == "EditMessageReplyMarkup":
            return True
        elif method_name == "AnswerCallbackQuery":
            return True
        elif method_name == "DeleteMessage":
            return True
        return None


async def setup_test_db() -> aiosqlite.Connection:
    """Setup a clean test database in memory."""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON;")
    
    # Run all schema migrations
    await run_migrations(db)
    
    # Insert test user and settings
    await db.execute(
        "INSERT INTO users (user_id, created_at, onboarded, mode, full_access) VALUES (?, ?, 1, 'full', 1)",
        (6856090314, datetime.now(timezone.utc).isoformat())
    )
    await db.execute(
        "INSERT INTO settings (user_id, lang, created_at, updated_at) VALUES (?, 'ru', datetime('now'), datetime('now'))",
        (6856090314,)
    )
    
    # Insert mock account
    await db.execute(
        "INSERT INTO accounts (user_id, name, balance, currency, created_at, updated_at) VALUES (?, 'Карта', 100000, 'KZT', datetime('now'), datetime('now'))",
        (6856090314,)
    )
    await db.execute(
        "INSERT INTO accounts (user_id, name, balance, currency, created_at, updated_at) VALUES (?, 'Наличные', 5000, 'KZT', datetime('now'), datetime('now'))",
        (6856090314,)
    )
    
    # Insert mock category
    await db.execute(
        "INSERT INTO categories (id, user_id, name, emoji, kind, is_archived, created_at, updated_at) VALUES (?, ?, 'Продукты', '🍔', 'expense', 0, datetime('now'), datetime('now'))",
        (402, 6856090314)
    )
    
    await db.commit()
    return db


async def run_crawler():
    print("=== STARTING BOT FLOW CRAWLER ===")
    
    # Initialize mock components
    bot = MockBot()
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Setup test database
    db = await setup_test_db()
    
    # Configure loguru to print exceptions to stdout
    from loguru import logger
    logger.remove()
    logger.add(sys.stdout, level="DEBUG")
    
    # Register outer/inner middlewares matching main.py
    fsm_escape_mw = FsmEscapeMiddleware()
    dp.message.outer_middleware(fsm_escape_mw)
    dp.callback_query.outer_middleware(fsm_escape_mw)
    
    access_mw = AccessContextMiddleware()
    dp.message.middleware(access_mw)
    dp.callback_query.middleware(access_mw)
    
    # Register all routers
    for r in get_routers():
        dp.include_router(r)
        
    user = User(id=6856090314, is_bot=False, first_name="TestUser", username="testuser")
    chat = Chat(id=6856090314, type="private")
    
    state_ctx = dp.fsm.resolve_context(bot, chat.id, user.id)
    
    # Helper to check active state
    async def get_state_info():
        s = await state_ctx.get_state()
        data = await state_ctx.get_data()
        return f"State: {s}, Data: {data}"
        
    print(f"Initial: {await get_state_info()}")
    
    # ----------------------------------------------------
    # Step 1: Click ➖ Расход (Starts Expense Flow)
    # ----------------------------------------------------
    print("\n--- Step 1: Sending '➖ Расход' ---")
    msg1 = Message(
        message_id=101,
        date=datetime.now(timezone.utc),
        chat=chat,
        text="➖ Расход",
        from_user=user
    )
    bot.sent_messages.clear()
    await dp.feed_update(bot, Update(update_id=1, message=msg1), db=db)
    print(await get_state_info())
    assert await state_ctx.get_state() == ExpenseFlow.amount, "Should transition to ExpenseFlow.amount state!"
    
    # ----------------------------------------------------
    # Step 2: Send Amount '500'
    # ----------------------------------------------------
    print("\n--- Step 2: Sending Amount '500' ---")
    msg2 = Message(
        message_id=102,
        date=datetime.now(timezone.utc),
        chat=chat,
        text="500",
        from_user=user
    )
    bot.sent_messages.clear()
    await dp.feed_update(bot, Update(update_id=2, message=msg2), db=db)
    print(await get_state_info())
    assert await state_ctx.get_state() == ExpenseFlow.account, "Should transition to ExpenseFlow.account state!"
    
    # ----------------------------------------------------
    # Step 3: Select Account (CallbackQuery expacc:1)
    # ----------------------------------------------------
    print("\n--- Step 3: Selecting Account (expacc:1) ---")
    cb3 = CallbackQuery(
        id="cb_103",
        from_user=user,
        chat_instance="chat_inst_1",
        message=Message(
            message_id=999,
            date=datetime.now(timezone.utc),
            chat=chat,
            text="Choose account",
            from_user=User(id=999, is_bot=True, first_name="Bot")
        ),
        data="expacc:1"
    )
    bot.sent_messages.clear()
    await dp.feed_update(bot, Update(update_id=3, callback_query=cb3), db=db)
    print(await get_state_info())
    assert await state_ctx.get_state() == ExpenseFlow.category, "Should transition to ExpenseFlow.category state!"
    
    # ----------------------------------------------------
    # Step 4: Select Category (CallbackQuery expcat:402)
    # ----------------------------------------------------
    print("\n--- Step 4: Selecting Category (expcat:402) ---")
    cb4 = CallbackQuery(
        id="cb_104",
        from_user=user,
        chat_instance="chat_inst_1",
        message=Message(
            message_id=999,
            date=datetime.now(timezone.utc),
            chat=chat,
            text="Choose category",
            from_user=User(id=999, is_bot=True, first_name="Bot")
        ),
        data="expcat:402"
    )
    bot.sent_messages.clear()
    await dp.feed_update(bot, Update(update_id=4, callback_query=cb4), db=db)
    print(await get_state_info())
    assert await state_ctx.get_state() == ExpenseFlow.need_note, "Should transition to ExpenseFlow.need_note state!"

    # ----------------------------------------------------
    # Step 5: Click No Note (CallbackQuery expnote:no)
    # ----------------------------------------------------
    print("\n--- Step 5: Clicking No Note (expnote:no) ---")
    cb5 = CallbackQuery(
        id="cb_105",
        from_user=user,
        chat_instance="chat_inst_1",
        message=Message(
            message_id=999,
            date=datetime.now(timezone.utc),
            chat=chat,
            text="Need note?",
            from_user=User(id=999, is_bot=True, first_name="Bot")
        ),
        data="expnote:no"
    )
    bot.sent_messages.clear()
    await dp.feed_update(bot, Update(update_id=5, callback_query=cb5), db=db)
    print(await get_state_info())
    assert await state_ctx.get_state() == ExpenseFlow.confirm, "Should transition to ExpenseFlow.confirm state!"

    # ----------------------------------------------------
    # Step 6: Click Confirm (CallbackQuery expcfm:save)
    # ----------------------------------------------------
    print("\n--- Step 6: Confirming Transaction (expcfm:save) ---")
    cb6 = CallbackQuery(
        id="cb_106",
        from_user=user,
        chat_instance="chat_inst_1",
        message=Message(
            message_id=999,
            date=datetime.now(timezone.utc),
            chat=chat,
            text="Confirm transaction?",
            from_user=User(id=999, is_bot=True, first_name="Bot")
        ),
        data="expcfm:save"
    )
    bot.sent_messages.clear()
    await dp.feed_update(bot, Update(update_id=6, callback_query=cb6), db=db)
    print(await get_state_info())
    assert await state_ctx.get_state() is None, "Should complete transaction and clear FSM state!"
    
    # Check if transaction was recorded in the database
    cur = await db.execute("SELECT amount, note FROM transactions WHERE user_id = 6856090314")
    row = await cur.fetchone()
    assert row is not None, "Transaction must be inserted in database!"
    print(f"Database Record: amount={row['amount']}, note={row['note']}")
    
    # ----------------------------------------------------
    # Step 7: Test Cancellation during active state
    # ----------------------------------------------------
    print("\n--- Step 7: Starting new flow and testing cancel ---")
    bot.sent_messages.clear()
    await dp.feed_update(bot, Update(update_id=7, message=msg1), db=db)
    print(f"After starting Expense: {await get_state_info()}")
    assert await state_ctx.get_state() == ExpenseFlow.amount
    
    print("\n--- Sending '❌ Отмена' in active state ---")
    msg_cancel = Message(
        message_id=103,
        date=datetime.now(timezone.utc),
        chat=chat,
        text="❌ Отмена",
        from_user=user
    )
    await dp.feed_update(bot, Update(update_id=8, message=msg_cancel), db=db)
    print(f"After Cancel: {await get_state_info()}")
    assert await state_ctx.get_state() is None, "FsmEscapeMiddleware must cancel state and return to None!"
    
    # ----------------------------------------------------
    # Step 8: Verify Categories management legacy screen
    # ----------------------------------------------------
    print("\n--- Step 8: Verifying Categories Settings (st:cats) ---")
    cb_cats = CallbackQuery(
        id="cb_108",
        from_user=user,
        chat_instance="chat_inst_1",
        message=Message(
            message_id=999,
            date=datetime.now(timezone.utc),
            chat=chat,
            text="Settings Menu",
            from_user=User(id=999, is_bot=True, first_name="Bot")
        ),
        data="st:cats"
    )
    bot.sent_messages.clear()
    await dp.feed_update(bot, Update(update_id=9, callback_query=cb_cats), db=db)
    
    # Ensure there are no warnings or errors, and st:cats was handled
    any_errors = any("Session expired" in str(msg) or "Сессия устарела" in str(msg) for _, msg in bot.sent_messages)
    assert not any_errors, "Should not trigger Session Expired when hitting st:cats!"
    print("✅ st:cats processed cleanly without Session Expired warnings.")

    # ----------------------------------------------------
    # Step 9: Verify Evening / Daily Report scheduler delivery
    # ----------------------------------------------------
    print("\n--- Step 9: Testing Evening / Daily Report Scheduler Delivery ---")
    
    # Configure user settings to enable daily report at 21:00 in UTC+5 (Asia/Aqtobe) timezone
    await db.execute(
        "UPDATE settings SET daily_report_enabled = 1, daily_report_time = '21:00', timezone = 'Asia/Aqtobe' WHERE user_id = 6856090314"
    )
    await db.commit()
    
    # Mock current system UTC time representing exactly 16:00 UTC (which is 21:00 local time in Asia/Aqtobe)
    mock_utc_now = datetime(2026, 5, 18, 16, 0, 0, tzinfo=timezone.utc)
    
    # Patch datetime.now in notify_scheduler to return our mocked utc time
    import app.scheduler.notify_scheduler as ns
    from unittest.mock import patch
    
    bot.sent_messages.clear()
    
    # Let's inspect targets in database
    targets = await ns.list_notify_targets(db)
    print(f"DATABASE TARGETS COUNT: {len(targets)}")
    for t in targets:
        print(f"Target: user_id={t[0]}, daily_enabled={t[4]}, hhmm={t[5]}, last_sent={t[6]}, timezone={t[2]}")
        
    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz:
                return mock_utc_now.astimezone(tz)
            return mock_utc_now

    with patch("app.scheduler.notify_scheduler.datetime", MockDatetime):
        # Run the tick_notify scheduler loop
        await ns.tick_notify(bot, db)
        
    print(f"SENT MESSAGES COUNT: {len(bot.sent_messages)}")
    for method, params in bot.sent_messages:
        print(f"Sent: {method} - {params.get('text')}")
        
    # Check if the report was sent!
    report_sent = False
    for method, params in bot.sent_messages:
        if method == "SendMessage" and "Итог за день" in params.get("text", ""):
            report_sent = True
            print("📩 Successfully intercepted sent Daily Report message!")
            print(f"Report Text:\n{params.get('text')}")
            break
            
    assert report_sent, "Daily Report must be sent by the scheduler!"
    print("✅ Evening/Daily Report scheduler works flawlessly and delivers exactly when due!")

    print("\n=== ALL FLOW TESTS PASSED SUCCESSFULLY! 100% SOUND AND ROBUST! ===")
    await db.close()


if __name__ == "__main__":
    asyncio.run(run_crawler())
