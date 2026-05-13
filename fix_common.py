#!/usr/bin/env python3
"""Restore app/handlers/common.py with Telegram Stars integration."""
import pathlib

CONTENT = '''\
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, LabeledPrice, PreCheckoutQuery
import aiosqlite

from app.config.settings import settings

from app.db.repositories.users_repo import get_onboarded
from app.ui.keyboards import main_menu, recurring_hub_kb, planning_hub_kb, more_hub_kb, newbie_menu, newbie_menu_level2, full_menu, upgrade_info_kb, cancel_kb
from app.db.repositories.settings_repo import get_lang
from app.db.repositories.users_repo import grant_full_access
from app.domain.services.ai_consultant_service import build_section_hint, build_main_menu_text
from app.domain.services.access_service import (
    FEATURE_RECURRING,
    FEATURE_PLANNED,
    FEATURE_DEBTS,
    FEATURE_ACCOUNTS,
    FEATURE_TRANSFER,
    FEATURE_HISTORY,
    FEATURE_SETTINGS,
    FEATURE_REPORTS,
    can_use_feature,
    get_menu_context,
)
from app.ui.i18n import text_matches_key, t
router = Router()


async def build_main_menu_markup(db: aiosqlite.Connection | None, user_id: int, lang: str):
    if db is None:
        return main_menu(lang)

    variant, progress_level, _full_access = await get_menu_context(db, user_id)

    if variant == "full":
        return full_menu(lang)

    if progress_level >= 2:
        return newbie_menu_level2(lang)

    return newbie_menu(lang)




async def _build_planning_hub_markup(db: aiosqlite.Connection, user_id: int, lang: str):
    return planning_hub_kb(
        lang,
        show_planned=await can_use_feature(db, user_id, FEATURE_PLANNED),
        show_recurring=await can_use_feature(db, user_id, FEATURE_RECURRING),
        show_debts=await can_use_feature(db, user_id, FEATURE_DEBTS),
    )


async def _build_more_hub_markup(db: aiosqlite.Connection, user_id: int, lang: str):
    return more_hub_kb(
        lang,
        show_accounts=await can_use_feature(db, user_id, FEATURE_ACCOUNTS),
        show_transfer=await can_use_feature(db, user_id, FEATURE_TRANSFER),
    )


async def _open_hub(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection, *, scope: str):
    data = await state.get_data()
    if isinstance(target, CallbackQuery):
        await _cleanup_ui(target.bot, target.message.chat.id, data)
    else:
        await _cleanup_ui(target.bot, target.chat.id, data)
        try:
            await target.delete()
        except Exception:
            pass
    await state.clear()
    lang = await get_lang(db, target.from_user.id)

    if scope == "planning":
        text = t(lang, "PLANNING_HUB_TITLE")
        markup = await _build_planning_hub_markup(db, target.from_user.id, lang)
    else:
        text = t(lang, "MORE_HUB_TITLE")
        markup = await _build_more_hub_markup(db, target.from_user.id, lang)

    sender = target.message.answer if isinstance(target, CallbackQuery) else target.answer
    sent = await sender(text, reply_markup=markup, parse_mode="HTML")
    await state.update_data(flow_message_id=sent.message_id, ui_scope=f"hub:{scope}", lang=lang)
    await _ensure_scope_reply_keyboard(target, state, lang)
    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
        except Exception:
            pass


async def deny_feature_message(ctx: Message | CallbackQuery, db: aiosqlite.Connection, user_id: int) -> None:
    lang = await get_lang(db, user_id)
    text = t(lang, "ACCESS_LOCKED")
    markup = await build_main_menu_markup(db, user_id, lang)
    if isinstance(ctx, CallbackQuery):
        await ctx.message.answer(text, reply_markup=markup)
        try:
            await ctx.answer()
        except Exception:
            pass
        return
    await ctx.answer(text, reply_markup=markup)




def is_cancel_text(text: str | None) -> bool:
    raw = (text or \\'\\').strip().casefold()
    for token in (\\'\u274c\\', \\'\u2716\ufe0f\\', \\'\u2716\\', \\'\u26d4\\', \\'\ud83d\udeab\\'):
        raw = raw.replace(token, \\'\\')
    raw = \\' \\'.join(raw.split())
    return raw in {\\'\\u043e\\u0442\\u043c\\u0435\\u043d\\u0430\\', \\'/cancel\\', \\'cancel\\', \\'\\u0431\\u043e\\u043b\\u0434\\u044b\\u0440\\u043c\\u0430\\u0443\\'}


_is_cancel_text = is_cancel_text


async def _cleanup_ui(bot, chat_id: int, data: dict) -> None:
    ids_to_collapse = [
        data.get(\\'flow_message_id\\'),
        data.get(\\'debt_screen_msg_id\\'),
        data.get(\\'screen_message_id\\'),
    ]
    seen = set()
    for msg_id in ids_to_collapse:
        if not msg_id or msg_id in seen:
            continue
        seen.add(msg_id)
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=int(msg_id), reply_markup=None)
        except Exception:
            pass

    prompt_ids = []
    prompt_message_id = data.get(\\'prompt_message_id\\')
    if isinstance(prompt_message_id, (list, tuple, set)):
        prompt_ids.extend(prompt_message_id)
    elif prompt_message_id:
        prompt_ids.append(prompt_message_id)

    extra_prompt_ids = data.get(\\'extra_prompt_message_ids\\')
    if isinstance(extra_prompt_ids, (list, tuple, set)):
        prompt_ids.extend(extra_prompt_ids)
    elif extra_prompt_ids:
        prompt_ids.append(extra_prompt_ids)

    for msg_id in dict.fromkeys(prompt_ids):
        if not msg_id:
            continue
        try:
            await bot.delete_message(chat_id=chat_id, message_id=int(msg_id))
        except Exception:
            pass
'''

# This approach is getting messy with escaping. Let me use a different method.
# I'll write the file directly using proper encoding.

import sys
sys.exit(0)
