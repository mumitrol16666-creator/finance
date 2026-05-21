from __future__ import annotations

from datetime import datetime, timezone

import aiosqlite
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repositories.budgets_repo import (
    get_category_budget,
    month_key,
    month_limits_status_map,
    month_spent_map,
    upsert_budget,
)
from app.db.repositories.categories_repo import (
    archive_category,
    create_category,
    get_category,
    list_categories,
    name_exists_any_kind,
    rename_category,
    set_category_emoji,
)
from app.db.repositories.settings_repo import get_lang
from app.fsm.states import BudgetFlow, CategoriesFlow
from app.handlers.common import (
    build_main_menu_markup,
    cancel_to_main_menu,
    is_cancel_text,
    deny_feature_message,
    neutralize_keyboard,
    consume_user_input,
    _cleanup_ui,
)
from app.domain.services.access_service import FEATURE_BUDGETS, can_use_feature
from app.domain.money import parse_money_for_user
from app.ui.formatters import make_progress_bar
from app.ui.keyboards import cancel_kb, minimized_menu_kb
from aiogram.filters import BaseFilter

class CatLimFlowFilter(BaseFilter):
    async def __call__(self, message: Message, state: FSMContext) -> bool:
        data = await state.get_data()
        return "catlim_after" in data

router = Router()
PARSE_MODE = "HTML"
CATLIM_SCOPE = "settings_catlim"


async def _ensure_settings_reply_keyboard(target: Message | CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    if data.get("settings_reply_message_id"):
        return
    sender = target.message.answer if isinstance(target, CallbackQuery) else target.answer
    txt = "\u200b"
    sent = await sender(txt, reply_markup=minimized_menu_kb(lang), disable_notification=True)
    extra_ids = data.get("extra_prompt_message_ids") or []
    if not isinstance(extra_ids, list):
        extra_ids = [extra_ids]
    extra_ids = [x for x in extra_ids if x]
    extra_ids.append(sent.message_id)
    await state.update_data(settings_reply_message_id=sent.message_id, extra_prompt_message_ids=extra_ids)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_money(value: int | None) -> str:
    if value is None:
        return "—"
    from app.domain.money import fmt_money as _fmt_money
    return _fmt_money(int(value), currency="KZT")


def _month_title(month: str, lang: str) -> str:
    month_map = {
        "ru": ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"],
        "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
        "kk": ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"],
    }
    try:
        year, month_num = month.split("-")
        idx = int(month_num) - 1
        return f"{month_map.get(lang, month_map['ru'])[idx]} {year}"
    except Exception:
        return month


def _label(name: str, emoji: str | None, lang: str = "ru") -> str:
    from app.ui.i18n import t_category
    return f"{emoji + ' ' if emoji else ''}{t_category(name, lang)}"


def _T(lang: str, key: str, **kwargs) -> str:
    lang = (lang or "ru").lower()
    data = {
        "ru": {
            "root": "🗂 <b>КАТЕГОРИИ И ЛИМИТЫ</b>\n━━━━━━━━━━━━━━\n\nЗдесь можно управлять категориями и лимитами по ним.\nВыбери нужный раздел ниже.",
            "root_hint": "Сначала удобно настроить расходные категории и сразу проверить лимиты по ним.",
            "expense_list": "🗂 <b>КАТЕГОРИИ РАСХОДОВ</b>\n━━━━━━━━━━━━━━\n\nНажми на категорию для управления или быстрой настройки лимита.",
            "income_list": "🗂 <b>КАТЕГОРИИ ДОХОДОВ</b>\n━━━━━━━━━━━━━━\n\nНажми на категорию для управления или переименования.",
            "limits": "📌 <b>ЛИМИТЫ ПО КАТЕГОРИЯМ</b>\n━━━━━━━━━━━━━━\n\nПериод: <b>{month}</b>",
            "empty_expense": "Категорий расходов пока нет. Добавь первую категорию ниже.",
            "empty_income": "Категорий доходов пока нет. Добавь первую категорию ниже.",
            "cat_card": "🗂 <b>{name}</b>\n━━━━━━━━━━━━━━\n\n📊 <b>ДАННЫЕ ЗА МЕСЯЦ</b>\n├ Лимит: <code>{limit}</code>\n├ Израсходовано: <code>{spent}</code>\n└ Остаток: <b>{left}</b>",
            "cat_card_no_limit": "🗂 <b>{name}</b>\n━━━━━━━━━━━━━━\n\n📊 <b>ДАННЫЕ ЗА МЕСЯЦ</b>\n├ Лимит: <i>не задан</i>\n└ Израсходовано: <code>{spent}</code>\n\nМожно сразу поставить лимит или оставить без него.",
            "kind_expense": "расход",
            "kind_income": "доход",
            "set_limit_title": "📌 <b>УСТАНОВКА ЛИМИТА</b>\n━━━━━━━━━━━━━━\n\nКатегория: <b>{name}</b>\n├ Текущий: <code>{current}</code>\n└ Потрачено: <code>{spent}</code>",
            "add_title": "➕ <b>НОВАЯ КАТЕГОРИЯ</b>\n━━━━━━━━━━━━━━\n\nВведите название для новой категории.",
            "rename_title": "✏️ <b>ПЕРЕИМЕНОВАНИЕ</b>\n━━━━━━━━━━━━━━\n\nКатегория: <b>{name}</b>\nВведите новое название.",
            "input_hint_cat": "Напишите название и нажмите «Отмена», если передумали.",
            "input_hint_limit": "Введите сумму цифрами. Пример: <code>15000</code> или <code>1 200</code>. «Отмена» — выйти.",
            "bad_name": "Название должно быть от <b>2</b> до <b>24</b> символов.",
            "name_exists": "Такая категория уже есть. Выбери другое название.",
            "bad_amount": "Нужна сумма больше 0 цифрами. Пример: <code>15000</code>",
            "done_add": "✅ Категория добавлена.",
            "done_rename": "✅ Категория переименована.",
            "done_limit": "✅ Лимит сохранён.",
            "done_limit_removed": "✅ Лимит убран.",
            "done_delete": "✅ Категория удалена.",
            "done_emoji": "✅ Emoji обновлён.",
            "emoji_title": "😀 <b>EMOJI КАТЕГОРИИ</b>\n━━━━━━━━━━━━━━\n\nОтправьте один emoji или <code>-</code>, чтобы убрать его.",
            "emoji_error": "Пожалуйста, отправьте ровно один emoji или <code>-</code>.",
            "delete_confirm": "🗑 <b>УДАЛЕНИЕ КАТЕГОРИИ</b>\n━━━━━━━━━━━━━━\n\nВы уверены, что хотите удалить <b>{name}</b>?\n\n<i>Категория исчезнет из активных списков, но история транзакций сохранится.</i>",
            "remove_limit_confirm": "🗑 <b>УДАЛЕНИЕ ЛИМИТА</b>\n━━━━━━━━━━━━━━\n\nКатегория: <b>{name}</b>\n└ Лимит: <code>{current}</code>\n\nВы уверены, что хотите убрать лимит?",
            "not_found": "Категория не найдена.",
            "btn_expense": "➖ Расходные",
            "btn_income": "➕ Доходные",
            "btn_limits": "📌 Обзор лимитов",
            "btn_add": "➕ Добавить категорию",
            "btn_set_limit": "📌 Установить лимит",
            "btn_change_limit": "✏️ Изменить лимит",
            "btn_remove_limit": "🗑 Убрать лимит",
            "btn_rename": "✏️ Переименовать",
            "btn_emoji": "😀 Изменить Emoji",
            "btn_delete": "🗑 Удалить категорию",
            "btn_to_settings": "⬅️ Назад",
            "btn_back": "⬅️ Назад",
            "btn_menu": "🏠 Главное меню",
            "btn_yes_delete": "🗑 Да, удалить",
            "btn_yes_remove_limit": "🗑 Да, убрать лимит",
            "LABEL_ZERO_LEFT": "в ноль",
            "LABEL_SPENT": "потрачено",
            "LABEL_NO_LIMIT": "без лимита",
        },
        "en": {
            "root": "🗂 <b>Categories and limits</b>\n\nManage categories and their limits in one place.\nChoose a section below.",
            "root_hint": "Start with expense categories and set limits right there.",
            "expense_list": "🗂 <b>Expense categories</b>\n\nTap a category to open actions, rename it or set a limit quickly.",
            "income_list": "🗂 <b>Income categories</b>\n\nTap a category to open actions or rename it.",
            "limits": "📌 <b>Category limits</b>\n\nPeriod: <b>{month}</b>\nSee where a limit is set, where it is missing and where overspending is close.",
            "empty_expense": "There are no expense categories yet. Add the first one below.",
            "empty_income": "There are no income categories yet. Add the first one below.",
            "cat_card": "🗂 <b>{name}</b>\n━━━━━━━━━━━━━━\n\n📊 <b>MONTHLY DATA</b>\n├ Limit: <code>{limit}</code>\n├ Spent: <code>{spent}</code>\n└ Left: <b>{left}</b>",
            "cat_card_no_limit": "🗂 <b>{name}</b>\n━━━━━━━━━━━━━━\n\n📊 <b>MONTHLY DATA</b>\n├ Limit: <i>not set</i>\n└ Spent: <code>{spent}</code>\n\nYou can set a limit now or leave this category without one.",
            "kind_expense": "expense",
            "kind_income": "income",
            "set_limit_title": "📌 <b>Category limit</b>\n\nCategory: <b>{name}</b>\nCurrent limit: <b>{current}</b>\nSpent this month: <b>{spent}</b>\n\nEnter a new limit amount.",
            "add_title": "➕ <b>New category</b>\n\nEnter the category name.",
            "rename_title": "✏️ <b>Rename category</b>\n\nEnter the new category name.",
            "input_hint_cat": "Send the name and use “Cancel” if you changed your mind.",
            "input_hint_limit": "Enter the amount. Example: <code>15000</code> or <code>1,200</code>. Cancel to go back.",
            "bad_name": "The name must be between <b>2</b> and <b>24</b> characters.",
            "name_exists": "This category already exists. Choose another name.",
            "bad_amount": "Enter a number greater than 0. Example: <code>15000</code>",
            "done_add": "✅ Category added.",
            "done_rename": "✅ Category renamed.",
            "done_limit": "✅ Limit saved.",
            "done_limit_removed": "✅ Limit removed.",
            "done_delete": "✅ Category removed from the active list.",
            "done_emoji": "✅ Emoji updated.",
            "emoji_title": "😀 <b>CATEGORY EMOJI</b>\n━━━━━━━━━━━━━━\n\nSend one emoji or <code>-</code> to remove it.",
            "emoji_error": "Please send exactly one emoji or <code>-</code>.",
            "delete_confirm": "🗑 <b>Delete category</b>\n\nCategory: <b>{name}</b>\n\nIt will disappear from active lists. Existing transactions will stay.\nIts current limit will also be removed.\n\nDelete this category?",
            "remove_limit_confirm": "🗑 <b>Remove limit</b>\n\nCategory: <b>{name}</b>\nCurrent limit: <b>{current}</b>\n\nRemove this category limit?",
            "not_found": "Category not found.",
            "btn_expense": "➖ Expense",
            "btn_income": "➕ Income",
            "btn_limits": "📌 Limits overview",
            "btn_add": "➕ Add category",
            "btn_set_limit": "📌 Set limit",
            "btn_change_limit": "✏️ Change limit",
            "btn_remove_limit": "🗑 Remove limit",
            "btn_rename": "✏️ Rename",
            "btn_emoji": "😀 Change Emoji",
            "btn_delete": "🗑 Delete category",
            "btn_to_settings": "⬅️ Back",
            "btn_back": "⬅️ Back",
            "btn_menu": "🏠 Main menu",
            "btn_yes_delete": "🗑 Yes, delete",
            "btn_yes_remove_limit": "🗑 Yes, remove",
            "LABEL_ZERO_LEFT": "zero left",
            "LABEL_SPENT": "spent",
            "LABEL_NO_LIMIT": "no limit",
        },
        "kk": {
            "root": "🗂 <b>Санаттар мен лимиттер</b>\n\nМұнда санаттар мен оларға қойылатын лимиттер бір жерде басқарылады.\nТөменнен бөлімді таңдаңыз.",
            "root_hint": "Алдымен шығыс санаттарын ашып, лимиттерді сол жерден баптауға ыңғайлы.",
            "expense_list": "🗂 <b>Шығыс санаттары</b>\n\nӘрекеттерді ашу, атауын өзгерту немесе лимит орнату үшін санатты таңдаңыз.",
            "income_list": "🗂 <b>Кіріс санаттары</b>\n\nӘрекеттерді ашу немесе атауын өзгерту үшін санатты таңдаңыз.",
            "limits": "📌 <b>Санат лимиттері</b>\n\nКезең: <b>{month}</b>\nМұнда лимит қайда қойылғанын, қайда жоқ екенін және қайда артық жұмсау қаупі барын көруге болады.",
            "empty_expense": "Шығыс санаттары әлі жоқ. Төменнен біріншісін қосыңыз.",
            "empty_income": "Кіріс санаттары әлі жоқ. Төменнен біріншісін қосыңыз.",
            "cat_card": "🗂 <b>{name}</b>\n━━━━━━━━━━━━━━\n\n📊 <b>АЙЛЫҚ ДЕРЕКТЕР</b>\n├ Лимит: <code>{limit}</code>\n├ Жұмсалды: <code>{spent}</code>\n└ Қалды: <b>{left}</b>",
            "cat_card_no_limit": "🗂 <b>{name}</b>\n━━━━━━━━━━━━━━\n\n📊 <b>АЙЛЫҚ ДЕРЕКТЕР</b>\n├ Лимит: <i>орнатылмаған</i>\n└ Жұмсалды: <code>{spent}</code>\n\nҚаласаңыз лимитті қазір орнатыңыз немесе лимитсіз қалдырыңыз.",
            "kind_expense": "шығыс",
            "kind_income": "кіріс",
            "set_limit_title": "📌 <b>Санат лимиті</b>\n\nСанат: <b>{name}</b>\nҚазіргі лимит: <b>{current}</b>\nОсы айда жұмсалды: <b>{spent}</b>\n\nЖаңа лимит сомасын енгізіңіз.",
            "add_title": "➕ <b>Жаңа санат</b>\n\nСанат атауын енгізіңіз.",
            "rename_title": "✏️ <b>Санат атауын өзгерту</b>\n\nЖаңа санат атауын енгізіңіз.",
            "input_hint_cat": "Атауын жіберіңіз, ал ойыңыз өзгерсе «Болдырмау» түймесін басыңыз.",
            "input_hint_limit": "Соманы жазыңыз. Мысалы: <code>15000</code> немесе <code>1 200</code>. Шығу — «Болдырмау».",
            "bad_name": "Атауы <b>2</b> мен <b>24</b> таңба аралығында болуы керек.",
            "name_exists": "Мұндай санат бар. Басқа атау таңдаңыз.",
            "bad_amount": "0-ден үлкен сан енгізіңіз. Мысал: <code>15000</code>",
            "done_add": "✅ Санат қосылды.",
            "done_rename": "✅ Санат атауы өзгертілді.",
            "done_limit": "✅ Лимит сақталды.",
            "done_limit_removed": "✅ Лимит өшірілді.",
            "done_delete": "✅ Санат белсенді тізімнен өшірілді.",
            "done_emoji": "✅ Emoji жаңартылды.",
            "emoji_title": "😀 <b>САНАТ EMOJI-І</b>\n━━━━━━━━━━━━━━\n\nБір emoji немесе өшіру үшін <code>-</code> жіберіңіз.",
            "emoji_error": "Тек бір emoji немесе <code>-</code> жіберіңіз.",
            "delete_confirm": "🗑 <b>Санатты өшіру</b>\n\nСанат: <b>{name}</b>\n\nОл белсенді тізімнен жоғалады. Ескі операциялар сақталады.\nҚазіргі лимиті де өшіріледі.\n\nСанатты өшіру керек пе?",
            "remove_limit_confirm": "🗑 <b>Лимитті өшіру</b>\n\nСанат: <b>{name}</b>\nҚазіргі лимит: <b>{current}</b>\n\nОсы санаттың лимитін өшіру керек пе?",
            "not_found": "Санат табылмады.",
            "btn_expense": "➖ Шығыс",
            "btn_income": "➕ Кіріс",
            "btn_limits": "📌 Лимиттер шолуы",
            "btn_add": "➕ Санат қосу",
            "btn_set_limit": "📌 Лимит орнату",
            "btn_change_limit": "✏️ Лимитті өзгерту",
            "btn_remove_limit": "🗑 Лимитті өшіру",
            "btn_rename": "✏️ Атын өзгерту",
            "btn_emoji": "😀 Emoji-ді өзгерту",
            "btn_delete": "🗑 Санатты өшіру",
            "btn_to_settings": "⬅️ Артқа",
            "btn_back": "⬅️ Артқа",
            "btn_menu": "🏠 Басты мәзір",
            "btn_yes_delete": "🗑 Иә, өшіру",
            "btn_yes_remove_limit": "🗑 Иә, өшіру",
            "LABEL_ZERO_LEFT": "бітті",
            "LABEL_SPENT": "жұмсалды",
            "LABEL_NO_LIMIT": "лимитсіз",
        },
    }
    base = data.get(lang, data["ru"]).get(key, data["ru"].get(key, key))
    return base.format(**kwargs) if kwargs else base


async def _safe_delete_message(bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(message_id))
    except Exception:
        pass


async def _safe_remove_markup(bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=int(message_id), reply_markup=None)
    except Exception:
        pass


async def _clear_prompt(target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    bot = target.bot
    chat_id = target.chat.id if isinstance(target, Message) else target.message.chat.id
    await _safe_delete_message(bot, chat_id, prompt_message_id)
    await state.update_data(prompt_message_id=None)


async def _render(target: Message | CallbackQuery, state: FSMContext, text: str, reply_markup) -> None:
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")
    bot = target.bot
    chat_id = target.chat.id if isinstance(target, Message) else target.message.chat.id

    # Always delete the old window to keep the new one at the bottom
    if flow_message_id:
        await _safe_delete_message(bot, chat_id, flow_message_id)

    if isinstance(target, CallbackQuery):
        sent = await target.message.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    else:
        sent = await target.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)

    await state.update_data(flow_message_id=sent.message_id)
    await _ensure_settings_reply_keyboard(target, state, (await state.get_data()).get("lang") or "ru")


async def _start_input(target: CallbackQuery, state: FSMContext, *, screen_text: str, prompt_text: str, next_state, extra: dict | None = None) -> None:
    data = await state.get_data()
    lang = data.get("lang") or "ru"
    await _clear_prompt(target, state)
    
    # Combine screen info and prompt into one clean message at the bottom
    combined_text = f"{screen_text}\n\n{prompt_text}"
    await _render(target, state, combined_text, reply_markup=None)
    
    await state.update_data(ui_scope=CATLIM_SCOPE, lang=lang, **(extra or {}))
    await state.set_state(next_state)
    
    # Save the new flow message as prompt_id so it gets cleaned up after input
    new_data = await state.get_data()
    await state.update_data(prompt_message_id=new_data.get("flow_message_id"))


async def _lang(db: aiosqlite.Connection, user_id: int) -> str:
    try:
        return await get_lang(db, user_id)
    except Exception:
        return "ru"


async def _safe_answer(
    c: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> None:
    """Answer callback query; swallow errors (expired or duplicate taps)."""
    try:
        await c.answer(text=text, show_alert=show_alert)
    except Exception:
        pass


def _root_kb(lang: str):
    kb = InlineKeyboardBuilder()
    kb.button(text=_T(lang, "btn_expense"), callback_data="st:catlim:list:expense")
    kb.button(text=_T(lang, "btn_income"), callback_data="st:catlim:list:income")
    kb.button(text=_T(lang, "btn_limits"), callback_data="st:catlim:limits")
    kb.button(text=_T(lang, "btn_to_settings"), callback_data="st:root")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def _list_kb(items: list[tuple[str, str]], *, add_cb: str, back_cb: str, lang: str, include_limits_button: bool = False):
    kb = InlineKeyboardBuilder()
    for title, callback in items:
        kb.button(text=title, callback_data=callback)
    kb.button(text=_T(lang, "btn_add"), callback_data=add_cb)
    if include_limits_button:
        kb.button(text=_T(lang, "btn_limits"), callback_data="st:catlim:limits")
    kb.button(text=_T(lang, "btn_back"), callback_data=back_cb)
    kb.adjust(1)
    return kb.as_markup()


def _card_kb(*, lang: str, category_id: int, kind: str, has_limit: bool, back_cb: str):
    kb = InlineKeyboardBuilder()
    kb.button(text=_T(lang, "btn_rename"), callback_data=f"st:catlim:rename:{category_id}")
    kb.button(text=_T(lang, "btn_emoji"), callback_data=f"st:catlim:emoji:{category_id}")
    kb.button(text=_T(lang, "btn_delete"), callback_data=f"st:catlim:delete:{category_id}")
    if kind == "expense":
        kb.button(text=_T(lang, "btn_change_limit") if has_limit else _T(lang, "btn_set_limit"), callback_data=f"st:catlim:limit:{category_id}")
        if has_limit:
            kb.button(text=_T(lang, "btn_remove_limit"), callback_data=f"st:catlim:limit_remove:{category_id}")
    kb.button(text=_T(lang, "btn_back"), callback_data=back_cb)
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def _confirm_kb(*, yes_cb: str, back_cb: str, lang: str, remove_limit: bool = False):
    kb = InlineKeyboardBuilder()
    kb.button(text=_T(lang, "btn_yes_remove_limit") if remove_limit else _T(lang, "btn_yes_delete"), callback_data=yes_cb)
    kb.button(text=_T(lang, "btn_back"), callback_data=back_cb)
    kb.adjust(1)
    return kb.as_markup()


async def _expense_status_map(db: aiosqlite.Connection, user_id: int):
    month = month_key()
    statuses = await month_limits_status_map(db, user_id, month)
    spent_map = await month_spent_map(db, user_id, month)
    return month, statuses, spent_map


async def _build_category_rows(db: aiosqlite.Connection, user_id: int, lang: str, *, kind: str):
    cats = await list_categories(db, user_id, kind)
    month, statuses, spent_map = await _expense_status_map(db, user_id)
    rows: list[tuple[str, str]] = []
    for cid, name, emoji in cats:
        title = _label(name, emoji, lang)
        if kind == "expense":
            status = statuses.get(int(cid))
            spent = int(spent_map.get(int(cid), 0))
            if status:
                limit = int(status.get("limit") or 0)
                left = int(status.get("left") or 0)
                pbar = make_progress_bar(spent, limit, width=8)
                if left < 0:
                    right = f"🔴 {pbar} -{_fmt_money(abs(left))}"
                elif left == 0:
                    right = f"🟡 {pbar} {_T(lang, 'LABEL_ZERO_LEFT')}"
                else:
                    right = f"🟢 {pbar} {_fmt_money(left)}"
            elif spent > 0:
                right = f"⚪️ {_fmt_money(spent)} {_T(lang, 'LABEL_SPENT')}"
            else:
                right = f"⚪️ {_T(lang, 'LABEL_NO_LIMIT')}"
            title = f"{title} · {right}"
        rows.append((title, f"st:catlim:item:{cid}"))
    return cats, month, rows


async def show_catlim_root(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    lang = await _lang(db, target.from_user.id)
    await _clear_prompt(target, state)
    await state.set_state(None)
    await state.update_data(ui_scope=CATLIM_SCOPE, lang=lang, catlim_return_to="st:root", catlim_current_screen="st:catlim")
    text = f"{_T(lang, 'root')}\n\n{_T(lang, 'root_hint')}"
    await _render(target, state, text, _root_kb(lang))


async def show_category_list(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection, *, kind: str) -> None:
    lang = await _lang(db, target.from_user.id)
    cats, _month, rows = await _build_category_rows(db, target.from_user.id, lang, kind=kind)
    header = _T(lang, "expense_list") if kind == "expense" else _T(lang, "income_list")
    if not cats:
        header += f"\n\n{_T(lang, 'empty_expense' if kind == 'expense' else 'empty_income')}"
    await _clear_prompt(target, state)
    await state.set_state(None)
    await state.update_data(ui_scope=CATLIM_SCOPE, lang=lang, catlim_kind=kind, catlim_return_to=f"st:catlim:list:{kind}", catlim_current_screen=f"st:catlim:list:{kind}")
    await _render(
        target,
        state,
        header,
        _list_kb(
            rows,
            add_cb=f"st:catlim:add:{kind}",
            back_cb="st:catlim",
            lang=lang,
            include_limits_button=(kind == "expense"),
        ),
    )


async def show_limits_overview(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    lang = await _lang(db, target.from_user.id)
    cats, month, rows = await _build_category_rows(db, target.from_user.id, lang, kind="expense")
    text = _T(lang, "limits", month=_month_title(month, lang))
    if not cats:
        text += f"\n\n{_T(lang, 'empty_expense')}"
    await _clear_prompt(target, state)
    await state.set_state(None)
    await state.update_data(ui_scope=CATLIM_SCOPE, lang=lang, catlim_kind="expense", catlim_return_to="st:catlim:limits", catlim_current_screen="st:catlim:limits")
    await _render(
        target,
        state,
        text,
        _list_kb(rows, add_cb="st:catlim:add:expense", back_cb="st:catlim", lang=lang),
    )


async def show_category_card(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection, *, category_id: int, return_to: str | None = None) -> bool:
    lang = await _lang(db, target.from_user.id)
    row = await get_category(db, target.from_user.id, category_id)
    if not row or int(row[4] or 0) == 1:
        if isinstance(target, CallbackQuery):
            await target.answer(_T(lang, "not_found"), show_alert=True)
        return False
    _id, name, emoji, kind, _archived = row
    month = month_key()
    spent_map = await month_spent_map(db, target.from_user.id, month) if kind == "expense" else {}
    spent = int(spent_map.get(int(category_id), 0))
    limit_amount = await get_category_budget(db, target.from_user.id, month, category_id) if kind == "expense" else None
    left = (int(limit_amount) - spent) if limit_amount is not None else None
    label = _label(name, emoji, lang)
    if kind == "expense":
        if limit_amount is None:
            text = _T(lang, "cat_card_no_limit", name=label, kind=_T(lang, "kind_expense"), spent=_fmt_money(spent))
        else:
            text = _T(lang, "cat_card", name=label, kind=_T(lang, "kind_expense"), limit=_fmt_money(limit_amount), spent=_fmt_money(spent), left=_fmt_money(left))
            pbar = make_progress_bar(spent, int(limit_amount), width=15)
            percent = int((spent / int(limit_amount)) * 100) if int(limit_amount) > 0 else 0
            text += f"\n\n<code>{pbar}</code> {percent}%"
    else:
        income_hint = _T(lang, "income_list").split("\n\n", 1)[1]
        text = (
            f"🗂 <b>{label}</b>\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"📈 <b>ИНФОРМАЦИЯ</b>\n"
            f"└ Тип: <b>{_T(lang, 'kind_income')}</b>\n\n"
            f"{income_hint}"
        )
    back_cb = return_to or ("st:catlim:limits" if kind == "expense" else f"st:catlim:list:{kind}")
    await _clear_prompt(target, state)
    await state.set_state(None)
    await state.update_data(
        ui_scope=CATLIM_SCOPE,
        lang=lang,
        cat_id=category_id,
        catlim_kind=kind,
        catlim_return_to=back_cb,
        catlim_month=month,
        catlim_limit=limit_amount,
        catlim_spent=spent,
    )
    await _render(target, state, text, _card_kb(lang=lang, category_id=category_id, kind=kind, has_limit=limit_amount is not None, back_cb=back_cb))
    return True


async def _remove_current_month_limit(db: aiosqlite.Connection, user_id: int, category_id: int) -> None:
    await db.execute("DELETE FROM budgets WHERE user_id=? AND month=? AND category_id=?", (user_id, month_key(), category_id))


async def _return_after_input(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    data = await state.get_data()
    mode = data.get("catlim_after")
    cat_id = data.get("cat_id")
    kind = data.get("catlim_kind") or "expense"
    if mode == "card" and cat_id:
        await show_category_card(target, state, db, category_id=int(cat_id), return_to=data.get("catlim_return_to"))
        return
    if mode == "limits":
        await show_limits_overview(target, state, db)
        return
    await show_category_list(target, state, db, kind=kind)


@router.callback_query(F.data == "st:catlim")
async def catlim_root_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _safe_answer(c)
    await show_catlim_root(c, state, db)


@router.callback_query(F.data == "st:cats")
async def catlim_legacy_cats(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _safe_answer(c)
    await show_catlim_root(c, state, db)


@router.callback_query(F.data == "st:budgets")
async def catlim_legacy_budgets(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _safe_answer(c)
    await show_limits_overview(c, state, db)


@router.callback_query(F.data.startswith("st:catlim:list:"))
async def catlim_list_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _safe_answer(c)
    kind = (c.data or "").split(":")[-1]
    await show_category_list(c, state, db, kind=kind)


@router.callback_query(F.data == "st:catlim:limits")
async def catlim_limits_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _safe_answer(c)
    await show_limits_overview(c, state, db)


@router.callback_query(F.data.startswith("st:catlim:item:"))
async def catlim_item_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    try:
        category_id = int((c.data or "").split(":")[-1])
    except Exception:
        await _safe_answer(c)
        return
    await neutralize_keyboard(c)
    data = await state.get_data()
    await show_category_card(c, state, db, category_id=category_id, return_to=data.get("catlim_current_screen") or data.get("catlim_return_to") or f"st:catlim:list:{data.get('catlim_kind', 'expense')}")
    await _safe_answer(c)


@router.callback_query(F.data.startswith("st:catlim:add:"))
async def catlim_add_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    if not await can_use_feature(db, c.from_user.id, FEATURE_BUDGETS):
        await deny_feature_message(c, db, c.from_user.id)
        return
    lang = await _lang(db, c.from_user.id)
    kind = (c.data or "").split(":")[-1]
    await _start_input(
        c,
        state,
        screen_text=_T(lang, "add_title"),
        prompt_text=_T(lang, "input_hint_cat"),
        next_state=CategoriesFlow.add_name,
        extra={"catlim_kind": kind, "catlim_after": "list", "catlim_return_to": f"st:catlim:list:{kind}"},
    )
    await _safe_answer(c)


@router.message(CategoriesFlow.add_name, F.text, CatLimFlowFilter())
async def catlim_add_name(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    await consume_user_input(m, state)
    lang = await _lang(db, m.from_user.id)
    name = (m.text or "").strip()
    name = " ".join(name.split())
    if len(name) < 2 or len(name) > 24:
        await m.answer(_T(lang, "bad_name"), reply_markup=minimized_menu_kb(lang), parse_mode=PARSE_MODE)
        return
    if await name_exists_any_kind(db, m.from_user.id, name):
        await m.answer(_T(lang, "name_exists"), reply_markup=minimized_menu_kb(lang), parse_mode=PARSE_MODE)
        return
    kind = (await state.get_data()).get("catlim_kind") or "expense"
    await create_category(db, m.from_user.id, name, None, kind, _now())
    await db.commit()
    await m.answer(_T(lang, "done_add"), parse_mode=PARSE_MODE)
    await state.set_state(None)
    await _return_after_input(m, state, db)


@router.callback_query(F.data.startswith("st:catlim:rename:"))
async def catlim_rename_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    if not await can_use_feature(db, c.from_user.id, FEATURE_BUDGETS):
        await deny_feature_message(c, db, c.from_user.id)
        return
    lang = await _lang(db, c.from_user.id)
    category_id = int((c.data or "").split(":")[-1])
    data = await state.get_data()
    await _start_input(
        c,
        state,
        screen_text=_T(lang, "rename_title"),
        prompt_text=_T(lang, "input_hint_cat"),
        next_state=CategoriesFlow.rename,
        extra={
            "cat_id": category_id,
            "catlim_after": "card",
            "catlim_return_to": data.get("catlim_return_to") or f"st:catlim:list:{data.get('catlim_kind', 'expense')}",
        },
    )
    await _safe_answer(c)


@router.message(CategoriesFlow.rename, F.text, CatLimFlowFilter())
async def catlim_rename_text(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    await consume_user_input(m, state)
    lang = await _lang(db, m.from_user.id)
    data = await state.get_data()
    category_id = int(data.get("cat_id") or 0)
    row = await get_category(db, m.from_user.id, category_id)
    if not row:
        await cancel_to_main_menu(m, state, db)
        return
    new_name = " ".join((m.text or "").strip().split())
    if len(new_name) < 2 or len(new_name) > 24:
        await m.answer(_T(lang, "bad_name"), reply_markup=minimized_menu_kb(lang), parse_mode=PARSE_MODE)
        return
    if new_name.lower() != str(row[1]).lower() and await name_exists_any_kind(db, m.from_user.id, new_name):
        await m.answer(_T(lang, "name_exists"), reply_markup=minimized_menu_kb(lang), parse_mode=PARSE_MODE)
        return
    await rename_category(db, m.from_user.id, category_id, new_name, _now())
    await db.commit()
    await m.answer(_T(lang, "done_rename"), parse_mode=PARSE_MODE)
    await state.set_state(None)
    await _return_after_input(m, state, db)


@router.callback_query(F.data.startswith("st:catlim:limit:"))
async def catlim_limit_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    if not await can_use_feature(db, c.from_user.id, FEATURE_BUDGETS):
        await deny_feature_message(c, db, c.from_user.id)
        return
    category_id = int((c.data or "").split(":")[-1])
    row = await get_category(db, c.from_user.id, category_id)
    lang = await _lang(db, c.from_user.id)
    if not row or row[3] != "expense" or int(row[4] or 0) == 1:
        await _safe_answer(c, _T(lang, "not_found"), show_alert=True)
        return
    limit_amount = await get_category_budget(db, c.from_user.id, month_key(), category_id)
    spent = int((await month_spent_map(db, c.from_user.id, month_key())).get(category_id, 0))
    data = await state.get_data()
    await _start_input(
        c,
        state,
        screen_text=_T(lang, "set_limit_title", name=_label(row[1], row[2], lang), current=_fmt_money(limit_amount) if limit_amount is not None else "не задан" if lang == 'ru' else ("not set" if lang == 'en' else "орнатылмаған"), spent=_fmt_money(spent)),
        prompt_text=_T(lang, "input_hint_limit"),
        next_state=BudgetFlow.enter_amount,
        extra={
            "cat_id": category_id,
            "catlim_after": "limits",
            "catlim_return_to": data.get("catlim_return_to") or "st:catlim:limits",
        },
    )
    await _safe_answer(c)


@router.message(BudgetFlow.enter_amount, F.text)
async def catlim_limit_text(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    data = await state.get_data()
    # Same FSM state is reused by ``/budget`` wizard (category_id + month); catlim uses cat_id only.
    if data.get("cat_id") is None:
        from app.handlers.budgets import budget_enter_amount

        await budget_enter_amount(m, state, db)
        return

    await consume_user_input(m, state)
    lang = await _lang(db, m.from_user.id)
    amount = await parse_money_for_user(db, m.from_user.id, m.text, max_minor=10_000_000_000)
    if amount is None or amount <= 0:
        await m.answer(_T(lang, "bad_amount"), reply_markup=minimized_menu_kb(lang), parse_mode=PARSE_MODE)
        return
    category_id = int((await state.get_data()).get("cat_id") or 0)
    await upsert_budget(db, m.from_user.id, month_key(), category_id, int(amount))
    await db.commit()
    await m.answer(_T(lang, "done_limit"), parse_mode=PARSE_MODE)
    await state.set_state(None)
    await _return_after_input(m, state, db)


@router.callback_query(F.data.startswith("st:catlim:limit_remove:"))
async def catlim_limit_remove_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await _lang(db, c.from_user.id)
    category_id = int((c.data or "").split(":")[-1])
    row = await get_category(db, c.from_user.id, category_id)
    if not row:
        await _safe_answer(c, _T(lang, "not_found"), show_alert=True)
        return
    current = await get_category_budget(db, c.from_user.id, month_key(), category_id)
    data = await state.get_data()
    await state.set_state(None)
    await state.update_data(cat_id=category_id, catlim_kind=row[3], catlim_return_to=data.get("catlim_return_to") or "st:catlim:limits")
    await _clear_prompt(c, state)
    await _render(
        c,
        state,
        _T(lang, "remove_limit_confirm", name=_label(row[1], row[2], lang), current=_fmt_money(current)),
        _confirm_kb(yes_cb=f"st:catlim:limit_remove_confirm:{category_id}", back_cb=f"st:catlim:item:{category_id}", lang=lang, remove_limit=True),
    )
    await _safe_answer(c)


@router.callback_query(F.data.startswith("st:catlim:limit_remove_confirm:"))
async def catlim_limit_remove_confirm(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    category_id = int((c.data or "").split(":")[-1])
    lang = await _lang(db, c.from_user.id)
    await _remove_current_month_limit(db, c.from_user.id, category_id)
    await db.commit()
    await show_category_card(c, state, db, category_id=category_id, return_to=(await state.get_data()).get("catlim_return_to"))
    await _safe_answer(c, _T(lang, "done_limit_removed"))


@router.callback_query(F.data.startswith("st:catlim:delete:"))
async def catlim_delete_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_BUDGETS):
        await deny_feature_message(c, db, c.from_user.id)
        return
    lang = await _lang(db, c.from_user.id)
    category_id = int((c.data or "").split(":")[-1])
    row = await get_category(db, c.from_user.id, category_id)
    if not row:
        await _safe_answer(c, _T(lang, "not_found"), show_alert=True)
        return
    data = await state.get_data()
    await state.set_state(None)
    await state.update_data(cat_id=category_id, catlim_kind=row[3], catlim_return_to=data.get("catlim_return_to") or f"st:catlim:list:{row[3]}")
    await _clear_prompt(c, state)
    await _render(
        c,
        state,
        _T(lang, "delete_confirm", name=_label(row[1], row[2], lang)),
        _confirm_kb(yes_cb=f"st:catlim:delete_confirm:{category_id}", back_cb=f"st:catlim:item:{category_id}", lang=lang),
    )
    await _safe_answer(c)


@router.callback_query(F.data.startswith("st:catlim:delete_confirm:"))
async def catlim_delete_confirm(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    category_id = int((c.data or "").split(":")[-1])
    lang = await _lang(db, c.from_user.id)
    row = await get_category(db, c.from_user.id, category_id)
    if not row:
        await _safe_answer(c, _T(lang, "not_found"), show_alert=True)
        return
    kind = row[3]
    await _remove_current_month_limit(db, c.from_user.id, category_id)
    await archive_category(db, c.from_user.id, category_id, _now())
    await db.commit()
    await show_category_list(c, state, db, kind=kind)
    await _safe_answer(c, _T(lang, "done_delete"))


@router.callback_query(F.data.startswith("st:catlim:emoji:"))
async def catlim_emoji_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    if not await can_use_feature(db, c.from_user.id, FEATURE_BUDGETS):
        await deny_feature_message(c, db, c.from_user.id)
        return
    lang = await _lang(db, c.from_user.id)
    category_id = int((c.data or "").split(":")[-1])
    data = await state.get_data()
    await _start_input(
        c,
        state,
        screen_text=_T(lang, "emoji_title"),
        prompt_text=_T(lang, "input_hint_cat"),
        next_state=CategoriesFlow.emoji,
        extra={
            "cat_id": category_id,
            "catlim_after": "card",
            "catlim_return_to": data.get("catlim_return_to") or f"st:catlim:list:{data.get('catlim_kind', 'expense')}",
        },
    )
    await _safe_answer(c)


@router.message(CategoriesFlow.emoji, F.text, CatLimFlowFilter())
async def catlim_emoji_text(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    await consume_user_input(m, state)
    lang = await _lang(db, m.from_user.id)
    data = await state.get_data()
    category_id = int(data.get("cat_id") or 0)
    row = await get_category(db, m.from_user.id, category_id)
    if not row:
        await cancel_to_main_menu(m, state, db)
        return
    em = (m.text or "").strip()
    if em == "-":
        em = None
    if em and len(em) > 4:
        await m.answer(_T(lang, "emoji_error"), reply_markup=minimized_menu_kb(lang), parse_mode=PARSE_MODE)
        return
    await set_category_emoji(db, m.from_user.id, category_id, em, _now())
    await db.commit()
    await m.answer(_T(lang, "done_emoji"), parse_mode=PARSE_MODE)
    await state.set_state(None)
    await _return_after_input(m, state, db)
