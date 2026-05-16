"""Aiogram middlewares wired in ``main.py``."""

from app.middlewares.throttling import ThrottlingMiddleware

__all__ = ["ThrottlingMiddleware"]
