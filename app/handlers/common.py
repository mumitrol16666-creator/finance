from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, LabeledPrice, PreCheckoutQuery
import aiosqlite

from app.config.settings import settings

from app.db.repositories.users_repo import get_onboarded
from app.ui.keyboards import main_menu, recurring_hub_kb, planning_hub_kb, more_hub_kb, newbie_menu, newbie_menu_level2, full_menu, upgrade_info_kb, cancel_kb, minimized_menu_kb
from app.db.repositories.settings_repo import get_lang
from app.db.repositories.users_repo import grant_full_access
from app.db.repositories.accounts_repo import list_accounts
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
from app.db.repositories.planned_repo import list_planned
from app.db.repositories.recurring_repo import list_recurring_expenses, list_recurring_incomes
from app.db.repositories.debts_repo import count_active_debts
from app.ui.i18n import text_matches_key, t
router = Router()


async def build_main_menu_markup(db: aiosqlite.Connection | None, user_id: int, lang: str):
    if db is None:
        return main_menu(lang)

    variant, progress_level, _full_access, expiration_date = await get_menu_context(db, user_id)
    
    days_left = None
    if expiration_date:
        from datetime import date as _date
        from app.domain.time_utils import today_in_user_tz
        try:
            exp = _date.fromisoformat(expiration_date)
            days_left = (exp - await today_in_user_tz(db, user_id)).days
            # Ensure it's not negative for the UI if we want to show '0' or treat it as expired
            if days_left < 0:
                days_left = 0
        except Exception:
            pass

    if variant == "full" or expiration_date is not None:
        return full_menu(lang, days_left=days_left)

    if progress_level >= 2:
        return newbie_menu_level2(lang, days_left=days_left)

    return newbie_menu(lang, days_left=days_left)




async def _build_planning_hub_markup(db: aiosqlite.Connection, user_id: int, lang: str):
    return planning_hub_kb(
        lang,
        show_planned=True,
        show_recurring=True,
        show_debts=True,
    )


async def _build_more_hub_markup(db: aiosqlite.Connection, user_id: int, lang: str):
    return more_hub_kb(
        lang,
        show_accounts=True,
        show_transfer=True,
    )


async def _more_hub_text(db: aiosqlite.Connection, user_id: int, lang: str) -> str:
    active = await list_accounts(db, user_id)
    all_rows = await list_accounts(db, user_id, include_archived=True)
    archived_count = max(0, len(all_rows) - len(active))
    
    # row[2] = balance, row[4] = currency, row[5] = is_saving
    active_regular = [r for r in active if not r[5]]
    savings = [r for r in active if r[5]]
    
    # Calculate totals per currency for regular accounts
    currency_totals = {}
    for r in active_regular:
        curr = r[4] or "KZT"
        currency_totals[curr] = currency_totals.get(curr, 0) + int(r[2] or 0)
    
    # Format the total string
    from app.domain.money import fmt_money_compact
    if not currency_totals:
        fmt_total = fmt_money_compact(0, "KZT")
    else:
        fmt_total = ", ".join([fmt_money_compact(val, curr) for curr, val in currency_totals.items()])

    title = t(lang, "MORE_HUB_TITLE")
    
    stats = {
        "ru": f"💰 Общий баланс: <b>{fmt_total}</b>\n💳 Активных счетов: <b>{len(active)}</b>",
        "en": f"💰 Total balance: <b>{fmt_total}</b>\n💳 Active accounts: <b>{len(active)}</b>",
        "kk": f"💰 Жалпы баланс: <b>{fmt_total}</b>\n💳 Белсенді шоттар: <b>{len(active)}</b>",
    }.get(lang, f"💰 Общий баланс: <b>{fmt_total}</b>\n💳 Активных счетов: <b>{len(active)}</b>")
    
    if archived_count > 0:
        arch_text = {
            "ru": f"\n🗄 В архиве: <b>{archived_count}</b>",
            "en": f"\n🗄 Archived: <b>{archived_count}</b>",
            "kk": f"\n🗄 Архивте: <b>{archived_count}</b>",
        }.get(lang, f"\n🗄 В архиве: <b>{archived_count}</b>")
        stats += arch_text

    return f"{title}\n\n{stats}"


async def _get_planning_hint(db: aiosqlite.Connection, user_id: int, lang: str) -> str:
    planned = await list_planned(db, user_id)
    recurring_exp = await list_recurring_expenses(db, user_id)
    recurring_inc = await list_recurring_incomes(db, user_id)
    debts_count = await count_active_debts(db, user_id)

    hints = []
    if lang == "kk":
        if not planned:
            hints.append("• 🗓 <b>Жоспарланған шығындарды</b> (жалдау, жазылымдар) қосыңыз, бот оларды еске салады.")
        if not (recurring_exp or recurring_inc):
            hints.append("• 🔁 <b>Тұрақты төлемдерді</b> баптаңыз, оларды ай сайын қолмен енгізбеу үшін.")
        if debts_count == 0:
            hints.append("• 💳 <b>Қарыздар мен кредиттерді</b> жазыңыз, өтеу кестесін қадағалау үшін.")
        header = "\n\n💡 <b>Ұсыныс:</b>\n"
    elif lang == "en":
        if not planned:
            hints.append("• 🗓 Add <b>planned expenses</b> (rent, subscriptions) so the bot can remind you.")
        if not (recurring_exp or recurring_inc):
            hints.append("• 🔁 Set up <b>recurring payments</b> to avoid manual entry every month.")
        if debts_count == 0:
            hints.append("• 💳 Log <b>debts or credits</b> to track the repayment schedule.")
        header = "\n\n💡 <b>Recommendation:</b>\n"
    else:
        if not planned:
            hints.append("• 🗓 Добавь <b>запланированные траты</b> (аренда, подписки), чтобы бот напомнил о них.")
        if not (recurring_exp or recurring_inc):
            hints.append("• 🔁 Настрой <b>регулярные платежи</b>, чтобы не вводить их вручную каждый месяц.")
        if debts_count == 0:
            hints.append("• 💳 Запиши <b>долги или кредиты</b>, чтобы следить за графиком погашения.")
        header = "\n\n💡 <b>Рекомендация:</b>\n"

    if not hints:
        return ""
    
    return header + "\n".join(hints)


async def _open_hub(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection, *, scope: str):
    data = await state.get_data()
    lang = await get_lang(db, target.from_user.id)

    if scope == "planning":
        text = t(lang, "PLANNING_HUB_TITLE")
        hint = await _get_planning_hint(db, target.from_user.id, lang)
        text += hint
        markup = await _build_planning_hub_markup(db, target.from_user.id, lang)
    else:
        text = await _more_hub_text(db, target.from_user.id, lang)
        markup = await _build_more_hub_markup(db, target.from_user.id, lang)

    if isinstance(target, CallbackQuery) and data.get("flow_message_id"):
        # We are already in an inline flow, just edit the text
        try:
            await target.bot.edit_message_text(
                chat_id=target.message.chat.id,
                message_id=int(data["flow_message_id"]),
                text=text,
                reply_markup=markup,
                parse_mode="HTML"
            )
            await state.update_data(ui_scope=f"hub:{scope}", lang=lang)
            await target.answer()
            return
        except Exception:
            pass

    # Fallback if no flow_message_id or if called from a Message
    if isinstance(target, CallbackQuery):
        await neutralize_keyboard(target)
        await _cleanup_ui(target.bot, target.message.chat.id, data)
    else:
        await _cleanup_ui(target.bot, target.chat.id, data)
        try:
            await target.delete()
        except Exception:
            pass

    await state.clear()
    sender = target.message.answer if isinstance(target, CallbackQuery) else target.answer
    sent = await sender(text, reply_markup=markup, parse_mode="HTML")
    await state.update_data(flow_message_id=sent.message_id, ui_scope=f"hub:{scope}", lang=lang)
    await _ensure_minimized_menu(target, state, lang)
    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
        except Exception:
            pass


async def deny_feature_message(ctx: Message | CallbackQuery, db: aiosqlite.Connection, user_id: int) -> None:
    lang = await get_lang(db, user_id)
    from app.db.repositories.users_repo import is_promo_used, is_eligible_for_trial_3d
    promo_used = await is_promo_used(db, user_id)
    show_trial = await is_eligible_for_trial_3d(db, user_id)
    
    text = _upgrade_message(lang, promo_used=promo_used)
    markup = upgrade_info_kb(lang, promo_used=promo_used, show_trial_btn=show_trial)
    
    if isinstance(ctx, CallbackQuery):
        await neutralize_keyboard(ctx)
        # We try to answer the callback so it doesn't spin
        try:
            await ctx.answer()
        except Exception:
            pass
        # Then we send a new message with the upgrade info
        await ctx.message.answer(text, reply_markup=markup, parse_mode="HTML")
        return
        
    await ctx.answer(text, reply_markup=markup, parse_mode="HTML")




async def neutralize_keyboard(c: CallbackQuery) -> None:
    """Drop the inline keyboard of the source message *before* doing any work.

    This is the single most effective defense against double-tap on terminal
    callbacks (``save``, ``confirm``, ``pay``, ``delete``): once the keyboard
    is gone, the second tap can't fire the same callback again. We swallow all
    Telegram errors because the message might already be edited / deleted, in
    which case there is nothing to neutralize.
    """
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


def is_cancel_text(text: str | None) -> bool:
    raw = (text or '').strip().casefold()
    for token in ('❌', '⛔', '✖', '✕', '×'):
        raw = raw.replace(token, '')
    raw = ' '.join(raw.split())
    return raw in {'отмена', 'отменить', '/cancel', 'cancel', 'болдырмау'}

def is_main_menu_text(text: str | None) -> bool:
    raw = (text or '').strip().casefold()
    for token in ('🏠', ' '):
        raw = raw.replace(token, '')
    return raw in {'главноеменю', 'mainmenu', 'бастымәзір'}


_is_cancel_text = is_cancel_text


async def _cleanup_ui(bot, chat_id: int, data: dict) -> None:
    ids_to_collapse = [
        data.get('flow_message_id'),
        data.get('debt_screen_msg_id'),
        data.get('screen_message_id'),
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
    prompt_message_id = data.get('prompt_message_id')
    if isinstance(prompt_message_id, (list, tuple, set)):
        prompt_ids.extend(prompt_message_id)
    elif prompt_message_id:
        prompt_ids.append(prompt_message_id)

    extra_prompt_ids = data.get('extra_prompt_message_ids')
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


async def _ensure_minimized_menu(target: Message | CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    if data.get("settings_reply_message_id"):
        return
    sender = target.message.answer if isinstance(target, CallbackQuery) else target.answer
    text = {"ru": "Меню свернуто для удобства", "en": "Menu minimized for convenience", "kk": "Мәзір ыңғайлылық үшін жиналды"}.get(lang, "Меню свернуто для удобства")
    sent = await sender(text, reply_markup=minimized_menu_kb(lang), disable_notification=True)
    extra_ids = data.get("extra_prompt_message_ids") or []
    if not isinstance(extra_ids, list):
        extra_ids = [extra_ids]
    extra_ids = [x for x in extra_ids if x]
    extra_ids.append(sent.message_id)
    await state.update_data(settings_reply_message_id=sent.message_id, extra_prompt_message_ids=extra_ids)


async def consume_user_input(m: Message, state: FSMContext) -> None:
    """Clean chat noise after a successful FSM text input.

    Deletes (best-effort) both the message the user just sent and the prompt
    bot message stored under ``prompt_message_id`` in FSM data. This keeps the
    "flow window" pinned at the top instead of letting the user's own message
    push the bot's instructions out of view — the pattern we already use in
    onboarding/settings, generalized for planning flows.
    """
    data = await state.get_data()
    prompt_id = data.get("prompt_message_id")
    try:
        if prompt_id:
            await m.bot.delete_message(chat_id=m.chat.id, message_id=int(prompt_id))
    except Exception:
        pass
    try:
        await m.delete()
    except Exception:
        pass
    if prompt_id:
        await state.update_data(prompt_message_id=None)


async def cancel_to_main_menu(ctx: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection | None = None) -> None:
    data = await state.get_data()
    user_id = ctx.from_user.id
    lang = "ru"
    try:
        if db is not None:
            lang = await get_lang(db, user_id)
    except Exception:
        pass

    if isinstance(ctx, CallbackQuery):
        await _cleanup_ui(ctx.bot, ctx.message.chat.id, data)
        await state.clear()
        menu_text = await build_main_menu_text(db, user_id, lang) if db is not None else t(lang, "MENU_LABEL")
        await ctx.message.answer(menu_text, reply_markup=await build_main_menu_markup(db, user_id, lang), parse_mode="HTML")
        try:
            await ctx.answer()
        except Exception:
            pass
        return

    await _cleanup_ui(ctx.bot, ctx.chat.id, data)

    try:
        await ctx.delete()
    except Exception:
        pass

    await state.clear()
    menu_text = await build_main_menu_text(db, user_id, lang) if db is not None else t(lang, "MENU_LABEL")
    await ctx.answer(menu_text, reply_markup=await build_main_menu_markup(db, user_id, lang), parse_mode="HTML")


@router.message(F.text.casefold().in_({'меню', 'menu'}))
@router.message(F.text == '/menu')
async def menu_any(m: Message, state: FSMContext, db: aiosqlite.Connection):
    data = await state.get_data()
    await _cleanup_ui(m.bot, m.chat.id, data)
    await state.clear()
    lang = await get_lang(db, m.from_user.id)
    menu_text = await build_main_menu_text(db, m.from_user.id, lang)
    await m.answer(menu_text, reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode="HTML")


@router.message(Command("cancel"))
async def cancel_command(m: Message, state: FSMContext, db: aiosqlite.Connection):
    """Global /cancel — works over any FSM state."""
    await cancel_to_main_menu(m, state, db)


@router.message(lambda m: is_cancel_text(getattr(m, 'text', None)))
@router.message(lambda m: is_main_menu_text(getattr(m, 'text', None)))
async def cancel_any(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await cancel_to_main_menu(m, state, db)


@router.callback_query(F.data == 'cancel')
@router.callback_query(F.data.endswith(':cancel'))
async def cancel_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await cancel_to_main_menu(c, state, db)


async def require_onboarded(db: aiosqlite.Connection, user_id: int) -> bool:
    ob = await get_onboarded(db, user_id)
    return ob == 1


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_MORE"))
async def more_hub_entry(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await _open_hub(m, state, db, scope="more")


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_PLANNING"))
async def planning_hub_entry(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await _open_hub(m, state, db, scope="planning")


@router.callback_query(F.data == "hub:planning")
async def planning_hub_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _open_hub(c, state, db, scope="planning")


@router.callback_query(F.data == "hub:more")
async def more_hub_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _open_hub(c, state, db, scope="more")


@router.callback_query(F.data == "hub:main")
async def hub_main(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    await cancel_to_main_menu(c, state, db)


@router.callback_query(F.data == "more:history")
async def more_history(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_HISTORY):
        await deny_feature_message(c, db, c.from_user.id)
        return
    from app.handlers.history import _render_history
    lang = await get_lang(db, c.from_user.id)
    await state.set_state(None)
    await state.update_data(ui_scope="history", lang=lang)
    await _ensure_minimized_menu(c, state, lang)
    await _render_history(c, db, c.from_user.id, offset=0, prefer_edit=True, state=state)


@router.callback_query(F.data == "more:accounts")
async def more_accounts(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_ACCOUNTS):
        await deny_feature_message(c, db, c.from_user.id)
        return
    from app.handlers.settings import _go_accounts_menu
    lang = await get_lang(db, c.from_user.id)
    await state.set_state(None)
    await state.update_data(ui_scope="settings", lang=lang, settings_return_to="accounts_menu")
    await _go_accounts_menu(c, state, db)
    await c.answer()


@router.callback_query(F.data == "more:transfer")
async def more_transfer(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_TRANSFER):
        await deny_feature_message(c, db, c.from_user.id)
        return
    from app.handlers.transactions import _clear_flow_message, _tr_render_amount
    from app.fsm.states import TransferFlow
    lang = await get_lang(db, c.from_user.id)
    await _clear_flow_message(c.bot, c.message.chat.id, state)
    await state.clear()
    await state.update_data(ui_scope="transfer", lang=lang)
    await _ensure_minimized_menu(c, state, lang)
    await state.set_state(TransferFlow.amount)
    await _tr_render_amount(c, state)


def _full_access_price() -> int:
    return int(getattr(settings, "full_access_stars_price", 150))


def _full_access_days() -> int:
    return int(getattr(settings, "full_access_days", 90))


def _upgrade_message(lang: str, has_full_access: bool = False, promo_used: bool = False) -> str:
    if lang == "en":
        greeting = "🌟 <b>Full access activated!</b>" if has_full_access else "You are currently using the free mode."
        price_1m = "15 ⭐ (One-time offer)" if not promo_used else "70 ⭐"
        price_3m = "150 ⭐"
        return (
            "✨ <b>Full access</b>\n\n"
            f"{greeting}\n\n"
            "<b>Available for free</b>\n"
            "• income and expense tracking\n"
            "• history\n"
            "• accounts\n"
            "• settings\n"
            "• basic daily and weekly reports\n\n"
            "<b>Full access unlocks</b>\n"
            "• transfers between accounts\n"
            "• planned operations\n"
            "• recurring income and expenses\n"
            "• debts and credits\n"
            "• budgets and limits\n"
            "• category reports\n"
            "• monthly reports\n"
            "• AI consultant\n\n"
            "<b>Subscription pricing:</b>\n"
            f"• <b>1 month</b> — {price_1m}\n"
            f"• <b>3 months</b> — {price_3m}\n\n"
            "Press one of the buttons below to renew or unlock full access."
        )

    if lang == "kk":
        greeting = "🌟 <b>Толық қолжетімділік белсенді!</b>" if has_full_access else "Қазір сен тегін режимді қолданып отырсың."
        price_1m = "15 ⭐ (Бір реттік акция)" if not promo_used else "70 ⭐"
        price_3m = "150 ⭐"
        return (
            "✨ <b>Толық қолжетімділік</b>\n\n"
            f"{greeting}\n\n"
            "<b>Тегін режимде қолжетімді</b>\n"
            "• кіріс пен шығысты енгізу\n"
            "• тарих\n"
            "• шоттар\n"
            "• баптаулар\n"
            "• күндік және апталық негізгі есептер\n\n"
            "<b>Толық қолжетімділікте ашылады</b>\n"
            "• шоттар арасындағы аударымдар\n"
            "• жоспарланған операциялар\n"
            "• тұрақты кірістер мен шығыстар\n"
            "• қарыздар мен кредиттер\n"
            "• бюджеттер мен лимиттер\n"
            "• санаттар бойынша есептер\n"
            "• айлық есептер\n"
            "• AI-кеңесші\n\n"
            "<b>Жазылым құны:</b>\n"
            f"• <b>1 ай</b> — {price_1m}\n"
            f"• <b>3 ай</b> — {price_3m}\n\n"
            "Толық қолжетімділікті ашу немесе ұзарту үшін төмендегі батырмалардың бірін бас."
        )

    greeting = "🌟 <b>У тебя активирован полный доступ!</b>" if has_full_access else "Сейчас ты пользуешься бесплатной версией."
    price_1m = "15 ⭐ (Разовая акция)" if not promo_used else "70 ⭐"
    price_3m = "150 ⭐"
    return (
        "✨ <b>Полный доступ</b>\n\n"
        f"{greeting}\n\n"
        "<b>Доступно бесплатно:</b>\n"
        "• запись расходов и доходов\n"
        "• ведение основных счетов\n"
        "• отмена последней записи\n"
        "• базовые дневные и недельные отчеты\n\n"
        "<b>Открывается в Premium:</b>\n"
        "• AI-Консультант с персональными советами\n"
        "• продвинутые лимиты и бюджеты\n"
        "• переводы между счетами\n"
        "• подкатегории и месячные отчеты\n"
        "• учет долгов и регулярных платежей\n\n"
        "<b>Стоимость подписки:</b>\n"
        f"• <b>1 месяц</b> — {price_1m}\n"
        f"• <b>3 месяца</b> — {price_3m}\n\n"
        "Это инвестиция в финансовую дисциплину, которая окупается в первый же месяц.\n\n"
        "👇 Нажми на одну из кнопок ниже, чтобы снять все лимиты прямо сейчас."
    )


def _invoice_description(lang: str) -> str:
    days = _full_access_days()

    if lang == "en":
        return f"Full access to all bot sections for {days} days."

    if lang == "kk":
        return f"Боттың барлық бөлімдеріне {days} күнге толық қолжетімділік."

    return f"Полный доступ ко всем разделам бота на {days} дней."


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_UPGRADE_FULL") or (m.text and any(x in m.text for x in ["🌟 Полный режим", "🌟 Full Mode", "🌟 Толық режим", "💎 Продлить подписку", "💎 Upgrade / Renew", "💎 Жаңарту"])))
async def upgrade_info_message(m: Message, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)

    data = await state.get_data()
    await _cleanup_ui(m.bot, m.chat.id, data)

    try:
        await m.delete()
    except Exception:
        pass

    await state.clear()

    await _ensure_minimized_menu(m, state, lang)

    from app.domain.services.access_service import get_user_context
    from app.db.repositories.users_repo import is_promo_used, is_eligible_for_trial_3d
    ctx = await get_user_context(db, m.from_user.id)
    promo_used = await is_promo_used(db, m.from_user.id)
    show_trial = await is_eligible_for_trial_3d(db, m.from_user.id)

    sent = await m.answer(
        _upgrade_message(lang, has_full_access=ctx.full_access, promo_used=promo_used),
        parse_mode="HTML",
        reply_markup=upgrade_info_kb(lang, promo_used=promo_used, show_trial_btn=show_trial),
    )

    await state.update_data(
        flow_message_id=sent.message_id,
        ui_scope="upgrade",
        lang=lang,
    )


@router.callback_query(lambda c: c.data in {"upgrade:info", "upgrade:open"})
async def upgrade_info_callback(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    lang = await get_lang(db, c.from_user.id)

    data = await state.get_data()
    await _cleanup_ui(c.bot, c.message.chat.id, data)
    await state.clear()

    await _ensure_minimized_menu(c, state, lang)

    from app.domain.services.access_service import get_user_context
    from app.db.repositories.users_repo import is_promo_used, is_eligible_for_trial_3d
    ctx = await get_user_context(db, c.from_user.id)
    promo_used = await is_promo_used(db, c.from_user.id)
    show_trial = await is_eligible_for_trial_3d(db, c.from_user.id)

    sent = await c.message.answer(
        _upgrade_message(lang, has_full_access=ctx.full_access, promo_used=promo_used),
        parse_mode="HTML",
        reply_markup=upgrade_info_kb(lang, promo_used=promo_used, show_trial_btn=show_trial),
    )

    await state.update_data(
        flow_message_id=sent.message_id,
        ui_scope="upgrade",
        lang=lang,
    )

    await c.answer()


@router.callback_query(F.data == "upgrade:trial_3d")
async def upgrade_trial_3d(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    user_id = c.from_user.id
    lang = await get_lang(db, user_id)

    from app.domain.services.access_service import get_user_context
    from app.db.repositories.users_repo import is_eligible_for_trial_3d, mark_trial_3d_claimed, grant_full_access
    ctx = await get_user_context(db, user_id)
    eligible = await is_eligible_for_trial_3d(db, user_id)

    if ctx.full_access or not eligible:
        msg = {
            "ru": "⚠️ Вы не подходите под условия пробного периода или у вас уже активен Premium.",
            "en": "⚠️ You do not qualify for the trial period or Premium is already active.",
            "kk": "⚠️ Сіз сынақ мерзіміне сәйкес келмейсіз немесе сізде Premium белсенді."
        }.get(lang, "⚠️ Вы не подходите под условия пробного периода или у вас уже активен Premium.")
        await c.message.answer(msg)
        await c.answer()
        return

    try:
        await mark_trial_3d_claimed(db, user_id)
        await grant_full_access(db, user_id, days=3)
        await db.commit()
    except Exception as e:
        await db.rollback()
        from loguru import logger
        logger.exception("Failed to activate 3-day trial: {}", e)
        error_msg = {
            "ru": "⚠️ Ошибка при активации пробного периода. Попробуйте позже.",
            "en": "⚠️ Error activating trial period. Please try again later.",
            "kk": "⚠️ Сынақ мерзімін белсендіру қатесі. Кейінірек көріңіз."
        }.get(lang, "⚠️ Ошибка при активации пробного периода. Попробуйте позже.")
        await c.message.answer(error_msg)
        await c.answer()
        return

    success_msg = {
        "ru": (
            "🎉 <b>Добро пожаловать в Premium!</b>\n\n"
            "Вам бесплатно предоставлен пробный Premium-доступ на <b>3 дня</b>.\n"
            "Попробуйте все функции: голосовой ввод, AI-консультант, переводы между счетами, лимиты и бюджеты!"
        ),
        "en": (
            "🎉 <b>Welcome to Premium!</b>\n\n"
            "You have been granted a free <b>3-day trial</b> of Premium.\n"
            "Try all the features: voice input, AI consultant, transfers, limits and budgets!"
        ),
        "kk": (
            "🎉 <b>Premium-ға қош келдіңіз!</b>\n\n"
            "Сізге <b>3 күндік</b> тегін Premium сынақ мерзімі берілді.\n"
            "Барлық мүмкіндіктерді байқап көріңіз: дауыстық енгізу, AI-кеңесші, аударымдар, лимиттер мен бюджеттер!"
        )
    }.get(lang, "🎉 <b>Добро пожаловать в Premium!</b>")

    await state.clear()
    await c.message.answer(success_msg, parse_mode="HTML")

    from app.handlers.common import build_main_menu_markup
    from app.domain.services.ai_consultant_service import build_main_menu_text
    menu_text = await build_main_menu_text(db, user_id, lang)
    await c.message.answer(menu_text, reply_markup=await build_main_menu_markup(db, user_id, lang), parse_mode="HTML")
    await c.answer()


@router.callback_query(F.data.startswith("upgrade:activate"))
async def upgrade_activate(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    lang = await get_lang(db, c.from_user.id)

    pkg = "3m"
    parts = c.data.split(":")
    if len(parts) > 2:
        pkg = parts[2]
        
    if pkg == "1m":
        days = 30
        from app.db.repositories.users_repo import is_promo_used
        promo_used = await is_promo_used(db, c.from_user.id)
        price = 15 if not promo_used else 70
        label = "Premium 1 месяц" if lang == "ru" else ("Premium 1 month" if lang == "en" else "Premium 1 ай")
    else:
        days = 90
        price = 150
        label = "Premium 3 месяца" if lang == "ru" else ("Premium 3 months" if lang == "en" else "Premium 3 ай")

    desc = {
        "ru": f"Полный доступ ко всем разделам бота на {days} дней.",
        "en": f"Full access to all bot sections for {days} days.",
        "kk": f"Боттың барлық бөлімдеріне {days} күнге толық қолжетімділік.",
    }.get(lang, f"Полный доступ ко всем разделам бота на {days} дней.")

    await c.bot.send_invoice(
        chat_id=c.from_user.id,
        title=label,
        description=desc[:255],
        payload=f"full_access_upgrade:{days}",
        provider_token="",
        currency="XTR",
        prices=[
            LabeledPrice(
                label=label,
                amount=price,
            )
        ],
    )

    await c.answer()


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    payload = pre_checkout_query.invoice_payload or ""
    if payload.startswith("full_access_upgrade") or payload == "ai_chat_extra_messages" or payload == "ai_reports_extra_pack" or payload.startswith("export_single:"):
        await pre_checkout_query.answer(ok=True)
    else:
        await pre_checkout_query.answer(ok=False, error_message="Unknown payment type")


@router.message(F.successful_payment)
async def process_successful_payment(m: Message, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)
    payload = m.successful_payment.invoice_payload

    if payload == "ai_reports_extra_pack":
        from app.db.repositories.settings_repo import add_ai_reports_extra
        from datetime import datetime as _dt, timezone as _tz
        try:
            await add_ai_reports_extra(db, m.from_user.id, 5, _dt.now(_tz.utc).isoformat())
            await db.commit()
        except Exception:
            await db.rollback()
            await m.answer("⚠️ Error adding reports." if lang == "en" else ("⚠️ Есептер қосу қатесі." if lang == "kk" else "⚠️ Ошибка при добавлении отчетов."))
            return
        success = {
            "ru": "✅ <b>+5 глубоких разборов добавлено!</b>\n\nМожешь запустить новый разбор.",
            "en": "✅ <b>+5 deep reports added!</b>\n\nYou can start a new report.",
            "kk": "✅ <b>+5 терең талдау қосылды!</b>\n\nЖаңа талдауды бастауға болады.",
        }.get(lang, "✅ <b>+5 глубоких разборов добавлено!</b>")
        await m.answer(success, parse_mode="HTML")
        return

    if payload == "ai_chat_extra_messages":
        from app.db.repositories.settings_repo import add_ai_chat_extra
        from datetime import datetime as _dt, timezone as _tz
        try:
            await add_ai_chat_extra(db, m.from_user.id, 50, _dt.now(_tz.utc).isoformat())
            await db.commit()
        except Exception:
            await db.rollback()
            await m.answer("⚠️ Error adding messages." if lang == "en" else ("⚠️ Хабарлама қосу қатесі." if lang == "kk" else "⚠️ Ошибка при добавлении сообщений."))
            return
        success = {
            "ru": "✅ <b>+50 сообщений добавлено!</b>\n\nМожешь продолжить общение с AI.",
            "en": "✅ <b>+50 messages added!</b>\n\nYou can continue chatting with AI.",
            "kk": "✅ <b>+50 хабарлама қосылды!</b>\n\nAI-мен сөйлесуді жалғастыра аласыз.",
        }.get(lang, "✅ <b>+50 сообщений добавлено!</b>")
        await m.answer(success, parse_mode="HTML")
        return

    if payload.startswith("export_single:"):
        period = payload.split(":")[-1]
        from app.handlers.export import send_premium_xlsx_report
        try:
            await send_premium_xlsx_report(m.bot, db, m.from_user.id, period, lang, m.chat.id)
        except Exception as e:
            from loguru import logger
            logger.error(f"Failed to generate and send paid export: {e}")
            await m.answer("⚠️ Error generating report." if lang == "en" else ("⚠️ Есепті құру қатесі." if lang == "kk" else "⚠️ Ошибка при создании отчета."))
        return

    if not payload.startswith("full_access_upgrade"):
        return

    data = await state.get_data()
    days = 90
    parts = payload.split(":")
    if len(parts) > 1 and parts[1].isdigit():
        days = int(parts[1])
    else:
        days = _full_access_days()

    try:
        await _cleanup_ui(m.bot, m.chat.id, data)
        await grant_full_access(db, m.from_user.id, days=days)
        if days == 30:
            from app.db.repositories.users_repo import mark_promo_used
            await mark_promo_used(db, m.from_user.id)
        from datetime import datetime as _dt, timezone as _tz
        now_str = _dt.now(_tz.utc).isoformat()
        await db.execute(
            "UPDATE settings SET trial_reminder_sent = 0, updated_at = ? WHERE user_id = ?",
            (now_str, m.from_user.id)
        )
        await db.commit()
    except Exception:
        await db.rollback()

        error_text = {
            "ru": "⚠️ Ошибка при активации доступа. Напиши администратору.",
            "en": "⚠️ Access activation error. Please contact the administrator.",
            "kk": "⚠️ Қолжетімділікті қосу кезінде қате болды. Әкімшіге жазыңыз.",
        }.get(lang, "⚠️ Ошибка при активации доступа. Напиши администратору.")

        await m.answer(error_text)
        return

    await state.clear()

    success_text = {
        "ru": (
            "✅ <b>Полный доступ активирован</b>\n\n"
            "Теперь доступны все разделы бота."
        ),
        "en": (
            "✅ <b>Full access enabled</b>\n\n"
            "All bot sections are now available."
        ),
        "kk": (
            "✅ <b>Толық қолжетімділік қосылды</b>\n\n"
            "Енді боттың барлық бөлімдері қолжетімді."
        ),
    }.get(
        lang,
        "✅ <b>Полный доступ активирован</b>\n\nТеперь доступны все разделы бота.",
    )

    menu_text = await build_main_menu_text(db, m.from_user.id, lang)

    await m.answer(
        success_text,
        parse_mode="HTML",
    )

    await m.answer(
        menu_text,
        parse_mode="HTML",
        reply_markup=await build_main_menu_markup(db, m.from_user.id, lang),
    )
