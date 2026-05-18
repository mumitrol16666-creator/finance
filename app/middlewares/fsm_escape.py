from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.fsm.context import FSMContext
from loguru import logger

from app.ui.i18n import text_matches_key
from app.handlers.common import _cleanup_ui, is_cancel_text, is_main_menu_text


class FsmEscapeMiddleware(BaseMiddleware):
    """Middleware that allows users to break out of stuck FSM flows instantly.
    
    If the user is in an active FSM state and sends a global command,
    a main menu reply keyboard button, or clicks an inline cancel button,
    this middleware intercepts the update.
    
    For menu navigation reply keyboard buttons (e.g., Expense, Income, Reports),
    it clears the FSM state and allows the update to proceed to let the dispatcher
    launch the fresh menu screen.
    
    For cancellation commands, text phrases, or inline cancel clicks,
    it directly calls the global cancel_to_main_menu handler and terminates the chain,
    instantly returning the main menu and preventing stuck callback spinners.
    """

    def _is_menu_navigation(self, text: str | None) -> bool:
        if not text:
            return False
        
        raw = text.strip()
        
        # 1. Main menu reply keyboard buttons across all 3 languages
        menu_keys = [
            "BTN_EXPENSE",
            "BTN_INCOME",
            "BTN_PLANNING",
            "BTN_REPORT",
            "BTN_SETTINGS",
            "BTN_MORE",
            "BTN_UPGRADE_FULL",
        ]
        for key in menu_keys:
            if text_matches_key(raw, key):
                return True
                
        # 2. Subscription/Upgrade status labels
        raw_fold = raw.casefold()
        if any(x in raw_fold for x in ["полный режим", "full mode", "толық режим", "продлить подписку", "upgrade / renew", "жаңарту"]):
            return True
            
        return False

    def _is_cancellation(self, text: str | None) -> bool:
        if not text:
            return False
        
        raw = text.strip()
        
        # 1. Any command starting with / (e.g., /start, /cancel, /menu)
        if raw.startswith("/"):
            return True
            
        # 2. General cancel/menu phrases in any language
        if is_cancel_text(raw) or is_main_menu_text(raw):
            return True
            
        # 3. Return to main menu reply keyboard button
        if text_matches_key(raw, "BTN_RETURN_TO_MAIN_MENU"):
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
        chat_id = None
        db = data.get("db")
        
        if isinstance(event, Message):
            chat_id = event.chat.id
            text = event.text or event.caption or ""
            
            # If user pressed a main menu navigation button
            if self._is_menu_navigation(text):
                logger.info(f"User {event.from_user.id} escaped state {current_state} via menu navigation: '{text}'")
                flow_data = await state.get_data()
                try:
                    await _cleanup_ui(event.bot, chat_id, flow_data)
                except Exception as e:
                    logger.debug(f"FsmEscapeMiddleware: cleanup failed: {e}")
                
                await state.clear()
                return await handler(event, data)
                
            # If user sent a cancel or start command/phrase
            elif self._is_cancellation(text):
                logger.info(f"User {event.from_user.id} cancelled state {current_state} via text: '{text}'")
                from app.handlers.common import cancel_to_main_menu
                await cancel_to_main_menu(event, state, db)
                return
                
        elif isinstance(event, CallbackQuery):
            chat_id = event.message.chat.id if event.message else None
            cb_data = event.data or ""
            
            # Inline cancel clicks
            if cb_data in ("cancel", "flow:cancel") or cb_data.endswith(":cancel"):
                logger.info(f"User {event.from_user.id} cancelled state {current_state} via callback_data: '{cb_data}'")
                from app.handlers.common import cancel_to_main_menu
                await cancel_to_main_menu(event, state, db)
                return

        return await handler(event, data)
