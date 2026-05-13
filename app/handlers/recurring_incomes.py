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
    create_recurring_income,
    list_recurring_incomes,
    get_recurring_income,
    archive_recurring_income,
    restore_recurring_income,
    mark_recurring_received,
    skip_recurring_income,
    mark_recurring_income_reminded,
)
from app.db.repositories.settings_repo import get_lang
from app.db.repositories.tx_repo import create_tx, apply_expense_income
from app.fsm.states import RecurringIncomeFlow
from app.handlers.common import cancel_to_main_menu, is_cancel_text, build_main_menu_markup
from app.ui.i18n import text_matches_key, t
from app.ui.keyboards import main_menu, cancel_kb, categories_kb, accounts_kb
from app.domain.services.ai_consultant_service import build_section_hint

router = Router()
PARSE_MODE = 'HTML'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fmt_money(value: int) -> str:
    s = str(abs(int(value)))
    parts = []
    while s:
        parts.append(s[-3:])
        s = s[:-3]
    out = ' '.join(reversed(parts)) if parts else '0'
    return f"{'-' if value < 0 else ''}{out} тг"


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
    kb.button(text='➕ Добавить' if lang == 'ru' else ('➕ Add' if lang == 'en' else '➕ Қосу'), callback_data='ri:add')
    kb.button(text='📋 Активные' if lang == 'ru' else ('📋 Active' if lang == 'en' else '📋 Белсенді'), callback_data='ri:list')
    kb.button(text='🗄 Архив' if lang == 'ru' else ('🗄 Archive' if lang == 'en' else '🗄 Архив'), callback_data='ri:archived')
    kb.button(text=t(lang, 'BTN_BACK'), callback_data='hub:planning')
    kb.adjust(2, 1, 1)
    return kb.as_markup()



def recurring_rows_kb(rows, archived: bool, lang: str = 'ru'):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    for row in rows:
        title = f"{row['title']} — {fmt_money(int(row['amount']))}"
        kb.button(text=title, callback_data=f"ri:item:{row['id']}")
    kb.button(text=t(lang, 'BTN_BACK'), callback_data='ri:menu')
    kb.adjust(1)
    return kb.as_markup()



def recurring_actions_kb(recurring_id: int, archived: bool, lang: str = 'ru', back_cb: str | None = None):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    if archived:
        kb.button(text='♻️ Восстановить' if lang == 'ru' else ('♻️ Restore' if lang == 'en' else '♻️ Қалпына келтіру'), callback_data=f'ri:restore:{recurring_id}')
    else:
        kb.button(text='✅ Отметить как получено' if lang == 'ru' else ('✅ Mark received' if lang == 'en' else '✅ Алынды деп белгілеу'), callback_data=f'ri:received:{recurring_id}')
        kb.button(text='🚫 Не получил' if lang == 'ru' else ("🚫 Didn't receive" if lang == 'en' else '🚫 Алынбады'), callback_data=f'ri:missed:{recurring_id}')
        kb.button(text='🗂 В архив' if lang == 'ru' else ('🗂 Archive' if lang == 'en' else '🗂 Архив'), callback_data=f'ri:archive:{recurring_id}')
    kb.button(text=t(lang, 'BTN_BACK'), callback_data=back_cb or ('ri:list' if not archived else 'ri:archived'))
    kb.adjust(1)
    return kb.as_markup()


def recurring_reminder_actions_kb(recurring_id: int, lang: str = 'ru'):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text='✅ Получено' if lang == 'ru' else ('✅ Received' if lang == 'en' else '✅ Алынды'), callback_data=f'ri:remindrecv:{recurring_id}')
    kb.button(text='🚫 Не получил' if lang == 'ru' else ("🚫 Didn't receive" if lang == 'en' else '🚫 Алынбады'), callback_data=f'ri:remindmissed:{recurring_id}')
    kb.button(text='🕒 Завтра' if lang == 'ru' else ('🕒 Tomorrow' if lang == 'en' else '🕒 Ертең'), callback_data=f'ri:remindsnooze:{recurring_id}')
    kb.button(text='🔗 Уже внёс вручную' if lang == 'ru' else ('🔗 Already added manually' if lang == 'en' else '🔗 Қолмен енгізіп қойдым'), callback_data=f'ri:remindmanual:{recurring_id}')
    kb.button(text='📂 Детали' if lang == 'ru' else ('📂 Details' if lang == 'en' else '📂 Толығырақ'), callback_data=f'ri:remdetail:{recurring_id}')
    kb.adjust(2, 2, 1)
    return kb.as_markup()



def recurring_confirm_kb(lang: str = 'ru'):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text='✅ Сохранить' if lang == 'ru' else ('✅ Save' if lang == 'en' else '✅ Сақтау'), callback_data='ri:save')
    kb.button(text='❌ Отмена' if lang == 'ru' else ('❌ Cancel' if lang == 'en' else '❌ Болдырмау'), callback_data='ri:menu')
    kb.adjust(1)
    return kb.as_markup()


async def _menu_text(db: aiosqlite.Connection, user_id: int, lang: str) -> str:
    await ensure_schema(db)
    active = await list_recurring_incomes(db, user_id, archived=False)
    archived = await list_recurring_incomes(db, user_id, archived=True)
    nearest = active[0] if active else None
    lines = [
        '♻️ <b>Постоянные доходы</b>' if lang == 'ru' else ('♻️ <b>Recurring incomes</b>' if lang == 'en' else '♻️ <b>Тұрақты кірістер</b>'),
        '',
        'Регулярные поступления для прогноза и напоминаний.' if lang == 'ru' else ('Recurring inflows for forecast and reminders.' if lang == 'en' else 'Болжам мен еске салуға арналған тұрақты түсімдер.'),
        f"Активных: <b>{len(active)}</b>" if lang == 'ru' else (f"Active: <b>{len(active)}</b>" if lang == 'en' else f"Белсенді: <b>{len(active)}</b>"),
    ]
    if archived:
        lines.append(f"В архиве: <b>{len(archived)}</b>" if lang == 'ru' else (f"Archived: <b>{len(archived)}</b>" if lang == 'en' else f"Архивте: <b>{len(archived)}</b>"))
    if nearest:
        lines.extend([
            '',
            'Ближайший:' if lang == 'ru' else ('Nearest:' if lang == 'en' else 'Жақын арада:'),
            f"• <b>{escape(str(nearest['title']))}</b> — {fmt_money(int(nearest['amount']))} — {nearest['next_run_date']}",
        ])
    hint = await build_section_hint(db, user_id, 'recurring_incomes', lang)
    return '\n'.join(lines) + hint


async def _show_menu(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, target.from_user.id)
    await _clear_recurring_flow_data(state)
    await state.set_state(None)
    await _render_screen(target, state, await _menu_text(db, target.from_user.id, lang), reply_markup=recurring_menu_kb(lang))


async def _ask_title(target: Message | CallbackQuery, state: FSMContext, lang: str):
    await state.set_state(RecurringIncomeFlow.title)
    text = (
        '➕ <b>Новый постоянный доход</b>\n\nВведи название дохода.\nНапример: <code>Зарплата</code>'
        if lang == 'ru' else
        ('➕ <b>New recurring income</b>\n\nEnter the income title.\nExample: <code>Salary</code>' if lang == 'en' else '➕ <b>Жаңа тұрақты кіріс</b>\n\nКіріс атауын енгізіңіз.\nМысалы: <code>Жалақы</code>')
    )
    await _enter_chat_mode(target, state, text, reply_markup=cancel_kb(lang))


async def _ask_amount(target: Message | CallbackQuery, state: FSMContext, lang: str, title: str):
    await state.set_state(RecurringIncomeFlow.amount)
    text = (
        f'➕ <b>{escape(title)}</b>\n\n💰 Введи сумму в тенге.\nПример: <code>350000</code>'
        if lang == 'ru' else
        (f'➕ <b>{escape(title)}</b>\n\n💰 Enter the amount in KZT.\nExample: <code>350000</code>' if lang == 'en' else f'➕ <b>{escape(title)}</b>\n\n💰 Соманы теңгемен енгізіңіз.\nМысалы: <code>350000</code>')
    )
    await _enter_chat_mode(target, state, text, reply_markup=cancel_kb(lang))


async def _ask_day(target: Message | CallbackQuery, state: FSMContext, lang: str, data: dict):
    await state.set_state(RecurringIncomeFlow.day)
    title = escape(str(data.get('ri_title') or '—'))
    amount = fmt_money(int(data.get('ri_amount') or 0))
    text = (
        f'📅 <b>День поступления</b>\n\n<b>{title}</b>\n💰 {amount}\n\nВведи число от <b>1</b> до <b>31</b>.'
        if lang == 'ru' else
        (f'📅 <b>Income day</b>\n\n<b>{title}</b>\n💰 {amount}\n\nEnter a day from <b>1</b> to <b>31</b>.' if lang == 'en' else f'📅 <b>Түсу күні</b>\n\n<b>{title}</b>\n💰 {amount}\n\n<b>1</b>-ден <b>31</b>-ге дейінгі күнді енгізіңіз.')
    )
    await _enter_chat_mode(target, state, text, reply_markup=cancel_kb(lang))


async def _ask_comment(target: Message | CallbackQuery, state: FSMContext, lang: str, data: dict):
    await state.set_state(RecurringIncomeFlow.comment)
    title = escape(str(data.get('ri_title') or '—'))
    amount = fmt_money(int(data.get('ri_amount') or 0))
    day = int(data.get('ri_day') or 0)
    text = (
        f'📝 <b>Комментарий</b>\n\n<b>{title}</b>\n💰 {amount}\n📅 {day} число\n\nДобавь комментарий для истории или отправь <code>-</code>.'
        if lang == 'ru' else
        (f'📝 <b>Comment</b>\n\n<b>{title}</b>\n💰 {amount}\n📅 day {day}\n\nAdd a note for history or send <code>-</code>.' if lang == 'en' else f'📝 <b>Пікір</b>\n\n<b>{title}</b>\n💰 {amount}\n📅 {day} күні\n\nТарих үшін пікір қосыңыз немесе <code>-</code> жіберіңіз.')
    )
    await _enter_chat_mode(target, state, text, reply_markup=cancel_kb(lang))


async def _show_confirm(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    data = await state.get_data()
    lang = await get_lang(db, target.from_user.id)

    cats = await list_categories(db, target.from_user.id, 'income')
    accs = await list_accounts(db, target.from_user.id)
    cat_name = '—'
    acc_name = '—'
    for row in cats:
        if int(row['id']) == int(data.get('ri_category_id') or 0):
            cat_name = escape(str(row['name']))
            break
    for row in accs:
        if int(row['id']) == int(data.get('ri_account_id') or 0):
            acc_name = escape(str(row['name']))
            break

    comment = data.get('ri_comment')
    text = (
        'Проверь данные 👇\n\n'
        f"Название: <b>{escape(str(data.get('ri_title') or '—'))}</b>\n"
        f"Сумма: <b>{fmt_money(int(data.get('ri_amount') or 0))}</b>\n"
        f"Категория: <b>{cat_name}</b>\n"
        f"Счёт: <b>{acc_name}</b>\n"
        f"День месяца: <b>{int(data.get('ri_day') or 0)}</b>\n"
        f"Комментарий: <b>{escape(str(comment)) if comment else '—'}</b>\n\n"
        'Сохраняем?'
        if lang == 'ru' else
        (
            'Check the details 👇\n\n'
            f"Title: <b>{escape(str(data.get('ri_title') or '—'))}</b>\n"
            f"Amount: <b>{fmt_money(int(data.get('ri_amount') or 0))}</b>\n"
            f"Category: <b>{cat_name}</b>\n"
            f"Account: <b>{acc_name}</b>\n"
            f"Day of month: <b>{int(data.get('ri_day') or 0)}</b>\n"
            f"Comment: <b>{escape(str(comment)) if comment else '—'}</b>\n\n"
            'Save it?'
            if lang == 'en' else
            'Деректерді тексеріңіз 👇\n\n'
            f"Атауы: <b>{escape(str(data.get('ri_title') or '—'))}</b>\n"
            f"Сома: <b>{fmt_money(int(data.get('ri_amount') or 0))}</b>\n"
            f"Санат: <b>{cat_name}</b>\n"
            f"Шот: <b>{acc_name}</b>\n"
            f"Ай күні: <b>{int(data.get('ri_day') or 0)}</b>\n"
            f"Пікір: <b>{escape(str(comment)) if comment else '—'}</b>\n\n"
            'Сақтаймыз ба?'
        )
    )
    await _render_screen(target, state, text, reply_markup=recurring_confirm_kb(lang))


from app.domain.services.access_service import FEATURE_RECURRING, can_use_feature
from app.handlers.common import cancel_to_main_menu, is_cancel_text, deny_feature_message

@router.message(lambda m: text_matches_key(getattr(m, 'text', None), 'BTN_RECURRING_INCOMES'))
async def recurring_entry(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, m.from_user.id, FEATURE_RECURRING):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await ensure_schema(db)
    await _show_menu(m, state, db)


@router.callback_query(F.data == 'ri:menu')
async def recurring_menu_cb(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    if not await can_use_feature(db, c.from_user.id, FEATURE_RECURRING):
        await deny_feature_message(c, db, c.from_user.id)
        return
    await _show_menu(c, state, db)
    await c.answer()



@router.callback_query(F.data == 'ri:list')
async def recurring_list(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    rows = await list_recurring_incomes(db, c.from_user.id, archived=False)
    text = '📋 <b>Активные постоянные доходы</b>' if lang == 'ru' else ('📋 <b>Active recurring incomes</b>' if lang == 'en' else '📋 <b>Белсенді тұрақты кірістер</b>')
    if not rows:
        text += '\n\n' + ('Пока пусто.' if lang == 'ru' else ('No items yet.' if lang == 'en' else 'Әзірге бос.'))
    await _render_screen(c, state, text, reply_markup=recurring_rows_kb(rows, archived=False, lang=lang))
    await c.answer()


@router.callback_query(F.data == 'ri:archived')
async def recurring_archived(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    rows = await list_recurring_incomes(db, c.from_user.id, archived=True)
    text = '🗄 <b>Архив постоянных доходов</b>' if lang == 'ru' else ('🗄 <b>Recurring income archive</b>' if lang == 'en' else '🗄 <b>Тұрақты кірістер архиві</b>')
    if not rows:
        text += '\n\n' + ('Архив пуст.' if lang == 'ru' else ('Archive is empty.' if lang == 'en' else 'Архив бос.'))
    await _render_screen(c, state, text, reply_markup=recurring_rows_kb(rows, archived=True, lang=lang))
    await c.answer()


@router.callback_query(F.data == 'ri:add')
async def recurring_add(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    await _clear_recurring_flow_data(state)
    await _ask_title(c, state, lang)
    await c.answer()


@router.message(RecurringIncomeFlow.title, F.text)
async def recurring_title(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    title = (m.text or '').strip()
    if len(title) < 2 or len(title) > 60:
        await m.answer('Название должно быть от 2 до 60 символов.')
        return
    await state.update_data(ri_title=title)
    await _ask_amount(m, state, await get_lang(db, m.from_user.id), title)


@router.message(RecurringIncomeFlow.amount, F.text)
async def recurring_amount(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    raw = (m.text or '').replace(' ', '').strip()
    if not raw.isdigit() or int(raw) <= 0:
        await m.answer('Нужна положительная сумма цифрами.')
        return
    await state.update_data(ri_amount=int(raw))
    cats = await list_categories(db, m.from_user.id, 'income')
    await state.set_state(RecurringIncomeFlow.category)
    lang = await get_lang(db, m.from_user.id)
    text = '🗂 <b>Выбери категорию дохода</b>' if lang == 'ru' else ('🗂 <b>Choose income category</b>' if lang == 'en' else '🗂 <b>Кіріс санатын таңдаңыз</b>')
    await _enter_chat_mode(m, state, text, reply_markup=categories_kb(cats, 'ri:cat', lang))


@router.callback_query(RecurringIncomeFlow.category, F.data.startswith('ri:cat:'))
async def recurring_category(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await state.update_data(ri_category_id=int(c.data.split(':')[-1]))
    accs = await list_accounts(db, c.from_user.id)
    await state.set_state(RecurringIncomeFlow.account)
    lang = await get_lang(db, c.from_user.id)
    await _edit_screen(c, state, '🏦 <b>Выбери счёт</b>' if lang == 'ru' else ('🏦 <b>Choose account</b>' if lang == 'en' else '🏦 <b>Шотты таңдаңыз</b>'), reply_markup=accounts_kb(accs, 'ri:acc', lang))
    await c.answer()


@router.callback_query(RecurringIncomeFlow.account, F.data.startswith('ri:acc:'))
async def recurring_account(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await state.update_data(ri_account_id=int(c.data.split(':')[-1]))
    data = await state.get_data()
    await _ask_day(c, state, await get_lang(db, c.from_user.id), data)
    await c.answer()


@router.message(RecurringIncomeFlow.day, F.text)
async def recurring_day(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    raw = (m.text or '').strip()
    if not raw.isdigit() or not (1 <= int(raw) <= 31):
        await m.answer('Нужно число от 1 до 31.')
        return
    await state.update_data(ri_day=int(raw))
    data = await state.get_data()
    await _ask_comment(m, state, await get_lang(db, m.from_user.id), data)


@router.message(RecurringIncomeFlow.comment, F.text)
async def recurring_comment(m: Message, state: FSMContext, db: aiosqlite.Connection):
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    comment = (m.text or '').strip()
    if comment == '-':
        comment = None
    await state.update_data(ri_comment=comment)
    await _show_confirm(m, state, db)


@router.callback_query(F.data == 'ri:save')
async def recurring_save(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    data = await state.get_data()
    try:
        await create_recurring_income(
            db,
            c.from_user.id,
            data['ri_title'],
            int(data['ri_amount']),
            int(data['ri_category_id']),
            int(data['ri_account_id']),
            int(data['ri_day']),
            data.get('ri_comment'),
            now_iso(),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    lang = await get_lang(db, c.from_user.id)
    try:
        await c.answer('Сохранено' if lang == 'ru' else ('Saved' if lang == 'en' else 'Сақталды'))
    except Exception:
        pass
    await _clear_last_screen(c, state, forget=True)
    await _clear_recurring_flow_data(state)
    await c.message.answer(
        '✅ Постоянный доход сохранён.' if lang == 'ru' else ('✅ Recurring income saved.' if lang == 'en' else '✅ Тұрақты кіріс сақталды.'),
        parse_mode=PARSE_MODE,
    )
    await cancel_to_main_menu(c, state, db)


@router.callback_query(F.data.startswith('ri:item:'))
async def recurring_item(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    row = await get_recurring_income(db, c.from_user.id, int(c.data.split(':')[-1]))
    if not row:
        await c.answer('Не найдено', show_alert=True)
        return
    lang = await get_lang(db, c.from_user.id)
    archived = bool(int(row['is_archived'] or 0))
    lines = [
        f"♻️ <b>{escape(str(row['title']))}</b>",
        '',
        f"💰 {fmt_money(int(row['amount']))}",
        f"🗂 {escape(str(row['category_name']))}",
        f"🏦 {escape(str(row['account_name']))}",
        f"📅 День месяца: <b>{int(row['day_of_month'])}</b>",
        f"⏭ Следующая дата: <b>{escape(str(row['next_run_date']))}</b>",
    ]
    if row['comment']:
        lines.append(f"📝 {escape(str(row['comment']))}")
    if row['last_received_at']:
        lines.append(f"✅ Последняя отметка: <b>{escape(str(row['last_received_at']))[:10]}</b>")
    await _render_screen(c, state, '\n'.join(lines), reply_markup=recurring_actions_kb(int(row['id']), archived, lang))
    await c.answer()




@router.callback_query(F.data.startswith('ri:remdetail:'))
async def recurring_reminder_detail(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    row = await get_recurring_income(db, c.from_user.id, int(c.data.split(':')[-1]))
    if not row:
        await c.answer('Не найдено', show_alert=True)
        return
    lang = await get_lang(db, c.from_user.id)
    archived = bool(int(row['is_archived'] or 0))
    lines = [
        f"♻️ <b>{escape(str(row['title']))}</b>",
        '',
        f"💰 {fmt_money(int(row['amount']))}",
        f"🗂 {escape(str(row['category_name']))}",
        f"🏦 {escape(str(row['account_name']))}",
        f"📅 День месяца: <b>{int(row['day_of_month'])}</b>",
        f"⏭ Следующая дата: <b>{escape(str(row['next_run_date']))}</b>",
    ]
    if row['comment']:
        lines.append(f"📝 {escape(str(row['comment']))}")
    if row['last_received_at']:
        lines.append(f"✅ Последняя отметка: <b>{escape(str(row['last_received_at']))[:10]}</b>")
    await _render_screen(c, state, "\n".join(lines), reply_markup=recurring_actions_kb(int(row['id']), archived, lang, back_cb=f"ri:remcard:{int(row['id'])}"))
    await c.answer()


@router.callback_query(F.data.startswith('ri:remcard:'))
async def recurring_reminder_card(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    row = await get_recurring_income(db, c.from_user.id, int(c.data.split(':')[-1]))
    if not row:
        await c.answer('Не найдено', show_alert=True)
        return
    lang = await get_lang(db, c.from_user.id)
    lines = [
        f"♻️ <b>{escape(str(row['title']))}</b>",
        '',
        ('Напоминание по постоянному доходу.' if lang == 'ru' else ('Recurring income reminder.' if lang == 'en' else 'Тұрақты кіріс туралы еске салу.')),
        f"💰 {fmt_money(int(row['amount']))}",
        f"🏦 {escape(str(row['account_name']))}",
        f"🗂 {escape(str(row['category_name']))}",
        f"📅 {escape(str(row['next_run_date']))}",
    ]
    if row['comment']:
        lines.append(f"📝 {escape(str(row['comment']))}")
    await _render_screen(c, state, '\n'.join(lines), reply_markup=recurring_reminder_actions_kb(int(row['id']), lang))
    await c.answer()


@router.callback_query(F.data.startswith('ri:remindsnooze:'))
async def recurring_snooze_from_reminder(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    recurring_id = int(c.data.split(':')[-1])
    tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    try:
        await mark_recurring_income_reminded(db, c.from_user.id, recurring_id, tomorrow)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    lang = await get_lang(db, c.from_user.id)
    text = (
        '🕒 <b>Напомню завтра</b>\\nСегодня больше не трогаю этот доход.'
        if lang == 'ru' else
        ('🕒 <b>I will remind you tomorrow</b>\\nI will not bother you about this income again today.' if lang == 'en' else '🕒 <b>Ертең еске саламын</b>\\nБүгін бұл кіріс туралы қайта мазаламаймын.')
    )
    try:
        await c.message.edit_text(text, parse_mode=PARSE_MODE)
    except Exception:
        await c.message.answer(text, parse_mode=PARSE_MODE)
    await c.answer()


@router.callback_query(F.data.startswith('ri:remindmanual:'))
async def recurring_manual_from_reminder(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    recurring_id = int(c.data.split(':')[-1])
    ts = now_iso()
    row = await get_recurring_income(db, c.from_user.id, recurring_id)
    if not row:
        await c.answer('Не найдено', show_alert=True)
        return
    try:
        await mark_recurring_received(db, c.from_user.id, recurring_id, ts)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    lang = await get_lang(db, c.from_user.id)
    text = (
        '🔗 <b>Отмечено как уже внесённое вручную</b>\\nНовый доход не создан, шаблон сдвинут на следующий месяц.'
        if lang == 'ru' else
        ('🔗 <b>Marked as already added manually</b>\\nNo new income was created, the template was moved to the next month.' if lang == 'en' else '🔗 <b>Қолмен бұрын енгізілген деп белгіленді</b>\\nЖаңа кіріс жасалмады, үлгі келесі айға жылжытылды.')
    )
    try:
        await c.message.edit_text(text, parse_mode=PARSE_MODE)
    except Exception:
        await c.message.answer(text, parse_mode=PARSE_MODE)
    await c.answer()

@router.callback_query(F.data.startswith('ri:archive:'))
async def recurring_archive(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    try:
        await archive_recurring_income(db, c.from_user.id, int(c.data.split(':')[-1]), now_iso())
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await recurring_list(c, state, db)


@router.callback_query(F.data.startswith('ri:restore:'))
async def recurring_restore(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    try:
        await restore_recurring_income(db, c.from_user.id, int(c.data.split(':')[-1]), now_iso())
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await recurring_archived(c, state, db)



async def _mark_income_missed(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, recurring_id: int, *, from_reminder: bool):
    ts = now_iso()
    row = await get_recurring_income(db, c.from_user.id, recurring_id)
    if not row:
        await c.answer('Не найдено', show_alert=True)
        return

    try:
        await skip_recurring_income(db, c.from_user.id, recurring_id, ts)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    lang = await get_lang(db, c.from_user.id)
    text = '🚫 <b>Доход отмечен как не полученный</b>\nБаланс не изменён, запись в историю не создана, шаблон перенесён на следующий месяц.' if lang == 'ru' else ("🚫 <b>Income marked as not received</b>\nBalance was not changed, no history record was created, and the template was moved to next month." if lang == 'en' else '🚫 <b>Кіріс алынбады деп белгіленді</b>\nБаланс өзгермеді, тарихқа жазба жасалмады, үлгі келесі айға жылжытылды.')
    done_text = '🚫 Доход пропущен на этот месяц.' if lang == 'ru' else ("🚫 Income skipped for this month." if lang == 'en' else '🚫 Кіріс осы айға өткізіліп жіберілді.')

    if from_reminder:
        try:
            await c.message.edit_text(text, parse_mode=PARSE_MODE)
        except Exception:
            await c.message.answer(done_text, parse_mode=PARSE_MODE)
        await c.answer()
        return

    await _clear_last_screen(c, state, forget=True)
    await _clear_recurring_flow_data(state)
    await c.message.answer(text, reply_markup=await build_main_menu_markup(db, c.from_user.id, lang), parse_mode=PARSE_MODE)
    await c.answer('Готово' if lang == 'ru' else ('Done' if lang == 'en' else 'Дайын'))


async def _mark_income_received(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, recurring_id: int, *, from_reminder: bool):
    ts = now_iso()
    row = await get_recurring_income(db, c.from_user.id, recurring_id)
    if not row:
        await c.answer('Не найдено', show_alert=True)
        return

    note = str(row['comment'] or row['title'] or '')
    try:
        tx_id = await create_tx(db, c.from_user.id, ts, 'income', int(row['amount']), int(row['account_id']), int(row['category_id']), note, ts)
        await apply_expense_income(db, c.from_user.id, tx_id, int(row['amount']), int(row['account_id']))
        await mark_recurring_received(db, c.from_user.id, recurring_id, ts)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    lang = await get_lang(db, c.from_user.id)
    text = '✅ <b>Доход отмечен как полученный</b>\nШаблон сдвинут на следующий месяц, запись добавлена в историю.' if lang == 'ru' else ('✅ <b>Income marked as received</b>\nTemplate moved to the next month and saved to history.' if lang == 'en' else '✅ <b>Кіріс алынды деп белгіленді</b>\nҮлгі келесі айға жылжытылып, тарихқа сақталды.')
    done_text = '✅ Доход отмечен и добавлен в историю.' if lang == 'ru' else ('✅ Income recorded in history.' if lang == 'en' else '✅ Кіріс белгіленіп, тарихқа қосылды.')

    if from_reminder:
        try:
            await c.message.edit_text(text, parse_mode=PARSE_MODE)
        except Exception:
            await c.message.answer(done_text, parse_mode=PARSE_MODE)
        await c.answer()
        return

    await _clear_last_screen(c, state, forget=True)
    await _clear_recurring_flow_data(state)
    await c.message.answer(text, reply_markup=await build_main_menu_markup(db, c.from_user.id, lang), parse_mode=PARSE_MODE)
    await c.answer('Готово')


@router.callback_query(F.data.startswith('ri:received:'))
async def recurring_paid(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    recurring_id = int(c.data.split(':')[-1])
    await _mark_income_received(c, state, db, recurring_id, from_reminder=False)


@router.callback_query(F.data.startswith('ri:missed:'))
async def recurring_missed(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    recurring_id = int(c.data.split(':')[-1])
    await _mark_income_missed(c, state, db, recurring_id, from_reminder=False)


@router.callback_query(F.data.startswith('ri:remindrecv:'))
async def recurring_received_from_reminder(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    recurring_id = int(c.data.split(':')[-1])
    await _mark_income_received(c, state, db, recurring_id, from_reminder=True)


@router.callback_query(F.data.startswith('ri:remindmissed:'))
async def recurring_missed_from_reminder(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    recurring_id = int(c.data.split(':')[-1])
    await _mark_income_missed(c, state, db, recurring_id, from_reminder=True)
