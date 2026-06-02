from __future__ import annotations
from app.domain.services.access_service import FEATURE_REPORTS, can_use_feature

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import aiosqlite
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardRemove, BufferedInputFile, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repositories.accounts_repo import list_accounts
from app.db.repositories.tx_repo import list_last
from app.db.repositories.budgets_repo import month_limits_status_map
from app.db.repositories.planned_repo import planned_before_month_end
from app.db.repositories.recurring_repo import (
    recurring_due_before_month_end,
    recurring_income_due_before_month_end,
)
from app.db.repositories.settings_repo import get_lang, get_timezone
from app.db.repositories.users_repo import get_streak
from app.domain.services.ai_consultant_service import build_section_hint
from app.domain.services.reports_service import (
    day_bounds_utc,
    month_bounds_utc,
    report_by_category,
    report_period,
    week_bounds_utc,
    build_smart_suggestion,
    iso,
)
from app.handlers.common import deny_feature_message, cancel_to_main_menu, build_main_menu_markup, _cleanup_ui, _ensure_minimized_menu, neutralize_keyboard
from app.ui.formatters import fmt_money
from app.ui.i18n import t, text_matches_key, t_category
from app.ui.keyboards import cancel_kb, reports_kb, minimized_menu_kb

router = Router()

TOP_CATS_PREVIEW = 5
TOP_CATS_EXPANDED = 10
PARSE_MODE = "HTML"


_RU_MON_SHORT = {
    1: "янв", 2: "фев", 3: "мар", 4: "апр",
    5: "май", 6: "июн", 7: "июл", 8: "авг",
    9: "сен", 10: "окт", 11: "ноя", 12: "дек",
}
_KK_MON_SHORT = {
    1: "қаң", 2: "ақп", 3: "нау", 4: "сәу",
    5: "мам", 6: "мау", 7: "шіл", 8: "там",
    9: "қыр", 10: "қаз", 11: "қар", 12: "жел",
}
_EN_MON_SHORT = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def _fmt_human_date(lang: str, dt) -> str:
    months_map = {
        "ru": [
            "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря",
        ],
        "en": [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        "kk": [
            "қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым",
            "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан",
        ],
    }
    weekdays_map = {
        "ru": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
        "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "kk": ["дс", "сс", "ср", "бс", "жм", "сн", "жс"],
    }

    lang = (lang or "ru").lower()
    months = months_map.get(lang, months_map["ru"])
    weekdays = weekdays_map.get(lang, weekdays_map["ru"])

    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt).date()
    elif isinstance(dt, datetime):
        dt = dt.date()

    return f"{dt.day} {months[dt.month - 1]}, {weekdays[dt.weekday()]}"


def _mon_short(lang: str, month: int) -> str:
    lang = (lang or "ru").lower()
    if lang == "kk":
        return _KK_MON_SHORT.get(month, str(month))
    if lang == "en":
        return _EN_MON_SHORT.get(month, str(month))
    return _RU_MON_SHORT.get(month, str(month))


def _fmt_day_label(lang: str, dt_local: datetime) -> str:
    return f"{dt_local.day} {_mon_short(lang, dt_local.month)} {dt_local.year}"


def _fmt_week_label(lang: str, start_local: datetime, end_local: datetime) -> str:
    if start_local.month == end_local.month and start_local.year == end_local.year:
        return f"{start_local.day}–{end_local.day} {_mon_short(lang, end_local.month)} {end_local.year}"
    return (
        f"{start_local.day} {_mon_short(lang, start_local.month)}"
        f" – "
        f"{end_local.day} {_mon_short(lang, end_local.month)} {end_local.year}"
    )


def _fmt_month_label(lang: str, dt_local: datetime) -> str:
    return f"{_mon_short(lang, dt_local.month)} {dt_local.year}"


def _fmt_money(n: int) -> str:
    return fmt_money(n)


def _pct(part: int, whole: int) -> str:
    if whole <= 0:
        return "0%"
    return f"{(part / whole) * 100:.1f}%"


def _delta_str(d: int) -> str:
    if d > 0:
        return f"+{_fmt_money(d)}"
    if d < 0:
        return f"-{_fmt_money(abs(d))}"
    return "0"


def _delta_pct_str(cur: int, prev: int) -> str:
    if prev == 0:
        return "—"
    return f"{((cur - prev) / prev) * 100:.1f}%"


def _arrow(diff: int) -> str:
    if diff > 0:
        return "⬆️"
    if diff < 0:
        return "⬇️"
    return "➖"


def _safe_tz(tz_name: str):
    try:
        return ZoneInfo(tz_name or "UTC"), (tz_name or "UTC")
    except Exception:
        return timezone.utc, "UTC"


def _month_bounds_safe(tz_name: str, now_utc: datetime) -> tuple[datetime, datetime, str | None, str | None]:
    try:
        return month_bounds_utc(tz_name, now_utc)
    except TypeError:
        return month_bounds_utc(tz_name)


def _prev_month_bounds_utc(tz_name: str, now_utc: datetime | None = None) -> tuple[datetime, datetime]:
    now_utc = now_utc or datetime.now(timezone.utc)
    tz, _ = _safe_tz(tz_name)
    local_now = now_utc.astimezone(tz)

    y, m = local_now.year, local_now.month
    py, pm = (y - 1, 12) if m == 1 else (y, m - 1)

    local_start = datetime(py, pm, 1, 0, 0, 0, tzinfo=tz)
    ny, nm = (py + 1, 1) if pm == 12 else (py, pm + 1)
    local_end = datetime(ny, nm, 1, 0, 0, 0, tzinfo=tz)

    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _labels(lang: str) -> dict[str, str]:
    lang = (lang or "ru").lower()

    if lang == "en":
        return {
            "menu_title": "📊 Reports",
            "today": "Day",
            "week": "Week",
            "month": "Month",
            "show_categories": "Show categories",
            "hide_categories": "Hide categories",
            "to_menu": "🏠 Menu",
            "income": "Income",
            "expense": "Expense",
            "net": "Net",
            "ops": "Ops",
            "avg_check": "Avg expense",
            "finance_block": "💰 <b>FINANCE</b>\n━━━━━━━━━━━━━━",
            "activity_block": "📌 <b>ACTIVITY</b>\n━━━━━━━━━━━━━━",
            "compare_yesterday": "🔎 <b>COMPARISON (YESTERDAY)</b>\n━━━━━━━━━━━━━━",
            "compare_week": "🔎 <b>COMPARISON (PREV WEEK)</b>\n━━━━━━━━━━━━━━",
            "compare_prev": "🔎 <b>COMPARED TO PREVIOUS</b>\n━━━━━━━━━━━━━━",
            "categories_block": "🧾 <b>EXPENSE CATEGORIES</b>\n━━━━━━━━━━━━━━",
            "other": "Other",
            "no_data": "No data",
            "streak": "Streak",
            "best": "Best",
            "report_day_title": "📊 <b>DAILY REPORT</b>",
            "report_week_title": "📊 <b>WEEKLY REPORT</b>",
            "report_month_title": "📊 <b>MONTHLY REPORT</b>",
            "streak_title": "🔥 <b>DISCIPLINE</b>\n━━━━━━━━━━━━━━",
            "streak_about": "Your current consistency.",
            "month_plan_block": "🗓 <b>UNTIL MONTH END</b>\n━━━━━━━━━━━━━━",
            "planned_income": "Planned recurring income",
            "planned_expense": "Planned recurring expenses",
            "planned_one_time": "Planned one-time operations",
            "planned_required_income": "Required one-time income",
            "planned_required_expense": "Required one-time expenses",
            "planned_flexible_income": "Flexible one-time income",
            "planned_flexible_expense": "Flexible one-time expenses",
            "planned_after_required": "Balance after required items",
            "planned_net": "Net effect",
            "upcoming": "Upcoming",
            "forecast_balance": "Projected ending balance",
            "hub_text": "Quick snapshot for the current month.",
            "hub_hint": "Choose a view below. The AI report is here too.",
        }

    if lang == "kk":
        return {
            "menu_title": "📊 Есептер",
            "today": "Күн",
            "week": "Апта",
            "month": "Ай",
            "show_categories": "Санаттарды көрсету",
            "hide_categories": "Санаттарды жасыру",
            "to_menu": "🏠 Мәзір",
            "income": "Кіріс",
            "expense": "Шығыс",
            "net": "Нәтиже",
            "ops": "Операция",
            "avg_check": "Орташа шығыс",
            "finance_block": "💰 <b>ҚАРЖЫ</b>\n━━━━━━━━━━━━━━",
            "activity_block": "📌 <b>БЕЛСЕНДІЛІК</b>\n━━━━━━━━━━━━━━",
            "compare_yesterday": "🔎 <b>САЛЫСТЫРУ (КЕШЕ)</b>\n━━━━━━━━━━━━━━",
            "compare_week": "🔎 <b>САЛЫСТЫРУ (ӨТКЕН АПТА)</b>\n━━━━━━━━━━━━━━",
            "compare_prev": "🔎 <b>ӨТКЕН КЕЗЕҢМЕН САЛЫСТЫРУ</b>\n━━━━━━━━━━━━━━",
            "categories_block": "🧾 <b>ШЫҒЫС САНАТТАРЫ</b>\n━━━━━━━━━━━━━━",
            "other": "Басқа",
            "no_data": "Дерек жоқ",
            "streak": "Серия",
            "best": "Үздік",
            "report_day_title": "📊 <b>КҮНДІК ЕСЕП</b>",
            "report_week_title": "📊 <b>АПТАЛЫҚ ЕСЕП</b>",
            "report_month_title": "📊 <b>АЙЛЫҚ ЕСЕП</b>",
            "streak_title": "🔥 <b>ДИСЦИПЛИНА</b>\n━━━━━━━━━━━━━━",
            "streak_about": "Қазіргі тұрақтылық көрсеткіші.",
            "month_plan_block": "🗓 <b>АЙ СОҢЫНА ДЕЙІН</b>\n━━━━━━━━━━━━━━",
            "planned_income": "Күтілетін тұрақты кіріс",
            "planned_expense": "Күтілетін тұрақты шығыс",
            "planned_one_time": "Жоспарланған бір реттік операциялар",
            "planned_required_income": "Міндетті бір реттік кіріс",
            "planned_required_expense": "Міндетті бір реттік шығыс",
            "planned_flexible_income": "Икемді бір реттік кіріс",
            "planned_flexible_expense": "Икемді бір реттік шығыс",
            "planned_after_required": "Міндеттіден кейінгі қалдық",
            "planned_net": "Таза әсері",
            "upcoming": "Жақын төлемдер",
            "forecast_balance": "Ай соңындағы болжамды қалдық",
            "hub_text": "Ағымдағы ай бойынша жылдам көрініс.",
            "hub_hint": "Төменнен қажетті көріністі таңдаңыз. AI-есеп те осында.",
        }

    return {
        "menu_title": "📊 Отчёты",
        "today": "День",
        "week": "Неделя",
        "month": "Месяц",
        "show_categories": "Показать категории",
        "hide_categories": "Скрыть категории",
        "to_menu": "🏠 Меню",
        "income": "Доход",
        "expense": "Расход",
        "net": "Итог",
        "ops": "Операций",
        "avg_check": "Средний чек",
        "finance_block": "💰 <b>ФИНАНСЫ</b>\n━━━━━━━━━━━━━━",
        "activity_block": "📌 <b>АКТИВНОСТЬ</b>\n━━━━━━━━━━━━━━",
        "compare_yesterday": "🔎 <b>СРАВНЕНИЕ (ВЧЕРА)</b>\n━━━━━━━━━━━━━━",
        "compare_week": "🔎 <b>СРАВНЕНИЕ (ПРОШЛАЯ НЕДЕЛЯ)</b>\n━━━━━━━━━━━━━━",
        "compare_prev": "🔎 <b>СРАВНЕНИЕ С ПРОШЛЫМ ПЕРИОДОМ</b>\n━━━━━━━━━━━━━━",
        "categories_block": "🧾 <b>РАСХОДЫ ПО КАТЕГОРИЯМ</b>\n━━━━━━━━━━━━━━",
        "other": "Другое",
        "no_data": "Нет данных",
        "streak": "Серия",
        "best": "Лучшая",
        "report_day_title": "📊 <b>ОТЧЕТ ЗА ДЕНЬ</b>",
        "report_week_title": "📊 <b>ОТЧЕТ ЗА НЕДЕЛЮ</b>",
        "report_month_title": "📊 <b>ОТЧЕТ ЗА МЕСЯЦ</b>",
        "streak_title": "🔥 <b>ДИСЦИПЛИНА</b>\n━━━━━━━━━━━━━━",
        "streak_about": "Текущая дисциплина по учету финансов.",
        "month_plan_block": "🗓 <b>ДО КОНЦА МЕСЯЦА</b>\n━━━━━━━━━━━━━━",
        "planned_income": "Ожидаемые постоянные доходы",
        "planned_expense": "Ожидаемые постоянные расходы",
        "planned_one_time": "Планируемые разовые операции",
        "planned_required_income": "Обязательные разовые доходы",
        "planned_required_expense": "Обязательные разовые расходы",
        "planned_flexible_income": "Гибкие разовые доходы",
        "planned_flexible_expense": "Гибкие разовые расходы",
        "planned_after_required": "Остаток после обязательных",
        "planned_net": "Чистый эффект",
        "upcoming": "Ближайшие движения",
        "forecast_balance": "Прогноз остатка к концу месяца",
        "hub_text": "Быстрый срез по текущему месяцу.",
        "hub_hint": "Выбери нужный срез ниже. Здесь же доступен AI-отчет.",
    }


def _report_kb(lang: str, period: str, show_categories: bool) -> InlineKeyboardMarkup:
    labels = _labels(lang)
    kb = InlineKeyboardBuilder()

    day_emoji = "☀️"
    week_emoji = "🗓"
    month_emoji = "📅"

    day_text = f"{day_emoji} {labels['today']}"
    week_text = f"{week_emoji} {labels['week']}"
    month_text = f"{month_emoji} {labels['month']}"

    if period == "day":
        day_text = f"🟢 {day_text}"
    elif period == "week":
        week_text = f"🟢 {week_text}"
    elif period == "month":
        month_text = f"🟢 {month_text}"

    kb.button(text=day_text, callback_data=f"rp:view:day:{1 if period == 'day' and show_categories else 0}")
    kb.button(text=week_text, callback_data=f"rp:view:week:{1 if period == 'week' and show_categories else 0}")
    kb.button(text=month_text, callback_data=f"rp:view:month:{1 if period == 'month' and show_categories else 0}")

    if show_categories:
        cat_text = f"🟢 📂 {labels['hide_categories']}"
    else:
        cat_text = f"🗂 {labels['show_categories']}"

    kb.button(text=cat_text, callback_data=f"rp:view:{period}:{0 if show_categories else 1}")
    kb.button(text=t(lang, "BTN_BACK"), callback_data="rp:hub")
    kb.adjust(3, 1, 1)
    return kb.as_markup()


def _streak_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "BTN_BACK"), callback_data="rp:hub")
    return kb.as_markup()


async def _edit_or_answer(m: Message, db: aiosqlite.Connection, text: str, *, reply_markup=None, prefer_edit: bool = False):
    if prefer_edit:
        try:
            await m.edit_text(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)
            return m
        except TelegramBadRequest as exc:
            err = str(exc).lower()
            if "message is not modified" in err:
                return m
            if (
                "message can't be edited" not in err
                and "message to edit not found" not in err
                and "there is no text in the message to edit" not in err
            ):
                return m
        except Exception:
            return m

    # Standard hub pattern: prefer new message for clean UI
    return await m.answer(text, reply_markup=reply_markup, parse_mode=PARSE_MODE)


def _fmt_title(title: str, label_human: str) -> str:
    return f"{title}\n<i>{label_human}</i>"


def _build_categories_lines(lang: str, expense_total: int, cats: list[tuple], *, expanded: bool) -> list[str]:
    labels = _labels(lang)
    limit = TOP_CATS_EXPANDED if expanded else TOP_CATS_PREVIEW
    lines: list[str] = ["", labels["categories_block"]]

    if not cats or expense_total <= 0:
        lines.append(f"• {labels['no_data']}")
        return lines

    shown = 0
    for row in cats[:limit]:
        name, emoji, total = row[0], row[1], row[2]
        label = t_category((name or "").strip(), lang) or t(lang, "NO_CATEGORY")
        prefix = f"{emoji} " if emoji else ""
        value = int(total or 0)
        shown += value
        lines.append(f"• {prefix}{label} — <b>{_fmt_money(value)}</b> ({_pct(value, expense_total)})")

    other = int(expense_total - shown)
    if other > 0:
        lines.append(f"• {labels['other']} — <b>{_fmt_money(other)}</b> ({_pct(other, expense_total)})")

    return lines


async def _month_plan_snapshot(db: aiosqlite.Connection, user_id: int, tz_name: str, end_utc: datetime) -> dict:
    tz_obj, _ = _safe_tz(tz_name)
    local_today = datetime.now(tz_obj).date().isoformat()
    local_month_end = end_utc.astimezone(tz_obj).date().isoformat()

    exp_rows = await recurring_due_before_month_end(db, user_id, local_today, local_month_end)
    inc_rows = await recurring_income_due_before_month_end(db, user_id, local_today, local_month_end)
    plan_rows = await planned_before_month_end(db, user_id, local_today, local_month_end)
    accounts = await list_accounts(db, user_id)

    planned_expense = sum(int(row[2] or 0) for row in exp_rows)
    planned_income = sum(int(row[2] or 0) for row in inc_rows)
    planned_one_time_income = sum(int(row[3] or 0) for row in plan_rows if str(row[1]) == "income")
    planned_one_time_expense = sum(int(row[3] or 0) for row in plan_rows if str(row[1]) == "expense")
    required_income_total = sum(int(row[3] or 0) for row in plan_rows if int(row[8] or 0) == 1 and str(row[1]) == "income")
    required_expense_total = sum(int(row[3] or 0) for row in plan_rows if int(row[8] or 0) == 1 and str(row[1]) == "expense")
    flexible_income_total = sum(int(row[3] or 0) for row in plan_rows if int(row[8] or 0) != 1 and str(row[1]) == "income")
    flexible_expense_total = sum(int(row[3] or 0) for row in plan_rows if int(row[8] or 0) != 1 and str(row[1]) == "expense")
    current_balance = sum(int(row[2] or 0) for row in accounts if len(row) >= 4 and not int(row[3] or 0))

    upcoming: list[tuple[str, str, str, int]] = []
    for row in inc_rows[:3]:
        upcoming.append((str(row[7] or ""), "+", str(row[1] or "—"), int(row[2] or 0)))
    for row in exp_rows[:3]:
        upcoming.append((str(row[7] or ""), "-", str(row[1] or "—"), int(row[2] or 0)))
    for row in plan_rows[:4]:
        upcoming.append((str(row[6] or ""), "+" if str(row[1]) == "income" else "-", str(row[2] or "—"), int(row[3] or 0)))
    upcoming.sort(key=lambda item: (item[0], item[1]))

    net = (planned_income + planned_one_time_income) - (planned_expense + planned_one_time_expense)
    required_net = required_income_total - required_expense_total
    return {
        "income_total": planned_income,
        "expense_total": planned_expense,
        "one_time_income_total": planned_one_time_income,
        "one_time_expense_total": planned_one_time_expense,
        "required_income_total": required_income_total,
        "required_expense_total": required_expense_total,
        "flexible_income_total": flexible_income_total,
        "flexible_expense_total": flexible_expense_total,
        "income_count": len(inc_rows),
        "expense_count": len(exp_rows),
        "one_time_count": len(plan_rows),
        "net": net,
        "forecast_balance_required_only": current_balance + planned_income - planned_expense + required_net,
        "forecast_balance": current_balance + net,
        "upcoming": upcoming[:6],
    }


def _build_month_plan_lines(lang: str, snapshot: dict) -> list[str]:
    labels = _labels(lang)
    income_total = int(snapshot.get("income_total") or 0)
    expense_total = int(snapshot.get("expense_total") or 0)
    income_count = int(snapshot.get("income_count") or 0)
    expense_count = int(snapshot.get("expense_count") or 0)
    one_time_income = int(snapshot.get("one_time_income_total") or 0)
    one_time_expense = int(snapshot.get("one_time_expense_total") or 0)
    one_time_count = int(snapshot.get("one_time_count") or 0)
    net = int(snapshot.get("net") or 0)
    required_income_total = int(snapshot.get("required_income_total") or 0)
    required_expense_total = int(snapshot.get("required_expense_total") or 0)
    flexible_income_total = int(snapshot.get("flexible_income_total") or 0)
    flexible_expense_total = int(snapshot.get("flexible_expense_total") or 0)
    forecast_balance_required_only = int(snapshot.get("forecast_balance_required_only") or 0)
    forecast_balance = int(snapshot.get("forecast_balance") or 0)
    upcoming = snapshot.get("upcoming") or []

    if income_count <= 0 and expense_count <= 0 and one_time_count <= 0:
        return []

    lines = [
        "",
        labels["month_plan_block"],
        f"• {labels['planned_income']}: <b>{_fmt_money(income_total)}</b> ({income_count})",
        f"• {labels['planned_expense']}: <b>{_fmt_money(expense_total)}</b> ({expense_count})",
        f"• {labels['planned_one_time']}: <b>{_delta_str(one_time_income - one_time_expense)}</b> ({one_time_count})",
        f"• {labels['planned_required_income']}: <b>{_fmt_money(required_income_total)}</b>",
        f"• {labels['planned_required_expense']}: <b>{_fmt_money(required_expense_total)}</b>",
        f"• {labels['planned_flexible_income']}: <b>{_fmt_money(flexible_income_total)}</b>",
        f"• {labels['planned_flexible_expense']}: <b>{_fmt_money(flexible_expense_total)}</b>",
        f"• {labels['planned_after_required']}: <b>{_fmt_money(forecast_balance_required_only)}</b>",
        f"• {labels['planned_net']}: <b>{_delta_str(net)}</b>",
        f"• {labels['forecast_balance']}: <b>{_fmt_money(forecast_balance)}</b>",
    ]

    if upcoming:
        lines.append(f"• {labels['upcoming']}:")
        for iso_date, sign, title, amount in upcoming:
            human_date = iso_date
            try:
                human_date = _fmt_human_date(lang, iso_date)
            except Exception:
                pass
            prefix = "+" if sign == "+" else "−"
            lines.append(f"  {prefix} {title} — <b>{_fmt_money(amount)}</b> · {human_date}")

    return lines


def _build_streak_line(lang: str, cur: int, best: int) -> str:
    labels = _labels(lang)
    if cur <= 0:
        return f"🔥 {labels['streak']}: 0"
    badge = "👑" if cur >= 30 else ("🚀" if cur >= 8 else "🔥")
    return f"{badge} {labels['streak']}: <b>{cur}</b> · {labels['best']}: <b>{best}</b>"


def _period_meta(lang: str, tz_name: str, period: str, now_utc: datetime) -> dict:
    tz_obj, _ = _safe_tz(tz_name)
    labels = _labels(lang)

    if period == "day":
        start, end, _raw, _tz_norm = day_bounds_utc(tz_name)
        prev_start = start - timedelta(days=1)
        prev_end = end - timedelta(days=1)
        label = _fmt_day_label(lang, start.astimezone(tz_obj))
        return {
            "start": start,
            "end": end,
            "prev_start": prev_start,
            "prev_end": prev_end,
            "title": _fmt_title(labels["report_day_title"], label),
            "compare_title": labels["compare_yesterday"],
        }

    if period == "week":
        start, end, _raw, _tz_norm = week_bounds_utc(tz_name)
        prev_start = start - timedelta(days=7)
        prev_end = end - timedelta(days=7)
        start_local = start.astimezone(tz_obj)
        end_local = (end - timedelta(seconds=1)).astimezone(tz_obj)
        label = _fmt_week_label(lang, start_local, end_local)
        return {
            "start": start,
            "end": end,
            "prev_start": prev_start,
            "prev_end": prev_end,
            "title": _fmt_title(labels["report_week_title"], label),
            "compare_title": labels["compare_week"],
        }

    start, end, _raw, _tz_norm = _month_bounds_safe(tz_name, now_utc)
    prev_start, prev_end = _prev_month_bounds_utc(tz_name, now_utc)
    label = _fmt_month_label(lang, start.astimezone(tz_obj))
    prev_label = _fmt_month_label(lang, prev_start.astimezone(tz_obj))
    compare_title = f"{labels['compare_prev']} ({prev_label})"
    return {
        "start": start,
        "end": end,
        "prev_start": prev_start,
        "prev_end": prev_end,
        "title": _fmt_title(labels["report_month_title"], label),
        "compare_title": f"🔎 <b>{compare_title}</b>",
    }


async def _open_reports_scope(m: Message, state: FSMContext, db: aiosqlite.Connection) -> str:
    lang = await get_lang(db, m.from_user.id)
    await state.clear()
    await state.update_data(ui_scope="reports")
    return lang


def _progress_bar(percent: float, length: int = 10) -> str:
    filled = int((percent / 100) * length)
    filled = max(0, min(length, filled))
    return f"[{'█'*filled}{'░'*(length - filled)}]"

async def _reports_hub_text(db: aiosqlite.Connection, user_id: int, lang: str) -> str:
    tz_name = await get_timezone(db, user_id)
    now_utc = datetime.now(timezone.utc)
    meta = _period_meta(lang, tz_name, "month", now_utc)
    day_meta = _period_meta(lang, tz_name, "day", now_utc)
    
    # 1. Cashflow (Month & Day)
    income, expense, cnt = await report_period(db, user_id, meta["start"], meta["end"])
    net = income - expense
    day_inc, day_exp, day_cnt = await report_period(db, user_id, day_meta["start"], day_meta["end"])
    
    # 2. Net Worth (Total Balance)
    accounts = await list_accounts(db, user_id)
    total_balance = sum(int(row[2] or 0) for row in accounts if len(row) >= 4 and not int(row[3] or 0))
    
    # 3. Gamification / Streak
    streak_cur, streak_best, _ = await get_streak(db, user_id)
    week_pct = min(100, (streak_cur / 7) * 100)
    streak_bar = _progress_bar(week_pct, 7)
    
    # 4. Recent Activity
    recent_txs = await list_last(db, user_id, limit=3)
    
    # 5. Budgets / Projections
    tz_obj, _ = _safe_tz(tz_name)
    current_month_key = f"{now_utc.astimezone(tz_obj).year:04d}-{now_utc.astimezone(tz_obj).month:02d}"
    limits = await month_limits_status_map(db, user_id, current_month_key)
    
    total_limit = sum(int(cat["limit"]) for cat in limits.values()) if limits else 0
    total_spent_limit = sum(int(cat["spent"]) for cat in limits.values()) if limits else 0
    budget_pct = (total_spent_limit / total_limit * 100) if total_limit > 0 else 0
    budget_bar = _progress_bar(budget_pct, 10)
    
    # 6. Smart Suggestion
    suggestion = await build_smart_suggestion(db, user_id, lang)
    
    from app.domain.money import get_user_currency, get_symbol
    
    if lang == "en":
        title = "📈 <b>FINANCIAL PULSE</b>\n━━━━━━━━━━━━━━"
        nw_text = f"🏦 Net Worth: <b>{_fmt_money(total_balance)}</b>"
        cf_title = "📊 <b>CASHFLOW</b>"
        cf_day = f"• Today: +{_fmt_money(day_inc)} / -{_fmt_money(day_exp)}"
        cf_month = f"• Month: +{_fmt_money(income)} / -{_fmt_money(expense)}\n• Net: <b>{_delta_str(net)}</b>"
        
        act_title = "⚡ <b>RECENT ACTIVITY</b>"
        act_lines = []
        for tx in recent_txs:
            amt = int(tx[4])
            sign = "+" if tx[3] == "income" else "-"
            act_lines.append(f"• {sign}{_fmt_money(amt)} {tx[7] or 'Ops'}")
        if not act_lines:
            act_lines.append("• No recent transactions")
            
        bud_title = "🎯 <b>MONTHLY PROJECTIONS</b>"
        if total_limit > 0:
            bud_text = f"• Budget: <code>{budget_bar}</code> {budget_pct:.0f}%\n• Left: <b>{_fmt_money(total_limit - total_spent_limit)}</b>"
        else:
            bud_text = "• No limits set. Add budgets to see projections."
            
        gam_title = "🔥 <b>DISCIPLINE STREAK</b>"
        gam_text = f"• <code>{streak_bar}</code> <b>{streak_cur}</b> days (Best: {streak_best})"
    elif lang == "kk":
        title = "📈 <b>ҚАРЖЫЛЫҚ ПУЛЬС</b>\n━━━━━━━━━━━━━━"
        nw_text = f"🏦 Жалпы жағдай: <b>{_fmt_money(total_balance)}</b>"
        cf_title = "📊 <b>АЙНАЛЫМ</b>"
        cf_day = f"• Бүгін: +{_fmt_money(day_inc)} / -{_fmt_money(day_exp)}"
        cf_month = f"• Осы ай: +{_fmt_money(income)} / -{_fmt_money(expense)}\n• Таза: <b>{_delta_str(net)}</b>"
        
        act_title = "⚡ <b>СОҢҒЫ ОПЕРАЦИЯЛАР</b>"
        act_lines = []
        for tx in recent_txs:
            amt = int(tx[4])
            sign = "+" if tx[3] == "income" else "-"
            act_lines.append(f"• {sign}{_fmt_money(amt)} {tx[7] or 'Операция'}")
        if not act_lines:
            act_lines.append("• Операциялар жоқ")
            
        bud_title = "🎯 <b>БЮДЖЕТ БОЛЖАМЫ</b>"
        if total_limit > 0:
            bud_text = f"• Бюджет: <code>{budget_bar}</code> {budget_pct:.0f}%\n• Қалдық: <b>{_fmt_money(total_limit - total_spent_limit)}</b>"
        else:
            bud_text = "• Лимиттер орнатылмаған."
            
        gam_title = "🔥 <b>ДИСЦИПЛИНА</b>"
        gam_text = f"• <code>{streak_bar}</code> <b>{streak_cur}</b> күн (Үздік: {streak_best})"
    else:
        title = "📈 <b>ФИНАНСОВЫЙ ПУЛЬС</b>\n━━━━━━━━━━━━━━"
        nw_text = f"🏦 Капитал: <b>{_fmt_money(total_balance)}</b>"
        cf_title = "📊 <b>ДЕНЕЖНЫЙ ПОТОК</b>"
        cf_day = f"• Сегодня: +{_fmt_money(day_inc)} / -{_fmt_money(day_exp)}"
        cf_month = f"• За месяц: +{_fmt_money(income)} / -{_fmt_money(expense)}\n• Итог: <b>{_delta_str(net)}</b>"
        
        act_title = "⚡ <b>ПОСЛЕДНЯЯ АКТИВНОСТЬ</b>"
        act_lines = []
        for tx in recent_txs:
            amt = int(tx[4])
            sign = "+" if tx[3] == "income" else "-"
            act_lines.append(f"• {sign}{_fmt_money(amt)} {tx[7] or 'Операция'}")
        if not act_lines:
            act_lines.append("• Нет недавних операций")
            
        bud_title = "🎯 <b>ПРОГНОЗЫ И БЮДЖЕТ</b>"
        if total_limit > 0:
            bud_text = f"• Бюджет: <code>{budget_bar}</code> {budget_pct:.0f}%\n• Остаток: <b>{_fmt_money(total_limit - total_spent_limit)}</b>"
        else:
            bud_text = "• Бюджеты не заданы. Добавьте лимиты для прогноза."
            
        gam_title = "🔥 <b>ДИСЦИПЛИНА</b>"
        gam_text = f"• <code>{streak_bar}</code> <b>{streak_cur}</b> дн. (Лучшая: {streak_best})"

    lines = [
        title,
        nw_text,
        "",
        cf_title,
        cf_day,
        cf_month,
        "",
        act_title,
        *act_lines,
        "",
        bud_title,
        bud_text,
        "",
        gam_title,
        gam_text,
    ]
    if suggestion:
        lines.extend(["", suggestion])

    return "\n".join(lines)


async def _show_reports_hub(m: Message, state: FSMContext, db: aiosqlite.Connection) -> None:
    data = await state.get_data()
    lang = await get_lang(db, m.from_user.id)
    
    # 1. Cleanup old UI noise
    await _cleanup_ui(m.bot, m.chat.id, data)
    try:
        await m.delete()
    except Exception:
        pass
        
    await state.clear()
    
    # 2. Ensure minimized bottom menu (the 🏠 Menu button)
    await _ensure_minimized_menu(m, state, lang)
    
    # 3. Send fresh report hub
    text = await _reports_hub_text(db, m.from_user.id, lang)
    kb = reports_kb(lang)
    
    rendered = await m.answer(
        text,
        reply_markup=kb,
        parse_mode=PARSE_MODE
    )
    if rendered:
        await state.update_data(flow_message_id=rendered.message_id, ui_scope="reports", lang=lang)


async def _open_period_report(m: Message, state: FSMContext, db: aiosqlite.Connection, period: str) -> None:
    data = await state.get_data()
    lang = await get_lang(db, m.from_user.id)
    
    # Cleanup pattern matching planning hub
    await _cleanup_ui(m.bot, m.chat.id, data)
    try:
        await m.delete()
    except Exception:
        pass
        
    await state.clear()
    await _ensure_minimized_menu(m, state, lang)
    
    await _render_report(
        m,
        db,
        m.from_user.id,
        period=period,
        show_categories=False,
        prefer_edit=False,
        state=state,
    )


async def _render_streak(m: Message, db: aiosqlite.Connection, user_id: int, *, prefer_edit: bool, state: FSMContext | None = None):
    lang = await get_lang(db, user_id)
    labels = _labels(lang)
    streak_cur, streak_best, _ = await get_streak(db, user_id)

    lines = [
        labels["streak_title"],
        "",
        labels["streak_about"],
        "",
        _build_streak_line(lang, streak_cur, streak_best),
    ]

    hint = await build_section_hint(db, user_id, "reports", lang)
    if hint:
        lines += ["", hint]

    rendered = await _edit_or_answer(m, db, "\n".join(lines), reply_markup=_streak_kb(lang), prefer_edit=prefer_edit)
    if state is not None and rendered is not None:
        await state.update_data(flow_message_id=rendered.message_id, ui_scope="reports")


@router.message(lambda m: text_matches_key(getattr(m, "text", None), "BTN_REPORT"))
async def report_menu(m: Message, db: aiosqlite.Connection, state: FSMContext):
    if not await can_use_feature(db, m.from_user.id, FEATURE_REPORTS):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await _show_reports_hub(m, state, db)


@router.message(Command("day"))
@router.message(Command("today"))
@router.message(F.text.regexp(r"^/сегодня(@\w+)?$"))
async def today_cmd(m: Message, db: aiosqlite.Connection, state: FSMContext):
    if not await can_use_feature(db, m.from_user.id, FEATURE_REPORTS):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await _open_period_report(m, state, db, "day")


@router.message(Command("week"))
@router.message(F.text.regexp(r"^/неделя(@\w+)?$"))
async def week_cmd(m: Message, db: aiosqlite.Connection, state: FSMContext):
    if not await can_use_feature(db, m.from_user.id, FEATURE_REPORTS):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await _open_period_report(m, state, db, "week")


@router.message(Command("month"))
@router.message(F.text.regexp(r"^/месяц(@\w+)?$"))
async def month_cmd(m: Message, db: aiosqlite.Connection, state: FSMContext):
    if not await can_use_feature(db, m.from_user.id, FEATURE_REPORTS):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await _open_period_report(m, state, db, "month")


@router.message(Command("cats_today"))
async def cats_today_cmd(m: Message, db: aiosqlite.Connection, state: FSMContext):
    if not await can_use_feature(db, m.from_user.id, FEATURE_REPORTS):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await _render_report(m, db, m.from_user.id, period="day", show_categories=True, prefer_edit=False, state=state)


@router.message(Command("cats_month"))
async def cats_month_cmd(m: Message, db: aiosqlite.Connection, state: FSMContext):
    if not await can_use_feature(db, m.from_user.id, FEATURE_REPORTS):
        await deny_feature_message(m, db, m.from_user.id)
        return
    await _render_report(m, db, m.from_user.id, period="month", show_categories=True, prefer_edit=False, state=state)


@router.callback_query(F.data.startswith("rp:") & (F.data != "rp:export"))
async def reports_cb(c: CallbackQuery, db: aiosqlite.Connection, state: FSMContext):
    await c.answer()
    user_id = c.from_user.id

    if c.data == "rp:to_menu":
        await neutralize_keyboard(c)
        await cancel_to_main_menu(c, state, db)
        return

    if c.data == "rp:streak":
        await _render_streak(c.message, db, user_id, prefer_edit=True, state=state)
        return

    if c.data == "rp:hub":
        lang = await get_lang(db, c.from_user.id)
        rendered = await _edit_or_answer(
            c.message,
            db,
            await _reports_hub_text(db, c.from_user.id, lang),
            reply_markup=reports_kb(lang),
            prefer_edit=True,
        )
        if state is not None and rendered is not None:
            await state.update_data(flow_message_id=rendered.message_id, ui_scope="reports")
        return

    legacy_map = {
        "rp:today": ("day", False),
        "rp:week": ("week", False),
        "rp:month": ("month", False),
        "rp:cats_today": ("day", True),
        "rp:cats_month": ("month", True),
    }
    if c.data in legacy_map:
        period, show_categories = legacy_map[c.data]
        await _render_report(c.message, db, user_id, period=period, show_categories=show_categories, prefer_edit=True, state=state)
        return

    if c.data.startswith("rp:view:"):
        parts = c.data.split(":")
        if len(parts) != 4:
            return

        period = parts[2]
        show_categories = parts[3] == "1"
        if period not in {"day", "week", "month"}:
            return

        await _render_report(c.message, db, user_id, period=period, show_categories=show_categories, prefer_edit=True, state=state)


async def _render_report(
    m: Message,
    db: aiosqlite.Connection,
    user_id: int,
    *,
    period: str,
    show_categories: bool,
    prefer_edit: bool,
    state: FSMContext | None = None,
):
    lang = await get_lang(db, user_id)
    labels = _labels(lang)
    tz_name = await get_timezone(db, user_id)
    now_utc = datetime.now(timezone.utc)

    meta = _period_meta(lang, tz_name, period, now_utc)
    start = meta["start"]
    end = meta["end"]
    prev_start = meta["prev_start"]
    prev_end = meta["prev_end"]
    title = meta["title"]
    compare_title = meta["compare_title"]

    inc, exp, cnt = await report_period(db, user_id, start, end)
    p_inc, p_exp, _ = await report_period(db, user_id, prev_start, prev_end)
    cats = await report_by_category(db, user_id, start, end, "expense", TOP_CATS_EXPANDED)
    streak_cur, streak_best, _ = await get_streak(db, user_id)

    net = inc - exp
    
    cur_exp_cnt = await db.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id=? AND type='expense' AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, iso(start), iso(end))
    )
    cnt_expense = (await cur_exp_cnt.fetchone())[0] or 0
    avg_exp = int(exp / cnt_expense) if cnt_expense > 0 and exp > 0 else 0
    d_inc = inc - p_inc
    d_exp = exp - p_exp

    lines: list[str] = [
        title,
        "",
        labels["finance_block"],
        f"• {labels['income']}: <b>{_fmt_money(inc)}</b>",
        f"• {labels['expense']}: <b>{_fmt_money(exp)}</b>",
        f"• {labels['net']}: <b>{_delta_str(net)}</b>",
        "",
        labels["activity_block"],
        f"• {labels['ops']}: {cnt}",
    ]

    if exp > 0:
        lines.append(f"• {labels['avg_check']}: {_fmt_money(avg_exp)}")

    if p_inc != 0 or p_exp != 0:
        lines += [
            "",
            compare_title,
            f"• {labels['income']}: {_arrow(d_inc)} {_delta_str(d_inc)} ({_delta_pct_str(inc, p_inc)})",
            f"• {labels['expense']}: {_arrow(d_exp)} {_delta_str(d_exp)} ({_delta_pct_str(exp, p_exp)})",
        ]

    if period == "month":
        month_plan = await _month_plan_snapshot(db, user_id, tz_name, end)
        lines += _build_month_plan_lines(lang, month_plan)

    if show_categories:
        lines += _build_categories_lines(lang, exp, cats, expanded=True)

    hint = await build_section_hint(db, user_id, "reports", lang)
    if hint:
        lines += ["", hint]

    lines += ["", labels["streak_title"], _build_streak_line(lang, streak_cur, streak_best)]

    caption = "\n".join(lines)
    show_chart = show_categories and exp > 0 and len(cats) > 0
    reply_markup = _report_kb(lang, period, show_categories)
    is_photo = bool(m.photo)

    if show_chart:
        from app.domain.services.chart_service import draw_expense_donut_chart
        formatted_total = f"-{_fmt_money(exp)}"
        chart_buf = draw_expense_donut_chart(cats, exp, formatted_total, lang)
        file_input = BufferedInputFile(chart_buf.getvalue(), filename="chart.png")

        # Truncate caption if it exceeds 1024 characters (Telegram limitation)
        if len(caption) > 1000:
            caption = caption[:997] + "..."

        if is_photo:
            if prefer_edit:
                try:
                    rendered = await m.edit_media(
                        media=InputMediaPhoto(media=file_input, caption=caption, parse_mode=PARSE_MODE),
                        reply_markup=reply_markup
                    )
                except Exception:
                    try:
                        await m.delete()
                    except Exception:
                        pass
                    rendered = await m.answer_photo(photo=file_input, caption=caption, reply_markup=reply_markup, parse_mode=PARSE_MODE)
            else:
                rendered = await m.answer_photo(photo=file_input, caption=caption, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        else:
            if prefer_edit:
                try:
                    await m.delete()
                except Exception:
                    pass
            rendered = await m.answer_photo(photo=file_input, caption=caption, reply_markup=reply_markup, parse_mode=PARSE_MODE)
    else:
        if is_photo:
            try:
                await m.delete()
            except Exception:
                pass
            rendered = await m.answer(caption, reply_markup=reply_markup, parse_mode=PARSE_MODE)
        else:
            rendered = await _edit_or_answer(
                m,
                db,
                caption,
                reply_markup=reply_markup,
                prefer_edit=prefer_edit,
            )

    if state is not None and rendered is not None:
        await state.update_data(flow_message_id=rendered.message_id, ui_scope="reports")
