from __future__ import annotations

from datetime import datetime, timezone, timedelta
from html import escape

import aiosqlite
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.repositories.accounts_repo import list_accounts
from app.db.repositories.categories_repo import list_categories
from app.db.repositories.recurring_repo import (
    ensure_schema,
    create_recurring_expense,
    list_recurring_expenses,
    get_recurring_expense,
    archive_recurring_expense,
    restore_recurring_expense,
    mark_recurring_paid,
    mark_recurring_reminded,
)
from app.db.repositories.settings_repo import get_lang
from app.db.repositories.tx_repo import create_tx, apply_expense_income
from app.fsm.states import RecurringExpenseFlow
from app.handlers.common import cancel_to_main_menu, consume_user_input, is_cancel_text, build_main_menu_markup, neutralize_keyboard
from app.ui.i18n import text_matches_key, t
from app.ui.keyboards import main_menu, cancel_kb, categories_kb, accounts_kb, flow_done_actions_kb, inline_cancel_kb

router = Router()
PARSE_MODE = 'HTML'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fmt_money(value: int, currency: str = "KZT") -> str:
    """Thin wrapper around the central formatter so the user's currency
    is rendered consistently (KZT/RUB/USD/etc.) instead of a hardcoded 'тг'."""
    from app.domain.money import fmt_money as _fmt_money
    return _fmt_money(value, currency=currency)


async def _safe_remove_markup(bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=int(message_id), reply_markup=None)
    except Exception:
        pass


async def _remember_screen(state: FSMContext, message_id: int | None):
    await state.update_data(flow_message_id=message_id)


async def _clear_last_screen(target: Message | CallbackQuery, state: FSMContext, *, forget: bool = False):
    data = await state.get_data()
    message_id = data.get('flow_message_id')
    bot = target.bot
    chat_id = target.chat.id if isinstance(target, Message) else target.message.chat.id
    await _safe_remove_markup(bot, chat_id, message_id)
    if isinstance(target, CallbackQuery):
        await _safe_remove_markup(bot, chat_id, target.message.message_id)
    if forget:
        await _remember_screen(state, None)


async def _delete_message(bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(message_id))
    except Exception:
        pass


async def _enter_input_step(target: Message | CallbackQuery, state: FSMContext, text: str, lang: str):
    """Send a fresh prompt for a text input step. Removes the previous flow
    message entirely (not just its markup) so the chat doesn't accumulate
    stale ask-screens; attaches an inline Cancel button right under the
    prompt for users whose reply keyboard is collapsed."""
    data = await state.get_data()
    bot = target.bot
    chat_id = target.chat.id if isinstance(target, Message) else target.message.chat.id
    prev = data.get('flow_message_id')
    await _delete_message(bot, chat_id, prev)
    sender = target.answer if isinstance(target, Message) else target.message.answer
    sent = await sender(text, reply_markup=inline_cancel_kb(lang), parse_mode=PARSE_MODE)
    await _remember_screen(state, sent.message_id)
    return sent


async def _show_input_error(m: Message, state: FSMContext, lang: str, text: str):
    """Validation error variant: drop the user's input and rewrite the current
    flow message in place. Falls back to a fresh prompt if editing fails."""
    try:
        await m.delete()
    except Exception:
        pass
    data = await state.get_data()
    flow_id = data.get('flow_message_id')
    if flow_id:
        try:
            await m.bot.edit_message_text(
                chat_id=m.chat.id,
                message_id=int(flow_id),
                text=text,
                reply_markup=inline_cancel_kb(lang),
                parse_mode=PARSE_MODE,
            )
            return
        except Exception:
            pass
    sent = await m.answer(text, reply_markup=inline_cancel_kb(lang), parse_mode=PARSE_MODE)
    await _remember_screen(state, sent.message_id)


async def _send_screen(target: Message | CallbackQuery, state: FSMContext, text: str, reply_markup=None):
    sender = target.answer if isinstance(target, Message) else target.message.answer
    sent = await sender(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    await _remember_screen(state, sent.message_id)
    return sent


async def _edit_screen(c: CallbackQuery, state: FSMContext, text: str, reply_markup=None):
    data = await state.get_data()
    flow_message_id = data.get('flow_message_id')
    if flow_message_id:
        try:
            await c.bot.edit_message_text(
                chat_id=c.message.chat.id,
                message_id=int(flow_message_id),
                text=text,
                reply_markup=reply_markup,
                parse_mode=PARSE_MODE,
            )
            await _remember_screen(state, int(flow_message_id))
            return
        except TelegramBadRequest:
            pass
        except Exception:
            pass
    try:
        await c.message.edit_text(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        await _remember_screen(state, c.message.message_id)
    except TelegramBadRequest:
        sent = await c.message.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        await _remember_screen(state, sent.message_id)


async def _enter_chat_mode(target: Message | CallbackQuery, state: FSMContext, text: str, reply_markup=None):
    await _clear_last_screen(target, state, forget=True)
    return await _send_screen(target, state, text, reply_markup=reply_markup)


async def _clear_recurring_flow_data(state: FSMContext):
    data = await state.get_data()
    keep = {'flow_message_id': data.get('flow_message_id')}
    await state.clear()
    await state.update_data(**keep)


async def _render_screen(target: Message | CallbackQuery, state: FSMContext, text: str, reply_markup=None):
    if isinstance(target, CallbackQuery):
        await _edit_screen(target, state, text, reply_markup=reply_markup)
    else:
        await _enter_chat_mode(target, state, text, reply_markup=reply_markup)



def recurring_menu_kb(lang: str = 'ru'):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, 'BTN_ADD'), callback_data='re:add')
    kb.button(text=t(lang, 'BTN_LIST_ACTIVE'), callback_data='re:list')
    kb.button(text=t(lang, 'BTN_ARCHIVE'), callback_data='re:archived')
    kb.button(text=t(lang, 'BTN_BACK'), callback_data='hub:planning')
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def recurring_rows_kb(rows, archived: bool, lang: str = 'ru'):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for row in rows:
        title = f"{row['title']} — {fmt_money(int(row['amount']))}"
        kb.button(text=title, callback_data=f"re:item:{row['id']}")
    back_cb = 're:menu'
    kb.button(text=t(lang, 'BTN_BACK'), callback_data=back_cb)
    kb.adjust(1)
    return kb.as_markup()


def recurring_actions_kb(recurring_id: int, archived: bool, lang: str = 'ru', back_cb: str | None = None):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    if archived:
        kb.button(text=t(lang, 'BTN_RESTORE'), callback_data=f're:restore:{recurring_id}')
    else:
        kb.button(text=t(lang, 'RE_BTN_PAID'), callback_data=f're:paid:{recurring_id}')
        kb.button(text=t(lang, 'BTN_TO_ARCHIVE'), callback_data=f're:archive:{recurring_id}')
    kb.button(text=t(lang, 'BTN_BACK'), callback_data=back_cb or ('re:list' if not archived else 're:archived'))
    kb.adjust(1)
    return kb.as_markup()


def recurring_reminder_actions_kb(recurring_id: int, lang: str = 'ru'):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, 'RE_BTN_PAID_SHORT'), callback_data=f're:remindpay:{recurring_id}')
    kb.button(text=t(lang, 'BTN_TOMORROW'), callback_data=f're:remindsnooze:{recurring_id}')
    kb.button(text=t(lang, 'BTN_ADDED_MANUALLY'), callback_data=f're:remindmanual:{recurring_id}')
    kb.button(text=t(lang, 'BTN_DETAILS'), callback_data=f're:remdetail:{recurring_id}')
    kb.adjust(2, 2)
    return kb.as_markup()


def recurring_confirm_kb(lang: str = 'ru'):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, 'BTN_SAVE'), callback_data='re:save')
    kb.button(text=t(lang, 'BTN_CANCEL'), callback_data='re:menu')
    kb.adjust(1)
    return kb.as_markup()


async def _menu_text(db: aiosqlite.Connection, user_id: int, lang: str) -> str:
    await ensure_schema(db)
    active = await list_recurring_expenses(db, user_id, archived=False)
    archived = await list_recurring_expenses(db, user_id, archived=True)
    nearest = active[0] if active else None
    lines = [
        t(lang, 'RE_MENU_EXPENSES_TITLE'),
        '',
        t(lang, 'RE_MENU_EXPENSES_DESC'),
        t(lang, 'PL_ACTIVE_COUNT').format(n=len(active)),
    ]
    if archived:
        lines.append(t(lang, 'PL_ARCHIVED_COUNT').format(n=len(archived)))
    if nearest:
        lines.extend([
            '',
            t(lang, 'NEAREST'),
            f"• <b>{escape(str(nearest['title']))}</b> — {fmt_money(int(nearest['amount']))} — {nearest['next_run_date']}",
        ])
    return '\n'.join(lines)


async def _show_menu(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, target.from_user.id)
    await _clear_recurring_flow_data(state)
    await state.set_state(None)
    await _render_screen(target, state, await _menu_text(db, target.from_user.id, lang), reply_markup=recurring_menu_kb(lang))


async def _ask_title(target: Message | CallbackQuery, state: FSMContext, lang: str):
    await state.set_state(RecurringExpenseFlow.title)
    await _enter_input_step(target, state, t(lang, 'RE_EXP_TITLE_PROMPT'), lang)


async def _ask_amount(target: Message | CallbackQuery, state: FSMContext, lang: str, title: str):
    await state.set_state(RecurringExpenseFlow.amount)
    await _enter_input_step(
        target, state, t(lang, 'RE_AMOUNT_PROMPT').format(title=escape(title)), lang
    )


async def _ask_day(target: Message | CallbackQuery, state: FSMContext, lang: str, data: dict):
    await state.set_state(RecurringExpenseFlow.day)
    title = escape(str(data.get('re_title') or '—'))
    amount = fmt_money(int(data.get('re_amount') or 0))
    await _enter_input_step(
        target, state, t(lang, 'RE_DAY_PROMPT').format(title=title, amount=amount), lang
    )


async def _ask_comment(target: Message | CallbackQuery, state: FSMContext, lang: str, data: dict):
    await state.set_state(RecurringExpenseFlow.comment)
    title = escape(str(data.get('re_title') or '—'))
    amount = fmt_money(int(data.get('re_amount') or 0))
    await _enter_input_step(
        target, state, t(lang, 'RE_COMMENT_PROMPT').format(title=title, amount=amount), lang
    )


async def _show_confirm(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    data = await state.get_data()
    lang = await get_lang(db, target.from_user.id)

    cats = await list_categories(db, target.from_user.id, 'expense')
    accounts = await list_accounts(db, target.from_user.id)
    cat_name = next((escape(str(c[1])) for c in cats if int(c[0]) == int(data.get('re_category_id') or 0)), '—')
    acc_name = next((escape(str(a[1])) for a in accounts if int(a[0]) == int(data.get('re_account_id') or 0)), '—')
    comment = data.get('re_comment')

    text = t(lang, 'RE_CONFIRM').format(
        title=escape(str(data.get('re_title') or '—')),
        amount=fmt_money(int(data.get('re_amount') or 0)),
        category=cat_name,
        account=acc_name,
        day=int(data.get('re_day') or 0),
        comment=escape(str(comment)) if comment else '—',
    )
    await _render_screen(target, state, text, reply_markup=recurring_confirm_kb(lang))


from app.domain.services.access_service import FEATURE_RECURRING, can_use_feature
from app.handlers.common import cancel_to_main_menu, is_cancel_text, deny_feature_message

@router.message(lambda m: text_matches_key(getattr(m, 'text', None), 'BTN_RECURRING_EXPENSES'))
async def recurring_entry(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await ensure_schema(db)
    await _show_menu(m, state, db)


@router.callback_query(F.data == 're:menu')
async def recurring_menu_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _show_menu(c, state, db)
    await c.answer()



@router.callback_query(F.data == 're:list')
async def recurring_list(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    rows = await list_recurring_expenses(db, c.from_user.id, archived=False)
    text = t(lang, 'RE_LIST_EXPENSES_ACTIVE')
    if not rows:
        text += '\n\n' + t(lang, 'PL_LIST_EMPTY')
    await _render_screen(c, state, text, reply_markup=recurring_rows_kb(rows, archived=False, lang=lang))
    await c.answer()


@router.callback_query(F.data == 're:archived')
async def recurring_archived(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    rows = await list_recurring_expenses(db, c.from_user.id, archived=True)
    text = t(lang, 'RE_LIST_EXPENSES_ARCHIVED')
    if not rows:
        text += '\n\n' + t(lang, 'PL_ARCHIVE_EMPTY')
    await _render_screen(c, state, text, reply_markup=recurring_rows_kb(rows, archived=True, lang=lang))
    await c.answer()


@router.callback_query(F.data == 're:add')
async def recurring_add(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_RECURRING):
        await deny_feature_message(c, db, c.from_user.id)
        return
    lang = await get_lang(db, c.from_user.id)
    await _clear_recurring_flow_data(state)
    await _ask_title(c, state, lang)
    await c.answer()


@router.message(RecurringExpenseFlow.title, F.text)
async def recurring_title(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    lang = await get_lang(db, m.from_user.id)
    title = (m.text or '').strip()
    if len(title) < 2 or len(title) > 60:
        await _show_input_error(m, state, lang, t(lang, 'RE_TITLE_LEN_ERROR'))
        return
    try:
        await m.delete()
    except Exception:
        pass
    await state.update_data(re_title=title)
    await _ask_amount(m, state, lang, title)


@router.message(RecurringExpenseFlow.amount, F.text)
async def recurring_amount(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    from app.domain.money import parse_money_for_user
    lang = await get_lang(db, m.from_user.id)
    amt = await parse_money_for_user(db, m.from_user.id, m.text)
    if amt is None or amt <= 0:
        await _show_input_error(m, state, lang, t(lang, "AMOUNT_INVALID"))
        return
    try:
        await m.delete()
    except Exception:
        pass
    await state.update_data(re_amount=amt)
    cats = await list_categories(db, m.from_user.id, 'expense')
    await state.set_state(RecurringExpenseFlow.category)
    text = t(lang, 'RE_PICK_CATEGORY_EXPENSE')
    data = await state.get_data()
    page = int(data.get('re_cat_page', 0) or 0)
    # Category picker is a fresh inline screen — drop the previous prompt entirely.
    await _delete_message(m.bot, m.chat.id, data.get('flow_message_id'))
    sent = await m.answer(text, reply_markup=categories_kb(cats, 're:cat', lang, page=page), parse_mode=PARSE_MODE)
    await _remember_screen(state, sent.message_id)


@router.callback_query(RecurringExpenseFlow.category, F.data.regexp(r'^re:cat:page:\d+$'))
async def recurring_cat_page(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    page = int(c.data.split(':')[3])
    await state.update_data(re_cat_page=page)
    cats = await list_categories(db, c.from_user.id, 'expense')
    lang = await get_lang(db, c.from_user.id)
    text = t(lang, 'RE_PICK_CATEGORY_EXPENSE')
    await _edit_screen(c, state, text, reply_markup=categories_kb(cats, 're:cat', lang, page=page))
    await c.answer()


@router.callback_query(RecurringExpenseFlow.category, F.data.regexp(r'^re:cat:\d+$'))
async def recurring_cat(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await state.update_data(re_category_id=int(c.data.split(':')[-1]))
    accs = await list_accounts(db, c.from_user.id)
    await state.set_state(RecurringExpenseFlow.account)
    lang = await get_lang(db, c.from_user.id)
    await _edit_screen(c, state, t(lang, 'RE_PICK_ACCOUNT'), reply_markup=accounts_kb(accs, 're:acc', lang))
    await c.answer()


@router.callback_query(RecurringExpenseFlow.account, F.data.startswith('re:acc:'))
async def recurring_acc(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await state.update_data(re_account_id=int(c.data.split(':')[-1]))
    data = await state.get_data()
    await _ask_day(c, state, await get_lang(db, c.from_user.id), data)
    await c.answer()


@router.message(RecurringExpenseFlow.day, F.text)
async def recurring_day(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    lang = await get_lang(db, m.from_user.id)
    raw = (m.text or '').strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 31):
        await _show_input_error(m, state, lang, t(lang, 'RE_DAY_INVALID'))
        return
    try:
        await m.delete()
    except Exception:
        pass
    await state.update_data(re_day=int(raw))
    data = await state.get_data()
    await _ask_comment(m, state, lang, data)


@router.message(RecurringExpenseFlow.comment, F.text)
async def recurring_comment(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    comment = (m.text or '').strip()
    if comment == '-':
        comment = None
    try:
        await m.delete()
    except Exception:
        pass
    await state.update_data(re_comment=comment)
    await _show_confirm(m, state, db)


@router.callback_query(F.data == 're:save')
async def recurring_save(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    data = await state.get_data()
    try:
        await create_recurring_expense(
            db,
            c.from_user.id,
            data['re_title'],
            int(data['re_amount']),
            int(data['re_category_id']),
            int(data['re_account_id']),
            int(data['re_day']),
            data.get('re_comment'),
            now_iso(),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    lang = await get_lang(db, c.from_user.id)
    try:
        await c.answer(t(lang, 'TOAST_SAVED'))
    except Exception:
        pass
    await _clear_last_screen(c, state, forget=True)
    await _clear_recurring_flow_data(state)
    await c.message.answer(t(lang, 'RE_SAVED_EXPENSE'), parse_mode=PARSE_MODE)
    await cancel_to_main_menu(c, state, db)


def _recurring_card_lines(row, lang: str, *, reminder_head_key: str | None = None) -> list[str]:
    lines = [
        f"🔁 <b>{escape(str(row['title']))}</b>",
        '',
    ]
    if reminder_head_key:
        lines.append(t(lang, reminder_head_key))
    lines.extend([
        t(lang, 'RE_CARD_AMOUNT').format(value=fmt_money(int(row['amount']))),
        t(lang, 'RE_CARD_CATEGORY').format(value=escape(str(row['category_name']))),
        t(lang, 'RE_CARD_ACCOUNT').format(value=escape(str(row['account_name']))),
        t(lang, 'RE_CARD_DAY').format(value=int(row['day_of_month'])),
        t(lang, 'RE_CARD_NEXT_RUN').format(value=escape(str(row['next_run_date']))),
    ])
    if row['comment']:
        lines.append(t(lang, 'RE_CARD_COMMENT').format(value=escape(str(row['comment']))))
    if row['last_paid_at']:
        lines.append(t(lang, 'RE_CARD_LAST_PAID').format(value=escape(str(row['last_paid_at']))[:10]))
    return lines


@router.callback_query(F.data.startswith('re:item:'))
async def recurring_item(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = 'ru'):
    recurring_id = int(c.data.split(':')[-1])
    row = await get_recurring_expense(db, c.from_user.id, recurring_id)
    if not row:
        await c.answer(t(lang, 'NOT_FOUND'), show_alert=True)
        return
    archived = int(row['is_archived'] or 0) == 1
    await _render_screen(
        c, state, '\n'.join(_recurring_card_lines(row, lang)),
        reply_markup=recurring_actions_kb(recurring_id, archived=archived, lang=lang),
    )
    await c.answer()


@router.callback_query(F.data.startswith('re:remdetail:'))
async def recurring_reminder_detail(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = 'ru'):
    recurring_id = int(c.data.split(':')[-1])
    row = await get_recurring_expense(db, c.from_user.id, recurring_id)
    if not row:
        await c.answer(t(lang, 'NOT_FOUND'), show_alert=True)
        return
    archived = int(row['is_archived'] or 0) == 1
    await _render_screen(
        c, state, '\n'.join(_recurring_card_lines(row, lang)),
        reply_markup=recurring_actions_kb(recurring_id, archived=archived, lang=lang, back_cb=f're:remcard:{recurring_id}'),
    )
    await c.answer()


@router.callback_query(F.data.startswith('re:remcard:'))
async def recurring_reminder_card(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = 'ru'):
    recurring_id = int(c.data.split(':')[-1])
    row = await get_recurring_expense(db, c.from_user.id, recurring_id)
    if not row:
        await c.answer(t(lang, 'NOT_FOUND'), show_alert=True)
        return
    await _render_screen(
        c, state,
        '\n'.join(_recurring_card_lines(row, lang, reminder_head_key='RE_REMINDER_HEAD_EXPENSE')),
        reply_markup=recurring_reminder_actions_kb(recurring_id, lang),
    )
    await c.answer()


@router.callback_query(F.data.startswith('re:remindsnooze:'))
async def recurring_snooze_from_reminder(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = 'ru'):
    from app.domain.time_utils import today_in_user_tz
    recurring_id = int(c.data.split(':')[-1])
    today_local = (await today_in_user_tz(db, c.from_user.id)).isoformat()
    try:
        await mark_recurring_reminded(db, c.from_user.id, recurring_id, today_local)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    text = t(lang, "REMINDER_SNOOZED_EXPENSE")
    actions = flow_done_actions_kb(lang, list_cb='re:list', menu_cb='hub:planning')
    try:
        await c.message.edit_text(text, parse_mode=PARSE_MODE, reply_markup=actions)
    except Exception:
        await c.message.answer(text, parse_mode=PARSE_MODE, reply_markup=actions)
    await c.answer()


@router.callback_query(F.data.startswith('re:remindmanual:'))
async def recurring_manual_from_reminder(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = 'ru'):
    recurring_id = int(c.data.split(':')[-1])
    ts = now_iso()
    row = await get_recurring_expense(db, c.from_user.id, recurring_id)
    if not row:
        await c.answer(t(lang, 'NOT_FOUND'), show_alert=True)
        return
    try:
        await mark_recurring_paid(db, c.from_user.id, recurring_id, ts)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    text = t(lang, "REMINDER_MANUAL_EXPENSE")
    actions = flow_done_actions_kb(lang, list_cb='re:list', menu_cb='hub:planning')
    try:
        await c.message.edit_text(text, parse_mode=PARSE_MODE, reply_markup=actions)
    except Exception:
        await c.message.answer(text, parse_mode=PARSE_MODE, reply_markup=actions)
    await c.answer()

@router.callback_query(F.data.startswith('re:archive:'))
async def recurring_archive(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    recurring_id = int(c.data.split(':')[-1])
    try:
        await archive_recurring_expense(db, c.from_user.id, recurring_id, now_iso())
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await recurring_list(c, state, db)


@router.callback_query(F.data.startswith('re:restore:'))
async def recurring_restore(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    recurring_id = int(c.data.split(':')[-1])
    try:
        await restore_recurring_expense(db, c.from_user.id, recurring_id, now_iso())
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await recurring_archived(c, state, db)


async def _mark_expense_paid(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, recurring_id: int, *, from_reminder: bool):
    lang = await get_lang(db, c.from_user.id)
    row = await get_recurring_expense(db, c.from_user.id, recurring_id)
    if not row:
        await c.answer(t(lang, 'NOT_FOUND'), show_alert=True)
        return
    ts = now_iso()
    try:
        tx_id = await create_tx(db, c.from_user.id, ts, 'expense', -int(row['amount']), int(row['account_id']), int(row['category_id']), row['comment'] or row['title'], ts, None, tier='obligation')
        await apply_expense_income(db, c.from_user.id, tx_id, -int(row['amount']), int(row['account_id']))
        await mark_recurring_paid(db, c.from_user.id, recurring_id, ts)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    text = t(lang, 'RE_PAID_OK')
    actions = flow_done_actions_kb(lang, list_cb='re:list', menu_cb='hub:planning')
    if from_reminder:
        try:
            await c.message.edit_text(text, parse_mode=PARSE_MODE, reply_markup=actions)
        except Exception:
            await c.message.answer(text, parse_mode=PARSE_MODE, reply_markup=actions)
        await c.answer(t(lang, 'DONE_OK'))
        return
    await _clear_last_screen(c, state, forget=True)
    await _clear_recurring_flow_data(state)
    await c.message.answer(text, parse_mode=PARSE_MODE, reply_markup=actions)
    await c.answer(t(lang, 'DONE_OK'))


@router.callback_query(F.data.startswith('re:paid:'))
async def recurring_paid(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    recurring_id = int(c.data.split(':')[-1])
    await _mark_expense_paid(c, state, db, recurring_id, from_reminder=False)


@router.callback_query(F.data.startswith('re:remindpay:'))
async def recurring_paid_from_reminder(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    recurring_id = int(c.data.split(':')[-1])
    await _mark_expense_paid(c, state, db, recurring_id, from_reminder=True)
