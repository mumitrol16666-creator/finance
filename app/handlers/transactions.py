from __future__ import annotations

from html import escape

from app.domain.time_utils import user_month_key

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.fsm.context import FSMContext

from app.fsm.states import ExpenseFlow, IncomeFlow, TransferFlow
from app.domain.validators import parse_positive_int, clean_note
from app.domain.money import parse_money_for_user
from app.domain.services.ai_service import simple_feedback
from app.domain.services.accounting_service import (
    get_balance_after,
    add_expense_v2,
    add_income,
    add_transfer,
)

from app.db.repositories.accounts_repo import list_accounts, get_account
from app.db.repositories.categories_repo import list_categories, get_category, create_category, name_exists_any_kind
from app.db.repositories.settings_repo import get_settings, get_lang
from app.db.repositories.budgets_repo import (
    get_category_budget,
    month_spent_by_category,
    month_spent_map,
)

from app.handlers.common import cancel_to_main_menu, is_cancel_text, deny_feature_message, build_main_menu_markup, neutralize_keyboard
from app.domain.services.access_service import FEATURE_TRANSFER, can_use_feature
from app.ui.i18n import text_matches_key, t as _i18n_t, t_category
from app.ui.keyboards import (
    cancel_kb,
    accounts_kb,
    categories_kb,
    yes_no_kb,
    main_menu,
    budgets_categories_kb,
)
from app.ui.formatters import fmt_money

router = Router()

PARSE_MODE = "HTML"


# =========================================================
# Common helpers
# =========================================================
def _format_month(month: str | None, lang: str = "ru") -> str:
    if not month:
        return ""

    try:
        y, m = month.split("-")
        if lang == "en":
            months = [
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"
            ]
        elif lang == "kk":
            months = [
                "қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым",
                "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"
            ]
        else:
            months = [
                "январь", "февраль", "март", "апрель", "май", "июнь",
                "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"
            ]
        return f"{months[int(m) - 1]} {y}"
    except Exception:
        return month


async def start_prefilled_expense(
    target: Message | CallbackQuery,
    state: FSMContext,
    db,
    *,
    amount: int,
    note: str | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    skip_note_prompt: bool = False,
):
    await _clear_flow_message(
        target.bot,
        target.message.chat.id if isinstance(target, CallbackQuery) else target.chat.id,
        state,
    )

    await state.clear()

    payload: dict = {
        "amount": int(amount),
        "note": note,
    }

    user_id = target.from_user.id

    acc = None
    if account_id:
        acc = await _validate_account(db, user_id, int(account_id))
        if acc:
            payload["account_id"] = int(account_id)
            payload["account_name"] = acc[1]
            payload["balance_before"] = acc[2]

    cat = None
    if category_id:
        cat = await _validate_category(db, user_id, int(category_id))
        if cat:
            _, cat_name, cat_emoji, _, _ = cat
            month = await user_month_key(db, user_id)
            category_limit = await get_category_budget(
                db=db,
                user_id=user_id,
                category_id=int(category_id),
                month=month,
            )
            payload["category_id"] = int(category_id)
            payload["category_name"] = cat_name
            payload["category_emoji"] = (cat_emoji or "")
            payload["category_limit"] = category_limit
            payload["category_limit_month"] = month

    await state.update_data(**payload)

    if not payload.get("account_id"):
        await state.set_state(ExpenseFlow.account)
        await _exp_render_account(target, state, db)
        return

    if not payload.get("category_id"):
        await state.set_state(ExpenseFlow.category)
        await _exp_render_category(target, state, db)
        return

    if note is None and not skip_note_prompt:
        await state.set_state(ExpenseFlow.need_note)
        await _exp_render_need_note(target, state)
        return

    await state.set_state(ExpenseFlow.confirm)
    await _exp_render_confirm(target, state, db)

async def start_prefilled_income(
    target: Message | CallbackQuery,
    state: FSMContext,
    db,
    *,
    amount: int,
    note: str | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    skip_note_prompt: bool = False,
):
    await _clear_flow_message(
        target.bot,
        target.message.chat.id if isinstance(target, CallbackQuery) else target.chat.id,
        state,
    )

    await state.clear()

    payload: dict = {
        "amount": int(amount),
        "note": note,
    }

    user_id = target.from_user.id

    acc = None
    if account_id:
        acc = await _validate_account(db, user_id, int(account_id))
        if acc:
            payload["account_id"] = int(account_id)
            payload["account_name"] = acc[1]
            payload["balance_before"] = acc[2]

    cat = None
    if category_id:
        cat = await _validate_category(db, user_id, int(category_id))
        if cat:
            _, cat_name, cat_emoji, _, _ = cat
            payload["category_id"] = int(category_id)
            payload["category_name"] = cat_name
            payload["category_emoji"] = (cat_emoji or "")

    await state.update_data(**payload)

    if not payload.get("account_id"):
        await state.set_state(IncomeFlow.account)
        await _inc_render_account(target, state, db)
        return

    if not payload.get("category_id"):
        await state.set_state(IncomeFlow.category)
        await _inc_render_category(target, state, db)
        return

    if note is None and not skip_note_prompt:
        await state.set_state(IncomeFlow.need_note)
        await _inc_render_need_note(target, state)
        return

    await state.set_state(IncomeFlow.confirm)
    await _inc_render_confirm(target, state, db)


async def _delete_flow_message(bot, chat_id: int, state: FSMContext):
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")
    prompt_message_id = data.get("prompt_message_id")

    for msg_id in [flow_message_id, prompt_message_id]:
        if not msg_id:
            continue
        try:
            await bot.delete_message(chat_id=chat_id, message_id=int(msg_id))
        except Exception:
            pass

def _prev_month_key(month: str) -> str:
    y, m = map(int, month.split("-"))
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"

async def _clear_flow_message(bot, chat_id: int, state: FSMContext):
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")
    if not flow_message_id:
        return

    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=int(flow_message_id),
            reply_markup=None,
        )
    except Exception:
        pass


async def _clear_prompt_message(bot, chat_id: int, state: FSMContext):
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    if not prompt_message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(prompt_message_id))
    except Exception:
        pass
    await state.update_data(prompt_message_id=None)


async def _flow_enter_text_mode(
    target: Message | CallbackQuery,
    state: FSMContext,
    screen_text: str,
    *,
    prompt_text: str | None = None,
    lang: str = "ru",
) -> None:
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")

    if isinstance(target, CallbackQuery):
        bot = target.bot
        chat_id = target.message.chat.id
        current_message = target.message
        send = target.message.answer
    else:
        bot = target.bot
        chat_id = target.chat.id
        current_message = None
        send = target.answer

    await _clear_prompt_message(bot, chat_id, state)

    if flow_message_id:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=int(flow_message_id),
                reply_markup=None,
            )
        except Exception:
            pass
    elif current_message is not None:
        flow_message_id = current_message.message_id

    if current_message is not None:
        try:
            await current_message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    prompt = await send(prompt_text or screen_text, reply_markup=cancel_kb(lang), parse_mode=PARSE_MODE)
    await state.update_data(flow_message_id=flow_message_id, prompt_message_id=prompt.message_id)

async def _note_max(db, user_id: int) -> int:
    s = await get_settings(db, user_id)
    return int(s[4]) if s else 80


def _is_cancel_text(text: str | None) -> bool:
    return is_cancel_text(text)


async def _safe_delete_message(msg: Message):
    try:
        await msg.delete()
    except Exception:
        pass


async def _safe_remove_markup(msg: Message):
    try:
        await msg.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def _safe_edit_text(msg: Message, text: str, reply_markup=None):
    try:
        await msg.edit_text(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        return True
    except Exception:
        return False


async def _flow_render(
    target: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    *,
    reply_markup=None,
) -> Message | None:
    if isinstance(reply_markup, ReplyKeyboardMarkup):
        lang = (await state.get_data()).get("lang", "ru")
        await _flow_enter_text_mode(target, state, text, lang=lang)
        return None

    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")

    if isinstance(target, Message):
        await _clear_prompt_message(target.bot, target.chat.id, state)
        if flow_message_id:
            try:
                await target.bot.edit_message_reply_markup(
                    chat_id=target.chat.id,
                    message_id=int(flow_message_id),
                    reply_markup=None,
                )
            except Exception:
                pass
        sent = await target.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        await state.update_data(flow_message_id=sent.message_id)
        return sent

    bot = target.bot
    chat_id = target.message.chat.id
    fallback_message = target.message

    await _clear_prompt_message(bot, chat_id, state)

    if flow_message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=int(flow_message_id),
                text=text,
                reply_markup=reply_markup,
                parse_mode=PARSE_MODE,
            )
            return None
        except Exception:
            pass

    if flow_message_id:
        try:
            if int(flow_message_id) != fallback_message.message_id:
                await bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=int(flow_message_id),
                    reply_markup=None,
                )
        except Exception:
            pass

    edited = await _safe_edit_text(fallback_message, text, reply_markup=reply_markup)
    if edited:
        await state.update_data(flow_message_id=fallback_message.message_id)
        return fallback_message

    sent = await target.message.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    await state.update_data(flow_message_id=sent.message_id)
    return sent

async def _flow_finish(
    ctx: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    db=None,
):
    """
    Финал сценария:
    - удаляем экранное сообщение сценария
    - очищаем FSM
    - отправляем одно финальное сообщение с main_menu
    """
    if isinstance(ctx, CallbackQuery):
        await _delete_flow_message(ctx.bot, ctx.message.chat.id, state)
        await state.clear()
        lang = await get_lang(db, ctx.from_user.id) if db is not None else "ru"
        await ctx.message.answer(text, reply_markup=await build_main_menu_markup(db, ctx.from_user.id, lang), parse_mode=PARSE_MODE)
        await ctx.answer()
        return

    await _delete_flow_message(ctx.bot, ctx.chat.id, state)
    await state.clear()
    lang = await get_lang(db, ctx.from_user.id) if db is not None else "ru"
    await ctx.answer(text, reply_markup=await build_main_menu_markup(db, ctx.from_user.id, lang), parse_mode=PARSE_MODE)


def _action_buttons_kb(
    save_cb: str,
    *,
    edit1_text: str | None = None,
    edit1_cb: str | None = None,
    edit2_text: str | None = None,
    edit2_cb: str | None = None,
    edit3_text: str | None = None,
    edit3_cb: str | None = None,
    save_text: str = "✅ Сохранить",
    cancel_text: str = "❌ Отмена",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=save_text, callback_data=save_cb)]
    ]

    edit_row: list[InlineKeyboardButton] = []
    if edit1_text and edit1_cb:
        edit_row.append(InlineKeyboardButton(text=edit1_text, callback_data=edit1_cb))
    if edit2_text and edit2_cb:
        edit_row.append(InlineKeyboardButton(text=edit2_text, callback_data=edit2_cb))
    if edit_row:
        rows.append(edit_row)

    if edit3_text and edit3_cb:
        rows.append([InlineKeyboardButton(text=edit3_text, callback_data=edit3_cb)])

    rows.append(
        [InlineKeyboardButton(text=cancel_text, callback_data=save_cb.rsplit(":", 1)[0] + ":cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _overdraft_kb(
    prefix: str,
    *,
    yes_text: str = "✅ Провести",
    no_text: str = "⬅️ Назад",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=yes_text, callback_data=f"{prefix}:yes"),
                InlineKeyboardButton(text=no_text, callback_data=f"{prefix}:no"),
            ]
        ]
    )


def _exp_confirm_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return _action_buttons_kb(
        "expcfm:save",
        edit1_text=_i18n_t(lang, "TX_EDIT_CAT"),
        edit1_cb="expcfm:category",
        edit2_text=_i18n_t(lang, "TX_EDIT_NOTE"),
        edit2_cb="expcfm:note",
        save_text=_i18n_t(lang, "BTN_SAVE"),
        cancel_text=_i18n_t(lang, "BTN_CANCEL"),
    )


def _inc_confirm_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return _action_buttons_kb(
        "inccfm:save",
        edit1_text=_i18n_t(lang, "TX_EDIT_CAT"),
        edit1_cb="inccfm:category",
        edit2_text=_i18n_t(lang, "TX_EDIT_NOTE"),
        edit2_cb="inccfm:note",
        save_text=_i18n_t(lang, "BTN_SAVE"),
        cancel_text=_i18n_t(lang, "BTN_CANCEL"),
    )


def _tr_confirm_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    return _action_buttons_kb(
        "trcfm:save",
        edit1_text=_i18n_t(lang, "TX_EDIT_FROM"),
        edit1_cb="trcfm:from",
        edit2_text=_i18n_t(lang, "TX_EDIT_TO"),
        edit2_cb="trcfm:to",
        edit3_text=_i18n_t(lang, "TX_EDIT_NOTE"),
        edit3_cb="trcfm:note",
        save_text=_i18n_t(lang, "TX_BTN_PROCEED_TR"),
        cancel_text=_i18n_t(lang, "BTN_CANCEL"),
    )


def _exp_summary_lines(data: dict, lang: str = "ru") -> str:
    lines = []

    if data.get("amount") is not None:
        lines.append(f"{_i18n_t(lang, 'TX_SUM')}: <b>{fmt_money(int(data['amount']))}</b>")

    if data.get("account_name"):
        lines.append(f"{_i18n_t(lang, 'TX_ACC')}: <b>{escape(str(data['account_name']))}</b>")

    if data.get("category_name"):
        emoji = (data.get("category_emoji") or "").strip()
        label = f"{emoji} {escape(t_category(str(data['category_name']), lang))}".strip()
        lines.append(f"{_i18n_t(lang, 'TX_CAT')}: <b>{label}</b>")

    if data.get("note"):
        lines.append(f"{_i18n_t(lang, 'TX_NOTE')}: <i>{escape(str(data['note']))}</i>")

    return "\n".join(lines)


def _inc_summary_lines(data: dict, lang: str = "ru") -> str:
    lines = []

    if data.get("amount") is not None:
        lines.append(f"{_i18n_t(lang, 'TX_INC_SUM')}: <b>{fmt_money(int(data['amount']))}</b>")

    if data.get("account_name"):
        lines.append(f"{_i18n_t(lang, 'TX_ACC')}: <b>{escape(str(data['account_name']))}</b>")

    if data.get("category_name"):
        emoji = (data.get("category_emoji") or "").strip()
        label = f"{emoji} {escape(t_category(str(data['category_name']), lang))}".strip()
        lines.append(f"{_i18n_t(lang, 'TX_INC_CAT')}: <b>{label}</b>")

    if data.get("note"):
        lines.append(f"{_i18n_t(lang, 'TX_NOTE')}: <i>{escape(str(data['note']))}</i>")

    return "\n".join(lines)


def _tr_summary_lines(data: dict, lang: str = "ru") -> str:
    lines = [_i18n_t(lang, 'TX_TR_STEP_1').split('\\n')[0], ""]

    if data.get("amount") is not None:
        lines.append(f"{_i18n_t(lang, 'TX_SUM')}: <b>{fmt_money(int(data['amount']))}</b>")

    if data.get("from_name"):
        lines.append(f"{_i18n_t(lang, 'TX_FROM')}: <b>{escape(str(data['from_name']))}</b>")

    if data.get("to_name"):
        lines.append(f"{_i18n_t(lang, 'TX_TO')}: <b>{escape(str(data['to_name']))}</b>")

    if data.get("note"):
        lines.append(f"{_i18n_t(lang, 'TX_NOTE')}: <i>{escape(str(data['note']))}</i>")

    return "\n".join(lines)


async def _validate_account(db, user_id: int, account_id: int):
    acc = await get_account(db, user_id, account_id)
    if not acc:
        return None
    if int(acc[3] or 0) == 1:
        return None
    return acc


async def _validate_category(db, user_id: int, category_id: int):
    cat = await get_category(db, user_id, category_id)
    if not cat:
        return None
    _, _, _, _, is_archived = cat
    if int(is_archived or 0) == 1:
        return None
    return cat


async def _try_auto_pick_only_account(
    db,
    user_id: int,
    target: Message | CallbackQuery,
    state: FSMContext,
    *,
    is_expense: bool,
) -> bool:
    """If the user has exactly one active account, skip the picker and continue."""
    accs = await list_accounts(db, user_id)
    active = [r for r in accs if int(r[3] or 0) == 0]
    if len(active) != 1:
        return False
    acc_id = int(active[0][0])
    acc = await _validate_account(db, user_id, acc_id)
    if not acc:
        return False
    await state.update_data(
        account_id=acc_id,
        account_name=acc[1],
        balance_before=acc[2],
    )
    data = await state.get_data()
    if is_expense:
        if data.get("category_id"):
            await state.set_state(ExpenseFlow.confirm)
            await _exp_render_confirm(target, state, db)
        else:
            await state.set_state(ExpenseFlow.category)
            await _exp_render_category(target, state, db)
    else:
        if data.get("category_id"):
            await state.set_state(IncomeFlow.confirm)
            await _inc_render_confirm(target, state, db)
        else:
            await state.set_state(IncomeFlow.category)
            await _inc_render_category(target, state, db)
    return True


# =========================================================
# Expense screens
# =========================================================

async def _exp_render_amount(target: Message | CallbackQuery, state: FSMContext):
    lang = (await state.get_data()).get("lang", "ru")
    await _flow_render(target, state, _i18n_t(lang, "TX_EXP_STEP_1"), reply_markup=cancel_kb(lang))


async def _exp_render_account(target: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    accs = await list_accounts(db, target.from_user.id)
    active = [r for r in accs if int(r[3] or 0) == 0]
    if not active:
        await _flow_render(
            target,
            state,
            f"{_exp_summary_lines(data, lang)}\n\n{_i18n_t(lang, 'TX_NO_ACTIVE_ACCOUNTS')}",
            reply_markup=cancel_kb(lang),
        )
        return
    if await _try_auto_pick_only_account(
        db, target.from_user.id, target, state, is_expense=True
    ):
        return
    text = (
        f"{_exp_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_EXP_STEP_2')}"
    )
    await _flow_render(target, state, text, reply_markup=accounts_kb(accs, "expacc", lang))


async def _exp_render_category(target: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    user_id = target.from_user.id

    cats = await list_categories(db, user_id, kind="expense")
    month = await user_month_key(db, user_id)

    spent_map = await month_spent_map(db, user_id, month)
    left_map: dict[int, int] = {}

    for cid, name, emoji in cats:
        limit = await get_category_budget(db, user_id, month, cid)
        spent = spent_map.get(cid, 0)

        if isinstance(limit, int) and limit > 0:
            left_map[cid] = limit - spent

    text = (
        f"{_exp_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_EXP_STEP_3')}"
    )

    await _flow_render(
        target,
        state,
        text,
        reply_markup=budgets_categories_kb(
            cats,
            left_map,
            prefix="expcat",
            cancel_cb="cancel",
            lang=lang,
            add_cb="expcat:add",
        ),
    )


async def _exp_render_need_note(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    text = (
        f"{_exp_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_EXP_STEP_4_ASK')}"
    )
    await _flow_render(target, state, text, reply_markup=yes_no_kb("expnote", lang))


async def _exp_render_note_input(target: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    max_len = await _note_max(db, target.from_user.id)
    text = (
        f"{_exp_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_EXP_STEP_4_INPUT').format(max=max_len)}"
    )
    await _flow_render(target, state, text, reply_markup=cancel_kb(lang))


async def _exp_render_confirm(target: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    amt = int(data["amount"])
    acc_id = int(data["account_id"])
    user_id = target.from_user.id

    bal_before, bal_after, acc_name = (
        await get_balance_after(db, user_id, acc_id, -amt)
    ) or (None, None, None)

    if bal_before is None:
        await state.clear()
        return await (
            target.message.answer("Счёт не найден.", reply_markup=await build_main_menu_markup(db, target.from_user.id, await get_lang(db, target.from_user.id)))
            if isinstance(target, CallbackQuery)
            else target.answer("Счёт не найден.", reply_markup=await build_main_menu_markup(db, target.from_user.id, await get_lang(db, target.from_user.id)))
        )

    await state.update_data(
        balance_before=bal_before,
        balance_after=bal_after,
        account_name=acc_name or data.get("account_name"),
    )
    data = await state.get_data()

    cat_emoji = (data.get("category_emoji") or "").strip()
    cat_name = escape(t_category(str(data.get("category_name") or _i18n_t(lang, "TX_CAT_LIMIT_NONE")), lang))
    cat_label = f"{cat_emoji} {cat_name}".strip()

    category_id = int(data["category_id"])
    category_limit = data.get("category_limit")
    month = await user_month_key(db, user_id)
    spent_before = await month_spent_by_category(db, user_id, month, category_id)
    after_spent = spent_before + amt
    lines = [
        f"{_i18n_t(lang, 'TX_EXP_CONFIRM_HEAD')}",
        "",
        f"{_i18n_t(lang, 'TX_CAT')}: <b>{cat_label}</b>",
    ]

    if isinstance(category_limit, int) and category_limit > 0:
        left_after = category_limit - after_spent
        lines.append(_i18n_t(lang, "TX_EXP_CONFIRM_LIMIT").format(limit=fmt_money(category_limit)))
        lines.append(_i18n_t(lang, "TX_EXP_CONFIRM_SPENT").format(spent=fmt_money(spent_before)))

        if left_after >= 0:
            lines.append(_i18n_t(lang, "TX_EXP_CONFIRM_LEFT").format(left=fmt_money(left_after)))
        else:
            lines.append(_i18n_t(lang, "TX_EXP_CONFIRM_OVER").format(over=fmt_money(abs(left_after))))
    else:
        lines.append(_i18n_t(lang, "TX_EXP_CONFIRM_LIMIT_NONE"))

    lines.extend([
        _i18n_t(lang, "TX_EXP_CONFIRM_AMOUNT").format(amount=fmt_money(int(data['amount']))),
        _i18n_t(lang, "TX_EXP_CONFIRM_ACCOUNT").format(account=escape(str(data.get('account_name') or '—'))),
        _i18n_t(lang, "TX_EXP_CONFIRM_BALANCE").format(before=fmt_money(int(bal_before)), after=fmt_money(int(bal_after))),
    ])

    if data.get("note"):
        lines.append(f"{_i18n_t(lang, 'TX_NOTE')}: <i>{escape(str(data['note']))}</i>")

    if int(bal_after) < 0:
        lines += ["", _i18n_t(lang, "TX_EXP_CONFIRM_MINUS")]

    lines += ["", f"{_i18n_t(lang, 'TX_EXP_STEP_5')}", f"{_i18n_t(lang, 'TX_EXP_CONFIRM_SAVE')}"]

    await _flow_render(target, state, "\n".join(lines), reply_markup=_exp_confirm_kb(lang))


# =========================================================
# Expense handlers
# =========================================================

@router.message(ExpenseFlow.amount, F.text)
async def exp_amount(m: Message, state: FSMContext, db):
    if _is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    amt = await parse_money_for_user(db, m.from_user.id, m.text)
    if amt is None:
        lang = await get_lang(db, m.from_user.id)
        return await m.answer(_i18n_t(lang, "AMOUNT_INVALID"), reply_markup=cancel_kb(lang))

    await state.update_data(amount=amt)
    await state.set_state(ExpenseFlow.account)

    await _exp_render_account(m, state, db)


@router.callback_query(ExpenseFlow.account, F.data.regexp(r"^expacc:\d+$"))
async def exp_account(c: CallbackQuery, state: FSMContext, db):
    acc_id = int(c.data.split(":")[1])
    acc = await _validate_account(db, c.from_user.id, acc_id)

    if not acc:
        await c.answer("Account not found" if (await get_lang(db, c.from_user.id))=="en" else ("Шот табылмады" if (await get_lang(db, c.from_user.id))=="kk" else "Счёт не найден"), show_alert=True)
        return

    await state.update_data(
        account_id=acc_id,
        account_name=acc[1],
        balance_before=acc[2],
    )

    data = await state.get_data()
    if data.get("category_id"):
        await state.set_state(ExpenseFlow.confirm)
        await _exp_render_confirm(c, state, db)
        await c.answer()
        return

    await state.set_state(ExpenseFlow.category)
    await _exp_render_category(c, state, db)
    await c.answer()


@router.callback_query(ExpenseFlow.category, F.data.regexp(r"^expcat:\d+$"))
async def exp_category(c: CallbackQuery, state: FSMContext, db):
    cat_id = int(c.data.split(":")[1])
    cat = await _validate_category(db, c.from_user.id, cat_id)

    if not cat:
        await c.answer("Category not found" if (await get_lang(db, c.from_user.id))=="en" else ("Санат табылмады" if (await get_lang(db, c.from_user.id))=="kk" else "Категория не найдена"), show_alert=True)
        return

    _, cat_name, cat_emoji, _, _ = cat

    month = await user_month_key(db, c.from_user.id)
    category_limit = await get_category_budget(
        db=db,
        user_id=c.from_user.id,
        category_id=cat_id,
        month=month,
    )

    await state.update_data(
        category_id=cat_id,
        category_name=cat_name,
        category_emoji=(cat_emoji or ""),
        category_limit=category_limit,
        category_limit_month=month,
    )
    await state.set_state(ExpenseFlow.need_note)

    await _exp_render_need_note(c, state)
    await c.answer()


@router.callback_query(ExpenseFlow.category, F.data == "expcat:add")
async def exp_category_add_prompt(c: CallbackQuery, state: FSMContext, db):
    lang = (await state.get_data()).get("lang", "ru")
    text = (
        "➕ <b>Новая категория</b>\n\n"
        "Напиши название новой категории одним коротким словом.\n"
        "Она будет добавлена в список «Расход»."
    )
    if lang == "en":
        text = "➕ <b>New Category</b>\n\nType the name of the new category.\nIt will be added to the 'Expense' list."
    elif lang == "kk":
        text = "➕ <b>Жаңа санат</b>\n\nЖаңа санаттың атын жазыңыз.\nОл «Шығыс» тізіміне қосылады."

    await state.set_state(ExpenseFlow.add_category)
    await _flow_render(c, state, text, reply_markup=cancel_kb(lang))
    await c.answer()


@router.message(ExpenseFlow.add_category, F.text)
async def exp_category_add_handle(m: Message, state: FSMContext, db):
    raw = (m.text or "").strip()
    if _is_cancel_text(raw):
        await cancel_to_main_menu(m, state, db)
        return

    lang = (await state.get_data()).get("lang", "ru")
    if len(raw) < 2 or len(raw) > 20:
        await m.answer("❌ Название должно быть от 2 до 20 символов." if lang=="ru" else "❌ Name must be 2-20 chars.")
        return

    # Check for duplicates
    if await name_exists_any_kind(db, m.from_user.id, raw):
        await m.answer("❌ Категория с таким названием уже есть." if lang=="ru" else "❌ Category already exists.")
        return

    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    cat_id = await create_category(db, m.from_user.id, raw, "🔹", "expense", ts)
    
    await state.update_data(
        category_id=cat_id,
        category_name=raw,
        category_emoji="🔹",
        category_limit=None,
        category_limit_month=None,
    )
    await state.set_state(ExpenseFlow.need_note)
    await _exp_render_need_note(m, state)


@router.callback_query(IncomeFlow.category, F.data == "inccat:add")
async def inc_category_add_prompt(c: CallbackQuery, state: FSMContext, db):
    lang = (await state.get_data()).get("lang", "ru")
    text = (
        "➕ <b>Новая категория</b>\n\n"
        "Напиши название новой категории одним коротким словом.\n"
        "Она будет добавлена в список «Доход»."
    )
    if lang == "en":
        text = "➕ <b>New Category</b>\n\nType the name of the new category.\nIt will be added to the 'Income' list."
    elif lang == "kk":
        text = "➕ <b>Жаңа санат</b>\n\nЖаңа санаттың атын жазыңыз.\nОл «Кіріс» тізіміне қосылады."

    await state.set_state(IncomeFlow.add_category)
    await _flow_render(c, state, text, reply_markup=cancel_kb(lang))
    await c.answer()


@router.message(IncomeFlow.add_category, F.text)
async def inc_category_add_handle(m: Message, state: FSMContext, db):
    raw = (m.text or "").strip()
    if _is_cancel_text(raw):
        await cancel_to_main_menu(m, state, db)
        return

    lang = (await state.get_data()).get("lang", "ru")
    if len(raw) < 2 or len(raw) > 20:
        await m.answer("❌ Название должно быть от 2 до 20 символов." if lang=="ru" else "❌ Name must be 2-20 chars.")
        return

    if await name_exists_any_kind(db, m.from_user.id, raw):
        await m.answer("❌ Категория с таким названием уже есть." if lang=="ru" else "❌ Category already exists.")
        return

    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    cat_id = await create_category(db, m.from_user.id, raw, "🔹", "income", ts)
    
    await state.update_data(
        category_id=cat_id,
        category_name=raw,
        category_emoji="🔹",
    )
    await state.set_state(IncomeFlow.need_note)
    await _inc_render_need_note(m, state)


@router.callback_query(ExpenseFlow.need_note, F.data.startswith("expnote:"))
async def exp_need_note(c: CallbackQuery, state: FSMContext, db):
    ans = c.data.split(":")[1]

    if ans == "yes":
        await state.set_state(ExpenseFlow.note)
        await _exp_render_note_input(c, state, db)
    else:
        await state.update_data(note=None)
        await state.set_state(ExpenseFlow.confirm)
        await _exp_render_confirm(c, state, db)

    await c.answer()


@router.message(ExpenseFlow.note, F.text | F.caption)
async def exp_note(m: Message, state: FSMContext, db):
    raw = (m.text or m.caption or "").strip()
    if _is_cancel_text(raw):
        await cancel_to_main_menu(m, state, db)
        return

    max_len = await _note_max(db, m.from_user.id)
    note = clean_note(raw, max_len)
    if not note:
        lang = (await state.get_data()).get("lang", "ru")
        return await m.answer(_i18n_t(lang, "NOTE_INVALID_LEN").format(max=max_len), reply_markup=cancel_kb(lang))

    await state.update_data(note=note)
    await state.set_state(ExpenseFlow.confirm)


    await _exp_render_confirm(m, state, db)


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_EXPENSE"))
async def exp_start(m: Message, state: FSMContext, db):
    await _clear_flow_message(m.bot, m.chat.id, state)
    await state.clear()
    lang = await get_lang(db, m.from_user.id)
    await state.update_data(lang=lang)
    await state.set_state(ExpenseFlow.amount)
    await _exp_render_amount(m, state)


@router.callback_query(ExpenseFlow.confirm, F.data.startswith("expcfm:"))
async def exp_confirm(c: CallbackQuery, state: FSMContext, db):
    action = c.data.split(":")[1]

    if action == "cancel":
        lang = (await state.get_data()).get("lang", "ru")
        await _flow_finish(c, state, _i18n_t(lang, "CANCELLED").split(".")[0] + ".", db)
        return

    if action == "category":
        await state.set_state(ExpenseFlow.category)
        await _exp_render_category(c, state, db)
        await c.answer()
        return

    if action == "note":
        await state.set_state(ExpenseFlow.note)
        await _exp_render_note_input(c, state, db)
        await c.answer()
        return

    if action == "save":
        # Defuse the inline keyboard immediately so a rage-tap can't fire this
        # callback twice and create a duplicate transaction (audit 1.3).
        await neutralize_keyboard(c)
        data = await state.get_data()
        bal_after = data.get("balance_after")

        if isinstance(bal_after, int) and bal_after < 0:
            await state.set_state(ExpenseFlow.confirm_overdraft)
            text = (
                "⚠️ <b>Подтверждение перерасхода</b>\n\n"
                f"💳 Счёт: <b>{escape(str(data['account_name']))}</b>\n"
                f"📊 Баланс: <b>{fmt_money(int(data['balance_before']))} → {fmt_money(int(data['balance_after']))}</b>\n\n"
                "Провести расход?"
            )
            await _flow_render(
                c,
                state,
                text,
                reply_markup=_overdraft_kb("expod", yes_text="✅ Провести", no_text="⬅️ Назад"),
            )
            await c.answer()
            return

        await _exp_save(c, state, db)
        return


@router.callback_query(ExpenseFlow.confirm_overdraft, F.data.startswith("expod:"))
async def exp_od(c: CallbackQuery, state: FSMContext, db):
    ans = c.data.split(":")[1]

    if ans == "no":
        await state.set_state(ExpenseFlow.confirm)
        await _exp_render_confirm(c, state, db)
        await c.answer()
        return

    await neutralize_keyboard(c)
    await _exp_save(c, state, db)


async def _exp_save(ctx: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()

    tx_id, meta = await add_expense_v2(
        db,
        ctx.from_user.id,
        int(data["amount"]),
        int(data["account_id"]),
        int(data["category_id"]),
        data.get("note"),
    )

    feedback = simple_feedback(int(data["amount"]), None)

    cat_name = data.get("category_name") or "Без категории"
    cat_emoji = (data.get("category_emoji") or "").strip()
    cat_label = f"{cat_emoji} {cat_name}".strip()

    bal_before_txt = (
        fmt_money(int(data["balance_before"]))
        if isinstance(data.get("balance_before"), int)
        else str(data.get("balance_before") or "—")
    )
    bal_after_txt = (
        fmt_money(int(data["balance_after"]))
        if isinstance(data.get("balance_after"), int)
        else str(data.get("balance_after") or "—")
    )

    lang = data.get("lang", "ru")
    msg = (
        f"{_i18n_t(lang, 'TX_EXP_SUCCESS')}\n\n"
        f"{_i18n_t(lang, 'TX_CAT')}: {escape(cat_label)}\n"
        f"{_i18n_t(lang, 'TX_EXP_CONFIRM_AMOUNT').format(amount=fmt_money(int(data['amount'])))}\n"
        f"{_i18n_t(lang, 'TX_EXP_CONFIRM_ACCOUNT').format(account=escape(str(data['account_name'])))}\n"
        f"{_i18n_t(lang, 'TX_EXP_CONFIRM_BALANCE').format(before=bal_before_txt, after=bal_after_txt)}\n"
        f"\n<i>ID: {tx_id}</i>"
    )

    if data.get("note"):
        msg += f"\n{_i18n_t(lang, 'TX_NOTE')}: <i>{escape(str(data['note']))}</i>"

    dl = meta.get("daily_limit")
    after_day = meta.get("after_total")
    st_day = meta.get("daily_state")
    if isinstance(dl, int) and isinstance(after_day, int) and dl > 0:
        left = dl - after_day
        if st_day == "warn":
            msg += _i18n_t(lang, "TX_DAILY_LIMIT_WARN").format(left=fmt_money(left))
        elif st_day == "over":
            msg += _i18n_t(lang, "TX_DAILY_LIMIT_OVER").format(left=fmt_money(abs(left)))
        elif st_day == "hard_over":
            msg += _i18n_t(lang, "TX_DAILY_LIMIT_HARD_OVER").format(left=fmt_money(abs(left)))

    cb = meta.get("cat_budget")
    st_cat = meta.get("cat_state")
    left_cat = meta.get("cat_left")
    month = _format_month(meta.get("month"), lang)
    if isinstance(cb, int) and cb > 0 and isinstance(month, str) and isinstance(left_cat, int):
        if st_cat == "warn":
            msg += _i18n_t(lang, "TX_CAT_LIMIT_WARN").format(month=escape(month), left=fmt_money(left_cat))
        elif st_cat == "over":
            msg += _i18n_t(lang, "TX_CAT_LIMIT_OVER").format(month=escape(month), left=fmt_money(abs(left_cat)))
        elif st_cat == "hard_over":
            msg += _i18n_t(lang, "TX_CAT_LIMIT_HARD_OVER").format(month=escape(month), left=fmt_money(abs(left_cat)))

    if feedback:
        msg += f"\n\n<i>{escape(str(feedback))}</i>"

    await _flow_finish(ctx, state, msg, db)


# =========================================================
# Income screens
# =========================================================

async def _inc_render_amount(target: Message | CallbackQuery, state: FSMContext):
    lang = (await state.get_data()).get("lang", "ru")
    await _flow_render(target, state, _i18n_t(lang, "TX_INC_STEP_1"), reply_markup=cancel_kb(lang))


async def _inc_render_account(target: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    accs = await list_accounts(db, target.from_user.id)
    active = [r for r in accs if int(r[3] or 0) == 0]
    if not active:
        await _flow_render(
            target,
            state,
            f"{_inc_summary_lines(data, lang)}\n\n{_i18n_t(lang, 'TX_NO_ACTIVE_ACCOUNTS')}",
            reply_markup=cancel_kb(lang),
        )
        return
    if await _try_auto_pick_only_account(
        db, target.from_user.id, target, state, is_expense=False
    ):
        return
    text = (
        f"{_inc_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_INC_STEP_2')}"
    )
    await _flow_render(target, state, text, reply_markup=accounts_kb(accs, "incacc", lang))


async def _inc_render_category(target: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    cats = await list_categories(db, target.from_user.id, "income")
    text = (
        f"{_inc_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_INC_STEP_3')}"
    )
    page = int(data.get("inc_cat_page", 0) or 0)
    await _flow_render(target, state, text, reply_markup=categories_kb(cats, "inccat", page=page, add_cb="inccat:add", lang=lang))


async def _inc_render_need_note(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    text = (
        f"{_inc_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_INC_STEP_4_ASK')}"
    )
    await _flow_render(target, state, text, reply_markup=yes_no_kb("incnote", lang))


async def _inc_render_note_input(target: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    max_len = await _note_max(db, target.from_user.id)
    text = (
        f"{_inc_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_INC_STEP_4_INPUT').format(max=max_len)}"
    )
    await _flow_render(target, state, text, reply_markup=cancel_kb(lang))


async def _inc_render_confirm(target: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    lang = data.get("lang", "ru")

    acc = await _validate_account(db, target.from_user.id, int(data["account_id"]))
    if not acc:
        await state.clear()
        return await (
            target.message.answer("Счёт не найден.", reply_markup=await build_main_menu_markup(db, target.from_user.id, await get_lang(db, target.from_user.id)))
            if isinstance(target, CallbackQuery)
            else target.answer("Счёт не найден.", reply_markup=await build_main_menu_markup(db, target.from_user.id, await get_lang(db, target.from_user.id)))
        )

    bal_before = int(acc[2])
    bal_after = bal_before + int(data["amount"])

    await state.update_data(account_name=acc[1])
    data = await state.get_data()

    cat_emoji = (data.get("category_emoji") or "").strip()
    cat_name = escape(t_category(str(data.get("category_name") or _i18n_t(lang, "TX_CAT_LIMIT_NONE")), lang))
    cat_label = f"{cat_emoji} {cat_name}".strip()
    lines = [
        f"{_i18n_t(lang, 'TX_INC_CONFIRM_HEAD')}",
        "",
        f"{_i18n_t(lang, 'TX_CAT')}: <b>{cat_label}</b>",
        _i18n_t(lang, "TX_INC_CONFIRM_AMOUNT").format(amount=fmt_money(int(data['amount']))),
        _i18n_t(lang, "TX_EXP_CONFIRM_ACCOUNT").format(account=escape(str(data['account_name']))),
        _i18n_t(lang, "TX_EXP_CONFIRM_BALANCE").format(before=fmt_money(bal_before), after=fmt_money(bal_after)),
    ]

    if data.get("note"):
        lines.append(f"{_i18n_t(lang, 'TX_NOTE')}: <i>{escape(str(data['note']))}</i>")

    lines += ["", f"{_i18n_t(lang, 'TX_INC_CONFIRM_ASK')}"]

    await _flow_render(target, state, "\n".join(lines), reply_markup=_inc_confirm_kb(lang))

# =========================================================
# Income handlers
# =========================================================

@router.message(IncomeFlow.amount, F.text)
async def inc_amount(m: Message, state: FSMContext, db):
    if _is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    amt = await parse_money_for_user(db, m.from_user.id, m.text)
    if amt is None:
        lang = await get_lang(db, m.from_user.id)
        return await m.answer(_i18n_t(lang, "AMOUNT_INVALID"), reply_markup=cancel_kb(lang))

    await state.update_data(amount=amt)
    await state.set_state(IncomeFlow.account)


    await _inc_render_account(m, state, db)


@router.callback_query(IncomeFlow.account, F.data.regexp(r"^incacc:\d+$"))
async def inc_account(c: CallbackQuery, state: FSMContext, db):
    acc_id = int(c.data.split(":")[1])
    acc = await _validate_account(db, c.from_user.id, acc_id)

    if not acc:
        await c.answer("Account not found" if (await get_lang(db, c.from_user.id))=="en" else ("Шот табылмады" if (await get_lang(db, c.from_user.id))=="kk" else "Счёт не найден"), show_alert=True)
        return

    await state.update_data(
        account_id=acc_id,
        account_name=acc[1],
        balance_before=acc[2],
    )

    data = await state.get_data()
    if data.get("category_id"):
        await state.set_state(IncomeFlow.confirm)
        await _inc_render_confirm(c, state, db)
        await c.answer()
        return

    await state.set_state(IncomeFlow.category)
    await _inc_render_category(c, state, db)
    await c.answer()

@router.callback_query(IncomeFlow.category, F.data.regexp(r"^inccat:page:\d+$"))
async def inc_category_page(c: CallbackQuery, state: FSMContext, db):
    page = int(c.data.split(":")[2])
    await state.update_data(inc_cat_page=page)
    await _inc_render_category(c, state, db)
    await c.answer()


@router.callback_query(IncomeFlow.category, F.data.regexp(r"^inccat:\d+$"))
async def inc_category(c: CallbackQuery, state: FSMContext, db):
    cat_id = int(c.data.split(":")[1])
    cat = await _validate_category(db, c.from_user.id, cat_id)

    if not cat:
        await c.answer("Category not found" if (await get_lang(db, c.from_user.id))=="en" else ("Санат табылмады" if (await get_lang(db, c.from_user.id))=="kk" else "Категория не найдена"), show_alert=True)
        return

    _, cat_name, cat_emoji, _, _ = cat
    await state.update_data(
        category_id=cat_id,
        category_name=cat_name,
        category_emoji=(cat_emoji or ""),
    )
    await state.set_state(IncomeFlow.need_note)

    await _inc_render_need_note(c, state)
    await c.answer()


@router.callback_query(IncomeFlow.need_note, F.data.startswith("incnote:"))
async def inc_need_note(c: CallbackQuery, state: FSMContext, db):
    ans = c.data.split(":")[1]

    if ans == "yes":
        await state.set_state(IncomeFlow.note)
        await _inc_render_note_input(c, state, db)
    else:
        await state.update_data(note=None)
        await state.set_state(IncomeFlow.confirm)
        await _inc_render_confirm(c, state, db)

    await c.answer()


@router.message(IncomeFlow.note, F.text | F.caption)
async def inc_note(m: Message, state: FSMContext, db):
    raw = (m.text or m.caption or "").strip()
    if _is_cancel_text(raw):
        await cancel_to_main_menu(m, state, db)
        return

    max_len = await _note_max(db, m.from_user.id)
    note = clean_note(raw, max_len)
    if not note:
        lang = (await state.get_data()).get("lang", "ru")
        return await m.answer(_i18n_t(lang, "NOTE_INVALID_LEN").format(max=max_len), reply_markup=cancel_kb(lang))

    await state.update_data(note=note)
    await state.set_state(IncomeFlow.confirm)

    await _inc_render_confirm(m, state, db)


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_INCOME"))
async def inc_start(m: Message, state: FSMContext, db):
    await _clear_flow_message(m.bot, m.chat.id, state)
    await state.clear()
    lang = await get_lang(db, m.from_user.id)
    await state.update_data(lang=lang)
    await state.set_state(IncomeFlow.amount)
    await _inc_render_amount(m, state)


@router.callback_query(IncomeFlow.confirm, F.data.startswith("inccfm:"))
async def inc_confirm(c: CallbackQuery, state: FSMContext, db):
    action = c.data.split(":")[1]

    if action == "cancel":
        lang = (await state.get_data()).get("lang", "ru")
        await _flow_finish(c, state, _i18n_t(lang, "CANCELLED").split(".")[0] + ".", db)
        return

    if action == "category":
        await state.set_state(IncomeFlow.category)
        await _inc_render_category(c, state, db)
        await c.answer()
        return

    if action == "note":
        await state.set_state(IncomeFlow.note)
        await _inc_render_note_input(c, state, db)
        await c.answer()
        return

    if action == "save":
        await neutralize_keyboard(c)
        await _inc_save(c, state, db)
        return


async def _inc_save(ctx: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()

    tx_id = await add_income(
        db,
        ctx.from_user.id,
        int(data["amount"]),
        int(data["account_id"]),
        int(data["category_id"]),
        data.get("note"),
    )

    acc = await get_account(db, ctx.from_user.id, int(data["account_id"]))
    bal_after = acc[2] if acc else None

    cat_name = data.get("category_name") or "Без категории"
    cat_emoji = (data.get("category_emoji") or "").strip()
    cat_label = f"{cat_emoji} {cat_name}".strip()
    bal_after_txt = fmt_money(int(bal_after)) if isinstance(bal_after, int) else "—"

    month = await user_month_key(db, ctx.from_user.id)
    prev_month = _prev_month_key(month)
    month_txt = _format_month(month)
    prev_month_txt = _format_month(prev_month)

    # Текущий месяц: сумма, количество, максимум
    cur = await db.execute(
        """
        SELECT
            COALESCE(SUM(amount), 0),
            COUNT(*),
            COALESCE(MAX(amount), 0)
        FROM transactions
        WHERE user_id = ?
          AND type = 'income'
          AND strftime('%Y-%m', created_at) = ?
          AND deleted_at IS NULL
        """,
        (ctx.from_user.id, month),
    )
    row = await cur.fetchone()
    month_total = int(row[0] or 0)
    month_count = int(row[1] or 0)
    month_max = int(row[2] or 0)

    # Прошлый месяц: только сумма
    cur = await db.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ?
          AND type = 'income'
          AND strftime('%Y-%m', created_at) = ?
          AND deleted_at IS NULL
        """,
        (ctx.from_user.id, prev_month),
    )
    row = await cur.fetchone()
    prev_month_total = int(row[0] or 0)

    # По текущей категории за месяц
    cur = await db.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM transactions
        WHERE user_id = ?
          AND type = 'income'
          AND category_id = ?
          AND strftime('%Y-%m', created_at) = ?
          AND deleted_at IS NULL
        """,
        (ctx.from_user.id, int(data["category_id"]), month),
    )
    row = await cur.fetchone()
    cat_month_total = int(row[0] or 0)

    delta = month_total - prev_month_total

    lang = data.get("lang", "ru")
    month_txt = _format_month(month, lang)
    prev_month_txt = _format_month(prev_month, lang)
    msg = (
        f"{_i18n_t(lang, 'TX_INC_SUCCESS')}\n\n"
        f"{_i18n_t(lang, 'TX_CAT')}: {escape(cat_label)}\n"
        f"{_i18n_t(lang, 'TX_INC_CONFIRM_AMOUNT').format(amount=fmt_money(int(data['amount'])))}\n"
        f"{_i18n_t(lang, 'TX_EXP_CONFIRM_ACCOUNT').format(account=escape(str(data['account_name'])))}\n"
        f"{_i18n_t(lang, 'TX_ACC')}: <b>{bal_after_txt}</b>\n\n"
        f"{_i18n_t(lang, 'TX_INC_MONTH_TOTAL').format(month=escape(month_txt), total=fmt_money(month_total))}\n"
        f"{_i18n_t(lang, 'TX_INC_MONTH_COUNT').format(month=escape(month_txt), count=month_count)}\n"
        f"{_i18n_t(lang, 'TX_INC_CAT_MONTH_TOTAL').format(month=escape(month_txt), total=fmt_money(cat_month_total))}\n"
        f"{_i18n_t(lang, 'TX_INC_MONTH_MAX').format(total=fmt_money(month_max))}\n"
    )

    if prev_month_total > 0:
        if delta > 0:
            msg += _i18n_t(lang, "TX_INC_MONTH_GROWTH").format(month=escape(prev_month_txt), delta=fmt_money(delta)) + "\n"
        elif delta < 0:
            msg += _i18n_t(lang, "TX_INC_MONTH_DECLINE").format(month=escape(prev_month_txt), delta=fmt_money(abs(delta))) + "\n"
        else:
            msg += _i18n_t(lang, "TX_INC_MONTH_EQUAL").format(month=escape(prev_month_txt)) + "\n"
    else:
        msg += _i18n_t(lang, "TX_INC_MONTH_NO_DATA").format(month=escape(prev_month_txt)) + "\n"

    msg += f"\n<i>ID: {tx_id}</i>"

    if data.get("note"):
        msg += f"\n{_i18n_t(lang, 'TX_NOTE')}: <i>{escape(str(data['note']))}</i>"

    await _flow_finish(ctx, state, msg, db)

# =========================================================
# Transfer screens
# =========================================================

async def _tr_render_amount(target: Message | CallbackQuery, state: FSMContext):
    lang = (await state.get_data()).get("lang", "ru")
    await _flow_render(target, state, _i18n_t(lang, "TX_TR_STEP_1"), reply_markup=cancel_kb(lang))


async def _tr_render_from(target: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    accs = await list_accounts(db, target.from_user.id)
    text = (
        f"{_tr_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_TR_STEP_2')}"
    )
    await _flow_render(target, state, text, reply_markup=accounts_kb(accs, "trfrom", lang))


async def _tr_render_to(target: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    accs = await list_accounts(db, target.from_user.id)
    text = (
        f"{_tr_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_TR_STEP_3')}"
    )
    await _flow_render(target, state, text, reply_markup=accounts_kb(accs, "trto", lang))


async def _tr_render_need_note(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    text = (
        f"{_tr_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_TR_STEP_4_ASK')}"
    )
    await _flow_render(target, state, text, reply_markup=yes_no_kb("trnote", lang))


async def _tr_render_note_input(target: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    max_len = await _note_max(db, target.from_user.id)
    text = (
        f"{_tr_summary_lines(data, lang)}\n\n"
        f"{_i18n_t(lang, 'TX_TR_STEP_4_INPUT').format(max=max_len)}"
    )
    await _flow_render(target, state, text, reply_markup=cancel_kb(lang))


async def _tr_render_confirm(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")

    from_before = int(data["from_before"])
    from_after = from_before - int(data["amount"])
    await state.update_data(from_after=from_after)

    data = await state.get_data()

    lines = [
        f"{_i18n_t(lang, 'TX_TR_CONFIRM_HEAD')}",
        "",
        _i18n_t(lang, "TX_TR_CONFIRM_FROM").format(account=escape(str(data['from_name']))),
        _i18n_t(lang, "TX_TR_CONFIRM_TO").format(account=escape(str(data['to_name']))),
        _i18n_t(lang, "TX_TR_CONFIRM_SUM").format(amount=fmt_money(int(data['amount']))),
        _i18n_t(lang, "TX_TR_CONFIRM_BALANCE").format(before=fmt_money(int(from_before)), after=fmt_money(int(from_after))),
    ]

    if data.get("note"):
        lines.append(f"{_i18n_t(lang, 'TX_NOTE')}: <i>{escape(str(data['note']))}</i>")

    if from_after < 0:
        lines += ["", _i18n_t(lang, "TX_TR_CONFIRM_MINUS")]

    lines += ["", f"{_i18n_t(lang, 'TX_TR_STEP_5')}", f"{_i18n_t(lang, 'TX_TR_CONFIRM_PROCEED')}"]

    await _flow_render(target, state, "\n".join(lines), reply_markup=_tr_confirm_kb(lang))


# =========================================================
# Transfer handlers
# =========================================================

@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_TRANSFER"))
async def tr_start(m: Message, state: FSMContext, db):
    if not await can_use_feature(db, m.from_user.id, FEATURE_TRANSFER):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await _clear_flow_message(m.bot, m.chat.id, state)
    await state.clear()
    lang = await get_lang(db, m.from_user.id)
    await state.update_data(lang=lang)
    await state.set_state(TransferFlow.amount)
    await _tr_render_amount(m, state)


@router.message(TransferFlow.amount, F.text)
async def tr_amount(m: Message, state: FSMContext, db):
    if _is_cancel_text(m.text):
        return await cancel_to_main_menu(m, state, db)

    amt = await parse_money_for_user(db, m.from_user.id, m.text)
    if amt is None:
        lang = await get_lang(db, m.from_user.id)
        return await m.answer(_i18n_t(lang, "AMOUNT_INVALID"), reply_markup=cancel_kb(lang))

    await state.update_data(amount=amt)
    await state.set_state(TransferFlow.from_account)


    await _tr_render_from(m, state, db)


@router.callback_query(TransferFlow.from_account, F.data.startswith("trfrom:"))
async def tr_from(c: CallbackQuery, state: FSMContext, db):
    from_id = int(c.data.split(":")[1])
    acc = await _validate_account(db, c.from_user.id, from_id)

    if not acc:
        await c.answer("Account not found" if (await get_lang(db, c.from_user.id))=="en" else ("Шот табылмады" if (await get_lang(db, c.from_user.id))=="kk" else "Счёт не найден"), show_alert=True)
        return

    await state.update_data(
        from_account=from_id,
        from_name=acc[1],
        from_before=acc[2],
    )
    await state.set_state(TransferFlow.to_account)

    await _tr_render_to(c, state, db)
    await c.answer()


@router.callback_query(TransferFlow.to_account, F.data.startswith("trto:"))
async def tr_to(c: CallbackQuery, state: FSMContext, db):
    to_id = int(c.data.split(":")[1])
    data = await state.get_data()

    if to_id == int(data["from_account"]):
        await c.answer("Нужны разные счета", show_alert=True)
        return

    acc = await _validate_account(db, c.from_user.id, to_id)
    if not acc:
        await c.answer("Account not found" if (await get_lang(db, c.from_user.id))=="en" else ("Шот табылмады" if (await get_lang(db, c.from_user.id))=="kk" else "Счёт не найден"), show_alert=True)
        return

    await state.update_data(
        to_account=to_id,
        to_name=acc[1],
        to_before=acc[2],
    )
    await state.set_state(TransferFlow.need_note)

    await _tr_render_need_note(c, state)
    await c.answer()


@router.callback_query(TransferFlow.need_note, F.data.startswith("trnote:"))
async def tr_need_note(c: CallbackQuery, state: FSMContext, db):
    ans = c.data.split(":")[1]

    if ans == "yes":
        await state.set_state(TransferFlow.note)
        await _tr_render_note_input(c, state, db)
    else:
        await state.update_data(note=None)
        await state.set_state(TransferFlow.confirm)
        await _tr_render_confirm(c, state)

    await c.answer()


@router.message(TransferFlow.note, F.text)
async def tr_note(m: Message, state: FSMContext, db):
    if _is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return

    max_len = await _note_max(db, m.from_user.id)
    note = clean_note(m.text, max_len)
    if not note:
        return await m.answer(f"Комментарий 1–{max_len} символов.")

    await state.update_data(note=note)
    await state.set_state(TransferFlow.confirm)


    await _tr_render_confirm(m, state)


@router.callback_query(TransferFlow.confirm, F.data.startswith("trcfm:"))
async def tr_confirm(c: CallbackQuery, state: FSMContext, db):
    action = c.data.split(":")[1]

    if action == "cancel":
        lang = (await state.get_data()).get("lang", "ru")
        await _flow_finish(c, state, _i18n_t(lang, "CANCELLED").split(".")[0] + ".", db)
        return

    if action == "from":
        await state.set_state(TransferFlow.from_account)
        await _tr_render_from(c, state, db)
        await c.answer()
        return

    if action == "to":
        await state.set_state(TransferFlow.to_account)
        await _tr_render_to(c, state, db)
        await c.answer()
        return

    if action == "note":
        await state.set_state(TransferFlow.note)
        await _tr_render_note_input(c, state, db)
        await c.answer()
        return

    if action == "save":
        await neutralize_keyboard(c)
        data = await state.get_data()
        from_after = data.get("from_after")

        if isinstance(from_after, int) and from_after < 0:
            lang = data.get("lang", "ru")
            text = _i18n_t(lang, "TX_TR_OD_TITLE").format(
                account=escape(str(data['from_name'])),
                before=fmt_money(int(data['from_before'])),
                after=fmt_money(int(data['from_after']))
            )
            await state.set_state(TransferFlow.confirm_overdraft)
            await _flow_render(
                c,
                state,
                text,
                reply_markup=_overdraft_kb("trod", yes_text=_i18n_t(lang, "TX_EXP_OD_YES"), no_text=_i18n_t(lang, "TX_EXP_OD_NO")),
            )
            await c.answer()
            return

        await _tr_save(c, state, db)
        return


@router.callback_query(TransferFlow.confirm_overdraft, F.data.startswith("trod:"))
async def tr_od(c: CallbackQuery, state: FSMContext, db):
    ans = c.data.split(":")[1]

    if ans == "no":
        await state.set_state(TransferFlow.confirm)
        await _tr_render_confirm(c, state)
        await c.answer()
        return

    await neutralize_keyboard(c)
    await _tr_save(c, state, db)


async def _tr_save(ctx: Message | CallbackQuery, state: FSMContext, db):
    data = await state.get_data()

    tx1, tx2 = await add_transfer(
        db,
        ctx.from_user.id,
        int(data["amount"]),
        int(data["from_account"]),
        int(data["to_account"]),
        data.get("note"),
    )

    from_acc = await get_account(db, ctx.from_user.id, int(data["from_account"]))
    to_acc = await get_account(db, ctx.from_user.id, int(data["to_account"]))

    from_balance = from_acc[2] if from_acc else None
    to_balance = to_acc[2] if to_acc else None

    from_balance_txt = fmt_money(int(from_balance)) if isinstance(from_balance, int) else "—"
    to_balance_txt = fmt_money(int(to_balance)) if isinstance(to_balance, int) else "—"

    lang = data.get("lang", "ru")
    msg = (
        f"{_i18n_t(lang, 'TX_TR_SUCCESS')}\n\n"
        f"{_i18n_t(lang, 'TX_FROM')}: <b>{escape(str(data['from_name']))}</b>\n"
        f"{_i18n_t(lang, 'TX_TO')}: <b>{escape(str(data['to_name']))}</b>\n"
        f"{_i18n_t(lang, 'TX_SUM')}: <b>{fmt_money(int(data['amount']))}</b>\n\n"
        f"📊 {escape(str(data['from_name']))}: <b>{from_balance_txt}</b>\n"
        f"📊 {escape(str(data['to_name']))}: <b>{to_balance_txt}</b>\n"
        f"\n<i>ID: {tx1}/{tx2}</i>"
    )

    if data.get("note"):
        msg += f"\n{_i18n_t(lang, 'TX_NOTE')}: <i>{escape(str(data['note']))}</i>"

    await _flow_finish(ctx, state, msg, db)


# ---------------------------------------------------------------------------
# FSM fallback handlers: catch non-text input while we're expecting an amount.
# Without these, sending a sticker/photo/voice in *.amount state silently
# leaves the user stuck — see audit 1.6.
# ---------------------------------------------------------------------------
@router.message(ExpenseFlow.amount, ~F.text)
@router.message(IncomeFlow.amount, ~F.text)
@router.message(TransferFlow.amount, ~F.text)
async def _amount_non_text_fallback(m: Message, state: FSMContext, db):
    lang = await get_lang(db, m.from_user.id)
    await m.answer(_i18n_t(lang, "ENTER_AMOUNT_HINT"))