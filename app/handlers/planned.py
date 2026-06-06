from __future__ import annotations
from app.domain.services.access_service import FEATURE_PLANNED, can_use_feature

from datetime import datetime, timezone, timedelta
from html import escape

import aiosqlite
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.repositories.accounts_repo import list_accounts
from app.db.repositories.categories_repo import list_categories
from app.db.repositories.planned_repo import (
    ensure_schema,
    create_planned,
    list_planned,
    get_planned,
    set_planned_archived,
    mark_planned_done,
    update_planned_date,
    mark_planned_reminded,
)
from app.db.repositories.settings_repo import get_lang
from app.db.repositories.tx_repo import create_tx, apply_expense_income
from app.domain.money import parse_money_for_user
from app.domain.time_utils import today_in_user_tz
from app.domain.validators import parse_friendly_date
from app.fsm.states import PlannedFlow
from app.handlers.common import deny_feature_message,  cancel_to_main_menu, consume_user_input, is_cancel_text
from app.ui.i18n import text_matches_key, t
from app.ui.keyboards import main_menu, cancel_kb, flow_done_actions_kb, inline_cancel_kb
from app.domain.services.ai_consultant_service import build_section_hint

router = Router()
PARSE_MODE = "HTML"
PLANNED_SCOPE = "planned_section"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fmt_money(value: int, currency: str = "KZT") -> str:
    """Thin wrapper around ``app.domain.money.fmt_money`` so 'тг' is no longer
    hardcoded — see ``app.domain.money.CURRENCY_SYMBOL``."""
    from app.domain.money import fmt_money as _fmt_money
    return _fmt_money(value, currency=currency)


def _chat_and_bot(target: Message | CallbackQuery):
    if isinstance(target, CallbackQuery):
        return target.bot, target.message.chat.id
    return target.bot, target.chat.id


async def _safe_delete_message(bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(message_id))
    except Exception:
        pass


async def _safe_remove_markup(bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=int(message_id),
            reply_markup=None,
        )
    except Exception:
        pass


async def _clear_prompt(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prompt_id = data.get("prompt_message_id")
    bot, chat_id = _chat_and_bot(target)
    await _safe_delete_message(bot, chat_id, prompt_id)
    await state.update_data(prompt_message_id=None)


async def _start_planned_session(state: FSMContext):
    await state.update_data(ui_scope=PLANNED_SCOPE)


async def _ensure_planned_reply_keyboard(target: Message | CallbackQuery, state: FSMContext, lang: str):
    data = await state.get_data()
    if data.get("planned_reply_message_id"):
        return
    sender = target.message.answer if isinstance(target, CallbackQuery) else target.answer
    sent = await sender("Режим планирования открыт.", reply_markup=cancel_kb(lang), disable_notification=True)
    extra_ids = data.get("extra_prompt_message_ids") or []
    if not isinstance(extra_ids, list):
        extra_ids = [extra_ids]
    extra_ids = [x for x in extra_ids if x]
    extra_ids.append(sent.message_id)
    await state.update_data(planned_reply_message_id=sent.message_id, extra_prompt_message_ids=extra_ids)


async def _reset_flow_ui(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    bot, chat_id = _chat_and_bot(target)

    await _safe_delete_message(bot, chat_id, data.get("prompt_message_id"))
    await _safe_remove_markup(bot, chat_id, data.get("flow_message_id"))

    if isinstance(target, CallbackQuery):
        await _safe_remove_markup(bot, chat_id, target.message.message_id)

    await state.update_data(prompt_message_id=None, flow_message_id=None)


async def _render_screen(
    target: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    reply_markup=None,
):
    await _start_planned_session(state)
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")
    bot, chat_id = _chat_and_bot(target)
    current_message = None if isinstance(target, Message) else target.message

    if isinstance(target, Message):
        if flow_message_id:
            await _safe_remove_markup(bot, chat_id, flow_message_id)
        sent = await target.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        await state.update_data(flow_message_id=sent.message_id)
        return

    if flow_message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(flow_message_id),
                text=text,
                reply_markup=reply_markup,
                parse_mode=PARSE_MODE,
            )
            return
        except Exception:
            pass

    if current_message is not None:
        try:
            await current_message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=PARSE_MODE,
            )
            await state.update_data(flow_message_id=current_message.message_id)
            return
        except Exception:
            pass

    sent = await target.message.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    await state.update_data(flow_message_id=sent.message_id)


async def _show_input_prompt(
    target: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    lang: str,
):
    await _clear_prompt(target, state)
    sent = await (
        target.message.answer(text, reply_markup=inline_cancel_kb(lang), parse_mode=PARSE_MODE)
        if isinstance(target, CallbackQuery)
        else target.answer(text, reply_markup=inline_cancel_kb(lang), parse_mode=PARSE_MODE)
    )
    await state.update_data(prompt_message_id=sent.message_id)


async def _input_error(m: Message, state: FSMContext, lang: str, text: str):
    """Show a validation error on the current prompt without spamming new
    messages: delete the user's bad input, then edit the prompt in place.
    Falls back to a fresh prompt if editing is no longer possible."""
    try:
        await m.delete()
    except Exception:
        pass
    data = await state.get_data()
    prompt_id = data.get("prompt_message_id")
    if prompt_id:
        try:
            await m.bot.edit_message_text(
                chat_id=m.chat.id,
                message_id=int(prompt_id),
                text=text,
                reply_markup=inline_cancel_kb(lang),
                parse_mode=PARSE_MODE,
            )
            return
        except Exception:
            pass
    sent = await m.answer(text, reply_markup=inline_cancel_kb(lang), parse_mode=PARSE_MODE)
    await state.update_data(prompt_message_id=sent.message_id)


def planned_menu_kb(lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_ADD"), callback_data="pl:add")
    kb.button(text=t(lang, "BTN_LIST_ACTIVE"), callback_data="pl:list")
    kb.button(text=t(lang, "BTN_ARCHIVE"), callback_data="pl:archived")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="hub:planning")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def planned_kind_kb(lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "PL_KIND_EXPENSE"), callback_data="pl:kind:expense")
    kb.button(text=t(lang, "PL_KIND_INCOME"), callback_data="pl:kind:income")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="pl:menu")
    kb.adjust(2, 1)
    return kb.as_markup()


def planned_importance_kb(lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "PL_IMPORTANCE_REQUIRED"), callback_data="pl:req:1")
    kb.button(text=t(lang, "PL_IMPORTANCE_FLEXIBLE"), callback_data="pl:req:0")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="pl:add")
    kb.adjust(1)
    return kb.as_markup()


def planned_rows_kb(rows, archived: bool, lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for row in rows:
        sign = "+" if str(row["kind"]) == "income" else "−"
        marker = "🧱 " if int(row["is_required"] or 0) == 1 else "🫧 "
        kb.button(
            text=f"{marker}{sign} {row['title']} — {fmt_money(int(row['amount']))}",
            callback_data=f"pl:item:{row['id']}",
        )
    kb.button(text=t(lang, "BTN_BACK"), callback_data="pl:menu")
    kb.adjust(1)
    return kb.as_markup()


def planned_actions_kb(item_id: int, archived: bool, lang: str = "ru", back_cb: str | None = None):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    if archived:
        kb.button(text=t(lang, "BTN_RESTORE"), callback_data=f"pl:restore:{item_id}")
        back = back_cb or "pl:archived"
    else:
        kb.button(text=t(lang, "PL_BTN_DONE"), callback_data=f"pl:done:{item_id}")
        kb.button(text=t(lang, "PL_BTN_MOVE"), callback_data=f"pl:move:{item_id}")
        kb.button(text=t(lang, "BTN_TO_ARCHIVE"), callback_data=f"pl:archive:{item_id}")
        back = back_cb or "pl:list"
    kb.button(text=t(lang, "BTN_BACK"), callback_data=back)
    kb.adjust(1)
    return kb.as_markup()




def planned_categories_pick_kb(cats, lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for cid, name, emoji, *_ in cats:
        label = f"{emoji + ' ' if emoji else ''}{name}"
        kb.button(text=label, callback_data=f"pl:cat:{cid}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="pl:step:importance")
    kb.adjust(2)
    return kb.as_markup()


def planned_accounts_pick_kb(accounts, lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    for acc_id, name, bal, arch in accounts:
        if arch:
            continue
        kb.button(text=f"{name} ({bal})", callback_data=f"pl:acc:{acc_id}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="pl:step:category")
    kb.adjust(1)
    return kb.as_markup()


def planned_reminder_actions_kb(item_id: int, lang: str = "ru"):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "PL_BTN_REMINDER_DONE"), callback_data=f"pl:done:{item_id}")
    kb.button(text=t(lang, "BTN_TOMORROW"), callback_data=f"pl:remindsnooze:{item_id}")
    kb.button(text=t(lang, "BTN_ADDED_MANUALLY"), callback_data=f"pl:remindmanual:{item_id}")
    kb.button(text=t(lang, "BTN_DETAILS"), callback_data=f"pl:remdetail:{item_id}")
    kb.adjust(2, 2)
    return kb.as_markup()


async def _menu_text(db, user_id: int, lang: str) -> str:
    await ensure_schema(db)
    active = await list_planned(db, user_id, archived=False)
    archived = await list_planned(db, user_id, archived=True)
    nearest = active[0] if active else None

    lines = [
        t(lang, "PL_MENU_TITLE"),
        "",
        t(lang, "PL_MENU_DESCRIPTION"),
        t(lang, "PL_ACTIVE_COUNT").format(n=len(active)),
    ]

    if archived:
        lines.append(t(lang, "PL_ARCHIVED_COUNT").format(n=len(archived)))

    if nearest:
        nearest_kind = str(nearest["kind"] or "expense")
        kind_label = t(lang, "PL_KIND_LABEL_INCOME" if nearest_kind == "income" else "PL_KIND_LABEL_EXPENSE")
        lines.extend(
            [
                "",
                t(lang, "PL_NEAREST"),
                f"• <b>{escape(str(nearest['title']))}</b> — {fmt_money(int(nearest['amount']))} — {nearest['planned_date']} — {kind_label}",
            ]
        )

    hint = await build_section_hint(db, user_id, "planned", lang)
    if hint:
        lines += ["", hint]

    return "\n".join(lines)


async def _show_menu(target: Message | CallbackQuery, state: FSMContext, db):
    lang = await get_lang(db, target.from_user.id)
    await _clear_prompt(target, state)
    await state.set_state(None)
    await _render_screen(
        target,
        state,
        await _menu_text(db, target.from_user.id, lang),
        reply_markup=planned_menu_kb(lang),
    )


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_PLANNED"))
async def planned_entry(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await ensure_schema(db)
    await _show_menu(m, state, db)


@router.callback_query(F.data == "pl:menu")
async def planned_menu_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _show_menu(c, state, db)
    await c.answer()



@router.callback_query(F.data == "pl:list")
async def planned_list(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    rows = await list_planned(db, c.from_user.id, False)
    text = t(lang, "PL_LIST_TITLE_ACTIVE")
    if not rows:
        text += "\n\n" + t(lang, "PL_LIST_EMPTY")
    await _render_screen(c, state, text, reply_markup=planned_rows_kb(rows, False, lang))
    await c.answer()


@router.callback_query(F.data == "pl:archived")
async def planned_archived(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    rows = await list_planned(db, c.from_user.id, True)
    text = t(lang, "PL_LIST_TITLE_ARCHIVED")
    if not rows:
        text += "\n\n" + t(lang, "PL_ARCHIVE_EMPTY")
    await _render_screen(c, state, text, reply_markup=planned_rows_kb(rows, True, lang))
    await c.answer()


@router.callback_query(F.data == "pl:add")
async def planned_add(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_PLANNED):
        await deny_feature_message(c, db, c.from_user.id)
        return
    lang = await get_lang(db, c.from_user.id)
    await _reset_flow_ui(c, state)
    await state.set_state(PlannedFlow.kind)
    await _render_screen(
        c,
        state,
        t(lang, "PL_NEW_PICK_KIND"),
        reply_markup=planned_kind_kb(lang),
    )
    await c.answer()


@router.callback_query(F.data.startswith("pl:kind:"))
async def planned_kind(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    kind = c.data.split(":")[-1]
    lang = await get_lang(db, c.from_user.id)

    await state.update_data(pl_kind=kind)
    await state.set_state(PlannedFlow.title)

    await _render_screen(c, state, t(lang, "PL_TITLE_PROMPT"))
    await _show_input_prompt(c, state, t(lang, "PL_TITLE_PROMPT"), lang)
    await c.answer()


@router.message(PlannedFlow.title, F.text)
async def planned_title(m: Message, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    title = (m.text or "").strip()
    if len(title) < 2 or len(title) > 60:
        await _input_error(m, state, lang, t(lang, "PL_TITLE_LEN_ERROR"))
        return

    await consume_user_input(m, state)
    await state.update_data(pl_title=title)
    await state.set_state(PlannedFlow.amount)
    await _show_input_prompt(m, state, t(lang, "AMOUNT_PROMPT_PLANNED"), lang)


@router.message(PlannedFlow.amount, F.text)
async def planned_amount(m: Message, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    amt = await parse_money_for_user(db, m.from_user.id, m.text)
    if amt is None or amt <= 0:
        await _input_error(m, state, lang, t(lang, "AMOUNT_INVALID"))
        return

    await consume_user_input(m, state)
    await state.update_data(pl_amount=int(amt))
    await state.set_state(PlannedFlow.importance)
    await _render_screen(
        m,
        state,
        t(lang, "PL_PICK_IMPORTANCE"),
        reply_markup=planned_importance_kb(lang),
    )


@router.callback_query(F.data.startswith("pl:req:"))
async def planned_importance(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    is_required = int(c.data.split(":")[-1])
    await state.update_data(pl_required=is_required)

    kind = (await state.get_data()).get("pl_kind", "expense")
    cats = await list_categories(db, c.from_user.id, kind)
    lang = await get_lang(db, c.from_user.id)

    await state.set_state(PlannedFlow.category)
    await _render_screen(
        c,
        state,
        t(lang, "PL_PICK_CATEGORY"),
        reply_markup=planned_categories_pick_kb(cats, lang),
    )
    await c.answer()


@router.callback_query(F.data == "pl:step:importance")
async def planned_step_importance(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    await state.set_state(PlannedFlow.importance)
    await _render_screen(
        c,
        state,
        t(lang, "PL_PICK_IMPORTANCE"),
        reply_markup=planned_importance_kb(lang),
    )
    await c.answer()


@router.callback_query(F.data == "pl:step:category")
async def planned_step_category(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    data = await state.get_data()
    kind = data.get("pl_kind", "expense")
    cats = await list_categories(db, c.from_user.id, kind)
    lang = await get_lang(db, c.from_user.id)
    await state.set_state(PlannedFlow.category)
    await _render_screen(
        c,
        state,
        t(lang, "PL_PICK_CATEGORY"),
        reply_markup=planned_categories_pick_kb(cats, lang),
    )
    await c.answer()


@router.callback_query(F.data.startswith("pl:cat:"))
async def planned_cat(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    cid = int(c.data.split(":")[-1])
    await state.update_data(pl_category_id=cid)

    accs = await list_accounts(db, c.from_user.id)
    lang = await get_lang(db, c.from_user.id)

    await state.set_state(PlannedFlow.account)
    await _render_screen(
        c,
        state,
        t(lang, "PL_PICK_ACCOUNT"),
        reply_markup=planned_accounts_pick_kb(accs, lang),
    )
    await c.answer()


@router.callback_query(F.data.startswith("pl:acc:"))
async def planned_acc(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    aid = int(c.data.split(":")[-1])
    lang = await get_lang(db, c.from_user.id)

    await state.update_data(pl_account_id=aid)
    await state.set_state(PlannedFlow.date)

    await _render_screen(c, state, t(lang, "DATE_PROMPT_PLANNED"))
    await _show_input_prompt(c, state, t(lang, "DATE_PROMPT_PLANNED"), lang)
    await c.answer()


@router.message(PlannedFlow.date, F.text)
async def planned_date(m: Message, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    iso = parse_friendly_date(m.text)
    if not iso:
        await _input_error(m, state, lang, t(lang, "DATE_INVALID"))
        return

    await consume_user_input(m, state)
    await state.update_data(pl_date=iso)
    await state.set_state(PlannedFlow.comment)
    await _show_input_prompt(m, state, t(lang, "PL_COMMENT_HINT"), lang)


@router.message(PlannedFlow.comment, F.text)
async def planned_comment(m: Message, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    comment = (m.text or "").strip()
    comment = None if comment == "-" else comment
    await consume_user_input(m, state)
    data = await state.get_data()

    try:
        await create_planned(
            db,
            m.from_user.id,
            data["pl_kind"],
            data["pl_title"],
            int(data["pl_amount"]),
            int(data["pl_category_id"]),
            int(data["pl_account_id"]),
            data["pl_date"],
            comment,
            now_iso(),
            int(data.get("pl_required", 1)),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await _show_menu(m, state, db)
    await m.answer(t(lang, "PLANNED_SAVED"), parse_mode=PARSE_MODE)


def _planned_card_lines(row, lang: str, *, with_reminder_head: bool = False) -> list[str]:
    sign = "+" if str(row["kind"]) == "income" else "−"
    type_label = t(lang, "PL_CARD_TYPE_INCOME" if str(row["kind"]) == "income" else "PL_CARD_TYPE_EXPENSE")
    imp_label = t(
        lang,
        "PL_CARD_IMPORTANCE_REQUIRED" if int(row["is_required"] or 0) == 1 else "PL_CARD_IMPORTANCE_FLEXIBLE",
    )

    lines = [
        f"🗓 <b>{escape(str(row['title']))}</b>",
        "",
    ]
    if with_reminder_head:
        lines.append(t(lang, "PL_REMINDER_HEAD"))
    lines.extend(
        [
            t(lang, "PL_CARD_TYPE").format(value=type_label),
            t(lang, "PL_CARD_AMOUNT").format(value=f"{sign}{fmt_money(int(row['amount']))}"),
            t(lang, "PL_CARD_DATE").format(value=row["planned_date"]),
            t(lang, "PL_CARD_IMPORTANCE").format(value=imp_label),
            t(lang, "PL_CARD_CATEGORY").format(value=escape(str(row["category_name"]))),
            t(lang, "PL_CARD_ACCOUNT").format(value=escape(str(row["account_name"]))),
        ]
    )
    if row["comment"]:
        lines.append(t(lang, "PL_CARD_COMMENT").format(value=escape(str(row["comment"]))))
    return lines


@router.callback_query(F.data.startswith("pl:item:"))
async def planned_item(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    item_id = int(c.data.split(":")[-1])
    row = await get_planned(db, c.from_user.id, item_id)

    if not row:
        await c.answer(t(lang, "NOT_FOUND"), show_alert=True)
        return

    await _render_screen(
        c,
        state,
        "\n".join(_planned_card_lines(row, lang)),
        reply_markup=planned_actions_kb(item_id, bool(row["is_archived"]), lang),
    )
    await c.answer()




@router.callback_query(F.data.startswith("pl:remdetail:"))
async def planned_reminder_detail(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    item_id = int(c.data.split(":")[-1])
    row = await get_planned(db, c.from_user.id, item_id)

    if not row:
        await c.answer(t(lang, "NOT_FOUND"), show_alert=True)
        return

    await _render_screen(
        c,
        state,
        "\n".join(_planned_card_lines(row, lang)),
        reply_markup=planned_actions_kb(item_id, bool(row["is_archived"]), lang, back_cb=f"pl:remcard:{item_id}"),
    )
    await c.answer()


@router.callback_query(F.data.startswith("pl:remcard:"))
async def planned_reminder_card(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    item_id = int(c.data.split(":")[-1])
    row = await get_planned(db, c.from_user.id, item_id)

    if not row:
        await c.answer(t(lang, "NOT_FOUND"), show_alert=True)
        return

    await _render_screen(
        c,
        state,
        "\n".join(_planned_card_lines(row, lang, with_reminder_head=True)),
        reply_markup=planned_reminder_actions_kb(item_id, lang),
    )
    await c.answer()


@router.callback_query(F.data.startswith("pl:remindsnooze:"))
async def planned_snooze_from_reminder(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    item_id = int(c.data.split(":")[-1])
    today_local = (await today_in_user_tz(db, c.from_user.id)).isoformat()
    try:
        await mark_planned_reminded(db, c.from_user.id, item_id, today_local)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    text = t(lang, "REMINDER_SNOOZED_PLANNED")
    actions = flow_done_actions_kb(lang, list_cb="pl:list", menu_cb="hub:planning")
    try:
        await c.message.edit_text(text, parse_mode=PARSE_MODE, reply_markup=actions)
    except Exception:
        await c.message.answer(text, parse_mode=PARSE_MODE, reply_markup=actions)
    await c.answer()


@router.callback_query(F.data.startswith("pl:remindmanual:"))
async def planned_manual_from_reminder(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    item_id = int(c.data.split(":")[-1])
    row = await mark_planned_done(db, c.from_user.id, item_id, now_iso())
    if not row:
        await c.answer(t(lang, "NOT_FOUND"), show_alert=True)
        return
    await db.commit()
    lang = await get_lang(db, c.from_user.id)
    text = t(lang, "REMINDER_MANUAL_PLANNED")
    actions = flow_done_actions_kb(lang, list_cb="pl:list", menu_cb="hub:planning")
    try:
        await c.message.edit_text(text, parse_mode=PARSE_MODE, reply_markup=actions)
    except Exception:
        await c.message.answer(text, parse_mode=PARSE_MODE, reply_markup=actions)
    await c.answer()

@router.callback_query(F.data.startswith("pl:archive:"))
async def planned_archive(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    item_id = int(c.data.split(":")[-1])
    await set_planned_archived(db, c.from_user.id, item_id, True, now_iso())
    await db.commit()
    await planned_list(c, state, db)


@router.callback_query(F.data.startswith("pl:restore:"))
async def planned_restore(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    item_id = int(c.data.split(":")[-1])
    await set_planned_archived(db, c.from_user.id, item_id, False, now_iso())
    await db.commit()
    await planned_archived(c, state, db)


@router.callback_query(F.data.startswith("pl:move:"))
async def planned_move(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_PLANNED):
        await deny_feature_message(c, db, c.from_user.id)
        return
    await _reset_flow_ui(c, state)

    item_id = int(c.data.split(":")[-1])
    lang = await get_lang(db, c.from_user.id)
    row = await get_planned(db, c.from_user.id, item_id)
    if not row:
        await c.answer(t(lang, "NOT_FOUND"), show_alert=True)
        return
    await state.update_data(pl_move_id=item_id)
    await state.set_state(PlannedFlow.move_date)

    move_prompt = t(lang, "DATE_PROMPT_PLANNED_MOVE").format(current=row["planned_date"])
    await _render_screen(c, state, move_prompt)
    await _show_input_prompt(c, state, move_prompt, lang)
    await c.answer()


@router.message(PlannedFlow.move_date, F.text)
async def planned_move_date(m: Message, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    iso = parse_friendly_date(m.text)
    if not iso:
        await _input_error(m, state, lang, t(lang, "DATE_INVALID"))
        return

    item_id = (await state.get_data()).get("pl_move_id")
    if not item_id:
        await cancel_to_main_menu(m, state, db)
        return

    try:
        await update_planned_date(db, m.from_user.id, int(item_id), iso, now_iso())
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await consume_user_input(m, state)
    await m.answer(t(lang, "PLANNED_DATE_UPDATED"), parse_mode=PARSE_MODE)
    await cancel_to_main_menu(m, state, db)
    return


@router.callback_query(F.data.startswith("pl:done:"))
async def planned_done(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, lang: str = "ru"):
    item_id = int(c.data.split(":")[-1])
    await db.execute("BEGIN IMMEDIATE")
    try:
        row = await mark_planned_done(db, c.from_user.id, item_id, now_iso())
        if not row:
            await db.rollback()
            await c.answer(t(lang, "NOT_FOUND"), show_alert=True)
            return

        amount = int(row["amount"] or 0)
        kind = str(row["kind"] or "expense")
        acc = int(row["account_id"])
        cat = int(row["category_id"])
        note = str(row["comment"] or row["title"] or "") or None

        sign_amount = amount if kind == "income" else -amount
        tier = 'obligation' if int(row.get("is_required") or 0) == 1 else 'routine'
        tx_id = await create_tx(db, c.from_user.id, now_iso(), kind, sign_amount, acc, cat, note, now_iso(), tier=tier)
        await apply_expense_income(db, c.from_user.id, tx_id, sign_amount, acc)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await _render_screen(
        c,
        state,
        t(lang, "PL_DONE_OK"),
        reply_markup=flow_done_actions_kb(lang, list_cb="pl:list", menu_cb="hub:planning"),
    )
    await c.answer()
