from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from app.ui.i18n import t, t_category


def newbie_menu(lang: str = "ru", days_left: int | None = None) -> ReplyKeyboardMarkup:
    return main_menu(lang, show_reports=False, show_planning=False, show_settings=True, show_upgrade=True, days_left=days_left)


def newbie_menu_level2(lang: str = "ru", days_left: int | None = None) -> ReplyKeyboardMarkup:
    return main_menu(lang, show_reports=True, show_planning=False, show_settings=True, show_upgrade=True, days_left=days_left)


def full_menu(lang: str = "ru", days_left: int | None = None) -> ReplyKeyboardMarkup:
    return main_menu(lang, show_reports=True, show_planning=True, show_settings=True, show_upgrade=False, days_left=days_left)


def main_menu(
    lang: str = "ru",
    *,
    show_reports: bool = True,
    show_planning: bool = False,
    show_settings: bool = False,
    show_upgrade: bool = False,
    days_left: int | None = None,
) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    button_order = [
        "BTN_EXPENSE",
        "BTN_INCOME",
    ]
    if show_planning:
        button_order.append("BTN_PLANNING")
    if show_reports:
        button_order.append("BTN_REPORT")
    if show_settings:
        button_order.append("BTN_SETTINGS")
    button_order.append("BTN_MORE")

    for key in button_order:
        kb.add(KeyboardButton(text=t(lang, key)))
    
    # Subscription status button
    if days_left is not None:
        if days_left > 0:
            if lang == "en":
                status_text = f"🌟 Full Mode ({days_left}d)"
            elif lang == "kk":
                status_text = f"🌟 Толық режим ({days_left} күн)"
            else:
                status_text = f"🌟 Полный режим ({days_left} дн.)"
        else:
            if lang == "en":
                status_text = "💎 Upgrade / Renew"
            elif lang == "kk":
                status_text = "💎 Жаңарту / Продлить"
            else:
                status_text = "💎 Продлить подписку"
        kb.add(KeyboardButton(text=status_text))
    elif show_upgrade:
        kb.add(KeyboardButton(text=t(lang, "BTN_UPGRADE_FULL")))

    rows = [2] * (len(button_order) // 2)
    if len(button_order) % 2:
        rows.append(1)
    if show_upgrade or days_left is not None:
        rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup(resize_keyboard=True)


def cancel_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text=t(lang, "BTN_CANCEL")))
    return kb.as_markup(resize_keyboard=True)


def inline_cancel_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    """Single inline cancel button attached to any prompt that expects text
    input. Lets the user bail out without scrolling back to the reply keyboard.
    All flows share the ``flow:cancel`` callback handler (see common.py)."""
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_CANCEL"), callback_data="flow:cancel")
    return kb.as_markup()


def flow_done_actions_kb(
    lang: str = "ru",
    *,
    list_cb: str | None = None,
    menu_cb: str = "hub:planning",
) -> InlineKeyboardMarkup:
    """Compact ``[📋 List] [🏠 Menu]`` keyboard shown after we finalize a
    planning flow (done / paid / received / snooze / manual). Without it the
    user is left on a bare message with no obvious next step."""
    kb = InlineKeyboardBuilder()
    if list_cb:
        if lang == "en":
            list_label = "📋 List"
        elif lang == "kk":
            list_label = "📋 Тізім"
        else:
            list_label = "📋 Список"
        kb.button(text=list_label, callback_data=list_cb)
    if lang == "en":
        menu_label = "🏠 Menu"
    elif lang == "kk":
        menu_label = "🏠 Мәзір"
    else:
        menu_label = "🏠 Меню"
    kb.button(text=menu_label, callback_data=menu_cb)
    kb.adjust(2 if list_cb else 1)
    return kb.as_markup()

def minimized_menu_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text=t(lang, "BTN_RETURN_TO_MAIN_MENU")))
    return kb.as_markup(resize_keyboard=True)


def back_and_menu_kb(lang: str = "ru") -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text=t(lang, "BTN_BACK")))
    kb.add(KeyboardButton(text=t(lang, "BTN_RETURN_TO_MAIN_MENU")))
    kb.adjust(1, 1)
    return kb.as_markup(resize_keyboard=True)


def recurring_hub_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_RECURRING_EXPENSES"), callback_data="re:menu")
    kb.button(text=t(lang, "BTN_RECURRING_INCOMES"), callback_data="ri:menu")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="hub:planning")
    kb.adjust(1, 1, 1)
    return kb.as_markup()


def planning_hub_kb(lang: str = "ru", *, show_planned: bool = True, show_recurring: bool = True, show_debts: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if show_planned:
        kb.button(text=t(lang, "BTN_PLANNED"), callback_data="pl:menu")
    if show_recurring:
        kb.button(text=t(lang, "BTN_RECURRING_EXPENSES"), callback_data="re:menu")
        kb.button(text=t(lang, "BTN_RECURRING_INCOMES"), callback_data="ri:menu")
    if show_debts:
        kb.button(text=t(lang, "BTN_DEBTS"), callback_data="debt:menu")
    
    # Smart suggestions button (always visible in Planning hub if full access)
    kb.button(text=t(lang, "BTN_SMART_SUGGEST"), callback_data="hub:smart_suggest")
    
    kb.adjust(1, 1, 1, 1, 1)
    return kb.as_markup()


def more_hub_kb(lang: str = "ru", *, show_accounts: bool = True, show_transfer: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if show_accounts:
        kb.button(text=t(lang, "BTN_ACCOUNTS"), callback_data="more:accounts")
    if show_transfer:
        kb.button(text=t(lang, "BTN_TRANSFER"), callback_data="more:transfer")
    kb.adjust(1, 1)
    return kb.as_markup()

def lang_selection_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🇷🇺 Русский", callback_data="ob:lang:ru")
    kb.button(text="🇬🇧 English", callback_data="ob:lang:en")
    kb.button(text="🇰🇿 Қазақша", callback_data="ob:lang:kk")
    kb.adjust(3)
    return kb.as_markup()

def onboarding_start_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_START"), callback_data="ob:start")
    kb.button(text=t(lang, "BTN_CANCEL"), callback_data="cancel")
    kb.adjust(2)
    return kb.as_markup()

def currency_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="₸ KZT", callback_data="ob:cur:KZT")
    kb.button(text="₽ RUB", callback_data="ob:cur:RUB")
    kb.button(text="$ USD", callback_data="ob:cur:USD")
    kb.button(text="€ EUR", callback_data="ob:cur:EUR")
    kb.adjust(2,2,1)
    return kb.as_markup()

def yes_no_kb(prefix: str, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_YES"), callback_data=f"{prefix}:yes")
    kb.button(text=t(lang, "BTN_NO"), callback_data=f"{prefix}:no")
    kb.adjust(2)
    return kb.as_markup()

def daily_time_quick_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="20:00", callback_data="ob:time:20:00")
    kb.button(text="21:00", callback_data="ob:time:21:00")
    kb.button(text="22:00", callback_data="ob:time:22:00")
    kb.button(text=t(lang, "BTN_OTHER"), callback_data="ob:time:other")
    kb.adjust(2,2,1)
    return kb.as_markup()

def accounts_kb(accounts: list[tuple[int, str, int, int, str | None, int]], prefix: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """Account rows from ``list_accounts`` are 6-tuple: id, name, balance, is_archived, currency, is_saving."""
    kb = InlineKeyboardBuilder()
    for row in accounts:
        acc_id, name, bal, arch = int(row[0]), row[1], int(row[2] or 0), int(row[3] or 0)
        currency = (row[4] or "KZT") if len(row) > 4 else "KZT"
        if arch:
            continue
        kb.button(
            text=f"{name} — {_fmt_balance_compact(bal, currency)}",
            callback_data=f"{prefix}:{acc_id}",
        )
    kb.button(text=t(lang, "BTN_CANCEL"), callback_data="cancel")
    kb.adjust(1)
    return kb.as_markup()

CATEGORIES_PAGE_SIZE = 12


def categories_kb(
    cats: list[tuple[int, str, str | None]],
    prefix: str,
    lang: str = "ru",
    *,
    page: int = 0,
    page_size: int = CATEGORIES_PAGE_SIZE,
    nav_prefix: str | None = None,
    add_cb: str | None = None,
) -> InlineKeyboardMarkup:
    """Render a paginated category picker.

    ``cats`` is already ordered "popular first" by ``list_categories``. We just
    slice the page and append Prev / Next nav rows when there's more than one
    page. ``nav_prefix`` is the callback prefix used for paging — defaults to
    ``prefix`` so a single inline flow doesn't have to register extra callbacks.
    """
    nav_prefix = nav_prefix or prefix
    total = len(cats)
    page = max(0, int(page))
    start = page * page_size
    end = start + page_size
    visible = cats[start:end]

    kb = InlineKeyboardBuilder()
    for cid, name, emoji in visible:
        label = f"{emoji + ' ' if emoji else ''}{t_category(name, lang)}"
        kb.button(text=label, callback_data=f"{prefix}:{cid}")

    rows = [2] * ((len(visible) + 1) // 2)

    if total > page_size:
        if page > 0:
            kb.button(text="◀️", callback_data=f"{nav_prefix}:page:{page - 1}")
        kb.button(text=f"{page + 1}/{(total + page_size - 1) // page_size}", callback_data=f"{nav_prefix}:page:{page}")
        if end < total:
            kb.button(text="▶️", callback_data=f"{nav_prefix}:page:{page + 1}")
        nav_count = (1 if page > 0 else 0) + 1 + (1 if end < total else 0)
        rows.append(nav_count)

    if add_cb:
        kb.button(text=t(lang, "BTN_ADD_CATEGORY"), callback_data=add_cb)
        rows.append(1)

    kb.button(text=t(lang, "BTN_CANCEL"), callback_data="cancel")
    rows.append(1)
    kb.adjust(*rows)
    return kb.as_markup()

def categories_kb_with_add(cats: list[tuple[int,str,str|None]], prefix: str, add_cb: str, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for cid, name, emoji in cats:
        label = f"{emoji+' ' if emoji else ''}{t_category(name, lang)}"
        kb.button(text=label, callback_data=f"{prefix}:{cid}")
    kb.button(text=t(lang, "BTN_ADD_CATEGORY"), callback_data=add_cb)
    kb.button(text=t(lang, "BTN_CANCEL"), callback_data="cancel")
    kb.adjust(2)
    return kb.as_markup()

def settings_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_SETTINGS_CAT_LIMITS"), callback_data="st:catlim")
    kb.button(text=t(lang, "BTN_SETTINGS_NOTIFS"), callback_data="st:notifs")
    kb.button(text=t(lang, "BTN_LANGUAGE"), callback_data="st:lang")
    kb.button(text=t(lang, "BTN_SETTINGS_RESET"), callback_data="st:reset")
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()

def settings_accounts_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=("📂 Открыть счёт" if lang=="ru" else ("📂 Open account" if lang=="en" else "📂 Шотты ашу")), callback_data="st:acc:open")
    kb.button(text=t(lang, "BTN_ADD_ACCOUNT"), callback_data="st:acc:add")
    kb.button(text=t(lang, "BTN_RENAME"), callback_data="st:acc:rename")
    kb.button(text=t(lang, "BTN_EDIT_BALANCE"), callback_data="st:acc:balance")
    kb.button(text=t(lang, "BTN_ARCHIVE"), callback_data="st:acc:archive")
    kb.button(text=("🗄 Архив счетов" if lang=="ru" else ("🗄 Archived accounts" if lang=="en" else "🗄 Архив шоттар")), callback_data="st:acc:archived")
    kb.button(text=t(lang, "BTN_BACK_TO_SETTINGS"), callback_data="st:root")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()




def _fmt_balance_compact(value: int, currency: str = "KZT") -> str:
    from app.domain.money import fmt_money_compact
    return fmt_money_compact(value, currency)


def active_accounts_kb(accs, action_prefix: str, lang: str = "ru", back_cb: str = "st:accounts") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    
    # Split accs into regular and savings
    regular = [a for a in accs if not a[5]] # is_saving is at index 5
    savings = [a for a in accs if a[5]]
    
    for row in regular:
        acc_id, name, balance, _archived, currency, _is_saving = row
        kb.button(text=f"💳 {name} — {_fmt_balance_compact(balance, currency)}", callback_data=f"{action_prefix}:{acc_id}")
    
    if savings:
        # Visual separator or just a list of savings
        for row in savings:
            acc_id, name, balance, _archived, currency, _is_saving = row
            kb.button(text=f"🎯 {name} — {_fmt_balance_compact(balance, currency)}", callback_data=f"{action_prefix}:{acc_id}")
            
    kb.button(text=t(lang, "BTN_BACK"), callback_data=back_cb)
    kb.adjust(1)
    return kb.as_markup()


def account_actions_kb(account_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    change_cur = {"ru": "💱 Сменить валюту", "en": "💱 Change currency", "kk": "💱 Валютаны өзгерту"}.get(lang, "💱 Change currency")
    change_type = {"ru": "📌 Сменить тип (Копилка/Обычный)", "en": "📌 Switch type (Saving/Regular)", "kk": "📌 Түрін өзгерту"}.get(lang, "📌 Switch type")
    
    kb.button(text=t(lang, "BTN_RENAME"), callback_data=f"st:acc:view:rename:{account_id}")
    kb.button(text=t(lang, "BTN_EDIT_BALANCE"), callback_data=f"st:acc:view:balance:{account_id}")
    kb.button(text=change_cur, callback_data=f"st:acc:view:currency:{account_id}")
    kb.button(text=change_type, callback_data=f"st:acc:view:type_toggle:{account_id}")
    kb.button(text=t(lang, "BTN_ARCHIVE"), callback_data=f"st:acc:view:archive:{account_id}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="st:acc:open")
    kb.adjust(1)
    return kb.as_markup()
def archived_accounts_kb(accs, action_prefix: str, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for row in accs:
        acc_id, name, balance, _archived, currency, _is_saving = row
        kb.button(text=f"📁 {name} — {_fmt_balance_compact(balance, currency)}", callback_data=f"{action_prefix}:{acc_id}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="st:accounts")
    kb.adjust(1)
    return kb.as_markup()


def archived_account_actions_kb(account_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    restore = "♻️ Восстановить" if lang=="ru" else ("♻️ Restore" if lang=="en" else "♻️ Қалпына келтіру")
    delete = "🗑 Удалить навсегда" if lang=="ru" else ("🗑 Delete forever" if lang=="en" else "🗑 Біржола жою")
    kb.button(text=restore, callback_data=f"st:acc:restore:{account_id}")
    kb.button(text=delete, callback_data=f"st:acc:delete:{account_id}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="st:acc:archived")
    kb.adjust(1)
    return kb.as_markup()

def lang_kb(back_cb: str | None = None, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Русский 🇷🇺", callback_data="lang:ru")
    kb.button(text="English 🇬🇧", callback_data="lang:en")
    kb.button(text="Қазақша 🇰🇿", callback_data="lang:kk")
    if back_cb:
        kb.button(text=t(lang, "BTN_BACK"), callback_data=back_cb)
    kb.adjust(1)
    return kb.as_markup()

def reports_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # Row 1: Period reports
    kb.button(text=t(lang, "BTN_TODAY"), callback_data="rp:view:day:0")
    kb.button(text=t(lang, "BTN_WEEK"), callback_data="rp:view:week:0")
    kb.button(text=t(lang, "BTN_MONTH"), callback_data="rp:view:month:0")
    # Row 2: Streak
    kb.button(text=t(lang, "BTN_STREAK"), callback_data="rp:streak")
    # Row 3: AI Consultant
    kb.button(text=t(lang, "BTN_AI_REPORT"), callback_data="ai:open")
    kb.adjust(3, 1, 1)
    return kb.as_markup()


def reset_confirm_kb(lang: str = "ru"):
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_SETTINGS_RESET"), callback_data="st:reset:confirm")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="st:root")
    kb.adjust(1, 1)
    return kb.as_markup()

def upgrade_info_kb(lang: str, price: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    text = t(lang, "BTN_UNLOCK_FULL")
    kb.button(text=f"{text} ({price} ⭐️)", callback_data="upgrade:activate")
    kb.adjust(1)
    return kb.as_markup()

def cats_kind_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # keeping domain terms mostly Russian for now would be worse than mixed UI
    kb.button(text="➖ Расходы" if lang=="ru" else ("➖ Expenses" if lang=="en" else "➖ Шығыстар"), callback_data="st:cats:kind:expense")
    kb.button(text="➕ Доходы" if lang=="ru" else ("➕ Income" if lang=="en" else "➕ Кірістер"), callback_data="st:cats:kind:income")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="st:back")
    kb.adjust(2,1)
    return kb.as_markup()

def cats_list_manage_kb(cats: list[tuple[int,str,str|None]], kind: str, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for cid, name, emoji in cats:
        label = f"{emoji+' ' if emoji else ''}{t_category(name, lang)}"
        kb.button(text=label, callback_data=f"st:cats:pick:{cid}")
    kb.button(text=t(lang, "BTN_ADD_CATEGORY"), callback_data=f"st:cats:add:{kind}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="st:cats")
    kb.adjust(2)
    return kb.as_markup()

def cat_actions_kb(category_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_RENAME"), callback_data=f"st:cats:rename:{category_id}")
    kb.button(text="😀 Emoji", callback_data=f"st:cats:emoji:{category_id}")
    kb.button(text="🗑 Архивировать" if lang=="ru" else ("🗑 Archive" if lang=="en" else "🗑 Архивтеу"), callback_data=f"st:cats:arch:{category_id}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="st:cats")
    kb.adjust(2,1,1)
    return kb.as_markup()

def quick_draft_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_SAVE"), callback_data="qa:save")
    kb.button(text=t(lang, "BTN_AMOUNT"), callback_data="qa:edit_amount")
    kb.button(text=t(lang, "BTN_CATEGORY"), callback_data="qa:pickcat")
    kb.button(text=t(lang, "BTN_ACCOUNT"), callback_data="qa:pickacc")
    kb.button(text=t(lang, "BTN_CANCEL"), callback_data="cancel")
    kb.adjust(2,2,1)
    return kb.as_markup()

def quick_pick_type_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_PICK_INCOME"), callback_data="qa:type:income")
    kb.button(text=t(lang, "BTN_PICK_EXPENSE"), callback_data="qa:type:expense")
    kb.button(text=t(lang, "BTN_CANCEL"), callback_data="cancel")
    kb.adjust(2,1)
    return kb.as_markup()

def undo_kb(tx_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔴➖ Отменить", callback_data=f"qa:undo:{tx_id}")
    return kb.as_markup()

def budgets_categories_kb(cats, right_map: dict[int, str] | None = None, badge_map: dict[int, str] | None = None, prefix: str = "bud:cat", cancel_cb: str = "cancel", lang: str = "ru", add_cb: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    right_map = right_map or {}
    badge_map = badge_map or {}
    badge_prefix = {"over": "🔴 ", "warn": "🟡 ", "ok": "🟢 ", "plain": "⚪️ "}
    for cid, name, emoji in cats:
        title = f"{(emoji + ' ') if emoji else ''}{t_category(name, lang)}"
        if cid in right_map:
            badge = badge_prefix.get(badge_map.get(cid, "plain"), "")
            title = f"{title} — {badge}{right_map[cid]}"
        kb.button(text=title, callback_data=f"{prefix}:{cid}")
    if add_cb:
        kb.button(text=t(lang, "BTN_ADD_CATEGORY"), callback_data=add_cb)
    kb.button(text=t(lang, "BTN_CANCEL"), callback_data=cancel_cb)
    kb.adjust(1)
    return kb.as_markup()

def budgets_confirm_kb(lang: str = "ru"):
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_SET_LIMIT"), callback_data="bud:save")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="bud:back")
    kb.button(text=t(lang, "BTN_CANCEL"), callback_data="cancel")
    kb.adjust(1)
    return kb.as_markup()

def budgets_done_kb(lang: str = "ru"):
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_ADD_MORE"), callback_data="bud:again")
    kb.button(text=t(lang, "BTN_MENU"), callback_data="bud:menu")
    kb.adjust(1)
    return kb.as_markup()

def budget_over_kb(prefix: str, lang: str = "ru"):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Всё равно сохранить" if lang=="ru" else ("✅ Save anyway" if lang=="en" else "✅ Сонда да сақтау"), callback_data=f"{prefix}:yes")
    kb.button(text=t(lang, "BTN_CANCEL"), callback_data=f"{prefix}:no")
    kb.adjust(1)
    return kb.as_markup()

def notifications_kb(
    daily_enabled: int, 
    daily_time: str, 
    nudge_enabled: int, 
    nudge_interval_min: int, 
    inc_enabled: int, 
    inc_days: int, 
    exp_enabled: int, 
    exp_days: int, 
    lang: str = "ru"
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    de = "✅" if int(daily_enabled or 0) == 1 else "❌"
    ne = "✅" if int(nudge_enabled or 0) == 1 else "❌"
    interval_h = int(nudge_interval_min or 180) // 60
    
    # Days labels
    def _days_label(enabled, days, l):
        if not enabled:
            return "❌"
        if days == 0:
            return "🎯 " + ("Today" if l=="en" else ("Бүгін" if l=="kk" else "В день события"))
        return f"⏳ {days} " + ("d." if l=="en" else ("күн" if l=="kk" else "дн."))

    inc_label = _days_label(inc_enabled, inc_days, lang)
    exp_label = _days_label(exp_enabled, exp_days, lang)

    if lang=="en":
        kb.button(text=f"📅 Daily report: {de}", callback_data="st:notifs:daily:toggle")
        kb.button(text=f"⏰ Report time: {daily_time or '21:00'}", callback_data="st:notifs:daily:time")
        kb.button(text=f"🔁 Nudges: {ne}", callback_data="st:notifs:nudge:toggle")
        kb.button(text=f"🕒 Interval: {interval_h}h", callback_data="st:notifs:nudge:interval")
        kb.button(text=f"💰 Salary: {inc_label}", callback_data="st:notifs:inc:menu")
        kb.button(text=f"💳 Expenses: {exp_label}", callback_data="st:notifs:exp:menu")
    elif lang=="kk":
        kb.button(text=f"📅 Күндік есеп: {de}", callback_data="st:notifs:daily:toggle")
        kb.button(text=f"⏰ Есеп уақыты: {daily_time or '21:00'}", callback_data="st:notifs:daily:time")
        kb.button(text=f"🔁 Еске салу: {ne}", callback_data="st:notifs:nudge:toggle")
        kb.button(text=f"🕒 Аралық: {interval_h} сағ", callback_data="st:notifs:nudge:interval")
        kb.button(text=f"💰 Жалақы: {inc_label}", callback_data="st:notifs:inc:menu")
        kb.button(text=f"💳 Шығыстар: {exp_label}", callback_data="st:notifs:exp:menu")
    else:
        kb.button(text=f"📅 Ежедневный отчёт: {de}", callback_data="st:notifs:daily:toggle")
        kb.button(text=f"⏰ Время отчёта: {daily_time or '21:00'}", callback_data="st:notifs:daily:time")
        kb.button(text=f"🔁 Напоминания днём: {ne}", callback_data="st:notifs:nudge:toggle")
        kb.button(text=f"🕒 Интервал: {interval_h}ч", callback_data="st:notifs:nudge:interval")
        kb.button(text=f"💰 Зарплата/Доход: {inc_label}", callback_data="st:notifs:inc:menu")
        kb.button(text=f"💳 Подписки/Траты: {exp_label}", callback_data="st:notifs:exp:menu")
    
    kb.button(text=t(lang, "BTN_NOTIFS_BACK"), callback_data="st:root")
    kb.adjust(1)
    return kb.as_markup()

def recurring_days_kb(kind: str, current_enabled: int, current_days: int, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # Options: 0 (Today), 1, 3, 5, 7
    options = [0, 1, 3, 5, 7]
    for d in options:
        mark = "✅ " if (current_enabled and current_days == d) else ""
        if d == 0:
            label = "День в день" if lang=="ru" else ("Today" if lang=="en" else "Бүгін")
        else:
            label = f"{d} " + ("дн." if lang=="ru" else ("d." if lang=="en" else "күн"))
        kb.button(text=f"{mark}{label}", callback_data=f"st:notifs:{kind}:set:{d}")
    
    off_mark = "✅ " if not current_enabled else ""
    off_label = "Выключить" if lang=="ru" else ("Turn off" if lang=="en" else "Өшіру")
    kb.button(text=f"{off_mark}{off_label}", callback_data=f"st:notifs:{kind}:set:off")
    
    kb.button(text=t(lang, "BTN_BACK"), callback_data="st:notifs:menu")
    kb.adjust(2, 3, 1, 1)
    return kb.as_markup()

def nudge_interval_kb(current_min: int, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    cur = int(current_min or 180)
    options = [("1 час" if lang=="ru" else ("1 hour" if lang=="en" else "1 сағат"), 60), ("3 часа" if lang=="ru" else ("3 hours" if lang=="en" else "3 сағат"), 180), ("6 часов" if lang=="ru" else ("6 hours" if lang=="en" else "6 сағат"), 360)]
    for title, minutes in options:
        mark = "✅ " if cur == minutes else ""
        kb.button(text=f"{mark}{title}", callback_data=f"st:notifs:nudge:set:{minutes}")
    kb.button(text=t(lang, "BTN_OFF"), callback_data="st:notifs:nudge:set:0")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="st:notifs:menu")
    kb.adjust(2,2)
    return kb.as_markup()

def debts_menu_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if lang=="en":
        out, inn, add, rem = "📤 I owe", "📥 Owed to me", "➕ Add", "⚙️ Reminders"
    elif lang=="kk":
        out, inn, add, rem = "📤 Мен қарызбын", "📥 Маған қарыз", "➕ Қосу", "⚙️ Еске салғыштар"
    else:
        out, inn, add, rem = "📤 Я должен", "📥 Мне должны", "➕ Добавить", "⚙️ Напоминания"
    kb.button(text=out, callback_data="debt:list:out")
    kb.button(text=inn, callback_data="debt:list:in")
    kb.button(text=add, callback_data="debt:add")
    kb.button(text=rem, callback_data="debt:settings")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="hub:planning")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def debt_item_kb(debt_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    paid = "✅ Оплачено/Получил" if lang=="ru" else ("✅ Paid / received" if lang=="en" else "✅ Төленді / алдым")
    details = "🧾 Подробнее" if lang=="ru" else ("🧾 Details" if lang=="en" else "🧾 Толығырақ")
    kb.button(text=paid, callback_data=f"debt:paid:{debt_id}")
    kb.button(text=details, callback_data=f"debt:view:{debt_id}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="debt:menu")
    kb.adjust(2, 1)
    return kb.as_markup()




def debt_reminders_settings_kb(enabled: int, days_before: int, lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if lang == "en":
        onoff = f"🔔 Reminders: {'ON' if int(enabled or 0) == 1 else 'OFF'}"
        title1, title3, title7 = "1 day", "3 days", "7 days"
    elif lang == "kk":
        onoff = f"🔔 Еске салу: {'ҚОСУЛЫ' if int(enabled or 0) == 1 else 'ӨШІРУЛІ'}"
        title1, title3, title7 = "1 күн", "3 күн", "7 күн"
    else:
        onoff = f"🔔 Напоминания: {'ВКЛ' if int(enabled or 0) == 1 else 'ВЫКЛ'}"
        title1, title3, title7 = "1 день", "3 дня", "7 дней"

    kb.button(text=onoff, callback_data="debt:settings:toggle")
    for days, title in [(1, title1), (3, title3), (7, title7)]:
        mark = "✅ " if int(days_before or 3) == days else ""
        kb.button(text=f"{mark}{title}", callback_data=f"debt:settings:days:{days}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="debt:menu")
    kb.adjust(1, 3, 1)
    return kb.as_markup()

def ai_consultant_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "AI_CHAT_START"), callback_data="ai:chat:start")
    kb.button(text=t(lang, "AI_REPORT_START"), callback_data="ai:report:start")
    kb.button(text=t(lang, "AI_EDIT_GOAL"), callback_data="ai:goal:edit")
    kb.button(text=t(lang, "AI_CLARIFY"), callback_data="ai:clarify")
    kb.button(text=t(lang, "AI_BACK"), callback_data="ai:back")
    kb.adjust(1, 1, 1, 1, 1)
    return kb.as_markup()


def ai_chat_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "AI_CHAT_NEW_TOPIC"), callback_data="ai:chat:reset")
    kb.button(text=t(lang, "AI_CHAT_REPORT"), callback_data="ai:report:start")
    kb.button(text=t(lang, "AI_CHAT_EXIT"), callback_data="ai:chat:exit")
    kb.adjust(2, 1)
    return kb.as_markup()


def ai_chat_limit_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "AI_CHAT_BUY_MORE"), callback_data="ai:chat:buy")
    kb.button(text=t(lang, "AI_BACK_TO_AI"), callback_data="ai:menu")
    kb.adjust(1, 1)
    return kb.as_markup()


def ai_report_period_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "AI_MONTH"), callback_data="ai:period:month")
    kb.button(text=t(lang, "AI_WEEK"), callback_data="ai:period:week")
    kb.button(text=t(lang, "AI_DAY"), callback_data="ai:period:day")
    kb.button(text=t(lang, "AI_BACK_TO_AI"), callback_data="ai:menu")
    kb.adjust(1, 2, 1)
    return kb.as_markup()


def ai_report_actions_kb(lang: str = "ru", *, can_download: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if can_download:
        kb.button(text=t(lang, "AI_DOWNLOAD"), callback_data="ai:download")
    kb.button(text=t(lang, "AI_CHAT_START"), callback_data="ai:chat:start")
    kb.button(text=t(lang, "AI_NEW_REPORT"), callback_data="ai:report:start")
    kb.button(text=t(lang, "AI_BACK_TO_AI"), callback_data="ai:menu")
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()


def account_currency_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🇰🇿 KZT", callback_data="acc:cur:KZT")
    kb.button(text="🇺🇸 USD", callback_data="acc:cur:USD")
    kb.button(text="🇷🇺 RUB", callback_data="acc:cur:RUB")
    kb.button(text="🇪🇺 EUR", callback_data="acc:cur:EUR")
    kb.adjust(2, 2)
    return kb.as_markup()


def account_type_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    regular = {"ru": "💳 Обычный счёт", "en": "💳 Regular account", "kk": "💳 Қалыпты шот"}.get(lang, "💳 Regular account")
    saving = {"ru": "🎯 Копилка / Сбережения", "en": "🎯 Savings / Goal", "kk": "🎯 Копилка / Жинақ"}.get(lang, "🎯 Savings / Goal")
    
    kb.button(text=regular, callback_data="acc:type:regular")
    kb.button(text=saving, callback_data="acc:type:saving")
    kb.adjust(1)
    return kb.as_markup()


def account_limit_reached_kb(lang: str, price: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    text = t(lang, "BTN_UNLOCK_FULL")
    kb.button(text=f"{text} ({price} ⭐️)", callback_data="upgrade:activate")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="st:accounts")
    kb.adjust(1)
    return kb.as_markup()
