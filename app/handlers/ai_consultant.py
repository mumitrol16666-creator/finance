from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import aiosqlite
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

from app.db.repositories.ai_context_repo import save_ai_context_note
from app.db.repositories.settings_repo import (
    get_ai_usage,
    get_ai_chat_usage,
    get_financial_goal,
    get_lang,
    get_timezone,
    set_ai_usage,
    set_ai_chat_usage,
    add_ai_chat_extra,
    set_financial_goal,
)
from app.db.repositories.tx_repo import get_expenses_for_period
from app.domain.services.access_service import FEATURE_AI, can_use_feature
from app.domain.services.ai_consultant_service import build_ai_context
from app.domain.services.ai_llm_service import render_final_ai_question, render_final_ai_report
from app.domain.services.reports_service import month_bounds_utc
from app.ui.formatters import fmt_money
from app.fsm.states import AiConsultantFlow
from app.handlers.common import cancel_to_main_menu, deny_feature_message, neutralize_keyboard
from app.ui.i18n import text_matches_key, t
from app.ui.keyboards import (
    ai_consultant_kb,
    ai_chat_kb,
    ai_chat_limit_kb,
    ai_report_actions_kb,
    ai_report_period_kb,
    cancel_kb,
    reports_kb,
)

router = Router()
PARSE_MODE = "HTML"
AI_MONTHLY_LIMIT = 5
AI_CHAT_MONTHLY_LIMIT = 50
AI_CHAT_EXTRA_PACK = 50
AI_CHAT_EXTRA_PRICE = 150


def _ai_t(lang: str, key: str, **kwargs) -> str:
    lang = (lang or "ru").lower()
    data = {
        "ru": {
            "goal_label": "Цель",
            "goal_none": "не задана",
            "menu_body": "Здесь можно <b>поговорить с AI</b> о деньгах, сделать <b>полный разбор периода</b> или <b>повысить точность анализа</b>.\n\n"
                         "<b>Цель</b>: <b>{goal}</b>\n"
                         "📊 Глубоких разборов осталось: <b>{left} из {limit}</b>\n"
                         "💬 Сообщений в чате осталось: <b>{chat_left}</b>\n\n"
                         "<b>Что выбрать</b>\n"
                         "• <b>Чат с AI</b> — свободный диалог по своим финансам\n"
                         "• <b>Получить разбор</b> — глубокий анализ периода\n"
                         "• <b>Повысить точность</b> — уточнить контекст для AI",
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
            "clarify_saved": "✅ <b>Уточнение сохранено</b>\n\nТеперь AI будет учитывать эту пометку в следующем разборе или ответе.",
            "limit_reached": "Лимит отчётов исчерпан",
            "loading_1": "⚙️ <b>AI-консультант</b>\n\nПроверяю качество данных...",
            "loading_2": "⚙️ <b>AI-консультант</b>\n\nСобираю финансовый контекст...",
            "loading_3": "⚙️ <b>AI-консультант</b>\n\nГотовлю честный разбор...",
            "download_first": "Сначала получи разбор, чтобы было что скачивать",
            "download_caption": "📥 Полный AI-разбор",
            "chat_welcome": "💬 <b>Чат с AI-консультантом</b>\n\nЗадай любой вопрос по своим финансам.\nНапример: \"смогу ли я накопить на ноутбук за 3 месяца?\"\n\nПросто пиши сообщение — я отвечу.",
            "chat_new_topic": "🔄 Новая тема. Контекст сброшен.\n\nО чём хочешь поговорить?",
            "chat_thinking": "💭 Думаю...",
            "chat_limit_reached": "⚠️ <b>Лимит сообщений исчерпан</b>\n\nВ этом месяце ты использовал все {limit} сообщений чата.\nМожешь докупить ещё {extra_pack} сообщений за {price} ⭐.",
            "chat_limit_warning": "\n\n<i>💬 Осталось сообщений: {left}</i>",
            "chat_buy_success": "✅ <b>+{extra_pack} сообщений добавлено!</b>\n\nМожешь продолжить общение с AI.",
            "chat_buy_title": "Докупить AI-сообщения",
            "chat_buy_desc": "Дополнительные {extra_pack} сообщений для чата с AI-консультантом",
        },
        "en": {
            "goal_label": "Goal",
            "goal_none": "not set",
            "menu_body": "Here you can <b>chat with AI</b> about money, get a <b>full period analysis</b> or <b>improve analysis accuracy</b>.\n\n"
                         "<b>Goal</b>: <b>{goal}</b>\n"
                         "📊 Deep reviews left: <b>{left} out of {limit}</b>\n"
                         "💬 Chat messages left: <b>{chat_left}</b>\n\n"
                         "<b>What to choose</b>\n"
                         "• <b>Chat with AI</b> — free-form dialog about your finances\n"
                         "• <b>Get report</b> — deep period analysis\n"
                         "• <b>Improve accuracy</b> — clarify context for AI",
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
            "clarify_saved": "✅ <b>Clarification saved</b>\n\nNow AI will take this note into account in the next review or answer.",
            "limit_reached": "Reports limit reached",
            "loading_1": "⚙️ <b>AI Consultant</b>\n\nChecking data quality...",
            "loading_2": "⚙️ <b>AI Consultant</b>\n\nGathering financial context...",
            "loading_3": "⚙️ <b>AI Consultant</b>\n\nPreparing an honest review...",
            "download_first": "Get a review first to have something to download",
            "download_caption": "📥 Full AI Analysis",
            "chat_welcome": "💬 <b>Chat with AI Consultant</b>\n\nAsk any question about your finances.\nFor example: \"can I save up for a laptop in 3 months?\"\n\nJust type your message — I'll answer.",
            "chat_new_topic": "🔄 New topic. Context cleared.\n\nWhat would you like to discuss?",
            "chat_thinking": "💭 Thinking...",
            "chat_limit_reached": "⚠️ <b>Message limit reached</b>\n\nYou've used all {limit} chat messages this month.\nYou can buy {extra_pack} more messages for {price} ⭐.",
            "chat_limit_warning": "\n\n<i>💬 Messages left: {left}</i>",
            "chat_buy_success": "✅ <b>+{extra_pack} messages added!</b>\n\nYou can continue chatting with AI.",
            "chat_buy_title": "Buy AI messages",
            "chat_buy_desc": "Additional {extra_pack} messages for AI consultant chat",
        },
        "kk": {
            "goal_label": "Мақсат",
            "goal_none": "орнатылмаған",
            "menu_body": "Мұнда сіз <b>AI-мен ақша туралы сөйлесе</b> аласыз, <b>кезеңді толық талдай</b> аласыз немесе <b>талдау дәлдігін арттыра</b> аласыз.\n\n"
                         "<b>Мақсат</b>: <b>{goal}</b>\n"
                         "📊 Терең талдаулар қалды: <b>{limit}-тен {left}</b>\n"
                         "💬 Чат хабарламалары қалды: <b>{chat_left}</b>\n\n"
                         "<b>Не таңдау керек</b>\n"
                         "• <b>AI-мен чат</b> — қаржы бойынша еркін диалог\n"
                         "• <b>Талдау алу</b> — кезеңді терең талдау\n"
                         "• <b>Дәлдікті арттыру</b> — AI үшін контекстті нақтылау",
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
            "clarify_saved": "✅ <b>Нақтылау сақталды</b>\n\nЕнді AI бұл ескертуді келесі талдауда немесе жауапта ескереді.",
            "limit_reached": "Есептер лимиті бітті",
            "loading_1": "⚙️ <b>AI-кеңесші</b>\n\nДеректер сапасын тексеруде...",
            "loading_2": "⚙️ <b>AI-кеңесші</b>\n\nҚаржылық контекстті жинақтауда...",
            "loading_3": "⚙️ <b>AI-кеңесші</b>\n\nӘділ талдау дайындауда...",
            "download_first": "Жүктеп алу үшін алдымен талдау алыңыз",
            "download_caption": "📥 Толық AI талдау",
            "chat_welcome": "💬 <b>AI-кеңесшімен чат</b>\n\nҚаржыңыз туралы кез келген сұрақ қойыңыз.\nМысалы: \"3 айда ноутбукке ақша жинай аламын ба?\"\n\nХабарлама жазыңыз — мен жауап беремін.",
            "chat_new_topic": "🔄 Жаңа тақырып. Контекст тазартылды.\n\nНе туралы сөйлескіңіз келеді?",
            "chat_thinking": "💭 Ойланудамын...",
            "chat_limit_reached": "⚠️ <b>Хабарлама лимиті бітті</b>\n\nОсы айда барлық {limit} чат хабарламасын пайдаландыңыз.\nТағы {extra_pack} хабарлама {price} ⭐-ға сатып алуға болады.",
            "chat_limit_warning": "\n\n<i>💬 Хабарламалар қалды: {left}</i>",
            "chat_buy_success": "✅ <b>+{extra_pack} хабарлама қосылды!</b>\n\nAI-мен сөйлесуді жалғастыра аласыз.",
            "chat_buy_title": "AI хабарламалар сатып алу",
            "chat_buy_desc": "AI-кеңесші чаты үшін қосымша {extra_pack} хабарлама",
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


def _menu_text(lang: str, goal_text: str | None, used: int, chat_left: int = 0) -> str:
    left = max(0, AI_MONTHLY_LIMIT - used)
    title = t(lang, "AI_MENU_TITLE")
    goal_str = goal_text if goal_text else _ai_t(lang, "goal_none")
    return f"{title}\n\n" + _ai_t(lang, "menu_body", goal=goal_str, left=left, limit=AI_MONTHLY_LIMIT, chat_left=chat_left)


async def _ensure_chat_limit(db: aiosqlite.Connection, user_id: int) -> tuple[int, int, int]:
    """Returns (used, total_limit, extra)."""
    used, month, extra = await get_ai_chat_usage(db, user_id)
    current_month = await _current_month(db, user_id)
    if month != current_month:
        used = 0
        extra = 0
        await set_ai_chat_usage(db, user_id, 0, current_month, _now_iso())
        await db.commit()
    total_limit = AI_CHAT_MONTHLY_LIMIT + extra
    return used, total_limit, extra


async def _open_menu(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    lang = await get_lang(db, target.from_user.id)
    goal = await get_financial_goal(db, target.from_user.id)
    used, _month = await _ensure_limit(db, target.from_user.id)
    chat_used, chat_total, _extra = await _ensure_chat_limit(db, target.from_user.id)
    chat_left = max(0, chat_total - chat_used)
    await state.update_data(ui_scope="ai_consultant")
    await state.set_state(None)
    await _clear_prompt(target, state)
    await _render_screen(target, state, _menu_text(lang, goal, used, chat_left), reply_markup=ai_consultant_kb(lang))


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


async def _show_ai_teaser(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection) -> None:
    await _collapse_ui(target, state)
    await state.clear()
    
    if isinstance(target, Message):
        try:
            await target.delete()
        except Exception:
            pass
    else:
        await target.answer()

    user_id = target.from_user.id
    lang = await get_lang(db, user_id)
    tz_name = await get_timezone(db, user_id)
    
    # Get month bounds in UTC
    start, end, _, _ = month_bounds_utc(tz_name)
    start_iso = start.astimezone(timezone.utc).isoformat()
    end_iso = end.astimezone(timezone.utc).isoformat()
    
    # Fetch expenses for the period
    expenses = await get_expenses_for_period(db, user_id, start_iso, end_iso)
    
    # Check if empty
    if not expenses:
        # Send base offer
        if lang == "en":
            text = "🧠 My AI brain is ready, but you have no transactions logged this month. Unlock me for 150 ⭐️, and I will start analyzing your every step!"
            btn_text = "Unlock AI for 150 ⭐️"
        elif lang == "kk":
            text = "🧠 Менің AI-миым жұмысқа дайын, бірақ осы айда әлі жазбаларыңыз жоқ. Мені 150 ⭐️-ға ашыңыз, мен сіздің әрбір қадамыңызды талдай бастаймын!"
            btn_text = "ИИ-ді 150 ⭐️-ға ашу"
        else:
            text = "🧠 Мой ИИ-мозг готов к работе, но пока у вас нет записей в этом месяце. Разблокируйте меня за 150 ⭐️, и я начну анализировать каждый ваш шаг!"
            btn_text = "Разблокировать ИИ за 150 ⭐️"
    else:
        # Compute Top-1 category and amount
        from collections import defaultdict
        cat_sums = defaultdict(int)
        for amount, cat_name, cat_emoji in expenses:
            display_name = f"{cat_emoji} {cat_name}".strip() if cat_emoji else cat_name
            cat_sums[display_name] += amount
        
        # Sort by total descending
        sorted_cats = sorted(cat_sums.items(), key=lambda x: x[1], reverse=True)
        top_category, top_amount_val = sorted_cats[0]
        top_amount = fmt_money(top_amount_val)
        
        # Formulate teaser text
        if lang == "en":
            text = "🧠 <i>I've briefly analyzed your expenses for this month.</i>\n" \
                   f"I see that the main part of your budget goes to category <b>{top_category}</b> ({top_amount}).\n\n" \
                   "I have 3 specific tips on how to optimize these expenses and save up to 15% next month...\n" \
                   "░░░░░░░░░░░░░░░░░░░░\n" \
                   "Полный разбор доступен после подключения Full Access."
            btn_text = "Unlock AI for 150 ⭐️"
        elif lang == "kk":
            text = "🧠 <i>Осы айдағы шығындарыңызды жылдам талдап шықтым.</i>\n" \
                   f"Бюджеттің негізгі бөлігі <b>{top_category}</b> санатына кетіп жатқанын көріп тұрмын ({top_amount}).\n\n" \
                   "Шығындарды оңтайландыру және келесі айда 15%-ға дейін үнемдеу туралы 3 нақты кеңесім бар...\n" \
                   "░░░░░░░░░░░░░░░░░░░░\n" \
                   "Толық талдау Full Access қосылғаннан кейін қолжетімді."
            btn_text = "ИИ-ді 150 ⭐️-ға ашу"
        else:
            text = "🧠 <i>Я бегло проанализировал твои расходы за этот месяц.</i>\n" \
                   f"Я вижу, что основная часть бюджета уходит на категорию <b>{top_category}</b> ({top_amount}).\n\n" \
                   "У меня есть 3 конкретных совета, как оптимизировать эти траты и сэкономить до 15% в следующем месяце...\n" \
                   "░░░░░░░░░░░░░░░░░░░░\n" \
                   "Полный разбор — после подключения Full Access."
            btn_text = "Разблокировать ИИ за 150 ⭐️"

    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=btn_text, callback_data="upgrade:activate")],
            [InlineKeyboardButton(text=t(lang, "AI_BACK"), callback_data="ai:back")]
        ]
    )
    
    await state.update_data(ui_scope="ai_consultant_teaser")
    await _render_screen(target, state, text, reply_markup=markup)


@router.callback_query(F.data == "ai:open")
async def ai_entry_from_reports(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_AI):
        await _show_ai_teaser(c, state, db)
        return
    await _enter_ai(c, state, db)


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_AI"))
async def ai_entry(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, m.from_user.id, FEATURE_AI):
        await _show_ai_teaser(m, state, db)
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
        reply_markup=ai_consultant_kb(lang),
    )


# ──────────────────────────────────────────────
#  ЧАТ-РЕЖИМ
# ──────────────────────────────────────────────

@router.callback_query(F.data == "ai:chat:start")
async def ai_chat_start(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    # Проверяем лимит
    chat_used, chat_total, _extra = await _ensure_chat_limit(db, c.from_user.id)
    if chat_used >= chat_total:
        await _render_screen(
            c, state,
            _ai_t(lang, "chat_limit_reached", limit=chat_total, extra_pack=AI_CHAT_EXTRA_PACK, price=AI_CHAT_EXTRA_PRICE),
            reply_markup=ai_chat_limit_kb(lang),
        )
        await c.answer()
        return
    await state.update_data(ui_scope="ai_consultant", ai_chat_history=[])
    await state.set_state(AiConsultantFlow.ai_chatting)
    await _clear_prompt(c, state)
    await _render_screen(c, state, _ai_t(lang, "chat_welcome"), reply_markup=ai_chat_kb(lang))
    await c.answer()


@router.message(AiConsultantFlow.ai_chatting, F.text)
async def ai_chat_message(m: Message, state: FSMContext, db: aiosqlite.Connection):
    from app.db.connection import get_db
    question = (m.text or "").strip()
    if len(question) < 3:
        return

    # Удаляем сообщение пользователя для чистоты
    try:
        await m.delete()
    except Exception:
        pass

    async with get_db() as db_session:
        lang = await get_lang(db_session, m.from_user.id)

        # Проверяем лимит
        chat_used, chat_total, _extra = await _ensure_chat_limit(db_session, m.from_user.id)
        if chat_used >= chat_total:
            await state.set_state(None)
            await _render_screen(
                m, state,
                _ai_t(lang, "chat_limit_reached", limit=chat_total, extra_pack=AI_CHAT_EXTRA_PACK, price=AI_CHAT_EXTRA_PRICE),
                reply_markup=ai_chat_limit_kb(lang),
            )
            return

        tz_name = await get_timezone(db_session, m.from_user.id)
        goal = await get_financial_goal(db_session, m.from_user.id)
        context = await build_ai_context(db_session, m.from_user.id, tz_name, "month", goal)

    # Показываем «думаю...»
    await _render_screen(m, state, _ai_t(lang, "chat_thinking"))

    state_data = await state.get_data()
    chat_history = state_data.get("ai_chat_history", [])

    text = await render_final_ai_question(context, question, chat_history)

    # Сохраняем историю (до 10 ходов)
    chat_history.append({"q": question, "a": text})
    chat_history = chat_history[-10:]

    # Инкремент использования
    async with get_db() as db_session:
        current_month = await _current_month(db_session, m.from_user.id)
        await set_ai_chat_usage(db_session, m.from_user.id, chat_used + 1, current_month, _now_iso())
        await db_session.commit()
        chat_left = max(0, chat_total - chat_used - 1)

    # НЕ сбрасываем state — остаёмся в ai_chatting
    await state.update_data(ai_chat_history=chat_history)

    # Предупреждение если осталось мало сообщений
    warning = ""
    if chat_left <= 5 and chat_left > 0:
        warning = _ai_t(lang, "chat_limit_warning", left=chat_left)

    await _render_screen(m, state, text + warning, reply_markup=ai_chat_kb(lang))


@router.callback_query(F.data == "ai:chat:exit")
async def ai_chat_exit(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _open_menu(c, state, db)
    await c.answer()


@router.callback_query(F.data == "ai:chat:reset")
async def ai_chat_reset(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    await state.update_data(ai_chat_history=[])
    await _render_screen(c, state, _ai_t(lang, "chat_new_topic"), reply_markup=ai_chat_kb(lang))
    await c.answer()


@router.callback_query(F.data == "ai:chat:buy")
async def ai_chat_buy(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    await c.bot.send_invoice(
        chat_id=c.from_user.id,
        title=_ai_t(lang, "chat_buy_title"),
        description=_ai_t(lang, "chat_buy_desc", extra_pack=AI_CHAT_EXTRA_PACK)[:255],
        payload="ai_chat_extra_messages",
        provider_token="",
        currency="XTR",
        prices=[
            LabeledPrice(
                label=_ai_t(lang, "chat_buy_title"),
                amount=AI_CHAT_EXTRA_PRICE,
            )
        ],
    )
    await c.answer()


@router.callback_query(F.data.startswith("ai:period:"))
async def ai_generate(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    from app.db.connection import get_db
    kind = c.data.split(":")[-1]
    
    async with get_db() as db_session:
        goal = await get_financial_goal(db_session, c.from_user.id)
        lang = await get_lang(db_session, c.from_user.id)
        if not goal:
            await ai_goal_edit(c, state, db_session)
            return

        used, month = await _ensure_limit(db_session, c.from_user.id)
        if used >= AI_MONTHLY_LIMIT:
            await _open_menu(c, state, db_session)
            await c.answer(_ai_t(lang, "limit_reached"), show_alert=True)
            return

    await state.update_data(ui_scope="ai_consultant")
    await _animate_loading(c, state, [
        _ai_t(lang, "loading_1"),
        _ai_t(lang, "loading_2"),
        _ai_t(lang, "loading_3"),
    ])

    async with get_db() as db_session:
        tz_name = await get_timezone(db_session, c.from_user.id)
        context = await build_ai_context(db_session, c.from_user.id, tz_name, kind, goal)
    
    report_text, download_text = await render_final_ai_report(context)

    if (context.get("data_quality") or {}).get("sufficient_for_deep_report"):
        async with get_db() as db_session:
            await set_ai_usage(db_session, c.from_user.id, used + 1, month, _now_iso())
            await db_session.commit()

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
    # Возвращаемся в хаб отчётов, а не в главное меню
    from app.handlers.reports import _reports_hub_text
    lang = await get_lang(db, c.from_user.id)
    text = await _reports_hub_text(db, c.from_user.id, lang)
    await _collapse_ui(c, state)
    await state.clear()
    await state.update_data(ui_scope="reports")
    await _render_screen(c, state, text, reply_markup=reports_kb(lang))
    await c.answer()

