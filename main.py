import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import SimpleEventIsolation
from loguru import logger

from app.config.settings import settings
from app.db.connection import open_db
from app.db.migrate import run_migrations
from app.handlers import get_routers
from app.logging.setup import setup_logging
from app.scheduler.notify_scheduler import setup_notify_scheduler


async def main():
    setup_logging(settings.debug)

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(events_isolation=SimpleEventIsolation())

    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="today", description="Отчёт: сегодня"),
        BotCommand(command="week", description="Отчёт: неделя"),
        BotCommand(command="month", description="Отчёт: месяц"),
        BotCommand(command="cats_today", description="Категории: сегодня"),
        BotCommand(command="cats_month", description="Категории: месяц"),
    ])

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