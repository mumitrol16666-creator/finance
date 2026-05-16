"""PNG charts: daily expense dynamics + top categories pie.

Triggered by ``/chart`` — uses matplotlib in a non-interactive backend so it
works on headless servers. Falls back to a plain text summary if matplotlib
is missing (e.g. on first deploy before pip install).
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repositories.settings_repo import get_lang, get_settings
from app.domain.services.reports_service import iso
from app.domain.time_utils import now_in_user_tz

router = Router()


def _row_get(row, key: str, index: int, *, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        pass
    try:
        return row[index]
    except (IndexError, TypeError):
        return default


def _chart_menu_kb(lang: str):
    kb = InlineKeyboardBuilder()
    labels = {
        "ru": {"week": "📊 За неделю", "month": "📊 За месяц", "cats": "🥧 По категориям (месяц)", "cancel": "❌ Отмена"},
        "en": {"week": "📊 Last 7 days", "month": "📊 Last 30 days", "cats": "🥧 Categories (month)", "cancel": "❌ Cancel"},
        "kk": {"week": "📊 Аптада", "month": "📊 Айда", "cats": "🥧 Санаттар (ай)", "cancel": "❌ Бас тарту"},
    }
    L = labels.get(lang, labels["ru"])
    kb.button(text=L["week"], callback_data="chart:dyn:7")
    kb.button(text=L["month"], callback_data="chart:dyn:30")
    kb.button(text=L["cats"], callback_data="chart:cats")
    kb.button(text=L["cancel"], callback_data="cancel")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


async def _fetch_daily_totals(
    db: aiosqlite.Connection, user_id: int, days: int, tz_name: str, end_local: datetime,
) -> list[tuple[str, int, int]]:
    """Return (YYYY-MM-DD, expense, income) tuples, one per local day.

    Per-day SQL aggregation is fine for short windows (≤60 days) — we keep it
    simple and avoid a single complex CTE.
    """
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc

    start_local = (end_local - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows: list[tuple[str, int, int]] = []
    cursor_date = start_local
    while cursor_date.date() <= end_local.date():
        local_start = datetime(cursor_date.year, cursor_date.month, cursor_date.day, 0, 0, 0, tzinfo=tz)
        local_end = local_start + timedelta(days=1)
        start_utc = local_start.astimezone(timezone.utc)
        end_utc = local_end.astimezone(timezone.utc)
        cur = await db.execute(
            "SELECT "
            "  COALESCE(SUM(CASE WHEN type='expense' THEN -amount ELSE 0 END), 0) AS expense, "
            "  COALESCE(SUM(CASE WHEN type='income' THEN amount ELSE 0 END), 0) AS income "
            "FROM transactions "
            "WHERE user_id=? AND ts>=? AND ts<? AND deleted_at IS NULL",
            (user_id, iso(start_utc), iso(end_utc)),
        )
        row = await cur.fetchone()
        rows.append((cursor_date.strftime("%Y-%m-%d"), int(row[0] or 0), int(row[1] or 0)))
        cursor_date = cursor_date + timedelta(days=1)
    return rows


def _build_dynamics_png(rows: list[tuple[str, int, int]], lang: str, currency: str) -> bytes | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    dates = [r[0] for r in rows]
    expenses = [r[1] for r in rows]
    incomes = [r[2] for r in rows]
    short_labels = [d[-5:] for d in dates]

    title_by_lang = {
        "ru": f"Динамика операций ({currency})",
        "en": f"Dynamics ({currency})",
        "kk": f"Динамика ({currency})",
    }
    legend_expense = {"ru": "Расход", "en": "Expense", "kk": "Шығыс"}.get(lang, "Расход")
    legend_income = {"ru": "Доход", "en": "Income", "kk": "Кіріс"}.get(lang, "Доход")

    fig, ax = plt.subplots(figsize=(10, 5), dpi=140)
    ax.bar(short_labels, expenses, color="#E53E3E", alpha=0.85, label=legend_expense)
    ax.bar(short_labels, incomes, color="#38A169", alpha=0.6, label=legend_income, bottom=0)
    ax.set_title(title_by_lang.get(lang, title_by_lang["ru"]))
    ax.set_ylabel(currency)
    ax.grid(True, axis="y", alpha=0.2)
    ax.legend()
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


async def _fetch_top_categories(
    db: aiosqlite.Connection, user_id: int, tz_name: str, now_local: datetime, limit: int = 8,
) -> list[tuple[str, int]]:
    """Categories aggregated for the user's current local month."""
    from app.domain.services.reports_service import month_bounds_utc
    start_utc, end_utc, _, _ = month_bounds_utc(tz_name, datetime.now(timezone.utc))
    cur = await db.execute(
        "SELECT COALESCE(c.name, ?) AS name, SUM(-t.amount) AS total "
        "FROM transactions t LEFT JOIN categories c ON c.id=t.category_id "
        "WHERE t.user_id=? AND t.type='expense' AND t.ts>=? AND t.ts<? AND t.deleted_at IS NULL "
        "GROUP BY name ORDER BY total DESC LIMIT ?",
        ("—", user_id, iso(start_utc), iso(end_utc), limit),
    )
    return [(str(r[0] or "—"), int(r[1] or 0)) for r in await cur.fetchall()]


def _build_categories_pie(rows: list[tuple[str, int]], lang: str, currency: str) -> bytes | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    if not rows:
        return None

    title_by_lang = {
        "ru": f"Структура расходов за месяц ({currency})",
        "en": f"Expense breakdown this month ({currency})",
        "kk": f"Айдағы шығыстар құрылымы ({currency})",
    }

    labels = [r[0] for r in rows]
    values = [r[1] for r in rows]

    fig, ax = plt.subplots(figsize=(8, 8), dpi=140)
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
    ax.set_title(title_by_lang.get(lang, title_by_lang["ru"]))
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


@router.message(Command("chart"))
async def chart_entry(m: Message, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)
    prompt = {
        "ru": "📊 <b>Графики</b>\n\nЧто построить?",
        "en": "📊 <b>Charts</b>\n\nWhat to draw?",
        "kk": "📊 <b>Графиктер</b>\n\nНе салу керек?",
    }.get(lang, "📊 <b>Графики</b>\n\nЧто построить?")
    await m.answer(prompt, reply_markup=_chart_menu_kb(lang), parse_mode="HTML")


@router.callback_query(F.data.startswith("chart:dyn:"))
async def chart_dynamics(c: CallbackQuery, db: aiosqlite.Connection):
    try:
        days = int((c.data or "chart:dyn:7").split(":")[2])
    except (ValueError, IndexError):
        days = 7
    days = max(2, min(60, days))

    user_id = c.from_user.id
    lang = await get_lang(db, user_id)
    settings = await get_settings(db, user_id)
    currency = _row_get(settings, "currency", 0, default="KZT")
    tz_name = _row_get(settings, "timezone", 1, default="Asia/Aqtobe")

    now_local = await now_in_user_tz(db, user_id)
    rows = await _fetch_daily_totals(db, user_id, days, tz_name, now_local)

    try:
        await c.answer({"ru": "Рисую…", "en": "Drawing…", "kk": "Сурет салынуда…"}.get(lang, "Рисую…"))
    except Exception:
        pass

    png = _build_dynamics_png(rows, lang, currency)
    if png is None:
        # matplotlib missing — fall back to a textual list so the feature still works.
        text_rows = [f"{d}: -{exp} / +{inc}" for d, exp, inc in rows]
        await c.message.answer("\n".join(text_rows) or "—")
        return

    await c.message.answer_document(BufferedInputFile(png, filename=f"dynamics_{days}d.png"))


@router.callback_query(F.data == "chart:cats")
async def chart_categories(c: CallbackQuery, db: aiosqlite.Connection):
    user_id = c.from_user.id
    lang = await get_lang(db, user_id)
    settings = await get_settings(db, user_id)
    currency = _row_get(settings, "currency", 0, default="KZT")
    tz_name = _row_get(settings, "timezone", 1, default="Asia/Aqtobe")

    now_local = await now_in_user_tz(db, user_id)
    rows = await _fetch_top_categories(db, user_id, tz_name, now_local)

    if not rows:
        await c.answer(
            {"ru": "Нет данных за месяц.", "en": "No data for this month.", "kk": "Бұл айда дерек жоқ."}.get(lang, "Нет данных за месяц."),
            show_alert=True,
        )
        return

    try:
        await c.answer({"ru": "Рисую…", "en": "Drawing…", "kk": "Сурет салынуда…"}.get(lang, "Рисую…"))
    except Exception:
        pass

    png = _build_categories_pie(rows, lang, currency)
    if png is None:
        text_rows = [f"• {n} — {v}" for n, v in rows]
        await c.message.answer("\n".join(text_rows))
        return

    await c.message.answer_document(BufferedInputFile(png, filename="categories.png"))
