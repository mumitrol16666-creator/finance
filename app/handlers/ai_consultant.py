from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import aiosqlite
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.db.repositories.ai_context_repo import save_ai_context_note
from app.db.repositories.settings_repo import (
    get_ai_usage,
    get_financial_goal,
    get_lang,
    get_timezone,
    set_ai_usage,
    set_financial_goal,
)
from app.domain.services.access_service import FEATURE_AI, can_use_feature
from app.domain.services.ai_consultant_service import build_ai_context
from app.domain.services.ai_llm_service import render_final_ai_question, render_final_ai_report
from app.fsm.states import AiConsultantFlow
from app.handlers.common import cancel_to_main_menu, deny_feature_message
from app.ui.i18n import text_matches_key, t
from app.ui.keyboards import (
    ai_consultant_kb,
    ai_question_actions_kb,
    ai_report_actions_kb,
    ai_report_period_kb,
    cancel_kb,
)

router = Router()
PARSE_MODE = "HTML"
AI_MONTHLY_LIMIT = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _current_month() -> str:
    return datetime.now().strftime("%Y-%m")


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


async def _collapse_ui(target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")
    prompt_message_id = data.get("prompt_message_id")
    bot = target.bot
    chat_id = target.chat.id if isinstance(target, Message) else target.message.chat.id
    await _safe_delete_message(bot, chat_id, prompt_message_id)
    await _safe_remove_markup(bot, chat_id, flow_message_id)
    await state.update_data(prompt_message_id=None, flow_message_id=None)


async def _render_screen(target: Message | CallbackQuery, state: FSMContext, text: str, *, reply_markup=None) -> None:
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")
    bot = target.bot
    chat_id = target.chat.id if isinstance(target, Message) else target.message.chat.id
    current_message = None if isinstance(target, Message) else target.message

    if flow_message_id:
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=int(flow_message_id), text=text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
            return
        except Exception:
            pass

    if current_message is not None:
        try:
            await current_message.edit_text(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
            await state.update_data(flow_message_id=current_message.message_id)
            return
        except Exception:
            pass

    sent = await (target.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE) if isinstance(target, Message) else target.message.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE))
    await state.update_data(flow_message_id=sent.message_id)


async def _show_prompt(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection, text: str) -> None:
    await _clear_prompt(target, state)
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")
    bot = target.bot
    chat_id = target.chat.id if isinstance(target, Message) else target.message.chat.id
    if flow_message_id:
        await _safe_remove_markup(bot, chat_id, flow_message_id)
    if isinstance(target, CallbackQuery):
        await _safe_remove_markup(bot, chat_id, target.message.message_id)
    lang = await get_lang(db, target.from_user.id)
    sent = await (target.answer(text, reply_markup=cancel_kb(lang), parse_mode=PARSE_MODE) if isinstance(target, Message) else target.message.answer(text, reply_markup=cancel_kb(lang), parse_mode=PARSE_MODE))
    await state.update_data(prompt_message_id=sent.message_id)


async def _ensure_limit(db: aiosqlite.Connection, user_id: int) -> tuple[int, str]:
    used, month = await get_ai_usage(db, user_id)
    current_month = _current_month()
    if month != current_month:
        used = 0
        await set_ai_usage(db, user_id, 0, current_month, _now_iso())
        await db.commit()
    return used, current_month


def _menu_text(lang: str, goal_text: str | None, used: int) -> str:
    left = max(0, AI_MONTHLY_LIMIT - used)
    title = t(lang, "AI_MENU_TITLE")
    goal_block = (
        f"<b>Цель</b>: <b>{goal_text}</b>"
        if goal_text
        else "<b>Цель</b>: не задана"
    )
    return (
        f"{title}\n\n"
        "Здесь можно сделать <b>полный разбор периода</b>, задать <b>конкретный вопрос по деньгам</b> "
        "или быстро <b>повысить точность анализа</b>.\n\n"
        f"{goal_block}\n"
        f"📊 Глубоких разборов в этом месяце осталось: <b>{left} из {AI_MONTHLY_LIMIT}</b>\n\n"
        "<b>Что выбрать</b>\n"
        "• <b>Получить разбор</b> — если нужен общий вывод по периоду\n"
        "• <b>Задать вопрос</b> — если у тебя одна конкретная финансовая задача\n"
        "• <b>Повысить точность</b> — если были незанесённые траты, разовые скачки или месяц был нетипичным"
    )


async def _open_menu(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    lang = await get_lang(db, target.from_user.id)
    goal = await get_financial_goal(db, target.from_user.id)
    used, _month = await _ensure_limit(db, target.from_user.id)
    await state.update_data(ui_scope="ai_consultant")
    await state.set_state(None)
    await _clear_prompt(target, state)
    await _render_screen(target, state, _menu_text(lang, goal, used), reply_markup=ai_consultant_kb(lang))


async def _animate_loading(c: CallbackQuery, state: FSMContext, steps: list[str]) -> None:
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id") or c.message.message_id
    for step in steps:
        try:
            await c.bot.edit_message_text(chat_id=c.message.chat.id, message_id=int(flow_message_id), text=step, parse_mode=PARSE_MODE)
        except Exception:
            pass
        await asyncio.sleep(0.25)




async def _open_report_picker(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    lang = await get_lang(db, target.from_user.id)
    text = (
        "<b>Формат AI-разбора</b>\n\n"
        "<b>Месяц</b> — основной сценарий для нормального вывода по тратам, целям и рискам.\n"
        "<b>Неделя</b> — быстрый разбор свежего отрезка.\n"
        "<b>День</b> — короткий локальный срез без глубокой картины."
    )
    await _render_screen(target, state, text, reply_markup=ai_report_period_kb(lang))


async def _enter_ai(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    await _collapse_ui(target, state)
    await state.clear()
    if isinstance(target, Message):
        try:
            await target.delete()
        except Exception:
            pass
    else:
        await target.answer()
    goal = await get_financial_goal(db, target.from_user.id)
    if goal:
        await _open_menu(target, state, db)
        return
    await state.update_data(ui_scope="ai_consultant")
    await state.set_state(AiConsultantFlow.waiting_goal)
    await _show_prompt(
        target,
        state,
        db,
        "<b>Сначала задай финансовую цель</b>\n\n"
        "Напиши её обычным текстом. Например:\n"
        "• накопить на ноутбук\n"
        "• сократить лишние траты\n"
        "• закрыть долг\n"
        "• накопить 600 000 тг на покупку",
    )


@router.callback_query(F.data == "ai:open")
async def ai_entry_from_reports(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_AI):
        await deny_feature_message(c, db, c.from_user.id)
        return
    await _enter_ai(c, state, db)


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_AI"))
async def ai_entry(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, m.from_user.id, FEATURE_AI):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await _enter_ai(m, state, db)


@router.callback_query(F.data == "ai:menu")
async def ai_menu_return(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _open_menu(c, state, db)
    await c.answer()


@router.callback_query(F.data == "ai:report:start")
async def ai_report_start(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    goal = await get_financial_goal(db, c.from_user.id)
    if not goal:
        await ai_goal_edit(c, state, db)
        return
    await state.update_data(ui_scope="ai_consultant")
    await state.set_state(None)
    await _clear_prompt(c, state)
    await _open_report_picker(c, state, db)
    await c.answer()


@router.callback_query(F.data == "ai:goal:edit")
async def ai_goal_edit(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await state.update_data(ui_scope="ai_consultant")
    await state.set_state(AiConsultantFlow.waiting_goal)
    await _show_prompt(c, state, db, "🎯 <b>Новая финансовая цель</b>\n\nНапиши цель обычным текстом. Можно сразу с суммой.")
    await c.answer()


@router.message(AiConsultantFlow.waiting_goal, F.text)
async def ai_goal_save(m: Message, state: FSMContext, db: aiosqlite.Connection):
    goal = (m.text or "").strip()
    if len(goal) < 4:
        await m.answer("Цель слишком короткая. Напиши нормально, что ты хочешь и желательно с суммой.", parse_mode=PARSE_MODE)
        return
    await set_financial_goal(db, m.from_user.id, goal, _now_iso())
    await db.commit()
    await _open_menu(m, state, db)


@router.callback_query(F.data == "ai:clarify")
async def ai_clarify(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await state.update_data(ui_scope="ai_consultant")
    await state.set_state(AiConsultantFlow.waiting_context_note)
    await _show_prompt(
        c,
        state,
        db,
        "<b>Уточнение для AI</b>\n\nКоротко напиши одним сообщением:\n• были ли незанесённые траты или доходы\n• был ли месяц типичным\n• были ли разовые крупные операции\n• всё ли обязательное внесено",
    )
    await c.answer()


@router.message(AiConsultantFlow.waiting_context_note, F.text)
async def ai_clarify_save(m: Message, state: FSMContext, db: aiosqlite.Connection):
    content = (m.text or "").strip()
    if len(content) < 8:
        await m.answer("Слишком коротко. Нужна хотя бы короткая пометка, что именно может искажать разбор.", parse_mode=PARSE_MODE)
        return
    await save_ai_context_note(db, m.from_user.id, note_type="report_clarification", period_kind="month", content=content[:2000], created_at=_now_iso())
    await db.commit()
    await state.set_state(None)
    await _clear_prompt(m, state)
    lang = await get_lang(db, m.from_user.id)
    await _render_screen(
        m,
        state,
        "✅ <b>Уточнение сохранено</b>\n\nТеперь AI будет учитывать эту пометку в следующем разборе или ответе. Можешь сразу вернуться к разбору месяца или задать вопрос.",
        reply_markup=ai_report_actions_kb(lang, can_download=False),
    )


@router.callback_query(F.data == "ai:question")
async def ai_question_entry(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await state.update_data(ui_scope="ai_consultant")
    await state.set_state(AiConsultantFlow.waiting_question)
    await _show_prompt(c, state, db, "<b>Вопрос к AI</b>\n\nНапиши вопрос по своим финансам. Например:\n• смогу ли я накопить на велосипед за 4 месяца\n• тянут ли мои траты покупку на 150 000 тг\n• что мне сейчас важнее: гасить долг или копить")
    await c.answer()


@router.message(AiConsultantFlow.waiting_question, F.text)
async def ai_question_answer(m: Message, state: FSMContext, db: aiosqlite.Connection):
    question = (m.text or "").strip()
    if len(question) < 6:
        await m.answer("Вопрос слишком короткий. Нужен нормальный запрос, чтобы AI понял задачу, а не гадал.", parse_mode=PARSE_MODE)
        return
    tz_name = await get_timezone(db, m.from_user.id)
    goal = await get_financial_goal(db, m.from_user.id)
    context = await build_ai_context(db, m.from_user.id, tz_name, "month", goal)
    text = await render_final_ai_question(context, question)
    await state.set_state(None)
    await _clear_prompt(m, state)
    lang = await get_lang(db, m.from_user.id)
    await state.update_data(last_ai_question=question)
    await _render_screen(m, state, text, reply_markup=ai_question_actions_kb(lang))


@router.callback_query(F.data.startswith("ai:period:"))
async def ai_generate(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    kind = c.data.split(":")[-1]
    goal = await get_financial_goal(db, c.from_user.id)
    if not goal:
        await ai_goal_edit(c, state, db)
        return

    used, month = await _ensure_limit(db, c.from_user.id)
    if used >= AI_MONTHLY_LIMIT:
        await _open_menu(c, state, db)
        await c.answer("Лимит отчётов исчерпан", show_alert=True)
        return

    await state.update_data(ui_scope="ai_consultant")
    await _animate_loading(c, state, [
        "⚙️ <b>AI-консультант</b>\n\nПроверяю качество данных...",
        "⚙️ <b>AI-консультант</b>\n\nСобираю финансовый контекст...",
        "⚙️ <b>AI-консультант</b>\n\nГотовлю честный разбор...",
    ])

    tz_name = await get_timezone(db, c.from_user.id)
    context = await build_ai_context(db, c.from_user.id, tz_name, kind, goal)
    report_text, download_text = await render_final_ai_report(context)

    if (context.get("data_quality") or {}).get("sufficient_for_deep_report"):
        await set_ai_usage(db, c.from_user.id, used + 1, month, _now_iso())
        await db.commit()

    await state.update_data(last_ai_report_text=download_text, last_ai_kind=kind)
    lang = await get_lang(db, c.from_user.id)
    can_download = bool((context.get("data_quality") or {}).get("sufficient_for_deep_report"))
    await _render_screen(c, state, report_text, reply_markup=ai_report_actions_kb(lang, can_download=can_download))
    await c.answer()


@router.callback_query(F.data == "ai:download")
async def ai_download(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    data = await state.get_data()
    payload = data.get("last_ai_report_text")
    if not payload:
        await c.answer("Сначала получи разбор, чтобы было что скачивать", show_alert=True)
        return
    kind = data.get("last_ai_kind") or "report"
    buf = BufferedInputFile(str(payload).encode("utf-8"), filename=f"ai_report_{kind}.txt")
    await c.message.answer_document(buf, caption="📥 Полный AI-разбор")
    await c.answer()


@router.callback_query(F.data == "ai:back")
async def ai_back(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await cancel_to_main_menu(c, state, db)
