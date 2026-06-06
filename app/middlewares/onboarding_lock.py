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
    "tg_reg_lang": TelegramOnboarding.tg_reg_lang,
    "tg_reg_currency": TelegramOnboarding.tg_reg_currency,
    "tg_reg_acc_name": TelegramOnboarding.tg_reg_acc_name,
    "tg_reg_acc_balance": TelegramOnboarding.tg_reg_acc_balance,
    "tg_reg_daily": TelegramOnboarding.tg_reg_daily,
    "tg_reg_daily_time": TelegramOnboarding.tg_reg_daily_time,
    "tg_reg_daily_time_custom": TelegramOnboarding.tg_reg_daily_time_custom,
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
            
            # Auto-restore FSM state if it's out of sync
            if onboarding_state and onboarding_state in STATE_MAP:
                current_fsm_state = await state_ctx.get_state()
                expected_fsm_state = STATE_MAP[onboarding_state]
                if current_fsm_state != expected_fsm_state.state:
                    logger.info(f"Syncing FSM state for user {user_id} to {expected_fsm_state.state} (from DB: {onboarding_state})")
                    await state_ctx.set_state(expected_fsm_state)
            
            # If they are setting a legacy password, let them tap other setting callbacks
            # and automatically clean up the temporary state.
            if onboarding_state == "waiting_legacy_password":
                if isinstance(event, CallbackQuery):
                    cb_data = event.data or ""
                    if cb_data and not cb_data.startswith("ob:"):
                        logger.info(f"User {user_id} clicked callback '{cb_data}' while in waiting_legacy_password. Auto-completing state.")
                        await db.execute("UPDATE users SET onboarding_state = 'completed' WHERE id = ?", (user_id,))
                        await db.commit()
                        await state_ctx.clear()
                        onboarding_state = "completed"
            
            # If user has an onboarding state and it is a locked onboarding stage
            if onboarding_state and onboarding_state not in ("completed", "waiting_legacy_password"):
                # If they sent /start, let it pass so they can restart
                if is_start_cmd:
                    return await handler(event, data)
                    
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
