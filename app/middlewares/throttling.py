"""Per-user throttling for callback queries and messages.

Designed to absorb "rage-tap" double clicks on inline buttons (which can otherwise
create duplicate transactions — see audit 1.3). It is intentionally tiny:
- no Redis, no scheduler, just an in-memory dict;
- per-user, per-event-type;
- silently swallows the second event within the window so users don't see a
  scary error and the bot doesn't spam.
"""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, *, rate: float = 0.7) -> None:
        # Minimum interval (seconds) between accepted events from the same user.
        self.rate = max(0.0, float(rate))
        self._last_event: dict[tuple[int, str], float] = {}

    def _bucket_key(self, event: TelegramObject) -> tuple[int, str] | None:
        from_user = getattr(event, "from_user", None)
        user_id = getattr(from_user, "id", None)
        if user_id is None:
            return None
        if isinstance(event, CallbackQuery):
            return (int(user_id), "callback")
        if isinstance(event, Message):
            return (int(user_id), "message")
        return (int(user_id), "other")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if self.rate <= 0:
            return await handler(event, data)

        key = self._bucket_key(event)
        if key is None:
            return await handler(event, data)

        now = time.monotonic()
        last = self._last_event.get(key, 0.0)
        if now - last < self.rate:
            # Acknowledge a callback so the spinner clears, then drop the event.
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer()
                except Exception:
                    pass
            return None
        self._last_event[key] = now
        return await handler(event, data)
