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
from aiogram.types import BufferedInputFile, CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import asyncio
from app.db.repositories.settings_repo import get_lang, get_settings
from app.db.repositories.users_repo import get_free_exports_used, increment_free_export
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


def _build_downgrade_preview_png(rows: list, lang: str, currency: str) -> bytes | None:
    """
    Генерирует премиальное превью графиков для бесплатного пользователя,
    чтобы вызвать "эффект потери" и мотивировать к покупке.
    """
    if not rows:
        return None

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import io
    except ImportError:
        return None

    # 1. Агрегация данных
    total_income = 0
    total_expense = 0
    expenses_by_cat = {}

    for row in rows:
        try:
            tx_id, ts, ttype, amount, account, category, emoji, note = row
        except Exception:
            continue
        
        is_income = ttype == 'income' 
        amt = abs(int(amount or 0))
        
        if is_income:
            total_income += amt
        else:
            total_expense += amt
            cat_name = str(category or "").strip()
            if not cat_name:
                cat_name = {
                    "ru": "Другое",
                    "en": "Other",
                    "kk": "Басқа"
                }.get(lang, "Другое")
            expenses_by_cat[cat_name] = expenses_by_cat.get(cat_name, 0) + amt

    # Берем Топ-5 категорий
    top_categories = sorted(expenses_by_cat.items(), key=lambda x: x[1], reverse=True)[:5]
    cat_labels = [item[0] for item in top_categories]
    cat_sizes = [item[1] for item in top_categories]

    # 2. Настройка фигуры и темы
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), dpi=150)
    
    # Темная премиальная тема (sleek dark mode)
    bg_color = '#1E1E2E'
    text_color = '#CDD6F4'
    fig.patch.set_facecolor(bg_color)
    
    # Цвета графиков
    color_income = '#A6E3A1'  # Мятный
    color_expense = '#F38BA8' # Рубиновый
    colors_pie = ['#89B4FA', '#F9E2AF', '#F38BA8', '#A6E3A1', '#CBA6F7']

    # --- Левый график: Доходы vs Расходы ---
    ax1.set_facecolor(bg_color)
    
    labels_dynamics = {
        "ru": ['Доходы', 'Расходы'],
        "en": ['Income', 'Expenses'],
        "kk": ['Кірістер', 'Шығыстар']
    }.get(lang, ['Доходы', 'Расходы'])
    
    title_dynamics = {
        "ru": "Денежный поток",
        "en": "Cash Flow",
        "kk": "Ақша ағыны"
    }.get(lang, "Денежный поток")
    
    bars = ax1.bar(labels_dynamics, [total_income, total_expense], color=[color_income, color_expense], width=0.5)
    ax1.set_title(title_dynamics, color=text_color, fontsize=16, pad=20, weight='bold')
    ax1.tick_params(colors=text_color, labelsize=12)
    
    # Убираем рамки
    for spine in ax1.spines.values():
        spine.set_visible(False)
    ax1.grid(axis='y', color='#313244', linestyle='--', alpha=0.7)

    # --- Правый график: Топ-5 категорий расходов ---
    title_pie = {
        "ru": "Топ расходов",
        "en": "Top Expenses",
        "kk": "Ең көп шығыстар"
    }.get(lang, "Топ расходов")
    
    if cat_sizes:
        _, texts, autotexts = ax2.pie(
            cat_sizes, 
            labels=cat_labels, 
            colors=colors_pie,
            autopct='%1.1f%%', 
            startangle=140,
            textprops={'color': text_color, 'fontsize': 12},
            wedgeprops={'edgecolor': bg_color, 'linewidth': 2}
        )
        for autotext in autotexts:
            autotext.set_color(bg_color)
            autotext.set_weight('bold')
        ax2.set_title(title_pie, color=text_color, fontsize=16, pad=20, weight='bold')
    else:
        ax2.set_facecolor(bg_color)
        ax2.text(0.5, 0.5, {
            "ru": "Нет расходов за период",
            "en": "No expenses",
            "kk": "Шығыстар жоқ"
        }.get(lang, "Нет расходов"), color=text_color, ha='center', va='center', fontsize=14)
        for spine in ax2.spines.values():
            spine.set_visible(False)
        ax2.set_xticks([])
        ax2.set_yticks([])

    # --- 3. Водяной знак ---
    watermark_text = {
        "ru": "ПРОФЕССИОНАЛЬНАЯ АНАЛИТИКА · FINANCEBOT",
        "en": "PROFESSIONAL ANALYTICS · FINANCEBOT",
        "kk": "КӘСІБИ ТАЛДАУ · FINANCEBOT"
    }.get(lang, "ПРОФЕССИОНАЛЬНАЯ АНАЛИТИКА · FINANCEBOT")
    
    fig.text(0.5, 0.5, watermark_text, 
             fontsize=32, color='white', alpha=0.04, 
             ha='center', va='center', rotation=15, weight='bold')

    # 4. Сохранение в байты
    buf = io.BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png', facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=150)
    plt.close(fig)
    buf.seek(0)
    
    return buf.getvalue()


def format_localized_datetime(dt, lang: str) -> str:
    months = {
        "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"],
        "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
        "kk": ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"]
    }
    lang_months = months.get(lang, months["ru"])
    month_name = lang_months[dt.month - 1]
    
    time_str = dt.strftime("%H:%M")
    if lang == "ru":
        return f"{dt.day} {month_name} {dt.year} г. {time_str}"
    elif lang == "kk":
        return f"{dt.year} жылғы {dt.day} {month_name}, {time_str}"
    else: # en
        return f"{month_name} {dt.day}, {dt.year} {time_str}"


def format_localized_month(month_str: str, lang: str) -> str:
    try:
        parts = month_str.split("-")
        if len(parts) != 2:
            return month_str
        year, month_idx = int(parts[0]), int(parts[1])
        months = {
            "ru": ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"],
            "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
            "kk": ["Қаңтар", "Ақпан", "Наурыз", "Сәуір", "Мамыр", "Маусым", "Шілде", "Тамыз", "Қыркүйек", "Қазан", "Қараша", "Желтоқсан"]
        }
        lang_months = months.get(lang, months["ru"])
        month_name = lang_months[month_idx - 1]
        return f"{month_name} {year}"
    except Exception:
        return month_str


def _build_xlsx(
    rows: Iterable[tuple],
    lang: str,
    currency: str,
    user_id: int,
    metrics: dict,
    profile: dict,
    priority_insights: dict,
    latest_rec: dict | None,
    tz_name: str = "Asia/Aqtobe"
) -> bytes | None:
    """Render rows into a premium, app-like 3-sheet Excel workbook.
    
    Aesthetics:
    - Minimalist Apple/Stripe-inspired Slate & Emerald theme.
    - Gridlines disabled on Summary and Analytics sheets for a dashboard feel.
    - Large row heights (22-35px) for spacious typography.
    - Explicit column widths to completely avoid text truncation (### or clipped text).
    - Localized dates in user's timezone (YYYY-MM-DD HH:MM).
    - Fully localized transaction types (Доход / Расход / Перевод).
    """
    try:
        import collections
        import io
        import calendar
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    except ImportError:
        return None

    # Localized labels
    all_labels = {
        "ru": {
            "title_summary": "FINANCIAL PULSE • EXECUTIVE SUMMARY",
            "health_title": "ФИНАНСОВЫЙ ИНДЕКС",
            "runway_title": "ЗАПАС ПРОЧНОСТИ",
            "burn_title": "DAILY BURN RATE",
            "main_risk": "КЛЮЧЕВОЙ ФИНАНСОВЫЙ РИСК",
            "ai_rec": "AI РЕКОМЕНДАЦИЯ КОУЧА",
            "behavioral": "ПОВЕДЕНЧЕСКИЙ ПРОФИЛЬ",
            "monthly_title": "Динамика доходов и расходов",
            "col_month": "Месяц",
            "col_income": "Доходы",
            "col_expense": "Расходы",
            "col_net": "Чистый доход",
            "col_savings": "Сбережения %",
            "category_title": "Структура расходов по категориям",
            "col_category": "Категория",
            "col_spent": "Потрачено",
            "col_share": "Доля расходов",
            "total": "Итого",
            "trends_title": "Сравнение трендов (vs пред. месяц)",
            "income_trend": "Изменение доходов",
            "expense_trend": "Изменение расходов",
            "savings_trend": "Коэффициент сбережений",
            "prediction_title": "Прогноз на конец месяца",
            "projected_spending": "Ожидаемые расходы к концу месяца",
            "anomalies_title": "Аномалии и предупреждения",
            "no_anomalies": "Аномалий или повышенных рисков не обнаружено.",
            "sheet_dashboard": "Executive Summary",
            "sheet_analytics": "Аналитика",
            "sheet_transactions": "История операций",
            "raw_headers": ["ID", "Дата и время", "Тип", "Сумма", "Валюта", "Счёт", "Категория", "Комментарий"]
        },
        "en": {
            "title_summary": "FINANCIAL PULSE • EXECUTIVE SUMMARY",
            "health_title": "FINANCIAL HEALTH INDEX",
            "runway_title": "RESERVES RUNWAY",
            "burn_title": "DAILY BURN RATE",
            "main_risk": "MAIN FINANCIAL RISK",
            "ai_rec": "AI COACH RECOMMENDATION",
            "behavioral": "BEHAVIORAL PROFILE",
            "monthly_title": "Monthly Cashflow Dynamics",
            "col_month": "Month",
            "col_income": "Income",
            "col_expense": "Expenses",
            "col_net": "Net Income",
            "col_savings": "Savings %",
            "category_title": "Expenses Structure by Category",
            "col_category": "Category",
            "col_spent": "Spent",
            "col_share": "Expense Share",
            "total": "Total",
            "trends_title": "Trend Comparison (vs last month)",
            "income_trend": "Income change",
            "expense_trend": "Expenses change",
            "savings_trend": "Savings rate change",
            "prediction_title": "Month-End Prediction",
            "projected_spending": "Projected month-end spending",
            "anomalies_title": "Anomaly Alerts",
            "no_anomalies": "No anomalies or high risks detected.",
            "sheet_dashboard": "Executive Summary",
            "sheet_analytics": "Analytics",
            "sheet_transactions": "Transaction History",
            "raw_headers": ["ID", "Date & Time", "Type", "Amount", "Currency", "Account", "Category", "Note"]
        },
        "kk": {
            "title_summary": "FINANCIAL PULSE • EXECUTIVE SUMMARY",
            "health_title": "ҚАРЖЫЛЫҚ ИНДЕКС",
            "runway_title": "ҚАУІПСІЗДІК ҚОРЫ",
            "burn_title": "DAILY BURN RATE",
            "main_risk": "НЕГІЗГІ ҚАРЖЫЛЫҚ ҚАУІП",
            "ai_rec": "AI КОУЧ ҰСЫНЫСЫ",
            "behavioral": "МІНЕЗ-ҚҰЛЫҚ ПРОФИЛІ",
            "monthly_title": "Кірістер мен шығыстар динамикасы",
            "col_month": "Ай",
            "col_income": "Кірістер",
            "col_expense": "Шығыстар",
            "col_net": "Таза кіріс",
            "col_savings": "Жинақ %",
            "category_title": "Санаттар бойынша шығыстар",
            "col_category": "Санат",
            "col_spent": "Жұмсалды",
            "col_share": "Шығыс үлесі",
            "total": "Жиынтығы",
            "trends_title": "Трендтерді салыстыру (өткен аймен)",
            "income_trend": "Кірістердің өзгеруі",
            "expense_trend": "Шығыстардың өзгеруі",
            "savings_trend": "Жинақ коэффициенті",
            "prediction_title": "Ай соңына болжам",
            "projected_spending": "Айдың соңына күтілетін шығыстар",
            "anomalies_title": "Аномалиялар мен ескертулер",
            "no_anomalies": "Аномалиялар немесе жоғары қауіптер табылған жоқ.",
            "sheet_dashboard": "Executive Summary",
            "sheet_analytics": "Талдау",
            "sheet_transactions": "Операциялар тарихы",
            "raw_headers": ["ID", "Күні мен уақыты", "Түрі", "Сома", "Валюта", "Шот", "Санат", "Түсініктеме"]
        }
    }
    L = all_labels.get(lang, all_labels["ru"])

    # 1. Process Data / Aggregations
    total_income = 0
    total_expense = 0
    monthly_data = collections.defaultdict(lambda: {"income": 0, "expense": 0})
    category_data = collections.defaultdict(int)

    rows_list = list(rows)
    for r in rows_list:
        tx_id, ts, ttype, amount, account, category, emoji, note = r
        val = abs(int(amount or 0))
        
        # Parse date and convert to local timezone to group by local month correctly
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            local_dt = dt.astimezone(ZoneInfo(tz_name))
            month_str = local_dt.strftime("%Y-%m")
        except Exception:
            month_str = str(ts)[:7] if ts and len(str(ts)) >= 7 else "Unknown"
        
        if ttype == "income":
            total_income += val
            monthly_data[month_str]["income"] += val
        elif ttype == "expense":
            total_expense += val
            monthly_data[month_str]["expense"] += val
            cat_display = f"{emoji} {category}".strip() if emoji or category else "Other"
            category_data[cat_display] += val

    wb = Workbook()
    
    # Premium Typography & Styling
    font_main_title = Font(name="Segoe UI", size=14, bold=True, color="FFFFFF")
    font_sec_hdr = Font(name="Segoe UI", size=11, bold=True, color="1E293B")
    font_tbl_hdr = Font(name="Segoe UI", size=10, bold=True, color="475569")
    font_bold = Font(name="Segoe UI", size=10, bold=True, color="0F172A")
    font_data = Font(name="Segoe UI", size=10, color="334155")
    font_subtext = Font(name="Segoe UI", size=9, color="64748B")
    font_mono = Font(name="Consolas", size=10, color="0F172A")
    
    # Cards styling
    font_card_val = Font(name="Segoe UI", size=22, bold=True, color="0F172A")
    
    # Soft distinct premium colors for cards
    fill_health = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid") # soft blue-50
    fill_runway = PatternFill(start_color="ECFDF5", end_color="ECFDF5", fill_type="solid") # soft emerald-50
    fill_burn = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")   # soft slate-50
    
    font_card_title_1 = Font(name="Segoe UI", size=9, bold=True, color="1E40AF") # Deep Indigo/Blue
    font_card_title_2 = Font(name="Segoe UI", size=9, bold=True, color="065F46") # Deep Emerald
    font_card_title_3 = Font(name="Segoe UI", size=9, bold=True, color="334155") # Dark Slate
    
    # Color Fills
    fill_header_banner = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid") # Dark Slate
    fill_card = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")         # Light Slate-50
    fill_tbl_hdr = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")     # Slate-100
    fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")       # Slate-50
    fill_accent_green = PatternFill(start_color="ECFDF5", end_color="ECFDF5", fill_type="solid") # Emerald Light
    
    # Custom Borders
    thin_gray = Side(style='thin', color='E2E8F0')
    border_all = Border(left=thin_gray, right=thin_gray, top=thin_gray, bottom=thin_gray)
    border_bottom = Border(bottom=Side(style='thin', color='E2E8F0'))
    border_double_bottom = Border(top=Side(style='thin', color='94A3B8'), bottom=Side(style='double', color='0F172A'))

    # ==========================================
    # SHEET 1: EXECUTIVE SUMMARY (App-like Dashboard)
    # ==========================================
    ws_sum = wb.active
    ws_sum.title = L["sheet_dashboard"]
    ws_sum.views.sheetView[0].showGridLines = False # Disable grid lines for a clean canvas

    # Title Banner Block (Dark Premium Header)
    ws_sum.merge_cells("A1:K1")
    ws_sum["A1"] = L["title_summary"]
    ws_sum["A1"].font = font_main_title
    ws_sum["A1"].fill = fill_header_banner
    ws_sum["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws_sum.row_dimensions[1].height = 42

    # Calculate financial health score
    sav_pct = metrics.get("savings_rate", {}).get("savings_rate_pct", 0)
    sav_score = min(40, max(0, int(sav_pct * 1.33)))
    runway = metrics.get("runway_days", 0)
    if runway == float('inf') or runway is None:
        runway_val = 99
        runway_score = 30
    else:
        runway_val = int(runway)
        runway_score = min(30, max(0, int(runway / 3.0)))
    discipline = profile.get("discipline_score", 100)
    discipline_score = min(30, max(0, int(discipline * 0.3)))
    health_score = sav_score + runway_score + discipline_score

    # Summary Cards Layout (3 spacious columns of cards)
    # Card 1: Financial Health (A3:C5)
    ws_sum.merge_cells("A3:C3")
    ws_sum.merge_cells("A4:C4")
    ws_sum.merge_cells("A5:C5")
    ws_sum["A3"] = L["health_title"]
    ws_sum["A3"].font = font_card_title_1
    ws_sum["A3"].alignment = Alignment(horizontal="center", vertical="center")
    ws_sum["A4"] = f"{health_score} / 100"
    ws_sum["A4"].font = font_card_val
    ws_sum["A4"].alignment = Alignment(horizontal="center", vertical="center")
    
    score_trend = {
        "ru": "Высокая дисциплина" if discipline > 80 else "Стабильный",
        "en": "High discipline" if discipline > 80 else "Stable",
        "kk": "Жоғары тәртіп" if discipline > 80 else "Тұрақты"
    }.get(lang, "High discipline" if discipline > 80 else "Stable")
    ws_sum["A5"] = score_trend
    ws_sum["A5"].font = font_subtext
    ws_sum["A5"].alignment = Alignment(horizontal="center", vertical="center")

    # Card 2: Runway (E3:G5)
    ws_sum.merge_cells("E3:G3")
    ws_sum.merge_cells("E4:G4")
    ws_sum.merge_cells("E5:G5")
    ws_sum["E3"] = L["runway_title"]
    ws_sum["E3"].font = font_card_title_2
    ws_sum["E3"].alignment = Alignment(horizontal="center", vertical="center")
    ws_sum["E4"] = f"{runway_val} дней" if lang == "ru" else (f"{runway_val} күн" if lang == "kk" else f"{runway_val} Days")
    ws_sum["E4"].font = font_card_val
    ws_sum["E4"].alignment = Alignment(horizontal="center", vertical="center")
    
    runway_desc = {
        "ru": "Резервы ликвидности",
        "en": "Liquidity reserves",
        "kk": "Ликвидтілік резервтері"
    }.get(lang, "Liquidity reserves")
    ws_sum["E5"] = runway_desc
    ws_sum["E5"].font = font_subtext
    ws_sum["E5"].alignment = Alignment(horizontal="center", vertical="center")

    # Card 3: Daily Burn Rate (I3:K5)
    ws_sum.merge_cells("I3:K3")
    ws_sum.merge_cells("I4:K4")
    ws_sum.merge_cells("I5:K5")
    ws_sum["I3"] = L["burn_title"]
    ws_sum["I3"].font = font_card_title_3
    ws_sum["I3"].alignment = Alignment(horizontal="center", vertical="center")
    
    burn_daily = metrics.get("burn_rate", {}).get("daily_burn_rate", 0)
    ws_sum["I4"] = f"{burn_daily} {currency}"
    ws_sum["I4"].font = font_card_val
    ws_sum["I4"].alignment = Alignment(horizontal="center", vertical="center")
    
    burn_trend_pct = metrics.get("burn_rate", {}).get("trend_pct", 0.0)
    trend_sign = "+" if burn_trend_pct > 0 else ""
    burn_desc = {
        "ru": f"{trend_sign}{burn_trend_pct}% vs пред. период",
        "en": f"{trend_sign}{burn_trend_pct}% vs last period",
        "kk": f"{trend_sign}{burn_trend_pct}% өткен кезеңмен"
    }.get(lang, f"{trend_sign}{burn_trend_pct}% vs last period")
    ws_sum["I5"] = burn_desc
    ws_sum["I5"].font = font_subtext
    ws_sum["I5"].alignment = Alignment(horizontal="center", vertical="center")

    # Style cards with background fills & borders
    for c in ["A", "B", "C"]:
        for r in [3, 4, 5]:
            ws_sum[f"{c}{r}"].fill = fill_health
            ws_sum[f"{c}{r}"].border = Border(
                top=thin_gray if r == 3 else None,
                bottom=thin_gray if r == 5 else None,
                left=thin_gray if c == "A" else None,
                right=thin_gray if c == "C" else None
            )
            
    for c in ["E", "F", "G"]:
        for r in [3, 4, 5]:
            ws_sum[f"{c}{r}"].fill = fill_runway
            ws_sum[f"{c}{r}"].border = Border(
                top=thin_gray if r == 3 else None,
                bottom=thin_gray if r == 5 else None,
                left=thin_gray if c == "E" else None,
                right=thin_gray if c == "G" else None
            )
            
    for c in ["I", "J", "K"]:
        for r in [3, 4, 5]:
            ws_sum[f"{c}{r}"].fill = fill_burn
            ws_sum[f"{c}{r}"].border = Border(
                top=thin_gray if r == 3 else None,
                bottom=thin_gray if r == 5 else None,
                left=thin_gray if c == "I" else None,
                right=thin_gray if c == "K" else None
            )

    ws_sum.row_dimensions[3].height = 20
    ws_sum.row_dimensions[4].height = 32
    ws_sum.row_dimensions[5].height = 20

    # Section 1: Main Financial Risk
    ws_sum["A7"] = L["main_risk"]
    ws_sum["A7"].font = font_sec_hdr
    ws_sum.row_dimensions[7].height = 28
    
    main_problem_text = {
        "ru": "Рисков не обнаружено",
        "en": "No risks detected",
        "kk": "Қауіп табылған жоқ"
    }.get(lang, "No risks detected")
    mp = priority_insights.get("main_problem")
    if mp:
        main_problem_text = mp.get("text", main_problem_text)
    
    ws_sum.merge_cells("A8:K8")
    ws_sum["A8"] = f" ⚠️  {main_problem_text}"
    ws_sum["A8"].font = font_bold
    ws_sum["A8"].alignment = Alignment(wrap_text=True, vertical="center", indent=1)
    ws_sum["A8"].border = border_all
    ws_sum["A8"].fill = fill_card
    ws_sum.row_dimensions[8].height = 30

    # Section 2: AI Recommended Action
    ws_sum["A10"] = L["ai_rec"]
    ws_sum["A10"].font = font_sec_hdr
    ws_sum.row_dimensions[10].height = 28
    
    rec_text = {
        "ru": "Продолжайте удерживать текущие лимиты расходов.",
        "en": "Keep maintaining current spending limits.",
        "kk": "Шығындар лимиттерін ұстап тұруды жалғастырыңыз."
    }.get(lang, "Keep maintaining current spending limits.")
    if latest_rec:
        rec_text = latest_rec.get("text", rec_text)
        
    ws_sum.merge_cells("A11:K11")
    ws_sum["A11"] = f" 💡  {rec_text}"
    ws_sum["A11"].font = font_data
    ws_sum["A11"].alignment = Alignment(wrap_text=True, vertical="center", indent=1)
    ws_sum["A11"].border = border_all
    ws_sum["A11"].fill = fill_accent_green
    ws_sum.row_dimensions[11].height = 30

    # Section 3: Behavioral Profile
    ws_sum["A13"] = L["behavioral"]
    ws_sum["A13"].font = font_sec_hdr
    ws_sum.row_dimensions[13].height = 28
    
    beh_summary = profile.get("behavioral_summary", "накапливаем статистику")
    if beh_summary == "накапливаем статистику":
        beh_summary = {
            "ru": "накапливаем статистику",
            "en": "collecting statistics",
            "kk": "статистика жиналуда"
        }.get(lang, "collecting statistics")
        
    ws_sum.merge_cells("A14:K14")
    ws_sum["A14"] = f" 👤  {beh_summary}"
    ws_sum["A14"].font = font_data
    ws_sum["A14"].alignment = Alignment(wrap_text=True, vertical="center", indent=1)
    ws_sum["A14"].border = border_all
    ws_sum["A14"].fill = fill_card
    ws_sum.row_dimensions[14].height = 30

    # Fixed wide column definitions for executive summary to completely prevent text cropping
    widths_sum = {"A": 15, "B": 15, "C": 15, "D": 5, "E": 15, "F": 15, "G": 15, "H": 5, "I": 15, "J": 15, "K": 15}
    for col, w in widths_sum.items():
        ws_sum.column_dimensions[col].width = w

    # ==========================================
    # SHEET 2: ANALYTICS (Structured Data Blocks)
    # ==========================================
    ws_an = wb.create_sheet(title=L["sheet_analytics"])
    ws_an.views.sheetView[0].showGridLines = False

    # Title Dynamic Cashflow
    ws_an["A1"] = L["monthly_title"]
    ws_an["A1"].font = font_sec_hdr
    ws_an.row_dimensions[1].height = 30

    headers_m = [L["col_month"], L["col_income"], L["col_expense"], L["col_net"], L["col_savings"]]
    for c_idx, h in enumerate(headers_m, start=1):
        cell = ws_an.cell(row=2, column=c_idx, value=h)
        cell.font = font_tbl_hdr
        cell.fill = fill_tbl_hdr
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border_all
    ws_an.row_dimensions[2].height = 24

    sorted_months = sorted(list(monthly_data.keys()))
    row_idx = 3
    for m_str in sorted_months:
        inc = monthly_data[m_str]["income"]
        exp = monthly_data[m_str]["expense"]
        net_val = inc - exp
        sav_val = net_val / inc if inc > 0 else 0.0
        
        ws_an.cell(row=row_idx, column=1, value=format_localized_month(m_str, lang)).alignment = Alignment(horizontal="center")
        ws_an.cell(row=row_idx, column=2, value=inc)
        ws_an.cell(row=row_idx, column=3, value=exp)
        ws_an.cell(row=row_idx, column=4, value=net_val)
        ws_an.cell(row=row_idx, column=5, value=sav_val)
        
        ws_an.cell(row=row_idx, column=2).number_format = '#,##0'
        ws_an.cell(row=row_idx, column=3).number_format = '#,##0'
        ws_an.cell(row=row_idx, column=4).number_format = '#,##0'
        ws_an.cell(row=row_idx, column=5).number_format = '0.0%'
        
        for c in range(1, 6):
            cell = ws_an.cell(row=row_idx, column=c)
            cell.font = font_data
            cell.border = border_all
            if row_idx % 2 == 1:
                cell.fill = fill_zebra
        ws_an.row_dimensions[row_idx].height = 20
        row_idx += 1

    # Monthly Total
    monthly_net_total = total_income - total_expense
    monthly_sav_total = monthly_net_total / total_income if total_income > 0 else 0.0

    ws_an.cell(row=row_idx, column=1, value=L["total"]).font = font_bold
    ws_an.cell(row=row_idx, column=1).alignment = Alignment(horizontal="center")
    ws_an.cell(row=row_idx, column=2, value=total_income).font = font_bold
    ws_an.cell(row=row_idx, column=3, value=total_expense).font = font_bold
    ws_an.cell(row=row_idx, column=4, value=monthly_net_total).font = font_bold
    ws_an.cell(row=row_idx, column=5, value=monthly_sav_total).font = font_bold
    
    ws_an.cell(row=row_idx, column=2).number_format = '#,##0'
    ws_an.cell(row=row_idx, column=3).number_format = '#,##0'
    ws_an.cell(row=row_idx, column=4).number_format = '#,##0'
    ws_an.cell(row=row_idx, column=5).number_format = '0.0%'
    
    for c in range(1, 6):
        ws_an.cell(row=row_idx, column=c).border = border_double_bottom
    ws_an.row_dimensions[row_idx].height = 22
    
    last_month_row = row_idx

    # Category breakdown (Right Side Table - starts at column H)
    ws_an["H1"] = L["category_title"]
    ws_an["H1"].font = font_sec_hdr

    headers_c = [L["col_category"], L["col_spent"], L["col_share"]]
    for c_idx, h in enumerate(headers_c, start=8):  # H, I, J
        cell = ws_an.cell(row=2, column=c_idx, value=h)
        cell.font = font_tbl_hdr
        cell.fill = fill_tbl_hdr
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border_all

    sorted_cats = sorted(category_data.items(), key=lambda x: x[1], reverse=True)
    c_row_idx = 3
    total_category_spent = sum(category_data.values())

    if sorted_cats:
        for cat_name, spent in sorted_cats:
            ws_an.cell(row=c_row_idx, column=8, value=cat_name)
            ws_an.cell(row=c_row_idx, column=9, value=spent)
            
            # Progress Bar & percentage in string
            share_val = spent / total_category_spent if total_category_spent > 0 else 0.0
            num_blocks = int(round(share_val * 10))
            bar_str = "█" * num_blocks + "░" * (10 - num_blocks)
            ws_an.cell(row=c_row_idx, column=10, value=f"{bar_str}  {share_val * 100:.1f}%")
            
            ws_an.cell(row=c_row_idx, column=9).number_format = '#,##0'
            ws_an.cell(row=c_row_idx, column=10).alignment = Alignment(horizontal="left")
            
            for c in range(8, 11):
                cell = ws_an.cell(row=c_row_idx, column=c)
                cell.font = font_data
                cell.border = border_all
                if c_row_idx % 2 == 1:
                    cell.fill = fill_zebra
            ws_an.row_dimensions[c_row_idx].height = 20
            c_row_idx += 1

        # Total Category spent
        ws_an.cell(row=c_row_idx, column=8, value=L["total"]).font = font_bold
        ws_an.cell(row=c_row_idx, column=8).alignment = Alignment(horizontal="center")
        ws_an.cell(row=c_row_idx, column=9, value=total_category_spent).font = font_bold
        ws_an.cell(row=c_row_idx, column=10, value="██████████  100%").font = font_bold
        ws_an.cell(row=c_row_idx, column=9).number_format = '#,##0'
        
        for c in range(8, 11):
            ws_an.cell(row=c_row_idx, column=c).border = border_double_bottom
        ws_an.row_dimensions[c_row_idx].height = 22
    else:
        ws_an.cell(row=3, column=8, value="-").alignment = Alignment(horizontal="center")
        ws_an.cell(row=3, column=9, value=0)
        ws_an.cell(row=3, column=10, value="░░░░░░░░░░  0%")
        c_row_idx = 3

    last_cat_row = c_row_idx

    # Trend Comparison Block (Generous rows and columns to prevent truncation)
    start_trend_row = max(last_month_row, last_cat_row) + 3
    
    ws_an.cell(row=start_trend_row, column=1, value=L["trends_title"]).font = font_sec_hdr
    ws_an.row_dimensions[start_trend_row].height = 28
    
    # Calculate side-by-side month comparison
    if len(sorted_months) >= 2:
        m_curr, m_prev = sorted_months[-1], sorted_months[-2]
        inc_c = monthly_data[m_curr]["income"]
        inc_p = monthly_data[m_prev]["income"]
        exp_c = monthly_data[m_curr]["expense"]
        exp_p = monthly_data[m_prev]["expense"]
    elif len(sorted_months) == 1:
        m_curr = sorted_months[0]
        m_prev = None
        inc_c = monthly_data[m_curr]["income"]
        inc_p = 0
        exp_c = monthly_data[m_curr]["expense"]
        exp_p = 0
    else:
        m_curr = None
        m_prev = None
        inc_c = 0
        inc_p = 0
        exp_c = 0
        exp_p = 0

    net_c = inc_c - exp_c
    net_p = inc_p - exp_p
    
    sav_c = (net_c / inc_c) if inc_c > 0 else 0.0
    sav_p = (net_p / inc_p) if inc_p > 0 else 0.0

    # Localized month headers
    prev_hdr = format_localized_month(m_prev, lang) if m_prev else ("-" if lang == "ru" else ("-" if lang == "kk" else "-"))
    curr_hdr = format_localized_month(m_curr, lang) if m_curr else ("-" if lang == "ru" else ("-" if lang == "kk" else "-"))

    # Table headers
    comp_headers = {
        "ru": ["Показатель", prev_hdr, curr_hdr, "Изменение"],
        "en": ["Metric", prev_hdr, curr_hdr, "Change"],
        "kk": ["Көрсеткіш", prev_hdr, curr_hdr, "Өзгеруі"]
    }.get(lang, ["Metric", prev_hdr, curr_hdr, "Change"])

    for c_idx, h in enumerate(comp_headers, start=1):
        cell = ws_an.cell(row=start_trend_row + 1, column=c_idx, value=h)
        cell.font = font_tbl_hdr
        cell.fill = fill_tbl_hdr
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border_all
    ws_an.row_dimensions[start_trend_row + 1].height = 22

    # Calculate change values and strings
    def get_pct_change_str(curr, prev, higher_is_bad=False):
        if prev == 0:
            if curr == 0:
                return "0.0%"
            return "+100.0% 📈" if not higher_is_bad else "+100.0% 📈 ⚠️"
        val = ((curr - prev) / prev) * 100.0
        sign = "+" if val > 0 else ""
        emoji = ""
        if val > 0:
            emoji = " 📈 ⚠️" if higher_is_bad else " 📈"
        elif val < 0:
            emoji = " 📉" if higher_is_bad else " 📉 ⚠️"
        return f"{sign}{val:.1f}%{emoji}"

    def get_net_change_str(curr, prev):
        diff = curr - prev
        sign = "+" if diff > 0 else ""
        emoji = " 🚀" if diff > 0 else " 📉"
        return f"{sign}{diff:+,} {currency}{emoji}".replace("+-", "-").replace("++", "+")

    pct_inc = get_pct_change_str(inc_c, inc_p, False)
    pct_exp = get_pct_change_str(exp_c, exp_p, True)
    net_change = get_net_change_str(net_c, net_p)
    
    # Savings rate difference in percentage points
    sav_diff_pct = (sav_c - sav_p) * 100.0
    sign_sav = "+" if sav_diff_pct > 0 else ""
    emoji_sav = " 📈" if sav_diff_pct > 0 else " 📉 ⚠️"
    sav_change = f"{sign_sav}{sav_diff_pct:+.1f}%{emoji_sav}".replace("+-", "-").replace("++", "+")

    # Localized metric rows
    row_labels = {
        "ru": ["Доходы", "Расходы", "Чистый доход", "Норма сбережений"],
        "en": ["Income", "Expenses", "Net Income", "Savings Rate"],
        "kk": ["Кірістер", "Шығыстар", "Таза кіріс", "Жинақ нормасы"]
    }.get(lang, ["Income", "Expenses", "Net Income", "Savings Rate"])

    comp_rows = [
        (row_labels[0], inc_p, inc_c, pct_inc, False),
        (row_labels[1], exp_p, exp_c, pct_exp, False),
        (row_labels[2], net_p, net_c, net_change, True), # diff is raw text
        (row_labels[3], sav_p, sav_c, sav_change, False, "0.0%")
    ]

    t_row = start_trend_row + 2
    for r_idx, item in enumerate(comp_rows):
        label, p_val, c_val, change_str, is_raw_text, *custom_fmt = item
        
        ws_an.cell(row=t_row, column=1, value=label).font = font_data
        ws_an.cell(row=t_row, column=1).border = border_all
        
        # Previous Month Cell
        cell_p = ws_an.cell(row=t_row, column=2)
        if not is_raw_text:
            cell_p.value = p_val
            cell_p.number_format = custom_fmt[0] if custom_fmt else '#,##0'
        else:
            cell_p.value = f"{p_val:+,}".replace("+-", "-").replace("++", "+")
        cell_p.font = font_data
        cell_p.border = border_all
        cell_p.alignment = Alignment(horizontal="right")

        # Current Month Cell
        cell_c = ws_an.cell(row=t_row, column=3)
        if not is_raw_text:
            cell_c.value = c_val
            cell_c.number_format = custom_fmt[0] if custom_fmt else '#,##0'
        else:
            cell_c.value = f"{c_val:+,}".replace("+-", "-").replace("++", "+")
        cell_c.font = font_data
        cell_c.border = border_all
        cell_c.alignment = Alignment(horizontal="right")

        # Delta Cell
        cell_d = ws_an.cell(row=t_row, column=4, value=change_str)
        cell_d.font = font_bold
        cell_d.border = border_all
        cell_d.alignment = Alignment(horizontal="center")
        
        # Zebra striping
        if t_row % 2 == 1:
            for col in range(1, 5):
                ws_an.cell(row=t_row, column=col).fill = fill_zebra
                
        ws_an.row_dimensions[t_row].height = 20
        t_row += 1

    # Prediction Block (Right Side of Trends)
    ws_an.cell(row=start_trend_row, column=8, value=L["prediction_title"]).font = font_sec_hdr
    
    # Calculate Prediction
    now_local = datetime.now(ZoneInfo(tz_name))
    days_in_month = calendar.monthrange(now_local.year, now_local.month)[1]
    day_of_month = max(1, now_local.day)
    
    curr_month_str = now_local.strftime("%Y-%m")
    curr_month_exp = monthly_data[curr_month_str]["expense"] if curr_month_str in monthly_data else total_expense
    projected_spending = int((curr_month_exp / day_of_month) * days_in_month)
    
    # Spanning columns to prevent text clipping
    ws_an.merge_cells(start_row=start_trend_row + 1, start_column=8, end_row=start_trend_row + 1, end_column=9)
    ws_an.cell(row=start_trend_row + 1, column=8, value=L["projected_spending"]).font = font_data
    ws_an.cell(row=start_trend_row + 1, column=8).border = border_bottom
    ws_an.cell(row=start_trend_row + 1, column=9).border = border_bottom
    
    cell_proj = ws_an.cell(row=start_trend_row + 1, column=10, value=projected_spending)
    cell_proj.font = font_mono
    cell_proj.alignment = Alignment(horizontal="right")
    cell_proj.number_format = f'#,##0" {currency}"'
    cell_proj.border = border_bottom
    ws_an.row_dimensions[start_trend_row + 1].height = 22

    # Anomaly Detection Block (Pushed down to prevent overlap)
    ws_an.cell(row=start_trend_row + 7, column=1, value=L["anomalies_title"]).font = font_sec_hdr
    ws_an.row_dimensions[start_trend_row + 7].height = 28
    
    # Detect category spikes
    anomalies = []
    for cat_name, spent in sorted_cats:
        if total_category_spent > 0:
            share = spent / total_category_spent
            if share > 0.45:
                anomalies.append(
                    f"Категория {cat_name} составляет {share * 100:.1f}% расходов"
                    if lang == "ru" else
                    (f"{cat_name} санатасы шығыстардың {share * 100:.1f}% құрайды" if lang == "kk" else f"{cat_name} accounts for {share * 100:.1f}% of expenses")
                )
                
    if not anomalies:
        anomalies.append(L["no_anomalies"])
        
    a_row = start_trend_row + 6
    for anomaly in anomalies:
        ws_an.merge_cells(start_row=a_row, start_column=1, end_row=a_row, end_column=10)
        cell_an = ws_an.cell(row=a_row, column=1, value=f"• {anomaly}")
        cell_an.font = font_subtext
        cell_an.alignment = Alignment(vertical="center", indent=1)
        ws_an.row_dimensions[a_row].height = 20
        a_row += 1

    # Generous Column Widths for Analytics Sheet to prevent "Изменение д"
    widths_an = {"A": 24, "B": 15, "C": 15, "D": 15, "E": 15, "F": 4, "G": 4, "H": 25, "I": 18, "J": 24}
    for col, w in widths_an.items():
        ws_an.column_dimensions[col].width = w

    # ==========================================
    # SHEET 3: TRANSACTIONS (Clean raw table)
    # ==========================================
    ws_tx = wb.create_sheet(title=L["sheet_transactions"])
    ws_tx.views.sheetView[0].showGridLines = True
    ws_tx.append(L["raw_headers"])

    # Format headers
    for cell in ws_tx[1]:
        cell.font = font_tbl_hdr
        cell.fill = fill_tbl_hdr
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border_all
    ws_tx.row_dimensions[1].height = 26

    # Transaction type localized labels dictionary mapping
    type_local_map = {
        "ru": {"income": "Доход", "expense": "Расход", "transfer": "Перевод"},
        "en": {"income": "Income", "expense": "Expense", "transfer": "Transfer"},
        "kk": {"income": "Кіріс", "expense": "Шығыс", "transfer": "Аударма"}
    }.get(lang, {"income": "Income", "expense": "Expense", "transfer": "Transfer"})

    for idx, r in enumerate(rows_list, start=2):
        tx_id, ts, ttype, amount, account, category, emoji, note = r
        cat_display = f"{emoji} {category}".strip() if emoji or category else ""
        
        # Localize type (Income/Expense/Transfer)
        ttype_display = type_local_map.get(str(ttype or "").strip().lower(), str(ttype or ""))
        
        # Format date strictly to YYYY-MM-DD HH:MM in user's timezone to avoid raw UTC
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            local_dt = dt.astimezone(ZoneInfo(tz_name))
            clean_date = format_localized_datetime(local_dt, lang)
        except Exception:
            clean_date = str(ts)[:16].replace("T", " ") if ts else ""
        
        ws_tx.append([
            int(tx_id),
            clean_date,
            ttype_display,
            int(amount or 0),
            currency,
            str(account or ""),
            cat_display,
            str(note or ""),
        ])

        # Zebra striping
        if idx % 2 == 1:
            for cell in ws_tx[idx]:
                cell.fill = fill_zebra
                
        # Cell border and alignment formatting
        for cell_idx, cell in enumerate(ws_tx[idx], start=1):
            cell.font = font_data
            cell.border = border_all
            if cell_idx in [1, 2, 3, 5]: # ID, Date, Type, Currency
                cell.alignment = Alignment(horizontal="center")
            elif cell_idx == 4: # Amount
                cell.alignment = Alignment(horizontal="right")
            else: # Account, Category, Note
                cell.alignment = Alignment(horizontal="left")
            
        ws_tx.cell(row=idx, column=4).number_format = '#,##0'
        ws_tx.row_dimensions[idx].height = 20

    # Widths configured generously for raw transactions to fit formatted dates and amounts
    widths_tx = [10, 26, 14, 15, 10, 18, 22, 40]
    for col_idx, width in enumerate(widths_tx, start=1):
        ws_tx.column_dimensions[chr(ord("A") + col_idx - 1)].width = width

    # Output to in-memory bytes
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

    # Determine free trial status using migration-backed users column
    exports_used = await get_free_exports_used(db, user_id)

    use_premium_xlsx = False
    is_free_trial_now = False

    if full_access:
        use_premium_xlsx = True
    elif exports_used == 0:
        # Give them exactly 1 free premium export as a trial!
        use_premium_xlsx = True
        is_free_trial_now = True

    if use_premium_xlsx:
        # Fetch additional metrics and database records for Executive Summary
        from app.domain.services.financial_analysis_engine import calculate_financial_metrics
        from app.domain.services.ai_priority_engine import select_top_insights
        
        tz_name = _row_get(settings, "timezone", 1, default="Asia/Aqtobe")
        metrics = await calculate_financial_metrics(db, user_id, tz_name)
        
        cur_prof = await db.execute("SELECT user_stage, behavioral_summary, discipline_score FROM ai_profile WHERE user_id=?", (user_id,))
        row_prof = await cur_prof.fetchone()
        if row_prof:
            profile = {"stage": row_prof[0], "behavioral_summary": row_prof[1], "discipline_score": row_prof[2]}
        else:
            profile = {"stage": "chaotic", "behavioral_summary": "накапливаем статистику", "discipline_score": 100}
            
        cur_ins = await db.execute("SELECT insight_key, insight_text, confidence FROM ai_insights WHERE user_id=? AND status='active'", (user_id,))
        rows_ins = await cur_ins.fetchall()
        ai_insights = [{"key": r[0], "text": r[1], "confidence": r[2]} for r in rows_ins]
        priority_insights = select_top_insights(ai_insights)
        
        cur_rec = await db.execute(
            """
            SELECT recommendation_type, message_text, target_metric_name, target_metric_start_value, target_metric_goal_value 
            FROM ai_recommendations_log 
            WHERE user_id=? AND status='sent' 
            ORDER BY id DESC LIMIT 1
            """,
            (user_id,)
        )
        row_rec = await cur_rec.fetchone()
        if row_rec:
            latest_rec = {
                "type": row_rec[0],
                "text": row_rec[1],
                "metric": row_rec[2],
                "start": row_rec[3],
                "goal": row_rec[4]
            }
        else:
            latest_rec = None

        payload = _build_xlsx(rows, lang, currency, user_id, metrics, profile, priority_insights, latest_rec, tz_name)
        if payload is not None:
            filename = f"finance_{label}.xlsx"
            caption = {
                "ru": (
                    "📊 <b>Ваш премиум-отчет готов!</b>\n\n"
                    "Файл содержит 3 аналитические вкладки (переключайтесь между ними внизу документа):\n"
                    "1️⃣ <b>Executive Summary</b> — Главный AI-дашборд и оценка финансового здоровья\n"
                    "2️⃣ <b>Аналитика</b> — Категории, сравнение трендов и прогноз\n"
                    "3️⃣ <b>История операций</b> — Полный реестр ваших транзакций"
                ),
                "en": (
                    "📊 <b>Your premium report is ready!</b>\n\n"
                    "The file contains 3 analytical sheets (switch between them at the bottom of the document):\n"
                    "1️⃣ <b>Executive Summary</b> — Main AI dashboard and Financial Health score\n"
                    "2️⃣ <b>Analytics</b> — Category structure, trends, and month-end projection\n"
                    "3️⃣ <b>Transaction History</b> — Full transaction ledger"
                ),
                "kk": (
                    "📊 <b>Сіздің премиум есебіңіз дайын!</b>\n\n"
                    "Файл 3 талдау парағынан тұрады (құжаттың төменгі жағында ауысыңыз):\n"
                    "1️⃣ <b>Executive Summary</b> — Басты AI-дашборд және қаржылық денсаулық индексі\n"
                    "2️⃣ <b>Талдау</b> — Санаттар құрылымы, трендтер және болжам\n"
                    "3️⃣ <b>Операциялар тарихы</b> — Барлық транзакциялар тізімі"
                )
            }.get(lang, "📊 <b>Ваш премиум-отчет готов!</b>")

            await c.message.answer_document(
                BufferedInputFile(payload, filename=filename),
                caption=caption,
                parse_mode="HTML"
            )
            
            if is_free_trial_now:
                # Mark as used
                await increment_free_export(db, user_id)
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
    
    # Generate the stunning preview dynamically in a separate thread (asyncio.to_thread) to avoid blocking event loop
    png_bytes = await asyncio.to_thread(_build_downgrade_preview_png, rows, lang, currency)

    upgrade_btn_text = {
        "ru": "👑 Вернуть графики за 150 ⭐️",
        "en": "👑 Restore charts for 150 ⭐️",
        "kk": "👑 Графиктерді қайтару (150 ⭐️)",
    }.get(lang, "👑 Вернуть графики за 150 ⭐️")

    menu_btn_text = {
        "ru": "🏠 В Главное меню",
        "en": "🏠 Main Menu",
        "kk": "🏠 Басты мәзірге",
    }.get(lang, "🏠 В Главное меню")

    paywall_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=upgrade_btn_text, callback_data="upgrade:activate")],
        [InlineKeyboardButton(text=menu_btn_text, callback_data="hub:main")]
    ])

    caption_text = {
        "ru": (
            "⚠️ **Вы уже использовали свой 1 бесплатный пробный премиум-экспорт.**\n\n"
            "😔 **Посмотрите, какую красоту вы теряете без Полного доступа!**\n\n"
            "На графике выше показана динамика ваших реальных расходов и доходов за выбранный период, "
            "которую премиум-пользователи видят прямо внутри интерактивного Excel-отчета с авто-формулами и печатным дашбордом.\n\n"
            "🔥 **Верните графики в свои отчёты прямо сейчас всего за 150 ⭐️!**"
        ),
        "en": (
            "⚠️ **You have already used your 1 free premium export trial.**\n\n"
            "😔 **Look at the beauty you are missing without Full Access!**\n\n"
            "The chart above showcases the dynamic flow of your actual income and expenses during this period, "
            "which premium users interact with inside their customized Excel workbook with active dashboards.\n\n"
            "🔥 **Restore visual charts in your reports right now for just 150 ⭐️!**"
        ),
        "kk": (
            "⚠️ **Сіз 1 тегін премиум экспорт тест-драйвын пайдаланып қойдыңыз.**\n\n"
            "😔 **Толық қолжетімділіксіз қандай сұлулықты жоғалтып жатқаныңызды қараңыз!**\n\n"
            "Жоғарыдағы график таңдалған кезеңдегі нақты кірістеріңіз бен шығыстарыңыздың динамикасын көрсетеді, "
            "оны премиум қолданушылар формулалары мен дашборды бар интерактивті Excel есебінен көре алады.\n\n"
            "🔥 **Қазірдің өзінде есептеріңізге графиктерді небәрі 150 ⭐️ қайтарыңыз!**"
        )
    }.get(lang, "")

    if png_bytes:
        photo = BufferedInputFile(png_bytes, filename="premium_preview.png")
        await c.message.answer_photo(
            photo=photo,
            caption=caption_text,
            parse_mode="Markdown",
            reply_markup=paywall_kb
        )
    else:
        await c.message.answer(
            caption_text,
            parse_mode="Markdown",
            reply_markup=paywall_kb
        )
