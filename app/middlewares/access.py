"""Inject user context (lang + access profile) into every handler.

Handlers used to fetch ``lang`` and ``UserAccessContext`` repeatedly per
update (sometimes 4-5 times within a single callback). The middleware does it
once and stuffs the result into ``data``, which is then injected as a kwarg
by aiogram. Handlers can opt in by adding ``lang: str`` and / or
``access_ctx: UserAccessContext`` parameters; absent params are simply
ignored, so this middleware is fully backward-compatible with existing
handlers that do their own lookup.

The middleware is intentionally permissive — it never blocks updates. If the
DB call fails (rare), defaults are injected so the handler can still respond.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from loguru import logger

DEFAULT_LANG = "ru"


class AccessContextMiddleware(BaseMiddleware):
    """Resolve user lang/access profile per update and inject into kwargs."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if from_user is None or not getattr(from_user, "id", None):
            return await handler(event, data)

        user_id = int(from_user.id)
        db = data.get("db")
        if db is None:
            return await handler(event, data)

        lang = data.get("lang")
        if not lang:
            try:
                from app.db.repositories.settings_repo import get_lang as _get_lang
                lang = await _get_lang(db, user_id)
            except Exception as exc:
                logger.debug("AccessContextMiddleware: get_lang failed: {}", exc)
                lang = DEFAULT_LANG
            data["lang"] = lang or DEFAULT_LANG

        if "access_ctx" not in data:
            try:
                from app.domain.services.access_service import get_user_context
                data["access_ctx"] = await get_user_context(db, user_id)
            except Exception as exc:
                logger.debug("AccessContextMiddleware: get_user_context failed: {}", exc)
                data["access_ctx"] = None

        ctx = data.get("access_ctx")
        if ctx is not None:
            data.setdefault("full_access", bool(getattr(ctx, "full_access", False)))
            data.setdefault("user_mode", getattr(ctx, "mode", "newbie"))

        return await handler(event, data)
