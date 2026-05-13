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
    raw = (text or '').strip().casefold()
    for token in ('?', '??', '?', '?', '??'):
        raw = raw.replace(token, '')
    raw = ' '.join(raw.split())
    return raw in {'������', '/cancel', 'cancel', '���������'}


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


async def _ensure_scope_reply_keyboard(target: Message | CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    if data.get("settings_reply_message_id"):
        return
    sender = target.message.answer if isinstance(target, CallbackQuery) else target.answer
    sent = await sender("����� ������.", reply_markup=cancel_kb(lang), disable_notification=True)
    extra_ids = data.get("extra_prompt_message_ids") or []
    if not isinstance(extra_ids, list):
        extra_ids = [extra_ids]
    extra_ids = [x for x in extra_ids if x]
    extra_ids.append(sent.message_id)
    await state.update_data(settings_reply_message_id=sent.message_id, extra_prompt_message_ids=extra_ids)


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


@router.message(F.text.casefold().in_({'����', 'menu'}))
@router.message(F.text == '/menu')
async def menu_any(m: Message, state: FSMContext, db: aiosqlite.Connection):
    data = await state.get_data()
    await _cleanup_ui(m.bot, m.chat.id, data)
    await state.clear()
    lang = await get_lang(db, m.from_user.id)
    menu_text = await build_main_menu_text(db, m.from_user.id, lang)
    await m.answer(menu_text, reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode="HTML")


@router.message(lambda m: is_cancel_text(getattr(m, 'text', None)))
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
    if not (
        await can_use_feature(db, m.from_user.id, FEATURE_PLANNED)
        or await can_use_feature(db, m.from_user.id, FEATURE_RECURRING)
        or await can_use_feature(db, m.from_user.id, FEATURE_DEBTS)
    ):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await _open_hub(m, state, db, scope="planning")


@router.callback_query(F.data == "hub:planning")
async def planning_hub_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _open_hub(c, state, db, scope="planning")


@router.callback_query(F.data == "hub:more")
async def more_hub_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _open_hub(c, state, db, scope="more")


@router.callback_query(F.data == "hub:main")
async def hub_main(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
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
    await _ensure_scope_reply_keyboard(c, state, lang)
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
    await _ensure_scope_reply_keyboard(c, state, lang)
    await state.set_state(TransferFlow.amount)
    await _tr_render_amount(c, state)


def _full_access_price() -> int:
    return int(getattr(settings, "full_access_stars_price", 150))


def _full_access_days() -> int:
    return int(getattr(settings, "full_access_days", 90))


def _upgrade_message(lang: str) -> str:
    price = _full_access_price()
    days = _full_access_days()

    if lang == "en":
        return (
            "✨ <b>Full access</b>\n\n"
            "You are currently using the free mode.\n\n"
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
            f"Price: <b>{price} ⭐</b>\n"
            f"Access period: <b>{days} days</b>\n\n"
            "Press the button below to unlock full access."
        )

    if lang == "kk":
        return (
            "✨ <b>Толық қолжетімділік</b>\n\n"
            "Қазір сен тегін режимді қолданып отырсың.\n\n"
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
            f"Бағасы: <b>{price} ⭐</b>\n"
            f"Қолжетімділік мерзімі: <b>{days} күн</b>\n\n"
            "Толық қолжетімділікті ашу үшін төмендегі батырманы бас."
        )

    return (
        "✨ <b>Полный доступ</b>\n\n"
        "Сейчас у тебя бесплатный режим.\n\n"
        "<b>Что доступно бесплатно</b>\n"
        "• учёт доходов и расходов\n"
        "• история\n"
        "• счета\n"
        "• настройки\n"
        "• базовые отчёты за день и неделю\n\n"
        "<b>Что открывается в полном доступе</b>\n"
        "• переводы между счетами\n"
        "• планируемые операции\n"
        "• постоянные доходы и расходы\n"
        "• долги и кредиты\n"
        "• бюджеты и лимиты\n"
        "• отчёты по категориям\n"
        "• месячные отчёты\n"
        "• AI-консультант\n\n"
        f"Цена: <b>{price} ⭐</b>\n"
        f"Срок доступа: <b>{days} дней</b>\n\n"
        "Нажми кнопку ниже, чтобы открыть полный доступ."
    )


def _invoice_description(lang: str) -> str:
    days = _full_access_days()

    if lang == "en":
        return f"Full access to all bot sections for {days} days."

    if lang == "kk":
        return f"Боттың барлық бөлімдеріне {days} күнге толық қолжетімділік."

    return f"Полный доступ ко всем разделам бота на {days} дней."


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_ALL_FEATURES"))
async def upgrade_info_message(m: Message, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)

    data = await state.get_data()
    await _cleanup_ui(m.bot, m.chat.id, data)

    try:
        await m.delete()
    except Exception:
        pass

    await state.clear()

    sent = await m.answer(
        _upgrade_message(lang),
        parse_mode="HTML",
        reply_markup=upgrade_info_kb(
            lang,
            price=_full_access_price(),
        ),
    )

    await state.update_data(
        flow_message_id=sent.message_id,
        ui_scope="upgrade",
        lang=lang,
    )


@router.callback_query(lambda c: c.data in {"upgrade:info", "upgrade:open"})
async def upgrade_info_callback(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)

    data = await state.get_data()
    await _cleanup_ui(c.bot, c.message.chat.id, data)
    await state.clear()

    sent = await c.message.answer(
        _upgrade_message(lang),
        parse_mode="HTML",
        reply_markup=upgrade_info_kb(
            lang,
            price=_full_access_price(),
        ),
    )

    await state.update_data(
        flow_message_id=sent.message_id,
        ui_scope="upgrade",
        lang=lang,
    )

    await c.answer()


@router.callback_query(F.data == "upgrade:activate")
async def upgrade_activate(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)

    await c.bot.send_invoice(
        chat_id=c.from_user.id,
        title=t(lang, "BTN_UNLOCK_FULL"),
        description=_invoice_description(lang)[:255],
        payload="full_access_upgrade",
        provider_token="",
        currency="XTR",
        prices=[
            LabeledPrice(
                label=t(lang, "BTN_UNLOCK_FULL"),
                amount=_full_access_price(),
            )
        ],
    )

    await c.answer()


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(m: Message, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)
    payload = m.successful_payment.invoice_payload

    if payload != "full_access_upgrade":
        return

    data = await state.get_data()

    try:
        await _cleanup_ui(m.bot, m.chat.id, data)
        await grant_full_access(db, m.from_user.id)
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
