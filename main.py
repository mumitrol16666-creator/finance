import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.fsm.storage.memory import SimpleEventIsolation
from loguru import logger

from app.config.settings import settings
from app.db.connection import open_db
from app.db.migrate import run_migrations
from app.handlers import get_routers
from app.logging.setup import setup_logging
from app.middlewares import ThrottlingMiddleware
from app.middlewares.access import AccessContextMiddleware
from app.middlewares.fsm_escape import FsmEscapeMiddleware
from app.middlewares_notification_quiet import NotificationQuietMiddleware
from app.scheduler.notify_scheduler import setup_notify_scheduler


BOT_COMMANDS: dict[str, list[BotCommand]] = {
    "ru": [
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="undo", description="Отменить последнюю запись"),
        BotCommand(command="export", description="Экспорт XLSX за месяц"),
        BotCommand(command="cancel", description="Сбросить текущее действие"),
    ],
    "en": [
        BotCommand(command="start", description="Start"),
        BotCommand(command="undo", description="Undo last entry"),
        BotCommand(command="export", description="Export XLSX for the month"),
        BotCommand(command="cancel", description="Cancel current action"),
    ],
    "kk": [
        BotCommand(command="start", description="Бастау"),
        BotCommand(command="undo", description="Соңғы жазуды болдырмау"),
        BotCommand(command="export", description="Айдың XLSX-экспорты"),
        BotCommand(command="cancel", description="Ағымдағы әрекетті бас тарту"),
    ],
}


async def _set_bot_commands(bot: Bot) -> None:
    """Register bot menu commands per language (RU as default)."""
    try:
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
    except Exception:
        pass

    await bot.set_my_commands(BOT_COMMANDS["ru"], scope=BotCommandScopeDefault())
    for lang_code in ("en", "kk"):
        try:
            await bot.delete_my_commands(scope=BotCommandScopeDefault(), language_code=lang_code)
        except Exception:
            pass
        try:
            await bot.set_my_commands(
                BOT_COMMANDS[lang_code],
                scope=BotCommandScopeDefault(),
                language_code=lang_code,
            )
        except Exception:
            pass


async def main():
    setup_logging(settings.debug)

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(events_isolation=SimpleEventIsolation())

    # Anti-double-tap on inline buttons (see audit 1.3) and noise suppression
    # for scheduled notifications while the user is actively chatting.
    throttling = ThrottlingMiddleware(rate=0.7)
    dp.callback_query.middleware(throttling)
    dp.message.middleware(throttling)

    # Graceful FSM escape for stuck users
    fsm_escape_mw = FsmEscapeMiddleware()
    dp.message.outer_middleware(fsm_escape_mw)
    dp.callback_query.outer_middleware(fsm_escape_mw)

    # Inject lang / access_ctx once per update so handlers don't refetch.
    access_mw = AccessContextMiddleware()
    dp.message.middleware(access_mw)
    dp.callback_query.middleware(access_mw)
    dp.message.middleware(NotificationQuietMiddleware(seconds=1800))
    dp.callback_query.middleware(NotificationQuietMiddleware(seconds=1800))

    await _set_bot_commands(bot)

    db = await open_db(settings.db_path)

    # migrations
    await run_migrations(db)

    # scheduler
    scheduler = setup_notify_scheduler(bot, db)
    scheduler.start()

    for r in get_routers():
        dp.include_router(r)

    logger.info("Bot started")
    try:
        await dp.start_polling(bot, db=db)
    finally:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())