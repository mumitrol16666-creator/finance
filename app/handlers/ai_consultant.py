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


def _ai_t(lang: str, key: str, **kwargs) -> str:
    lang = (lang or "ru").lower()
    data = {
        "ru": {
            "goal_label": "Цель",
            "goal_none": "не задана",
            "menu_body": "Здесь можно сделать <b>полный разбор периода</b>, задать <b>конкретный вопрос по деньгам</b> или быстро <b>повысить точность анализа</b>.\n\n"
                         "<b>Цель</b>: <b>{goal}</b>\n"
                         "📊 Глубоких разборов в этом месяце осталось: <b>{left} из {limit}</b>\n\n"
                         "<b>Что выбрать</b>\n"
                         "• <b>Получить разбор</b> — если нужен общий вывод по периоду\n"
                         "• <b>Задать вопрос</b> — если у тебя одна конкретная финансовая задача\n"
                         "• <b>Повысить точность</b> — если были незанесённые траты, разовые скачки или месяц был нетипичным",
            "report_picker": "<b>Формат AI-разбора</b>\n\n"
                             "<b>Месяц</b> — основной сценарий для нормального вывода по тратам, целям и рискам.\n"
                             "<b>Неделя</b> — быстрый разбор свежего отрезка.\n"
                             "<b>День</b> — короткий локальный срез без глубокой картины.",
            "need_goal_first": "<b>Сначала задай финансовую цель</b>\n\n"
                               "Напиши её обычным текстом. Например:\n"
                               "• накопить на ноутбук\n"
                               "• сократить лишние траты\n"
                               "• закрыть долг\n"
                               "• накопить 600 000 тг на покупку",
            "goal_new_title": "🎯 <b>Новая финансовая цель</b>\n\nНапиши цель обычным текстом. Можно сразу с суммой.",
            "goal_too_short": "Цель слишком короткая. Напиши нормально, что ты хочешь и желательно с суммой.",
            "clarify_prompt": "<b>Уточнение для AI</b>\n\nКоротко напиши одним сообщением:\n"
                              "• были ли незанесённые траты или доходы\n"
                              "• был ли месяц типичным\n"
                              "• были ли разовые крупные операции\n"
                              "• всё ли обязательное внесено",
            "clarify_too_short": "Слишком коротко. Нужна хотя бы короткая пометка, что именно может искажать разбор.",
            "clarify_saved": "✅ <b>Уточнение сохранено</b>\n\nТеперь AI будет учитывать эту пометку в следующем разборе или ответе. Можешь сразу вернуться к разбору месяца или задать вопрос.",
            "question_prompt": "<b>Вопрос к AI</b>\n\nНапиши вопрос по своим финансам. Например:\n"
                               "• смогу ли я накопить на велосипед за 4 месяца\n"
                               "• тянут ли мои траты покупку на 150 000 тг\n"
                               "• что мне сейчас важнее: гасить долг или копить",
            "question_too_short": "Вопрос слишком короткий. Нужен нормальный запрос, чтобы AI понял задачу, а не гадал.",
            "limit_reached": "Лимит отчётов исчерпан",
            "loading_1": "⚙️ <b>AI-консультант</b>\n\nПроверяю качество данных...",
            "loading_2": "⚙️ <b>AI-консультант</b>\n\nСобираю финансовый контекст...",
            "loading_3": "⚙️ <b>AI-консультант</b>\n\nГотовлю честный разбор...",
            "download_first": "Сначала получи разбор, чтобы было что скачивать",
            "download_caption": "📥 Полный AI-разбор",
        },
        "en": {
            "goal_label": "Goal",
            "goal_none": "not set",
            "menu_body": "Here you can get a <b>full period analysis</b>, ask a <b>specific money question</b> or quickly <b>improve analysis accuracy</b>.\n\n"
                         "<b>Goal</b>: <b>{goal}</b>\n"
                         "📊 Deep reviews left this month: <b>{left} out of {limit}</b>\n\n"
                         "<b>What to choose</b>\n"
                         "• <b>Get report</b> — if you need a general summary for the period\n"
                         "• <b>Ask question</b> — if you have a specific financial question\n"
                         "• <b>Improve accuracy</b> — if you had unrecorded expenses, one-off spikes, or the month was atypical",
            "report_picker": "<b>AI Analysis Format</b>\n\n"
                             "<b>Month</b> — the main scenario for regular analysis of expenses, goals, and risks.\n"
                             "<b>Week</b> — a quick review of the recent period.\n"
                             "<b>Day</b> — a short local snapshot without a deep picture.",
            "need_goal_first": "<b>Set a financial goal first</b>\n\n"
                               "Write it in plain text. For example:\n"
                               "• save up for a laptop\n"
                               "• cut down on unnecessary spending\n"
                               "• pay off debt\n"
                               "• save 600,000 KZT for a purchase",
            "goal_new_title": "🎯 <b>New financial goal</b>\n\nWrite your goal in plain text. You can include the amount.",
            "goal_too_short": "The goal is too short. Please write what you want clearly, preferably with the amount.",
            "clarify_prompt": "<b>Clarification for AI</b>\n\nWrite briefly in one message:\n"
                              "• were there any unrecorded expenses or incomes\n"
                              "• was the month typical\n"
                              "• were there any one-off large transactions\n"
                              "• has everything mandatory been entered",
            "clarify_too_short": "Too short. Please provide at least a brief note on what exactly might skew the analysis.",
            "clarify_saved": "✅ <b>Clarification saved</b>\n\nNow AI will take this note into account in the next review or answer. You can return to the month review or ask a question.",
            "question_prompt": "<b>Question for AI</b>\n\nWrite a question about your finances. For example:\n"
                               "• will I be able to save up for a bike in 4 months\n"
                               "• can my budget afford a 150,000 KZT purchase\n"
                               "• what is more important for me now: pay off debt or save",
            "question_too_short": "The question is too short. Please provide a proper request so that AI can understand the task.",
            "limit_reached": "Reports limit reached",
            "loading_1": "⚙️ <b>AI Consultant</b>\n\nChecking data quality...",
            "loading_2": "⚙️ <b>AI Consultant</b>\n\nGathering financial context...",
            "loading_3": "⚙️ <b>AI Consultant</b>\n\nPreparing an honest review...",
            "download_first": "Get a review first to have something to download",
            "download_caption": "📥 Full AI Analysis",
        },
        "kk": {
            "goal_label": "Мақсат",
            "goal_none": "орнатылмаған",
            "menu_body": "Мұнда сіз <b>кезеңді толық талдай</b> аласыз, <b>ақша бойынша нақты сұрақ</b> қоя аласыз немесе <b>талдау дәлдігін тез арттыра</b> аласыз.\n\n"
                         "<b>Мақсат</b>: <b>{goal}</b>\n"
                         "📊 Осы айда қалған терең талдаулар: <b>{limit}-тен {left}</b>\n\n"
                         "<b>Не таңдау керек</b>\n"
                         "• <b>Талдау алу</b> — егер кезең бойынша жалпы қорытынды қажет болса\n"
                         "• <b>Сұрақ қою</b> — егер сізде бір нақты қаржылық міндет болса\n"
                         "• <b>Дәлдікті арттыру</b> — егер енгізілмеген шығындар, бір реттік секірістер болса немесе ай ерекше болса",
            "report_picker": "<b>AI талдау форматы</b>\n\n"
                             "<b>Ай</b> — шығындар, мақсаттар мен тәуекелдерді қалыпты талдаудың негізгі сценарийі.\n"
                             "<b>Апта</b> — жаңа кезеңді жылдам шолу.\n"
                             "<b>Күн</b> — терең суретсіз қысқа жергілікті кесінді.",
            "need_goal_first": "<b>Алдымен қаржылық мақсатты белгілеңіз</b>\n\n"
                               "Оны әдеттегі мәтінмен жазыңыз. Мысалы:\n"
                               "• ноутбукке ақша жинау\n"
                               "• артық шығындарды азайту\n"
                               "• қарызды жабу\n"
                               "• сатып алу үшін 600 000 тг жинау",
            "goal_new_title": "🎯 <b>Жаңа қаржылық мақсат</b>\n\nМақсатыңызды әдеттегі мәтінмен жазыңыз. Соманы бірден көрсетуге болады.",
            "goal_too_short": "Мақсат тым қысқа. Не қалайтыныңызды нақты және сомасымен жазыңыз.",
            "clarify_prompt": "<b>AI үшін нақтылау</b>\n\nБір хабарламамен қысқаша жазыңыз:\n"
                              "• енгізілмеген шығындар немесе кірістер болды ма\n"
                              "• ай ерекше болды ма\n"
                              "• бір реттік ірі операциялар болды ма\n"
                              "• барлық міндетті нәрселер енгізілді ме",
            "clarify_too_short": "Тым қысқа. Талдауды не бұрмалауы мүмкін екендігі туралы кем дегенде қысқаша ескерту қажет.",
            "clarify_saved": "✅ <b>Нақтылау сақталды</b>\n\nЕнді AI бұл ескертуді келесі талдауда немесе жауапта ескереді. Айды талдауға бірден оралуға немесе сұрақ қоюға болады.",
            "question_prompt": "<b>AI-ға сұрақ</b>\n\nҚаржыңыз туралы сұрақ жазыңыз. Мысалы:\n"
                               "• 4 айда велосипедке ақша жинай аламын ба\n"
                               "• менің шығындарым 150 000 тг сатып алуды көтере ме\n"
                               "• маған қазір не маңыздырақ: қарызды өтеу ме әлде жинақтау ма",
            "question_too_short": "Сұрақ тым қысқа. AI тапсырманы түсінуі үшін нақты сұрақ қажет.",
            "limit_reached": "Есептер лимиті бітті",
            "loading_1": "⚙️ <b>AI-кеңесші</b>\n\nДеректер сапасын тексеруде...",
            "loading_2": "⚙️ <b>AI-кеңесші</b>\n\nҚаржылық контекстті жинақтауда...",
            "loading_3": "⚙️ <b>AI-кеңесші</b>\n\nӘділ талдау дайындауда...",
            "download_first": "Жүктеп алу үшін алдымен талдау алыңыз",
            "download_caption": "📥 Толық AI талдау",
        }
    }
    base = data.get(lang, data['ru']).get(key, data['ru'].get(key, key))
    return base.format(**kwargs) if kwargs else base


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _current_month(db: aiosqlite.Connection, user_id: int) -> str:
    from app.domain.time_utils import user_month_key
    return await user_month_key(db, user_id)


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
    current_month = await _current_month(db, user_id)
    if month != current_month:
        used = 0
        await set_ai_usage(db, user_id, 0, current_month, _now_iso())
        await db.commit()
    return used, current_month


def _menu_text(lang: str, goal_text: str | None, used: int) -> str:
    left = max(0, AI_MONTHLY_LIMIT - used)
    title = t(lang, "AI_MENU_TITLE")
    goal_str = goal_text if goal_text else _ai_t(lang, "goal_none")
    return f"{title}\n\n" + _ai_t(lang, "menu_body", goal=goal_str, left=left, limit=AI_MONTHLY_LIMIT)


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
    text = _ai_t(lang, "report_picker")
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
    lang = await get_lang(db, target.from_user.id)
    await _show_prompt(
        target,
        state,
        db,
        _ai_t(lang, "need_goal_first"),
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
    lang = await get_lang(db, c.from_user.id)
    await state.update_data(ui_scope="ai_consultant")
    await state.set_state(AiConsultantFlow.waiting_goal)
    await _show_prompt(c, state, db, _ai_t(lang, "goal_new_title"))
    await c.answer()


@router.message(AiConsultantFlow.waiting_goal, F.text)
async def ai_goal_save(m: Message, state: FSMContext, db: aiosqlite.Connection):
    goal = (m.text or "").strip()
    lang = await get_lang(db, m.from_user.id)
    if len(goal) < 4:
        await m.answer(_ai_t(lang, "goal_too_short"), parse_mode=PARSE_MODE)
        return
    await set_financial_goal(db, m.from_user.id, goal, _now_iso())
    await db.commit()
    await _open_menu(m, state, db)


@router.callback_query(F.data == "ai:clarify")
async def ai_clarify(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    await state.update_data(ui_scope="ai_consultant")
    await state.set_state(AiConsultantFlow.waiting_context_note)
    await _show_prompt(
        c,
        state,
        db,
        _ai_t(lang, "clarify_prompt"),
    )
    await c.answer()


@router.message(AiConsultantFlow.waiting_context_note, F.text)
async def ai_clarify_save(m: Message, state: FSMContext, db: aiosqlite.Connection):
    content = (m.text or "").strip()
    lang = await get_lang(db, m.from_user.id)
    if len(content) < 8:
        await m.answer(_ai_t(lang, "clarify_too_short"), parse_mode=PARSE_MODE)
        return
    await save_ai_context_note(db, m.from_user.id, note_type="report_clarification", period_kind="month", content=content[:2000], created_at=_now_iso())
    await db.commit()
    await state.set_state(None)
    await _clear_prompt(m, state)
    await _render_screen(
        m,
        state,
        _ai_t(lang, "clarify_saved"),
        reply_markup=ai_report_actions_kb(lang, can_download=False),
    )


@router.callback_query(F.data == "ai:question")
async def ai_question_entry(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    await state.update_data(ui_scope="ai_consultant")
    await state.set_state(AiConsultantFlow.waiting_question)
    await _show_prompt(c, state, db, _ai_t(lang, "question_prompt"))
    await c.answer()


@router.message(AiConsultantFlow.waiting_question, F.text)
async def ai_question_answer(m: Message, state: FSMContext, db: aiosqlite.Connection):
    question = (m.text or "").strip()
    lang = await get_lang(db, m.from_user.id)
    if len(question) < 6:
        await m.answer(_ai_t(lang, "question_too_short"), parse_mode=PARSE_MODE)
        return
    tz_name = await get_timezone(db, m.from_user.id)
    goal = await get_financial_goal(db, m.from_user.id)
    context = await build_ai_context(db, m.from_user.id, tz_name, "month", goal)
    text = await render_final_ai_question(context, question)
    await state.set_state(None)
    await _clear_prompt(m, state)
    await state.update_data(last_ai_question=question)
    await _render_screen(m, state, text, reply_markup=ai_question_actions_kb(lang))


@router.callback_query(F.data.startswith("ai:period:"))
async def ai_generate(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    kind = c.data.split(":")[-1]
    goal = await get_financial_goal(db, c.from_user.id)
    lang = await get_lang(db, c.from_user.id)
    if not goal:
        await ai_goal_edit(c, state, db)
        return

    used, month = await _ensure_limit(db, c.from_user.id)
    if used >= AI_MONTHLY_LIMIT:
        await _open_menu(c, state, db)
        await c.answer(_ai_t(lang, "limit_reached"), show_alert=True)
        return

    await state.update_data(ui_scope="ai_consultant")
    await _animate_loading(c, state, [
        _ai_t(lang, "loading_1"),
        _ai_t(lang, "loading_2"),
        _ai_t(lang, "loading_3"),
    ])

    tz_name = await get_timezone(db, c.from_user.id)
    context = await build_ai_context(db, c.from_user.id, tz_name, kind, goal)
    report_text, download_text = await render_final_ai_report(context)

    if (context.get("data_quality") or {}).get("sufficient_for_deep_report"):
        await set_ai_usage(db, c.from_user.id, used + 1, month, _now_iso())
        await db.commit()

    await state.update_data(last_ai_report_text=download_text, last_ai_kind=kind)
    can_download = bool((context.get("data_quality") or {}).get("sufficient_for_deep_report"))
    await _render_screen(c, state, report_text, reply_markup=ai_report_actions_kb(lang, can_download=can_download))
    await c.answer()


@router.callback_query(F.data == "ai:download")
async def ai_download(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    data = await state.get_data()
    payload = data.get("last_ai_report_text")
    if not payload:
        await c.answer(_ai_t(lang, "download_first"), show_alert=True)
        return
    kind = data.get("last_ai_kind") or "report"
    buf = BufferedInputFile(str(payload).encode("utf-8"), filename=f"ai_report_{kind}.txt")
    await c.message.answer_document(buf, caption=_ai_t(lang, "download_caption"))
    await c.answer()


@router.callback_query(F.data == "ai:back")
async def ai_back(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await cancel_to_main_menu(c, state, db)

