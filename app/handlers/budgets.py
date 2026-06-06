from __future__ import annotations

import aiosqlite
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.fsm.states import BudgetFlow
from app.handlers.common import cancel_to_main_menu, is_cancel_text, deny_feature_message, neutralize_keyboard
from app.domain.services.access_service import can_use_feature, FEATURE_BUDGETS
from app.ui.keyboards import (
    budgets_categories_kb,
    budgets_confirm_kb,
    budgets_done_kb,
    main_menu,
    cancel_kb,
)
from app.db.repositories.budgets_repo import (
    month_key,
    upsert_budget,
    month_limits_status_map,
    get_category_limit_status,
)
from app.ui.i18n import t
from app.db.repositories.categories_repo import list_categories, get_category
from app.db.repositories.settings_repo import get_lang
from app.handlers.settings_categories_limits import show_limits_overview

router = Router()


MONTHS_RU = {
    1: "январь",
    2: "февраль",
    3: "март",
    4: "апрель",
    5: "май",
    6: "июнь",
    7: "июль",
    8: "август",
    9: "сентябрь",
    10: "октябрь",
    11: "ноябрь",
    12: "декабрь",
}


def _fmt(n: int | None, *, with_currency: bool = True, currency: str = "KZT") -> str:
    """Format minor units using the central currency-aware formatter.

    ``with_currency=False`` drops the currency symbol (used when the symbol is
    rendered separately, e.g. badges). ``currency`` defaults to KZT so existing
    call sites keep working until they are updated to pass the user's currency.
    """
    if n is None:
        return "—"
    from app.domain.money import fmt_money as _fmt_money, get_symbol
    formatted = _fmt_money(int(n), currency=currency)
    if not with_currency:
        symbol = get_symbol(currency)
        return formatted.rsplit(" ", 1)[0] if formatted.endswith(symbol) else formatted
    return formatted


def _fmt_month(month: str) -> str:
    try:
        year_str, month_str = month.split("-")
        year = int(year_str)
        month_num = int(month_str)
        return f"{MONTHS_RU.get(month_num, month_str)} {year}"
    except Exception:
        return month


def _category_label(name: str, emoji: str | None) -> str:
    return f"{(emoji + ' ') if emoji else ''}{name}".strip()


def _cancel_reply_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    return cancel_kb(lang)

async def _track_flow_message(state: FSMContext, message_id: int):
    await state.update_data(flow_message_id=message_id)


async def _clear_budget_prompt(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if not prompt_message_id:
        return

    bot = target.bot
    chat_id = target.chat.id if isinstance(target, Message) else target.message.chat.id
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(prompt_message_id))
    except Exception:
        pass
    await state.update_data(prompt_message_id=None)


async def _safe_remove_markup(bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=int(message_id), reply_markup=None)
    except Exception:
        pass


async def _start_budget_input_flow(c: CallbackQuery, state: FSMContext, screen_text: str, prompt_text: str):
    await _clear_budget_prompt(c, state)
    await _safe_remove_markup(c.bot, c.message.chat.id, c.message.message_id)
    data = await state.get_data()
    lang = data.get("lang", "ru")
    screen = await c.message.answer(screen_text, parse_mode="HTML")
    prompt = await c.message.answer(prompt_text, reply_markup=_cancel_reply_kb(lang))
    await state.update_data(flow_message_id=screen.message_id, prompt_message_id=prompt.message_id)



def _category_actions_kb(*, has_limit: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    if has_limit:
        kb.button(text="✏️ Изменить лимит", callback_data="bud:start_set")
        kb.button(text="🗑 Убрать лимит", callback_data="bud:remove")
        kb.adjust(1, 1)
    else:
        kb.button(text="➕ Установить лимит", callback_data="bud:start_set")
        kb.adjust(1)

    kb.button(text="📂 Все категории", callback_data="bud:pick")
    kb.button(text="⬅️ В меню", callback_data="bud:menu")
    kb.adjust(1, 2)
    return kb.as_markup()


def _budget_picker_meta(
    cats: list[tuple[int, str, str | None]],
    status_map: dict[int, dict[str, int | str]],
) -> tuple[list[tuple[int, str, str | None]], dict[int, str], dict[int, str]]:
    status_map = status_map or {}

    def key(row: tuple[int, str, str | None]):
        cid, name, _emoji, *_ = row
        info = status_map.get(int(cid))

        if info:
            state = str(info.get("state") or "")
            spent = int(info.get("spent") or 0)
            limit_value = info.get("limit")

            if state == "over":
                bucket = 0
            elif state == "warn":
                bucket = 1
            elif limit_value is None and spent > 0:
                bucket = 2
            elif spent > 0:
                bucket = 3
            elif limit_value is None:
                bucket = 5
            else:
                bucket = 4

            return (bucket, -spent, name.lower())

        return (5, 0, name.lower())

    ordered = sorted(cats, key=key)

    right_map: dict[int, str] = {}
    badge_map: dict[int, str] = {}

    for cid, _name, _emoji, *_ in ordered:
        info = status_map.get(int(cid))

        if not info:
            right_map[int(cid)] = t(lang, "LABEL_NO_LIMIT")
            badge_map[int(cid)] = "plain"
            continue

        left = int(info.get("left") or 0)
        spent = int(info.get("spent") or 0)
        state = str(info.get("state") or "ok")
        limit_value = info.get("limit")

        if limit_value is None:
            if spent > 0:
                right_map[int(cid)] = f"{t(lang, 'LABEL_SPENT')} {_fmt(spent)}"
            else:
                right_map[int(cid)] = t(lang, "LABEL_NO_LIMIT")
            badge_map[int(cid)] = "plain"
            continue

        if state == "over":
            right_map[int(cid)] = f"{t(lang, 'LABEL_OVER')} {_fmt(abs(left))}"
            badge_map[int(cid)] = "over"
        elif state == "warn":
            right_map[int(cid)] = f"{t(lang, 'LABEL_LEFT')} {_fmt(left)}"
            badge_map[int(cid)] = "warn"
        else:
            right_map[int(cid)] = f"{t(lang, 'LABEL_LEFT')} {_fmt(left)}"
            badge_map[int(cid)] = "ok"

    return ordered, right_map, badge_map


def _progress_bar(percent: float, length: int = 10) -> str:
    filled = int((percent / 100) * length)
    filled = max(0, min(length, filled))
    return f"[{'█'*filled}{'░'*(length - filled)}]"

def _limit_card_text(
    *,
    month: str,
    category_name: str,
    spent: int,
    current_limit: int | None,
    left_now: int | None,
) -> str:
    lines = [
        "📌 <b>Лимит по категории</b>",
        "",
        f"🗂 Категория: <b>{category_name}</b>",
        f"📅 Период: <b>{_fmt_month(month)}</b>",
        f"💸 Расход за месяц: <b>{_fmt(spent)}</b>",
    ]

    if current_limit is None:
        lines.append("📉 Текущий лимит: <b>не задан</b>")
        if spent > 0:
            lines.append(f"⚪️ Сейчас категория без лимита, уже потрачено: <b>{_fmt(spent)}</b>")
        lines += [
            "",
            "Нажми <b>«Установить лимит»</b>, чтобы задать сумму для этой категории.",
        ]
        return "\n".join(lines)

    percent = (spent / current_limit) * 100 if current_limit > 0 else 0
    bar = _progress_bar(percent, 10)
    lines.append(f"📉 Текущий лимит: <b>{_fmt(current_limit)}</b>")
    lines.append(f"📊 <code>{bar}</code> {percent:.0f}%")

    if left_now is not None:
        if left_now > 0:
            lines.append(f"🟢 Остаток: <b>{_fmt(left_now)}</b>")
        elif left_now == 0:
            lines.append(f"🟡 Лимит исчерпан: <b>{_fmt(0)}</b>")
        else:
            lines.append(f"🔴 Перерасход: <b>{_fmt(abs(left_now))}</b>")

    lines += [
        "",
        "Выбери действие ниже.",
    ]
    return "\n".join(lines)


def _set_limit_prompt_text(
    *,
    month: str,
    category_name: str,
    spent: int,
    current_limit: int | None,
) -> str:
    lines = [
        "✏️ <b>Установка лимита</b>",
        "",
        f"🗂 Категория: <b>{category_name}</b>",
        f"📅 Период: <b>{_fmt_month(month)}</b>",
        f"💸 Расход за месяц: <b>{_fmt(spent)}</b>",
    ]

    if current_limit is None:
        lines.append("📉 Текущий лимит: <b>не задан</b>")
    else:
        lines.append(f"📉 Текущий лимит: <b>{_fmt(current_limit)}</b>")

    lines += [
        "",
        "Введи сумму лимита числом без пробелов и валюты.",
        "Например: <code>10000</code>",
    ]
    return "\n".join(lines)


def _confirm_text(
    *,
    month: str,
    category_name: str,
    amount: int,
    current_limit: int | None,
    spent: int,
) -> str:
    future_left = int(amount) - int(spent)

    lines = [
        "✅ <b>Подтверждение лимита</b>",
        "",
        f"🗂 Категория: <b>{category_name}</b>",
        f"📅 Период: <b>{_fmt_month(month)}</b>",
        f"💸 Расход за месяц: <b>{_fmt(spent)}</b>",
    ]

    if current_limit is None:
        lines.append("📉 Текущий лимит: <b>не задан</b>")
    else:
        lines.append(f"📉 Текущий лимит: <b>{_fmt(current_limit)}</b>")

    lines.append(f"🆕 Новый лимит: <b>{_fmt(amount)}</b>")

    if future_left > 0:
        lines.append(f"🟢 Остаток после установки: <b>{_fmt(future_left)}</b>")
    elif future_left == 0:
        lines.append("🟡 После установки лимит будет равен текущим тратам.")
    else:
        lines.append(f"🔴 Новый лимит уже ниже текущих трат на: <b>{_fmt(abs(future_left))}</b>")

    lines += ["", "Сохранить?"]
    return "\n".join(lines)


def _saved_text(
    *,
    month: str,
    category_name: str,
    amount: int,
    spent: int,
) -> str:
    future_left = int(amount) - int(spent)

    lines = [
        "✅ <b>Лимит сохранён</b>",
        "",
        f"🗂 Категория: <b>{category_name}</b>",
        f"📅 Период: <b>{_fmt_month(month)}</b>",
        f"📉 Новый лимит: <b>{_fmt(amount)}</b>",
        f"💸 Уже потрачено: <b>{_fmt(spent)}</b>",
    ]

    if future_left > 0:
        lines.append(f"🟢 Остаток теперь: <b>{_fmt(future_left)}</b>")
    elif future_left == 0:
        lines.append("🟡 Лимит теперь равен текущим тратам.")
    else:
        lines.append(f"🔴 Уже выше лимита на: <b>{_fmt(abs(future_left))}</b>")

    return "\n".join(lines)


def _remove_confirm_text(*, month: str, category_name: str, spent: int) -> str:
    return "\n".join(
        [
            "🗑 <b>Удаление лимита</b>",
            "",
            f"🗂 Категория: <b>{category_name}</b>",
            f"📅 Период: <b>{_fmt_month(month)}</b>",
            f"💸 Уже потрачено: <b>{_fmt(spent)}</b>",
            "",
            "Убрать лимит у этой категории?",
        ]
    )


def _removed_text(*, month: str, category_name: str, spent: int) -> str:
    return "\n".join(
        [
            "🗑 <b>Лимит убран</b>",
            "",
            f"🗂 Категория: <b>{category_name}</b>",
            f"📅 Период: <b>{_fmt_month(month)}</b>",
            f"💸 Уже потрачено в этом месяце: <b>{_fmt(spent)}</b>",
            "",
            "Теперь категория снова без лимита.",
        ]
    )


def _remove_confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Да, убрать", callback_data="bud:remove_confirm")
    kb.button(text="⬅️ Назад", callback_data="bud:remove_back")
    kb.adjust(1, 1)
    return kb.as_markup()


async def _delete_budget_if_exists(
    db: aiosqlite.Connection,
    user_id: int,
    month: str,
    category_id: int,
) -> None:
    await db.execute(
        """
        DELETE FROM budgets
        WHERE user_id = ? AND month = ? AND category_id = ?
        """,
        (user_id, month, category_id),
    )


async def _load_category_card_data(
    db: aiosqlite.Connection,
    *,
    user_id: int,
    category_id: int,
    month: str,
):
    row = await get_category(db, user_id, category_id)
    if not row:
        return None

    _cat_id, cat_name, cat_emoji, cat_kind, is_archived = row
    if int(is_archived or 0) == 1 or cat_kind != "expense":
        return None

    category_name = _category_label(cat_name, cat_emoji)
    status = await get_category_limit_status(db, user_id, month, category_id)

    current_limit = int(status["limit"]) if status and status.get("limit") is not None else None
    spent = int(status["spent"]) if status else 0
    left_now = int(status["left"]) if status and status.get("left") is not None else None

    return {
        "category_id": category_id,
        "category_name": category_name,
        "month": month,
        "current_limit": current_limit,
        "spent": spent,
        "left_now": left_now,
    }


async def _show_category_card(
    c: CallbackQuery,
    state: FSMContext,
    db: aiosqlite.Connection,
    *,
    category_id: int,
    month: str,
):
    data = await _load_category_card_data(
        db,
        user_id=c.from_user.id,
        category_id=category_id,
        month=month,
    )
    if not data:
        await state.clear()
        await c.message.edit_text("Категория недоступна.", reply_markup=None)
        await c.message.answer("Меню:", reply_markup=main_menu())
        return False

    await state.update_data(
        category_id=data["category_id"],
        category_name=data["category_name"],
        month=data["month"],
        current_limit=data["current_limit"],
        spent=data["spent"],
        amount=None,
    )
    await state.set_state(BudgetFlow.pick_category)

    await c.message.edit_text(
        _limit_card_text(
            month=data["month"],
            category_name=data["category_name"],
            spent=data["spent"],
            current_limit=data["current_limit"],
            left_now=data["left_now"],
        ),
        reply_markup=_category_actions_kb(has_limit=data["current_limit"] is not None),
        parse_mode="HTML",
    )
    return True


async def show_budget_categories(
    target: Message | CallbackQuery,
    state: FSMContext,
    db: aiosqlite.Connection,
):
    from app.ui.i18n import t as _i18n_t
    user_id = target.from_user.id
    lang = await get_lang(db, user_id)
    await state.update_data(lang=lang)
    await state.clear()
    await state.set_state(BudgetFlow.pick_category)
    await _clear_budget_prompt(target, state)

    month = month_key()
    cats = await list_categories(db, user_id, kind="expense")

    if not cats:
        text = _i18n_t(lang, "NO_EXPENSE_CATEGORIES")
        if isinstance(target, CallbackQuery):
            await target.answer()
            await target.message.edit_text(text, reply_markup=None, parse_mode="HTML")
            await target.message.answer(_i18n_t(lang, "MENU_TITLE"), reply_markup=main_menu(), parse_mode="HTML")
        else:
            await target.answer(text, reply_markup=main_menu(), parse_mode="HTML")
        return

    status_map = await month_limits_status_map(db, user_id, month)
    ordered, right_map, badge_map = _budget_picker_meta(cats, status_map)

    text = f"{_i18n_t(lang, 'LIMITS_TITLE')}\n\n{_i18n_t(lang, 'LIMITS_PICKER_HINT')}"
    kb = budgets_categories_kb(ordered, right_map=right_map, badge_map=badge_map)

    if isinstance(target, CallbackQuery):
        await target.answer()
        await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await _track_flow_message(state, target.message.message_id)
    else:
        sent = await target.answer(text, reply_markup=kb, parse_mode="HTML")
        await _track_flow_message(state, sent.message_id)


@router.message(Command("budget"))
async def budget_start(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, m.from_user.id, FEATURE_BUDGETS):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await show_limits_overview(m, state, db)


@router.callback_query(F.data == "st:budgets")
async def budget_from_settings(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await show_limits_overview(c, state, db)


@router.callback_query(BudgetFlow.pick_category, F.data.startswith("bud:cat:"))
async def budget_pick_cat(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await c.answer()

    try:
        cid = int(c.data.split(":")[2])
    except Exception:
        await show_budget_categories(c, state, db)
        return

    month = month_key()
    await _show_category_card(c, state, db, category_id=cid, month=month)


@router.callback_query(F.data == "bud:pick")
async def budget_pick_list(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await show_budget_categories(c, state, db)


@router.callback_query(BudgetFlow.pick_category, F.data == "bud:start_set")
async def budget_start_set(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_BUDGETS):
        await deny_feature_message(c, db, c.from_user.id)
        return
    await c.answer()

    data = await state.get_data()
    month = data.get("month")
    category_name = data.get("category_name")
    spent = int(data.get("spent") or 0)
    current_limit = data.get("current_limit")

    if not month or not category_name:
        await state.clear()
        lang = await get_lang(db, c.from_user.id)
        await c.message.edit_text(t(lang, "BUDGET_SESSION_EXPIRED"), reply_markup=None, parse_mode="HTML")
        await c.message.answer("Меню:", reply_markup=main_menu())
        return

    await state.set_state(BudgetFlow.enter_amount)

    await _start_budget_input_flow(
        c,
        state,
        _set_limit_prompt_text(
            month=str(month),
            category_name=str(category_name),
            spent=spent,
            current_limit=current_limit if isinstance(current_limit, int) else None,
        ),
        "Введи сумму или нажми «Отмена».",
    )


@router.message(BudgetFlow.enter_amount, F.text)
async def budget_enter_amount(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    from app.domain.money import parse_money_for_user
    from app.ui.i18n import t as _i18n_t

    lang = await get_lang(db, m.from_user.id)
    amount = await parse_money_for_user(db, m.from_user.id, m.text, max_minor=10_000_000_000)
    if amount is None:
        await m.answer(
            _i18n_t(lang, "AMOUNT_INVALID"),
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    month = data.get("month")
    cid = data.get("category_id")
    category_name = data.get("category_name")
    spent = int(data.get("spent") or 0)
    current_limit = data.get("current_limit")

    if not month or not cid or not category_name:
        await state.clear()
        lang = await get_lang(db, m.from_user.id)
        await m.answer(
            t(lang, "BUDGET_SESSION_EXPIRED"),
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML",
        )
        await m.answer("Меню:", reply_markup=main_menu())
        return

    await state.update_data(amount=amount)
    await state.set_state(BudgetFlow.confirm)

    await _clear_budget_prompt(m, state)

    await m.answer(
        _confirm_text(
            month=str(month),
            category_name=str(category_name),
            amount=amount,
            current_limit=current_limit if isinstance(current_limit, int) else None,
            spent=spent,
        ),
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML",
    )

    sent = await m.answer(
        "Подтверди действие:",
        reply_markup=budgets_confirm_kb(),
    )
    await state.update_data(flow_message_id=sent.message_id)


@router.callback_query(BudgetFlow.pick_category, F.data == "bud:remove")
async def budget_remove(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_BUDGETS):
        await deny_feature_message(c, db, c.from_user.id)
        return
    await c.answer()

    data = await state.get_data()
    month = data.get("month")
    category_name = data.get("category_name")
    spent = int(data.get("spent") or 0)

    if not month or not category_name:
        await state.clear()
        lang = await get_lang(db, c.from_user.id)
        await c.message.edit_text(t(lang, "BUDGET_SESSION_EXPIRED"), reply_markup=None, parse_mode="HTML")
        await c.message.answer("Меню:", reply_markup=main_menu())
        return

    await c.message.edit_text(
        _remove_confirm_text(
            month=str(month),
            category_name=str(category_name),
            spent=spent,
        ),
        reply_markup=_remove_confirm_kb(),
        parse_mode="HTML",
    )


@router.callback_query(BudgetFlow.pick_category, F.data == "bud:remove_back")
async def budget_remove_back(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await c.answer()
    data = await state.get_data()
    month = data.get("month")
    cid = data.get("category_id")

    if not month or not cid:
        await state.clear()
        lang = await get_lang(db, c.from_user.id)
        await c.message.edit_text(t(lang, "BUDGET_SESSION_EXPIRED"), reply_markup=None, parse_mode="HTML")
        await c.message.answer("Меню:", reply_markup=main_menu())
        return

    await _show_category_card(c, state, db, category_id=int(cid), month=str(month))


@router.callback_query(BudgetFlow.pick_category, F.data == "bud:remove_confirm")
async def budget_remove_confirm(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    await c.answer()

    data = await state.get_data()
    month = data.get("month")
    cid = data.get("category_id")
    category_name = data.get("category_name")
    spent = int(data.get("spent") or 0)

    if not month or not cid or not category_name:
        await state.clear()
        lang = await get_lang(db, c.from_user.id)
        await c.message.edit_text(t(lang, "BUDGET_SESSION_EXPIRED"), reply_markup=None, parse_mode="HTML")
        await c.message.answer("Меню:", reply_markup=main_menu())
        return

    try:
        await _delete_budget_if_exists(db, c.from_user.id, str(month), int(cid))
        await db.commit()
    except Exception:
        await db.rollback()
        await c.answer("Ошибка при удалении лимита.", show_alert=True)
        return

    await state.clear()
    await c.message.edit_text(
        _removed_text(
            month=str(month),
            category_name=str(category_name),
            spent=spent,
        ),
        reply_markup=budgets_done_kb(),
        parse_mode="HTML",
    )


@router.callback_query(BudgetFlow.confirm, F.data == "bud:save")
async def budget_save(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    await c.answer()
    data = await state.get_data()

    month = data.get("month")
    cid = data.get("category_id")
    amount = data.get("amount")
    category_name = data.get("category_name")
    spent = int(data.get("spent") or 0)

    if not month or not cid or amount is None or not category_name:
        await state.clear()
        lang = await get_lang(db, c.from_user.id)
        await c.message.edit_text(t(lang, "BUDGET_SESSION_EXPIRED"), reply_markup=None, parse_mode="HTML")
        await c.message.answer("Меню:", reply_markup=main_menu())
        return

    try:
        await upsert_budget(db, c.from_user.id, str(month), int(cid), int(amount))
        await db.commit()
    except Exception:
        await db.rollback()
        await c.answer("Ошибка сохранения. Попробуй ещё раз.", show_alert=True)
        return

    await state.clear()
    await c.message.edit_text(
        _saved_text(
            month=str(month),
            category_name=str(category_name),
            amount=int(amount),
            spent=spent,
        ),
        reply_markup=budgets_done_kb(),
        parse_mode="HTML",
    )


@router.callback_query(BudgetFlow.confirm, F.data == "bud:back")
async def budget_back(c: CallbackQuery, state: FSMContext):
    await c.answer()

    data = await state.get_data()
    month = data.get("month")
    category_name = data.get("category_name")
    spent = int(data.get("spent") or 0)
    current_limit = data.get("current_limit")

    if not month or not category_name:
        await state.clear()
        lang = await get_lang(db, c.from_user.id)
        await c.message.edit_text(t(lang, "BUDGET_SESSION_EXPIRED"), reply_markup=None, parse_mode="HTML")
        await c.message.answer("Меню:", reply_markup=main_menu())
        return

    await state.set_state(BudgetFlow.enter_amount)

    await _clear_budget_prompt(c, state)
    flow_message_id = data.get("flow_message_id")
    if flow_message_id:
        try:
            await c.bot.edit_message_text(
                chat_id=c.message.chat.id,
                message_id=int(flow_message_id),
                text=_set_limit_prompt_text(
                    month=str(month),
                    category_name=str(category_name),
                    spent=spent,
                    current_limit=current_limit if isinstance(current_limit, int) else None,
                ),
                reply_markup=None,
                parse_mode="HTML",
            )
        except Exception:
            screen = await c.message.answer(
                _set_limit_prompt_text(
                    month=str(month),
                    category_name=str(category_name),
                    spent=spent,
                    current_limit=current_limit if isinstance(current_limit, int) else None,
                ),
                parse_mode="HTML",
            )
            await state.update_data(flow_message_id=screen.message_id)
    else:
        screen = await c.message.answer(
            _set_limit_prompt_text(
                month=str(month),
                category_name=str(category_name),
                spent=spent,
                current_limit=current_limit if isinstance(current_limit, int) else None,
            ),
            parse_mode="HTML",
        )
        await state.update_data(flow_message_id=screen.message_id)

    lang = (await state.get_data()).get("lang", "ru")
    prompt = await c.message.answer(
        "Введи сумму или нажми «Отмена».",
        reply_markup=_cancel_reply_kb(lang),
    )
    await state.update_data(prompt_message_id=prompt.message_id)


@router.callback_query(F.data == "bud:again")
async def budget_again(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await c.answer()
    await show_budget_categories(c, state, db)


@router.callback_query(F.data == "bud:menu")
async def budget_menu(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.clear()
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await c.message.answer("Меню:", reply_markup=main_menu())


@router.callback_query(F.data == "bud:cancel")
async def budget_cancel(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    await cancel_to_main_menu(c, state, db)
    await c.message.answer("Отменено. Меню ниже.", reply_markup=main_menu())
