from __future__ import annotations

from datetime import datetime
from html import escape

import aiosqlite
from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repositories.settings_repo import get_lang
from app.db.repositories.tx_repo import delete_tx, list_last
from app.ui.formatters import fmt_money
from app.ui.i18n import text_matches_key
from app.ui.keyboards import cancel_kb
from app.handlers.common import build_main_menu_markup, neutralize_keyboard

router = Router()
PARSE_MODE = "HTML"
PAGE_SIZE = 10


def _L(lang: str) -> dict[str, str]:
    lang = (lang or "ru").lower()
    if lang == "en":
        return {
            "title": "🧾 <b>History</b>",
            "shown": "<i>Shown: {a}–{b}</i>",
            "empty": "<i>No transactions</i>",
            "empty2": "Nothing here yet.",
            "quick": "Quick commands:",
            "last10": "• <code>/last10</code> — last 10",
            "delcmd": "• <code>/del 123</code> — delete by ID",
            "income": "✅ Income",
            "expense": "💸 Expense",
            "transfer": "🔁 Between accounts",
            "operation": "🧾 Operation",
            "no_account": "No account",
            "delete": "🗑 Delete #{id} · {amount}",
            "newer": "⬅️ Newer",
            "older": "Older ➡️",
            "refresh": "🔄 Refresh",
            "yes_delete": "🗑 Yes, delete",
            "back": "⬅️ Back",
            "not_found": "Transaction not found.",
            "delete_error": "Delete error.",
            "deleted": "🗑 <b>Transaction deleted</b>\nID: <b>#{id}</b>",
            "deleted_alert": "Deleted",
            "confirm": "⚠️ <b>Delete confirmation</b>",
            "type": "Type",
            "amount": "Amount",
            "account": "Account",
            "date": "Date",
            "comment": "Comment",
            "delete_q": "Delete transaction?",
        }
    if lang == "kk":
        return {
            "title": "🧾 <b>Тарих</b>",
            "shown": "<i>Көрсетілді: {a}–{b}</i>",
            "empty": "<i>Операция жоқ</i>",
            "empty2": "Әзірге бос.",
            "quick": "Жылдам командалар:",
            "last10": "• <code>/last10</code> — соңғы 10",
            "delcmd": "• <code>/del 123</code> — ID бойынша жою",
            "income": "✅ Кіріс",
            "expense": "💸 Шығыс",
            "transfer": "🔁 Шоттар арасында",
            "operation": "🧾 Операция",
            "no_account": "Шотсыз",
            "delete": "🗑 Жою #{id} · {amount}",
            "newer": "⬅️ Жаңарақ",
            "older": "Ескірек ➡️",
            "refresh": "🔄 Жаңарту",
            "yes_delete": "🗑 Иә, жою",
            "back": "⬅️ Артқа",
            "not_found": "Операция табылмады.",
            "delete_error": "Жою қатесі.",
            "deleted": "🗑 <b>Операция жойылды</b>\nID: <b>#{id}</b>",
            "deleted_alert": "Жойылды",
            "confirm": "⚠️ <b>Жоюды растау</b>",
            "type": "Түрі",
            "amount": "Сома",
            "account": "Шот",
            "date": "Күні",
            "comment": "Пікір",
            "delete_q": "Операцияны жою керек пе?",
        }
    return {
        "title": "🧾 <b>История операций</b>",
        "shown": "<i>Показано: {a}–{b}</i>",
        "empty": "<i>Нет операций</i>",
        "empty2": "Пока пусто.",
        "quick": "Быстрые команды:",
        "last10": "• <code>/last10</code> — последние 10",
        "delcmd": "• <code>/del 123</code> — удалить по ID",
        "income": "✅ Доход",
        "expense": "💸 Расход",
        "transfer": "🔁 Между счетами",
        "operation": "🧾 Операция",
        "no_account": "Без счёта",
        "delete": "🗑 Удалить #{id} · {amount}",
        "newer": "⬅️ Новее",
        "older": "Старее ➡️",
        "refresh": "🔄 Обновить",
        "yes_delete": "🗑 Да, удалить",
        "back": "⬅️ Назад",
        "not_found": "Операция не найдена.",
        "delete_error": "Ошибка удаления.",
        "deleted": "🗑 <b>Операция удалена</b>\nID: <b>#{id}</b>",
        "deleted_alert": "Удалено",
        "confirm": "⚠️ <b>Подтверждение удаления</b>",
        "type": "Тип",
        "amount": "Сумма",
        "account": "Счёт",
        "date": "Дата",
        "comment": "Комментарий",
        "delete_q": "Удалить операцию?",
    }


def _tx_type_label(lang: str, ttype: str, amount: int) -> str:
    L = _L(lang)
    ttype = (ttype or "").strip().lower()
    if ttype == "income":
        return L["income"]
    if ttype == "expense":
        return L["expense"]
    if ttype in {"transfer", "transfer_out", "transfer_in"}:
        return L["transfer"]
    if amount > 0:
        return L["income"]
    if amount < 0:
        return L["expense"]
    return L["operation"]


def _tx_amount_text(amount: int) -> str:
    if amount > 0:
        return f"+{fmt_money(amount)}"
    if amount < 0:
        return f"-{fmt_money(abs(amount))}"
    return fmt_money(amount)


def _fmt_ts(ts: str | None) -> str:
    if not ts:
        return "—"
    raw = str(ts).strip()
    for candidate in (
        raw,
        raw.replace("Z", "+00:00"),
        raw.replace(" ", "T"),
        raw.replace(" ", "T").replace("Z", "+00:00"),
    ):
        try:
            return datetime.fromisoformat(candidate).strftime("%d.%m %H:%M")
        except Exception:
            pass
    return escape(raw[:16])


def _history_text(lang: str, rows: list[tuple], offset: int) -> str:
    L = _L(lang)
    lines = [L["title"], L["shown"].format(a=offset + 1, b=offset + len(rows)) if rows else L["empty"], ""]
    if not rows:
        lines.extend([L["empty2"], "", L["quick"], L["last10"], L["delcmd"]])
        return "\n".join(lines)

    for tx_id, ts, ttype, amount, acc_name, note in rows:
        amount = int(amount or 0)
        lines.append(f"<b>#{tx_id}</b> · {_tx_type_label(lang, str(ttype or ''), amount)}")
        lines.append(f"💰 <b>{_tx_amount_text(amount)}</b>")
        lines.append(f"💳 {escape(str(acc_name or L['no_account']))}")
        lines.append(f"🕒 {_fmt_ts(ts)}")
        note_txt = escape(str(note or "").strip())
        if note_txt:
            lines.append(f"📝 <i>{note_txt}</i>")
        lines.append("")
    return "\n".join(lines).rstrip()


def _history_kb(lang: str, rows: list[tuple], offset: int) -> InlineKeyboardMarkup:
    L = _L(lang)
    kb = InlineKeyboardBuilder()
    for tx_id, ts, ttype, amount, acc_name, note in rows:
        kb.button(text=L["delete"].format(id=tx_id, amount=_tx_amount_text(int(amount or 0))), callback_data=f"hist:askdel:{tx_id}:{offset}")

    nav = []
    if offset > 0:
        nav.append((L["newer"], f"hist:page:{max(0, offset - PAGE_SIZE)}"))
    if len(rows) == PAGE_SIZE:
        nav.append((L["older"], f"hist:page:{offset + PAGE_SIZE}"))
    for text, cb in nav:
        kb.button(text=text, callback_data=cb)
    kb.button(text=L["refresh"], callback_data=f"hist:page:{offset}")
    kb.button(text=L["back"], callback_data="rp:hub")
    kb.adjust(*([1] * len(rows)), len(nav) if nav else 1, 2)
    return kb.as_markup()


def _confirm_delete_kb(lang: str, tx_id: int, offset: int) -> InlineKeyboardMarkup:
    L = _L(lang)
    kb = InlineKeyboardBuilder()
    kb.button(text=L["yes_delete"], callback_data=f"hist:del:{tx_id}:{offset}")
    kb.button(text=L["back"], callback_data=f"hist:page:{offset}")
    kb.adjust(1, 1)
    return kb.as_markup()


async def _safe_edit_text(msg: Message, text: str, *, reply_markup=None) -> bool:
    try:
        await msg.edit_text(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        return True
    except TelegramBadRequest as e:
        return "message is not modified" in str(e).lower()
    except Exception:
        return False


async def _render_history(
    target: Message | CallbackQuery,
    db: aiosqlite.Connection,
    user_id: int,
    *,
    offset: int = 0,
    prefer_edit: bool = False,
    state: FSMContext | None = None,
    already_answered: bool = False,
):
    rows = await list_last(db, user_id, PAGE_SIZE + offset)
    rows = rows[offset: offset + PAGE_SIZE] if offset > 0 else rows[:PAGE_SIZE]
    lang = await get_lang(db, user_id)
    text = _history_text(lang, rows, offset)
    kb = _history_kb(lang, rows, offset)

    if isinstance(target, CallbackQuery):
        edited = await _safe_edit_text(target.message, text, reply_markup=kb) if prefer_edit else False
        if not edited:
            sent = await target.message.answer(text, reply_markup=kb, parse_mode=PARSE_MODE)
            if state is not None:
                await state.update_data(flow_message_id=sent.message_id, ui_scope="history")
        else:
            if state is not None:
                await state.update_data(flow_message_id=target.message.message_id, ui_scope="history")
        if not already_answered:
            try:
                await target.answer()
            except Exception:
                pass
        return

    sent = await target.answer(text, reply_markup=kb, parse_mode=PARSE_MODE)
    if state is not None:
        await state.update_data(flow_message_id=sent.message_id, ui_scope="history")


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_HISTORY"))
async def hist_entry(m: Message, db: aiosqlite.Connection, state: FSMContext):
    lang = await get_lang(db, m.from_user.id)
    await m.answer("🧾", reply_markup=cancel_kb(lang))
    await _render_history(m, db, m.from_user.id, offset=0, prefer_edit=False, state=state)


@router.message(Command("last10"))
async def last10_cmd(m: Message, db: aiosqlite.Connection, state: FSMContext):
    lang = await get_lang(db, m.from_user.id)
    await m.answer("🧾", reply_markup=cancel_kb(lang))
    await _render_history(m, db, m.from_user.id, offset=0, prefer_edit=False, state=state)


@router.message(F.text.regexp(r"^/del\s+\d+$"))
async def deltx(m: Message, db: aiosqlite.Connection):
    tx_id = int((m.text or "").split()[1])
    lang = await get_lang(db, m.from_user.id)
    L = _L(lang)
    try:
        ok, _status = await delete_tx(db, m.from_user.id, tx_id)
        if not ok:
            await db.rollback()
            return await m.answer(L["not_found"], reply_markup=await build_main_menu_markup(db, m.from_user.id, lang))
        await db.commit()
    except Exception:
        await db.rollback()
        return await m.answer(L["delete_error"], reply_markup=await build_main_menu_markup(db, m.from_user.id, lang))

    await m.answer(L["deleted"].format(id=tx_id), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode=PARSE_MODE)


@router.callback_query(F.data.startswith("hist:page:"))
async def hist_page(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    offset = int((c.data or "hist:page:0").split(":")[2])
    await _render_history(c, db, c.from_user.id, offset=offset, prefer_edit=True, state=state)


@router.callback_query(F.data.startswith("hist:askdel:"))
async def hist_ask_del(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    _, _, tx_id, offset = (c.data or "").split(":")
    tx_id = int(tx_id)
    offset = int(offset)
    rows = await list_last(db, c.from_user.id, PAGE_SIZE + offset)
    rows = rows[offset: offset + PAGE_SIZE] if offset > 0 else rows[:PAGE_SIZE]
    selected = next((row for row in rows if int(row[0]) == tx_id), None)
    lang = await get_lang(db, c.from_user.id)
    L = _L(lang)
    if not selected:
        await c.answer(L["not_found"], show_alert=True)
        return

    _tx_id, ts, ttype, amount, acc_name, note = selected
    amount = int(amount or 0)
    text = "\n".join([
        L["confirm"],
        "",
        f"ID: <b>#{tx_id}</b>",
        f"{L['type']}: {_tx_type_label(lang, str(ttype or ''), amount)}",
        f"{L['amount']}: <b>{_tx_amount_text(amount)}</b>",
        f"{L['account']}: {escape(str(acc_name or L['no_account']))}",
        f"{L['date']}: {_fmt_ts(ts)}",
        f"{L['comment']}: <i>{escape(str(note or '—'))}</i>",
        "",
        L["delete_q"],
    ])
    edited = await _safe_edit_text(c.message, text, reply_markup=_confirm_delete_kb(lang, tx_id, offset))
    if not edited:
        sent = await c.message.answer(text, reply_markup=_confirm_delete_kb(lang, tx_id, offset), parse_mode=PARSE_MODE)
        await state.update_data(flow_message_id=sent.message_id, ui_scope="history")
    else:
        await state.update_data(flow_message_id=c.message.message_id, ui_scope="history")
    await c.answer()


@router.callback_query(F.data.startswith("hist:del:"))
async def hist_del(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    _, _, tx_id, offset = (c.data or "").split(":")
    tx_id = int(tx_id)
    offset = int(offset)
    await neutralize_keyboard(c)
    lang = await get_lang(db, c.from_user.id)
    L = _L(lang)
    try:
        ok, _status = await delete_tx(db, c.from_user.id, tx_id)
        if not ok:
            await db.rollback()
            await c.answer(L["not_found"], show_alert=True)
            return
        await db.commit()
    except Exception:
        await db.rollback()
        await c.answer(L["delete_error"], show_alert=True)
        return

    await c.answer(L["deleted_alert"])
    rows = await list_last(db, c.from_user.id, PAGE_SIZE + offset)
    remain = rows[offset: offset + PAGE_SIZE]
    if offset > 0 and not remain:
        offset = max(0, offset - PAGE_SIZE)
    # Callback already answered above (deleted_alert) — don't answer twice.
    await _render_history(c, db, c.from_user.id, offset=offset, prefer_edit=True, state=state, already_answered=True)
