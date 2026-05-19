from __future__ import annotations
import asyncio
import aiosqlite
from aiogram import F, Router, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from loguru import logger

from app.config.settings import settings
from app.db.repositories.users_repo import get_all_active_users

router = Router()

def make_teaser_preview(text: str) -> str:
    """
    Формирует превью текста поста: берет первые 200 символов,
    если длиннее — обрезает до ближайшего пробела и добавляет многоточие.
    """
    if len(text) <= 200:
        return text
    truncated = text[:200]
    last_space = truncated.rfind(' ')
    if last_space != -1:
        truncated = truncated[:last_space]
    return truncated + "..."

async def run_teaser_broadcast(bot: Bot, db: aiosqlite.Connection, teaser_text: str, reply_markup: InlineKeyboardMarkup):
    """
    Безопасная фоновая рассылка тизера с задержкой 0.05 сек между сообщениями
    для предотвращения FloodWait ошибок лимита Telegram.
    """
    try:
        logger.info("Starting teaser broadcast...")
        user_ids = await get_all_active_users(db)
        logger.info(f"Found {len(user_ids)} active users for teaser broadcast.")
        
        success_count = 0
        fail_count = 0
        
        for user_id in user_ids:
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=teaser_text,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
                success_count += 1
            except Exception as e:
                logger.warning(f"Failed to send teaser to user {user_id}: {e}")
                fail_count += 1
            
            # Предотвращение FloodWait лимитов Telegram (макс. 30 сообщ/сек)
            await asyncio.sleep(0.05)
            
        logger.info(f"Teaser broadcast completed. Success: {success_count}, Failed: {fail_count}")
    except Exception as e:
        logger.error(f"Error in teaser broadcast: {e}")

@router.channel_post(F.chat.id == settings.main_channel_id)
async def channel_post_handler(message: Message, bot: Bot, db: aiosqlite.Connection):
    """
    Хэндлер перехвата новых постов из основного Telegram-канала.
    """
    text = message.text or message.caption
    if not text:
        logger.info("Channel post ignored because it has no text or caption.")
        return

    logger.info(f"Received channel post from chat {message.chat.id}. Truncating teaser...")
    teaser_text = make_teaser_preview(text)
    
    # Формируем кнопку со ссылкой на оригинальный пост
    try:
        post_url = message.get_url()
    except Exception as e:
        logger.error(f"Failed to get post URL: {e}")
        return

    reply_markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Читать далее ➡️", url=post_url)
            ]
        ]
    )
    
    # Запускаем рассылку в фоновой задаче, чтобы мгновенно завершить хэндлер
    asyncio.create_task(run_teaser_broadcast(bot, db, teaser_text, reply_markup))
