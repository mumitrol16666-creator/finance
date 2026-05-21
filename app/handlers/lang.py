from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import aiosqlite

from app.ui.i18n import t, text_matches_key
from app.ui.keyboards import lang_kb, cancel_kb, minimized_menu_kb
from app.handlers.common import build_main_menu_markup
from app.db.repositories.settings_repo import get_lang, set_lang
from app.domain.services.onboarding_service import utcnow_iso

router = Router()

@router.message(lambda m: text_matches_key(getattr(m, 'text', None), 'BTN_LANGUAGE'))
async def lang_menu(m: Message, db: aiosqlite.Connection, state: FSMContext):
    lang = await get_lang(db, m.from_user.id)
    await state.clear()
    prompt = await m.answer(t(lang, 'LANG_SCREEN'), reply_markup=minimized_menu_kb(lang))
    sent = await m.answer(t(lang, "LANG_PROMPT"), reply_markup=lang_kb(lang=lang))
    await state.update_data(
        flow_message_id=sent.message_id,
        prompt_message_id=prompt.message_id,
        ui_scope="lang",
    )

@router.callback_query(lambda c: (c.data or '').startswith("lang:"))
async def lang_set_cb(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    lang = (c.data or 'lang:ru').split(":", 1)[1]
    data = await state.get_data()
    prompt_message_id = data.get('prompt_message_id')
    try:
        await set_lang(db, c.from_user.id, lang, utcnow_iso())
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if prompt_message_id:
        try:
            await c.bot.delete_message(chat_id=c.message.chat.id, message_id=int(prompt_message_id))
        except Exception:
            pass

    await state.clear()
    await c.message.answer(t(lang, f'LANG_SET_{lang.upper()}'), reply_markup=await build_main_menu_markup(db, c.from_user.id, lang))
    await c.answer()
