
from __future__ import annotations

import aiosqlite
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from app.db.repositories.accounts_repo import list_accounts
from app.db.repositories.debts_repo import (
    add_debt,
    apply_debt_payment,
    close_debt,
    count_active_debts,
    debts_summary,
    get_debt,
    list_active_debts,
)
from app.domain.services.accounting_service import add_expense, add_income
from app.fsm.debt_states import DebtAdd, DebtPay
from app.ui.formatters import fmt_money
from app.ui.keyboards import cancel_kb, debts_menu_kb, main_menu
from app.handlers.common import cancel_to_main_menu, is_cancel_text

router = Router()

DATE_FMT = "%Y-%m-%d"


def _is_cancel(text: str | None) -> bool:
    return is_cancel_text(text)


def _today() -> date:
    return date.today()


def _date_human(ymd: str | None) -> str:
    if not ymd:
        return "—"
    try:
        return datetime.strptime(ymd, DATE_FMT).strftime("%d.%m.%Y")
    except Exception:
        return ymd

def _status_label(status: str) -> str:
    return {
        "active": "🟢 Активен",
        "due_today": "🟡 Платёж сегодня",
        "overdue": "🔴 Просрочен",
    }.get(status, "🟢 Активен")

def _parse_money(text: str | None) -> int | None:
    raw = (text or "").strip().replace(" ", "")
    if not raw:
        return None
    if raw.startswith("+"):
        raw = raw[1:]
    if not raw.isdigit():
        return None
    val = int(raw)
    if val < 0:
        return None
    return val


def _parse_friendly_date(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None

    for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime(DATE_FMT)
        except Exception:
            pass
    return None


def _normalize_row(row) -> dict:
    if isinstance(row, dict):
        debt = dict(row)
    elif hasattr(row, "keys"):
        debt = {k: row[k] for k in row.keys()}
    else:
        debt = {
            "id": row[0],
            "title": row[1],
            "payment_amount": row[2],
            "next_payment_date": row[3],
            "remaining_amount": row[4],
            "dtype": row[5],
            "direction": row[6],
            "is_active": row[7] if len(row) > 7 else 1,
            "status": row[8] if len(row) > 8 else "active",
        }

    debt["status"] = debt.get("status", "active")
    return debt


def _direction_label(direction: str) -> str:
    return "📤 Я должен" if direction == "out" else "📥 Мне должны"


def _dtype_label(dtype: str) -> str:
    return "🏦 Кредит / банк" if dtype == "bank" else "👤 Частный долг"


def _pay_label(direction: str, dtype: str) -> str:
    if direction == "out" and dtype == "bank":
        return "Платёж в месяц"
    if direction == "out":
        return "Обычно плачу"
    return "Обычно возвращают"


def _due_label(direction: str, dtype: str) -> str:
    if direction == "out" and dtype == "bank":
        return "Следующий платёж"
    if direction == "out":
        return "Напомнить"
    return "Ожидаю до"


def _debt_card_text(debt: dict) -> str:
    status_text = _status_label(debt.get("status", "active"))

    return (
        f"<b>{debt['title']}</b>\n"
        f"{_direction_label(debt['direction'])} • {_dtype_label(debt['dtype'])}\n"
        f"Статус: <b>{status_text}</b>\n\n"
        f"Остаток: <b>{fmt_money(int(debt.get('remaining_amount') or 0))}</b>\n"
        f"{_pay_label(debt['direction'], debt['dtype'])}: <b>{fmt_money(int(debt.get('payment_amount') or 0))}</b>\n"
        f"{_due_label(debt['direction'], debt['dtype'])}: <b>{_date_human(debt.get('next_payment_date'))}</b>"
    )


def _menu_summary_text(summary_row) -> str:
    out_sum = int(summary_row["out_sum"] or 0)
    in_sum = int(summary_row["in_sum"] or 0)
    out_count = int(summary_row["out_count"] or 0)
    in_count = int(summary_row["in_count"] or 0)
    return (
        "💳 <b>Кредиты и долги</b>\n\n"
        f"📤 Я должен: <b>{out_count}</b> записей • <b>{fmt_money(out_sum)}</b>\n"
        f"📥 Мне должны: <b>{in_count}</b> записей • <b>{fmt_money(in_sum)}</b>\n\n"
        "Открой нужный раздел."
    )


def _debt_list_kb(rows: list, direction: str):
    kb = InlineKeyboardBuilder()
    for row in rows:
        debt = _normalize_row(row)
        rem = fmt_money(int(debt.get("remaining_amount") or 0))
        title = debt["title"]
        status = debt.get("status")

        prefix = ""
        if status == "overdue":
            prefix = "🔴 "
        elif status == "due_today":
            prefix = "🟡 "

        label = f"{prefix}{title} · {rem}"
        if len(label) > 46:
            label = label[:43] + "..."
        kb.button(text=label, callback_data=f"debt:open:{debt['id']}")
    kb.button(text="➕ Добавить", callback_data=f"debt:add:{direction}")
    kb.button(text="⬅️ Назад", callback_data="debt:menu")
    kb.adjust(1)
    return kb.as_markup()


def _debt_detail_kb(debt_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отметить платёж", callback_data=f"debt:pay:{debt_id}")
    kb.button(text="✔️ Закрыть запись", callback_data=f"debt:close:{debt_id}")
    kb.button(text="⬅️ К списку", callback_data="debt:back:list")
    kb.button(text="🏠 В раздел долгов", callback_data="debt:menu")
    kb.adjust(1)
    return kb.as_markup()


def _direction_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Я должен", callback_data="debt:adddir:out")
    kb.button(text="📥 Мне должны", callback_data="debt:adddir:in")
    kb.adjust(1)
    return kb.as_markup()


def _type_kb(direction: str):
    kb = InlineKeyboardBuilder()
    if direction == "out":
        kb.button(text="🏦 Кредит / банк", callback_data="debt:addtype:bank")
        kb.button(text="👤 Частный долг", callback_data="debt:addtype:private")
        kb.adjust(1)
    else:
        kb.button(text="👤 Частный долг", callback_data="debt:addtype:private")
        kb.adjust(1)
    return kb.as_markup()


def _due_date_kb(direction: str, dtype: str):
    today = _today()
    kb = InlineKeyboardBuilder()
    if direction == "out" and dtype == "bank":
        kb.button(text="Сегодня", callback_data=f"debt:due:{today.strftime(DATE_FMT)}")
        kb.button(text="Завтра", callback_data=f"debt:due:{(today + timedelta(days=1)).strftime(DATE_FMT)}")
        kb.button(text="+ 7 дней", callback_data=f"debt:due:{(today + timedelta(days=7)).strftime(DATE_FMT)}")
        kb.button(text="+ 1 месяц", callback_data=f"debt:due:{(today + relativedelta(months=1)).strftime(DATE_FMT)}")
        kb.button(text="📅 Ввести дату", callback_data="debt:due:custom")
        kb.adjust(2, 2, 1)
    else:
        kb.button(text="Сегодня", callback_data=f"debt:due:{today.strftime(DATE_FMT)}")
        kb.button(text="Завтра", callback_data=f"debt:due:{(today + timedelta(days=1)).strftime(DATE_FMT)}")
        kb.button(text="+ 7 дней", callback_data=f"debt:due:{(today + timedelta(days=7)).strftime(DATE_FMT)}")
        kb.button(text="Без даты", callback_data="debt:due:none")
        kb.button(text="📅 Ввести дату", callback_data="debt:due:custom")
        kb.adjust(2, 2, 1)
    return kb.as_markup()


def _confirm_add_text(data: dict) -> str:
    direction = data["direction"]
    dtype = data["dtype"]
    title = data["title"]
    rem = int(data["remaining_amount"])
    pay = int(data["payment_amount"])
    next_dt = data.get("next_payment_date")
    return (
        "Проверь запись:\n\n"
        f"Название: <b>{title}</b>\n"
        f"Раздел: <b>{_direction_label(direction)}</b>\n"
        f"Тип: <b>{_dtype_label(dtype)}</b>\n"
        f"Остаток: <b>{fmt_money(rem)}</b>\n"
        f"{_pay_label(direction, dtype)}: <b>{fmt_money(pay)}</b>\n"
        f"{_due_label(direction, dtype)}: <b>{_date_human(next_dt)}</b>"
    )


def _confirm_add_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Сохранить", callback_data="debt:add:save")
    kb.button(text="❌ Отмена", callback_data="debt:menu")
    kb.adjust(1)
    return kb.as_markup()


def _pay_amount_kb(debt: dict):
    scheduled = int(debt.get("payment_amount") or 0)
    remaining = int(debt.get("remaining_amount") or 0)
    kb = InlineKeyboardBuilder()
    if scheduled > 0:
        kb.button(text=f"{fmt_money(scheduled)}", callback_data=f"debt:paysum:{scheduled}")
    if remaining > 0 and remaining != scheduled:
        kb.button(text=f"Закрыть полностью · {fmt_money(remaining)}", callback_data=f"debt:paysum:{remaining}")
    kb.button(text="✍️ Ввести сумму", callback_data="debt:paysum:custom")
    kb.button(text="⬅️ Назад", callback_data=f"debt:open:{debt['id']}")
    kb.adjust(1)
    return kb.as_markup()


def _accounts_kb(accounts, debt_id: int, amount: int):
    kb = InlineKeyboardBuilder()
    for acc in accounts:
        acc_id, name, balance, _arch = acc
        kb.button(text=f"{name} · {fmt_money(int(balance or 0))}", callback_data=f"debt:acc:{debt_id}:{amount}:{acc_id}")
    kb.button(text="⬅️ Назад", callback_data=f"debt:pay:{debt_id}")
    kb.adjust(1)
    return kb.as_markup()


def _close_kb(debt_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, закрыть", callback_data=f"debt:close:yes:{debt_id}")
    kb.button(text="⬅️ Нет", callback_data=f"debt:open:{debt_id}")
    kb.adjust(1)
    return kb.as_markup()

async def _clear_inline_by_msg(message: Message | None):
    if not message:
        return
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    except Exception:
        pass


async def _clear_last_debt_screen(bot, chat_id: int, state: FSMContext):
    data = await state.get_data()
    msg_id = data.get("debt_screen_msg_id")
    if not msg_id:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=None,
        )
    except TelegramBadRequest:
        pass
    except Exception:
        pass


async def _remember_debt_screen(state: FSMContext, msg: Message):
    await state.update_data(debt_screen_msg_id=msg.message_id)


async def _send_debt_screen(
    m: Message,
    state: FSMContext,
    text: str,
    reply_markup,
    parse_mode: str = "HTML",
):
    await _clear_last_debt_screen(m.bot, m.chat.id, state)
    sent = await m.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    await _remember_debt_screen(state, sent)
    return sent


async def _edit_debt_screen(
    c: CallbackQuery,
    state: FSMContext,
    text: str,
    reply_markup,
    parse_mode: str = "HTML",
):
    # текущее сообщение становится единственным активным экраном
    try:
        await c.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest:
        sent = await c.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        await _remember_debt_screen(state, sent)
        return sent

    await _remember_debt_screen(state, c.message)
    return c.message


async def _safe_edit(target: CallbackQuery, text: str, reply_markup=None):
    try:
        await target.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        await target.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")


async def _open_detail(c: CallbackQuery, db: aiosqlite.Connection, debt_id: int):
    debt_raw = await get_debt(db, c.from_user.id, debt_id)
    if not debt_raw:
        await c.answer("Запись не найдена.", show_alert=True)
        return
    debt = _normalize_row(debt_raw)
    await _safe_edit(c, _debt_card_text(debt), _debt_detail_kb(debt_id))
    await c.answer()


async def _ensure_category(
    db: aiosqlite.Connection,
    user_id: int,
    *,
    kind: str,
    name: str,
    emoji: str,
) -> int:
    cur = await db.execute(
        "SELECT id FROM categories WHERE user_id = ? AND kind = ? AND name = ?",
        (user_id, kind, name),
    )
    row = await cur.fetchone()
    if row:
        return int(row["id"] if hasattr(row, "keys") else row[0])

    cur = await db.execute(
        """
        INSERT INTO categories (
            user_id, name, emoji, kind, is_archived, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 0, datetime('now'), datetime('now'))
        """,
        (user_id, name, emoji, kind),
    )
    await db.commit()
    return int(cur.lastrowid)


async def _get_operation_category_id(
    db: aiosqlite.Connection,
    *,
    user_id: int,
    direction: str,
    dtype: str,
) -> int:
    if direction == "out":
        if dtype == "bank":
            return await _ensure_category(db, user_id, kind="expense", name="Платёж по кредиту", emoji="💳")
        return await _ensure_category(db, user_id, kind="expense", name="Возврат долга", emoji="📤")
    return await _ensure_category(db, user_id, kind="income", name="Мне вернули долг", emoji="📥")


def _next_date_after_payment(debt: dict) -> str | None:
    current = debt.get("next_payment_date")
    if not current:
        return None
    if debt["direction"] == "out" and debt["dtype"] == "bank":
        try:
            return (datetime.strptime(current, DATE_FMT) + relativedelta(months=1)).strftime(DATE_FMT)
        except Exception:
            return current
    return current


@router.message(F.text.in_({"💳 Кредиты и долги", "💳 Долги"}))
async def debts_entry(m: Message, db: aiosqlite.Connection, state: FSMContext):
    await state.clear()
    summary = await debts_summary(db, m.from_user.id)

    await m.answer(
        "🤝 <b>Кредиты и долги</b>",
        reply_markup=cancel_kb(),
        parse_mode="HTML",
    )

    await _send_debt_screen(
        m,
        state,
        _menu_summary_text(summary),
        debts_menu_kb(),
    )

@router.callback_query(F.data == "debt:menu")
async def debts_menu(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    summary = await debts_summary(db, c.from_user.id)
    await _edit_debt_screen(c, state, _menu_summary_text(summary), debts_menu_kb())
    await c.answer()

@router.callback_query(F.data == "debt:settings")
async def debts_settings_stub(c: CallbackQuery):
    await c.answer("Сначала доводим ядро долгов. Напоминания подключим следующим шагом.", show_alert=True)


@router.callback_query(F.data == "debt:add")
async def debt_add_start(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(DebtAdd.direction)
    await _safe_edit(c, "Что создаём?", _direction_kb())
    await c.answer()


@router.callback_query(F.data.in_({"debt:add:out", "debt:add:in"}))
async def debt_add_prefill_direction(c: CallbackQuery, state: FSMContext):
    direction = c.data.split(":")[-1]
    await state.clear()
    await state.update_data(direction=direction)
    await state.set_state(DebtAdd.dtype)
    await _safe_edit(c, "Выбери тип записи.", _type_kb(direction))
    await c.answer()


@router.callback_query(F.data.startswith("debt:adddir:"))
async def debt_add_direction(c: CallbackQuery, state: FSMContext):
    direction = c.data.split(":")[-1]
    await state.update_data(direction=direction)
    await state.set_state(DebtAdd.dtype)
    await _safe_edit(c, "Выбери тип записи.", _type_kb(direction))
    await c.answer()


@router.callback_query(F.data.startswith("debt:addtype:"))
async def debt_add_type(c: CallbackQuery, state: FSMContext):
    dtype = c.data.split(":")[-1]
    data = await state.get_data()
    direction = data.get("direction")
    if not direction:
        await state.clear()
        await _safe_edit(c, "💳 <b>Кредиты и долги</b>", debts_menu_kb())
        await c.answer()
        return

    await state.update_data(dtype=dtype)
    await state.set_state(DebtAdd.title)

    example = "Kaspi кредит" if dtype == "bank" else ("Ильяс" if direction == "out" else "Руслан")
    text = (
        "Как назвать запись?\n\n"
        f"Пример: <b>{example}</b>"
    )
    await _safe_edit(c, text, None)
    await c.message.answer("✍️ Напиши название или нажми <b>Отмена</b>.", reply_markup=cancel_kb(), parse_mode="HTML")
    await c.answer()

@router.message(F.text == "❌ Отмена")
async def debts_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Ок.", reply_markup=main_menu(), parse_mode="HTML")

@router.message(DebtAdd.title, F.text)
async def debt_add_title(m: Message, state: FSMContext):
    if _is_cancel(m.text):
        await state.clear()
        return await m.answer("Ок.", reply_markup=debts_menu_kb())

    title = (m.text or "").strip()
    if len(title) < 2:
        return await m.answer("Название слишком короткое. Напиши нормально: банк, человек или кредитка.")

    await state.update_data(title=title)
    await state.set_state(DebtAdd.remaining)
    await m.answer("Сколько всего осталось? Напиши сумму цифрами.\nПример: <b>250000</b>", reply_markup=cancel_kb(), parse_mode="HTML")


@router.message(DebtAdd.remaining, F.text)
async def debt_add_remaining(m: Message, state: FSMContext):
    if _is_cancel(m.text):
        await state.clear()
        return await m.answer("Ок.", reply_markup=debts_menu_kb())

    remaining = _parse_money(m.text)
    if remaining is None or remaining <= 0:
        return await m.answer("Нужна сумма больше 0. Пример: <b>250000</b>", reply_markup=cancel_kb(), parse_mode="HTML")

    data = await state.get_data()
    direction = data["direction"]
    dtype = data["dtype"]

    await state.update_data(remaining_amount=remaining)
    await state.set_state(DebtAdd.payment)

    if direction == "out" and dtype == "bank":
        prompt = "Какой у тебя обычный ежемесячный платёж? Только цифры."
    elif direction == "out":
        prompt = "Сколько обычно отдаёшь за раз? Можно <b>0</b>, если без фиксированной суммы."
    else:
        prompt = "Сколько обычно тебе возвращают за раз? Можно <b>0</b>."
    await m.answer(prompt, reply_markup=cancel_kb(), parse_mode="HTML")


@router.message(DebtAdd.payment, F.text)
async def debt_add_payment(m: Message, state: FSMContext):
    if _is_cancel(m.text):
        await state.clear()
        return await m.answer("Ок.", reply_markup=debts_menu_kb())

    payment = _parse_money(m.text)
    if payment is None:
        return await m.answer("Нужны только цифры. Пример: <b>20000</b>", reply_markup=cancel_kb(), parse_mode="HTML")

    data = await state.get_data()
    direction = data["direction"]
    dtype = data["dtype"]

    if direction == "out" and dtype == "bank" and payment <= 0:
        return await m.answer("Для кредита платёж должен быть больше 0.", reply_markup=cancel_kb())

    await state.update_data(payment_amount=payment)
    await state.set_state(DebtAdd.confirm)
    await m.answer(
        "Когда напомнить о следующем платеже?",
        reply_markup=_due_date_kb(direction, dtype),
    )


@router.callback_query(F.data == "debt:due:none", DebtAdd.confirm)
async def debt_due_none(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data["direction"] == "out" and data["dtype"] == "bank":
        await c.answer("Для кредита дата нужна.", show_alert=True)
        return

    await state.update_data(next_payment_date=None)
    data = await state.get_data()
    await _safe_edit(c, _confirm_add_text(data), _confirm_add_kb())
    await c.answer()


@router.callback_query(F.data == "debt:due:custom", DebtAdd.confirm)
async def debt_due_custom(c: CallbackQuery, state: FSMContext):
    await state.set_state(DebtAdd.custom_due_date)
    await _safe_edit(
        c,
        "Введи дату удобно для человека: <b>25.03.2026</b>\nМожно и так: <code>2026-03-25</code>",
        None,
    )
    await c.message.answer("✍️ Напиши дату или нажми <b>Отмена</b>.", reply_markup=cancel_kb(), parse_mode="HTML")
    await c.answer()


@router.callback_query(F.data.startswith("debt:due:"), DebtAdd.confirm)
async def debt_due_quick(c: CallbackQuery, state: FSMContext):
    ymd = c.data.split(":", 2)[-1]
    if ymd in {"custom", "none"}:
        await c.answer()
        return
    await state.update_data(next_payment_date=ymd)
    data = await state.get_data()
    await _safe_edit(c, _confirm_add_text(data), _confirm_add_kb())
    await c.answer()


@router.message(DebtAdd.custom_due_date, F.text)
async def debt_due_custom_save(m: Message, state: FSMContext):
    if _is_cancel(m.text):
        await state.clear()
        return await m.answer("Ок.", reply_markup=debts_menu_kb())

    ymd = _parse_friendly_date(m.text)
    data = await state.get_data()
    if not ymd and data["direction"] == "out" and data["dtype"] == "bank":
        return await m.answer("Дата для кредита обязательна. Формат: <b>25.03.2026</b>", reply_markup=cancel_kb(), parse_mode="HTML")
    if not ymd and (m.text or "").strip() not in {"0", "-", "нет"}:
        return await m.answer("Не понял дату. Напиши так: <b>25.03.2026</b>", reply_markup=cancel_kb(), parse_mode="HTML")

    await state.update_data(next_payment_date=ymd)
    await state.set_state(DebtAdd.confirm)
    data = await state.get_data()
    await m.answer(_confirm_add_text(data), reply_markup=_confirm_add_kb(), parse_mode="HTML")


@router.callback_query(F.data == "debt:add:save")
async def debt_add_save(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    data = await state.get_data()
    if not data:
        await c.answer("Сессия устарела.", show_alert=True)
        return

    if data["direction"] == "out" and data["dtype"] == "bank" and not data.get("next_payment_date"):
        await c.answer("Для кредита нужна дата платежа.", show_alert=True)
        return

    await add_debt(
        db=db,
        user_id=c.from_user.id,
        direction=data["direction"],
        dtype=data["dtype"],
        title=data["title"],
        payment_amount=int(data["payment_amount"]),
        next_payment_date=data.get("next_payment_date"),
        remaining_amount=int(data["remaining_amount"]),
    )
    await state.clear()
    summary = await debts_summary(db, c.from_user.id)
    await _safe_edit(c, "✅ <b>Запись добавлена.</b>\n\n" + _menu_summary_text(summary), debts_menu_kb())
    await c.answer()


@router.callback_query(F.data.startswith("debt:list:"))
async def debts_list(c: CallbackQuery, db: aiosqlite.Connection):
    direction = c.data.split(":")[-1]
    rows = await list_active_debts(db, c.from_user.id, direction=direction)
    title = _direction_label(direction)

    if not rows:
        await _safe_edit(
            c,
            f"<b>{title}</b>\n\nПока пусто.",
            _debt_list_kb([], direction),
        )
        await c.answer()
        return

    text = f"<b>{title}</b>\n\nВыбери запись:"
    await _safe_edit(c, text, _debt_list_kb(rows, direction))
    await c.answer()


@router.callback_query(F.data == "debt:back:list")
async def debt_back_to_list(c: CallbackQuery, db: aiosqlite.Connection):
    debt_id = None
    try:
        # fallback: try parse from current text impossible, so just open general menu
        pass
    finally:
        summary = await debts_summary(db, c.from_user.id)
        await _safe_edit(c, _menu_summary_text(summary), debts_menu_kb())
        await c.answer()


@router.callback_query(F.data.startswith("debt:open:"))
async def debt_open(c: CallbackQuery, db: aiosqlite.Connection):
    debt_id = int(c.data.split(":")[-1])
    await _open_detail(c, db, debt_id)


@router.callback_query(F.data.startswith("debt:close:yes:"))
async def debt_close_yes(c: CallbackQuery, db: aiosqlite.Connection):
    debt_id = int(c.data.split(":")[-1])
    await close_debt(db, c.from_user.id, debt_id)
    summary = await debts_summary(db, c.from_user.id)
    await _safe_edit(c, "✅ <b>Запись закрыта.</b>\n\n" + _menu_summary_text(summary), debts_menu_kb())
    await c.answer()


@router.callback_query(F.data.startswith("debt:close:"))
async def debt_close_ask(c: CallbackQuery):
    parts = c.data.split(":")
    if len(parts) == 4 and parts[2] == "yes":
        return
    debt_id = int(parts[-1])
    await _safe_edit(
        c,
        "Закрыть запись вручную?\n\nИспользуй это только если долг реально закрыт и больше не нужно напоминать о нём.",
        _close_kb(debt_id),
    )
    await c.answer()


@router.callback_query(F.data.startswith("debt:pay:"))
async def debt_pay_start(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    debt_id = int(c.data.split(":")[-1])
    debt_raw = await get_debt(db, c.from_user.id, debt_id)
    if not debt_raw:
        await c.answer("Запись не найдена.", show_alert=True)
        return

    debt = _normalize_row(debt_raw)
    if not int(debt.get("is_active", 1)):
        await c.answer("Запись уже закрыта.", show_alert=True)
        return

    await state.clear()
    await state.update_data(pay_debt_id=debt_id)
    await state.set_state(DebtPay.amount)

    text = _debt_card_text(debt) + "\n\nСколько провести сейчас?"
    await _safe_edit(c, text, _pay_amount_kb(debt))
    await c.answer()


@router.callback_query(F.data.startswith("debt:paysum:"), DebtPay.amount)
async def debt_pay_amount_pick(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    amount_raw = c.data.split(":")[-1]
    if amount_raw == "custom":
        await _safe_edit(c, "Введи сумму платежа цифрами.\nПример: <b>25000</b>", None)
        await c.message.answer("✍️ Напиши сумму или нажми <b>Отмена</b>.", reply_markup=cancel_kb(), parse_mode="HTML")
        await c.answer()
        return

    amount = int(amount_raw)
    await state.update_data(pay_amount=amount)
    data = await state.get_data()
    debt_id = int(data["pay_debt_id"])

    accounts = await list_accounts(db, c.from_user.id)
    if not accounts:
        await state.clear()
        await c.message.answer("Сначала добавь счёт.", reply_markup=debts_menu_kb())
        await c.answer()
        return

    await c.message.answer("С какого счёта провести операцию?", reply_markup=_accounts_kb(accounts, debt_id, amount))
    await c.answer()


@router.message(DebtPay.amount, F.text)
async def debt_pay_amount_custom(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if _is_cancel(m.text):
        await state.clear()
        return await m.answer("Ок.", reply_markup=debts_menu_kb())

    amount = _parse_money(m.text)
    if amount is None or amount <= 0:
        return await m.answer("Нужна сумма больше 0. Пример: <b>25000</b>", reply_markup=cancel_kb(), parse_mode="HTML")

    data = await state.get_data()
    debt_id = int(data["pay_debt_id"])
    await state.update_data(pay_amount=amount)

    accounts = await list_accounts(db, m.from_user.id)
    if not accounts:
        await state.clear()
        return await m.answer("Сначала добавь счёт.", reply_markup=debts_menu_kb())

    await m.answer("С какого счёта провести операцию?", reply_markup=_accounts_kb(accounts, debt_id, amount))


@router.callback_query(F.data.startswith("debt:acc:"))
async def debt_pick_account(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    parts = c.data.split(":")
    if len(parts) != 5:
        await c.answer("Неверные данные.", show_alert=True)
        return

    debt_id = int(parts[2])
    amount = int(parts[3])
    account_id = int(parts[4])

    debt_raw = await get_debt(db, c.from_user.id, debt_id)
    if not debt_raw:
        await c.answer("Запись не найдена.", show_alert=True)
        return

    debt = _normalize_row(debt_raw)
    direction = debt["direction"]
    dtype = debt["dtype"]
    title = debt["title"]

    category_id = await _get_operation_category_id(
        db,
        user_id=c.from_user.id,
        direction=direction,
        dtype=dtype,
    )

    if direction == "out":
        note = f"Платёж по кредиту: {title}" if dtype == "bank" else f"Возврат долга: {title}"
        await add_expense(db, c.from_user.id, amount, account_id, category_id, note)
    else:
        note = f"Мне вернули долг: {title}"
        await add_income(db, c.from_user.id, amount, account_id, category_id, note)

    next_date = _next_date_after_payment(debt)
    await apply_debt_payment(db, c.from_user.id, debt_id, amount, next_date)
    await state.clear()

    updated_raw = await get_debt(db, c.from_user.id, debt_id)
    if not updated_raw:
        summary = await debts_summary(db, c.from_user.id)
        await _safe_edit(c, "✅ Готово.\n\n" + _menu_summary_text(summary), debts_menu_kb())
        await c.answer()
        return

    updated = _normalize_row(updated_raw)
    if int(updated.get("is_active", 1)) == 0:
        summary = await debts_summary(db, c.from_user.id)
        await _safe_edit(c, "✅ Платёж проведён. Запись закрыта.\n\n" + _menu_summary_text(summary), debts_menu_kb())
        await c.answer()
        return

    await _safe_edit(c, "✅ Платёж проведён.\n\n" + _debt_card_text(updated), _debt_detail_kb(debt_id))
    await c.answer()
