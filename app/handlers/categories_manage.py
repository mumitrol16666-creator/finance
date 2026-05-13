from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from datetime import datetime, timezone

from app.fsm.states import CategoriesFlow
from app.handlers.common import cancel_to_main_menu, is_cancel_text
from app.ui.keyboards import cats_kind_kb, cats_list_manage_kb, cat_actions_kb, cancel_kb, main_menu
from app.domain.validators import clean_name
from app.db.repositories.categories_repo import (
    list_categories, get_category, name_exists_any_kind,
    create_category, rename_category, set_category_emoji, archive_category
)
from app.db.repositories.settings_repo import get_lang

router = Router()


def now():
    return datetime.now(timezone.utc).isoformat()


def _L(lang: str) -> dict[str, str]:
    lang = (lang or 'ru').lower()
    if lang == 'en':
        return {
            'cancel_hint': '❌ Cancel — back to menu.', 'cancelled': 'Cancelled.',
            'root': '🗂 Categories\n\nChoose the type of categories to manage.',
            'expense_title': 'Expense categories', 'income_title': 'Income categories',
            'not_found': 'Not found', 'category': 'Category',
            'add_title': '➕ New category\n\nEnter category name.', 'emoji_later': 'You can add emoji later.',
            'name_len': 'The name must be 2 to 24 characters long.', 'name_exists': 'This name already exists. Choose another one.',
            'done': '✅ Done.', 'rename_title': '✏️ New category name\n\nEnter a new name.', 'rename_example': 'Example: Food',
            'emoji_title': "😀 Category emoji\n\nSend one emoji or '-' to remove it.", 'emoji_example': 'Example: 🍔',
            'emoji_error': "Send one emoji or '-'.", 'archived': '✅ Category archived.',
        }
    if lang == 'kk':
        return {
            'cancel_hint': '❌ Болдырмау — мәзірге шығу.', 'cancelled': 'Болдырылмады.',
            'root': '🗂 Санаттар\n\nБасқарылатын санат түрін таңдаңыз.',
            'expense_title': 'Шығыс санаттары', 'income_title': 'Кіріс санаттары',
            'not_found': 'Табылмады', 'category': 'Санат',
            'add_title': '➕ Жаңа санат\n\nСанат атауын енгізіңіз.', 'emoji_later': 'Emoji-ді кейін қосуға болады.',
            'name_len': 'Атауы 2 мен 24 таңба аралығында болуы керек.', 'name_exists': 'Мұндай атау бар. Басқасын таңдаңыз.',
            'done': '✅ Дайын.', 'rename_title': '✏️ Санаттың жаңа атауы\n\nЖаңа атауды енгізіңіз.', 'rename_example': 'Мысалы: Тамақ',
            'emoji_title': "😀 Санат emoji-і\n\nБір emoji немесе өшіру үшін '-' жіберіңіз.", 'emoji_example': 'Мысалы: 🍔',
            'emoji_error': "Бір emoji немесе '-' жіберіңіз.", 'archived': '✅ Санат архивтелді.',
        }
    return {
        'cancel_hint': '❌ Отмена — выйти в меню.', 'cancelled': 'Отменено.',
        'root': '🗂 Категории\n\nВыбери тип категорий для управления.',
        'expense_title': 'Категории расходов', 'income_title': 'Категории доходов',
        'not_found': 'Не найдено', 'category': 'Категория',
        'add_title': '➕ Новая категория\n\nВведи название категории.', 'emoji_later': 'Emoji можно будет добавить потом.',
        'name_len': 'Название должно быть от 2 до 24 символов.', 'name_exists': 'Такое название уже есть. Выбери другое.',
        'done': '✅ Готово.', 'rename_title': '✏️ Новое название категории\n\nВведи новое название.', 'rename_example': 'Например: Еда',
        'emoji_title': "😀 Emoji категории\n\nОтправь один emoji или '-' чтобы убрать.", 'emoji_example': 'Пример: 🍔',
        'emoji_error': "Пришли один emoji или '-'.", 'archived': '✅ Категория архивирована.',
    }


async def _lang_from_db(db, user_id: int) -> str:
    try:
        return await get_lang(db, user_id)
    except Exception:
        return 'ru'


async def _set_flow_message(state: FSMContext, message_id: int):
    await state.update_data(flow_message_id=message_id)


async def _set_prompt_message(state: FSMContext, message_id: int | None):
    await state.update_data(prompt_message_id=message_id)


async def _clear_prompt(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prompt_message_id = data.get('prompt_message_id')
    if not prompt_message_id:
        return
    bot = target.bot
    chat_id = target.chat.id if isinstance(target, Message) else target.message.chat.id
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(prompt_message_id))
    except Exception:
        pass
    await _set_prompt_message(state, None)


async def _render(c: CallbackQuery, state: FSMContext, text: str, reply_markup):
    await c.message.edit_text(text, reply_markup=reply_markup)
    await _set_flow_message(state, c.message.message_id)


async def _freeze_current_screen(c: CallbackQuery):
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


async def _start_input_flow(c: CallbackQuery, state: FSMContext, screen_text: str, prompt_text: str, lang: str):
    await _clear_prompt(c, state)
    await _freeze_current_screen(c)
    sent = await c.message.answer(screen_text)
    await _set_flow_message(state, sent.message_id)
    prompt = await c.message.answer(prompt_text, reply_markup=cancel_kb(lang))
    await _set_prompt_message(state, prompt.message_id)


async def _send_prompt(c: CallbackQuery, state: FSMContext, text: str, lang: str):
    await _clear_prompt(c, state)
    sent = await c.message.answer(text, reply_markup=cancel_kb(lang))
    await _set_prompt_message(state, sent.message_id)


async def _restore_cancel_bar(target: Message | CallbackQuery, state: FSMContext, lang: str):
    L = _L(lang)
    sent = await (
        target.message.answer(L['cancel_hint'], reply_markup=cancel_kb(lang))
        if isinstance(target, CallbackQuery)
        else target.answer(L['cancel_hint'], reply_markup=cancel_kb(lang))
    )
    await _set_prompt_message(state, sent.message_id)


async def _cancel_to_menu(m: Message, state: FSMContext, db):
    await cancel_to_main_menu(m, state, db)


@router.callback_query(F.data == 'st:cats')
async def st_cats(c: CallbackQuery, state: FSMContext, db):
    lang = await _lang_from_db(db, c.from_user.id)
    await state.clear()
    await _render(c, state, _L(lang)['root'], reply_markup=cats_kind_kb(lang))
    await c.answer()


@router.callback_query(F.data.startswith('st:cats:kind:'))
async def st_cats_kind(c: CallbackQuery, state: FSMContext, db):
    lang = await _lang_from_db(db, c.from_user.id)
    kind = c.data.split(':')[3]
    await state.clear()
    await state.update_data(cats_kind=kind)
    cats = await list_categories(db, c.from_user.id, kind)
    title = _L(lang)['expense_title'] if kind == 'expense' else _L(lang)['income_title']
    await _render(c, state, f'{title}:', reply_markup=cats_list_manage_kb(cats, kind, lang))
    await c.answer()


@router.callback_query(F.data.startswith('st:cats:pick:'))
async def st_cats_pick(c: CallbackQuery, state: FSMContext, db):
    lang = await _lang_from_db(db, c.from_user.id)
    cid = int(c.data.split(':')[3])
    row = await get_category(db, c.from_user.id, cid)
    if not row:
        await c.answer(_L(lang)['not_found'], show_alert=True)
        return
    _id, name, emoji, kind, _arch = row
    await state.clear()
    await state.update_data(cats_kind=kind, cat_id=cid)
    label = f"{emoji + ' ' if emoji else ''}{name}"
    await _render(c, state, f"{_L(lang)['category']}: {label}", reply_markup=cat_actions_kb(cid, lang))
    await c.answer()


@router.callback_query(F.data.startswith('st:cats:add:'))
async def st_cats_add(c: CallbackQuery, state: FSMContext, db):
    lang = await _lang_from_db(db, c.from_user.id)
    kind = c.data.split(':')[3]
    await state.clear()
    await state.update_data(cats_kind=kind)
    await state.set_state(CategoriesFlow.add_name)
    await _start_input_flow(c, state, _L(lang)['add_title'], _L(lang)['emoji_later'], lang)
    await c.answer()


@router.message(CategoriesFlow.add_name, F.text)
async def st_cats_add_name(m: Message, state: FSMContext, db):
    lang = await _lang_from_db(db, m.from_user.id)
    L = _L(lang)
    if is_cancel_text(m.text):
        await _cancel_to_menu(m, state, db)
        return
    kind = (await state.get_data()).get('cats_kind')
    name = clean_name(m.text)
    if not name:
        return await m.answer(L['name_len'], reply_markup=cancel_kb(lang))
    if await name_exists_any_kind(db, m.from_user.id, name):
        return await m.answer(L['name_exists'], reply_markup=cancel_kb(lang))
    await create_category(db, m.from_user.id, name, None, kind, now())
    await db.commit()
    cats = await list_categories(db, m.from_user.id, kind)
    await _clear_prompt(m, state)
    data = await state.get_data()
    flow_message_id = data.get('flow_message_id')
    title = L['expense_title'] if kind == 'expense' else L['income_title']
    if flow_message_id:
        try:
            await m.bot.edit_message_text(chat_id=m.chat.id, message_id=int(flow_message_id), text=f'{title}:', reply_markup=cats_list_manage_kb(cats, kind, lang))
        except Exception:
            await m.answer(f'{title}:', reply_markup=cats_list_manage_kb(cats, kind, lang))
    await state.clear()
    await _restore_cancel_bar(m, state, lang)
    await m.answer(L['done'])


@router.callback_query(F.data.startswith('st:cats:rename:'))
async def st_cats_rename(c: CallbackQuery, state: FSMContext, db):
    lang = await _lang_from_db(db, c.from_user.id)
    cid = int(c.data.split(':')[3])
    await state.set_state(CategoriesFlow.rename)
    await state.update_data(cat_id=cid)
    await _start_input_flow(c, state, _L(lang)['rename_title'], _L(lang)['rename_example'], lang)
    await c.answer()


@router.message(CategoriesFlow.rename, F.text)
async def st_cats_rename_text(m: Message, state: FSMContext, db):
    lang = await _lang_from_db(db, m.from_user.id)
    L = _L(lang)
    if is_cancel_text(m.text):
        await _cancel_to_menu(m, state, db)
        return
    data = await state.get_data()
    cid = int(data.get('cat_id'))
    row = await get_category(db, m.from_user.id, cid)
    if not row:
        await _cancel_to_menu(m, state, db)
        return
    _id, old_name, _emoji, kind, _arch = row
    name = clean_name(m.text)
    if not name:
        return await m.answer(L['name_len'], reply_markup=cancel_kb(lang))
    if name.lower() != old_name.lower() and await name_exists_any_kind(db, m.from_user.id, name):
        return await m.answer(L['name_exists'], reply_markup=cancel_kb(lang))
    await rename_category(db, m.from_user.id, cid, name, now())
    await db.commit()
    cats = await list_categories(db, m.from_user.id, kind)
    await _clear_prompt(m, state)
    flow_message_id = data.get('flow_message_id')
    title = L['expense_title'] if kind == 'expense' else L['income_title']
    if flow_message_id:
        try:
            await m.bot.edit_message_text(chat_id=m.chat.id, message_id=int(flow_message_id), text=f'{title}:', reply_markup=cats_list_manage_kb(cats, kind, lang))
        except Exception:
            await m.answer(f'{title}:', reply_markup=cats_list_manage_kb(cats, kind, lang))
    await state.clear()
    await _restore_cancel_bar(m, state, lang)
    await m.answer(L['done'])


@router.callback_query(F.data.startswith('st:cats:emoji:'))
async def st_cats_emoji(c: CallbackQuery, state: FSMContext, db):
    lang = await _lang_from_db(db, c.from_user.id)
    cid = int(c.data.split(':')[3])
    await state.set_state(CategoriesFlow.emoji)
    await state.update_data(cat_id=cid, flow_message_id=c.message.message_id)
    await _render(c, state, _L(lang)['emoji_title'], reply_markup=None)
    await _send_prompt(c, state, _L(lang)['emoji_example'], lang)
    await c.answer()


@router.message(CategoriesFlow.emoji, F.text)
async def st_cats_emoji_text(m: Message, state: FSMContext, db):
    lang = await _lang_from_db(db, m.from_user.id)
    L = _L(lang)
    if is_cancel_text(m.text):
        await _cancel_to_menu(m, state, db)
        return
    data = await state.get_data()
    cid = int(data.get('cat_id'))
    row = await get_category(db, m.from_user.id, cid)
    if not row:
        await _cancel_to_menu(m, state, db)
        return
    _id, _name, _old_emoji, kind, _arch = row
    em = m.text.strip()
    if em == '-':
        em = None
    if em and len(em) > 4:
        return await m.answer(L['emoji_error'], reply_markup=cancel_kb(lang))
    await set_category_emoji(db, m.from_user.id, cid, em, now())
    await db.commit()
    cats = await list_categories(db, m.from_user.id, kind)
    await _clear_prompt(m, state)
    flow_message_id = data.get('flow_message_id')
    title = L['expense_title'] if kind == 'expense' else L['income_title']
    if flow_message_id:
        try:
            await m.bot.edit_message_text(chat_id=m.chat.id, message_id=int(flow_message_id), text=f'{title}:', reply_markup=cats_list_manage_kb(cats, kind, lang))
        except Exception:
            await m.answer(f'{title}:', reply_markup=cats_list_manage_kb(cats, kind, lang))
    await state.clear()
    await _restore_cancel_bar(m, state, lang)
    await m.answer(L['done'])


@router.callback_query(F.data.startswith('st:cats:arch:'))
async def st_cats_arch(c: CallbackQuery, state: FSMContext, db):
    lang = await _lang_from_db(db, c.from_user.id)
    cid = int(c.data.split(':')[3])
    row = await get_category(db, c.from_user.id, cid)
    if not row:
        await c.answer(_L(lang)['not_found'], show_alert=True)
        return
    _id, _name, _emoji, kind, _arch = row
    await archive_category(db, c.from_user.id, cid, now())
    await db.commit()
    await state.clear()
    cats = await list_categories(db, c.from_user.id, kind)
    await _render(c, state, _L(lang)['archived'], reply_markup=cats_list_manage_kb(cats, kind, lang))
    await c.answer()
