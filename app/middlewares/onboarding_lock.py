from __future__ import annotations
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from loguru import logger

from app.fsm.states import TelegramOnboarding

STATE_MAP = {
    "select_auth_type": TelegramOnboarding.select_auth_type,
    "tg_link_login": TelegramOnboarding.tg_link_login,
    "tg_link_password": TelegramOnboarding.tg_link_password,
    "tg_reg_name": TelegramOnboarding.tg_reg_name,
    "tg_reg_login": TelegramOnboarding.tg_reg_login,
    "tg_reg_password": TelegramOnboarding.tg_reg_password,
    "ai_survey_invite": TelegramOnboarding.ai_survey_invite,
    "ai_survey_q1": TelegramOnboarding.ai_survey_q1,
    "ai_survey_q2": TelegramOnboarding.ai_survey_q2,
    "ai_survey_q3": TelegramOnboarding.ai_survey_q3,
    "ai_survey_q4": TelegramOnboarding.ai_survey_q4,
    "waiting_legacy_password": TelegramOnboarding.waiting_legacy_password,
}

class OnboardingLockMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        db = data.get("db")
        state_ctx: FSMContext | None = data.get("state")
        
        if not db or not state_ctx:
            return await handler(event, data)
            
        user_id = None
        is_start_cmd = False
        text = ""
        cb_data = ""
        
        if isinstance(event, Message):
            user_id = event.from_user.id
            text = (event.text or "").strip()
            if text.startswith("/start"):
                is_start_cmd = True
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            cb_data = event.data or ""
            
        if user_id:
            # Query the database for onboarding_state
            cur = await db.execute("SELECT onboarding_state FROM users WHERE id = ?", (user_id,))
            row = await cur.fetchone()
            onboarding_state = row[0] if row else None
            
            # If user has an onboarding state and it is not completed
            if onboarding_state and onboarding_state != "completed":
                # If they sent /start, let it pass so they can restart
                if is_start_cmd:
                    return await handler(event, data)
                    
                # Auto-restore FSM state if it's out of sync
                if onboarding_state in STATE_MAP:
                    current_fsm_state = await state_ctx.get_state()
                    expected_fsm_state = STATE_MAP[onboarding_state]
                    if current_fsm_state != expected_fsm_state.state:
                        logger.info(f"Syncing FSM state for user {user_id} to {expected_fsm_state.state} (from DB: {onboarding_state})")
                        await state_ctx.set_state(expected_fsm_state)
                
                # Check message text / callback data restrictions
                if isinstance(event, Message):
                    # Ignore all other commands during onboarding
                    if text.startswith("/"):
                        logger.info(f"Ignoring command '{text}' for user {user_id} during onboarding")
                        return
                elif isinstance(event, CallbackQuery):
                    # Only allow onboarding callbacks
                    allowed_prefixes = ("ob:", "tg_reg:", "tg_link:", "ai_survey:")
                    if not any(cb_data.startswith(pref) for pref in allowed_prefixes):
                        logger.info(f"Ignoring callback '{cb_data}' for user {user_id} during onboarding")
                        await event.answer()
                        return

        return await handler(event, data)
