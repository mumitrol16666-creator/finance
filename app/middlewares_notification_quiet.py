from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.scheduler.notify_scheduler import suppress_notifications_for


class NotificationQuietMiddleware(BaseMiddleware):
    def __init__(self, *, seconds: int = 1800) -> None:
        self.seconds = max(60, int(seconds))

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_id = None

        if isinstance(event, Message) and event.from_user is not None:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user is not None:
            user_id = event.from_user.id
        else:
            from_user = getattr(event, 'from_user', None)
            if from_user is not None:
                user_id = getattr(from_user, 'id', None)

        if user_id is not None:
            suppress_notifications_for(int(user_id), seconds=self.seconds)

        return await handler(event, data)
