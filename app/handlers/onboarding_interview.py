from __future__ import annotations

from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from loguru import logger

from app.fsm.states import OnboardingInterview
from app.handlers.common import cancel_to_main_menu
from app.db.repositories.settings_repo import get_lang
from app.domain.services.onboarding_interview_service import (
    generate_interview_response,
    get_fallback_interview_response,
    parse_interview_json,
    save_interview_results_to_db,
    determine_fallback_archetype,
    parse_digit
)
from app.integrations.openai_client import has_openai_key

router = Router()
PARSE_MODE = "HTML"

WELCOME_TEXTS = {
    "ru": (
        "А теперь давай познакомимся поближе 😊\n"
        "Нам важно узнать твои цели, чтобы настроить бота под тебя. Это займет всего 1 минуту.\n\n"
        "🎁 <b>Внимание:</b> это разовое предложение! Пройди опрос прямо сейчас и получи <b>7 дней бесплатного Premium-доступа</b>. Если пропустишь, повторно пройти опрос и получить бонус не получится!"
    ),
    "en": (
        "And now let's get to know each other better 😊\n"
        "It is important for us to know your goals to customize the bot for you. It will take only 1 minute.\n\n"
        "🎁 <b>Note:</b> this is a one-time offer! Complete the quick interview now to get <b>7 days of free Premium access</b>. If you skip, you won't be able to take it later or claim the bonus!"
    ),
    "kk": (
        "Ал енді жақынырақ танысайық 😊\n"
        "Ботты сізге сәйкес баптау үшін қаржылық мақсаттарыңызды білу маңызды. Бұл бар болғаны 1 минут уақытты алады.\n\n"
        "🎁 <b>Назар аударыңыз:</b> бұл бір реттік ұсыныс! Сауалнамадан қазір өтіп, <b>7 күндік тегін Premium</b> алыңыз. Егер өткізіп жіберсеңіз, кейін сауалнамадан өтіп, бонусты алу мүмкін болмайды!"
    )
}

QUESTION_TEXTS = {
    "ru": "Какая твоя главная цель в финансах сейчас? Например: начать копить, перестать тратить лишнее или просто понять, куда уходят деньги?",
    "en": "What is your main financial goal right now? For example: start saving, stop overspending, or just understand where your money goes?",
    "kk": "Қазіргі уақытта негізгі қаржылық мақсатыңыз қандай? Мысалы: ақша жинауды бастау, артық шығынды тоқтату немесе ақшаның қайда кетіп жатқанын түсіну."
}

SKIP_TEXTS = {
    "ru": "⏭ Пропустить",
    "en": "⏭ Skip",
    "kk": "⏭ Өткізіп жіберу"
}

PREMIUM_BTN_TEXTS = {
    "ru": "Получить премиум на 7 дней",
    "en": "Get 7 days of Premium",
    "kk": "7 күндік Premium алу"
}

def skip_kb(lang: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=SKIP_TEXTS.get(lang, SKIP_TEXTS["ru"])))
    return builder.as_markup(resize_keyboard=True)

def let_go_kb(lang: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text=PREMIUM_BTN_TEXTS.get(lang, PREMIUM_BTN_TEXTS["ru"])))
    return builder.as_markup(resize_keyboard=True)

async def start_interview(message: Message, state: FSMContext, db):
    """Starts the 5-stage onboarding interview flow."""
    logger.info(f"Starting onboarding interview for user {message.chat.id}")
    await state.clear()
    await state.set_state(OnboardingInterview.stage_1_pain)
    
    lang = await get_lang(db, message.chat.id)
    
    welcome_text = WELCOME_TEXTS.get(lang, WELCOME_TEXTS["ru"])
    question_text = QUESTION_TEXTS.get(lang, QUESTION_TEXTS["ru"])
    
    await message.answer(welcome_text, parse_mode=PARSE_MODE)
    await message.answer(question_text, reply_markup=skip_kb(lang), parse_mode=PARSE_MODE)
    
    await state.update_data(
        history=[{"role": "assistant", "content": question_text}],
        stage_1_question=question_text
    )

@router.message(OnboardingInterview.stage_1_pain, F.text.in_({"⏭ Пропустить", "⏭ Skip", "⏭ Өткізіп жіберу"}))
@router.message(OnboardingInterview.stage_2_regret, F.text.in_({"⏭ Пропустить", "⏭ Skip", "⏭ Өткізіп жіберу"}))
@router.message(OnboardingInterview.stage_3_dream, F.text.in_({"⏭ Пропустить", "⏭ Skip", "⏭ Өткізіп жіберу"}))
@router.message(OnboardingInterview.stage_4_limit, F.text.in_({"⏭ Пропустить", "⏭ Skip", "⏭ Өткізіп жіберу"}))
@router.message(F.text.in_({"⏭ Пропустить", "⏭ Skip", "⏭ Өткізіп жіберу"}))
async def skip_interview(m: Message, state: FSMContext, db):
    logger.info(f"User {m.from_user.id} skipped onboarding interview")
    try:
        now_str = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE settings SET onboarding_interview_done=1, updated_at=? WHERE user_id=?",
            (now_str, m.from_user.id)
        )
        await db.commit()
    except Exception as e:
        logger.error(f"Error marking onboarding interview as done on skip: {e}")
        
    await state.clear()
    await cancel_to_main_menu(m, state, db)

@router.message(OnboardingInterview.stage_1_pain)
async def handle_stage_1_pain(m: Message, state: FSMContext, db):
    data = await state.get_data()
    history = data.get("history", [])
    history.append({"role": "user", "content": m.text})
    
    await state.update_data(stage_1_pain=m.text)
    
    await m.bot.send_chat_action(m.chat.id, "typing")
    lang = await get_lang(db, m.from_user.id)
    
    if has_openai_key():
        try:
            response = await generate_interview_response(history)
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            response = get_fallback_interview_response(1, m.text, data, lang)
    else:
        response = get_fallback_interview_response(1, m.text, data, lang)
        
    history.append({"role": "assistant", "content": response})
    await state.update_data(history=history)
    await state.set_state(OnboardingInterview.stage_2_regret)
    
    await m.answer(response, reply_markup=skip_kb(lang), parse_mode=PARSE_MODE)

@router.message(OnboardingInterview.stage_2_regret)
async def handle_stage_2_regret(m: Message, state: FSMContext, db):
    data = await state.get_data()
    history = data.get("history", [])
    history.append({"role": "user", "content": m.text})
    
    await state.update_data(stage_2_regret=m.text)
    
    await m.bot.send_chat_action(m.chat.id, "typing")
    lang = await get_lang(db, m.from_user.id)
    
    if has_openai_key():
        try:
            response = await generate_interview_response(history)
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            response = get_fallback_interview_response(2, m.text, data, lang)
    else:
        response = get_fallback_interview_response(2, m.text, data, lang)
        
    history.append({"role": "assistant", "content": response})
    await state.update_data(history=history)
    await state.set_state(OnboardingInterview.stage_3_dream)
    
    await m.answer(response, reply_markup=skip_kb(lang), parse_mode=PARSE_MODE)

@router.message(OnboardingInterview.stage_3_dream)
async def handle_stage_3_dream(m: Message, state: FSMContext, db):
    data = await state.get_data()
    history = data.get("history", [])
    history.append({"role": "user", "content": m.text})
    
    await state.update_data(stage_3_dream=m.text)
    
    await m.bot.send_chat_action(m.chat.id, "typing")
    lang = await get_lang(db, m.from_user.id)
    
    if has_openai_key():
        try:
            response = await generate_interview_response(history)
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            response = get_fallback_interview_response(3, m.text, data, lang)
    else:
        response = get_fallback_interview_response(3, m.text, data, lang)
        
    history.append({"role": "assistant", "content": response})
    await state.update_data(history=history)
    await state.set_state(OnboardingInterview.stage_4_limit)
    
    await m.answer(response, reply_markup=skip_kb(lang), parse_mode=PARSE_MODE)

@router.message(OnboardingInterview.stage_4_limit)
async def handle_stage_4_limit(m: Message, state: FSMContext, db):
    data = await state.get_data()
    history = data.get("history", [])
    history.append({"role": "user", "content": m.text})
    
    await state.update_data(stage_4_limit=m.text)
    
    await m.bot.send_chat_action(m.chat.id, "typing")
    lang = await get_lang(db, m.from_user.id)
    
    if has_openai_key():
        try:
            response = await generate_interview_response(history)
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            response = get_fallback_interview_response(4, m.text, data, lang)
    else:
        response = get_fallback_interview_response(4, m.text, data, lang)
        
    # Parse JSON and text
    clean_text, parsed = parse_interview_json(response)
    
    # If parsing failed or in fallback, use rules to reconstruct parsed structure
    if not parsed:
        pain = data.get("stage_1_pain", "")
        regret = data.get("stage_2_regret", "")
        dream = data.get("stage_3_dream", "Финансовая стабильность")
        parsed = {
            "main_goal": dream,
            "daily_limit": parse_digit(m.text),
            "archetype": determine_fallback_archetype(pain, regret, dream)
        }
    
    try:
        from app.db.repositories.users_repo import grant_full_access
        await grant_full_access(db, m.from_user.id, days=7)
        await save_interview_results_to_db(db, m.from_user.id, parsed)
    except Exception as e:
        logger.error(f"Failed to save interview results or grant full access: {e}")
        
    trial_msg = {
        "ru": "\n\n🎁 <b>Тебе начислено 7 дней бесплатного пробного периода!</b> 🎉",
        "en": "\n\n🎁 <b>You have been granted 7 days of free trial period!</b> 🎉",
        "kk": "\n\n🎁 <b>Сізге 7 күндік тегін сынақ мерзімі берілді!</b> 🎉",
    }.get(lang, "\n\n🎁 <b>Тебе начислено 7 дней бесплатного пробного периода!</b> 🎉")
        
    await state.set_state(OnboardingInterview.stage_5_summary)
    await m.answer(clean_text + trial_msg, reply_markup=let_go_kb(lang), parse_mode=PARSE_MODE)

@router.message(OnboardingInterview.stage_5_summary)
@router.message(F.text.in_({"🚀 Поехали!", "Получить премиум на 7 дней", "Get 7 days of Premium", "7 күндік Premium алу"}))
async def finish_interview(m: Message, state: FSMContext, db):
    await state.clear()
    await cancel_to_main_menu(m, state, db)
