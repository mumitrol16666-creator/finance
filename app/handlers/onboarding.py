# app/handlers/onboarding.py

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from app.config.settings import settings
from app.db.repositories.users_repo import get_onboarded
from app.ui.texts import get_text
from app.ui.keyboards import (
    onboarding_start_kb, currency_kb, cancel_kb,
    yes_no_kb, daily_time_quick_kb, lang_selection_kb
)
from app.fsm.states import Onboarding
from app.domain.validators import clean_name, parse_hhmm
from app.handlers.common import (
    cancel_to_main_menu, is_cancel_text, build_main_menu_markup,
    neutralize_keyboard
)
from app.domain.services.onboarding_service import (
    init_user, save_currency, add_account, has_any_account,
    save_daily_report, finish_onboarding, utcnow_iso
)
from app.db.repositories.settings_repo import get_lang, set_lang
from app.handlers.onboarding_interview import start_interview

router = Router()
PARSE_MODE = "HTML"

def dbg(txt: str) -> str:
    return f"\n\n#DBG {txt}" if settings.debug else ""

async def _try_delete(bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, int(message_id))
    except Exception:
        pass

async def answer_md(m: Message, text: str, **kwargs):
    return await m.answer(text, parse_mode=PARSE_MODE, **kwargs)

async def edit_md(msg, text: str, **kwargs):
    return await msg.edit_text(text, parse_mode=PARSE_MODE, **kwargs)

@router.message(CommandStart())
async def start(m: Message, state: FSMContext, db):
    await state.clear()
    onboarded = await get_onboarded(db, m.from_user.id)
    lang = await get_lang(db, m.from_user.id)
    if onboarded == 1:
        return await answer_md(m, get_text(lang, 'MENU'), reply_markup=await build_main_menu_markup(db, m.from_user.id, lang))
    await init_user(db, m.from_user.id, settings.timezone)
    
    prompt = (
        "🇷🇺 <b>Выберите язык</b>\n\n"
        "🇬🇧 <b>Choose language</b>\n\n"
        "🇰🇿 <b>Тілді таңдаңыз</b>"
    )
    sent = await answer_md(m, prompt, reply_markup=lang_selection_kb())
    await state.update_data(flow_message_id=sent.message_id, ui_scope='onboarding')

@router.callback_query(F.data.startswith('ob:lang:'))
async def ob_lang_selected(c: CallbackQuery, state: FSMContext, db):
    await neutralize_keyboard(c)
    lang = c.data.split(':')[-1]
    await set_lang(db, c.from_user.id, lang, utcnow_iso())
    await db.commit()
    
    await edit_md(c.message, get_text(lang, 'START_INTRO'), reply_markup=onboarding_start_kb(lang))
    await c.answer()

@router.callback_query(F.data == 'ob:cancel')
async def ob_cancel(c: CallbackQuery, state: FSMContext, db):
    await cancel_to_main_menu(c, state, db)

@router.callback_query(F.data == 'ob:start')
async def ob_start(c: CallbackQuery, state: FSMContext, db):
    await neutralize_keyboard(c)
    await state.clear()
    await state.update_data(flow_message_id=c.message.message_id, ui_scope='onboarding')
    lang = await get_lang(db, c.from_user.id)
    await edit_md(c.message, get_text(lang, 'ASK_CURRENCY'), reply_markup=currency_kb())
    await c.answer()

@router.callback_query(F.data.startswith('ob:cur:'))
async def ob_currency(c: CallbackQuery, state: FSMContext, db):
    await neutralize_keyboard(c)
    cur = c.data.split(':')[2]
    await save_currency(db, c.from_user.id, cur)
    lang = await get_lang(db, c.from_user.id)
    await edit_md(c.message, get_text(lang, 'CURRENCY_SAVED', cur=cur) + dbg(f' currency={cur}'), reply_markup=None)
    await state.set_state(Onboarding.acc_name)
    sent = await answer_md(c.message, get_text(lang, 'ASK_ACC_NAME'), reply_markup=cancel_kb(lang))
    await state.update_data(prompt_message_id=sent.message_id, ui_scope='onboarding')
    await c.answer()

@router.message(Onboarding.acc_name, F.text)
async def ob_acc_name(m: Message, state: FSMContext, db):
    lang = await get_lang(db, m.from_user.id)
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    name = clean_name(m.text)
    if not name:
        return await answer_md(m, get_text(lang, 'NAME_ERROR'), reply_markup=cancel_kb(lang))
    data = await state.get_data()
    await _try_delete(m.bot, m.chat.id, data.get("prompt_message_id"))
    try:
        await m.delete()
    except Exception:
        pass
    await state.update_data(acc_name=name)
    await state.set_state(Onboarding.acc_balance)
    sent = await answer_md(m, get_text(lang, 'ASK_ACC_BAL'), reply_markup=cancel_kb(lang))
    await state.update_data(prompt_message_id=sent.message_id)

@router.message(Onboarding.acc_balance, F.text)
async def ob_acc_bal(m: Message, state: FSMContext, db):
    lang = await get_lang(db, m.from_user.id)
    if is_cancel_text(m.text):
        await cancel_to_main_menu(m, state, db)
        return
    # Опорный 0 разрешён (открыли счёт с нулевым балансом), поэтому проверяем
    # его отдельно — parse_money всегда отвергает 0 как невалидный.
    from app.domain.money import parse_money_for_user
    raw = (m.text or "").strip().replace(" ", "").replace(",", ".")
    if raw in {"0", "0.0", "0.00"}:
        bal = 0
    else:
        bal = await parse_money_for_user(db, m.from_user.id, m.text, max_minor=99_999_999_00)
        if bal is None:
            return await answer_md(m, get_text(lang, 'SUM_ERROR'), reply_markup=cancel_kb(lang))
    data = await state.get_data()
    await _try_delete(m.bot, m.chat.id, data.get("prompt_message_id"))
    try:
        await m.delete()
    except Exception:
        pass
    await add_account(db, m.from_user.id, data['acc_name'], bal)
    await state.clear()
    await answer_md(m, get_text(lang, 'ASK_ADD_MORE'), reply_markup=yes_no_kb('ob:moreacc', lang))

@router.callback_query(F.data.startswith('ob:moreacc:'))
async def ob_more_acc(c: CallbackQuery, state: FSMContext, db):
    await neutralize_keyboard(c)
    ans = c.data.split(':')[2]
    lang = await get_lang(db, c.from_user.id)
    if ans == 'yes':
        await state.set_state(Onboarding.acc_name)
        sent = await answer_md(c.message, get_text(lang, 'ASK_ACC_NAME'), reply_markup=cancel_kb(lang))
        await state.update_data(prompt_message_id=sent.message_id, ui_scope='onboarding')
        await c.answer()
        return
    if not await has_any_account(db, c.from_user.id):
        await c.answer(get_text(lang, 'NEED_ONE_ACCOUNT'), show_alert=True)
        await state.set_state(Onboarding.acc_name)
        sent = await answer_md(c.message, get_text(lang, 'ASK_ACC_NAME'), reply_markup=cancel_kb(lang))
        await state.update_data(prompt_message_id=sent.message_id)
        return
    await answer_md(c.message, get_text(lang, 'ASK_DAILY'), reply_markup=yes_no_kb('ob:daily', lang))
    await c.answer()

@router.callback_query(F.data.startswith('ob:daily:'))
async def ob_daily(c: CallbackQuery, state: FSMContext, db):
    await neutralize_keyboard(c)
    ans = c.data.split(':')[2]
    lang = await get_lang(db, c.from_user.id)
    if ans == 'no':
        await save_daily_report(db, c.from_user.id, 0, '21:00')
        await finish_onboarding(db, c.from_user.id)
        await start_interview(c.message, state, db)
        await c.answer()
        return
    await save_daily_report(db, c.from_user.id, 1, '21:00')
    await answer_md(c.message, get_text(lang, 'ASK_DAILY_TIME'), reply_markup=daily_time_quick_kb(lang))
    await c.answer()

@router.callback_query(F.data.startswith('ob:time:'))
async def ob_time_pick(c: CallbackQuery, state: FSMContext, db):
    await neutralize_keyboard(c)
    part = c.data.split(':')[2:]
    lang = await get_lang(db, c.from_user.id)
    if part[0] == 'other':
        await state.set_state(Onboarding.daily_time_custom)
        await state.update_data(flow_message_id=c.message.message_id, ui_scope='onboarding')
        sent = await answer_md(c.message, get_text(lang, 'CUSTOM_TIME') + dbg(' time custom'), reply_markup=cancel_kb(lang))
        await state.update_data(prompt_message_id=sent.message_id)
        await c.answer()
        return
    hhmm = ':'.join(part)
    await save_daily_report(db, c.from_user.id, 1, hhmm)
    await finish_onboarding(db, c.from_user.id)
    await start_interview(c.message, state, db)
    await c.answer()

@router.message(Onboarding.daily_time_custom, F.text)
async def ob_time_custom(m: Message, state: FSMContext, db):
    lang = await get_lang(db, m.from_user.id)
    hhmm = parse_hhmm(m.text)
    if not hhmm:
        return await answer_md(m, get_text(lang, 'TIME_ERROR'))
    await save_daily_report(db, m.from_user.id, 1, hhmm)
    await finish_onboarding(db, m.from_user.id)
    await start_interview(m, state, db)
