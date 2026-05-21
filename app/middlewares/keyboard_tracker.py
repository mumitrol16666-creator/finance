from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Callable

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.methods import TelegramMethod, DeleteMessage, EditMessageReplyMarkup
from aiogram.types import Message
from aiogram.types.inline_keyboard_markup import InlineKeyboardMarkup
from loguru import logger

from app.db.connection import transaction


class KeyboardTrackerMiddleware(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: Callable[[Bot, TelegramMethod[Any]], Any],
        bot: Bot,
        method: TelegramMethod[Any],
    ) -> Any:
        result = await make_request(bot, method)
        
        try:
            if isinstance(method, DeleteMessage):
                chat_id = method.chat_id
                message_id = method.message_id
                if isinstance(chat_id, str):
                    try:
                        chat_id = int(chat_id)
                    except ValueError:
                        chat_id = None
                if chat_id is not None:
                    async with transaction() as db:
                        await db.execute(
                            "DELETE FROM sent_keyboards WHERE chat_id=? AND message_id=?",
                            (chat_id, message_id)
                        )

            elif isinstance(method, EditMessageReplyMarkup) and not method.reply_markup:
                chat_id = method.chat_id
                message_id = method.message_id
                if isinstance(chat_id, str):
                    try:
                        chat_id = int(chat_id)
                    except ValueError:
                        chat_id = None
                if chat_id is not None and message_id is not None:
                    async with transaction() as db:
                        await db.execute(
                            "DELETE FROM sent_keyboards WHERE chat_id=? AND message_id=?",
                            (chat_id, message_id)
                        )

            if isinstance(result, Message):
                chat_id = result.chat.id
                message_id = result.message_id
                
                if result.reply_markup and isinstance(result.reply_markup, InlineKeyboardMarkup):
                    sent_at = datetime.now(timezone.utc).isoformat()
                    async with transaction() as db:
                        await db.execute(
                            "INSERT OR REPLACE INTO sent_keyboards (chat_id, message_id, sent_at) VALUES (?, ?, ?)",
                            (chat_id, message_id, sent_at)
                        )
                else:
                    async with transaction() as db:
                        await db.execute(
                            "DELETE FROM sent_keyboards WHERE chat_id=? AND message_id=?",
                            (chat_id, message_id)
                        )
        except Exception as e:
            logger.error(f"Error in KeyboardTrackerMiddleware: {e}")

        return result
