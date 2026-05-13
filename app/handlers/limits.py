from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
import aiosqlite

from app.db.repositories.limits_repo import (
    set_daily_limit,
    get_daily_limit,
    set_category_daily_limit,
    today_expense_total,
    week_expense_total,
)
from app.db.repositories.categories_repo import list_categories
from app.db.repositories.settings_repo import get_lang
from app.handlers.common import build_main_menu_markup
from app.ui.formatters import block, fmt_money

router = Router()


def _L(lang: str) -> dict[str, str]:
    lang = (lang or 'ru').lower()
    if lang == 'en':
        return {
            'daily_limit': '📏 Daily limit', 'current': 'Current', 'change': 'Change', 'not_set': 'Not set.', 'set_hint': 'Set: /limit 15000',
            'bad_format': 'Invalid amount format.', 'updated': '✅ Daily limit updated', 'spent_today': 'Spent today', 'left': 'Left',
            'cat_limit': '📌 Category limit (per day)', 'cat_format': 'Format: /catlimit <category> <limit>', 'cat_example': 'Example: /catlimit Food 3000',
            'must_number': 'The limit must be a number > 0.', 'cat_not_found': 'Category not found.', 'add_categories': 'Add expense categories first.',
            'cat_set': '✅ Category limit set', 'category': 'Category', 'limit': 'Limit',
            'day_status': '📊 Day status', 'weekdiff': '📈 Week over week', 'this_week': 'This week', 'last_week': 'Last week', 'diff': 'Difference',
        }
    if lang == 'kk':
        return {
            'daily_limit': '📏 Күндік лимит', 'current': 'Ағымдағы', 'change': 'Өзгерту', 'not_set': 'Орнатылмаған.', 'set_hint': 'Орнату: /limit 15000',
            'bad_format': 'Сома форматы қате.', 'updated': '✅ Күндік лимит жаңартылды', 'spent_today': 'Бүгін жұмсалды', 'left': 'Қалды',
            'cat_limit': '📌 Санат лимиті (күніне)', 'cat_format': 'Формат: /catlimit <санат> <лимит>', 'cat_example': 'Мысал: /catlimit Тамақ 3000',
            'must_number': 'Лимит 0-ден үлкен сан болуы керек.', 'cat_not_found': 'Санат табылмады.', 'add_categories': 'Алдымен шығыс санаттарын қосыңыз.',
            'cat_set': '✅ Санат лимиті орнатылды', 'category': 'Санат', 'limit': 'Лимит',
            'day_status': '📊 Күн мәртебесі', 'weekdiff': '📈 Аптадан аптаға', 'this_week': 'Осы апта', 'last_week': 'Өткен апта', 'diff': 'Айырма',
        }
    return {
        'daily_limit': '📏 Дневной лимит', 'current': 'Текущий', 'change': 'Изменить', 'not_set': 'Не задан.', 'set_hint': 'Установить: /limit 15000',
        'bad_format': 'Неверный формат суммы.', 'updated': '✅ Дневной лимит обновлён', 'spent_today': 'Сегодня потрачено', 'left': 'Остаток',
        'cat_limit': '📌 Лимит на категорию (в день)', 'cat_format': 'Формат: /catlimit <категория> <лимит>', 'cat_example': 'Пример: /catlimit Еда 3000',
        'must_number': 'Лимит должен быть числом > 0.', 'cat_not_found': 'Категория не найдена.', 'add_categories': 'Сначала добавь категории расходов.',
        'cat_set': '✅ Лимит на категорию установлен', 'category': 'Категория', 'limit': 'Лимит',
        'day_status': '📊 Статус дня', 'weekdiff': '📈 Неделя к неделе', 'this_week': 'Эта неделя', 'last_week': 'Прошлая', 'diff': 'Разница',
    }


def _parse_amount(s: str) -> int | None:
    s = (s or '').strip().replace(' ', '').replace('_', '').replace('.', '')
    if not s or not s.isdigit():
        return None
    n = int(s)
    return n if n > 0 else None


def _badge(spent: int, limit_: int) -> str:
    if limit_ <= 0:
        return '⚪'
    if spent < limit_ * 0.8:
        return '🟢'
    if spent < limit_:
        return '🟡'
    if spent < limit_ * 1.2:
        return '🔴'
    return '⚫'


def _pct(diff: int, base: int) -> str:
    if base == 0:
        return '—'
    return f'{(diff / base) * 100:.1f}%'


@router.message(Command('limit'))
async def limit_cmd(m: Message, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)
    L = _L(lang)
    parts = (m.text or '').split(maxsplit=1)
    if len(parts) < 2:
        cur = await get_daily_limit(db, m.from_user.id)
        if cur:
            return await m.answer(block(L['daily_limit'], f"{L['current']}: {fmt_money(cur)}", '', f"{L['change']}: /limit 15000"), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode='HTML')
        return await m.answer(block(L['daily_limit'], L['not_set'], '', L['set_hint']), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode='HTML')
    amount = _parse_amount(parts[1])
    if amount is None:
        return await m.answer(block(L['daily_limit'], L['bad_format'], 'Example: /limit 15000' if lang=='en' else ('Мысал: /limit 15000' if lang=='kk' else 'Пример: /limit 15000')), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode='HTML')
    try:
        await set_daily_limit(db, m.from_user.id, amount)
        await db.commit()
    except Exception:
        await db.rollback(); raise
    spent = await today_expense_total(db, m.from_user.id)
    left = amount - spent
    left_line = fmt_money(left) if left >= 0 else f'-{fmt_money(abs(left))}'
    await m.answer(block(L['updated'], f"• {L['limit']}: {fmt_money(amount)}", f"• {L['spent_today']}: {fmt_money(spent)}", f"• {L['left']}: {left_line}"), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode='HTML')


@router.message(Command('catlimit'))
async def catlimit_cmd(m: Message, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)
    L = _L(lang)
    raw = (m.text or '').strip()
    parts = raw.split()
    if len(parts) < 3:
        return await m.answer(block(L['cat_limit'], L['cat_format'], L['cat_example']), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode='HTML')
    amount = _parse_amount(parts[-1])
    if amount is None:
        return await m.answer(block(L['cat_limit'], L['must_number'], L['cat_example']), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode='HTML')
    cat_name = ' '.join(parts[1:-1]).strip().lower()
    cats = await list_categories(db, m.from_user.id, kind='expense')
    match = None
    for cid, name, emoji, kind, arch in cats:
        if arch:
            continue
        if (name or '').strip().lower() == cat_name:
            match = (int(cid), name, emoji)
            break
    if not match:
        sample = ', '.join([(c[2] + ' ' if c[2] else '') + c[1] for c in cats[:10]])
        return await m.answer(block(L['cat_limit'], L['cat_not_found'], f'Examples: {sample}' if sample and lang=='en' else (f'Мысалдар: {sample}' if sample and lang=='kk' else (f'Примеры: {sample}' if sample else L['add_categories']))), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode='HTML')
    cid, name, emoji = match
    try:
        await set_category_daily_limit(db, m.from_user.id, cid, amount)
        await db.commit()
    except Exception:
        await db.rollback(); raise
    em = (emoji + ' ') if emoji else ''
    per_day = '/ day' if lang=='en' else ('/ күн' if lang=='kk' else '/ день')
    await m.answer(block(L['cat_set'], f"{L['category']}: {em}{name}", f"{L['limit']}: {fmt_money(amount)} {per_day}"), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode='HTML')


@router.message(Command('status'))
async def status_cmd(m: Message, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)
    L = _L(lang)
    spent = await today_expense_total(db, m.from_user.id)
    limit_ = await get_daily_limit(db, m.from_user.id)
    if not limit_:
        return await m.answer(block(L['day_status'], f"{L['spent_today']}: {fmt_money(spent)}", '', L['set_hint']), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode='HTML')
    left = int(limit_ - spent)
    left_line = fmt_money(left) if left >= 0 else f'-{fmt_money(abs(left))}'
    badge = _badge(spent, int(limit_))
    await m.answer(block(f"{badge} {L['day_status']}", f"• {L['spent_today']}: {fmt_money(spent)}", f"• {L['limit']}: {fmt_money(limit_)}", f"• {L['left']}: {left_line}"), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode='HTML')


@router.message(Command('weekdiff'))
async def weekdiff_cmd(m: Message, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)
    L = _L(lang)
    this_week = await week_expense_total(db, m.from_user.id, offset_weeks=0)
    last_week = await week_expense_total(db, m.from_user.id, offset_weeks=-1)
    diff = int(this_week - last_week)
    sign = '+' if diff > 0 else ''
    pct = _pct(diff, int(last_week))
    await m.answer(block(L['weekdiff'], f"• {L['this_week']}: {fmt_money(this_week)}", f"• {L['last_week']}: {fmt_money(last_week)}", f"• {L['diff']}: {sign}{fmt_money(diff)} ({pct})"), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang), parse_mode='HTML')
