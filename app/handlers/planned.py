from __future__ import annotations
from app.domain.services.access_service import FEATURE_PLANNED, can_use_feature

from datetime import datetime, timezone, timedelta
from html import escape

import aiosqlite
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.repositories.accounts_repo import list_accounts
from app.db.repositories.categories_repo import list_categories
from app.db.repositories.planned_repo import (
    ensure_schema,
    create_planned,
    list_planned,
    get_planned,
    set_planned_archived,
    mark_planned_done,
    update_planned_date,
    mark_planned_reminded,
)
from app.db.repositories.settings_repo import get_lang
from app.db.repositories.tx_repo import create_tx, apply_expense_income
from app.fsm.states import PlannedFlow
from app.handlers.common import deny_feature_message,  cancel_to_main_menu, is_cancel_text
from app.ui.i18n import text_matches_key, t
from app.ui.keyboards import main_menu, cancel_kb
from app.domain.services.ai_consultant_service import build_section_hint

router = Router()
PARSE_MODE = "HTML"
PLANNED_SCOPE = "planned_section"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fmt_money(value: int) -> str:
    s = str(abs(int(value)))
    parts: list[str] = []
    while s:
        parts.append(s[-3:])
        s = s[:-3]
    out = " ".join(reversed(parts)) if parts else "0"
    return f"{'-' if value < 0 else ''}{out} тг"


def _chat_and_bot(target: Message | CallbackQuery):
    if isinstance(target, CallbackQuery):
        return target.bot, target.message.chat.id
    return target.bot, target.chat.id


async def _safe_delete_message(bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(message_id))
    except Exception:
        pass


async def _safe_remove_markup(bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=int(message_id),
            reply_markup=None,
        )
    except Exception:
        pass


async def _clear_prompt(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prompt_id = data.get("prompt_message_id")
    bot, chat_id = _chat_and_bot(target)
    await _safe_delete_message(bot, chat_id, prompt_id)
    await state.update_data(prompt_message_id=None)


async def _start_planned_session(state: FSMContext):
    await state.update_data(ui_scope=PLANNED_SCOPE)


async def _ensure_planned_reply_keyboard(target: Message | CallbackQuery, state: FSMContext, lang: str):
    data = await state.get_data()
    if data.get("planned_reply_message_id"):
        return
    sender = target.message.answer if isinstance(target, CallbackQuery) else target.answer
    sent = await sender("Режим планирования открыт.", reply_markup=cancel_kb(lang), disable_notification=True)
    extra_ids = data.get("extra_prompt_message_ids") or []
    if not isinstance(extra_ids, list):
        extra_ids = [extra_ids]
    extra_ids = [x for x in extra_ids if x]
    extra_ids.append(sent.message_id)
    await state.update_data(planned_reply_message_id=sent.message_id, extra_prompt_message_ids=extra_ids)


async def _reset_flow_ui(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bot, chat_id = _chat_and_bot(target)

    await _safe_delete_message(bot, chat_id, data.get("prompt_message_id"))
    await _safe_remove_markup(bot, chat_id, data.get("flow_message_id"))

    if isinstance(target, CallbackQuery):
        await _safe_remove_markup(bot, chat_id, target.message.message_id)

    await state.update_data(prompt_message_id=None, flow_message_id=None)


async def _render_screen(
    target: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    reply_markup=None,
):
    await _start_planned_session(state)
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")
    bot, chat_id = _chat_and_bot(target)
    current_message = None if isinstance(target, Message) else target.message

    if isinstance(target, Message):
        if flow_message_id:
            await _safe_remove_markup(bot, chat_id, flow_message_id)
        sent = await target.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        await state.update_data(flow_message_id=sent.message_id)
        return

    if flow_message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(flow_message_id),
                text=text,
                reply_markup=reply_markup,
                parse_mode=PARSE_MODE,
            )
            await _ensure_planned_reply_keyboard(target, state, (await state.get_data()).get("lang") or "ru")
            return
        except Exception:
            pass

    if current_message is not None:
        try:
            await current_message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=PARSE_MODE,
            )
            await state.update_data(flow_message_id=current_message.message_id)
            await _ensure_planned_reply_keyboard(target, state, (await state.get_data()).get("lang") or "ru")
            return
        except Exception:
            pass

    sent = await target.message.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    await state.update_data(flow_message_id=sent.message_id)
    await _ensure_planned_reply_keyboard(target, state, (await state.get_data()).get("lang") or "ru")


async def _show_input_prompt(
    target: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    lang: str,
):
    await _clear_prompt(target, state)
    sent = await (
        target.message.answer(text, reply_markup=cancel_kb(lang), parse_mode=PARSE_MODE)
        if isinstance(target, CallbackQuery)
        else target.answer(text, reply_markup=cancel_kb(lang), parse_mode=PARSE_MODE)
    )
    await state.update_data(prompt_message_id=sent.message_id)


def planned_menu_kb(lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(
        text="➕ Добавить" if lang == "ru" else ("➕ Add" if lang == "en" else "➕ Қосу"),
        callback_data="pl:add",
    )
    kb.button(
        text="📋 Активные" if lang == "ru" else ("📋 Active" if lang == "en" else "📋 Белсенді"),
        callback_data="pl:list",
    )
    kb.button(
        text="🗄 Архив" if lang == "ru" else ("🗄 Archive" if lang == "en" else "🗄 Архив"),
        callback_data="pl:archived",
    )
    kb.button(text=t(lang, "BTN_BACK"), callback_data="hub:planning")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def planned_kind_kb(lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(
        text="➖ Расход" if lang == "ru" else ("➖ Expense" if lang == "en" else "➖ Шығыс"),
        callback_data="pl:kind:expense",
    )
    kb.button(
        text="➕ Доход" if lang == "ru" else ("➕ Income" if lang == "en" else "➕ Кіріс"),
        callback_data="pl:kind:income",
    )
    kb.button(text=t(lang, "BTN_BACK"), callback_data="pl:menu")
    kb.adjust(2, 1)
    return kb.as_markup()


def planned_importance_kb(lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(
        text="🧱 Обязательная" if lang == "ru" else ("🧱 Required" if lang == "en" else "🧱 Міндетті"),
        callback_data="pl:req:1",
    )
    kb.button(
        text="🫧 Гибкая" if lang == "ru" else ("🫧 Flexible" if lang == "en" else "🫧 Икемді"),
        callback_data="pl:req:0",
    )
    kb.button(text=t(lang, "BTN_BACK"), callback_data="pl:add")
    kb.adjust(1)
    return kb.as_markup()


def planned_rows_kb(rows, archived: bool, lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for row in rows:
        sign = "+" if str(row["kind"]) == "income" else "−"
        marker = "🧱 " if int(row["is_required"] or 0) == 1 else "🫧 "
        kb.button(
            text=f"{marker}{sign} {row['title']} — {fmt_money(int(row['amount']))}",
            callback_data=f"pl:item:{row['id']}",
        )
    kb.button(text=t(lang, "BTN_BACK"), callback_data="pl:menu")
    kb.adjust(1)
    return kb.as_markup()


def planned_actions_kb(item_id: int, archived: bool, lang: str = "ru", back_cb: str | None = None):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    if archived:
        kb.button(
            text="♻️ Восстановить" if lang == "ru" else ("♻️ Restore" if lang == "en" else "♻️ Қалпына келтіру"),
            callback_data=f"pl:restore:{item_id}",
        )
        back = back_cb or "pl:archived"
    else:
        kb.button(
            text="✅ Проведено" if lang == "ru" else ("✅ Mark done" if lang == "en" else "✅ Өтті деп белгілеу"),
            callback_data=f"pl:done:{item_id}",
        )
        kb.button(
            text="📅 Перенести дату" if lang == "ru" else ("📅 Move date" if lang == "en" else "📅 Күнін жылжыту"),
            callback_data=f"pl:move:{item_id}",
        )
        kb.button(
            text="🗂 В архив" if lang == "ru" else ("🗂 Archive" if lang == "en" else "🗂 Архив"),
            callback_data=f"pl:archive:{item_id}",
        )
        back = back_cb or "pl:list"
    kb.button(text=t(lang, "BTN_BACK"), callback_data=back)
    kb.adjust(1)
    return kb.as_markup()




def planned_categories_pick_kb(cats, lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for cid, name, emoji in cats:
        label = f"{emoji + ' ' if emoji else ''}{name}"
        kb.button(text=label, callback_data=f"pl:cat:{cid}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="pl:step:importance")
    kb.adjust(2)
    return kb.as_markup()


def planned_accounts_pick_kb(accounts, lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for acc_id, name, bal, arch in accounts:
        if arch:
            continue
        kb.button(text=f"{name} ({bal})", callback_data=f"pl:acc:{acc_id}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="pl:step:category")
    kb.adjust(1)
    return kb.as_markup()


def planned_reminder_actions_kb(item_id: int, lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Проведено" if lang == "ru" else ("✅ Done" if lang == "en" else "✅ Өтті"), callback_data=f"pl:done:{item_id}")
    kb.button(text="🕒 Завтра" if lang == "ru" else ("🕒 Tomorrow" if lang == "en" else "🕒 Ертең"), callback_data=f"pl:remindsnooze:{item_id}")
    kb.button(text="🔗 Уже внёс вручную" if lang == "ru" else ("🔗 Already added manually" if lang == "en" else "🔗 Қолмен енгізіп қойдым"), callback_data=f"pl:remindmanual:{item_id}")
    kb.button(text="📂 Детали" if lang == "ru" else ("📂 Details" if lang == "en" else "📂 Толығырақ"), callback_data=f"pl:remdetail:{item_id}")
    kb.adjust(2, 2)
    return kb.as_markup()


async def _menu_text(db, user_id: int, lang: str) -> str:
    await ensure_schema(db)
    active = await list_planned(db, user_id, archived=False)
    archived = await list_planned(db, user_id, archived=True)
    nearest = active[0] if active else None

    lines = [
        "🗓 <b>Планируемые платежи</b>"
        if lang == "ru"
        else ("🗓 <b>Planned payments</b>" if lang == "en" else "🗓 <b>Жоспарланған операциялар</b>"),
        "",
        "Разовые будущие доходы и расходы для прогноза."
        if lang == "ru"
        else (
            "Future one-time income and expenses for forecast."
            if lang == "en"
            else "Болжамға арналған бір реттік болашақ кірістер мен шығыстар."
        ),
        f"Активных: <b>{len(active)}</b>"
        if lang == "ru"
        else (f"Active: <b>{len(active)}</b>" if lang == "en" else f"Белсенді: <b>{len(active)}</b>"),
    ]

    if archived:
        lines.append(
            f"В архиве: <b>{len(archived)}</b>"
            if lang == "ru"
            else (f"Archived: <b>{len(archived)}</b>" if lang == "en" else f"Архивте: <b>{len(archived)}</b>")
        )

    if nearest:
        nearest_kind = str(nearest["kind"] or "expense")

        kind_ru = "доход" if nearest_kind == "income" else "расход"
        kind_en = "income" if nearest_kind == "income" else "expense"
        kind_kz = "кіріс" if nearest_kind == "income" else "шығыс"

        lines.extend(
            [
                "",
                "Ближайшая:" if lang == "ru" else ("Nearest:" if lang == "en" else "Жақын арада:"),
                (
                    f"• <b>{escape(str(nearest['title']))}</b> — {fmt_money(int(nearest['amount']))} — {nearest['planned_date']} — {kind_ru}"
                    if lang == "ru"
                    else (
                        f"• <b>{escape(str(nearest['title']))}</b> — {fmt_money(int(nearest['amount']))} — {nearest['planned_date']} — {kind_en}"
                        if lang == "en"
                        else f"• <b>{escape(str(nearest['title']))}</b> — {fmt_money(int(nearest['amount']))} — {nearest['planned_date']} — {kind_kz}"
                    )
                ),
            ]
        )

    hint = await build_section_hint(db, user_id, "planned", lang)
    if hint:
        lines += ["", hint]

    return "\n".join(lines)


async def _show_menu(target: Message | CallbackQuery, state: FSMContext, db):
    lang = await get_lang(db, target.from_user.id)
    await _clear_prompt(target, state)
    await state.set_state(None)
    await _render_screen(
        target,
        state,
        await _menu_text(db, target.from_user.id, lang),
        reply_markup=planned_menu_kb(lang),
    )


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_PLANNED"))
async def planned_entry(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, m.from_user.id, FEATURE_PLANNED):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await ensure_schema(db)
    await _show_menu(m, state, db)


@router.callback_query(F.data == "pl:menu")
async def planned_menu_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _show_menu(c, state, db)
    await c.answer()



@router.callback_query(F.data == "pl:list")
async def planned_list(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    rows = await list_planned(db, c.from_user.id, False)
    text = (
        "📋 <b>Активные планируемые операции</b>"
        if lang == "ru"
        else ("📋 <b>Active planned operations</b>" if lang == "en" else "📋 <b>Белсенді жоспарланған операциялар</b>")
    )
    if not rows:
        text += "\n\n" + ("Пока пусто." if lang == "ru" else ("No items yet." if lang == "en" else "Әзірге бос."))
    await _render_screen(c, state, text, reply_markup=planned_rows_kb(rows, False, lang))
    await c.answer()


@router.callback_query(F.data == "pl:archived")
async def planned_archived(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    rows = await list_planned(db, c.from_user.id, True)
    text = (
        "🗄 <b>Архив планируемых операций</b>"
        if lang == "ru"
        else ("🗄 <b>Planned archive</b>" if lang == "en" else "🗄 <b>Жоспарланған операциялар архиві</b>")
    )
    if not rows:
        text += "\n\n" + (
            "Архив пуст." if lang == "ru" else ("Archive is empty." if lang == "en" else "Архив бос.")
        )
    await _render_screen(c, state, text, reply_markup=planned_rows_kb(rows, True, lang))
    await c.answer()


@router.callback_query(F.data == "pl:add")
async def planned_add(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    await _reset_flow_ui(c, state)
    await state.set_state(PlannedFlow.kind)
    await _render_screen(
        c,
        state,
        "🗓 <b>Новая планируемая операция</b>\n\nВыбери тип."
        if lang == "ru"
        else (
            "🗓 <b>New planned operation</b>\n\nChoose type."
            if lang == "en"
            else "🗓 <b>Жаңа жоспарланған операция</b>\n\nТүрін таңдаңыз."
        ),
        reply_markup=planned_kind_kb(lang),
    )
    await c.answer()


@router.callback_query(F.data.startswith("pl:kind:"))
async def planned_kind(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    kind = c.data.split(":")[-1]
    lang = await get_lang(db, c.from_user.id)

    await state.update_data(pl_kind=kind)
    await state.set_state(PlannedFlow.title)

    await _render_screen(
        c,
        state,
        "Введи название операции." if lang == "ru" else ("Enter title." if lang == "en" else "Операция атауын енгізіңіз."),
    )
    await _show_input_prompt(
        c,
        state,
        "Пример: <code>Реклама 15 апреля</code>"
        if lang == "ru"
        else ("Example: <code>Laptop on 15 Apr</code>" if lang == "en" else "Мысал: <code>15 сәуір жарнама</code>"),
        lang,
    )
    await c.answer()


@router.message(PlannedFlow.title, F.text)
async def planned_title(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    title = (m.text or "").strip()
    if len(title) < 2 or len(title) > 60:
        await m.answer("Название должно быть от 2 до 60 символов.")
        return

    lang = await get_lang(db, m.from_user.id)
    await state.update_data(pl_title=title)
    await state.set_state(PlannedFlow.amount)
    await _show_input_prompt(m, state, "Введи сумму. Пример: <code>50000</code>", lang)


@router.message(PlannedFlow.amount, F.text)
async def planned_amount(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    raw = (m.text or "").strip().replace(" ", "")
    if not raw.isdigit():
        await m.answer("Нужны только цифры.")
        return

    await state.update_data(pl_amount=int(raw))
    lang = await get_lang(db, m.from_user.id)
    await state.set_state(PlannedFlow.importance)
    await _render_screen(
        m,
        state,
        "Это обязательная операция или гибкая?"
        if lang == "ru"
        else ("Is it required or flexible?" if lang == "en" else "Бұл міндетті ме әлде икемді ме?"),
        reply_markup=planned_importance_kb(lang),
    )


@router.callback_query(F.data.startswith("pl:req:"))
async def planned_importance(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    is_required = int(c.data.split(":")[-1])
    await state.update_data(pl_required=is_required)

    kind = (await state.get_data()).get("pl_kind", "expense")
    cats = await list_categories(db, c.from_user.id, kind)
    lang = await get_lang(db, c.from_user.id)

    await state.set_state(PlannedFlow.category)
    await _render_screen(
        c,
        state,
        "Выбери категорию." if lang == "ru" else ("Choose category." if lang == "en" else "Санатты таңдаңыз."),
        reply_markup=planned_categories_pick_kb(cats, lang),
    )
    await c.answer()


@router.callback_query(F.data == "pl:step:importance")
async def planned_step_importance(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    await state.set_state(PlannedFlow.importance)
    await _render_screen(
        c,
        state,
        "Это обязательная операция или гибкая?"
        if lang == "ru"
        else ("Is it required or flexible?" if lang == "en" else "Бұл міндетті ме әлде икемді ме?"),
        reply_markup=planned_importance_kb(lang),
    )
    await c.answer()


@router.callback_query(F.data == "pl:step:category")
async def planned_step_category(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    data = await state.get_data()
    kind = data.get("pl_kind", "expense")
    cats = await list_categories(db, c.from_user.id, kind)
    lang = await get_lang(db, c.from_user.id)
    await state.set_state(PlannedFlow.category)
    await _render_screen(
        c,
        state,
        "Выбери категорию." if lang == "ru" else ("Choose category." if lang == "en" else "Санатты таңдаңыз."),
        reply_markup=planned_categories_pick_kb(cats, lang),
    )
    await c.answer()


@router.callback_query(F.data.startswith("pl:cat:"))
async def planned_cat(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    cid = int(c.data.split(":")[-1])
    await state.update_data(pl_category_id=cid)

    accs = await list_accounts(db, c.from_user.id)
    lang = await get_lang(db, c.from_user.id)

    await state.set_state(PlannedFlow.account)
    await _render_screen(
        c,
        state,
        "Выбери счёт." if lang == "ru" else ("Choose account." if lang == "en" else "Шотты таңдаңыз."),
        reply_markup=planned_accounts_pick_kb(accs, lang),
    )
    await c.answer()


@router.callback_query(F.data.startswith("pl:acc:"))
async def planned_acc(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    aid = int(c.data.split(":")[-1])
    lang = await get_lang(db, c.from_user.id)

    await state.update_data(pl_account_id=aid)
    await state.set_state(PlannedFlow.date)

    await _render_screen(
        c,
        state,
        "Введи дату в формате YYYY-MM-DD."
        if lang == "ru"
        else ("Enter date in YYYY-MM-DD." if lang == "en" else "Күнді YYYY-MM-DD форматында енгізіңіз."),
    )
    await _show_input_prompt(c, state, "Пример: <code>2026-04-15</code>", lang)
    await c.answer()


@router.message(PlannedFlow.date, F.text)
async def planned_date(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    raw = (m.text or "").strip()
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except Exception:
        await m.answer("Нужна дата в формате YYYY-MM-DD.")
        return

    lang = await get_lang(db, m.from_user.id)
    await state.update_data(pl_date=raw)
    await state.set_state(PlannedFlow.comment)
    await _show_input_prompt(m, state, "Комментарий или <code>-</code>, чтобы пропустить.", lang)


@router.message(PlannedFlow.comment, F.text)
async def planned_comment(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    data = await state.get_data()
    comment = (m.text or "").strip()
    comment = None if comment == "-" else comment

    try:
        await create_planned(
            db,
            m.from_user.id,
            data["pl_kind"],
            data["pl_title"],
            int(data["pl_amount"]),
            int(data["pl_category_id"]),
            int(data["pl_account_id"]),
            data["pl_date"],
            comment,
            now_iso(),
            int(data.get("pl_required", 1)),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await _show_menu(m, state, db)
    lang = await get_lang(db, m.from_user.id)
    await m.answer(
        "✅ <b>Планируемая операция сохранена</b>"
        if lang == "ru"
        else (
            "✅ <b>Planned operation saved</b>"
            if lang == "en"
            else "✅ <b>Жоспарланған операция сақталды</b>"
        ),
        parse_mode=PARSE_MODE,
    )


@router.callback_query(F.data.startswith("pl:item:"))
async def planned_item(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    item_id = int(c.data.split(":")[-1])
    row = await get_planned(db, c.from_user.id, item_id)
    lang = await get_lang(db, c.from_user.id)

    if not row:
        await c.answer("Не найдено", show_alert=True)
        return

    sign = "+" if str(row["kind"]) == "income" else "−"
    required = "Обязательная" if int(row["is_required"] or 0) == 1 else "Гибкая"

    lines = [
        f"🗓 <b>{escape(str(row['title']))}</b>",
        "",
        f"• Тип: <b>{'Доход' if str(row['kind']) == 'income' else 'Расход'}</b>",
        f"• Сумма: <b>{sign}{fmt_money(int(row['amount']))}</b>",
        f"• Дата: <b>{row['planned_date']}</b>",
        f"• Важность: <b>{required}</b>",
        f"• Категория: <b>{escape(str(row['category_name']))}</b>",
        f"• Счёт: <b>{escape(str(row['account_name']))}</b>",
    ]

    if row["comment"]:
        lines.append(f"• Комментарий: <b>{escape(str(row['comment']))}</b>")

    await _render_screen(
        c,
        state,
        "\n".join(lines),
        reply_markup=planned_actions_kb(item_id, bool(row["is_archived"]), lang),
    )
    await c.answer()




@router.callback_query(F.data.startswith("pl:remdetail:"))
async def planned_reminder_detail(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    item_id = int(c.data.split(":")[-1])
    row = await get_planned(db, c.from_user.id, item_id)
    lang = await get_lang(db, c.from_user.id)

    if not row:
        await c.answer("Не найдено", show_alert=True)
        return

    sign = "+" if str(row["kind"]) == "income" else "−"
    required = "Обязательная" if int(row["is_required"] or 0) == 1 else "Гибкая"

    lines = [
        f"🗓 <b>{escape(str(row['title']))}</b>",
        "",
        f"• Тип: <b>{'Доход' if str(row['kind']) == 'income' else 'Расход'}</b>",
        f"• Сумма: <b>{sign}{fmt_money(int(row['amount']))}</b>",
        f"• Дата: <b>{row['planned_date']}</b>",
        f"• Важность: <b>{required}</b>",
        f"• Категория: <b>{escape(str(row['category_name']))}</b>",
        f"• Счёт: <b>{escape(str(row['account_name']))}</b>",
    ]

    if row["comment"]:
        lines.append(f"• Комментарий: <b>{escape(str(row['comment']))}</b>")

    await _render_screen(c, state, "\n".join(lines), reply_markup=planned_actions_kb(item_id, bool(row["is_archived"]), lang, back_cb=f"pl:remcard:{item_id}"))
    await c.answer()


@router.callback_query(F.data.startswith("pl:remcard:"))
async def planned_reminder_card(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    item_id = int(c.data.split(":")[-1])
    row = await get_planned(db, c.from_user.id, item_id)
    lang = await get_lang(db, c.from_user.id)

    if not row:
        await c.answer("Не найдено", show_alert=True)
        return

    sign = "+" if str(row["kind"]) == "income" else "−"
    required = "Обязательная" if int(row["is_required"] or 0) == 1 else "Гибкая"

    lines = [
        f"🗓 <b>{escape(str(row['title']))}</b>",
        "",
        ("Напоминание по планируемой операции." if lang == "ru" else ("Planned operation reminder." if lang == "en" else "Жоспарланған операция туралы еске салу.")),
        f"• Тип: <b>{'Доход' if str(row['kind']) == 'income' else 'Расход'}</b>",
        f"• Сумма: <b>{sign}{fmt_money(int(row['amount']))}</b>",
        f"• Дата: <b>{row['planned_date']}</b>",
        f"• Важность: <b>{required}</b>",
        f"• Категория: <b>{escape(str(row['category_name']))}</b>",
        f"• Счёт: <b>{escape(str(row['account_name']))}</b>",
    ]

    if row["comment"]:
        lines.append(f"• Комментарий: <b>{escape(str(row['comment']))}</b>")

    await _render_screen(c, state, '\n'.join(lines), reply_markup=planned_reminder_actions_kb(item_id, lang))
    await c.answer()


@router.callback_query(F.data.startswith("pl:remindsnooze:"))
async def planned_snooze_from_reminder(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    item_id = int(c.data.split(":")[-1])
    tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    try:
        await mark_planned_reminded(db, c.from_user.id, item_id, tomorrow)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    lang = await get_lang(db, c.from_user.id)
    text = (
        "🕒 <b>Напомню завтра</b>\\nСегодня больше не трогаю эту операцию."
        if lang == "ru" else
        ("🕒 <b>I will remind you tomorrow</b>\\nI will not bother you about this operation again today." if lang == "en" else "🕒 <b>Ертең еске саламын</b>\\nБүгін бұл операция туралы қайта мазаламаймын.")
    )
    try:
        await c.message.edit_text(text, parse_mode=PARSE_MODE)
    except Exception:
        await c.message.answer(text, parse_mode=PARSE_MODE)
    await c.answer()


@router.callback_query(F.data.startswith("pl:remindmanual:"))
async def planned_manual_from_reminder(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    item_id = int(c.data.split(":")[-1])
    row = await mark_planned_done(db, c.from_user.id, item_id, now_iso())
    if not row:
        await c.answer("Не найдено", show_alert=True)
        return
    await db.commit()
    lang = await get_lang(db, c.from_user.id)
    text = (
        "🔗 <b>Отмечено как уже внесённое вручную</b>\\nНовый факт не создан, операция закрыта без дубля."
        if lang == "ru" else
        ("🔗 <b>Marked as already added manually</b>\\nNo new record was created, the operation was closed without duplicates." if lang == "en" else "🔗 <b>Қолмен бұрын енгізілген деп белгіленді</b>\\nЖаңа жазба жасалмады, операция дубльсіз жабылды.")
    )
    try:
        await c.message.edit_text(text, parse_mode=PARSE_MODE)
    except Exception:
        await c.message.answer(text, parse_mode=PARSE_MODE)
    await c.answer()

@router.callback_query(F.data.startswith("pl:archive:"))
async def planned_archive(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    item_id = int(c.data.split(":")[-1])
    await set_planned_archived(db, c.from_user.id, item_id, True, now_iso())
    await db.commit()
    await planned_list(c, state, db)


@router.callback_query(F.data.startswith("pl:restore:"))
async def planned_restore(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    item_id = int(c.data.split(":")[-1])
    await set_planned_archived(db, c.from_user.id, item_id, False, now_iso())
    await db.commit()
    await planned_archived(c, state, db)


@router.callback_query(F.data.startswith("pl:move:"))
async def planned_move(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _reset_flow_ui(c, state)

    item_id = int(c.data.split(":")[-1])
    row = await get_planned(db, c.from_user.id, item_id)
    if not row:
        await c.answer("Не найдено", show_alert=True)
        return

    lang = await get_lang(db, c.from_user.id)
    await state.update_data(pl_move_id=item_id)
    await state.set_state(PlannedFlow.move_date)

    await _render_screen(
        c,
        state,
        "Введи новую дату в формате YYYY-MM-DD."
        if lang == "ru"
        else ("Enter new date in YYYY-MM-DD." if lang == "en" else "Жаңа күнді YYYY-MM-DD форматында енгізіңіз."),
    )
    await _show_input_prompt(c, state, f"Сейчас стоит: <code>{row['planned_date']}</code>", lang)
    await c.answer()


@router.message(PlannedFlow.move_date, F.text)
async def planned_move_date(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    raw = (m.text or "").strip()
    try:
        datetime.strptime(raw, "%Y-%m-%d")
    except Exception:
        await m.answer("Нужна дата в формате YYYY-MM-DD.")
        return

    item_id = (await state.get_data()).get("pl_move_id")
    if not item_id:
        await cancel_to_main_menu(m, state, db)
        return

    try:
        await update_planned_date(db, m.from_user.id, int(item_id), raw, now_iso())
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await m.answer("✅ <b>Дата операции обновлена</b>", parse_mode=PARSE_MODE)
    await cancel_to_main_menu(m, state, db)
    return


@router.callback_query(F.data.startswith("pl:done:"))
async def planned_done(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    item_id = int(c.data.split(":")[-1])
    row = await mark_planned_done(db, c.from_user.id, item_id, now_iso())
    if not row:
        await c.answer("Не найдено", show_alert=True)
        return

    amount = int(row["amount"] or 0)
    kind = str(row["kind"] or "expense")
    acc = int(row["account_id"])
    cat = int(row["category_id"])
    note = str(row["comment"] or row["title"] or "") or None

    sign_amount = amount if kind == "income" else -amount
    tx_id = await create_tx(db, c.from_user.id, now_iso(), kind, sign_amount, acc, cat, note, now_iso())
    await apply_expense_income(db, c.from_user.id, tx_id, sign_amount, acc)
    await db.commit()

    await _render_screen(
        c,
        state,
        "✅ <b>Операция проведена</b>\n\nФакт создан и перенесён в историю.",
    )
    await c.answer()
