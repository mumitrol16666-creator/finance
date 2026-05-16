"""Excel + CSV export of transactions for a chosen period.

Triggered by ``/export`` — the user gets an inline keyboard to pick the period
(today / week / month / all). The result is sent as an in-memory XLSX so we
don't hit disk. CSV is offered as a fallback for users whose phones don't
preview XLSX nicely.

This module is intentionally self-contained: no FSM state, no schema changes.
Reuses ``reports_service`` time helpers so the period bounds respect the
user's timezone.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Iterable

import aiosqlite
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.db.repositories.settings_repo import get_lang, get_settings
from app.domain.services.reports_service import day_bounds_utc, month_bounds_utc, iso
from app.domain.time_utils import now_in_user_tz
from app.ui.i18n import t

router = Router()


def _row_get(row, key: str, index: int, *, default=None):
    """Read a column from an aiosqlite.Row | dict | tuple, with a default."""
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


async def _fetch_rows(
    db: aiosqlite.Connection,
    user_id: int,
    start_iso: str | None,
    end_iso: str | None,
) -> list[tuple]:
    """Pull live (non-deleted) transactions joined with account & category."""
    sql = (
        "SELECT t.id, t.ts, t.type, t.amount, "
        "       COALESCE(a.name, '') AS account, "
        "       COALESCE(c.name, '') AS category, "
        "       COALESCE(c.emoji, '') AS emoji, "
        "       COALESCE(t.note, '') AS note "
        "FROM transactions t "
        "LEFT JOIN accounts a ON a.id = t.account_id "
        "LEFT JOIN categories c ON c.id = t.category_id "
        "WHERE t.user_id=? AND t.deleted_at IS NULL "
    )
    params: list = [user_id]
    if start_iso is not None:
        sql += "AND t.ts>=? "
        params.append(start_iso)
    if end_iso is not None:
        sql += "AND t.ts<? "
        params.append(end_iso)
    sql += "ORDER BY t.ts ASC, t.id ASC"
    cur = await db.execute(sql, params)
    return await cur.fetchall()


def _build_xlsx(rows: Iterable[tuple], lang: str, currency: str) -> bytes | None:
    """Render rows into an XLSX byte string.

    Returns ``None`` when ``openpyxl`` is not installed (graceful fallback to CSV).
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
    except ImportError:
        return None

    headers_by_lang = {
        "ru": ["ID", "Дата (UTC)", "Тип", "Сумма", "Валюта", "Счёт", "Категория", "Комментарий"],
        "en": ["ID", "Date (UTC)", "Type", "Amount", "Currency", "Account", "Category", "Note"],
        "kk": ["ID", "Күні (UTC)", "Түрі", "Сома", "Валюта", "Шот", "Санат", "Түсініктеме"],
    }
    headers = headers_by_lang.get(lang, headers_by_lang["ru"])

    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(headers)

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="2D3748", end_color="2D3748", fill_type="solid")
    center = Alignment(horizontal="center", vertical="center")
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center

    for r in rows:
        tx_id, ts, ttype, amount, account, category, emoji, note = r
        cat_display = f"{emoji} {category}".strip() if emoji or category else ""
        ws.append([
            int(tx_id),
            str(ts or ""),
            str(ttype or ""),
            int(amount or 0),
            currency,
            str(account or ""),
            cat_display,
            str(note or ""),
        ])

    widths = [6, 22, 10, 14, 8, 18, 22, 40]
    for col_idx, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(ord("A") + col_idx - 1)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_csv(rows: Iterable[tuple], lang: str, currency: str) -> bytes:
    headers_by_lang = {
        "ru": ["ID", "Дата (UTC)", "Тип", "Сумма", "Валюта", "Счёт", "Категория", "Комментарий"],
        "en": ["ID", "Date (UTC)", "Type", "Amount", "Currency", "Account", "Category", "Note"],
        "kk": ["ID", "Күні (UTC)", "Түрі", "Сома", "Валюта", "Шот", "Санат", "Түсініктеме"],
    }
    headers = headers_by_lang.get(lang, headers_by_lang["ru"])

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    for r in rows:
        tx_id, ts, ttype, amount, account, category, emoji, note = r
        cat_display = f"{emoji} {category}".strip() if emoji or category else ""
        writer.writerow([tx_id, ts, ttype, int(amount or 0), currency, account, cat_display, note])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _export_menu_kb(lang: str):
    kb = InlineKeyboardBuilder()
    labels = {
        "ru": {"day": "📅 За сегодня", "week": "📆 За неделю", "month": "🗓 За месяц", "all": "🗂 Всё", "cancel": "❌ Отмена"},
        "en": {"day": "📅 Today", "week": "📆 Week", "month": "🗓 Month", "all": "🗂 All", "cancel": "❌ Cancel"},
        "kk": {"day": "📅 Бүгін", "week": "📆 Апта", "month": "🗓 Ай", "all": "🗂 Барлығы", "cancel": "❌ Бас тарту"},
    }
    L = labels.get(lang, labels["ru"])
    for key in ("day", "week", "month", "all"):
        kb.button(text=L[key], callback_data=f"export:{key}")
    kb.button(text=L["cancel"], callback_data="cancel")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


async def _resolve_period(db: aiosqlite.Connection, user_id: int, period: str) -> tuple[str | None, str | None, str]:
    """Return (start_utc_iso, end_utc_iso, label) for the requested period."""
    if period == "all":
        return None, None, "all-time"

    now_local = await now_in_user_tz(db, user_id)
    settings = await get_settings(db, user_id)
    tz_name = _row_get(settings, "timezone", 1, default="Asia/Aqtobe")
    now_utc = datetime.now(timezone.utc)

    if period == "day":
        start, end, _, _ = day_bounds_utc(tz_name, now_utc)
        label = now_local.strftime("%Y-%m-%d")
    elif period == "week":
        start_day = (now_local - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        start = start_day.astimezone(timezone.utc)
        end = (now_local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        label = f"{start_day.strftime('%Y-%m-%d')}_{now_local.strftime('%Y-%m-%d')}"
    else:  # month
        start, end, _, _ = month_bounds_utc(tz_name, now_utc)
        label = now_local.strftime("%Y-%m")

    return iso(start), iso(end), label


@router.message(Command("export"))
async def export_entry(m: Message, db: aiosqlite.Connection):
    lang = await get_lang(db, m.from_user.id)
    prompt = {
        "ru": "📤 <b>Экспорт операций</b>\n\nВыбери период:",
        "en": "📤 <b>Export transactions</b>\n\nPick a period:",
        "kk": "📤 <b>Операцияларды экспорттау</b>\n\nКезеңді таңда:",
    }.get(lang, "📤 <b>Экспорт операций</b>\n\nВыбери период:")
    await m.answer(prompt, reply_markup=_export_menu_kb(lang), parse_mode="HTML")


@router.callback_query(F.data.startswith("export:"))
async def export_pick(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection):
    period = (c.data or "").split(":")[1]
    if period not in {"day", "week", "month", "all"}:
        await c.answer()
        return

    user_id = c.from_user.id
    lang = await get_lang(db, user_id)
    settings = await get_settings(db, user_id)
    currency = _row_get(settings, "currency", 0, default="KZT")

    try:
        start_iso, end_iso, label = await _resolve_period(db, user_id, period)
    except Exception:
        await c.answer("Period error", show_alert=True)
        return

    rows = await _fetch_rows(db, user_id, start_iso, end_iso)
    if not rows:
        empty_text = {
            "ru": "За выбранный период нет операций.",
            "en": "No transactions for the selected period.",
            "kk": "Таңдалған кезеңде операциялар жоқ.",
        }.get(lang, "За выбранный период нет операций.")
        await c.answer(empty_text, show_alert=True)
        return

    # Acknowledge immediately so the spinner clears while we build the file.
    try:
        await c.answer({"ru": "Готовлю файл…", "en": "Building…", "kk": "Файл әзірленуде…"}.get(lang, "Готовлю файл…"))
    except Exception:
        pass

    payload = _build_xlsx(rows, lang, currency)
    if payload is not None:
        filename = f"finance_{label}.xlsx"
        await c.message.answer_document(BufferedInputFile(payload, filename=filename))
    else:
        filename = f"finance_{label}.csv"
        await c.message.answer_document(BufferedInputFile(_build_csv(rows, lang, currency), filename=filename))
