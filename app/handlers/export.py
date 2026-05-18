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


def _build_xlsx(rows: Iterable[tuple], lang: str, currency: str, user_id: int = 0) -> bytes | None:
    """Render rows into a beautifully formatted, printable multi-sheet Excel workbook.
    
    Includes a "Dashboard" sheet with summary cards, monthly breakdown, category breakdown
    and two gorgeous matplotlib charts embedded as images (for flawless mobile/Telegram display),
    plus a detailed "Transactions" sheet.
    
    Returns ``None`` when required packages are not installed.
    """
    try:
        import collections
        import io
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
        from openpyxl.drawing.image import Image
        
        import matplotlib
        matplotlib.use('Agg')  # Headless backend to prevent server-side GUI threads
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    # 1. Localized catalog
    all_labels = {
        "ru": {
            "title": "📊 ФИНАНСОВАЯ АНАЛИТИКА",
            "total_income": "ВСЕГО ДОХОДОВ",
            "total_expense": "ВСЕГО РАСХОДОВ",
            "net_balance": "ЧИСТЫЙ БАЛАНС",
            "monthly_title": "Динамика по месяцам",
            "col_month": "Месяц",
            "col_income": "Доходы",
            "col_expense": "Расходы",
            "col_net": "Чистый доход",
            "col_savings": "Сбережения %",
            "category_title": "Расходы по категориям",
            "col_category": "Категория",
            "col_spent": "Потрачено",
            "col_share": "Доля %",
            "total": "Итого",
            "chart_monthly_title": "Динамика доходов и расходов",
            "chart_category_title": "Структура расходов по категориям",
            "sheet_dashboard": "Аналитика",
            "sheet_transactions": "История операций",
            "raw_headers": ["ID", "Дата (UTC)", "Тип", "Сумма", "Валюта", "Счёт", "Категория", "Комментарий"]
        },
        "en": {
            "title": "📊 FINANCIAL ANALYTICS",
            "total_income": "TOTAL INCOME",
            "total_expense": "TOTAL EXPENSES",
            "net_balance": "NET BALANCE",
            "monthly_title": "Monthly Cashflow",
            "col_month": "Month",
            "col_income": "Income",
            "col_expense": "Expenses",
            "col_net": "Net Income",
            "col_savings": "Savings %",
            "category_title": "Expenses by Category",
            "col_category": "Category",
            "col_spent": "Spent",
            "col_share": "Share %",
            "total": "Total",
            "chart_monthly_title": "Income vs Expenses Dynamics",
            "chart_category_title": "Expenses Structure by Category",
            "sheet_dashboard": "Analytics",
            "sheet_transactions": "Transaction History",
            "raw_headers": ["ID", "Date (UTC)", "Type", "Amount", "Currency", "Account", "Category", "Note"]
        },
        "kk": {
            "title": "📊 ҚАРЖЫЛЫҚ ТАЛДАУ",
            "total_income": "БАРЛЫҚ КІРІС",
            "total_expense": "БАРЛЫҚ ШЫҒЫС",
            "net_balance": "ТАЗА ҚАЛДЫҚ",
            "monthly_title": "Айлар бойынша динамика",
            "col_month": "Ай",
            "col_income": "Кірістер",
            "col_expense": "Шығыстар",
            "col_net": "Таза кіріс",
            "col_savings": "Жинақ %",
            "category_title": "Санаттар бойынша шығыстар",
            "col_category": "Санат",
            "col_spent": "Жұмсалды",
            "col_share": "Үлесі %",
            "total": "Жиынтығы",
            "chart_monthly_title": "Кірістер мен шығыстар динамикасы",
            "chart_category_title": "Шығыстардың санаттар бойынша құрылымы",
            "sheet_dashboard": "Талдау",
            "sheet_transactions": "Операциялар тарихы",
            "raw_headers": ["ID", "Күні (UTC)", "Түрі", "Сома", "Валюта", "Шот", "Санат", "Түсініктеме"]
        }
    }
    
    L = all_labels.get(lang, all_labels["ru"])

    # 2. Aggregations
    total_income = 0
    total_expense = 0
    monthly_data = collections.defaultdict(lambda: {"income": 0, "expense": 0})
    category_data = collections.defaultdict(int)

    # Convert iterable to stable list
    rows_list = list(rows)

    for r in rows_list:
        tx_id, ts, ttype, amount, account, category, emoji, note = r
        val = abs(int(amount or 0))  # Normalize all amounts to positive absolute values
        
        month_str = "Unknown"
        if ts and len(str(ts)) >= 7:
            month_str = str(ts)[:7]

        if ttype == "income":
            total_income += val
            monthly_data[month_str]["income"] += val
        elif ttype == "expense":
            total_expense += val
            monthly_data[month_str]["expense"] += val
            cat_display = f"{emoji} {category}".strip() if emoji or category else "Other"
            category_data[cat_display] += val

    wb = Workbook()
    wb.properties.calcMode = 'auto'  # Set calculation mode to automatic for Excel standard compliance

    # --- SHEET 1: DASHBOARD ---
    ws = wb.active
    ws.title = L["sheet_dashboard"]
    ws.views.sheetView[0].showGridLines = True

    # Styling Constants
    font_title = Font(name="Segoe UI", size=16, bold=True, color="FFFFFF")
    font_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    font_section = Font(name="Segoe UI", size=13, bold=True, color="1A202C")
    font_data = Font(name="Segoe UI", size=10)
    font_bold = Font(name="Segoe UI", size=10, bold=True)

    fill_title = PatternFill(start_color="2D3748", end_color="2D3748", fill_type="solid")
    fill_header = PatternFill(start_color="4A5568", end_color="4A5568", fill_type="solid")
    fill_zebra = PatternFill(start_color="F7FAFC", end_color="F7FAFC", fill_type="solid")

    thin_side = Side(style='thin', color='E2E8F0')
    thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    double_bottom = Border(top=Side(style='thin', color='CBD5E0'), bottom=Side(style='double', color='2D3748'))

    # Title Block
    ws.merge_cells("A1:K1")
    ws["A1"] = L["title"]
    ws["A1"].font = font_title
    ws["A1"].fill = fill_title
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 40

    # Summary Card 1: Income
    ws.merge_cells("A3:C3")
    ws.merge_cells("A4:C4")
    ws["A3"] = L["total_income"]
    ws["A4"] = total_income
    ws["A3"].font = Font(name="Segoe UI", size=10, bold=True, color="137333")
    ws["A3"].fill = PatternFill(start_color="E6F4EA", end_color="E6F4EA", fill_type="solid")
    ws["A3"].alignment = Alignment(horizontal="center", vertical="center")
    ws["A4"].font = Font(name="Segoe UI", size=16, bold=True, color="137333")
    ws["A4"].fill = PatternFill(start_color="E6F4EA", end_color="E6F4EA", fill_type="solid")
    ws["A4"].alignment = Alignment(horizontal="center", vertical="center")
    ws["A4"].number_format = f'#,##0" {currency}"'

    # Summary Card 2: Expense
    ws.merge_cells("E3:G3")
    ws.merge_cells("E4:G4")
    ws["E3"] = L["total_expense"]
    ws["E4"] = total_expense
    ws["E3"].font = Font(name="Segoe UI", size=10, bold=True, color="C5221F")
    ws["E3"].fill = PatternFill(start_color="FCE8E6", end_color="FCE8E6", fill_type="solid")
    ws["E3"].alignment = Alignment(horizontal="center", vertical="center")
    ws["E4"].font = Font(name="Segoe UI", size=16, bold=True, color="C5221F")
    ws["E4"].fill = PatternFill(start_color="FCE8E6", end_color="FCE8E6", fill_type="solid")
    ws["E4"].alignment = Alignment(horizontal="center", vertical="center")
    ws["E4"].number_format = f'#,##0" {currency}"'

    # Summary Card 3: Net Balance
    ws.merge_cells("I3:K3")
    ws.merge_cells("I4:K4")
    ws["I3"] = L["net_balance"]
    ws["I4"] = total_income - total_expense
    ws["I3"].font = Font(name="Segoe UI", size=10, bold=True, color="1A73E8")
    ws["I3"].fill = PatternFill(start_color="E8F0FE", end_color="E8F0FE", fill_type="solid")
    ws["I3"].alignment = Alignment(horizontal="center", vertical="center")
    ws["I4"].font = Font(name="Segoe UI", size=16, bold=True, color="1A73E8")
    ws["I4"].fill = PatternFill(start_color="E8F0FE", end_color="E8F0FE", fill_type="solid")
    ws["I4"].alignment = Alignment(horizontal="center", vertical="center")
    ws["I4"].number_format = f'#,##0" {currency}"'

    # Add border outlines to summary cards
    for col in ["A", "B", "C", "E", "F", "G", "I", "J", "K"]:
        ws[f"{col}3"].border = Border(top=thin_side, left=thin_side if col in ["A", "E", "I"] else None, right=thin_side if col in ["C", "G", "K"] else None)
        ws[f"{col}4"].border = Border(bottom=thin_side, left=thin_side if col in ["A", "E", "I"] else None, right=thin_side if col in ["C", "G", "K"] else None)

    # Row Heights
    ws.row_dimensions[3].height = 20
    ws.row_dimensions[4].height = 28

    # --- TABLE 1: MONTHLY CASHFLOW ---
    ws["A6"] = L["monthly_title"]
    ws["A6"].font = font_section
    ws.row_dimensions[6].height = 24

    headers_m = [L["col_month"], L["col_income"], L["col_expense"], L["col_net"], L["col_savings"]]
    for col_idx, h in enumerate(headers_m, start=1):
        cell = ws.cell(row=7, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    sorted_months = sorted(list(monthly_data.keys()))
    row_idx = 8
    for m_str in sorted_months:
        inc = monthly_data[m_str]["income"]
        exp = monthly_data[m_str]["expense"]
        
        # Pre-calculated values for absolute compatibility across all devices
        net_val = inc - exp
        sav_val = net_val / inc if inc > 0 else 0
        
        ws.cell(row=row_idx, column=1, value=m_str).alignment = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=2, value=inc)
        ws.cell(row=row_idx, column=3, value=exp)
        ws.cell(row=row_idx, column=4, value=net_val)
        ws.cell(row=row_idx, column=5, value=sav_val)
        
        ws.cell(row=row_idx, column=2).number_format = '#,##0'
        ws.cell(row=row_idx, column=3).number_format = '#,##0'
        ws.cell(row=row_idx, column=4).number_format = '#,##0'
        ws.cell(row=row_idx, column=5).number_format = '0.0%'
        
        for c in range(1, 6):
            cell = ws.cell(row=row_idx, column=c)
            cell.font = font_data
            cell.border = thin_border
            if row_idx % 2 == 1:
                cell.fill = fill_zebra
        row_idx += 1

    # Total Row for Monthly Table
    monthly_net_total = total_income - total_expense
    monthly_sav_total = monthly_net_total / total_income if total_income > 0 else 0

    ws.cell(row=row_idx, column=1, value=L["total"]).font = font_bold
    ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal="center")
    ws.cell(row=row_idx, column=2, value=total_income).font = font_bold
    ws.cell(row=row_idx, column=3, value=total_expense).font = font_bold
    ws.cell(row=row_idx, column=4, value=monthly_net_total).font = font_bold
    ws.cell(row=row_idx, column=5, value=monthly_sav_total).font = font_bold
    
    ws.cell(row=row_idx, column=2).number_format = '#,##0'
    ws.cell(row=row_idx, column=3).number_format = '#,##0'
    ws.cell(row=row_idx, column=4).number_format = '#,##0'
    ws.cell(row=row_idx, column=5).number_format = '0.0%'
    
    for c in range(1, 6):
        cell = ws.cell(row=row_idx, column=c)
        cell.border = double_bottom
        
    last_month_row = row_idx

    # --- TABLE 2: CATEGORY BREAKDOWN ---
    ws["H6"] = L["category_title"]
    ws["H6"].font = font_section

    headers_c = [L["col_category"], L["col_spent"], L["col_share"]]
    for col_idx, h in enumerate(headers_c, start=8): # H=8, I=9, J=10
        cell = ws.cell(row=7, column=col_idx, value=h)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    sorted_cats = sorted(category_data.items(), key=lambda x: x[1], reverse=True)
    c_row_idx = 8
    total_category_spent = sum(category_data.values())
    
    if sorted_cats:
        for cat_name, spent in sorted_cats:
            ws.cell(row=c_row_idx, column=8, value=cat_name)
            ws.cell(row=c_row_idx, column=9, value=spent)
            
            # Pre-calculated share for bulletproof compatibility
            share_val = spent / total_category_spent if total_category_spent > 0 else 0
            ws.cell(row=c_row_idx, column=10, value=share_val)
            
            ws.cell(row=c_row_idx, column=9).number_format = '#,##0'
            ws.cell(row=c_row_idx, column=10).number_format = '0.0%'
            
            for c in range(8, 11):
                cell = ws.cell(row=c_row_idx, column=c)
                cell.font = font_data
                cell.border = thin_border
                if c_row_idx % 2 == 1:
                    cell.fill = fill_zebra
            c_row_idx += 1
            
        # Total Row for Category Table
        ws.cell(row=c_row_idx, column=8, value=L["total"]).font = font_bold
        ws.cell(row=c_row_idx, column=8).alignment = Alignment(horizontal="center")
        ws.cell(row=c_row_idx, column=9, value=total_category_spent).font = font_bold
        ws.cell(row=c_row_idx, column=10, value=1.0 if total_category_spent > 0 else 0.0).font = font_bold
        
        ws.cell(row=c_row_idx, column=9).number_format = '#,##0'
        ws.cell(row=c_row_idx, column=10).number_format = '0.0%'
        
        for c in range(8, 11):
            cell = ws.cell(row=c_row_idx, column=c)
            cell.border = double_bottom
    else:
        # Graceful empty categories row
        ws.cell(row=8, column=8, value="-").alignment = Alignment(horizontal="center")
        ws.cell(row=8, column=9, value=0)
        ws.cell(row=8, column=10, value=0)
        c_row_idx = 8

    last_cat_row = c_row_idx

    # --- EMBEDDED HIGH-RESOLUTION CHARTS (MATPLOTLIB) ---
    # Chart 1: Monthly Cashflow Dynamics
    if sorted_months:
        incomes = [monthly_data[m]["income"] for m in sorted_months]
        expenses = [monthly_data[m]["expense"] for m in sorted_months]
        
        fig, ax = plt.subplots(figsize=(5.8, 3.8), dpi=120)
        x = range(len(sorted_months))
        width = 0.35
        
        # Soft corporate colors: Teal for Income, Red/Pink for Expense
        ax.bar([i - width/2 for i in x], incomes, width, label=L["col_income"], color="#2ec4b6")
        ax.bar([i + width/2 for i in x], expenses, width, label=L["col_expense"], color="#e63946")
        
        ax.set_title(L["chart_monthly_title"], fontsize=11, fontweight="bold", pad=12, color="#2d3748")
        ax.set_xticks(x)
        ax.set_xticklabels(sorted_months, fontsize=8)
        ax.tick_params(colors="#4a5568")
        ax.set_ylabel(currency, fontsize=8, color="#4a5568")
        ax.legend(frameon=True, facecolor="white", edgecolor="none", fontsize=8)
        ax.grid(True, axis='y', linestyle='--', alpha=0.3)
        
        # Clean borders
        for spine in ["top", "right", "left"]:
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color("#cbd5e0")
        
        plt.tight_layout()
        
        temp_path_m = f"temp_m_{user_id}.png"
        plt.savefig(temp_path_m, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        
        img_m = Image(temp_path_m)
        ws.add_image(img_m, f"A{last_month_row + 3}")

    # Chart 2: Category Structure (Pie Chart)
    if sorted_cats:
        cat_labels = [c[0] for c in sorted_cats]
        cat_values = [c[1] for c in sorted_cats]
        
        fig, ax = plt.subplots(figsize=(5.8, 3.8), dpi=120)
        
        # Premium multi-color corporate palette
        colors = ["#4ea8de", "#56cfe1", "#72efdd", "#80ffdb", "#48cae4", "#00b4d8", "#0077b6", "#023e8a", "#03045e"]
        if len(cat_values) > len(colors):
            colors = colors * (len(cat_values) // len(colors) + 1)
            
        ax.pie(cat_values, labels=cat_labels, autopct='%1.1f%%', startangle=90, colors=colors[:len(cat_values)],
               textprops={'fontsize': 7, 'color': '#2d3748'}, wedgeprops={'edgecolor': 'white', 'linewidth': 0.8})
        
        ax.set_title(L["chart_category_title"], fontsize=11, fontweight="bold", pad=12, color="#2d3748")
        ax.axis('equal')
        
        plt.tight_layout()
        
        temp_path_c = f"temp_c_{user_id}.png"
        plt.savefig(temp_path_c, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        
        img_c = Image(temp_path_c)
        ws.add_image(img_c, f"H{last_cat_row + 3}")

    # Set exact column widths for gorgeous layout
    widths = {"A": 12, "B": 15, "C": 15, "D": 15, "E": 15, "F": 4, "G": 4, "H": 25, "I": 16, "J": 12, "K": 4}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    # --- SHEET 2: DETAILED TRANSACTIONS ---
    ws_tx = wb.create_sheet(title=L["sheet_transactions"])
    ws_tx.views.sheetView[0].showGridLines = True
    ws_tx.append(L["raw_headers"])

    # Header styling for transaction sheet
    for cell in ws_tx[1]:
        cell.font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
        cell.fill = fill_title
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for idx, r in enumerate(rows_list, start=2):
        tx_id, ts, ttype, amount, account, category, emoji, note = r
        cat_display = f"{emoji} {category}".strip() if emoji or category else ""
        
        ws_tx.append([
            int(tx_id),
            str(ts or ""),
            str(ttype or ""),
            int(amount or 0),
            currency,
            str(account or ""),
            cat_display,
            str(note or ""),
        ])

        # Alternating row highlights (zebra)
        if idx % 2 == 1:
            for cell in ws_tx[idx]:
                cell.fill = fill_zebra

    # Format detail columns
    for row in range(2, len(rows_list) + 2):
        ws_tx.cell(row=row, column=4).number_format = '#,##0'

    widths_tx = [8, 22, 10, 14, 10, 18, 22, 40]
    for col_idx, width in enumerate(widths_tx, start=1):
        ws_tx.column_dimensions[chr(ord("A") + col_idx - 1)].width = width

    # Save to buffer
    buf = io.BytesIO()
    wb.save(buf)
    
    # Safely delete temp files
    import os
    for path in [f"temp_m_{user_id}.png", f"temp_c_{user_id}.png"]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
                
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
async def export_pick(c: CallbackQuery, state: FSMContext, db: aiosqlite.Connection, full_access: bool = False):
    from app.handlers.common import neutralize_keyboard
    await neutralize_keyboard(c)
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

    # Determine free trial status
    await db.execute("CREATE TABLE IF NOT EXISTS user_free_trial (user_id INTEGER PRIMARY KEY, premium_exports_used INTEGER NOT NULL DEFAULT 0)")
    await db.commit()

    cur = await db.execute("SELECT premium_exports_used FROM user_free_trial WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    exports_used = row[0] if row else 0

    use_premium_xlsx = False
    is_free_trial_now = False

    if full_access:
        use_premium_xlsx = True
    elif exports_used == 0:
        # Give them exactly 1 free premium export as a trial!
        use_premium_xlsx = True
        is_free_trial_now = True

    if use_premium_xlsx:
        payload = _build_xlsx(rows, lang, currency, user_id)
        if payload is not None:
            filename = f"finance_{label}.xlsx"
            await c.message.answer_document(BufferedInputFile(payload, filename=filename))
            
            if is_free_trial_now:
                # Mark as used
                await db.execute("INSERT OR REPLACE INTO user_free_trial (user_id, premium_exports_used) VALUES (?, 1)", (user_id,))
                await db.commit()
                
                # Send celebratory 1-time free trial congratulation
                trial_msg = {
                    "ru": (
                        "🎁 **Поздравляем! Вам начислен 1 тест-драйв премиум-отчёта!**\n\n"
                        "Мы подготовили для вас роскошный Excel-файл с интерактивными графиками и аналитическим дашбордом совершенно бесплатно. Оцените удобство и красоту профессиональной аналитики!\n\n"
                        "*(Следующие экспорты в Excel будут доступны при активации Полного доступа в настройках)*"
                    ),
                    "en": (
                        "🎁 **Congratulations! You have received 1 free premium report trial!**\n\n"
                        "We have prepared a gorgeous Excel file with interactive charts and an analytical dashboard for you completely free. Experience the power and beauty of professional analytics!\n\n"
                        "*(Subsequent Excel exports will be unlocked with Full Access)*"
                    ),
                    "kk": (
                        "🎁 **Құттықтаймыз! Сізге 1 тегін премиум есеп тест-драйвы берілді!**\n\n"
                        "Біз сіз үшін интерактивті графиктер мен талдау дашборды бар керемет Excel файлын мүлдем тегін дайындадық. Кәсіби талдаудың ыңғайлылығы мен сұлулығын бағалаңыз!\n\n"
                        "*(Келесі Excel экспорттары параметрлерде Толық қолжетімділікті белсендіргенде ашылады)*"
                    )
                }.get(lang, "🎁 **Поздравляем! Вам начислен 1 тест-драйв премиум-отчёта!**")
                
                await c.message.answer(trial_msg, parse_mode="Markdown")
            return

    # Fallback to CSV for free users (who already used their trial) or if openpyxl failed
    payload_csv = _build_csv(rows, lang, currency)
    filename = f"finance_{label}.csv"
    await c.message.answer_document(BufferedInputFile(payload_csv, filename=filename))
    
    # Check if they are a free user who has already used their trial
    trial_notice = ""
    if not full_access and exports_used > 0:
        trial_notice = {
            "ru": "⚠️ **Вы уже использовали свой 1 бесплатный пробный премиум-экспорт.**\n\n",
            "en": "⚠️ **You have already used your 1 free premium export trial.**\n\n",
            "kk": "⚠️ **Сіз 1 тегін премиум экспорт тест-драйвын пайдаланып қойдыңыз.**\n\n",
        }.get(lang, "")

    # Paywall pitching message to encourage upgrade
    pitch = {
        "ru": (
            f"{trial_notice}"
            "📊 **Ваш файл успешно экспортирован в формате CSV!**\n\n"
            "🌟 *Хотите получить премиальный Excel-отчёт с интерактивными графиками, "
            "разбивкой по месяцам/категориям и печатным дашбордом?*\n\n"
            "Активируйте **Полный доступ** прямо сейчас, чтобы разблокировать профессиональную аналитику!"
        ),
        "en": (
            f"{trial_notice}"
            "📊 **Your CSV file is ready!**\n\n"
            "🌟 *Want a premium Excel report with interactive charts, monthly/category cashflow breakdown "
            "and printable dashboard?*\n\n"
            "Activate **Full Access** right now to unlock advanced financial analytics!"
        ),
        "kk": (
            f"{trial_notice}"
            "📊 **Сіздің CSV файлыңыз сәтті дайындалды!**\n\n"
            "🌟 *Интерактивті графиктермен, айлар/санаттар бойынша бөлінген және басып шығаруға болатын "
            "премиум Excel есебін алғыңыз келе ме?*\n\n"
            "Кәсіби талдауды ашу үшін қазір **Толық қолжетімділікті** белсендіріңіз!"
        )
    }.get(lang, "📊 **Ваш файл успешно экспортирован в формате CSV!**")
    
    # Build inline keyboard to direct them to the upgrade screen or main menu
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    upgrade_btn_text = {
        "ru": "👑 Активировать Полный доступ",
        "en": "👑 Activate Full Access",
        "kk": "👑 Толық қолжетімділікті белсендіру",
    }.get(lang, "👑 Активировать Полный доступ")
    
    menu_btn_text = {
        "ru": "🏠 В Главное меню",
        "en": "🏠 Main Menu",
        "kk": "🏠 Басты мәзірге",
    }.get(lang, "🏠 В Главное меню")
    
    paywall_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=upgrade_btn_text, callback_data="upgrade:info")],
        [InlineKeyboardButton(text=menu_btn_text, callback_data="hub:main")]
    ])
    
    await c.message.answer(pitch, parse_mode="Markdown", reply_markup=paywall_kb)
