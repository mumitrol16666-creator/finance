from __future__ import annotations

import aiosqlite
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repositories.settings_repo import get_lang
from app.db.repositories.recurring_repo import create_recurring_expense, create_recurring_income
from app.domain.services.access_service import FEATURE_PLANNED, can_use_feature
from app.handlers.common import deny_feature_message, cancel_to_main_menu
from app.ui.i18n import t
from app.ui.formatters import fmt_money
from datetime import datetime, timezone

router = Router()

@router.callback_query(F.data == "hub:smart_suggest")
async def smart_suggest_start(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, *, already_answered: bool = False):
    if not await can_use_feature(db, c.from_user.id, FEATURE_PLANNED):
        await deny_feature_message(c, db, c.from_user.id)
        return

    lang = await get_lang(db, c.from_user.id)
    # Only acknowledge the callback the first time we enter the handler.
    # Re-entrant callers (see smart_add_confirm) already answered with the
    # success alert and must not call c.answer() twice on the same callback.
    if not already_answered:
        try:
            await c.answer(t(lang, "BTN_SMART_SUGGEST"))
        except Exception:
            pass
    
    from app.domain.services.ai_consultant_service import discover_recurring_candidates
    candidates = await discover_recurring_candidates(db, c.from_user.id)
    
    if not candidates:
        text = {
            "ru": "🔍 <b>Поиск регулярных трат</b>\n\nЯ проанализировал твою историю за последние 3 месяца, но не нашёл очевидных повторов или ключевых слов (аренда, подписки и т.д.), которых ещё нет в твоём списке.",
            "en": "🔍 <b>Search for recurring items</b>\n\nI've analyzed your history for the last 3 months but didn't find any obvious repeats or keywords (rent, subscriptions, etc.) that aren't already in your list.",
            "kk": "🔍 <b>Тұрақтыларды іздеу</b>\n\nМен соңғы 3 айдағы тарихыңызды талдадым, бірақ тізіміңізде жоқ қайталанатын немесе кілт сөздерді (жалдау, жазылымдар және т.б.) таппадым.",
        }.get(lang, "🔍")
        
        kb = InlineKeyboardBuilder()
        kb.button(text=t(lang, "BTN_BACK"), callback_data="hub:planning")
        try:
            await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                raise e
        return

    text = {
        "ru": "✨ <b>Умные предложения</b>\n\nЯ нашёл операции, которые похожи на регулярные. Нажми на нужную, чтобы быстро добавить её в список постоянных платежей:",
        "en": "✨ <b>Smart Suggestions</b>\n\nI found transactions that look recurring. Click on one to quickly add it to your recurring list:",
        "kk": "✨ <b>Ақылды ұсыныстар</b>\n\nМен тұрақтыға ұқсайтын операцияларды таптым. Тізімге тез қосу үшін біреуін таңдаңыз:",
    }.get(lang, "✨")

    kb = InlineKeyboardBuilder()
    for idx, cand in enumerate(candidates):
        prefix = "❓ " if cand.get("is_unsure") else ""
        label = f"{prefix}{cand['title']} ({fmt_money(cand['amount'])})"
        kb.button(text=label, callback_data=f"smart:add:{idx}")
    
    kb.button(text=t(lang, "BTN_BACK"), callback_data="hub:planning")
    kb.adjust(1)
    
    await state.update_data(smart_candidates=candidates)
    try:
        await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            raise e


@router.callback_query(F.data.startswith("smart:add:"))
async def smart_add_confirm(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    data = await state.get_data()
    candidates = data.get("smart_candidates")
    
    if not candidates:
        await c.answer("Error: session expired", show_alert=True)
        return

    try:
        idx = int(c.data.split(":")[-1])
        cand = candidates[idx]
        
        # Prevent double-click duplicates using unique ID
        processed_cids = data.get("processed_cids", [])
        if cand["cid"] in processed_cids:
            await c.answer("Already processed", show_alert=True)
            return
        
        # Add to processed list and update state
        processed_cids.append(cand["cid"])
        await state.update_data(processed_cids=processed_cids)
        
    except (ValueError, IndexError, KeyError):
        await c.answer("Not found", show_alert=True)
        return

    # Create the item
    ts = datetime.now(timezone.utc).isoformat()
    if cand["type"] == "expense":
        await create_recurring_expense(
            db, c.from_user.id, cand["title"], cand["amount"], 
            cand["category_id"], cand["account_id"], cand["day_of_month"], 
            f"Auto-detected from history (reason: {cand['reason']})", ts
        )
    else:
        await create_recurring_income(
            db, c.from_user.id, cand["title"], cand["amount"], 
            cand["category_id"], cand["account_id"], cand["day_of_month"], 
            f"Auto-detected from history (reason: {cand['reason']})", ts
        )
    
    await db.commit()
    
    success_text = {
        "ru": f"✅ Готово! <b>{cand['title']}</b> добавлен в регулярные операции (день: {cand['day_of_month']}).",
        "en": f"✅ Done! <b>{cand['title']}</b> added to recurring items (day: {cand['day_of_month']}).",
        "kk": f"✅ Дайын! <b>{cand['title']}</b> тұрақты операцияларға қосылды ({cand['day_of_month']} күн).",
    }.get(lang, "✅")
    
    await c.answer(success_text, show_alert=True)
    # Refresh the suggestions. The callback has already been answered above,
    # so signal the inner handler not to answer again (Telegram errors on a
    # second answer to the same callback_query_id).
    await smart_suggest_start(c, state, db, already_answered=True)
