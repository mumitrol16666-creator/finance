# app/handlers/onboarding.py

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from datetime import datetime, timezone
import aiosqlite
import re
from loguru import logger

from app.config.settings import settings
from app.db.repositories.users_repo import get_onboarded, set_onboarded, set_newbie_defaults, grant_full_access
from app.db.repositories.settings_repo import get_lang, set_lang, ensure_settings
from app.db.repositories.categories_repo import ensure_default_categories
from app.fsm.states import TelegramOnboarding
from app.domain.auth import hash_password, verify_password
from app.handlers.common import build_main_menu_markup, cancel_to_main_menu, neutralize_keyboard, is_cancel_text
from app.domain.services.ai_consultant_service import build_main_menu_text
from app.domain.money import get_user_currency, get_scale
from app.ui.texts import get_text
from app.ui.keyboards import (
    lang_selection_kb, currency_kb, cancel_kb, yes_no_kb, daily_time_quick_kb
)
from app.domain.validators import clean_name, parse_hhmm
from app.domain.services.onboarding_service import (
    init_user, save_currency, add_account, has_any_account,
    save_daily_report, finish_onboarding, utcnow_iso
)

router = Router()
PARSE_MODE = "HTML"

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

# Keyboard builders
def onboarding_welcome_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📱 Я уже зарегистрирован в приложении")
    builder.button(text="🤖 Зарегистрироваться через Telegram")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

def back_kb(btn_text: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=f"⬅️ {btn_text}")
    return builder.as_markup(resize_keyboard=True)

async def _try_delete(bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(message_id))
    except Exception:
        pass

# Helper to sync DB and FSM state
async def set_state_db(db: aiosqlite.Connection, user_id: int, state_name: str):
    await db.execute("UPDATE users SET onboarding_state = ? WHERE id = ?", (state_name, user_id))
    await db.commit()

@router.message(CommandStart())
async def start(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await state.clear()
    user_id = m.from_user.id
    
    # Check if user exists
    cur = await db.execute("SELECT onboarding_state, password_hash FROM users WHERE id = ?", (user_id,))
    row = await cur.fetchone()
    
    if row:
        onboarding_state, password_hash = row[0], row[1]
        if onboarding_state == "completed":
            lang = await get_lang(db, user_id)
            menu_text = await build_main_menu_text(db, user_id, lang)
            
            # Show a warning if password is still LEGACY_PLACEHOLDER
            if password_hash == 'LEGACY_PLACEHOLDER':
                menu_text = (
                    "⚠️ <b>Внимание:</b> У вас не установлен пароль для мобильного приложения!\n"
                    "Пожалуйста, отправьте команду /login, чтобы установить пароль и войти в приложение FinTrack.\n\n"
                ) + menu_text
                
            return await m.answer(menu_text, reply_markup=await build_main_menu_markup(db, user_id, lang), parse_mode=PARSE_MODE)
    else:
        # Create temp user
        now = utcnow_iso()
        # To satisfy NOT NULL constraints, username = f"tmp_tg_{user_id}", password_hash = "tmp_hash"
        await db.execute(
            "INSERT INTO users (id, telegram_id, username, password_hash, display_name, onboarding_state, created_at, onboarded) "
            "VALUES (?, ?, ?, ?, ?, 'select_auth_type', ?, 0)",
            (user_id, user_id, f"tmp_tg_{user_id}", "tmp_hash", f"User {user_id}", now)
        )
        await ensure_settings(db, user_id, now, settings.timezone)
        await db.commit()

    # Initiate onboarding
    await set_state_db(db, user_id, "select_auth_type")
    await state.set_state(TelegramOnboarding.select_auth_type)
    
    welcome_text = (
        "👋 <b>Добро пожаловать в FinTrack!</b>\n\n"
        "Я помогу вам легко контролировать расходы, ставить финансовые цели и оптимизировать бюджет с помощью искусственного интеллекта.\n\n"
        "Выберите способ продолжения:"
    )
    await m.answer(welcome_text, reply_markup=onboarding_welcome_kb(), parse_mode=PARSE_MODE)


# --- SELECT AUTH TYPE HANDLERS ---
@router.message(TelegramOnboarding.select_auth_type, F.text == "📱 Я уже зарегистрирован в приложении")
async def process_auth_link_start(m: Message, state: FSMContext, db: aiosqlite.Connection):
    user_id = m.from_user.id
    await set_state_db(db, user_id, "tg_link_login")
    await state.set_state(TelegramOnboarding.tg_link_login)
    await m.answer(
        "Введите ваш логин от приложения FinTrack:",
        reply_markup=back_kb("Назад к выбору"),
        parse_mode=PARSE_MODE
    )

@router.message(TelegramOnboarding.select_auth_type, F.text == "🤖 Зарегистрироваться через Telegram")
async def process_auth_reg_start(m: Message, state: FSMContext, db: aiosqlite.Connection):
    user_id = m.from_user.id
    await set_state_db(db, user_id, "tg_reg_name")
    await state.set_state(TelegramOnboarding.tg_reg_name)
    await m.answer(
        "Как к вам обращаться? Введите ваше имя:",
        reply_markup=back_kb("Назад к выбору"),
        parse_mode=PARSE_MODE
    )

# --- BRANCH A: LINK EXISTING ACCOUNT ---
@router.message(TelegramOnboarding.tg_link_login, F.text == "⬅️ Назад к выбору")
async def link_login_back(m: Message, state: FSMContext, db: aiosqlite.Connection):
    user_id = m.from_user.id
    await set_state_db(db, user_id, "select_auth_type")
    await state.set_state(TelegramOnboarding.select_auth_type)
    await m.answer("Выберите способ продолжения:", reply_markup=onboarding_welcome_kb(), parse_mode=PARSE_MODE)

@router.message(TelegramOnboarding.tg_link_login, F.text)
async def process_link_login(m: Message, state: FSMContext, db: aiosqlite.Connection):
    username = m.text.strip().lower()
    
    # Check if login exists in DB (excluding temporary bot accounts)
    cur = await db.execute("SELECT id FROM users WHERE LOWER(username) = ? AND username NOT LIKE 'tmp_tg_%'", (username,))
    row = await cur.fetchone()
    
    if not row:
        return await m.answer(
            "Пользователь с таким логином не найден. Проверьте ввод или выберите регистрацию через Telegram.",
            reply_markup=back_kb("Назад к выбору"),
            parse_mode=PARSE_MODE
        )
        
    await state.update_data(link_username=username)
    user_id = m.from_user.id
    await set_state_db(db, user_id, "tg_link_password")
    await state.set_state(TelegramOnboarding.tg_link_password)
    await m.answer(
        "Логин успешно найден! Теперь введите ваш пароль для подтверждения синхронизации:",
        reply_markup=back_kb("Назад к логину"),
        parse_mode=PARSE_MODE
    )

@router.message(TelegramOnboarding.tg_link_password, F.text == "⬅️ Назад к логину")
async def link_password_back(m: Message, state: FSMContext, db: aiosqlite.Connection):
    user_id = m.from_user.id
    await set_state_db(db, user_id, "tg_link_login")
    await state.set_state(TelegramOnboarding.tg_link_login)
    await m.answer(
        "Введите ваш логин от приложения FinTrack:",
        reply_markup=back_kb("Назад к выбору"),
        parse_mode=PARSE_MODE
    )

@router.message(TelegramOnboarding.tg_link_password, F.text)
async def process_link_password(m: Message, state: FSMContext, db: aiosqlite.Connection):
    password = m.text.strip()
    data = await state.get_data()
    username = data.get("link_username")
    temp_tg_id = m.from_user.id
    
    cur = await db.execute("SELECT id, password_hash, display_name FROM users WHERE LOWER(username) = ?", (username,))
    row = await cur.fetchone()
    
    if not row:
        # Unexpected: username vanished
        await set_state_db(db, temp_tg_id, "tg_link_login")
        await state.set_state(TelegramOnboarding.tg_link_login)
        return await m.answer("Произошла ошибка. Пожалуйста, введите логин заново:")
        
    app_user_id, password_hash, display_name = row[0], row[1], row[2]
    
    if password_hash == 'LEGACY_PLACEHOLDER':
        return await m.answer(
            "Для этого аккаунта еще не установлен пароль. Пожалуйста, зайдите в настройки мобильного приложения или обратитесь в поддержку.",
            reply_markup=back_kb("Назад к логину")
        )
        
    if not verify_password(password, password_hash):
        return await m.answer(
            "Неверный пароль. Пожалуйста, попробуйте еще раз:",
            reply_markup=back_kb("Назад к логину")
        )
        
    # Keep the Telegram ID as the internal ID because existing bot handlers use it
    # directly. The merge is atomic: either every table moves or nothing changes.
    try:
        linked = await db.execute(
            "SELECT telegram_id FROM users WHERE id=?",
            (app_user_id,),
        )
        linked_row = await linked.fetchone()
        if linked_row and linked_row[0] not in (None, temp_tg_id):
            return await m.answer("Этот аккаунт уже связан с другим Telegram-профилем.")

        await db.commit()
        await db.execute("PRAGMA foreign_keys = OFF;")
        await db.execute("BEGIN IMMEDIATE")

        tables_cur = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = []
        for table_row in await tables_cur.fetchall():
            table_name = str(table_row[0])
            if table_name in {"users", "migrations"}:
                continue
            columns_cur = await db.execute(f"PRAGMA table_info(`{table_name}`)")
            columns = {str(column[1]) for column in await columns_cur.fetchall()}
            if "user_id" in columns:
                tables.append(table_name)

        # Temporary onboarding data cannot override the established app account.
        for tbl in tables:
            await db.execute(f"DELETE FROM `{tbl}` WHERE user_id = ?", (temp_tg_id,))

        await db.execute("DELETE FROM users WHERE id = ?", (temp_tg_id,))

        for tbl in tables:
            await db.execute(
                f"UPDATE `{tbl}` SET user_id = ? WHERE user_id = ?",
                (temp_tg_id, app_user_id),
            )

        await db.execute("UPDATE users SET id = ?, telegram_id = ? WHERE id = ?", (temp_tg_id, temp_tg_id, app_user_id))

        fk_cur = await db.execute("PRAGMA foreign_key_check")
        fk_errors = await fk_cur.fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key check failed after account link: {fk_errors[:3]}")
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.exception("Failed to merge account during link: {}", e)
        return await m.answer("Произошла ошибка при связывании аккаунтов. Пожалуйста, попробуйте позже.")
    finally:
        await db.execute("PRAGMA foreign_keys = ON;")

    # Advance to AI Survey hook
    await set_state_db(db, temp_tg_id, "ai_survey_invite")
    await state.set_state(TelegramOnboarding.ai_survey_invite)
    await show_ai_survey_invite(m)


# --- BRANCH B: REGISTER NEW ACCOUNT ---
@router.message(TelegramOnboarding.tg_reg_name, F.text == "⬅️ Назад к выбору")
async def reg_name_back(m: Message, state: FSMContext, db: aiosqlite.Connection):
    user_id = m.from_user.id
    await set_state_db(db, user_id, "select_auth_type")
    await state.set_state(TelegramOnboarding.select_auth_type)
    await m.answer("Выберите способ продолжения:", reply_markup=onboarding_welcome_kb(), parse_mode=PARSE_MODE)

@router.message(TelegramOnboarding.tg_reg_name, F.text)
async def process_reg_name(m: Message, state: FSMContext, db: aiosqlite.Connection):
    name = m.text.strip()
    if not name or len(name) < 2:
        return await m.answer("Имя должно содержать не менее 2 символов. Пожалуйста, введите ваше имя:")
        
    user_id = m.from_user.id
    await db.execute("UPDATE users SET display_name = ? WHERE id = ?", (name, user_id))
    await set_state_db(db, user_id, "tg_reg_login")
    await state.set_state(TelegramOnboarding.tg_reg_login)
    await m.answer(
        "Придумайте уникальный логин (латиницей, без пробелов). Он понадобится вам, чтобы зайти в мобильное приложение FinTrack:",
        reply_markup=back_kb("Назад к имени"),
        parse_mode=PARSE_MODE
    )

@router.message(TelegramOnboarding.tg_reg_login, F.text == "⬅️ Назад к имени")
async def reg_login_back(m: Message, state: FSMContext, db: aiosqlite.Connection):
    user_id = m.from_user.id
    await set_state_db(db, user_id, "tg_reg_name")
    await state.set_state(TelegramOnboarding.tg_reg_name)
    await m.answer(
        "Как к вам обращаться? Введите ваше имя:",
        reply_markup=back_kb("Назад к выбору"),
        parse_mode=PARSE_MODE
    )

@router.message(TelegramOnboarding.tg_reg_login, F.text)
async def process_reg_login(m: Message, state: FSMContext, db: aiosqlite.Connection):
    username = m.text.strip().lower()
    
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        return await m.answer("Логин должен содержать только латинские буквы, цифры и подчеркивания. Попробуйте еще раз:")
        
    user_id = m.from_user.id
    # Check uniqueness (excluding their own temporary row)
    cur = await db.execute("SELECT 1 FROM users WHERE LOWER(username) = ? AND id != ?", (username, user_id))
    if await cur.fetchone():
        return await m.answer("Этот логин уже занят, попробуйте другой:")
        
    await db.execute("UPDATE users SET username = ? WHERE id = ?", (username, user_id))
    await set_state_db(db, user_id, "tg_reg_password")
    await state.set_state(TelegramOnboarding.tg_reg_password)
    await m.answer(
        "Отлично! Теперь придумайте надежный пароль:",
        reply_markup=back_kb("Назад к логину"),
        parse_mode=PARSE_MODE
    )

@router.message(TelegramOnboarding.tg_reg_password, F.text == "⬅️ Назад к логину")
async def reg_password_back(m: Message, state: FSMContext, db: aiosqlite.Connection):
    user_id = m.from_user.id
    await set_state_db(db, user_id, "tg_reg_login")
    await state.set_state(TelegramOnboarding.tg_reg_login)
    await m.answer(
        "Придумайте уникальный логин (латиницей, без пробелов):",
        reply_markup=back_kb("Назад к имени"),
        parse_mode=PARSE_MODE
    )

@router.message(TelegramOnboarding.tg_reg_password, F.text)
async def process_reg_password(m: Message, state: FSMContext, db: aiosqlite.Connection):
    password = m.text.strip()
    if len(password) < 6:
        return await m.answer("Пароль должен состоять минимум из 6 символов. Пожалуйста, придумайте надежный пароль:")
        
    user_id = m.from_user.id
    hashed = hash_password(password)
    
    await db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed, user_id))
    await db.commit()
    
    await set_state_db(db, user_id, "tg_reg_lang")
    await state.set_state(TelegramOnboarding.tg_reg_lang)
    
    prompt = (
        "🇷🇺 <b>Выберите язык</b>\n\n"
        "🇬🇧 <b>Choose language</b>\n\n"
        "🇰🇿 <b>Тілді таңдаңыз</b>"
    )
    sent = await m.answer(prompt, reply_markup=lang_selection_kb(), parse_mode=PARSE_MODE)
    await state.update_data(flow_message_id=sent.message_id)


# --- STEP-BY-STEP ONBOARDING WIZARD ---

@router.callback_query(TelegramOnboarding.tg_reg_lang, F.data.startswith('ob:lang:'))
async def ob_lang_selected(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    lang = c.data.split(':')[-1]
    await set_lang(db, c.from_user.id, lang, utcnow_iso())
    await db.commit()
    
    await set_state_db(db, c.from_user.id, "tg_reg_currency")
    await state.set_state(TelegramOnboarding.tg_reg_currency)
    
    await c.message.edit_text(
        get_text(lang, 'ASK_CURRENCY'),
        reply_markup=currency_kb(),
        parse_mode=PARSE_MODE
    )
    await c.answer()

@router.callback_query(TelegramOnboarding.tg_reg_currency, F.data.startswith('ob:cur:'))
async def ob_currency_selected(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    cur = c.data.split(':')[2]
    await save_currency(db, c.from_user.id, cur)
    lang = await get_lang(db, c.from_user.id)
    
    await set_state_db(db, c.from_user.id, "tg_reg_acc_name")
    await state.set_state(TelegramOnboarding.tg_reg_acc_name)
    
    # Send currency confirmation message first, then ask for account name
    await c.message.edit_text(
        get_text(lang, 'CURRENCY_SAVED', cur=cur),
        reply_markup=None,
        parse_mode=PARSE_MODE
    )
    
    sent = await c.message.answer(
        get_text(lang, 'ASK_ACC_NAME'),
        reply_markup=cancel_kb(lang),
        parse_mode=PARSE_MODE
    )
    await state.update_data(prompt_message_id=sent.message_id)
    await c.answer()

@router.message(TelegramOnboarding.tg_reg_acc_name, F.text)
async def ob_acc_name(m: Message, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    name = clean_name(m.text)
    if not name:
        return await m.answer(get_text(lang, 'NAME_ERROR'), reply_markup=cancel_kb(lang))
    data = await state.get_data()
    await _try_delete(m.bot, m.chat.id, data.get("prompt_message_id"))
    try:
        await m.delete()
    except Exception:
        pass
    await state.update_data(acc_name=name)
    await set_state_db(db, m.from_user.id, "tg_reg_acc_balance")
    await state.set_state(TelegramOnboarding.tg_reg_acc_balance)
    sent = await m.answer(get_text(lang, 'ASK_ACC_BAL'), reply_markup=cancel_kb(lang), parse_mode=PARSE_MODE)
    await state.update_data(prompt_message_id=sent.message_id)

@router.message(TelegramOnboarding.tg_reg_acc_balance, F.text)
async def ob_acc_bal(m: Message, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    from app.domain.money import parse_money_for_user
    raw = (m.text or "").strip().replace(" ", "").replace(",", ".")
    if raw in {"0", "0.0", "0.00"}:
        bal = 0
    else:
        bal = await parse_money_for_user(db, m.from_user.id, m.text, max_minor=99_999_999_00)
        if bal is None:
            return await m.answer(get_text(lang, 'SUM_ERROR'), reply_markup=cancel_kb(lang))
    data = await state.get_data()
    await _try_delete(m.bot, m.chat.id, data.get("prompt_message_id"))
    try:
        await m.delete()
    except Exception:
        pass
    await add_account(db, m.from_user.id, data['acc_name'], bal)
    await state.clear()
    
    await set_state_db(db, m.from_user.id, "tg_reg_daily")
    await state.set_state(TelegramOnboarding.tg_reg_daily)
    await m.answer(get_text(lang, 'ASK_DAILY'), reply_markup=yes_no_kb('ob:daily', lang), parse_mode=PARSE_MODE)

@router.callback_query(TelegramOnboarding.tg_reg_daily, F.data.startswith('ob:daily:'))
async def ob_daily_selected(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    ans = c.data.split(':')[2]
    lang = await get_lang(db, c.from_user.id)
    if ans == 'no':
        await save_daily_report(db, c.from_user.id, 0, '21:00')
        await finish_onboarding(db, c.from_user.id)
        
        # Go to AI Survey Invite
        await set_state_db(db, c.from_user.id, "ai_survey_invite")
        await state.set_state(TelegramOnboarding.ai_survey_invite)
        await show_ai_survey_invite(c.message)
        await c.answer()
        return
    await save_daily_report(db, c.from_user.id, 1, '21:00')
    await set_state_db(db, c.from_user.id, "tg_reg_daily_time")
    await state.set_state(TelegramOnboarding.tg_reg_daily_time)
    await c.message.edit_text(get_text(lang, 'ASK_DAILY_TIME'), reply_markup=daily_time_quick_kb(lang), parse_mode=PARSE_MODE)
    await c.answer()

@router.callback_query(TelegramOnboarding.tg_reg_daily_time, F.data.startswith('ob:time:'))
async def ob_time_pick(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    part = c.data.split(':')[2:]
    lang = await get_lang(db, c.from_user.id)
    if part[0] == 'other':
        await set_state_db(db, c.from_user.id, "tg_reg_daily_time_custom")
        await state.set_state(TelegramOnboarding.tg_reg_daily_time_custom)
        sent = await c.message.answer(get_text(lang, 'CUSTOM_TIME'), reply_markup=cancel_kb(lang))
        await state.update_data(prompt_message_id=sent.message_id)
        await c.answer()
        return
    hhmm = ':'.join(part)
    await save_daily_report(db, c.from_user.id, 1, hhmm)
    await finish_onboarding(db, c.from_user.id)
    
    # Go to AI Survey Invite
    await set_state_db(db, c.from_user.id, "ai_survey_invite")
    await state.set_state(TelegramOnboarding.ai_survey_invite)
    await show_ai_survey_invite(c.message)
    await c.answer()

@router.message(TelegramOnboarding.tg_reg_daily_time_custom, F.text)
async def ob_time_custom(m: Message, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    hhmm = parse_hhmm(m.text)
    if not hhmm:
        return await m.answer(get_text(lang, 'TIME_ERROR'))
    await save_daily_report(db, m.from_user.id, 1, hhmm)
    await finish_onboarding(db, m.from_user.id)
    
    # Go to AI Survey Invite
    await set_state_db(db, m.from_user.id, "ai_survey_invite")
    await state.set_state(TelegramOnboarding.ai_survey_invite)
    await show_ai_survey_invite(m)


# --- STEP 4: AI SURVEY HOOK ---
async def show_ai_survey_invite(m: Message):
    invite_text = (
        "Почти готово! Финальный шаг: пройдите короткий опрос от нашего ИИ-Аудитора. "
        "Это займет не более 1 минуты, но позволит ИИ сразу подстроить аналитику под ваши цели.\n\n"
        "🎁 <b>За прохождение опроса мы дарим вам 7 дней полного Premium-доступа!</b>"
    )
    
    # Inline buttons (no text bypass)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Ответить на 4 вопроса и получить Premium", callback_data="ai_survey:start")],
        [InlineKeyboardButton(text="⚠️ Начать без Premium (Отказываюсь от подарка)", callback_data="ai_survey:decline")]
    ])
    await m.answer(invite_text, reply_markup=kb, parse_mode=PARSE_MODE)

@router.callback_query(TelegramOnboarding.ai_survey_invite, F.data == "ai_survey:decline")
async def process_survey_decline(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    user_id = c.from_user.id
    now = utcnow_iso()
    await ensure_default_categories(db, user_id, now)
    await set_onboarded(db, user_id, 1)
    await set_newbie_defaults(db, user_id)
    await set_state_db(db, user_id, "completed")
    await state.clear()
    
    await c.message.edit_text("Опрос пропущен. Добро пожаловать на главный экран!")
    lang = await get_lang(db, user_id)
    menu_text = await build_main_menu_text(db, user_id, lang)
    await c.message.answer(menu_text, reply_markup=await build_main_menu_markup(db, user_id, lang), parse_mode=PARSE_MODE)
    await c.answer()

@router.callback_query(TelegramOnboarding.ai_survey_invite, F.data == "ai_survey:start")
async def process_survey_start(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    user_id = c.from_user.id
    await set_state_db(db, user_id, "ai_survey_q1")
    await state.set_state(TelegramOnboarding.ai_survey_q1)
    
    await c.message.delete()
    
    prompt = (
        "🎯 <b>Вопрос 1 из 4:</b>\n\n"
        "Какая ваша главная финансовая цель? (например: накопить на квартиру, закрыть кредиты, купить машину, создать подушку безопасности)"
    )
    await c.message.answer(prompt, reply_markup=back_kb("Назад к опросу"), parse_mode=PARSE_MODE)
    await c.answer()


# --- AI SURVEY QUESTIONS ---
# Q1 Back button
@router.message(TelegramOnboarding.ai_survey_q1, F.text == "⬅️ Назад к опросу")
async def survey_q1_back(m: Message, state: FSMContext, db: aiosqlite.Connection):
    user_id = m.from_user.id
    await set_state_db(db, user_id, "ai_survey_invite")
    await state.set_state(TelegramOnboarding.ai_survey_invite)
    await show_ai_survey_invite(m)

# Q1 Answer
@router.message(TelegramOnboarding.ai_survey_q1, F.text)
async def process_survey_q1(m: Message, state: FSMContext, db: aiosqlite.Connection):
    goal_text = m.text.strip()
    await state.update_data(survey_q1=goal_text)
    
    user_id = m.from_user.id
    await set_state_db(db, user_id, "ai_survey_q2")
    await state.set_state(TelegramOnboarding.ai_survey_q2)
    
    prompt = (
        "💰 <b>Вопрос 2 из 4:</b>\n\n"
        "Какую сумму вы планируете накопить или достичь для этой цели? (Напишите числом, например: 5000000)"
    )
    await m.answer(prompt, reply_markup=back_kb("Назад к первому вопросу"), parse_mode=PARSE_MODE)

# Q2 Back button
@router.message(TelegramOnboarding.ai_survey_q2, F.text == "⬅️ Назад к первому вопросу")
async def survey_q2_back(m: Message, state: FSMContext, db: aiosqlite.Connection):
    user_id = m.from_user.id
    await set_state_db(db, user_id, "ai_survey_q1")
    await state.set_state(TelegramOnboarding.ai_survey_q1)
    prompt = (
        "🎯 <b>Вопрос 1 из 4:</b>\n\n"
        "Какая ваша главная финансовая цель? (например: накопить на квартиру, закрыть кредиты, купить машину, создать подушку безопасности)"
    )
    await m.answer(prompt, reply_markup=back_kb("Назад к опросу"), parse_mode=PARSE_MODE)

# Q2 Answer
@router.message(TelegramOnboarding.ai_survey_q2, F.text)
async def process_survey_q2(m: Message, state: FSMContext, db: aiosqlite.Connection):
    amount_str = re.sub(r"\D", "", m.text)
    if not amount_str:
        return await m.answer("Пожалуйста, введите сумму числом (например: 150000):")
    
    amount = int(amount_str)
    await state.update_data(survey_q2=amount)
    
    user_id = m.from_user.id
    await set_state_db(db, user_id, "ai_survey_q3")
    await state.set_state(TelegramOnboarding.ai_survey_q3)
    
    prompt = (
        "📅 <b>Вопрос 3 из 4:</b>\n\n"
        "В какой срок вы планируете достичь этой цели? (например: за 1 год, за 6 месяцев, к концу 2026 года)"
    )
    await m.answer(prompt, reply_markup=back_kb("Назад ко второму вопросу"), parse_mode=PARSE_MODE)

# Q3 Back button
@router.message(TelegramOnboarding.ai_survey_q3, F.text == "⬅️ Назад ко второму вопросу")
async def survey_q3_back(m: Message, state: FSMContext, db: aiosqlite.Connection):
    user_id = m.from_user.id
    await set_state_db(db, user_id, "ai_survey_q2")
    await state.set_state(TelegramOnboarding.ai_survey_q2)
    prompt = (
        "💰 <b>Вопрос 2 из 4:</b>\n\n"
        "Какую сумму вы планируете накопить или достичь для этой цели? (Напишите числом, например: 5000000)"
    )
    await m.answer(prompt, reply_markup=back_kb("Назад к первому вопросу"), parse_mode=PARSE_MODE)

# Q3 Answer
@router.message(TelegramOnboarding.ai_survey_q3, F.text)
async def process_survey_q3(m: Message, state: FSMContext, db: aiosqlite.Connection):
    deadline = m.text.strip()
    await state.update_data(survey_q3=deadline)
    
    user_id = m.from_user.id
    await set_state_db(db, user_id, "ai_survey_q4")
    await state.set_state(TelegramOnboarding.ai_survey_q4)
    
    prompt = (
        "💳 <b>Вопрос 4 из 4:</b>\n\n"
        "Какая сумма дневного лимита на повседневные расходы будет для вас комфортной? (Напишите числом, например: 5000)"
    )
    await m.answer(prompt, reply_markup=back_kb("Назад к третьему вопросу"), parse_mode=PARSE_MODE)

# Q4 Back button
@router.message(TelegramOnboarding.ai_survey_q4, F.text == "⬅️ Назад к третьему вопросу")
async def survey_q4_back(m: Message, state: FSMContext, db: aiosqlite.Connection):
    user_id = m.from_user.id
    await set_state_db(db, user_id, "ai_survey_q3")
    await state.set_state(TelegramOnboarding.ai_survey_q3)
    prompt = (
        "📅 <b>Вопрос 3 из 4:</b>\n\n"
        "В какой срок вы планируете достичь этой цели? (например: за 1 год, за 6 месяцев, к концу 2026 года)"
    )
    await m.answer(prompt, reply_markup=back_kb("Назад ко второму вопросу"), parse_mode=PARSE_MODE)

# Q4 Answer
@router.message(TelegramOnboarding.ai_survey_q4, F.text)
async def process_survey_q4(m: Message, state: FSMContext, db: aiosqlite.Connection):
    limit_str = re.sub(r"\D", "", m.text)
    if not limit_str:
        return await m.answer("Пожалуйста, введите сумму дневного лимита числом (например: 5000):")
        
    daily_limit = int(limit_str)
    
    # Save everything to settings
    data = await state.get_data()
    goal_text = data.get("survey_q1")
    goal_amount = data.get("survey_q2")
    deadline = data.get("survey_q3")
    
    user_id = m.from_user.id
    now = utcnow_iso()
    
    currency = await get_user_currency(db, user_id)
    scale = get_scale(currency)
    daily_limit_minor = daily_limit * scale
    
    # We update settings:
    # financial_goal_text, financial_goal_amount, financial_goal_deadline, onboarding_daily_limit, onboarding_main_goal, onboarding_interview_done=1
    await db.execute(
        """
        UPDATE settings 
        SET financial_goal_text = ?, 
            financial_goal_amount = ?, 
            financial_goal_deadline = ?, 
            onboarding_main_goal = ?, 
            onboarding_daily_limit = ?, 
            onboarding_interview_done = 1,
            onboarding_archetype = 'controller',
            updated_at = ?
        WHERE user_id = ?
        """,
        (goal_text, goal_amount, deadline, goal_text, daily_limit_minor, now, user_id)
    )
    
    # Enable onboarding and grant 7 days trial Premium
    await ensure_default_categories(db, user_id, now)
    await set_onboarded(db, user_id, 1)
    await grant_full_access(db, user_id, days=7)
    
    # Complete onboarding state
    await set_state_db(db, user_id, "completed")
    await state.clear()
    
    congrats = (
        "🎉 <b>Опрос успешно пройден!</b>\n\n"
        "Мы сохранили ваши цели. Теперь наш ИИ-Аудитор подстроит рекомендации под ваши лимиты.\n\n"
        "🎁 <b>Вам начислено 7 дней бесплатного Premium-доступа!</b> Приятного использования!"
    )
    await m.answer(congrats, parse_mode=PARSE_MODE)
    
    lang = await get_lang(db, user_id)
    menu_text = await build_main_menu_text(db, user_id, lang)
    await m.answer(menu_text, reply_markup=await build_main_menu_markup(db, user_id, lang), parse_mode=PARSE_MODE)


# --- LEGACY PASSWORD SETUP BRIDGE HANDLER ---
@router.message(TelegramOnboarding.waiting_legacy_password, F.text)
async def process_legacy_password(m: Message, state: FSMContext, db: aiosqlite.Connection):
    password = m.text.strip()
    
    # Check if back/cancel text
    from app.handlers.common import is_cancel_text
    if is_cancel_text(password):
        user_id = m.from_user.id
        await set_state_db(db, user_id, "completed")
        await state.clear()
        return await cancel_to_main_menu(m, state, db)
        
    if len(password) < 6:
        return await m.answer("Пароль должен состоять минимум из 6 символов. Пожалуйста, введите надежный пароль:")
        
    user_id = m.from_user.id
    hashed = hash_password(password)
    
    await db.execute("UPDATE users SET password_hash = ?, onboarding_state = 'completed' WHERE id = ?", (hashed, user_id))
    await db.commit()
    await state.clear()
    
    await m.answer(
        "✅ <b>Пароль успешно установлен!</b>\n\n"
        "Теперь вы можете войти в мобильное приложение FinTrack, используя ваш логин и этот пароль.",
        parse_mode=PARSE_MODE
    )
    
    lang = await get_lang(db, user_id)
    menu_text = await build_main_menu_text(db, user_id, lang)
    await m.answer(menu_text, reply_markup=await build_main_menu_markup(db, user_id, lang), parse_mode=PARSE_MODE)
