# Added demo logging for tracing
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

from app.domain.services.access_service import FEATURE_DEBTS, can_use_feature

import aiosqlite
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repositories.accounts_repo import list_accounts
from app.db.repositories.settings_repo import get_debt_settings, update_debt_settings, get_lang
from app.db.repositories.debts_repo import (
    add_debt,
    apply_debt_payment,
    close_debt,
    debts_summary,
    get_debt,
    list_active_debts,
)
from app.domain.services.accounting_service import add_expense, add_income
from app.fsm.debt_states import DebtAdd, DebtPay
from app.ui.formatters import fmt_money
from app.ui.keyboards import cancel_kb, debts_menu_kb, flow_done_actions_kb, inline_cancel_kb, main_menu, debt_reminders_settings_kb
from app.ui.i18n import text_matches_key, t as _i18n_t
from app.db.repositories.settings_repo import get_lang
from app.handlers.common import deny_feature_message,  cancel_to_main_menu, is_cancel_text, neutralize_keyboard
from app.domain.services.ai_consultant_service import build_section_hint

router = Router()

DATE_FMT = "%Y-%m-%d"


# =========================================================
# Base helpers
# =========================================================

def _is_cancel(text: str | None) -> bool:
    return is_cancel_text(text)


def _today() -> date:
    """Legacy default; prefer ``await _today_for_user(db, user_id)`` in handlers.

    Kept synchronous so existing helpers that just need a *baseline* date
    (e.g. parsing default values) keep working. Anything that should respect
    the user's timezone should use ``today_in_user_tz`` directly.
    """
    return date.today()


async def _today_for_user(db, user_id: int) -> date:
    from app.domain.time_utils import today_in_user_tz
    return await today_in_user_tz(db, user_id)


def _date_human(ymd: str | None) -> str:
    if not ymd:
        return "—"
    try:
        return datetime.strptime(ymd, DATE_FMT).strftime("%d.%m.%Y")
    except Exception:
        return ymd


def _draw_progress_bar(remaining: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return ""
    # Progress is how much we ALREADY PAID
    paid = max(0, total - remaining)
    percent = min(100, int((paid / total) * 100))
    filled = int((percent / 100) * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"<code>{bar}</code> {percent}%"


def _status_label(status: str) -> str:
    return {
        "active": "🟢 Активен",
        "due_today": "🟡 Платёж сегодня",
        "overdue": "🔴 Просрочен",
    }.get(status, "🟢 Активен")


async def _parse_money(db, user_id: int, text: str | None) -> int | None:
    """Parse amount using the user's currency scale.

    Backward-compatible name; now async so we can fetch the user's currency.
    Returns whole currency units.
    """
    from app.domain.money import parse_money_for_user
    return await parse_money_for_user(db, user_id, text)


def _parse_friendly_date(text: str | None) -> str | None:
    from app.domain.validators import parse_friendly_date
    return parse_friendly_date(text)


def _normalize_row(row) -> dict:
    if isinstance(row, dict):
        debt = dict(row)
    elif hasattr(row, "keys"):
        debt = {k: row[k] for k in row.keys()}
    else:
        debt = {
            "id": row[0],
            "title": row[1],
            "payment_amount": row[2],
            "next_payment_date": row[3],
            "remaining_amount": row[4],
            "dtype": row[5],
            "direction": row[6],
            "is_active": row[7] if len(row) > 7 else 1,
            "status": row[8] if len(row) > 8 else "active",
        }

    debt["status"] = debt.get("status", "active")
    return debt


def _direction_label(direction: str) -> str:
    return "📤 Я должен" if direction == "out" else "📥 Мне должны"


def _dtype_label(dtype: str) -> str:
    return "🏦 Кредит / банк" if dtype == "bank" else "👤 Частный долг"


def _pay_label(direction: str, dtype: str) -> str:
    if direction == "out" and dtype == "bank":
        return "Платёж в месяц"
    if direction == "out":
        return "Обычно плачу"
    return "Обычно возвращают"


def _due_label(direction: str, dtype: str) -> str:
    if direction == "out" and dtype == "bank":
        return "Следующий платёж"
    if direction == "out":
        return "Напомнить"
    return "Ожидаю до"


def _account_pick_text(direction: str) -> str:
    if direction == "out":
        return "С какого счёта списать?"
    return "На какой счёт зачислить?"


def _debt_card_text(debt: dict) -> str:
    status_text = _status_label(debt.get("status", "active"))
    total = int(debt.get("total_amount") or 0)
    remaining = int(debt.get("remaining_amount") or 0)
    progress_bar = _draw_progress_bar(remaining, total)
    
    return (
        f"<b>{debt['title']}</b>\n"
        f"{progress_bar}\n\n"
        f"{_direction_label(debt['direction'])} • {_dtype_label(debt['dtype'])}\n"
        f"Статус: <b>{status_text}</b>\n\n"
        f"Остаток: <b>{fmt_money(remaining)}</b> из <b>{fmt_money(total)}</b>\n"
        f"{_pay_label(debt['direction'], debt['dtype'])}: "
        f"<b>{fmt_money(int(debt.get('payment_amount') or 0))}</b>\n"
        f"{_due_label(debt['direction'], debt['dtype'])}: "
        f"<b>{_date_human(debt.get('next_payment_date'))}</b>"
    )


def _menu_summary_text(summary_row) -> str:
    out_sum = int(summary_row["out_sum"] or 0)
    in_sum = int(summary_row["in_sum"] or 0)
    out_count = int(summary_row["out_count"] or 0)
    in_count = int(summary_row["in_count"] or 0)
    return (
        "💳 <b>Долги и кредиты</b>\n\n"
        f"📤 Я должен: <b>{out_count}</b> записей • <b>{fmt_money(out_sum)}</b>\n"
        f"📥 Мне должны: <b>{in_count}</b> записей • <b>{fmt_money(in_sum)}</b>\n\n"
        "Открой нужный раздел."
    )




async def _menu_screen_text(db: aiosqlite.Connection, user_id: int, lang: str = "ru") -> str:
    summary = await debts_summary(db, user_id)
    return _menu_summary_text(summary) + await build_section_hint(db, user_id, "debts", lang)

def _confirm_add_text(data: dict, lang: str = "ru") -> str:
    direction = data.get("direction")
    dtype = data.get("dtype")
    title = data.get("title") or "—"
    remaining = fmt_money(int(data.get("remaining_amount") or 0))
    payment = int(data.get("payment_amount") or 0)
    next_payment_date = _date_human(data.get("next_payment_date"))

    if direction == "out" and dtype == "bank":
        kind_text = "Кредит"
        payment_label = "Платёж в месяц"
    elif direction == "out":
        kind_text = "Я должен"
        payment_label = "Обычный платёж"
    else:
        kind_text = "Мне должны"
        payment_label = "Обычный возврат"

    payment_text = fmt_money(payment) if payment > 0 else "без фиксированной суммы"
    date_text = next_payment_date if next_payment_date and next_payment_date != "—" else "не указана"

    return (
        "Проверь данные 👇\n\n"
        f"Тип: <b>{kind_text}</b>\n"
        f"Название: <b>{title}</b>\n"
        f"Остаток: <b>{remaining}</b>\n"
        f"{payment_label}: <b>{payment_text}</b>\n"
        f"Дата: <b>{date_text}</b>\n\n"
        "Сохраняем?"
    )


def _next_date_after_payment(debt: dict) -> str | None:
    current = debt.get("next_payment_date")
    if not current:
        return None

    if debt["direction"] == "out" and debt["dtype"] == "bank":
        try:
            return (
                datetime.strptime(current, DATE_FMT) + relativedelta(months=1)
            ).strftime(DATE_FMT)
        except Exception:
            return current

    return current


# =========================================================
# Keyboards
# =========================================================

def _debt_list_kb(rows: list, direction: str):
    kb = InlineKeyboardBuilder()

    for row in rows:
        debt = _normalize_row(row)
        rem_val = int(debt.get("remaining_amount") or 0)
        rem_str = fmt_money(rem_val)
        title = debt["title"]
        status = debt.get("status")

        prefix = ""
        if status == "overdue":
            prefix = "🔴 "
        elif status == "due_today":
            prefix = "🟡 "

        total = int(debt.get("total_amount") or 0)
        if total <= 0:
            total = rem_val

        percent = 0
        if total > 0:
            percent = min(100, int(((total - rem_val) / total) * 100))

        label = f"{prefix}{title} · {percent}% · {rem_str}"
        if len(label) > 46:
            label = label[:43] + "..."

        kb.button(text=label, callback_data=f"debt:open:{debt['id']}:{direction}")

    kb.button(text="➕ Добавить", callback_data="debt:add")
    kb.button(text="⬅️ Назад", callback_data="debt:menu")
    kb.adjust(1)
    return kb.as_markup()


def _debt_detail_kb(debt_id: int, direction: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Провести платёж", callback_data=f"debt:pay:{debt_id}")
    kb.button(text="✔️ Закрыть запись", callback_data=f"debt:close:{debt_id}")
    kb.button(text="⬅️ К списку", callback_data=f"debt:back:list:{direction}")
    kb.button(text="🏠 Долги и кредиты", callback_data="debt:menu")
    kb.adjust(1)
    return kb.as_markup()


def _direction_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Я должен", callback_data="debt:adddir:out")
    kb.button(text="📥 Мне должны", callback_data="debt:adddir:in")
    kb.adjust(1)
    return kb.as_markup()


def _type_kb(direction: str):
    kb = InlineKeyboardBuilder()
    if direction == "out":
        kb.button(text="🏦 Кредит / банк", callback_data="debt:addtype:bank")
        kb.button(text="👤 Частный долг", callback_data="debt:addtype:private")
        kb.adjust(1)
    else:
        kb.button(text="👤 Частный долг", callback_data="debt:addtype:private")
        kb.adjust(1)
    return kb.as_markup()


def _due_date_kb(direction: str, dtype: str):
    today = _today()
    kb = InlineKeyboardBuilder()

    kb.button(text="Сегодня", callback_data=f"debt:due:{today.strftime(DATE_FMT)}")
    kb.button(
        text="Завтра",
        callback_data=f"debt:due:{(today + timedelta(days=1)).strftime(DATE_FMT)}",
    )
    kb.button(
        text="+ 7 дней",
        callback_data=f"debt:due:{(today + timedelta(days=7)).strftime(DATE_FMT)}",
    )

    if direction == "out" and dtype == "bank":
        kb.button(
            text="+ 1 месяц",
            callback_data=f"debt:due:{(today + relativedelta(months=1)).strftime(DATE_FMT)}",
        )
        kb.button(text="📅 Ввести дату", callback_data="debt:due:custom")
        kb.adjust(2, 2, 1)
    else:
        kb.button(text="Без даты", callback_data="debt:due:none")
        kb.button(text="📅 Ввести дату", callback_data="debt:due:custom")
        kb.adjust(2, 2, 1)

    return kb.as_markup()


def _confirm_add_kb(lang: str = "ru"):
    kb = InlineKeyboardBuilder()
    kb.button(text=_i18n_t(lang, "BTN_SAVE"), callback_data="debt:add:save")
    kb.button(text=_i18n_t(lang, "BTN_CANCEL"), callback_data="debt:menu")
    kb.adjust(1)
    return kb.as_markup()


def _pay_amount_kb(debt: dict):
    scheduled = int(debt.get("payment_amount") or 0)
    remaining = int(debt.get("remaining_amount") or 0)

    kb = InlineKeyboardBuilder()
    if scheduled > 0:
        kb.button(text=f"{fmt_money(scheduled)}", callback_data=f"debt:paysum:{scheduled}")
    if remaining > 0 and remaining != scheduled:
        kb.button(
            text=f"Закрыть полностью · {fmt_money(remaining)}",
            callback_data=f"debt:paysum:{remaining}",
        )
    kb.button(text="✍️ Ввести сумму", callback_data="debt:paysum:custom")
    kb.button(text="⬅️ Назад", callback_data=f"debt:open:{debt['id']}:{debt['direction']}")
    kb.adjust(1)
    return kb.as_markup()


def _accounts_kb(accounts, debt_id: int, amount: int):
    kb = InlineKeyboardBuilder()
    for acc in accounts:
        acc_id, name, balance, _arch = acc[0], acc[1], acc[2], acc[3]
        kb.button(
            text=f"{name} · {fmt_money(int(balance or 0))}",
            callback_data=f"debt:acc:{debt_id}:{amount}:{acc_id}",
        )
    kb.button(text="⬅️ Назад", callback_data=f"debt:pay:{debt_id}")
    kb.adjust(1)
    return kb.as_markup()


def _close_kb(debt_id: int, direction: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, закрыть", callback_data=f"debt:close:yes:{debt_id}")
    kb.button(text="⬅️ Нет", callback_data=f"debt:open:{debt_id}:{direction}")
    kb.adjust(1)
    return kb.as_markup()


# =========================================================
# Screen / chat mode helpers
# =========================================================

async def _remember_debt_screen(state: FSMContext, msg: Message):
    await state.update_data(debt_screen_msg_id=msg.message_id)


async def _forget_debt_screen(state: FSMContext):
    await state.update_data(debt_screen_msg_id=None)


async def _clear_last_debt_screen(
    bot,
    chat_id: int,
    state: FSMContext,
    *,
    forget: bool = False,
):
    data = await state.get_data()
    msg_id = data.get("debt_screen_msg_id")
    if not msg_id:
        if forget:
            await _forget_debt_screen(state)
        return

    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=None,
        )
    except TelegramBadRequest:
        pass
    except Exception:
        pass

    if forget:
        await _forget_debt_screen(state)


async def _send_debt_screen(
    m: Message,
    state: FSMContext,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
):
    sent = await m.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    await _remember_debt_screen(state, sent)
    return sent


async def _edit_debt_screen(
    c: CallbackQuery,
    state: FSMContext,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
):
    try:
        await c.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        await _remember_debt_screen(state, c.message)
        return c.message
    except TelegramBadRequest:
        sent = await c.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        await _remember_debt_screen(state, sent)
        return sent


async def _enter_chat_mode(
    target: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    reply_markup=None,
    parse_mode: str = "HTML",
):
    if isinstance(target, CallbackQuery):
        bot = target.bot
        chat_id = target.message.chat.id
        send = target.message.answer
    else:
        bot = target.bot
        chat_id = target.chat.id
        send = target.answer

    await _clear_last_debt_screen(bot, chat_id, state, forget=True)
    sent = await send(text, reply_markup=reply_markup, parse_mode=parse_mode)
    await _remember_debt_screen(state, sent)
    return sent


async def _delete_debt_message(bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(message_id))
    except Exception:
        pass


async def _debt_input_step(
    target: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    lang: str,
):
    """Send a fresh text-input prompt for the debts flow. Deletes the
    previous prompt entirely (not just its markup) so the chat doesn't
    accumulate orphan ask-screens, and attaches an inline Cancel button."""
    if isinstance(target, CallbackQuery):
        bot = target.bot
        chat_id = target.message.chat.id
        send = target.message.answer
    else:
        bot = target.bot
        chat_id = target.chat.id
        send = target.answer
    data = await state.get_data()
    await _delete_debt_message(bot, chat_id, data.get("debt_screen_msg_id"))
    sent = await send(text, reply_markup=inline_cancel_kb(lang), parse_mode="HTML")
    await _remember_debt_screen(state, sent)
    return sent


async def _debt_input_error(m: Message, state: FSMContext, lang: str, text: str):
    """Validation error: drop the bad user input and rewrite the current
    prompt in place. Falls back to a new prompt if editing fails."""
    try:
        await m.delete()
    except Exception:
        pass
    data = await state.get_data()
    msg_id = data.get("debt_screen_msg_id")
    if msg_id:
        try:
            await m.bot.edit_message_text(
                chat_id=m.chat.id,
                message_id=int(msg_id),
                text=text,
                reply_markup=inline_cancel_kb(lang),
                parse_mode="HTML",
            )
            return
        except Exception:
            pass
    sent = await m.answer(text, reply_markup=inline_cancel_kb(lang), parse_mode="HTML")
    await _remember_debt_screen(state, sent)


# =========================================================
# Domain helpers
# =========================================================

async def _open_detail(
    c: CallbackQuery,
    db: aiosqlite.Connection,
    state: FSMContext,
    debt_id: int,
    direction: str | None = None,
):
    lang = await get_lang(db, c.from_user.id)
    debt_raw = await get_debt(db, c.from_user.id, debt_id)
    if not debt_raw:
        await c.answer(_i18n_t(lang, "DEBT_NOT_FOUND"), show_alert=True)
        return

    debt = _normalize_row(debt_raw)
    list_direction = direction or debt["direction"]

    await state.update_data(
        last_debt_list_direction=list_direction,
        current_debt_id=debt_id,
    )
    await _edit_debt_screen(
        c,
        state,
        _debt_card_text(debt),
        _debt_detail_kb(debt_id, list_direction),
    )
    await c.answer()


async def _ensure_category(
    db: aiosqlite.Connection,
    user_id: int,
    *,
    kind: str,
    name: str,
    emoji: str,
) -> int:
    cur = await db.execute(
        "SELECT id FROM categories WHERE user_id = ? AND kind = ? AND name = ?",
        (user_id, kind, name),
    )
    row = await cur.fetchone()
    if row:
        return int(row["id"] if hasattr(row, "keys") else row[0])

    cur = await db.execute(
        """
        INSERT INTO categories (
            user_id, name, emoji, kind, is_archived, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 0, datetime('now'), datetime('now'))
        """,
        (user_id, name, emoji, kind),
    )
    await db.commit()
    return int(cur.lastrowid)


async def _get_operation_category_id(
    db: aiosqlite.Connection,
    *,
    user_id: int,
    direction: str,
    dtype: str,
) -> int:
    if direction == "out":
        if dtype == "bank":
            return await _ensure_category(
                db,
                user_id,
                kind="expense",
                name="Платёж по кредиту",
                emoji="💳",
            )
        return await _ensure_category(
            db,
            user_id,
            kind="expense",
            name="Возврат долга",
            emoji="📤",
        )

    return await _ensure_category(
        db,
        user_id,
        kind="income",
        name="Мне вернули долг",
        emoji="📥",
    )


# =========================================================
# Entry / menu
# =========================================================

@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_DEBTS"))
async def debts_entry(m: Message, db: aiosqlite.Connection, state: FSMContext):
    await state.clear()
    lang = await get_lang(db, m.from_user.id)

    await m.answer(
        "🤝 <b>Долги и кредиты</b>",
        reply_markup=cancel_kb(lang),
        parse_mode="HTML",
    )
    await _send_debt_screen(m, state, await _menu_screen_text(db, m.from_user.id, lang), debts_menu_kb(lang))


@router.callback_query(F.data == "debt:menu")
async def debts_menu(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    await state.clear()
    lang = await get_lang(db, c.from_user.id)
    await _edit_debt_screen(c, state, await _menu_screen_text(db, c.from_user.id, lang), debts_menu_kb(lang))
    await c.answer()


@router.callback_query(F.data == "debt:settings")
async def debts_settings(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    enabled, days_before = await get_debt_settings(db, c.from_user.id)
    if lang == "en":
        text = (
            "🔔 <b>Debt reminders</b>\n\n"
            f"Status: <b>{'enabled' if enabled else 'disabled'}</b>\n"
            f"Warn before due date: <b>{days_before} day(s)</b>\n\n"
            "These reminders use each debt's next payment date."
        )
    elif lang == "kk":
        text = (
            "🔔 <b>Қарыз еске салғыштары</b>\n\n"
            f"Күйі: <b>{'қосулы' if enabled else 'өшірулі'}</b>\n"
            f"Төлемге дейін: <b>{days_before} күн</b>\n\n"
            "Еске салғыштар әр қарыздың келесі төлем күні бойынша жіберіледі."
        )
    else:
        text = (
            "🔔 <b>Напоминания по долгам</b>\n\n"
            f"Статус: <b>{'включены' if enabled else 'выключены'}</b>\n"
            f"Предупреждать до даты платежа: <b>{days_before} дн.</b>\n\n"
            "Напоминания используют дату следующего платежа у каждой записи."
        )
    await _edit_debt_screen(c, state, text, debt_reminders_settings_kb(enabled, days_before, lang))
    await c.answer()


@router.callback_query(F.data == "debt:settings:toggle")
async def debts_settings_toggle(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    from app.domain.time_utils import now_in_user_tz
    enabled, days_before = await get_debt_settings(db, c.from_user.id)
    now_iso = (await now_in_user_tz(db, c.from_user.id)).isoformat()
    await update_debt_settings(db, c.from_user.id, 0 if enabled else 1, days_before, now_iso)
    await db.commit()
    await debts_settings(c, state, db)


@router.callback_query(F.data.startswith("debt:settings:days:"))
async def debts_settings_days(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    from app.domain.time_utils import now_in_user_tz
    days = int(c.data.split(":")[-1])
    enabled, _days_before = await get_debt_settings(db, c.from_user.id)
    now_iso = (await now_in_user_tz(db, c.from_user.id)).isoformat()
    await update_debt_settings(db, c.from_user.id, enabled, days, now_iso)
    await db.commit()
    await debts_settings(c, state, db)


# =========================================================
# Add debt flow
# =========================================================

@router.callback_query(F.data == "debt:add")
async def debt_add_start(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_DEBTS):
        await deny_feature_message(c, db, c.from_user.id)
        return
    await state.clear()
    await state.set_state(DebtAdd.direction)
    logger.debug("Starting debt add flow for user %s", c.from_user.id)
    lang = await get_lang(db, c.from_user.id)
    await _edit_debt_screen(
        c,
        state,
        _i18n_t(lang, "DEBT_ADD_PICK_KIND"),
        _direction_kb(),
    )
    await c.answer()


@router.callback_query(F.data.startswith("debt:adddir:"))
async def debt_add_direction(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    direction = c.data.split(":")[-1]
    await state.update_data(direction=direction)
    await state.set_state(DebtAdd.dtype)

    lang = await get_lang(db, c.from_user.id)
    await _edit_debt_screen(
        c,
        state,
        _i18n_t(lang, "DEBT_ADD_PICK_TYPE"),
        _type_kb(direction),
    )
    await c.answer()


@router.callback_query(F.data.startswith("debt:addtype:"))
async def debt_add_type(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    dtype = c.data.split(":")[-1]
    data = await state.get_data()
    direction = data.get("direction")

    if not direction:
        await state.clear()
        await _edit_debt_screen(
            c,
            state,
            _menu_summary_text({"out_sum": 0, "in_sum": 0, "out_count": 0, "in_count": 0}),
            debts_menu_kb(await get_lang(db, c.from_user.id)),
        )
        await c.answer()
        return

    await state.update_data(dtype=dtype)
    await state.set_state(DebtAdd.title)

    lang = await get_lang(db, c.from_user.id)
    if dtype == "bank":
        prompt = _i18n_t(lang, "DEBT_ADD_TITLE_BANK")
    elif direction == "out":
        prompt = _i18n_t(lang, "DEBT_ADD_TITLE_OUT")
    else:
        prompt = _i18n_t(lang, "DEBT_ADD_TITLE_IN")

    await _debt_input_step(c, state, prompt, lang)
    await c.answer()


@router.message(DebtAdd.title, F.text)
async def debt_add_title(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if _is_cancel(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    lang = await get_lang(db, m.from_user.id)
    title = (m.text or "").strip()
    if len(title) < 2:
        await _debt_input_error(m, state, lang, _i18n_t(lang, "DEBT_ADD_TITLE_SHORT"))
        return

    try:
        await m.delete()
    except Exception:
        pass

    await state.update_data(title=title)
    await state.set_state(DebtAdd.remaining)

    await _debt_input_step(m, state, _i18n_t(lang, "DEBT_ADD_REMAINING"), lang)


@router.message(DebtAdd.remaining, F.text)
async def debt_add_remaining(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if _is_cancel(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    lang = await get_lang(db, m.from_user.id)
    remaining = await _parse_money(db, m.from_user.id, m.text)
    if remaining is None or remaining <= 0:
        await _debt_input_error(m, state, lang, _i18n_t(lang, "AMOUNT_INVALID"))
        return

    try:
        await m.delete()
    except Exception:
        pass

    data = await state.get_data()
    direction = data["direction"]
    dtype = data["dtype"]

    await state.update_data(remaining_amount=remaining)
    await state.set_state(DebtAdd.payment)

    if direction == "out" and dtype == "bank":
        prompt = _i18n_t(lang, "DEBT_ADD_PAYMENT_BANK")
    elif direction == "out":
        prompt = _i18n_t(lang, "DEBT_ADD_PAYMENT_OUT")
    else:
        prompt = _i18n_t(lang, "DEBT_ADD_PAYMENT_IN")

    await _debt_input_step(m, state, prompt, lang)


@router.message(DebtAdd.payment, F.text)
async def debt_add_payment(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if _is_cancel(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    lang = await get_lang(db, m.from_user.id)
    payment = await _parse_money(db, m.from_user.id, m.text)
    if payment is None:
        await _debt_input_error(m, state, lang, _i18n_t(lang, "AMOUNT_INVALID"))
        return

    data = await state.get_data()
    direction = data["direction"]
    dtype = data["dtype"]

    if direction == "out" and dtype == "bank" and payment <= 0:
        await _debt_input_error(m, state, lang, _i18n_t(lang, "DEBT_ADD_PAYMENT_BANK_REQUIRED"))
        return

    try:
        await m.delete()
    except Exception:
        pass

    await state.update_data(payment_amount=payment)
    await state.set_state(DebtAdd.confirm)

    if direction == "out" and dtype == "bank":
        text = _i18n_t(lang, "DEBT_ADD_DATE_BANK")
    elif direction == "out":
        text = _i18n_t(lang, "DEBT_ADD_DATE_OUT")
    else:
        text = _i18n_t(lang, "DEBT_ADD_DATE_IN")

    await _enter_chat_mode(m, state, text, reply_markup=_due_date_kb(direction, dtype))


@router.callback_query(F.data == "debt:due:none", DebtAdd.confirm)
async def debt_due_none(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    data = await state.get_data()
    lang = await get_lang(db, c.from_user.id)

    if data["direction"] == "out" and data["dtype"] == "bank":
        await c.answer(_i18n_t(lang, "DEBT_ADD_DATE_BANK_REQUIRED_TOAST"), show_alert=True)
        return

    await state.update_data(next_payment_date=None)
    data = await state.get_data()

    await _edit_debt_screen(c, state, _confirm_add_text(data, lang), _confirm_add_kb(lang))
    await c.answer()


@router.callback_query(F.data == "debt:due:custom", DebtAdd.confirm)
async def debt_due_custom(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await state.set_state(DebtAdd.custom_due_date)
    lang = await get_lang(db, c.from_user.id)
    await _debt_input_step(c, state, _i18n_t(lang, "DEBT_ADD_DATE_PROMPT"), lang)
    await c.answer()


@router.callback_query(F.data.startswith("debt:due:"), DebtAdd.confirm)
async def debt_due_quick(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    ymd = c.data.split(":", 2)[-1]
    if ymd in {"custom", "none"}:
        await c.answer()
        return

    await state.update_data(next_payment_date=ymd)
    data = await state.get_data()
    lang = await get_lang(db, c.from_user.id)

    await _edit_debt_screen(c, state, _confirm_add_text(data, lang), _confirm_add_kb(lang))
    await c.answer()


@router.message(DebtAdd.custom_due_date, F.text)
async def debt_due_custom_save(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if _is_cancel(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    lang = await get_lang(db, m.from_user.id)
    ymd = _parse_friendly_date(m.text)
    data = await state.get_data()

    if not ymd and data["direction"] == "out" and data["dtype"] == "bank":
        await _debt_input_error(m, state, lang, _i18n_t(lang, "DEBT_ADD_DATE_BANK_REQUIRED"))
        return

    if not ymd and (m.text or "").strip().lower() not in {"0", "-", "нет"}:
        await _debt_input_error(m, state, lang, _i18n_t(lang, "DEBT_ADD_DATE_INVALID"))
        return

    try:
        await m.delete()
    except Exception:
        pass

    await state.update_data(next_payment_date=ymd)
    await state.set_state(DebtAdd.confirm)

    data = await state.get_data()
    await _enter_chat_mode(
        m,
        state,
        _confirm_add_text(data, lang),
        reply_markup=_confirm_add_kb(lang),
    )


@router.callback_query(F.data == "debt:add:save")
async def debt_add_save(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    data = await state.get_data()
    if not data:
        await c.answer(_i18n_t(lang, "DEBT_SESSION_EXPIRED"), show_alert=True)
        return
    await neutralize_keyboard(c)

    if data["direction"] == "out" and data["dtype"] == "bank" and not data.get("next_payment_date"):
        await c.answer(_i18n_t(lang, "DEBT_DATE_REQUIRED_FOR_CREDIT"), show_alert=True)
        return

    await add_debt(
        db=db,
        user_id=c.from_user.id,
        direction=data["direction"],
        dtype=data["dtype"],
        title=data["title"],
        payment_amount=int(data["payment_amount"]),
        next_payment_date=data.get("next_payment_date"),
        remaining_amount=int(data["remaining_amount"]),
    )

    await state.clear()
    summary = await debts_summary(db, c.from_user.id)

    await _edit_debt_screen(
        c,
        state,
        _i18n_t(lang, "DEBT_ADD_SAVED") + _menu_summary_text(summary),
        debts_menu_kb(lang),
    )
    await c.answer()


# =========================================================
# Lists / detail
# =========================================================

@router.callback_query(F.data.startswith("debt:list:"))
async def debts_list(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    direction = c.data.split(":")[-1]
    rows = await list_active_debts(db, c.from_user.id, direction=direction)
    title = _direction_label(direction)

    await state.update_data(last_debt_list_direction=direction)

    if not rows:
        await _edit_debt_screen(
            c,
            state,
            f"<b>{title}</b>\n\nПока пусто.",
            _debt_list_kb([], direction),
        )
        await c.answer()
        return

    await _edit_debt_screen(
        c,
        state,
        f"<b>{title}</b>\n\nВыбери запись:",
        _debt_list_kb(rows, direction),
    )
    await c.answer()


@router.callback_query(F.data.startswith("debt:back:list:"))
async def debt_back_to_list(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    direction = c.data.split(":")[-1]
    rows = await list_active_debts(db, c.from_user.id, direction=direction)
    title = _direction_label(direction)

    await state.update_data(last_debt_list_direction=direction)

    if not rows:
        await _edit_debt_screen(
            c,
            state,
            f"<b>{title}</b>\n\nПока пусто.",
            _debt_list_kb([], direction),
        )
        await c.answer()
        return

    await _edit_debt_screen(
        c,
        state,
        f"<b>{title}</b>\n\nВыбери запись:",
        _debt_list_kb(rows, direction),
    )
    await c.answer()


@router.callback_query(F.data.startswith("debt:open:"))
async def debt_open(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    parts = c.data.split(":")
    debt_id = int(parts[2])
    direction = parts[3] if len(parts) > 3 else None
    await _open_detail(c, db, state, debt_id, direction)


@router.callback_query(F.data.startswith("debt:close:yes:"))
async def debt_close_yes(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    await neutralize_keyboard(c)
    debt_id = int(c.data.split(":")[-1])
    await close_debt(db, c.from_user.id, debt_id)

    lang = await get_lang(db, c.from_user.id)
    summary = await debts_summary(db, c.from_user.id)
    await _edit_debt_screen(
        c,
        state,
        "✅ <b>Запись закрыта.</b>\n\n" + _menu_summary_text(summary) + await build_section_hint(db, c.from_user.id, "debts", lang),
        debts_menu_kb(lang),
    )
    await c.answer()


@router.callback_query(F.data.startswith("debt:close:") & ~F.data.startswith("debt:close:yes:"))
async def debt_close_ask(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    lang = await get_lang(db, c.from_user.id)
    parts = c.data.split(":")

    debt_id = int(parts[-1])
    debt_raw = await get_debt(db, c.from_user.id, debt_id)
    if not debt_raw:
        await c.answer(_i18n_t(lang, "DEBT_NOT_FOUND"), show_alert=True)
        return

    debt = _normalize_row(debt_raw)

    await _edit_debt_screen(
        c,
        state,
        "Закрыть запись вручную?\n\n"
        "Используй это только если долг реально закрыт и напоминания больше не нужны.",
        _close_kb(debt_id, debt["direction"]),
    )
    await c.answer()


# =========================================================
# Payment flow
# =========================================================

@router.callback_query(F.data.startswith("debt:pay:"))
async def debt_pay_start(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    lang = await get_lang(db, c.from_user.id)
    debt_id = int(c.data.split(":")[-1])
    debt_raw = await get_debt(db, c.from_user.id, debt_id)

    if not debt_raw:
        await c.answer(_i18n_t(lang, "DEBT_NOT_FOUND"), show_alert=True)
        return

    debt = _normalize_row(debt_raw)
    if not int(debt.get("is_active", 1)):
        await c.answer(_i18n_t(lang, "DEBT_ALREADY_CLOSED"), show_alert=True)
        return

    await state.update_data(
        pay_debt_id=debt_id,
        current_debt_id=debt_id,
        last_debt_list_direction=debt["direction"],
    )
    await state.set_state(DebtPay.amount)

    question = "Сколько провести сейчас?" if debt["direction"] == "out" else "Сколько тебе вернули сейчас?"
    text = _debt_card_text(debt) + f"\n\n{question}"

    await _edit_debt_screen(c, state, text, _pay_amount_kb(debt))
    await c.answer()


@router.callback_query(F.data.startswith("debt:paysum:"), DebtPay.amount)
async def debt_pay_amount_pick(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    amount_raw = c.data.split(":")[-1]
    if amount_raw != "custom":
        await neutralize_keyboard(c)
    data = await state.get_data()
    debt_id = int(data["pay_debt_id"])

    debt_raw = await get_debt(db, c.from_user.id, debt_id)
    if not debt_raw:
        await state.clear()
        await c.answer(_i18n_t(lang, "DEBT_NOT_FOUND"), show_alert=True)
        return

    debt = _normalize_row(debt_raw)

    if amount_raw == "custom":
        lang = await get_lang(db, c.from_user.id)
        await _debt_input_step(
            c,
            state,
            "Введи сумму цифрами.\n\nПример: <b>25000</b>",
            lang,
        )
        await c.answer()
        return

    amount = int(amount_raw)
    await state.update_data(pay_amount=amount)

    accounts = [a for a in await list_accounts(db, c.from_user.id) if not a[5]]
    if not accounts:
        await state.clear()
        await _edit_debt_screen(c, state, _i18n_t(lang, "DEBT_NEED_ACCOUNT"), debts_menu_kb())
        await c.answer()
        return

    text = (
        _debt_card_text(debt)
        + f"\n\nСумма: <b>{fmt_money(amount)}</b>\n"
        + _account_pick_text(debt["direction"])
    )
    await _edit_debt_screen(c, state, text, _accounts_kb(accounts, debt_id, amount))
    await c.answer()


@router.message(DebtPay.amount, F.text)
async def debt_pay_amount_custom(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if _is_cancel(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    lang = await get_lang(db, m.from_user.id)
    amount = await _parse_money(db, m.from_user.id, m.text)
    if amount is None or amount <= 0:
        await _debt_input_error(m, state, lang, _i18n_t(lang, "AMOUNT_INVALID"))
        return

    try:
        await m.delete()
    except Exception:
        pass

    data = await state.get_data()
    debt_id = int(data["pay_debt_id"])
    await state.update_data(pay_amount=amount)

    debt_raw = await get_debt(db, m.from_user.id, debt_id)
    if not debt_raw:
        await _clear_last_debt_screen(m.bot, m.chat.id, state, forget=True)
        await state.clear()
        await m.answer(_i18n_t(lang, "DEBT_NOT_FOUND"), reply_markup=debts_menu_kb())
        return

    debt = _normalize_row(debt_raw)

    accounts = [a for a in await list_accounts(db, m.from_user.id) if not a[5]]
    if not accounts:
        await _clear_last_debt_screen(m.bot, m.chat.id, state, forget=True)
        await state.clear()
        await m.answer(_i18n_t(lang, "DEBT_NEED_ACCOUNT"), reply_markup=debts_menu_kb())
        return

    text = (
        _debt_card_text(debt)
        + f"\n\nСумма: <b>{fmt_money(amount)}</b>\n"
        + _account_pick_text(debt["direction"])
    )
    await _enter_chat_mode(
        m,
        state,
        text,
        reply_markup=_accounts_kb(accounts, debt_id, amount),
    )


@router.callback_query(F.data.startswith("debt:acc:"))
async def debt_pick_account(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    lang = await get_lang(db, c.from_user.id)
    await neutralize_keyboard(c)
    parts = c.data.split(":")
    if len(parts) != 5:
        await c.answer(_i18n_t(lang, "DEBT_BAD_DATA"), show_alert=True)
        return

    debt_id = int(parts[2])
    amount = int(parts[3])
    account_id = int(parts[4])

    debt_raw = await get_debt(db, c.from_user.id, debt_id)
    if not debt_raw:
        await c.answer(_i18n_t(lang, "DEBT_NOT_FOUND"), show_alert=True)
        return

    debt = _normalize_row(debt_raw)
    direction = debt["direction"]
    dtype = debt["dtype"]
    title = debt["title"]

    category_id = await _get_operation_category_id(
        db,
        user_id=c.from_user.id,
        direction=direction,
        dtype=dtype,
    )

    await db.execute("BEGIN IMMEDIATE")
    try:
        if direction == "out":
            note = f"Платёж по кредиту: {title}" if dtype == "bank" else f"Возврат долга: {title}"
            await add_expense(db, c.from_user.id, amount, account_id, category_id, note, commit=False)
        else:
            note = f"Мне вернули долг: {title}"
            await add_income(db, c.from_user.id, amount, account_id, category_id, note, commit=False)

        next_date = _next_date_after_payment(debt)
        await apply_debt_payment(db, c.from_user.id, debt_id, amount, next_date, commit=False)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    updated_raw = await get_debt(db, c.from_user.id, debt_id)
    is_closed = False
    remaining_text = "0"

    if not updated_raw:
        is_closed = True
    else:
        updated = _normalize_row(updated_raw)
        remaining_amount = int(updated.get("remaining_amount") or 0)
        remaining_text = fmt_money(remaining_amount)
        if not int(updated.get("is_active", 1)) or remaining_amount <= 0:
            is_closed = True

    # закрываем старый экран полностью
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await state.clear()
    await _forget_debt_screen(state)

    if direction == "out":
        action_text = "Платёж проведён"
    else:
        action_text = "Возврат проведён"

    if is_closed:
        text = (
            f"✅ <b>{action_text}</b>\n\n"
            f"Запись: <b>{title}</b>\n"
            f"Сумма: <b>{fmt_money(amount)}</b>\n"
            f"Статус: <b>закрыта</b>"
        )
    else:
        text = (
            f"✅ <b>{action_text}</b>\n\n"
            f"Запись: <b>{title}</b>\n"
            f"Сумма: <b>{fmt_money(amount)}</b>\n"
            f"Остаток: <b>{remaining_text}</b>"
        )

    await c.message.answer(
        text,
        reply_markup=await build_main_menu_markup(db, c.from_user.id, await get_lang(db, c.from_user.id)),
        parse_mode="HTML",
    )
    await c.answer()


@router.callback_query(F.data.startswith("debt:remindsnooze:"))
async def debt_reminder_snooze(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    lang = await get_lang(db, c.from_user.id)
    # The reminder is already marked as sent for today in the scheduler logic
    # so we just show a confirmation.
    text = _i18n_t(lang, "REMINDER_SNOOZED_DEBT") or "Окей, напомню завтра!"
    actions = flow_done_actions_kb(lang, list_cb="debt:menu", menu_cb="hub:main")
    try:
        await c.message.edit_text(text, parse_mode="HTML", reply_markup=actions)
    except Exception:
        await c.message.answer(text, parse_mode="HTML", reply_markup=actions)
    await c.answer()
