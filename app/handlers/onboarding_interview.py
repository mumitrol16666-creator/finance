from __future__ import annotations

from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from loguru import logger

from app.fsm.states import OnboardingInterview
from app.handlers.common import cancel_to_main_menu, build_main_menu_markup
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

def skip_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="⏭ Пропустить"))
    return builder.as_markup(resize_keyboard=True)

def let_go_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="🚀 Поехали!"))
    return builder.as_markup(resize_keyboard=True)

async def start_interview(message: Message, state: FSMContext, db):
    """Starts the 5-stage onboarding interview flow."""
    logger.info(f"Starting onboarding interview for user {message.chat.id}")
    await state.clear()
    await state.set_state(OnboardingInterview.stage_1_pain)
    
    welcome_text = (
        "А теперь давай познакомимся поближе 😊\n"
        "Нам важно понять твоё отношение к деньгам, чтобы настроить бота под тебя. Это займёт всего 1 минуту."
    )
    question_text = "Что тебя больше всего напрягает в деньгах?"
    
    await message.answer(welcome_text, parse_mode=PARSE_MODE)
    await message.answer(question_text, reply_markup=skip_kb(), parse_mode=PARSE_MODE)
    
    await state.update_data(
        history=[{"role": "assistant", "content": question_text}],
        stage_1_question=question_text
    )

@router.message(OnboardingInterview.stage_1_pain, F.text == "⏭ Пропустить")
@router.message(OnboardingInterview.stage_2_regret, F.text == "⏭ Пропустить")
@router.message(OnboardingInterview.stage_3_dream, F.text == "⏭ Пропустить")
@router.message(OnboardingInterview.stage_4_limit, F.text == "⏭ Пропустить")
@router.message(F.text == "⏭ Пропустить")
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
    
    if has_openai_key():
        try:
            response = await generate_interview_response(history)
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            response = get_fallback_interview_response(1, m.text, data)
    else:
        response = get_fallback_interview_response(1, m.text, data)
        
    history.append({"role": "assistant", "content": response})
    await state.update_data(history=history)
    await state.set_state(OnboardingInterview.stage_2_regret)
    
    await m.answer(response, reply_markup=skip_kb(), parse_mode=PARSE_MODE)

@router.message(OnboardingInterview.stage_2_regret)
async def handle_stage_2_regret(m: Message, state: FSMContext, db):
    data = await state.get_data()
    history = data.get("history", [])
    history.append({"role": "user", "content": m.text})
    
    await state.update_data(stage_2_regret=m.text)
    
    if has_openai_key():
        try:
            response = await generate_interview_response(history)
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            response = get_fallback_interview_response(2, m.text, data)
    else:
        response = get_fallback_interview_response(2, m.text, data)
        
    history.append({"role": "assistant", "content": response})
    await state.update_data(history=history)
    await state.set_state(OnboardingInterview.stage_3_dream)
    
    await m.answer(response, reply_markup=skip_kb(), parse_mode=PARSE_MODE)

@router.message(OnboardingInterview.stage_3_dream)
async def handle_stage_3_dream(m: Message, state: FSMContext, db):
    data = await state.get_data()
    history = data.get("history", [])
    history.append({"role": "user", "content": m.text})
    
    await state.update_data(stage_3_dream=m.text)
    
    if has_openai_key():
        try:
            response = await generate_interview_response(history)
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            response = get_fallback_interview_response(3, m.text, data)
    else:
        response = get_fallback_interview_response(3, m.text, data)
        
    history.append({"role": "assistant", "content": response})
    await state.update_data(history=history)
    await state.set_state(OnboardingInterview.stage_4_limit)
    
    await m.answer(response, reply_markup=skip_kb(), parse_mode=PARSE_MODE)

@router.message(OnboardingInterview.stage_4_limit)
async def handle_stage_4_limit(m: Message, state: FSMContext, db):
    data = await state.get_data()
    history = data.get("history", [])
    history.append({"role": "user", "content": m.text})
    
    await state.update_data(stage_4_limit=m.text)
    
    if has_openai_key():
        try:
            response = await generate_interview_response(history)
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            response = get_fallback_interview_response(4, m.text, data)
    else:
        response = get_fallback_interview_response(4, m.text, data)
        
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
        await save_interview_results_to_db(db, m.from_user.id, parsed)
    except Exception as e:
        logger.error(f"Failed to save interview results to DB: {e}")
        
    await state.set_state(OnboardingInterview.stage_5_summary)
    await m.answer(clean_text, reply_markup=let_go_kb(), parse_mode=PARSE_MODE)

@router.message(OnboardingInterview.stage_5_summary)
@router.message(F.text == "🚀 Поехали!")
async def finish_interview(m: Message, state: FSMContext, db):
    await state.clear()
    await cancel_to_main_menu(m, state, db)
