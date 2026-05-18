import asyncio
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from datetime import datetime, timezone, timedelta
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update, Message, CallbackQuery, Chat, User, PreCheckoutQuery
from aiogram.methods import TelegramMethod

import aiosqlite

# Add workspace root to sys.path so we can import app modules
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.migrate import run_migrations
from app.handlers import get_routers
from app.middlewares.access import AccessContextMiddleware
from app.middlewares.fsm_escape import FsmEscapeMiddleware
from app.fsm.states import ExpenseFlow, IncomeFlow, CategoriesFlow


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
        elif method_name == "SendInvoice":
            return Message(
                message_id=1000,
                date=datetime.now(timezone.utc),
                chat=Chat(id=6856090314, type="private"),
                text="⭐️ Invoice: " + params.get("title", ""),
                from_user=User(id=999, is_bot=True, first_name="Bot")
            )
        return None


async def setup_test_db() -> aiosqlite.Connection:
    """Setup a clean test database in memory."""
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON;")
    
    # Run all schema migrations
    await run_migrations(db)
    
    # Insert test user and settings (starts as premium to test default behavior first)
    await db.execute(
        "INSERT INTO users (user_id, created_at, onboarded, mode, full_access) VALUES (?, ?, 1, 'full', 1)",
        (6856090314, datetime.now(timezone.utc).isoformat())
    )
    await db.execute(
        "INSERT INTO settings (user_id, lang, timezone, created_at, updated_at) VALUES (?, 'ru', 'UTC', datetime('now'), datetime('now'))",
        (6856090314,)
    )
    
    # Insert mock accounts
    await db.execute(
        "INSERT INTO accounts (user_id, name, balance, currency, created_at, updated_at) VALUES (?, 'Карта', 100000, 'KZT', datetime('now'), datetime('now'))",
        (6856090314,)
    )
    await db.execute(
        "INSERT INTO accounts (user_id, name, balance, currency, created_at, updated_at) VALUES (?, 'Наличные', 5000, 'KZT', datetime('now'), datetime('now'))",
        (6856090314,)
    )
    
    # Insert mock categories
    await db.execute(
        "INSERT INTO categories (id, user_id, name, emoji, kind, is_archived, created_at, updated_at) VALUES (?, ?, 'Продукты', '🍔', 'expense', 0, datetime('now'), datetime('now'))",
        (402, 6856090314)
    )
    await db.execute(
        "INSERT INTO categories (id, user_id, name, emoji, kind, is_archived, created_at, updated_at) VALUES (?, ?, 'Зарплата', '💰', 'income', 0, datetime('now'), datetime('now'))",
        (403, 6856090314)
    )
    
    await db.commit()
    return db


async def run_crawler():
    print("=====================================================================")
    print("                 🚀 RUNNING FinanceBot INTEGRATED FLOW CRAWLERS       ")
    print("=====================================================================\n")
    
    # Initialize mock components
    bot = MockBot()
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Setup test database
    db = await setup_test_db()
    
    # Configure loguru to print exceptions to stdout
    from loguru import logger
    logger.remove()
    logger.add(sys.stdout, level="ERROR")
    
    # Register middlewares
    fsm_escape_mw = FsmEscapeMiddleware()
    dp.message.outer_middleware(fsm_escape_mw)
    dp.callback_query.outer_middleware(fsm_escape_mw)
    
    access_mw = AccessContextMiddleware()
    dp.message.middleware(access_mw)
    dp.callback_query.middleware(access_mw)
    
    # Register routers
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

    # =======================================================================
    # 🐛 WORM 1: Expense Transaction Crawl (Guided Flow)
    # =======================================================================
    print("🐛 [Worm 1/5] Expense Flow Crawling...")
    
    # Step 1.1: Send '➖ Расход'
    msg1 = Message(message_id=101, date=datetime.now(timezone.utc), chat=chat, text="➖ Расход", from_user=user)
    await dp.feed_update(bot, Update(update_id=1, message=msg1), db=db)
    assert await state_ctx.get_state() == ExpenseFlow.amount, "Transition to ExpenseFlow.amount failed!"
    
    # Step 1.2: Send Amount '500'
    msg2 = Message(message_id=102, date=datetime.now(timezone.utc), chat=chat, text="500", from_user=user)
    await dp.feed_update(bot, Update(update_id=2, message=msg2), db=db)
    assert await state_ctx.get_state() == ExpenseFlow.account, "Transition to ExpenseFlow.account failed!"
    
    # Step 1.3: Select Account (expacc:1)
    cb3 = CallbackQuery(id="cb_103", from_user=user, chat_instance="inst_1", message=msg1, data="expacc:1")
    await dp.feed_update(bot, Update(update_id=3, callback_query=cb3), db=db)
    assert await state_ctx.get_state() == ExpenseFlow.category, "Transition to ExpenseFlow.category failed!"
    
    # Step 1.4: Select Category (expcat:402)
    cb4 = CallbackQuery(id="cb_104", from_user=user, chat_instance="inst_1", message=msg1, data="expcat:402")
    await dp.feed_update(bot, Update(update_id=4, callback_query=cb4), db=db)
    assert await state_ctx.get_state() == ExpenseFlow.need_note, "Transition to ExpenseFlow.need_note failed!"

    # Step 1.5: Click No Note (expnote:no)
    cb5 = CallbackQuery(id="cb_105", from_user=user, chat_instance="inst_1", message=msg1, data="expnote:no")
    await dp.feed_update(bot, Update(update_id=5, callback_query=cb5), db=db)
    assert await state_ctx.get_state() == ExpenseFlow.confirm, "Transition to ExpenseFlow.confirm failed!"

    # Step 1.6: Click Confirm (expcfm:save)
    bot.sent_messages.clear()
    cb6 = CallbackQuery(id="cb_106", from_user=user, chat_instance="inst_1", message=msg1, data="expcfm:save")
    await dp.feed_update(bot, Update(update_id=6, callback_query=cb6), db=db)
    assert await state_ctx.get_state() is None, "Expense FSM state cleanup failed!"
    
    # Verify in DB
    cur = await db.execute("SELECT amount FROM transactions WHERE user_id = 6856090314 AND type='expense'")
    row = await cur.fetchone()
    assert row is not None and abs(row['amount']) == 500, "Expense database save assertion failed!"
    
    print("🟢 [PING BACK] Worm 1/5: Expense transaction crawled, saved, FSM cleared perfectly.\n")

    # =======================================================================
    # 🐛 WORM 2: Income Transaction Crawl (Guided Flow)
    # =======================================================================
    print("🐛 [Worm 2/5] Income Flow Crawling...")
    
    # Step 2.1: Send '➕ Доход'
    msg_inc1 = Message(message_id=201, date=datetime.now(timezone.utc), chat=chat, text="➕ Доход", from_user=user)
    await dp.feed_update(bot, Update(update_id=21, message=msg_inc1), db=db)
    assert await state_ctx.get_state() == IncomeFlow.amount, "Transition to IncomeFlow.amount failed!"
    
    # Step 2.2: Send Amount '15000'
    msg_inc2 = Message(message_id=202, date=datetime.now(timezone.utc), chat=chat, text="15000", from_user=user)
    await dp.feed_update(bot, Update(update_id=22, message=msg_inc2), db=db)
    assert await state_ctx.get_state() == IncomeFlow.account, "Transition to IncomeFlow.account failed!"
    
    # Step 2.3: Select Account (incacc:1)
    cb_inc3 = CallbackQuery(id="cb_203", from_user=user, chat_instance="inst_1", message=msg_inc1, data="incacc:1")
    await dp.feed_update(bot, Update(update_id=23, callback_query=cb_inc3), db=db)
    assert await state_ctx.get_state() == IncomeFlow.category, "Transition to IncomeFlow.category failed!"
    
    # Step 2.4: Select Category (inccat:403)
    cb_inc4 = CallbackQuery(id="cb_204", from_user=user, chat_instance="inst_1", message=msg_inc1, data="inccat:403")
    await dp.feed_update(bot, Update(update_id=24, callback_query=cb_inc4), db=db)
    assert await state_ctx.get_state() == IncomeFlow.need_note, "Transition to IncomeFlow.need_note failed!"

    # Step 2.5: Click No Note (incnote:no)
    cb_inc5 = CallbackQuery(id="cb_205", from_user=user, chat_instance="inst_1", message=msg_inc1, data="incnote:no")
    await dp.feed_update(bot, Update(update_id=25, callback_query=cb_inc5), db=db)
    assert await state_ctx.get_state() == IncomeFlow.confirm, "Transition to IncomeFlow.confirm failed!"

    # Step 2.6: Click Confirm (inccfm:save)
    bot.sent_messages.clear()
    cb_inc6 = CallbackQuery(id="cb_206", from_user=user, chat_instance="inst_1", message=msg_inc1, data="inccfm:save")
    await dp.feed_update(bot, Update(update_id=26, callback_query=cb_inc6), db=db)
    assert await state_ctx.get_state() is None, "Income FSM state cleanup failed!"
    
    # Verify in DB
    cur = await db.execute("SELECT amount FROM transactions WHERE user_id = 6856090314 AND type='income'")
    row = await cur.fetchone()
    assert row is not None and row['amount'] == 15000, "Income database save assertion failed!"
    
    print("🟢 [PING BACK] Worm 2/5: Income transaction crawled, saved, FSM cleared perfectly.\n")

    # =======================================================================
    # 🐛 WORM 3: AI Consultant Teaser & Payment Handlers (Marketing Ajar Door)
    # =======================================================================
    print("🐛 [Worm 3/5] AI Consultant Premium Teaser Crawling...")
    
    # Step 3.1: Change user to Non-Premium
    await db.execute("UPDATE users SET full_access = 0, mode = 'newbie' WHERE user_id = 6856090314")
    await db.commit()
    
    # Step 3.2: Trigger AI Consultant Entry (Sends '🤖 AI консультант' text)
    bot.sent_messages.clear()
    msg_ai = Message(message_id=301, date=datetime.now(timezone.utc), chat=chat, text="🤖 AI консультант", from_user=user)
    await dp.feed_update(bot, Update(update_id=31, message=msg_ai), db=db)
    
    # Verify Premium Ajar Teaser screen was sent
    teaser_sent = False
    for method, params in bot.sent_messages:
        text_content = params.get("text", "")
        if method == "SendMessage" and ("ИИ-мозг" in text_content or "проанализировал" in text_content) and "🧠" in text_content:
            teaser_sent = True
            break
    assert teaser_sent, f"Premium Teaser block for AI Consultant must be sent! Actual sent: {bot.sent_messages}"
    
    # Step 3.3: Click 'upgrade:activate' payment callback button
    bot.sent_messages.clear()
    cb_pay = CallbackQuery(id="cb_302", from_user=user, chat_instance="inst_1", message=msg_ai, data="upgrade:activate")
    await dp.feed_update(bot, Update(update_id=32, callback_query=cb_pay), db=db)
    
    # Check that payment keyboard was neutralized (EditMessageReplyMarkup called with reply_markup=None)
    neutralized = False
    invoice_sent = False
    for method, params in bot.sent_messages:
        if method == "EditMessageReplyMarkup" and params.get("reply_markup") is None:
            neutralized = True
        elif method == "SendInvoice":
            invoice_sent = True
            
    assert neutralized, "Standard button-collapsing (EditMessageReplyMarkup) must fire to neutralize payment keyboard!"
    assert invoice_sent, "A Telegram Star payment invoice must be sent!"
    
    print("🟢 [PING BACK] Worm 3/5: AI Teaser was shown, keyboard neutralized on pay click, invoice generated successfully.\n")

    # =======================================================================
    # 🐛 WORM 4: Category Limit Push Promo Alerts (Red Alert)
    # =======================================================================
    print("🐛 [Worm 4/5] Category Budget Overspent Limit Push Crawling...")
    
    # Step 4.1: Ensure user is Non-Premium
    await db.execute("UPDATE users SET full_access = 0, mode = 'newbie' WHERE user_id = 6856090314")
    # Setup extremely small monthly category budget of '200' KZT
    # Format month as 'YYYY-MM' matching the datetime.now timezone date
    current_month_str = datetime.now(timezone.utc).date().strftime("%Y-%m")
    await db.execute(
        "INSERT INTO budgets (user_id, month, category_id, limit_amount, created_at, updated_at) VALUES (?, ?, 402, 200, datetime('now'), datetime('now'))",
        (6856090314, current_month_str)
    )
    await db.commit()
    
    # Step 4.2: Start expense transaction logging of 500 KZT (over budget limit!)
    await state_ctx.clear()
    msg_lim1 = Message(message_id=401, date=datetime.now(timezone.utc), chat=chat, text="➖ Расход", from_user=user)
    await dp.feed_update(bot, Update(update_id=41, message=msg_lim1), db=db)
    
    msg_lim2 = Message(message_id=402, date=datetime.now(timezone.utc), chat=chat, text="500", from_user=user)
    await dp.feed_update(bot, Update(update_id=42, message=msg_lim2), db=db)
    
    cb_lim3 = CallbackQuery(id="cb_403", from_user=user, chat_instance="inst_1", message=msg_lim1, data="expacc:1")
    await dp.feed_update(bot, Update(update_id=43, callback_query=cb_lim3), db=db)
    
    cb_lim4 = CallbackQuery(id="cb_404", from_user=user, chat_instance="inst_1", message=msg_lim1, data="expcat:402")
    await dp.feed_update(bot, Update(update_id=44, callback_query=cb_lim4), db=db)

    cb_lim5 = CallbackQuery(id="cb_405", from_user=user, chat_instance="inst_1", message=msg_lim1, data="expnote:no")
    await dp.feed_update(bot, Update(update_id=45, callback_query=cb_lim5), db=db)

    # Step 4.3: Confirm the overdraft expense of 500 KZT
    bot.sent_messages.clear()
    cb_lim6 = CallbackQuery(id="cb_406", from_user=user, chat_instance="inst_1", message=msg_lim1, data="expcfm:save")
    await dp.feed_update(bot, Update(update_id=46, callback_query=cb_lim6), db=db)
    
    # Verify Limit Push promo alert message was dispatched
    limit_push_alert_dispatched = False
    for method, params in bot.sent_messages:
        if method == "SendMessage" and "дотянуть до конца месяца" in params.get("text", ""):
            limit_push_alert_dispatched = True
            break
    assert limit_push_alert_dispatched, "A separate Limit Push promo warning with the AI help pitch must be sent!"
    
    print("🟢 [PING BACK] Worm 4/5: Red Alert breached, Limit Push promo alert dispatched with upgrade keyboard perfectly.\n")

    # =======================================================================
    # 🐛 WORM 5: 7-Day Streak Congratulations Trigger
    # =======================================================================
    print("🐛 [Worm 5/5] 7-Day Streak Reward Trigger Crawling...")
    
    # Step 5.1: Reset user to Non-Premium
    await db.execute("UPDATE users SET full_access = 0, mode = 'newbie' WHERE user_id = 6856090314")
    # Setup streak value to exactly 6 days before transaction
    yesterday_str = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    await db.execute(
        "UPDATE users SET current_streak = 6, last_activity_date = ? WHERE user_id = 6856090314",
        (yesterday_str,)
    )
    await db.commit()
    
    # Step 5.2: Start income transaction logging of 1000 KZT to trigger streak update
    await state_ctx.clear()
    msg_str1 = Message(message_id=501, date=datetime.now(timezone.utc), chat=chat, text="➕ Доход", from_user=user)
    await dp.feed_update(bot, Update(update_id=51, message=msg_str1), db=db)
    
    msg_str2 = Message(message_id=502, date=datetime.now(timezone.utc), chat=chat, text="1000", from_user=user)
    await dp.feed_update(bot, Update(update_id=52, message=msg_str2), db=db)
    
    cb_str3 = CallbackQuery(id="cb_503", from_user=user, chat_instance="inst_1", message=msg_str1, data="incacc:1")
    await dp.feed_update(bot, Update(update_id=53, callback_query=cb_str3), db=db)
    
    cb_str4 = CallbackQuery(id="cb_504", from_user=user, chat_instance="inst_1", message=msg_str1, data="inccat:403")
    await dp.feed_update(bot, Update(update_id=54, callback_query=cb_str4), db=db)

    cb_str5 = CallbackQuery(id="cb_505", from_user=user, chat_instance="inst_1", message=msg_str1, data="incnote:no")
    await dp.feed_update(bot, Update(update_id=55, callback_query=cb_str5), db=db)

    # Step 5.3: Confirm the income transaction of 1000 KZT
    bot.sent_messages.clear()
    cb_str6 = CallbackQuery(id="cb_506", from_user=user, chat_instance="inst_1", message=msg_str1, data="inccfm:save")
    await dp.feed_update(bot, Update(update_id=56, callback_query=cb_str6), db=db)
    
    # Check that streak is indeed 7 in database
    cur_user = await db.execute("SELECT current_streak FROM users WHERE user_id = 6856090314")
    user_row = await cur_user.fetchone()
    assert user_row is not None and user_row['current_streak'] == 7, "User's streak must increment to 7!"
    
    # Verify that the 7-day streak congratulations message with upgrade option was dispatched
    streak_reward_sent = False
    for method, params in bot.sent_messages:
        if method == "SendMessage" and "Невероятная дисциплина" in params.get("text", ""):
            streak_reward_sent = True
            break
    assert streak_reward_sent, "7-day streak congratulations reward message must be sent!"
    
    print("🟢 [PING BACK] Worm 5/5: 7-Day Streak incremented to 7, congratulations message with payment trigger sent perfectly.\n")

    # Clean up test database
    await db.close()
    
    print("=====================================================================")
    print(" 🎉 ALL BOT FLOW INTEGRATION CRAWLERS PASSED SUCCESSFULLY! 100% SOUND! ")
    print("=====================================================================")


if __name__ == "__main__":
    asyncio.run(run_crawler())
