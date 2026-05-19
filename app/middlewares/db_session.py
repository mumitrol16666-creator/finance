from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from app.db.connection import get_db


class DbSessionMiddleware(BaseMiddleware):
    """
    Middleware that opens an isolated SQLite database connection per update.
    Injects the connection into `data["db"]`.
    Closes the connection after the handler finishes.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with get_db() as db:
            data["db"] = db
            return await handler(event, data)
