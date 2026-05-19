"""Aiogram middlewares wired in ``main.py``."""

from app.middlewares.throttling import ThrottlingMiddleware
from app.middlewares.access import AccessContextMiddleware
from app.middlewares.fsm_escape import FsmEscapeMiddleware
from app.middlewares.db_session import DbSessionMiddleware

__all__ = [
    "ThrottlingMiddleware",
    "AccessContextMiddleware",
    "FsmEscapeMiddleware",
    "DbSessionMiddleware",
]
