from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.fsm.context import FSMContext
from loguru import logger

from app.ui.i18n import text_matches_key
from app.handlers.common import _cleanup_ui, is_cancel_text, is_main_menu_text


class FsmEscapeMiddleware(BaseMiddleware):
    """Middleware that allows users to break out of stuck FSM flows.
    
    If the user is in an active FSM state and sends a global command,
    a main menu reply keyboard button, or clicks an inline cancel button,
    this middleware intercepts the update, cleans up the old flow's UI,
    clears the FSM state, and allows the update to proceed.
    
    Since the state is cleared to None, the standard empty-state router
    handlers (e.g., for starting a new Expense/Income flow or showing the menu)
    will match and handle the update normally.
    """

    def _is_escape_trigger(self, text: str | None) -> bool:
        if not text:
            return False
        
        raw = text.strip()
        
        # 1. Any command starting with / (e.g., /start, /cancel, /menu)
        if raw.startswith("/"):
            return True
            
        # 2. General cancel/menu phrases in any language
        if is_cancel_text(raw) or is_main_menu_text(raw):
            return True
            
        # 3. Main menu reply keyboard buttons across all 3 languages
        menu_keys = [
            "BTN_EXPENSE",
            "BTN_INCOME",
            "BTN_PLANNING",
            "BTN_REPORT",
            "BTN_SETTINGS",
            "BTN_MORE",
            "BTN_UPGRADE_FULL",
            "BTN_RETURN_TO_MAIN_MENU",
        ]
        for key in menu_keys:
            if text_matches_key(raw, key):
                return True
                
        # 4. Subscription/Upgrade status labels
        raw_fold = raw.casefold()
        if any(x in raw_fold for x in ["полный режим", "full mode", "толық режим", "продлить подписку", "upgrade / renew", "жаңарту"]):
            return True
            
        return False

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        state: FSMContext | None = data.get("state")
        if state is None:
            return await handler(event, data)

        current_state = await state.get_state()
        if current_state is None:
            return await handler(event, data)

        # The user is in an active FSM state
        should_escape = False
        chat_id = None
        
        if isinstance(event, Message):
            chat_id = event.chat.id
            if self._is_escape_trigger(event.text or event.caption):
                logger.info(f"User {event.from_user.id} escaped state {current_state} via text: '{event.text}'")
                should_escape = True
                
        elif isinstance(event, CallbackQuery):
            chat_id = event.message.chat.id if event.message else None
            cb_data = event.data or ""
            # Inline cancel clicks
            if cb_data in ("cancel", "flow:cancel") or cb_data.endswith(":cancel"):
                logger.info(f"User {event.from_user.id} escaped state {current_state} via callback_data: '{cb_data}'")
                should_escape = True

        if should_escape and chat_id is not None:
            # 1. Clean up the UI of the old flow (remove inline keyboards, delete prompts)
            flow_data = await state.get_data()
            try:
                await _cleanup_ui(event.bot, chat_id, flow_data)
            except Exception as e:
                logger.debug(f"FsmEscapeMiddleware: cleanup failed: {e}")
                
            # 2. Clear the FSM state entirely
            await state.clear()

        return await handler(event, data)
