from __future__ import annotations

from datetime import datetime, timezone
from html import escape

import aiosqlite
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.db.repositories.accounts_repo import (
    account_has_transactions,
    archive_account,
    create_account,
    delete_account_permanently,
    get_account,
    list_accounts,
    list_archived_accounts,
    rename_account,
    restore_account,
    set_account_balance,
    update_account_currency,
    toggle_account_saving,
)
from app.db.repositories.reset_repo import wipe_user_data
from app.db.repositories.settings_repo import (
    get_notification_settings,
    update_daily_report,
    update_nudges,
    get_recurring_settings,
    update_recurring_inc_settings,
    update_recurring_exp_settings,
)
from app.domain.validators import clean_name, parse_hhmm
from app.fsm.states import SettingsFlow
from app.handlers.budgets import show_budget_categories
from app.handlers.common import (
    cancel_to_main_menu,
    is_cancel_text,
    build_main_menu_markup,
    consume_user_input,
    neutralize_keyboard,
)
from app.ui.i18n import t, text_matches_key
from app.db.repositories.settings_repo import get_lang
from app.ui.keyboards import (
    account_actions_kb,
    accounts_kb,
    active_accounts_kb,
    archived_account_actions_kb,
    archived_accounts_kb,
    cancel_kb,
    main_menu,
    notifications_kb,
    nudge_interval_kb,
    reset_confirm_kb,
    settings_accounts_kb,
    settings_kb,
    lang_kb,
    account_currency_kb,
    account_type_kb,
)

router = Router()

PARSE_MODE = "HTML"
SETTINGS_SCOPE = "settings"


def _s(lang: str, key: str, **kwargs) -> str:
    lang = (lang or "ru").lower()
    data = {
        "ru": {
            "root": "⚙️ <b>Настройки</b>\n\nЗдесь можно управлять счетами, лимитами, категориями и уведомлениями.\nВыбери нужный раздел ниже.",
            "empty_notifs": "🔔 <b>Уведомления</b>\n\nНастройки уведомлений пока недоступны.\nЗапусти <code>/start</code> и открой раздел снова.",
            "daily_on": "включён", "daily_off": "выключен", "nudge_on": "включены", "nudge_off": "выключены",
            "notifs_tpl": "🔔 <b>Уведомления</b>\n\n📅 Ежедневный отчёт: <b>{daily}</b>\n⏰ Время отчёта: <b>{time}</b>\n🔁 Напоминания в течение дня: <b>{nudge}</b>\n🕒 Интервал: <b>{hours} ч</b>\n\n💰 Зарплата/Доходы: <b>{inc}</b>\n💳 Подписки/Траты: <b>{exp}</b>\n\nЕжедневный отчёт показывает итог дня. Дневные напоминания помогают не забывать заносить операции.",
            "accounts_title": "💳 <b>Счета</b>", "total":"💰 Всего на счетах: <b>{value}</b>", "active":"📦 Активных счетов: <b>{value}</b>", "archived":"🗄 В архиве: <b>{value}</b>",
            "no_accounts1":"Пока нет ни одного активного счёта.", "no_accounts2":"Нажми <b>«Добавить счёт»</b>, чтобы создать первый.", "current":"<b>Текущие счета</b>", "below":"Ниже доступны действия со счетами.",
            "done":"✅ <b>Готово</b>", "new_acc":"➕ <b>Новый счёт</b>\n\nУкажи название счёта.", "example_kaspi":"Пример: <b>Kaspi</b>", "name_len":"Название должно быть длиной от <b>2</b> до <b>24</b> символов.",
            "balance_prompt":"💰 Теперь укажи стартовый баланс.\nПример: <code>15000</code> или <code>1 200,50</code>", "digits_only":"Нужны только цифры. Пример: <code>15000</code>", "no_accounts_alert":"Нет счетов",
            "acc_add_name_saved":"✅ <b>Название сохранено:</b> {name}",
            "acc_add_back_name":"✏️ Изменить название",
            "acc_add_balance_hint":"Если ошибся в сумме — просто отправь число ещё раз. Отмена — кнопка <b>«Отмена»</b> внизу.",
            "acc_add_balance_saved":"✅ <b>Стартовый баланс:</b> {amount}",
            "rename_pick":"✏️ <b>Переименование счёта</b>\n\nВыбери счёт из списка.", "rename_new":"✏️ <b>Новое название счёта</b>\n\nВведи новое название.", "example_cash":"Пример: <b>Наличные</b>",
            "archive_pick":"🗂 <b>Архивация счёта</b>\n\nВыбери счёт, который нужно убрать из активных.", "archived_ok":"✅ <b>Счёт перенесён в архив</b>",
            "reset":"⚠️ <b>Сброс данных</b>\n\nБудут удалены:\n• все операции\n• все счета\n• все лимиты\n\nДействие необратимо.", "reset_done":"✅ <b>Готово</b>\nДанные удалены. Новую настройку можно начать через <code>/start</code>.",
            "time_title":"⏰ <b>Время ежедневного отчёта</b>\n\nУкажи время, когда бот должен отправлять итог дня.", "time_example":"Пример: <code>21:00</code>", "time_err":"Нужно время в формате <b>HH:MM</b>. Пример: <code>09:30</code>",
            "interval":"🕒 <b>Интервал напоминаний</b>\n\nВыбери, как часто бот должен напоминать в течение дня.",
            "recurring_inc_title": "💰 <b>Напоминания о доходах</b>\n\nВыбери, за сколько дней до получения зарплаты или другого дохода бот должен прислать уведомление.",
            "recurring_exp_title": "💳 <b>Напоминания о расходах</b>\n\nВыбери, за сколько дней до списания (подписки, аренда и т.д.) бот должен напомнить об этом.",
        },
        "en": {
            "root": "⚙️ <b>Settings</b>\n\nManage accounts, limits, categories and notifications here.\nChoose a section below.",
            "empty_notifs": "🔔 <b>Notifications</b>\n\nNotification settings are not available yet.\nRun <code>/start</code> and open this section again.",
            "daily_on": "enabled", "daily_off": "disabled", "nudge_on": "enabled", "nudge_off": "disabled",
            "notifs_tpl": "🔔 <b>Notifications</b>\n\n📅 Daily report: <b>{daily}</b>\n⏰ Report time: <b>{time}</b>\n🔁 Nudges during the day: <b>{nudge}</b>\n🕒 Interval: <b>{hours} h</b>\n\n💰 Salary/Incomes: <b>{inc}</b>\n💳 Subscriptions/Expenses: <b>{exp}</b>\n\nThe daily report shows the result of the day. Nudges help you remember to add transactions.",
            "accounts_title": "💳 <b>Accounts</b>", "total":"💰 Total balance: <b>{value}</b>", "active":"📦 Active accounts: <b>{value}</b>", "archived":"🗄 Archived: <b>{value}</b>",
            "no_accounts1":"There are no active accounts yet.", "no_accounts2":"Tap <b>“Add account”</b> to create your first one.", "current":"<b>Current accounts</b>", "below":"Available actions are shown below.",
            "done":"✅ <b>Done</b>", "new_acc":"➕ <b>New account</b>\n\nEnter the account name.", "example_kaspi":"Example: <b>Kaspi</b>", "name_len":"The name must be between <b>2</b> and <b>24</b> characters.",
            "balance_prompt":"💰 Now enter the starting balance.\nExample: <code>15000</code> or <code>1,200.50</code>", "digits_only":"Digits only. Example: <code>15000</code>", "no_accounts_alert":"No accounts",
            "acc_add_name_saved":"✅ <b>Name saved:</b> {name}",
            "acc_add_back_name":"✏️ Change name",
            "acc_add_balance_hint":"Wrong amount? Just send the number again. Cancel — use the <b>Cancel</b> button below.",
            "acc_add_balance_saved":"✅ <b>Starting balance:</b> {amount}",
            "rename_pick":"✏️ <b>Rename account</b>\n\nChoose an account from the list.", "rename_new":"✏️ <b>New account name</b>\n\nEnter the new name.", "example_cash":"Example: <b>Cash</b>",
            "archive_pick":"🗂 <b>Archive account</b>\n\nChoose the account to remove from active ones.", "archived_ok":"✅ <b>Account moved to archive</b>",
            "reset":"⚠️ <b>Reset data</b>\n\nThe following will be deleted:\n• all transactions\n• all accounts\n• all limits\n\nThis action cannot be undone.", "reset_done":"✅ <b>Done</b>\nData deleted. You can start setup again with <code>/start</code>.",
            "time_title":"⏰ <b>Daily report time</b>\n\nSpecify when the bot should send the daily summary.", "time_example":"Example: <code>21:00</code>", "time_err":"Use <b>HH:MM</b> format. Example: <code>09:30</code>",
            "interval":"🕒 <b>Nudge interval</b>\n\nChoose how often the bot should remind you during the day.",
            "recurring_inc_title": "💰 <b>Income Reminders</b>\n\nChoose how many days before a salary or other income the bot should notify you.",
            "recurring_exp_title": "💳 <b>Expense Reminders</b>\n\nChoose how many days before a recurring expense (subscription, rent, etc.) the bot should notify you.",
        },
        "kk": {
            "root": "⚙️ <b>Баптаулар</b>\n\nМұнда шоттарды, лимиттерді, санаттарды және хабарламаларды басқаруға болады.\nТөменнен бөлімді таңдаңыз.",
            "empty_notifs": "🔔 <b>Хабарламалар</b>\n\nХабарлама баптаулары әзірге қолжетімсіз.\n<code>/start</code> іске қосып, бөлімді қайта ашыңыз.",
            "daily_on": "қосулы", "daily_off": "өшірулі", "nudge_on": "қосулы", "nudge_off": "өшірулі",
            "notifs_tpl": "🔔 <b>Хабарламалар</b>\n\n📅 Күндік есеп: <b>{daily}</b>\n⏰ Есеп уақыты: <b>{time}</b>\n🔁 Күндізгі еске салғыштар: <b>{nudge}</b>\n🕒 Аралық: <b>{hours} сағ</b>\n\n💰 Жалақы/Кірістер: <b>{inc}</b>\n💳 Жазылымдар/Шығыстар: <b>{exp}</b>\n\nКүндік есеп күн қорытындысын көрсетеді. Еске салғыштар операцияларды енгізуді ұмытпауға көмектеседі.",
            "accounts_title": "💳 <b>Шоттар</b>", "total":"💰 Барлығы шоттарда: <b>{value}</b>", "active":"📦 Белсенді шоттар: <b>{value}</b>", "archived":"🗄 Архивте: <b>{value}</b>",
            "no_accounts1":"Әзірге белсенді шот жоқ.", "no_accounts2":"Алғашқы шотты құру үшін <b>«Шот қосу»</b> түймесін басыңыз.", "current":"<b>Ағымдағы шоттар</b>", "below":"Қол жетімді әрекеттер төменде көрсетілген.",
            "done":"✅ <b>Дайын</b>", "new_acc":"➕ <b>Жаңа шот</b>\n\nШот атауын енгізіңіз.", "example_kaspi":"Мысал: <b>Kaspi</b>", "name_len":"Атауы <b>2</b> мен <b>24</b> таңба аралығында болуы керек.",
            "balance_prompt":"💰 Енді бастапқы балансты енгізіңіз.\nМысал: <code>15000</code> немесе <code>1 200,50</code>", "digits_only":"Тек цифрлар. Мысал: <code>15000</code>", "no_accounts_alert":"Шоттар жоқ",
            "acc_add_name_saved":"✅ <b>Атау сақталды:</b> {name}",
            "acc_add_back_name":"✏️ Атауды өзгерту",
            "acc_add_balance_hint":"Сан қате болса — тек саны қайта жіберіңіз. Бас тарту — төмендегі <b>«Бас тарту»</b> түймесі.",
            "acc_add_balance_saved":"✅ <b>Бастапқы баланс:</b> {amount}",
            "rename_pick":"✏️ <b>Шот атауын өзгерту</b>\n\nТізімнен шотты таңдаңыз.", "rename_new":"✏️ <b>Жаңа шот атауы</b>\n\nЖаңа атауды енгізіңіз.", "example_cash":"Мысал: <b>Қолма-қол</b>",
            "archive_pick":"🗂 <b>Шотты архивке жіберу</b>\n\nБелсенді тізімнен алып тастайтын шотты таңдаңыз.", "archived_ok":"✅ <b>Шот архивке жіберілді</b>",
            "reset":"⚠️ <b>Деректерді өшіру</b>\n\nМыналар жойылады:\n• барлық операциялар\n• барлық шоттар\n• барлық лимиттер\n\nБұл әрекетті қайтару мүмкін емес.", "reset_done":"✅ <b>Дайын</b>\nДеректер өшірілді. Жаңа баптауды <code>/start</code> арқылы бастауға болады.",
            "time_title":"⏰ <b>Күндік есеп уақыты</b>\n\nБот күн қорытындысын қай уақытта жіберуі керек екенін көрсетіңіз.", "time_example":"Мысал: <code>21:00</code>", "time_err":"<b>HH:MM</b> форматын қолданыңыз. Мысал: <code>09:30</code>",
            "interval":"🕒 <b>Еске салу аралығы</b>\n\nБот күн ішінде қаншалық жиі еске салу керегін таңдаңыз.",
            "recurring_inc_title": "💰 <b>Кірістер туралы еске салу</b>\n\nЖалақы немесе басқа кіріс түспес бұрын бот неше күн бұрын хабарлауы керек екенін таңдаңыз.",
            "recurring_exp_title": "💳 <b>Шығыстар туралы еске салу</b>\n\nТөлем (жазылымдар, жалдау және т.б.) жасалмас бұрын бот неше күн бұрын хабарлауы керек екенін таңдаңыз.",
        },
    }
    base = data.get(lang, data['ru']).get(key, data['ru'].get(key, key))
    return base.format(**kwargs) if kwargs else base




# =========================================================
# Base helpers
# =========================================================

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _safe_remove_markup(bot, chat_id: int, message_id: int | None):
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=int(message_id), reply_markup=None)
    except Exception:
        pass


async def _remember_screen(state: FSMContext, message_id: int | None):
    await state.update_data(flow_message_id=message_id)


async def _clear_prompt(target: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prompt_id = data.get("prompt_message_id")
    bot = target.bot
    chat_id = target.chat.id if isinstance(target, Message) else target.message.chat.id
    if prompt_id:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=int(prompt_id))
        except Exception:
            pass
    await state.update_data(prompt_message_id=None)


async def _edit_screen(c: CallbackQuery, state: FSMContext, text: str, reply_markup=None):
    data = await state.get_data()
    flow_id = data.get("flow_message_id")
    if flow_id:
        try:
            await c.bot.edit_message_text(
                chat_id=c.message.chat.id,
                message_id=int(flow_id),
                text=text,
                reply_markup=reply_markup,
                parse_mode=PARSE_MODE,
            )
            return
        except Exception:
            pass
    sent = await c.message.edit_text(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    await _remember_screen(state, sent.message_id)


async def _render_screen(target: Message | CallbackQuery, state: FSMContext, text: str, reply_markup=None):
    if isinstance(target, CallbackQuery):
        await _edit_screen(target, state, text, reply_markup=reply_markup)
    else:
        # For Message, we usually send a new one and clear previous
        data = await state.get_data()
        prev = data.get("flow_message_id")
        bot = target.bot
        chat_id = target.chat.id
        await _safe_remove_markup(bot, chat_id, prev)
        sent = await target.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        await _remember_screen(state, sent.message_id)


def _fmt_money(value: int, currency: str = "KZT") -> str:
    from app.domain.money import fmt_money_compact
    return fmt_money_compact(value, currency)


def _is_cancel(text: str | None) -> bool:
    return is_cancel_text(text)


def _chat_and_bot(target: Message | CallbackQuery):
    if isinstance(target, CallbackQuery):
        return target.bot, target.message.chat.id
    return target.bot, target.chat.id


async def _safe_delete_message(bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=int(message_id))
    except Exception:
        pass


async def _safe_remove_markup(bot, chat_id: int, message_id: int | None) -> None:
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


async def _clear_prompt(target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    prompt_message_id = data.get("prompt_message_id")
    bot, chat_id = _chat_and_bot(target)

    await _safe_delete_message(bot, chat_id, prompt_message_id)
    await state.update_data(prompt_message_id=None)


async def _collapse_settings_ui(target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")
    prompt_message_id = data.get("prompt_message_id")
    settings_reply_message_id = data.get("settings_reply_message_id")
    bot, chat_id = _chat_and_bot(target)

    await _safe_delete_message(bot, chat_id, prompt_message_id)
    await _safe_delete_message(bot, chat_id, settings_reply_message_id)
    await _safe_delete_message(bot, chat_id, flow_message_id)
    await state.update_data(prompt_message_id=None, flow_message_id=None, settings_reply_message_id=None, extra_prompt_message_ids=[])


async def _start_settings_session(state: FSMContext) -> None:
    await state.update_data(ui_scope=SETTINGS_SCOPE)


async def _ensure_settings_reply_keyboard(target: Message | CallbackQuery, state: FSMContext, lang: str) -> None:
    data = await state.get_data()
    if data.get("settings_reply_message_id"):
        return
    sender = target.message.answer if isinstance(target, CallbackQuery) else target.answer
    txt = {
        "ru": "Режим настроек открыт.",
        "en": "Settings mode is open.",
        "kk": "Баптау режимі ашық.",
    }.get(lang, "Режим настроек открыт.")
    sent = await sender(txt, reply_markup=cancel_kb(lang), disable_notification=True)
    extra_ids = data.get("extra_prompt_message_ids") or []
    if not isinstance(extra_ids, list):
        extra_ids = [extra_ids]
    extra_ids = [x for x in extra_ids if x]
    extra_ids.append(sent.message_id)
    await state.update_data(settings_reply_message_id=sent.message_id, extra_prompt_message_ids=extra_ids)


async def _cancel_settings_flow(m: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    await cancel_to_main_menu(m, state, db)


async def _render_screen(
    target: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    *,
    reply_markup=None,
) -> None:
    await _start_settings_session(state)
    data = await state.get_data()
    flow_message_id = data.get("flow_message_id")
    bot, chat_id = _chat_and_bot(target)

    if flow_message_id:
        await _safe_delete_message(bot, chat_id, flow_message_id)

    if isinstance(target, CallbackQuery):
        sent = await target.message.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    else:
        sent = await target.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)

    await state.update_data(flow_message_id=sent.message_id)
    lang = (await state.get_data()).get("lang") or "ru"
    await _ensure_settings_reply_keyboard(target, state, lang)


# =========================================================
# Screen texts
# =========================================================

async def _settings_root_text(db: aiosqlite.Connection, user_id: int, lang: str) -> str:
    daily_enabled, daily_time, nudge_enabled, nudge_interval_min = await get_notification_settings(db, user_id)

    lines = [
        _s(lang, "root"),
        "",
        (_s(lang, "daily_on") if int(daily_enabled or 0) == 1 else _s(lang, "daily_off")),
        (_s(lang, "nudge_on") if int(nudge_enabled or 0) == 1 else _s(lang, "nudge_off")),
    ]

    if int(daily_enabled or 0) == 1:
        lines[-2] = {
            "ru": f"📅 Ежедневный отчёт: <b>включён</b> · {daily_time or '21:00'}",
            "en": f"📅 Daily report: <b>enabled</b> · {daily_time or '21:00'}",
            "kk": f"📅 Күндік есеп: <b>қосулы</b> · {daily_time or '21:00'}",
        }.get(lang, f"📅 Ежедневный отчёт: <b>включён</b> · {daily_time or '21:00'}")
    else:
        lines[-2] = {
            "ru": "📅 Ежедневный отчёт: <b>выключен</b>",
            "en": "📅 Daily report: <b>disabled</b>",
            "kk": "📅 Күндік есеп: <b>өшірулі</b>",
        }.get(lang, "📅 Ежедневный отчёт: <b>выключен</b>")

    hours = int(nudge_interval_min or 180) // 60
    if int(nudge_enabled or 0) == 1:
        lines[-1] = {
            "ru": f"🔁 Напоминания: <b>включены</b> · каждые {hours} ч",
            "en": f"🔁 Nudges: <b>enabled</b> · every {hours} h",
            "kk": f"🔁 Еске салғыштар: <b>қосулы</b> · әр {hours} сағ",
        }.get(lang, f"🔁 Напоминания: <b>включены</b> · каждые {hours} ч")
    else:
        lines[-1] = {
            "ru": "🔁 Напоминания: <b>выключены</b>",
            "en": "🔁 Nudges: <b>disabled</b>",
            "kk": "🔁 Еске салғыштар: <b>өшірулі</b>",
        }.get(lang, "🔁 Напоминания: <b>выключены</b>")

    lines.extend(["", {
        "ru": "Ниже — основные разделы настроек.",
        "en": "Main settings sections are below.",
        "kk": "Төменде баптаулардың негізгі бөлімдері бар.",
    }.get(lang, "Ниже — основные разделы настроек.")])
    return "\n".join(lines)


def _empty_notifs_text(lang: str) -> str:
    return _s(lang, "empty_notifs")


def _notifs_text(lang: str, daily_enabled: int, daily_time: str, nudge_enabled: int, nudge_interval_min: int, inc_enabled: int, inc_days: int, exp_enabled: int, exp_days: int) -> str:
    daily_status = _s(lang, "daily_on") if int(daily_enabled or 0) == 1 else _s(lang, "daily_off")
    nudge_status = _s(lang, "nudge_on") if int(nudge_enabled or 0) == 1 else _s(lang, "nudge_off")
    interval_hours = int(nudge_interval_min or 180) // 60
    
    def _days_label(enabled, days, l):
        if not enabled:
            return "❌ " + ("Disabled" if l=="en" else ("Өшірулі" if l=="kk" else "Выключены"))
        if days == 0:
            return "🎯 " + ("Today" if l=="en" else ("Бүгін" if l=="kk" else "День в день"))
        return f"⏳ {days} " + ("d." if l=="en" else ("күн" if l=="kk" else "дн."))

    inc_status = _days_label(inc_enabled, inc_days, lang)
    exp_status = _days_label(exp_enabled, exp_days, lang)

    return _s(lang, "notifs_tpl", daily=daily_status, time=(daily_time or '21:00'), nudge=nudge_status, hours=interval_hours, inc=inc_status, exp=exp_status)


# =========================================================
# Root screens
# =========================================================

async def _go_settings_root(target: Message | CallbackQuery, state: FSMContext, db: aiosqlite.Connection | None = None) -> None:
    await neutralize_keyboard(target)
    await _start_settings_session(state)
    await _clear_prompt(target, state)
    await state.set_state(None)
    await state.update_data(settings_return_to="settings_root")

    await _render_screen(
        target,
        state,
        await _settings_root_text(db, target.from_user.id, await get_lang(db, target.from_user.id) if db else "ru"),
        reply_markup=settings_kb(await get_lang(db, target.from_user.id) if db else "ru"),
    )

async def _accounts_overview_text(db: aiosqlite.Connection, user_id: int, lang: str) -> str:
    active = await list_accounts(db, user_id)
    all_rows = await list_accounts(db, user_id, include_archived=True)
    archived_count = max(0, len(all_rows) - len(active))

    # Calculate totals per currency for regular accounts
    currency_totals = {}
    for r in active:
        # r[2] = balance, r[4] = currency, r[5] = is_saving
        if not r[5]:
            curr = r[4] or "KZT"
            currency_totals[curr] = currency_totals.get(curr, 0) + int(r[2] or 0)
    
    if not currency_totals:
        fmt_total = _fmt_money(0, "KZT")
    else:
        fmt_total = ", ".join([_fmt_money(val, curr) for curr, val in currency_totals.items()])

    lines = [
        _s(lang, "accounts_title"),
        "",
        _s(lang, "total", value=fmt_total),
        _s(lang, "active", value=len(active)),
    ]

    if archived_count:
        lines.append(_s(lang, "archived", value=archived_count))

    lines.append("")

    if not active:
        lines.append(_s(lang, "no_accounts1"))
        lines.append(_s(lang, "no_accounts2"))
        return "\n".join(lines)

    lines.append(_s(lang, "current"))
    for idx, row in enumerate(active, start=1):
        # row: (id, name, balance, is_archived, currency, is_saving)
        name, balance, currency, is_saving = row[1], row[2], row[4], row[5]
        icon = "🎯" if is_saving else "💳"
        lines.append(f"{idx}. {icon} {escape(str(name))} — <b>{_fmt_money(int(balance or 0), currency)}</b>")

    # Richest regular account
    regular = [r for r in active if not r[5]]
    if regular:
        richest = max(regular, key=lambda row: int(row[2] or 0))
        lines.append("")
        label = {"ru": "💡 Самый крупный счёт", "en": "💡 Largest account", "kk": "💡 Ең үлкен шот"}.get(lang, "💡 Самый крупный счёт")
        lines.append(f"{label}: <b>{escape(str(richest[1]))}</b> — <b>{_fmt_money(int(richest[2] or 0), richest[4])}</b>")
    
    lines.append(_s(lang, "below"))
    return "\n".join(lines)




async def _archived_accounts_text(db: aiosqlite.Connection, user_id: int, lang: str) -> str:
    archived = await list_archived_accounts(db, user_id)
    title = {
        "ru": "🗄 <b>Архив счетов</b>",
        "en": "🗄 <b>Archived accounts</b>",
        "kk": "🗄 <b>Шоттар архиві</b>",
    }.get(lang, "🗄 <b>Архив счетов</b>")
    if not archived:
        empty = {
            "ru": "В архиве пока пусто.",
            "en": "Archive is empty for now.",
            "kk": "Архив әзірге бос.",
        }.get(lang, "В архиве пока пусто.")
        return f"{title}\n\n{empty}"

    lines = [title, "", _s(lang, "archived", value=len(archived)), ""]
    for idx, row in enumerate(archived, start=1):
        # row: (id, name, balance, is_archived, currency, is_saving)
        name, balance, currency = row[1], row[2], row[4]
        lines.append(f"{idx}. {escape(str(name))} — <b>{_fmt_money(int(balance or 0), currency)}</b>")
    lines.append("")
    lines.append({
        "ru": "Выбери счёт, чтобы восстановить или удалить его навсегда.",
        "en": "Choose an account to restore it or delete it forever.",
        "kk": "Қалпына келтіру немесе біржола жою үшін шотты таңдаңыз.",
    }.get(lang, "Выбери счёт, чтобы восстановить или удалить его навсегда."))
    return "\n".join(lines)




async def _account_card_text(db: aiosqlite.Connection, user_id: int, account_id: int, lang: str) -> str:
    acc = await get_account(db, user_id, account_id)
    if not acc:
        return {
            "ru": "💳 <b>Счёт не найден</b>",
            "en": "💳 <b>Account not found</b>",
            "kk": "💳 <b>Шот табылмады</b>",
        }.get(lang, "💳 <b>Счёт не найден</b>")

    _acc_id, name, balance, is_archived, currency, is_saving = acc
    status = {
        "ru": "активный" if int(is_archived or 0) == 0 else "в архиве",
        "en": "active" if int(is_archived or 0) == 0 else "archived",
        "kk": "белсенді" if int(is_archived or 0) == 0 else "архивте",
    }.get(lang, "активный")
    
    type_label = {
        "ru": "💰 Обычный" if not is_saving else "🎯 Копилка",
        "en": "💰 Regular" if not is_saving else "🎯 Savings",
        "kk": "💰 Қалыпты" if not is_saving else "🎯 Копилка",
    }.get(lang)

    lines = [
        f"💳 <b>{escape(str(name))}</b>",
        "",
        ({"ru": "💰 Баланс", "en": "💰 Balance", "kk": "💰 Баланс"}.get(lang, "💰 Баланс")) + f": <b>{_fmt_money(int(balance or 0), currency)}</b>",
        ({"ru": "💱 Валюта", "en": "💱 Currency", "kk": "💱 Валюта"}.get(lang, "💱 Валюта")) + f": <b>{currency}</b>",
        ({"ru": "📌 Тип", "en": "📌 Type", "kk": "📌 Түрі"}.get(lang, "📌 Тип")) + f": <b>{type_label}</b>",
        ({"ru": "⚙️ Статус", "en": "⚙️ Status", "kk": "⚙️ Күйі"}.get(lang, "⚙️ Статус")) + f": <b>{status}</b>",
        "",
        {
            "ru": "Здесь можно переименовать счёт, поправить баланс, изменить его тип или валюту.",
            "en": "Here you can rename the account, adjust its balance, change its type or currency.",
            "kk": "Мұнда шот атауын өзгертуге, балансын түзетуге, түрін немесе валютасын өзгертуге болады.",
        }.get(lang),
    ]
    return "\n".join(lines)


def _account_archive_confirm_text(name: str, balance: int, lang: str) -> str:
    return {
        "ru": f"🗂 <b>Архивировать счёт</b>\n\nСчёт: <b>{escape(str(name))}</b>\nБаланс: <b>{_fmt_money(int(balance or 0))}</b>\n\nСчёт исчезнет из активных, но останется в архиве и его можно будет восстановить.",
        "en": f"🗂 <b>Archive account</b>\n\nAccount: <b>{escape(str(name))}</b>\nBalance: <b>{_fmt_money(int(balance or 0))}</b>\n\nThe account will disappear from active ones, but it will remain in archive and can be restored.",
        "kk": f"🗂 <b>Шотты архивке жіберу</b>\n\nШот: <b>{escape(str(name))}</b>\nБаланс: <b>{_fmt_money(int(balance or 0))}</b>\n\nШот белсенді тізімнен жоғалады, бірақ архивте қалады және оны қайта қалпына келтіруге болады.",
    }.get(lang, "")


def _account_archive_confirm_kb(account_id: int, lang: str):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    yes = {"ru": "✅ Архивировать", "en": "✅ Archive", "kk": "✅ Архивке жіберу"}.get(lang, "✅ Archive")
    back = {"ru": "⬅️ Назад к счёту", "en": "⬅️ Back to account", "kk": "⬅️ Шотқа оралу"}.get(lang, "⬅️ Back to account")
    kb.button(text=yes, callback_data=f"st:acc:view:archive:confirm:{account_id}")
    kb.button(text=back, callback_data=f"st:acc:card:{account_id}")
    kb.adjust(1)
    return kb.as_markup()

async def _go_archived_accounts_menu(
    target: Message | CallbackQuery,
    state: FSMContext,
    db: aiosqlite.Connection,
) -> None:
    await _start_settings_session(state)
    await _clear_prompt(target, state)
    await state.set_state(None)
    await state.update_data(settings_return_to="accounts_menu")

    lang = await get_lang(db, target.from_user.id)
    accs = await list_archived_accounts(db, target.from_user.id)
    text = await _archived_accounts_text(db, target.from_user.id, lang)
    await _render_screen(target, state, text, reply_markup=archived_accounts_kb(accs, "st:acc:archived:pick", lang))

async def _go_accounts_menu(
    target: Message | CallbackQuery,
    state: FSMContext,
    db: aiosqlite.Connection,
) -> None:
    await _start_settings_session(state)
    await _clear_prompt(target, state)
    await state.set_state(None)
    await state.update_data(settings_return_to="accounts_menu")

    lang = await get_lang(db, target.from_user.id)
    text = await _accounts_overview_text(db, target.from_user.id, lang)
    lang = await get_lang(db, target.from_user.id)
    await _render_screen(target, state, text, reply_markup=settings_accounts_kb(lang))


async def _go_notifs_menu(
    target: Message | CallbackQuery,
    state: FSMContext,
    db: aiosqlite.Connection,
) -> None:
    await _start_settings_session(state)
    await _clear_prompt(target, state)

    row = await get_notification_settings(db, target.from_user.id)
    rec_row = await get_recurring_settings(db, target.from_user.id)
    
    if not row:
        await state.set_state(None)
        await state.update_data(settings_return_to="settings_root")
        lang = await get_lang(db, target.from_user.id)
        await _render_screen(target, state, _empty_notifs_text(lang), reply_markup=settings_kb(lang))
        return

    daily_enabled, daily_time, nudge_enabled, nudge_interval = row
    inc_enabled, inc_days, exp_enabled, exp_days = rec_row

    await state.set_state(None)
    await state.update_data(settings_return_to="notifs_menu")
    lang = await get_lang(db, target.from_user.id)
    await _render_screen(
        target,
        state,
        _notifs_text(lang, daily_enabled, daily_time, nudge_enabled, nudge_interval, inc_enabled, inc_days, exp_enabled, exp_days),
        reply_markup=notifications_kb(
            daily_enabled,
            daily_time,
            nudge_enabled,
            nudge_interval,
            inc_enabled,
            inc_days,
            exp_enabled,
            exp_days,
            lang,
        ),
    )


# =========================================================
# Input / finish helpers
# =========================================================

async def _show_input_prompt(
    target: Message | CallbackQuery,
    state: FSMContext,
    text: str,
) -> None:
    await _start_settings_session(state)
    await _clear_prompt(target, state)

    data = await state.get_data()
    reply_markup = None if data.get("settings_reply_message_id") else cancel_kb((data.get("lang") or "ru"))
    sent = await (
        target.message.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        if isinstance(target, CallbackQuery)
        else target.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    )
    await state.update_data(prompt_message_id=sent.message_id)


async def _enter_input_mode(
    c: CallbackQuery,
    state: FSMContext,
    *,
    screen_text: str,
    prompt_text: str,
    next_state,
    return_to: str,
    extra_data: dict | None = None,
) -> None:
    payload = {"settings_return_to": return_to, "ui_scope": SETTINGS_SCOPE, "lang": (await state.get_data()).get("lang", "ru")}
    if extra_data:
        payload.update(extra_data)

    await state.update_data(**payload)
    await state.set_state(next_state)

    await _clear_prompt(c, state)
    await _safe_remove_markup(c.bot, c.message.chat.id, c.message.message_id)
    screen = await c.message.answer(screen_text, parse_mode=PARSE_MODE)
    await state.update_data(flow_message_id=screen.message_id)
    await _show_input_prompt(c, state, prompt_text)
    await c.answer()
    lang = (await state.get_data()).get("lang", "ru")
    await _ensure_settings_reply_keyboard(c, state, lang)


def _add_account_balance_actions_kb(lang: str):
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    kb = InlineKeyboardBuilder()
    kb.button(text=_s(lang, "acc_add_back_name"), callback_data="st:acc:add:back_name")
    kb.adjust(1)
    return kb.as_markup()


async def _return_after_success(
    target: Message | CallbackQuery,
    state: FSMContext,
    db: aiosqlite.Connection,
) -> None:
    data = await state.get_data()
    return_to = data.get("settings_return_to")
    acc_id = data.get("acc_id")

    if return_to == "notifs_menu":
        await _go_notifs_menu(target, state, db)
        return

    if return_to == "account_card" and acc_id:
        lang = await get_lang(db, target.from_user.id)
        acc = await get_account(db, target.from_user.id, int(acc_id))
        if acc and int(acc[3] or 0) == 0:
            await state.set_state(None)
            await state.update_data(settings_return_to="account_card", ui_scope=SETTINGS_SCOPE, acc_id=int(acc_id))
            await _render_screen(
                target,
                state,
                await _account_card_text(db, target.from_user.id, int(acc_id), lang),
                reply_markup=account_actions_kb(int(acc_id), lang),
            )
            return

    await _go_accounts_menu(target, state, db)


async def _finish_to_menu(
    ctx: Message | CallbackQuery,
    state: FSMContext,
    text: str,
    db: aiosqlite.Connection | None = None,
) -> None:
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await _collapse_settings_ui(ctx, state)
    await state.clear()

    if isinstance(ctx, CallbackQuery):
        await ctx.message.answer(text, reply_markup=await build_main_menu_markup(db, ctx.from_user.id, lang), parse_mode=PARSE_MODE)
        await ctx.answer()
        return

    await ctx.answer(text, reply_markup=await build_main_menu_markup(db, ctx.from_user.id, lang), parse_mode=PARSE_MODE)


# =========================================================
# Entry / global cancel
# =========================================================

@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_ACCOUNTS"))
async def accounts_entry(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await _collapse_settings_ui(m, state)
    await state.clear()

    try:
        await m.delete()
    except Exception:
        pass

    lang = await get_lang(db, m.from_user.id)
    await state.update_data(lang=lang)
    await _go_accounts_menu(m, state, db)


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_SETTINGS"))
async def settings_entry(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await _collapse_settings_ui(m, state)
    await state.clear()

    try:
        await m.delete()
    except Exception:
        pass

    lang = await get_lang(db, m.from_user.id)
    await state.update_data(lang=lang)
    await _go_settings_root(m, state, db)


# =========================================================
# Navigation
# =========================================================

@router.callback_query(F.data == "st:back")
async def st_back(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    data = await state.get_data()
    return_to = data.get("settings_return_to")

    if return_to == "accounts_menu":
        await _go_accounts_menu(c, state, db)
    elif return_to == "notifs_menu":
        await _go_notifs_menu(c, state, db)
    else:
        await _go_settings_root(c, state, db)

    await c.answer()


@router.callback_query(F.data == "st:root")
async def st_root(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    await _go_settings_root(c, state, db)
    await c.answer()


@router.callback_query(F.data == "st:close")
async def st_close(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _finish_to_menu(c, state, _s(await get_lang(db, c.from_user.id), "done"), db)


@router.callback_query(F.data == "st:accounts")
async def st_accounts(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    await _go_accounts_menu(c, state, db)
    await c.answer()




@router.callback_query(F.data.startswith("st:acc:view:archive:"))
async def st_acc_view_archive(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    parts = c.data.split(":")
    if len(parts) != 5:
        await c.answer()
        return
    acc_id = int(parts[-1])
    lang = await get_lang(db, c.from_user.id)
    acc = await get_account(db, c.from_user.id, acc_id)
    if not acc or int(acc[3] or 0) == 1:
        await _go_accounts_menu(c, state, db)
        await c.answer({"ru": "Счёт не найден", "en": "Account not found", "kk": "Шот табылмады"}.get(lang), show_alert=True)
        return
    await state.set_state(None)
    await state.update_data(settings_return_to="account_card", acc_id=acc_id, ui_scope=SETTINGS_SCOPE)
    await _render_screen(c, state, _account_archive_confirm_text(acc[1], int(acc[2] or 0), lang), reply_markup=_account_archive_confirm_kb(acc_id, lang))
    await c.answer()


@router.callback_query(F.data.startswith("st:acc:view:archive:confirm:"))
async def st_acc_view_archive_confirm(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    acc_id = int(c.data.split(":")[-1])
    lang = await get_lang(db, c.from_user.id)
    acc = await get_account(db, c.from_user.id, acc_id)
    if not acc or int(acc[3] or 0) == 1:
        await _go_accounts_menu(c, state, db)
        await c.answer({"ru": "Счёт не найден", "en": "Account not found", "kk": "Шот табылмады"}.get(lang), show_alert=True)
        return
    try:
        await archive_account(db, c.from_user.id, acc_id, now_iso())
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await _go_accounts_menu(c, state, db)
    await c.message.answer(_s(lang, "archived_ok"), parse_mode=PARSE_MODE)
    await c.answer()

@router.callback_query(F.data == "st:acc:archived")
async def st_accounts_archived(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _go_archived_accounts_menu(c, state, db)
    await c.answer()


@router.callback_query(F.data == "st:budgets")
async def st_budgets(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    await _start_settings_session(state)
    await _clear_prompt(c, state)
    await state.update_data(flow_message_id=c.message.message_id, settings_return_to="settings_root")
    await show_budget_categories(c, state, db)
    await c.answer()


@router.callback_query(F.data == "st:notifs")
async def st_notifs(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _go_notifs_menu(c, state, db)
    await c.answer()


@router.callback_query(F.data == "st:notifs:menu")
async def st_notifs_menu(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _go_notifs_menu(c, state, db)
    await c.answer()


@router.callback_query(F.data == "st:lang")
async def st_lang(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    await _start_settings_session(state)
    await _clear_prompt(c, state)
    await state.set_state(None)
    await state.update_data(settings_return_to="settings_root")
    await _render_screen(c, state, t(lang, "LANG_SCREEN"), reply_markup=lang_kb(back_cb="st:root", lang=lang))
    await c.answer()


# =========================================================
# Accounts flow
# =========================================================



@router.callback_query(F.data == "st:acc:open")
async def st_acc_open(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    accs = await list_accounts(db, c.from_user.id)
    if not accs:
        await _go_accounts_menu(c, state, db)
        await c.answer(_s(await get_lang(db, c.from_user.id), "no_accounts_alert"), show_alert=True)
        return

    lang = await get_lang(db, c.from_user.id)
    await _clear_prompt(c, state)
    await state.set_state(None)
    await state.update_data(settings_return_to="accounts_menu", ui_scope=SETTINGS_SCOPE)
    text = {
        "ru": "📂 <b>Карточка счёта</b>\n\nВыбери счёт, чтобы открыть его карточку.",
        "en": "📂 <b>Account card</b>\n\nChoose an account to open its card.",
        "kk": "📂 <b>Шот картасы</b>\n\nКартасын ашу үшін шотты таңдаңыз.",
    }.get(lang)
    await _render_screen(c, state, text, reply_markup=active_accounts_kb(accs, "st:acc:card", lang, back_cb="st:accounts"))
    await c.answer()


@router.callback_query(F.data.startswith("st:acc:card:"))
async def st_acc_view(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    parts = c.data.split(":")
    if len(parts) != 4:
        await c.answer()
        return
    acc_id = int(parts[-1])
    lang = await get_lang(db, c.from_user.id)
    acc = await get_account(db, c.from_user.id, acc_id)
    if not acc or int(acc[3] or 0) == 1:
        await _go_accounts_menu(c, state, db)
        await c.answer({
            "ru": "Счёт не найден",
            "en": "Account not found",
            "kk": "Шот табылмады",
        }.get(lang), show_alert=True)
        return
    await state.update_data(settings_return_to="account_card", acc_id=acc_id, ui_scope=SETTINGS_SCOPE)
    await _render_screen(c, state, await _account_card_text(db, c.from_user.id, acc_id, lang), reply_markup=account_actions_kb(acc_id, lang))
    await c.answer()


@router.callback_query(F.data.startswith("st:acc:view:rename:"))
async def st_acc_view_rename(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    acc_id = int(c.data.split(":")[-1])
    lang = await get_lang(db, c.from_user.id)
    await _enter_input_mode(
        c,
        state,
        screen_text=_s(lang, "rename_new"),
        prompt_text=_s(lang, "example_cash"),
        next_state=SettingsFlow.rename_new,
        return_to="account_card",
        extra_data={"acc_id": acc_id, "lang": lang},
    )


@router.callback_query(F.data == "st:acc:balance")
async def st_acc_balance(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    accs = await list_accounts(db, c.from_user.id)
    if not accs:
        await _go_accounts_menu(c, state, db)
        await c.answer(_s(await get_lang(db, c.from_user.id), "no_accounts_alert"), show_alert=True)
        return

    lang = await get_lang(db, c.from_user.id)
    await _clear_prompt(c, state)
    await state.set_state(SettingsFlow.balance_pick)
    await state.update_data(settings_return_to="accounts_menu", ui_scope=SETTINGS_SCOPE)
    text = {
        "ru": "💰 <b>Изменение баланса</b>\n\nВыбери счёт, баланс которого нужно поправить.",
        "en": "💰 <b>Edit balance</b>\n\nChoose the account whose balance you want to adjust.",
        "kk": "💰 <b>Балансты өзгерту</b>\n\nБалансын түзететін шотты таңдаңыз.",
    }.get(lang)
    await _render_screen(c, state, text, reply_markup=active_accounts_kb(accs, "balacc", lang))
    await c.answer()


@router.callback_query(F.data.startswith("st:acc:view:balance:"))
async def st_acc_view_balance(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    acc_id = int(c.data.split(":")[-1])
    acc = await get_account(db, c.from_user.id, acc_id)
    lang = await get_lang(db, c.from_user.id)
    if not acc:
        await _go_accounts_menu(c, state, db)
        await c.answer()
        return
    await _enter_input_mode(
        c,
        state,
        screen_text={
            "ru": f"💰 <b>Новый баланс</b>\n\nСчёт: <b>{escape(str(acc[1]))}</b>\nТекущий баланс: <b>{_fmt_money(int(acc[2] or 0))}</b>",
            "en": f"💰 <b>New balance</b>\n\nAccount: <b>{escape(str(acc[1]))}</b>\nCurrent balance: <b>{_fmt_money(int(acc[2] or 0))}</b>",
            "kk": f"💰 <b>Жаңа баланс</b>\n\nШот: <b>{escape(str(acc[1]))}</b>\nАғымдағы баланс: <b>{_fmt_money(int(acc[2] or 0))}</b>",
        }.get(lang),
        prompt_text={
            "ru": "Пример: <code>15000</code> или <code>-5000</code>",
            "en": "Example: <code>15000</code> or <code>-5000</code>",
            "kk": "Мысал: <code>15000</code> немесе <code>-5000</code>",
        }.get(lang),
        next_state=SettingsFlow.balance_new,
        return_to="account_card",
        extra_data={"acc_id": acc_id, "lang": lang},
    )


@router.callback_query(SettingsFlow.balance_pick, F.data.startswith("balacc:"))
async def st_acc_balance_pick(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    acc_id = int(c.data.split(":")[1])
    acc = await get_account(db, c.from_user.id, acc_id)
    lang = await get_lang(db, c.from_user.id)
    if not acc:
        await _go_accounts_menu(c, state, db)
        await c.answer()
        return
    await _enter_input_mode(
        c,
        state,
        screen_text={
            "ru": f"💰 <b>Новый баланс</b>\n\nСчёт: <b>{escape(str(acc[1]))}</b>\nТекущий баланс: <b>{_fmt_money(int(acc[2] or 0))}</b>",
            "en": f"💰 <b>New balance</b>\n\nAccount: <b>{escape(str(acc[1]))}</b>\nCurrent balance: <b>{_fmt_money(int(acc[2] or 0))}</b>",
            "kk": f"💰 <b>Жаңа баланс</b>\n\nШот: <b>{escape(str(acc[1]))}</b>\nАғымдағы баланс: <b>{_fmt_money(int(acc[2] or 0))}</b>",
        }.get(lang),
        prompt_text={
            "ru": "Пример: <code>15000</code> или <code>-5000</code>",
            "en": "Example: <code>15000</code> or <code>-5000</code>",
            "kk": "Мысал: <code>15000</code> немесе <code>-5000</code>",
        }.get(lang),
        next_state=SettingsFlow.balance_new,
        return_to="accounts_menu",
        extra_data={"acc_id": acc_id},
    )

@router.callback_query(F.data == "st:acc:add")
async def st_acc_add(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    lang = await get_lang(db, c.from_user.id)
    await _enter_input_mode(
        c,
        state,
        screen_text=_s(lang, "new_acc"),
        prompt_text=_s(lang, "example_kaspi"),
        next_state=SettingsFlow.add_name,
        return_to="accounts_menu",
        extra_data={"lang": lang},
    )


@router.message(SettingsFlow.add_name, F.text)
async def st_acc_add_name(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await consume_user_input(m, state)
    if _is_cancel(m.text):
        await _cancel_settings_flow(m, state, db)
        return

    lang = (await state.get_data()).get("lang", "ru")
    name = clean_name(m.text)
    if not name:
        await m.answer(_s(lang, "name_len"), parse_mode=PARSE_MODE)
        return

    await state.update_data(add_name=name)
    await state.set_state(SettingsFlow.add_balance)

    header = _s(lang, "acc_add_name_saved", name=escape(name))
    body = _s(lang, "balance_prompt")
    hint = _s(lang, "acc_add_balance_hint")
    text = f"{header}\n\n{body}\n\n<i>{hint}</i>"
    await _render_screen(m, state, text, reply_markup=_add_account_balance_actions_kb(lang))
    data = await state.get_data()
    await state.update_data(prompt_message_id=data.get("flow_message_id"))


@router.callback_query(SettingsFlow.add_balance, F.data == "st:acc:add:back_name")
async def st_acc_add_back_name(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    chat_id = c.message.chat.id
    await state.update_data(add_name=None)
    await state.set_state(SettingsFlow.add_name)
    await _clear_prompt(c, state)
    try:
        await c.message.delete()
    except Exception:
        pass
    await state.update_data(flow_message_id=None, prompt_message_id=None)
    await state.update_data(settings_return_to="accounts_menu", ui_scope=SETTINGS_SCOPE, lang=lang)
    screen = await c.bot.send_message(chat_id, _s(lang, "new_acc"), parse_mode=PARSE_MODE)
    await state.update_data(flow_message_id=screen.message_id)
    prompt = await c.bot.send_message(chat_id, _s(lang, "example_kaspi"), parse_mode=PARSE_MODE)
    await state.update_data(prompt_message_id=prompt.message_id)
    await _ensure_settings_reply_keyboard(c, state, lang)
    await c.answer()


@router.message(SettingsFlow.add_balance, F.text)
async def st_acc_add_balance(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await consume_user_input(m, state)
    if _is_cancel(m.text):
        await _cancel_settings_flow(m, state, db)
        return

    lang = (await state.get_data()).get("lang", "ru")
    from app.domain.money import parse_money_for_user, get_user_currency

    raw_norm = (m.text or "").strip().replace(" ", "").replace(",", ".")
    if raw_norm in {"0", "0.0", "0.00"}:
        balance = 0
    else:
        bal = await parse_money_for_user(db, m.from_user.id, m.text, max_minor=99_999_999_00)
        if bal is None:
            await m.answer(
                f"{t(lang, 'AMOUNT_INVALID')}\n\n<i>{_s(lang, 'acc_add_balance_hint')}</i>",
                parse_mode=PARSE_MODE,
            )
            return
        balance = bal

    data = await state.get_data()
    name = data.get("add_name")
    if not name:
        await cancel_to_main_menu(m, state, db)
        return

    await state.update_data(add_balance=balance)
    await state.set_state(SettingsFlow.add_currency)

    currency_u = await get_user_currency(db, m.from_user.id)
    amount_label = _fmt_money(int(balance), currency_u)
    header = _s(lang, "acc_add_balance_saved", amount=amount_label)
    cur_title = {
        "ru": "💱 <b>Выбери валюту счёта</b>",
        "en": "💱 <b>Choose account currency</b>",
        "kk": "💱 <b>Шот валютасын таңдаңыз</b>",
    }.get(lang, "💱 <b>Выбери валюту счёта</b>")
    text = f"{header}\n\n{cur_title}"
    await _render_screen(m, state, text, reply_markup=account_currency_kb())


@router.callback_query(SettingsFlow.add_currency, F.data.startswith("acc:cur:"))
async def st_acc_add_currency(c: CallbackQuery, state: FSMContext):
    currency = c.data.split(":")[-1]
    await state.update_data(add_currency=currency)
    await state.set_state(SettingsFlow.add_type)
    
    lang = (await state.get_data()).get("lang", "ru")
    text = {
        "ru": "📌 <b>Тип счёта</b>\n\nОбычные счета учитываются в общем балансе. Копилки (сбережения) спрятаны из общего итога, чтобы вы видели только свободные деньги.",
        "en": "📌 <b>Account type</b>\n\nRegular accounts are included in total balance. Savings (goals) are hidden from total to show only free cash.",
        "kk": "📌 <b>Шот түрі</b>\n\nҚалыпты шоттар жалпы баланста ескеріледі. Копилкалар (жинақтар) бос ақшаны ғана көру үшін жалпы қорытындыдан жасырылған.",
    }.get(lang)
    
    await _render_screen(c, state, text, reply_markup=account_type_kb(lang))
    await c.answer()


@router.callback_query(SettingsFlow.add_type, F.data.startswith("acc:type:"))
async def st_acc_add_type(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    is_saving = 1 if c.data.split(":")[-1] == "saving" else 0
    data = await state.get_data()
    name = data.get("add_name")
    balance = data.get("add_balance")
    currency = data.get("add_currency")
    lang = data.get("lang", "ru")
    
    if not name or balance is None:
        await cancel_to_main_menu(c, state, db)
        return

    try:
        _account_id, action = await create_account(db, c.from_user.id, name, balance, now_iso(), currency=currency, is_saving=is_saving)
        await db.commit()
    except ValueError as e:
        await db.rollback()
        if str(e) == "active_name_exists":
            error_screen = {
                "ru": "⚠️ <b>Счёт с таким названием уже существует среди активных.</b>\n\nПожалуйста, введи другое, уникальное название для этого счёта.",
                "en": "⚠️ <b>An active account with this name already exists.</b>\n\nPlease enter a different, unique name for this account.",
                "kk": "⚠️ <b>Осындай атаумен белсенді шот бар.</b>\n\nБұл шот үшін басқа, бірегей атауды енгізіңіз.",
            }.get(lang, "⚠️ Счёт с таким названием уже существует.")
            await state.update_data(add_name=None)
            await _enter_input_mode(
                c,
                state,
                screen_text=error_screen,
                prompt_text=_s(lang, "example_kaspi"),
                next_state=SettingsFlow.add_name,
                return_to="accounts_menu",
            )
            return
        raise
    except Exception:
        await db.rollback()
        raise

    if action == "restored":
        msg = {
            "ru": "♻️ <b>Архивный счёт восстановлен</b>\n\nБот вернул существующий архивный счёт и обновил его параметры.",
            "en": "♻️ <b>Archived account restored</b>\n\nThe archived one was restored and its parameters updated.",
            "kk": "♻️ <b>Архивтегі шот қалпына келтірілді</b>\n\nАрхивтегі шот қайтарылып, параметрлері жаңартылды.",
        }.get(lang)
        await c.message.answer(msg, parse_mode=PARSE_MODE)

    await _return_after_success(c, state, db)
    await c.answer()


@router.callback_query(F.data == "st:acc:rename")
async def st_acc_rename(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    accs = await list_accounts(db, c.from_user.id)
    if not accs:
        await _go_accounts_menu(c, state, db)
        await c.answer(_s(await get_lang(db, c.from_user.id), "no_accounts_alert"), show_alert=True)
        return

    await _clear_prompt(c, state)
    await state.set_state(SettingsFlow.rename_pick)
    await state.update_data(settings_return_to="accounts_menu", ui_scope=SETTINGS_SCOPE)

    await _render_screen(
        c,
        state,
        "✏️ <b>Переименование счёта</b>\n\nВыбери счёт из списка.",
        reply_markup=accounts_kb(accs, "renacc"),
    )
    await c.answer()


@router.callback_query(SettingsFlow.rename_pick, F.data.startswith("renacc:"))
async def st_acc_rename_pick(c: CallbackQuery, state: FSMContext):
    acc_id = int(c.data.split(":")[1])

    await _enter_input_mode(
        c,
        state,
        screen_text="✏️ <b>Новое название счёта</b>\n\nВведи новое название.",
        prompt_text=_s((await state.get_data()).get("lang", "ru"), "example_cash"),
        next_state=SettingsFlow.rename_new,
        return_to="accounts_menu",
        extra_data={"acc_id": acc_id},
    )


@router.message(SettingsFlow.rename_new, F.text)
async def st_acc_rename_new(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await consume_user_input(m, state)
    if _is_cancel(m.text):
        await _cancel_settings_flow(m, state, db)
        return

    name = clean_name(m.text)
    if not name:
        await m.answer(_s((await state.get_data()).get("lang", "ru"), "name_len"), parse_mode=PARSE_MODE)
        return

    data = await state.get_data()
    acc_id = data.get("acc_id")
    if not acc_id:
        await cancel_to_main_menu(m, state, db)
        return

    try:
        await rename_account(db, m.from_user.id, int(acc_id), name, now_iso())
        await db.commit()
    except ValueError as e:
        await db.rollback()
        if str(e) == "active_name_exists":
            lang = (await state.get_data()).get("lang", "ru")
            msg = {
                "ru": "⚠️ <b>Активный счёт с таким названием уже существует.</b>\n\nВведи другое название для этого счёта:",
                "en": "⚠️ <b>An active account with this name already exists.</b>\n\nPlease enter a different name for this account:",
                "kk": "⚠️ <b>Осындай атаумен белсенді шот бар.</b>\n\nБұл шот үшін басқа атау енгізіңіз:",
            }.get(lang, "⚠️ Активный счёт с таким названием уже существует.")
            await m.answer(msg, parse_mode=PARSE_MODE)
            return
        raise
    except Exception:
        await db.rollback()
        raise

    await _return_after_success(m, state, db)




@router.message(SettingsFlow.balance_new, F.text)
async def st_acc_balance_new(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await consume_user_input(m, state)
    if _is_cancel(m.text):
        await _cancel_settings_flow(m, state, db)
        return

    raw = (m.text or "").strip().replace(" ", "")
    if not raw or raw in {"-", "+"}:
        await m.answer({
            "ru": "Нужно число. Пример: <code>15000</code> или <code>-5000</code>",
            "en": "Enter a number. Example: <code>15000</code> or <code>-5000</code>",
            "kk": "Сан енгізіңіз. Мысал: <code>15000</code> немесе <code>-5000</code>",
        }.get((await state.get_data()).get("lang", "ru")), parse_mode=PARSE_MODE)
        return
    sign = -1 if raw.startswith("-") else 1
    digits = raw[1:] if raw[:1] in "+-" else raw
    if not digits.isdigit():
        await m.answer({
            "ru": "Нужно число. Пример: <code>15000</code> или <code>-5000</code>",
            "en": "Enter a number. Example: <code>15000</code> or <code>-5000</code>",
            "kk": "Сан енгізіңіз. Мысал: <code>15000</code> немесе <code>-5000</code>",
        }.get((await state.get_data()).get("lang", "ru")), parse_mode=PARSE_MODE)
        return

    new_balance = sign * int(digits)
    data = await state.get_data()
    acc_id = data.get("acc_id")
    if not acc_id:
        await cancel_to_main_menu(m, state, db)
        return

    try:
        await set_account_balance(db, m.from_user.id, int(acc_id), int(new_balance), now_iso())
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await m.answer({
        "ru": "✅ <b>Баланс счёта обновлён</b>",
        "en": "✅ <b>Account balance updated</b>",
        "kk": "✅ <b>Шот балансы жаңартылды</b>",
    }.get((await state.get_data()).get("lang", "ru")), parse_mode=PARSE_MODE)
    await _return_after_success(m, state, db)

@router.callback_query(F.data == "st:acc:archive")
async def st_acc_archive(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    accs = await list_accounts(db, c.from_user.id)
    if not accs:
        await _go_accounts_menu(c, state, db)
        await c.answer(_s(await get_lang(db, c.from_user.id), "no_accounts_alert"), show_alert=True)
        return

    await _clear_prompt(c, state)
    await state.set_state(SettingsFlow.archive_pick)
    await state.update_data(settings_return_to="accounts_menu", ui_scope=SETTINGS_SCOPE)

    await _render_screen(
        c,
        state,
        "🗂 <b>Архивация счёта</b>\n\nВыбери счёт, который нужно убрать из активных.",
        reply_markup=accounts_kb(accs, "arcacc"),
    )
    await c.answer()


@router.callback_query(SettingsFlow.archive_pick, F.data.startswith("arcacc:"))
async def st_acc_archive_pick(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    acc_id = int(c.data.split(":")[1])
    lang = await get_lang(db, c.from_user.id)
    acc = await get_account(db, c.from_user.id, acc_id)
    if not acc or int(acc[3] or 0) == 1:
        await _go_accounts_menu(c, state, db)
        await c.answer({"ru": "Счёт не найден", "en": "Account not found", "kk": "Шот табылмады"}.get(lang), show_alert=True)
        return
    await state.set_state(None)
    await state.update_data(settings_return_to="accounts_menu", acc_id=acc_id, ui_scope=SETTINGS_SCOPE)
    await _render_screen(c, state, _account_archive_confirm_text(acc[1], int(acc[2] or 0), lang), reply_markup=_account_archive_confirm_kb(acc_id, lang))
    await c.answer()


@router.callback_query(F.data.startswith("st:acc:view:currency:"))
async def st_acc_view_currency_pick(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    acc_id = int(c.data.split(":")[-1])
    lang = await get_lang(db, c.from_user.id)
    
    # We use a special prefix for existing account currency change
    kb = InlineKeyboardBuilder()
    for cur in ["KZT", "USD", "RUB", "EUR"]:
        kb.button(text=f"{cur}", callback_data=f"st:acc:setcur:{acc_id}:{cur}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data=f"st:acc:card:{acc_id}")
    kb.adjust(2, 2, 1)
    
    text = {
        "ru": "💱 <b>Смена валюты счёта</b>\n\nВыбери новую валюту. Баланс останется прежним в цифрах, но поменяется обозначение.",
        "en": "💱 <b>Change account currency</b>\n\nSelect new currency. The numeric balance will remain the same, but the symbol will change.",
        "kk": "💱 <b>Валютаны өзгерту</b>\n\nЖаңа валютаны таңдаңыз.",
    }.get(lang)
    
    await _render_screen(c, state, text, reply_markup=kb.as_markup())
    await c.answer()


@router.callback_query(F.data.startswith("st:acc:setcur:"))
async def st_acc_view_currency_set(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    parts = c.data.split(":")
    acc_id = int(parts[3])
    currency = parts[4]
    
    await update_account_currency(db, c.from_user.id, acc_id, currency, now_iso())
    await db.commit()
    
    await state.update_data(acc_id=acc_id)
    await _return_after_success(c, state, db)
    await c.answer()


@router.callback_query(F.data.startswith("st:acc:view:type_toggle:"))
async def st_acc_view_type_toggle(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    acc_id = int(c.data.split(":")[-1])
    
    await toggle_account_saving(db, c.from_user.id, acc_id, now_iso())
    await db.commit()
    
    await state.update_data(acc_id=acc_id)
    # Using return_to account_card logic
    data = await state.get_data()
    await state.update_data(settings_return_to="account_card") 
    await _return_after_success(c, state, db)
    await c.answer()


@router.callback_query(F.data.startswith("st:acc:archived:pick:"))
async def st_acc_archived_pick(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    acc_id = int(c.data.split(":")[-1])
    acc = await get_account(db, c.from_user.id, acc_id)
    if not acc or int(acc[3] or 0) != 1:
        await _go_archived_accounts_menu(c, state, db)
        await c.answer()
        return

    lang = await get_lang(db, c.from_user.id)
    title = {
        "ru": f"🗄 <b>{escape(str(acc[1]))}</b>\n\nБаланс: <b>{_fmt_money(int(acc[2] or 0))}</b>\n\nВыбери действие.",
        "en": f"🗄 <b>{escape(str(acc[1]))}</b>\n\nBalance: <b>{_fmt_money(int(acc[2] or 0))}</b>\n\nChoose an action.",
        "kk": f"🗄 <b>{escape(str(acc[1]))}</b>\n\nБаланс: <b>{_fmt_money(int(acc[2] or 0))}</b>\n\nӘрекетті таңдаңыз.",
    }.get(lang)
    await _render_screen(c, state, title, reply_markup=archived_account_actions_kb(acc_id, lang))
    await c.answer()


@router.callback_query(F.data.startswith("st:acc:restore:"))
async def st_acc_restore(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    acc_id = int(c.data.split(":")[-1])
    try:
        await restore_account(db, c.from_user.id, acc_id, now_iso())
        await db.commit()
    except ValueError as e:
        await db.rollback()
        if str(e) == "active_name_exists":
            msg = {
                "ru": "Нельзя восстановить: среди активных уже есть счёт с таким названием.",
                "en": "Cannot restore: an active account with this name already exists.",
                "kk": "Қалпына келтіру мүмкін емес: осындай атаумен белсенді шот бар.",
            }.get(await get_lang(db, c.from_user.id))
            await c.answer(msg, show_alert=True)
            return
        raise

    lang = await get_lang(db, c.from_user.id)
    msg = {
        "ru": "♻️ <b>Счёт восстановлен</b>",
        "en": "♻️ <b>Account restored</b>",
        "kk": "♻️ <b>Шот қалпына келтірілді</b>",
    }.get(lang)
    await _go_accounts_menu(c, state, db)
    await c.message.answer(msg, parse_mode=PARSE_MODE)
    await c.answer()


@router.callback_query(F.data.startswith("st:acc:delete:"))
async def st_acc_delete(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await neutralize_keyboard(c)
    acc_id = int(c.data.split(":")[-1])
    lang = await get_lang(db, c.from_user.id)
    if await account_has_transactions(db, c.from_user.id, acc_id):
        msg = {
            "ru": "Нельзя удалить счёт навсегда, пока у него есть операции в истории.",
            "en": "You cannot delete this account forever while it has transactions in history.",
            "kk": "Тарихта операциялар бар кезде бұл шотты біржола жоюға болмайды.",
        }.get(lang)
        await c.answer(msg, show_alert=True)
        return

    try:
        await delete_account_permanently(db, c.from_user.id, acc_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    msg = {
        "ru": "🗑 <b>Счёт удалён навсегда</b>",
        "en": "🗑 <b>Account deleted forever</b>",
        "kk": "🗑 <b>Шот біржола жойылды</b>",
    }.get(lang)
    await _go_archived_accounts_menu(c, state, db)
    await c.message.answer(msg, parse_mode=PARSE_MODE)
    await c.answer()


# =========================================================
# Reset
# =========================================================

@router.callback_query(F.data.in_({"st:reset", "st:acc:reset"}))
async def reset_ask_confirm(c: CallbackQuery, state: FSMContext):
    await _clear_prompt(c, state)
    await state.set_state(None)
    await state.update_data(settings_return_to="settings_root", ui_scope=SETTINGS_SCOPE)

    await _render_screen(
        c,
        state,
        "⚠️ <b>Полный сброс профиля</b>\n\n"
        "Будет удалено всё, что связано с аккаунтом:\n"
        "• операции и история\n"
        "• счета\n"
        "• категории и лимиты\n"
        "• долги\n"
        "• планируемые операции\n"
        "• постоянные доходы и расходы\n"
        "• настройки\n"
        "• серия активности и прогресс\n"
        "• сам профиль пользователя\n\n"
        "После этого бот будет считать тебя новым пользователем.\n"
        "Действие необратимо.",
        reply_markup=reset_confirm_kb(),
    )
    await c.answer()


@router.callback_query(F.data == "st:reset:cancel")
async def reset_cancel(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    await _go_settings_root(c, state, db)
    await c.answer()


@router.callback_query(F.data == "st:reset:confirm")
async def reset_confirm(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    try:
        await wipe_user_data(db, c.from_user.id)
    except Exception:
        await db.rollback()
        raise

    await _finish_to_menu(
        c,
        state,
        "✅ <b>Сброс выполнен</b>\nТвой профиль и все финансовые данные удалены.\nЧтобы начать заново, отправь <code>/start</code>.",
    )


# =========================================================
# Notifications flow
# =========================================================

@router.callback_query(F.data == "st:notifs:daily:toggle")
async def st_notifs_daily_toggle(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    row = await get_notification_settings(db, c.from_user.id)
    if not row:
        await _go_notifs_menu(c, state, db)
        await c.answer()
        return

    daily_enabled, daily_time, _nudge_enabled, _nudge_interval = row
    new_enabled = 0 if int(daily_enabled or 0) == 1 else 1

    await update_daily_report(
        db,
        c.from_user.id,
        new_enabled,
        str(daily_time or "21:00"),
        now_iso(),
    )
    await db.commit()

    await _go_notifs_menu(c, state, db)
    await c.answer()


@router.callback_query(F.data == "st:notifs:daily:time")
async def st_notifs_daily_time(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    await _enter_input_mode(
        c,
        state,
        screen_text="⏰ <b>Время ежедневного отчёта</b>\n\nУкажи время, когда бот должен отправлять итог дня.",
        prompt_text=_s(lang, "time_example"),
        next_state=SettingsFlow.daily_report_time,
        return_to="notifs_menu",
    )


@router.message(SettingsFlow.daily_report_time, F.text)
async def st_notifs_daily_time_set(m: Message, state: FSMContext, db: aiosqlite.Connection):
    await consume_user_input(m, state)
    if _is_cancel(m.text):
        await _cancel_settings_flow(m, state, db)
        return

    hhmm = parse_hhmm(m.text or "")
    if not hhmm:
        await m.answer(_s((await state.get_data()).get("lang", "ru"), "time_err"), parse_mode=PARSE_MODE)
        return

    row = await get_notification_settings(db, m.from_user.id)
    if not row:
        await cancel_to_main_menu(m, state, db)
        return

    daily_enabled, _daily_time, _nudge_enabled, _nudge_interval = row

    await update_daily_report(
        db,
        m.from_user.id,
        int(daily_enabled or 0),
        hhmm,
        now_iso(),
    )
    await db.commit()

    await _return_after_success(m, state, db)


@router.callback_query(F.data == "st:notifs:nudge:toggle")
async def st_notifs_nudge_toggle(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    row = await get_notification_settings(db, c.from_user.id)
    if not row:
        await _go_notifs_menu(c, state, db)
        await c.answer()
        return

    _daily_enabled, _daily_time, nudge_enabled, nudge_interval = row

    if int(nudge_enabled or 0) == 1:
        await update_nudges(db, c.from_user.id, 0, int(nudge_interval or 180), now_iso())
    else:
        interval = int(nudge_interval or 180) or 180
        await update_nudges(db, c.from_user.id, 1, interval, now_iso())

    await db.commit()
    await _go_notifs_menu(c, state, db)
    await c.answer()


@router.callback_query(F.data == "st:notifs:nudge:interval")
async def st_notifs_nudge_interval(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    row = await get_notification_settings(db, c.from_user.id)
    if not row:
        await _go_notifs_menu(c, state, db)
        await c.answer()
        return

    _daily_enabled, _daily_time, _nudge_enabled, nudge_interval = row

    await _clear_prompt(c, state)
    await state.set_state(None)
    await state.update_data(settings_return_to="notifs_menu", ui_scope=SETTINGS_SCOPE)

    await _render_screen(
        c,
        state,
        "🕒 <b>Интервал напоминаний</b>\n\nВыбери, как часто бот должен напоминать в течение дня.",
        reply_markup=nudge_interval_kb(int(nudge_interval or 180), await get_lang(db, c.from_user.id)),
    )
    await c.answer()


@router.callback_query(F.data.startswith("st:notifs:nudge:set:"))
async def st_notifs_nudge_set(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    minutes = int(c.data.split(":")[-1])

    row = await get_notification_settings(db, c.from_user.id)
    if not row:
        await _go_notifs_menu(c, state, db)
        await c.answer()
        return

    _daily_enabled, _daily_time, _nudge_enabled, nudge_interval = row

    if minutes <= 0:
        await update_nudges(db, c.from_user.id, 0, int(nudge_interval or 180), now_iso())
    else:
        await update_nudges(db, c.from_user.id, 1, minutes, now_iso())

    await db.commit()
    await _go_notifs_menu(c, state, db)
    await c.answer()

@router.callback_query(F.data == "st:notifs:inc:menu")
async def st_notifs_inc_menu(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    inc_enabled, inc_days, _, _ = await get_recurring_settings(db, c.from_user.id)
    
    await _clear_prompt(c, state)
    await state.set_state(None)
    await state.update_data(settings_return_to="notifs_menu", ui_scope=SETTINGS_SCOPE)

    from app.ui.keyboards import recurring_days_kb
    await _render_screen(
        c,
        state,
        _s(lang, "recurring_inc_title"),
        reply_markup=recurring_days_kb("inc", inc_enabled, inc_days, lang),
    )
    await c.answer()

@router.callback_query(F.data == "st:notifs:exp:menu")
async def st_notifs_exp_menu(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    lang = await get_lang(db, c.from_user.id)
    _, _, exp_enabled, exp_days = await get_recurring_settings(db, c.from_user.id)
    
    await _clear_prompt(c, state)
    await state.set_state(None)
    await state.update_data(settings_return_to="notifs_menu", ui_scope=SETTINGS_SCOPE)

    from app.ui.keyboards import recurring_days_kb
    await _render_screen(
        c,
        state,
        _s(lang, "recurring_exp_title"),
        reply_markup=recurring_days_kb("exp", exp_enabled, exp_days, lang),
    )
    await c.answer()

@router.callback_query(F.data.startswith("st:notifs:inc:set:"))
async def st_notifs_inc_set(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    val = c.data.split(":")[-1]
    
    inc_enabled, inc_days, _, _ = await get_recurring_settings(db, c.from_user.id)
    
    if val == "off":
        await update_recurring_inc_settings(db, c.from_user.id, 0, inc_days, now_iso())
    else:
        await update_recurring_inc_settings(db, c.from_user.id, 1, int(val), now_iso())
    
    await db.commit()
    await _go_notifs_menu(c, state, db)
    await c.answer()

@router.callback_query(F.data.startswith("st:notifs:exp:set:"))
async def st_notifs_exp_set(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    val = c.data.split(":")[-1]
    
    _, _, exp_enabled, exp_days = await get_recurring_settings(db, c.from_user.id)
    
    if val == "off":
        await update_recurring_exp_settings(db, c.from_user.id, 0, exp_days, now_iso())
    else:
        await update_recurring_exp_settings(db, c.from_user.id, 1, int(val), now_iso())
    
    await db.commit()
    await _go_notifs_menu(c, state, db)
    await c.answer()
