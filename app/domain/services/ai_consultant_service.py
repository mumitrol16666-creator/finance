from __future__ import annotations

import calendar
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean
from zoneinfo import ZoneInfo

import aiosqlite

from app.db.repositories.budgets_repo import month_limits_status_map, month_key
from app.db.repositories.debts_repo import list_active_debts
from app.db.repositories.settings_repo import get_financial_goal, get_timezone
from app.db.repositories.recurring_repo import (
    recurring_due_before_month_end,
    recurring_income_due_before_month_end,
    list_recurring_expenses,
    list_recurring_incomes,
)
from app.db.repositories.ai_context_repo import get_latest_ai_context_note
from app.db.repositories.planned_repo import planned_before_month_end
from app.domain.services.reports_service import day_bounds_utc, month_bounds_utc, week_bounds_utc
from app.ui.formatters import fmt_money
from app.ui.i18n import t

ESSENTIAL_HINTS = {
    "арен", "ипот", "кредит", "коммун", "жкх", "садик", "школ", "налог",
    "подписк", "gym", "фитнес", "internet", "интернет", "связь", "mobile", "телефон",
    "netflix", "spotify", "youtube", "yandex", "яндекс", "apple", "icloud", "google",
    "страховк", "лифт", "парковк", "охрана", "домофон"
}


@dataclass
class PeriodMeta:
    kind: str
    title: str
    start: datetime
    end: datetime
    prev_start: datetime
    prev_end: datetime
    month_start: datetime
    month_end: datetime
    month_days_elapsed: int
    month_days_total: int


def _safe_tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "Asia/Aqtobe")
    except Exception:
        return ZoneInfo("UTC")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _pct(part: int | float, total: int | float) -> float:
    if not total:
        return 0.0
    return (part / total) * 100.0


def _parse_goal_amount(goal_text: str | None) -> int | None:
    if not goal_text:
        return None
    nums = re.findall(r"\d[\d\s]{2,}", goal_text)
    if not nums:
        nums = re.findall(r"\d+", goal_text)
    if not nums:
        return None
    raw = max(nums, key=len)
    raw = re.sub(r"\D", "", raw)
    if not raw:
        return None
    try:
        value = int(raw)
    except Exception:
        return None
    return value if value > 0 else None


def _kind_title(kind: str) -> str:
    return {
        "day": "за день",
        "week": "за неделю",
        "month": "за месяц",
    }.get(kind, "за период")


def build_period_meta(kind: str, tz_name: str, now_utc: datetime | None = None) -> PeriodMeta:
    now_utc = now_utc or datetime.now(timezone.utc)
    tz = _safe_tz(tz_name)

    if kind == "day":
        start, end, _label, _ = day_bounds_utc(tz_name, now_utc)
        prev_start = start - timedelta(days=1)
        prev_end = start
    elif kind == "week":
        start, end, _label, _ = week_bounds_utc(tz_name, now_utc)
        prev_start = start - timedelta(days=7)
        prev_end = start
    else:
        start, end, _label, _ = month_bounds_utc(tz_name, now_utc)
        local_start = start.astimezone(tz)
        py, pm = (local_start.year - 1, 12) if local_start.month == 1 else (local_start.year, local_start.month - 1)
        prev_local_start = datetime(py, pm, 1, 0, 0, 0, tzinfo=tz)
        if pm == 12:
            prev_local_end = datetime(py + 1, 1, 1, 0, 0, 0, tzinfo=tz)
        else:
            prev_local_end = datetime(py, pm + 1, 1, 0, 0, 0, tzinfo=tz)
        prev_start = prev_local_start.astimezone(timezone.utc)
        prev_end = prev_local_end.astimezone(timezone.utc)

    month_start, month_end, _month_label, _ = month_bounds_utc(tz_name, now_utc)
    local_now = now_utc.astimezone(tz)
    month_days_elapsed = max(1, local_now.day)
    month_days_total = calendar.monthrange(local_now.year, local_now.month)[1]

    return PeriodMeta(
        kind=kind,
        title=_kind_title(kind),
        start=start,
        end=end,
        prev_start=prev_start,
        prev_end=prev_end,
        month_start=month_start,
        month_end=month_end,
        month_days_elapsed=month_days_elapsed,
        month_days_total=month_days_total,
    )


async def _fetch_rows(db: aiosqlite.Connection, user_id: int, start: datetime, end: datetime) -> list[aiosqlite.Row]:
    cur = await db.execute(
        """
        SELECT t.id, t.ts, t.type, t.amount, COALESCE(c.name, 'Без категории') AS category_name,
               COALESCE(c.emoji, '') AS category_emoji, COALESCE(t.note, '') AS note
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.user_id = ? AND t.ts >= ? AND t.ts < ? AND t.deleted_at IS NULL
        ORDER BY t.ts ASC, t.id ASC
        """,
        (user_id, _iso(start), _iso(end)),
    )
    return await cur.fetchall()


async def _fetch_expense_category_sums(db: aiosqlite.Connection, user_id: int, start: datetime, end: datetime) -> dict[str, int]:
    cur = await db.execute(
        """
        SELECT COALESCE(c.name, 'Без категории') AS category_name, SUM(-t.amount) AS total
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.user_id = ? AND t.type = 'expense' AND t.ts >= ? AND t.ts < ? AND t.deleted_at IS NULL
        GROUP BY COALESCE(c.name, 'Без категории')
        ORDER BY total DESC
        """,
        (user_id, _iso(start), _iso(end)),
    )
    rows = await cur.fetchall()
    return {str(r[0]): int(r[1] or 0) for r in rows}


async def _fetch_month_history_expenses(db: aiosqlite.Connection, user_id: int, tz_name: str, months: int = 4) -> list[int]:
    tz = _safe_tz(tz_name)
    now = datetime.now(timezone.utc).astimezone(tz)
    vals: list[int] = []
    y, m = now.year, now.month
    for _ in range(months):
        start_local = datetime(y, m, 1, tzinfo=tz)
        if m == 12:
            end_local = datetime(y + 1, 1, 1, tzinfo=tz)
        else:
            end_local = datetime(y, m + 1, 1, 1, tzinfo=tz)
        cur = await db.execute(
            "SELECT SUM(-amount) FROM transactions WHERE user_id=? AND type='expense' AND ts>=? AND ts<? AND deleted_at IS NULL",
            (user_id, _iso(start_local.astimezone(timezone.utc)), _iso(end_local.astimezone(timezone.utc))),
        )
        row = await cur.fetchone()
        vals.append(int(row[0] or 0))
        if m == 1:
            y, m = y - 1, 12
        else:
            m -= 1
    return list(reversed(vals))


async def _fetch_active_accounts(db: aiosqlite.Connection, user_id: int):
    cur = await db.execute(
        "SELECT name, balance, currency, is_saving FROM accounts WHERE user_id=? AND is_archived=0 ORDER BY is_saving ASC, balance DESC",
        (user_id,),
    )
    return await cur.fetchall()


async def _fetch_currency(db: aiosqlite.Connection, user_id: int) -> str:
    cur = await db.execute("SELECT currency FROM settings WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    return str(row[0] or "KZT") if row else "KZT"


async def _fetch_budget_snapshot(db: aiosqlite.Connection, user_id: int, month: str) -> dict:
    status_map = await month_limits_status_map(db, user_id, month)
    over = []
    warn = []
    total_limit = 0
    total_spent = 0

    for cid, info in status_map.items():
        total_limit += int(info["limit"] or 0)
        total_spent += int(info["spent"] or 0)
        item = {
            "category_id": int(cid),
            "limit": int(info["limit"] or 0),
            "spent": int(info["spent"] or 0),
            "left": int(info["left"] or 0),
            "state": str(info["state"]),
        }
        if item["state"] == "over":
            over.append(item)
        elif item["state"] == "warn":
            warn.append(item)

    over.sort(key=lambda x: x["left"])
    warn.sort(key=lambda x: x["left"])
    return {
        "count": len(status_map),
        "over_count": len(over),
        "warn_count": len(warn),
        "total_limit": total_limit,
        "total_spent": total_spent,
        "over": over[:5],
        "warn": warn[:5],
    }


async def _fetch_category_names(db: aiosqlite.Connection, category_ids: list[int]) -> dict[int, str]:
    if not category_ids:
        return {}
    placeholders = ",".join("?" for _ in category_ids)
    cur = await db.execute(
        f"SELECT id, COALESCE(emoji, ''), name FROM categories WHERE id IN ({placeholders})",
        tuple(category_ids),
    )
    rows = await cur.fetchall()
    out: dict[int, str] = {}
    for row in rows:
        cid = int(row[0])
        emoji = str(row[1] or "")
        name = str(row[2] or "Без категории")
        out[cid] = f"{emoji + ' ' if emoji else ''}{name}"
    return out


async def _fetch_debt_snapshot(db: aiosqlite.Connection, user_id: int) -> dict:
    rows = await list_active_debts(db, user_id)
    out_total = 0
    in_total = 0
    monthly_out = 0
    overdue = 0
    due_today = 0
    soon = 0
    nearest: list[dict] = []
    from app.domain.time_utils import today_in_user_tz
    today = await today_in_user_tz(db, user_id)

    for row in rows:
        if hasattr(row, "keys"):
            debt = {k: row[k] for k in row.keys()}
        else:
            debt = {
                "id": row[0], "title": row[1], "payment_amount": row[2], "next_payment_date": row[3],
                "remaining_amount": row[4], "dtype": row[5], "direction": row[6], "is_active": row[7], "status": row[8],
            }

        direction = str(debt.get("direction") or "out")
        remaining = int(debt.get("remaining_amount") or 0)
        payment_amount = int(debt.get("payment_amount") or 0)
        status = str(debt.get("status") or "active")
        next_payment_date = debt.get("next_payment_date")

        if direction == "out":
            out_total += remaining
            monthly_out += payment_amount
        else:
            in_total += remaining

        if status == "overdue":
            overdue += 1
        elif status == "due_today":
            due_today += 1

        due_dt = None
        if next_payment_date:
            try:
                due_dt = datetime.strptime(str(next_payment_date), "%Y-%m-%d").date()
            except Exception:
                due_dt = None
        if due_dt and 0 <= (due_dt - today).days <= 7:
            soon += 1

        nearest.append({
            "title": str(debt.get("title") or "Долг"),
            "remaining": remaining,
            "payment_amount": payment_amount,
            "next_payment_date": str(next_payment_date or ""),
            "status": status,
            "direction": direction,
            "dtype": str(debt.get("dtype") or "private"),
        })

    nearest.sort(key=lambda x: (0 if x["status"] == "overdue" else 1 if x["status"] == "due_today" else 2,
                                x["next_payment_date"] or "9999-99-99"))
    return {
        "active_count": len(rows),
        "out_total": out_total,
        "in_total": in_total,
        "monthly_out": monthly_out,
        "overdue_count": overdue,
        "due_today_count": due_today,
        "due_soon_count": soon,
        "nearest": nearest[:5],
    }


def _summarize(rows: list[aiosqlite.Row], tz_name: str) -> dict:
    tz = _safe_tz(tz_name)
    income = 0
    expense = 0
    tx_count = 0
    expense_rows: list[tuple[datetime, int, str, str]] = []
    category_sum: defaultdict[str, int] = defaultdict(int)
    category_count: defaultdict[str, int] = defaultdict(int)
    notes_counter: Counter[str] = Counter()
    weekday_expense = 0
    weekend_expense = 0
    evening_expense = 0
    morning_expense = 0
    small_expense_sum = 0
    small_expense_count = 0
    daily_expense_map: defaultdict[str, int] = defaultdict(int)

    for row in rows:
        tx_count += 1
        ts_raw = str(row["ts"])
        try:
            dt_utc = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            dt_utc = datetime.now(timezone.utc)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        local_dt = dt_utc.astimezone(tz)
        ttype = str(row["type"] or "")
        amount = int(row["amount"] or 0)
        note = str(row["note"] or "").strip()
        category_name = str(row["category_name"] or "Без категории")

        if ttype == "income":
            income += amount
            continue
        if ttype != "expense":
            continue

        exp_amt = int(-amount)
        expense += exp_amt
        expense_rows.append((local_dt, exp_amt, category_name, note))
        category_sum[category_name] += exp_amt
        category_count[category_name] += 1
        daily_expense_map[local_dt.date().isoformat()] += exp_amt

        if note:
            notes_counter[note[:80]] += 1

        if local_dt.weekday() >= 5:
            weekend_expense += exp_amt
        else:
            weekday_expense += exp_amt

        if local_dt.hour >= 18:
            evening_expense += exp_amt
        elif local_dt.hour < 12:
            morning_expense += exp_amt

        if exp_amt <= 3000:
            small_expense_sum += exp_amt
            small_expense_count += 1

    top_categories = sorted(category_sum.items(), key=lambda x: x[1], reverse=True)
    top_notes = notes_counter.most_common(4)
    biggest = max(expense_rows, key=lambda x: x[1], default=None)
    avg_expense = int(round(mean([r[1] for r in expense_rows]))) if expense_rows else 0
    active_days = max(1, len(daily_expense_map)) if expense > 0 else 1
    avg_per_active_day = int(round(expense / active_days)) if expense else 0

    return {
        "income": income,
        "expense": expense,
        "net": income - expense,
        "tx_count": tx_count,
        "expense_tx_count": len(expense_rows),
        "top_categories": top_categories,
        "category_count": dict(category_count),
        "top_notes": top_notes,
        "biggest": biggest,
        "avg_expense": avg_expense,
        "avg_per_active_day": avg_per_active_day,
        "weekday_expense": weekday_expense,
        "weekend_expense": weekend_expense,
        "evening_expense": evening_expense,
        "morning_expense": morning_expense,
        "small_expense_sum": small_expense_sum,
        "small_expense_count": small_expense_count,
        "daily_expense_map": dict(daily_expense_map),
    }


async def _fetch_recurring_snapshot(db: aiosqlite.Connection, user_id: int, tz_name: str, month_end: datetime) -> dict:
    tz = _safe_tz(tz_name)
    local_today = datetime.now(tz).date().isoformat()
    local_month_end = month_end.astimezone(tz).date().isoformat()
    rows = await recurring_due_before_month_end(db, user_id, local_today, local_month_end)
    total = 0
    items: list[dict] = []
    for row in rows:
        amount = int(row[2] or 0)
        total += amount
        items.append({
            "id": int(row[0]),
            "title": str(row[1] or "—"),
            "amount": amount,
            "comment": str(row[6] or ""),
            "next_run_date": str(row[7] or ""),
        })
    return {"count": len(items), "total": total, "items": items[:5]}


async def _fetch_recurring_income_snapshot(db: aiosqlite.Connection, user_id: int, tz_name: str, month_end: datetime) -> dict:
    tz = _safe_tz(tz_name)
    local_today = datetime.now(tz).date().isoformat()
    local_month_end = month_end.astimezone(tz).date().isoformat()
    rows = await recurring_income_due_before_month_end(db, user_id, local_today, local_month_end)
    total = 0
    items: list[dict] = []
    for row in rows:
        amount = int(row[2] or 0)
        total += amount
        items.append({
            "id": int(row[0]),
            "title": str(row[1] or "—"),
            "amount": amount,
            "comment": str(row[6] or ""),
            "next_run_date": str(row[7] or ""),
        })
    return {"count": len(items), "total": total, "items": items[:5]}



async def _fetch_planned_snapshot(db: aiosqlite.Connection, user_id: int, tz_name: str, month_end: datetime) -> dict:
    tz = _safe_tz(tz_name)
    local_today = datetime.now(tz).date().isoformat()
    local_month_end = month_end.astimezone(tz).date().isoformat()
    rows = await planned_before_month_end(db, user_id, local_today, local_month_end)
    income_total = 0
    expense_total = 0
    required_income_total = 0
    required_expense_total = 0
    flexible_income_total = 0
    flexible_expense_total = 0
    items: list[dict] = []
    for row in rows:
        amount = int(row[3] or 0)
        kind = str(row[1] or 'expense')
        is_required = int(row[8] or 0) == 1
        if kind == 'income':
            income_total += amount
            if is_required:
                required_income_total += amount
            else:
                flexible_income_total += amount
        else:
            expense_total += amount
            if is_required:
                required_expense_total += amount
            else:
                flexible_expense_total += amount
        items.append({
            'id': int(row[0]),
            'kind': kind,
            'title': str(row[2] or '—'),
            'amount': amount,
            'planned_date': str(row[6] or ''),
            'comment': str(row[7] or ''),
            'is_required': is_required,
        })
    return {
        'count': len(items),
        'income_total': income_total,
        'expense_total': expense_total,
        'net': income_total - expense_total,
        'required_income_total': required_income_total,
        'required_expense_total': required_expense_total,
        'flexible_income_total': flexible_income_total,
        'flexible_expense_total': flexible_expense_total,
        'required_net': required_income_total - required_expense_total,
        'flexible_net': flexible_income_total - flexible_expense_total,
        'required_count': sum(1 for x in items if x['is_required']),
        'flexible_count': sum(1 for x in items if not x['is_required']),
        'items': items[:5]
    }

async def _fetch_data_quality_note(db: aiosqlite.Connection, user_id: int, kind: str) -> dict | None:
    note = await get_latest_ai_context_note(db, user_id, note_type="report_clarification", period_kind=kind)
    if note:
        return note
    return await get_latest_ai_context_note(db, user_id, note_type="report_clarification", period_kind="month")


def _collect_activity_metrics(rows: list[aiosqlite.Row], tz_name: str) -> dict:
    tz = _safe_tz(tz_name)
    active_days: set[str] = set()
    income_days: set[str] = set()
    expense_days: set[str] = set()
    income_count = 0
    expense_count = 0
    categories: set[str] = set()
    notes_count = 0
    recurring_signals: Counter[str] = Counter()

    for row in rows:
        ts_raw = str(row["ts"])
        try:
            dt_utc = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except Exception:
            dt_utc = datetime.now(timezone.utc)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        local_day = dt_utc.astimezone(tz).date().isoformat()
        active_days.add(local_day)
        ttype = str(row["type"] or "")
        if ttype == "income":
            income_count += 1
            income_days.add(local_day)
        elif ttype == "expense":
            expense_count += 1
            expense_days.add(local_day)
            categories.add(str(row["category_name"] or "Без категории"))
            note = str(row["note"] or "").strip()
            if note:
                notes_count += 1
                recurring_signals[note[:40].lower()] += 1
            cat = str(row["category_name"] or "").strip().lower()
            if cat:
                recurring_signals[cat[:40]] += 1

    repeated = [name for name, cnt in recurring_signals.items() if cnt >= 2 and name]
    return {
        "active_days": len(active_days),
        "income_days": len(income_days),
        "expense_days": len(expense_days),
        "income_count": income_count,
        "expense_count": expense_count,
        "tx_count": len(rows),
        "expense_categories_count": len(categories),
        "notes_count": notes_count,
        "repeated_signals": repeated[:8],
    }


def _has_possible_missing_recurring(current_rows: list[aiosqlite.Row], previous_rows: list[aiosqlite.Row]) -> bool:
    hints: Counter[str] = Counter()
    for row in [*current_rows, *previous_rows]:
        if str(row["type"] or "") != "expense":
            continue
        cat = str(row["category_name"] or "").lower()
        note = str(row["note"] or "").lower()
        for source in (cat, note):
            if not source:
                continue
            if any(token in source for token in ESSENTIAL_HINTS):
                hints[source[:50]] += 1
    return any(cnt >= 1 for cnt in hints.values())


def _build_data_quality(kind: str, current_metrics: dict, previous_metrics: dict, month_metrics: dict, *,
                        has_goal: bool, has_limits: bool, has_debts: bool, has_planned: bool,
                        recurring_count: int, recurring_income_count: int, clarification_present: bool,
                        possible_missing_recurring: bool, stale_recurring_count: int = 0) -> dict:
    blockers: list[str] = []
    warnings: list[str] = []
    recommendations: list[str] = []

    active_days = month_metrics["active_days"] if kind == "month" else current_metrics["active_days"]
    tx_count = month_metrics["tx_count"] if kind == "month" else current_metrics["tx_count"]
    income_count = month_metrics["income_count"] if kind == "month" else current_metrics["income_count"]
    expense_count = month_metrics["expense_count"] if kind == "month" else current_metrics["expense_count"]
    categories_count = month_metrics["expense_categories_count"] if kind == "month" else current_metrics["expense_categories_count"]

    if active_days < 21:
        blockers.append(f"мало активных дней для глубокого анализа: {active_days}")
        recommendations.append("Продолжай вести учет! AI-отчет станет доступен после 21 дня активного ведения, чтобы анализ был максимально точным и без догадок.")
    if tx_count < 30:
        blockers.append(f"недостаточно операций для статистики: {tx_count}")
        recommendations.append("для качественного разбора нужно хотя бы 30-40 записей, чтобы увидеть реальные паттерны трат")
    if income_count == 0:
        blockers.append("нет занесённых доходов за базовый период")
        recommendations.append("заноси все реальные доходы, иначе свободный остаток и прогноз искажаются")
    if expense_count == 0:
        blockers.append("нет занесённых расходов за базовый период")
        recommendations.append("без расходов AI не видит структуру трат и не может искать утечки")
    if categories_count < 3 and expense_count > 0:
        blockers.append(f"слишком узкая картина по категориям: {categories_count}")
        recommendations.append("раскидай расходы хотя бы по нескольким категориям, иначе анализ будет плоским")

    sufficient_for_compare = previous_metrics["active_days"] >= 8 and previous_metrics["tx_count"] >= 12 and previous_metrics["expense_count"] > 0
    if not sufficient_for_compare:
        warnings.append("сравнение с прошлым периодом ограничено: прошлый период заполнен слабо")

    sufficient_for_forecast = active_days >= 12 and expense_count >= 10 and income_count >= 1
    if not sufficient_for_forecast:
        warnings.append("прогноз по будущим месяцам грубый: база для темпа пока слабая")

    if recurring_count == 0 and recurring_income_count == 0:
        warnings.append("не заполнен блок постоянных операций — прогноз может быть неполным")
        recommendations.append("проверь постоянные расходы и доходы: аренда, связь, подписки, зарплата, транспорт")
    elif recurring_count == 0:
        warnings.append("постоянные расходы не заполнены или заполнены слабо")
        recommendations.append("если есть аренда, подписки, связь или другие обязательные платежи — внеси их как постоянные")

    if possible_missing_recurring and recurring_count == 0:
        warnings.append("по операциям видны признаки регулярных трат, но блок постоянных расходов пуст")

    if not has_limits:
        warnings.append("лимиты категорий не заданы — AI не видит твою планку по тратам")
    if not has_planned:
        warnings.append("планируемые операции не заполнены — будущие разовые движения денег могут отсутствовать")
    if has_debts and not sufficient_for_forecast:
        warnings.append("при долгах слабая база особенно режет точность прогноза")
    if not clarification_present:
        warnings.append("нет пользовательского уточнения: были ли незанесённые траты и нетипичные операции")
    if stale_recurring_count > 0:
        warnings.append(f"найдено неактивных постоянных операций: {stale_recurring_count}")
        recommendations.append("🧹 Похоже, некоторые подписки или платежи больше не активны. Проверь и удали их для чистоты прогноза.")

    confidence = "high" if not blockers and sufficient_for_compare and sufficient_for_forecast else ("medium" if not blockers else "low")
    sufficient_for_deep_report = not blockers

    return {
        "active_days": active_days,
        "tx_count": tx_count,
        "income_count": income_count,
        "expense_count": expense_count,
        "categories_count": categories_count,
        "sufficient_for_deep_report": sufficient_for_deep_report,
        "sufficient_for_compare": sufficient_for_compare,
        "sufficient_for_forecast": sufficient_for_forecast,
        "blockers": blockers,
        "warnings": warnings[:6],
        "recommendations": recommendations[:6],
        "confidence": confidence,
        "has_goal": has_goal,
        "has_limits": has_limits,
        "has_debts": has_debts,
        "has_planned": has_planned,
        "recurring_count": recurring_count,
        "recurring_income_count": recurring_income_count,
        "clarification_present": clarification_present,
    }


async def build_ai_context(db: aiosqlite.Connection, user_id: int, tz_name: str, kind: str, goal_text: str | None) -> dict:
    meta = build_period_meta(kind, tz_name)
    current_rows = await _fetch_rows(db, user_id, meta.start, meta.end)
    previous_rows = await _fetch_rows(db, user_id, meta.prev_start, meta.prev_end)
    month_rows = await _fetch_rows(db, user_id, meta.month_start, meta.month_end)
    current = _summarize(current_rows, tz_name)
    previous = _summarize(previous_rows, tz_name)
    month = _summarize(month_rows, tz_name)
    current_metrics = _collect_activity_metrics(current_rows, tz_name)
    previous_metrics = _collect_activity_metrics(previous_rows, tz_name)
    month_metrics = _collect_activity_metrics(month_rows, tz_name)
    month_history = await _fetch_month_history_expenses(db, user_id, tz_name, months=4)
    prev_cat = await _fetch_expense_category_sums(db, user_id, meta.prev_start, meta.prev_end)
    goal_amount = _parse_goal_amount(goal_text)
    active_accounts = await _fetch_active_accounts(db, user_id)
    currency = await _fetch_currency(db, user_id)
    budget_month = month_key(meta.month_start.astimezone(_safe_tz(tz_name)).date())
    budget_snapshot = await _fetch_budget_snapshot(db, user_id, budget_month)
    category_name_map = await _fetch_category_names(db, [x["category_id"] for x in (budget_snapshot["over"] + budget_snapshot["warn"]) if x.get("category_id")])
    for bucket in (budget_snapshot["over"], budget_snapshot["warn"]):
        for item in bucket:
            item["category_name"] = category_name_map.get(item["category_id"], f"Категория #{item['category_id']}")
    debt_snapshot = await _fetch_debt_snapshot(db, user_id)
    recurring_snapshot = await _fetch_recurring_snapshot(db, user_id, tz_name, meta.month_end)
    recurring_income_snapshot = await _fetch_recurring_income_snapshot(db, user_id, tz_name, meta.month_end)
    planned_snapshot = await _fetch_planned_snapshot(db, user_id, tz_name, meta.month_end)
    clarification_note = await _fetch_data_quality_note(db, user_id, kind)

    projected_month_expense = int(round(month["expense"] / max(1, meta.month_days_elapsed) * meta.month_days_total)) if month["expense"] else 0
    projected_month_income = int(round(month["income"] / max(1, meta.month_days_elapsed) * meta.month_days_total)) if month["income"] else 0
    projected_month_expense += int(recurring_snapshot.get("total") or 0)
    projected_month_income += int(recurring_income_snapshot.get("total") or 0)
    projected_month_expense += int(planned_snapshot.get("expense_total") or 0)
    projected_month_income += int(planned_snapshot.get("income_total") or 0)
    projected_free_cash = projected_month_income - projected_month_expense
    projected_required_free_cash = projected_month_income - projected_month_expense - int(planned_snapshot.get("flexible_income_total") or 0) + int(planned_snapshot.get("flexible_expense_total") or 0)
    # Calculate totals per currency for regular accounts
    currency_totals = {}
    for r in active_accounts:
        # r[1] = balance, r[2] = currency, r[3] = is_saving
        if not r[3]: # not a saving account
            curr = r[2] or "KZT"
            currency_totals[curr] = currency_totals.get(curr, 0) + int(r[1] or 0)
    
    # We still need a numeric 'total_balance' for some legacy calculations (like runway)
    # Let's sum them all as-is (this is slightly incorrect for mixed currencies but good for a 'raw' metric)
    raw_total_balance = sum(int(r[1] or 0) for r in active_accounts if not r[3])
    
    # Store the formatted multicurrency total in context
    from app.domain.money import fmt_money_compact
    if not currency_totals:
        fmt_total_balance = fmt_money_compact(0, "KZT")
    else:
        fmt_total_balance = ", ".join([fmt_money_compact(val, curr) for curr, val in currency_totals.items()])

    runway_days = int(raw_total_balance / max(1, month["avg_per_active_day"])) if month["avg_per_active_day"] > 0 else None

    adjustable = []
    for cat, amount in current["top_categories"]:
        lc = cat.lower()
        if any(h in lc for h in ESSENTIAL_HINTS):
            continue
        adjustable.append((cat, amount))
    if not adjustable:
        adjustable = current["top_categories"][:]

    category_deltas = []
    for cat, amount in current["top_categories"][:5]:
        diff = amount - int(prev_cat.get(cat, 0))
        category_deltas.append((cat, amount, diff))

    eta_current_months = None
    eta_with_cut_months = None
    if goal_amount and projected_free_cash > 0:
        eta_current_months = max(1, round(goal_amount / projected_free_cash))
    scenario_savings_20 = []
    total_scenario_20 = 0
    for cat, amount in adjustable[:2]:
        save = int(round(amount * 0.2))
        total_scenario_20 += save
        scenario_savings_20.append((cat, save))
    if goal_amount and projected_free_cash + total_scenario_20 > 0:
        eta_with_cut_months = max(1, round(goal_amount / (projected_free_cash + total_scenario_20)))

    debt_pressure_ratio = 0.0
    if debt_snapshot["monthly_out"] > 0 and month["income"] > 0:
        debt_pressure_ratio = debt_snapshot["monthly_out"] / month["income"]

    # Hygiene Audit: find "ghost" recurring items (inactive for 60+ days)
    all_expenses = await list_recurring_expenses(db, user_id)
    all_incomes = await list_recurring_incomes(db, user_id)
    stale_recurring_count = 0
    from app.domain.time_utils import now_in_user_tz
    now = (await now_in_user_tz(db, user_id)).replace(tzinfo=None)
    for r in [*all_expenses, *all_incomes]:
        last_activity = r[9] # last_paid_at or last_received_at
        created_at = r[8] if len(r) > 8 else None # fallback
        
        # Determine the effective "last seen" date
        ref_date_str = last_activity or created_at
        if ref_date_str:
            try:
                ref_dt = datetime.fromisoformat(ref_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                if (now - ref_dt).days > 60:
                    stale_recurring_count += 1
            except Exception:
                pass

    data_quality = _build_data_quality(
        kind,
        current_metrics,
        previous_metrics,
        month_metrics,
        has_goal=bool(goal_text),
        has_limits=bool(budget_snapshot.get("count")),
        has_debts=bool(debt_snapshot.get("active_count")),
        has_planned=bool(planned_snapshot.get("count")),
        recurring_count=int(recurring_snapshot.get("count") or 0),
        stale_recurring_count=stale_recurring_count,
        recurring_income_count=int(recurring_income_snapshot.get("count") or 0),
        clarification_present=bool(clarification_note and clarification_note.get("content")),
        possible_missing_recurring=_has_possible_missing_recurring(current_rows, previous_rows),
    )

    return {
        "meta": meta,
        "currency": currency,
        "goal_text": goal_text,
        "goal_amount": goal_amount,
        "current": current,
        "previous": previous,
        "month": month,
        "month_history": month_history,
        "active_accounts": active_accounts,
        "total_balance": raw_total_balance,
        "fmt_total_balance": fmt_total_balance,
        "runway_days": runway_days,
        "projected_month_income": projected_month_income,
        "projected_month_expense": projected_month_expense,
        "projected_free_cash": projected_free_cash,
        "projected_required_free_cash": projected_required_free_cash,
        "scenario_savings_20": scenario_savings_20,
        "scenario_total_20": total_scenario_20,
        "eta_current_months": eta_current_months,
        "eta_with_cut_months": eta_with_cut_months,
        "category_deltas": category_deltas,
        "budget_snapshot": budget_snapshot,
        "debt_snapshot": debt_snapshot,
        "recurring_snapshot": recurring_snapshot,
        "recurring_income_snapshot": recurring_income_snapshot,
        "planned_snapshot": planned_snapshot,
        "debt_pressure_ratio": debt_pressure_ratio,
        "current_metrics": current_metrics,
        "previous_metrics": previous_metrics,
        "month_metrics": month_metrics,
        "clarification_note": clarification_note,
        "data_quality": data_quality,
    }

def _line(label: str, value: str) -> str:
    return f"• {label}: <b>{value}</b>"


def render_ai_insufficient_report(context: dict) -> str:
    quality = context.get("data_quality") or {}
    lines = [
        "🤖 <b>Пока без глубокого разбора</b>",
        "",
        "Сейчас я не хочу делать красивый, но пустой отчёт. База ещё слабая, поэтому честный глубокий разбор пока рано.",
        "",
        "<b>Что мешает сделать сильный разбор</b>",
    ]
    for item in quality.get("blockers") or ["данных пока слишком мало"]:
        lines.append(f"• {item}")
    if quality.get("warnings"):
        lines.extend(["", "<b>Что ещё снижает точность</b>"])
        for item in quality.get("warnings")[:4]:
            lines.append(f"• {item}")
    lines.extend(["", "<b>Что сделать дальше</b>"])
    recs = quality.get("recommendations") or ["стабильно вести учёт хотя бы один полный месяц"]
    for item in recs[:5]:
        lines.append(f"• {item}")
    note = context.get("clarification_note") or {}
    if note.get("content"):
        lines.extend(["", "<b>Твоё уточнение</b>", f"• {note['content']}"])
    lines.extend([
        "",
        "Сейчас лучше либо быстро уточнить данные, либо задать один конкретный вопрос. Когда в базе будет нормальный месяц учёта, AI сможет делать уже полноценный разбор по тратам, лимитам, долгам и цели.",
    ])
    return "\n".join(lines)


SYSTEM_PROMPT_RECURRING_DISCOVERY = """
Ты — эксперт по анализу банковских выписок. Твоя задача — найти ПОВТОРЯЮЩИЕСЯ (регулярные) платежи в истории транзакций.

ВХОДНЫЕ ДАННЫЕ:
1. Список последних транзакций (дата, сумма, категория, заметка).
2. Список УЖЕ СУЩЕСТВУЮЩИХ регулярных планов (чтобы не предлагать дубликаты).

КРИТЕРИИ ДЛЯ ВЫБОРА:
- Это типичные подписки (Netflix, Spotify, iCloud, мобильная связь).
- Это аренда, коммуналка, ипотека, садик, школа.
- Это зарплата или регулярные пополнения.
- ИГНОРИРУЙ: разовые покупки в магазинах, такси, рестораны (даже если они повторяются часто — это не подписки).

ПРАВИЛА:
- Группируй похожие записи, даже если заметки чуть-чуть отличаются (например, "Аренда май" и "Аренда июнь").
- Для каждой найденной группы верни JSON:
  - "title": понятное название (например, "Аренда квартиры")
  - "amount": средняя сумма (целое число)
  - "kind": "expense" или "income"
  - "day": день месяца (от 1 до 28), когда обычно проходит платеж
  - "category_hint": название категории
  - "reason": почему ты считаешь это регулярным (коротко)

Верни ТОЛЬКО валидный JSON-массив объектов. Если ничего не нашел — [].
""".strip()


def render_ai_question_answer(context: dict, question: str) -> str:
    quality = context.get("data_quality") or {}
    month = context.get("month") or {}
    lines = ["🤖 <b>Ответ на твой вопрос</b>", "", f"<b>Вопрос</b>: {question}", ""]
    if not quality.get("sufficient_for_deep_report"):
        lines.append("Сейчас могу дать только грубую оценку. Данных пока недостаточно для точного вывода без выдумки.")
    else:
        lines.append("Ниже ответ по текущим данным без догадок сверх базы.")
    lines.extend(["", "<b>Что вижу по данным</b>"])
    lines.append(f"• доходы за месяц: <b>{fmt_money(int(month.get('income') or 0))}</b>")
    lines.append(f"• расходы за месяц: <b>{fmt_money(int(month.get('expense') or 0))}</b>")
    lines.append(f"• прогноз свободного остатка: <b>{fmt_money(int(context.get('projected_free_cash') or 0))}</b>")
    req_cash = int(context.get('projected_required_free_cash') or 0)
    lines.append(f"• после обязательных будущих движений: <b>{fmt_money(req_cash)}</b>")
    if context.get('goal_text'):
        lines.append(f"• текущая цель: <b>{context.get('goal_text')}</b>")
    lines.extend(["", "<b>Оценка</b>"])
    if req_cash < 0:
        lines.append("• по текущей базе обязательные расходы уже съедают безопасный остаток — крупную покупку без пересборки плана считать преждевременно")
    elif int(context.get('projected_free_cash') or 0) <= 0:
        lines.append("• при текущем темпе свободный остаток к концу периода не формируется — покупку или новую цель тянуть опасно")
    else:
        lines.append("• положительный остаток есть, но решение зависит от горизонта, цены вопроса и полноты учёта обязательных трат")
    if not quality.get('sufficient_for_forecast'):
        lines.append("• прогноз ограничен: темп учёта и история ещё слабые")
    lines.extend(["", "<b>Что нужно, чтобы ответ был сильнее</b>"])
    for item in (quality.get('recommendations') or ["вести учёт стабильнее ещё хотя бы несколько недель"])[:4]:
        lines.append(f"• {item}")
    return "\n".join(lines)


def render_ai_report(context: dict) -> str:
    quality = context.get("data_quality") or {}
    if not quality.get("sufficient_for_deep_report"):
        return render_ai_insufficient_report(context)
    meta: PeriodMeta = context["meta"]
    current = context["current"]
    previous = context["previous"]
    month = context["month"]
    goal_text = context.get("goal_text") or "цель не задана"
    projected_month_expense = int(context["projected_month_expense"] or 0)
    projected_free_cash = int(context["projected_free_cash"] or 0)
    projected_required_free_cash = int(context.get("projected_required_free_cash") or 0)
    category_deltas = context["category_deltas"]
    scenario_savings_20 = context["scenario_savings_20"]
    scenario_total_20 = int(context["scenario_total_20"] or 0)
    eta_current = context.get("eta_current_months")
    eta_cut = context.get("eta_with_cut_months")
    total_balance = int(context.get("total_balance") or 0)
    runway_days = context.get("runway_days")
    budget_snapshot = context.get("budget_snapshot") or {}
    debt_snapshot = context.get("debt_snapshot") or {}
    recurring_snapshot = context.get("recurring_snapshot") or {}
    recurring_income_snapshot = context.get("recurring_income_snapshot") or {}
    planned_snapshot = context.get("planned_snapshot") or {}
    debt_pressure_ratio = float(context.get("debt_pressure_ratio") or 0.0)

    expense_diff = current["expense"] - previous["expense"]
    income_diff = current["income"] - previous["income"]

    # Calculate Goal Progress
    goal_amount = context.get("goal_amount")
    goal_progress_bar = ""
    if goal_amount and goal_amount > 0:
        # We need to know how much is saved/available for the goal
        # For simplicity, let's assume total_balance is what's being saved
        # or we could use a specific account. Let's use total_balance for now.
        progress = min(100, int((total_balance / goal_amount) * 100))
        filled = int(progress / 10)
        bar = "🔵" * filled + "⚪" * (10 - filled)
        goal_progress_bar = f"\n📈 Прогресс: {bar} <b>{progress}%</b>"

    lines = [
        f"🤖 <b>AI-анализ {meta.title}</b>",
        "────────────────",
        f"🎯 Цель: <b>{goal_text}</b>{goal_progress_bar}",
        "",
        "<b>💰 ИТОГИ ПЕРИОДА</b>",
        f"• Доходы: <b>{fmt_money(current['income'])}</b>",
        f"• Расходы: <b>{fmt_money(current['expense'])}</b>",
        f"• Чистый итог: <b>{fmt_money(current['net'])}</b>",
        "",
    ]

    if current["top_categories"]:
        lines.extend(["<b>📂 ГДЕ ДЕНЬГИ? (Топ-4)</b>"])
        for cat, amount in current["top_categories"][:4]:
            share = _pct(amount, max(1, current["expense"]))
            lines.append(f"• {cat} — <b>{fmt_money(amount)}</b> ({share:.1f}%)")
        lines.append("")

    insights: list[str] = []
    if month["expense"] > 0 and projected_month_expense > month["expense"]:
        insights.append(
            f"При текущем темпе к концу месяца расход может выйти примерно на <b>{fmt_money(projected_month_expense)}</b>."
        )
    if current["small_expense_sum"] >= max(15000, current["expense"] * 0.15):
        insights.append(
            f"Мелкие расходы до 3 000 уже набрали <b>{fmt_money(current['small_expense_sum'])}</b> в сумме."
        )
    if current["evening_expense"] > current["expense"] * 0.45:
        insights.append("Почти половина расходов приходится на вечер — это похоже на импульсивные покупки.")
    if current["weekend_expense"] > current["weekday_expense"] and current["expense"] > 0:
        insights.append("На выходных траты выше, чем в будни — стоит отдельно контролировать лимит на выходные.")
    if category_deltas:
        hot_cat, _hot_amt, hot_diff = max(category_deltas, key=lambda x: x[2])
        if hot_diff > 0:
            insights.append(
                f"Сильнее всего выросла категория <b>{hot_cat}</b>: +<b>{fmt_money(hot_diff)}</b> к прошлому такому же периоду."
            )
    if current["top_notes"]:
        repeated = [n for n in current["top_notes"] if n[1] > 1]
        if repeated:
            notes_preview = ", ".join(f"{text} ×{cnt}" for text, cnt in repeated[:3])
            insights.append(f"По заметкам повторяются траты: <b>{notes_preview}</b>.")

    if total_balance > 0:
        insights.append(f"На счетах сейчас около <b>{fmt_money(total_balance)}</b>.")
        if runway_days is not None and runway_days <= 21 and month["avg_per_active_day"] > 0:
            insights.append(f"При текущем среднем темпе расходов этого хватит примерно на <b>{runway_days} дн.</b> без новых поступлений.")

    if budget_snapshot.get("over_count"):
        insights.append(f"Есть категории с перерасходом лимита: <b>{budget_snapshot['over_count']}</b> шт.")
    elif budget_snapshot.get("warn_count"):
        insights.append(f"Есть категории на грани лимита: <b>{budget_snapshot['warn_count']}</b> шт.")

    if recurring_snapshot.get("count"):
        insights.append(f"До конца месяца ещё ожидается постоянных расходов: <b>{fmt_money(int(recurring_snapshot['total']))}</b> по <b>{recurring_snapshot['count']}</b> шаблонам.")
    if recurring_income_snapshot.get("count"):
        insights.append(f"До конца месяца ещё ожидается постоянных доходов: <b>{fmt_money(int(recurring_income_snapshot['total']))}</b> по <b>{recurring_income_snapshot['count']}</b> шаблонам.")
    if planned_snapshot.get("count"):
        insights.append(f"Плюс висит разовых планируемых движений: <b>{fmt_money(int(planned_snapshot.get('net') or 0))}</b> по <b>{planned_snapshot['count']}</b> операциям.")
        if planned_snapshot.get("required_count"):
            insights.append(f"Из них обязательные разовые операции дают эффект <b>{fmt_money(int(planned_snapshot.get('required_net') or 0))}</b> по <b>{planned_snapshot['required_count']}</b> операциям.")

    if debt_snapshot.get("active_count"):
        if debt_snapshot.get("overdue_count"):
            insights.append(f"Есть просроченные долги: <b>{debt_snapshot['overdue_count']}</b>.")
        elif debt_snapshot.get("due_today_count"):
            insights.append("По долгам есть платёж сегодня — это повышает давление на кэшфлоу.")
        elif debt_snapshot.get("due_soon_count"):
            insights.append(f"В ближайшие 7 дней ожидается платежей по долгам: <b>{debt_snapshot['due_soon_count']}</b>.")

    if insights:
        lines.extend(["", "<b>Что видно по данным</b>"])
        lines.extend(f"• {x}" for x in insights[:6])

    if budget_snapshot.get("over_count") or budget_snapshot.get("warn_count"):
        lines.extend(["", "<b>Риск по лимитам</b>"])
        for item in budget_snapshot.get("over", [])[:3]:
            lines.append(
                f"• {item['category_name']} — перерасход <b>{fmt_money(abs(int(item['left'])))}</b> "
                f"(лимит {fmt_money(int(item['limit']))}, уже потрачено {fmt_money(int(item['spent']))})"
            )
        for item in budget_snapshot.get("warn", [])[:2]:
            lines.append(
                f"• {item['category_name']} — осталось около <b>{fmt_money(max(0, int(item['left'])))}</b> до лимита"
            )

    if debt_snapshot.get("active_count"):
        lines.extend(["", "<b>Долговое давление</b>"])
        lines.append(f"• Активных записей: <b>{debt_snapshot['active_count']}</b>")
        if debt_snapshot.get("out_total"):
            lines.append(f"• Ты должен всего: <b>{fmt_money(int(debt_snapshot['out_total']))}</b>")
        if debt_snapshot.get("monthly_out"):
            lines.append(f"• Регулярная долговая нагрузка: <b>{fmt_money(int(debt_snapshot['monthly_out']))}</b> за цикл")
        if debt_pressure_ratio >= 0.35:
            lines.append("• Долговая нагрузка уже тяжёлая относительно текущих доходов.")
        elif debt_pressure_ratio >= 0.2:
            lines.append("• Долги заметно съедают свободный остаток, это стоит учитывать до новых крупных трат.")

    advice: list[str] = []
    if scenario_savings_20:
        if len(scenario_savings_20) == 1:
            cat, save = scenario_savings_20[0]
            advice.append(f"Снижение категории <b>{cat}</b> на 20% даст примерно <b>{fmt_money(save)}</b> экономии за такой же период.")
        else:
            parts = ", ".join(f"{cat} ≈ {fmt_money(save)}" for cat, save in scenario_savings_20)
            advice.append(f"Главные точки воздействия сейчас: {parts}. Вместе это около <b>{fmt_money(scenario_total_20)}</b> экономии.")
    if budget_snapshot.get("over_count"):
        advice.append("Сначала режь категории с уже пробитым лимитом — это самые быстрые утечки, которые влияют на конец месяца прямо сейчас.")
    if projected_required_free_cash < 0:
        advice.append("После обязательных будущих движений месяц уже выглядит криво: дефицит формируется не из хотелок, а из базы. Тут сначала надо выровнять обязательную часть.")
    elif projected_free_cash < 0:
        advice.append("По обязательной части всё ещё держится, но в минус тебя уводят уже гибкие планы и плавающие траты. Их как раз и стоит трогать первыми.")
    elif projected_free_cash < max(20000, projected_month_expense * 0.1):
        advice.append("Свободный остаток тонкий. Лучше заранее поставить жёсткий лимит на 1–2 плавающие категории и не трогать резерв на счёте.")
    else:
        advice.append(f"При текущем темпе у тебя может остаться около <b>{fmt_money(projected_free_cash)}</b> свободных денег к концу месяца.")
    if debt_snapshot.get("monthly_out") and projected_free_cash > 0 and debt_snapshot["monthly_out"] > projected_free_cash:
        advice.append("Регулярные платежи по долгам выше прогнозного свободного остатка — лучше не брать на себя новые обязательства и синхронизировать график выплат.")
    if eta_current:
        eta_text = f"При текущем свободном остатке цель может занять около <b>{eta_current} мес.</b>"
        if eta_cut and eta_cut < eta_current:
            eta_text += f" Если урезать 2 главные категории, срок может сократиться примерно до <b>{eta_cut} мес.</b>"
        advice.append(eta_text)

    lines.extend(["", "<b>Что делать дальше</b>"])
    lines.extend(f"• {x}" for x in advice[:5])

    return "\n".join(lines)


def render_ai_report_download(context: dict) -> str:
    quality = context.get("data_quality") or {}
    if not quality.get("sufficient_for_deep_report"):
        plain = render_ai_insufficient_report(context).replace("<b>", "").replace("</b>", "")
        return plain
    meta: PeriodMeta = context["meta"]
    current = context["current"]
    previous = context["previous"]
    month = context["month"]
    budget_snapshot = context.get("budget_snapshot") or {}
    debt_snapshot = context.get("debt_snapshot") or {}
    lines = [
        f"AI-консультант {meta.title}",
        "=" * 32,
        f"Цель: {context.get('goal_text') or 'не задана'}",
        f"Валюта: {context.get('currency') or 'KZT'}",
        "",
        f"Доходы: {fmt_money(current['income'])}",
        f"Расходы: {fmt_money(current['expense'])}",
        f"Баланс: {fmt_money(current['net'])}",
        f"Операций: {current['tx_count']}",
        "",
        f"Предыдущий период — доходы: {fmt_money(previous['income'])}",
        f"Предыдущий период — расходы: {fmt_money(previous['expense'])}",
        "",
        "Топ категорий:",
    ]
    for cat, amount in current["top_categories"][:8]:
        lines.append(f"- {cat}: {fmt_money(amount)}")
    lines.extend([
        "",
        f"Текущий месяц MTD расход: {fmt_money(month['expense'])}",
        f"Прогноз доходов к концу месяца: {fmt_money(int(context.get('projected_month_income') or 0))}",
        f"Прогноз расхода к концу месяца: {fmt_money(int(context['projected_month_expense'] or 0))}",
        f"Прогноз свободного остатка: {fmt_money(int(context['projected_free_cash'] or 0))}",
        f"После обязательных будущих движений: {fmt_money(int(context.get('projected_required_free_cash') or 0))}",
        f"Баланс на счетах: {fmt_money(int(context.get('total_balance') or 0))}",
        f"Запас по дням: {context.get('runway_days') if context.get('runway_days') is not None else 'n/a'}",
        "",
        f"Лимиты: over={budget_snapshot.get('over_count', 0)}, warn={budget_snapshot.get('warn_count', 0)}",
        f"Долги: active={debt_snapshot.get('active_count', 0)}, overdue={debt_snapshot.get('overdue_count', 0)}, monthly_out={fmt_money(int(debt_snapshot.get('monthly_out', 0) or 0))}",
        "",
        "Сценарий сокращения 20%:",
    ])
    for cat, save in context["scenario_savings_20"]:
        lines.append(f"- {cat}: экономия ≈ {fmt_money(save)}")
    lines.append("")
    lines.append("Полный текстовый разбор:")
    lines.append(render_ai_report(context).replace("<b>", "").replace("</b>", ""))
    return "\n".join(lines)


def build_ai_scheduler_warning(context: dict) -> str:
    projected_free_cash = int(context.get("projected_free_cash") or 0)
    projected_required_free_cash = int(context.get("projected_required_free_cash") or 0)
    budget_snapshot = context.get("budget_snapshot") or {}
    debt_snapshot = context.get("debt_snapshot") or {}
    recurring_snapshot = context.get("recurring_snapshot") or {}
    recurring_income_snapshot = context.get("recurring_income_snapshot") or {}
    planned_snapshot = context.get("planned_snapshot") or {}
    runway_days = context.get("runway_days")
    month = context.get("month") or {}
    lines: list[str] = []

    if budget_snapshot.get("over_count"):
        lines.append(f"Лимиты уже пробиты: <b>{budget_snapshot['over_count']}</b>")
    elif budget_snapshot.get("warn_count"):
        lines.append(f"Категории на грани лимита: <b>{budget_snapshot['warn_count']}</b>")

    if projected_required_free_cash < 0:
        lines.append(f"После обязательных будущих движений уже минус: <b>{fmt_money(projected_required_free_cash)}</b>")
    elif projected_free_cash < 0:
        lines.append(f"Обязательная часть ещё держится, но полный прогноз уже в минусе: <b>{fmt_money(projected_free_cash)}</b>")
    elif projected_free_cash < max(15000, int((context.get('projected_month_expense') or 0) * 0.1)) and month.get('expense'):
        lines.append(f"Свободный остаток тонкий: около <b>{fmt_money(projected_free_cash)}</b> к концу месяца")

    if runway_days is not None and runway_days <= 14 and int(context.get('total_balance') or 0) > 0:
        lines.append(f"Запаса на счетах примерно на <b>{runway_days} дн.</b> при текущем темпе")

    if recurring_snapshot.get("count"):
        lines.append(f"До конца месяца ещё висит постоянных платежей: <b>{fmt_money(int(recurring_snapshot['total']))}</b>")
    if planned_snapshot.get("count"):
        lines.append(f"Разовых планируемых операций впереди: <b>{planned_snapshot['count']}</b> · эффект <b>{fmt_money(int(planned_snapshot.get('net') or 0))}</b>")
        if planned_snapshot.get("required_count"):
            lines.append(f"Из них обязательных разовых: <b>{planned_snapshot['required_count']}</b> · эффект <b>{fmt_money(int(planned_snapshot.get('required_net') or 0))}</b>")
    if recurring_income_snapshot.get("count"):
        lines.append(f"До конца месяца ещё ожидается постоянных поступлений: <b>{fmt_money(int(recurring_income_snapshot['total']))}</b>")

    if debt_snapshot.get("overdue_count"):
        lines.append(f"Просроченные долги: <b>{debt_snapshot['overdue_count']}</b>")
    elif debt_snapshot.get("due_today_count"):
        lines.append("Сегодня есть платёж по долгу")
    elif debt_snapshot.get("due_soon_count"):
        lines.append(f"Платежи по долгам в ближайшие 7 дней: <b>{debt_snapshot['due_soon_count']}</b>")

    if not lines:
        return ""

    return "⚠️ <b>AI-сигналы</b>\n" + "\n".join(f"• {x}" for x in lines[:4])


_SECTION_HINTS = {
    "ru": {
        "title": "💡 <b>Подсказка</b>",
        "no_recurring_expenses": "Пока нет ни одного постоянного расхода. Прогноз месяца слепее, чем должен быть.",
        "recurring_expenses_due": "До конца месяца ещё <b>{count}</b> постоянных платежей на <b>{total}</b>.",
        "recurring_expenses_clear": "Постоянные платежи до конца месяца уже не висят.",
        "no_recurring_incomes": "Пока нет ни одного постоянного дохода. Прогноз поступлений занижен.",
        "recurring_incomes_due": "До конца месяца ещё ожидается <b>{count}</b> постоянных поступлений на <b>{total}</b>.",
        "recurring_incomes_clear": "До конца месяца новых постоянных поступлений не ожидается.",
        "planned_required": "Обязательных разовых операций впереди: <b>{count}</b> · эффект <b>{net}</b>.",
        "planned_flexible": "Гибких разовых операций впереди: <b>{count}</b>. Проверь, все ли из них реально нужны.",
        "planned_empty": "Планируемые операции пусты. Разовые траты и поступления сейчас не участвуют в прогнозе.",
        "debt_overdue": "Есть просроченные долги: <b>{count}</b>. С них и начинай.",
        "debt_today": "Сегодня есть платёж по долгу. Не пропусти его в отчёте дня.",
        "debt_soon": "В ближайшие 7 дней платежей по долгам: <b>{count}</b>.",
        "debt_empty": "Активных долгов нет. Этот раздел пока чистый.",
        "reports_over": "Лимиты уже пробиты: <b>{count}</b>. Отчёт уже горит красным.",
        "reports_warn": "Категорий на грани лимита: <b>{count}</b>.",
        "reports_minus": "После обязательных будущих движений месяц уже в минусе: <b>{amount}</b>.",
        "reports_thin": "Свободный остаток к концу месяца тонкий: около <b>{amount}</b>.",
        "reports_empty_suggest": "Пока критичных сигналов нет. Но для точного прогноза остатка к концу месяца добавь <b>Планирование</b>.",
        "reports_ok": "Критичных сигналов по месяцу сейчас нет.",
        "main_minus": "После обязательных движений месяц уже уходит в минус: <b>{amount}</b>.",
        "main_overdue": "Просроченные долги: <b>{count}</b>. Не делай вид, что их нет.",
        "main_limits": "Лимиты уже пробиты в <b>{count}</b> категориях.",
        "main_due": "До конца месяца ещё висят обязательные движения на <b>{amount}</b>.",
        "main_empty_suggest": "Все спокойно. Но ты ещё не используешь <b>Планирование</b> — добавь будущие траты или долги, чтобы бот помогал точнее.",
        "main_ok": "Главных тревожных сигналов сейчас нет.",
    },
    "en": {
        "title": "💡 <b>Hint</b>",
        "no_recurring_expenses": "No recurring expenses yet. Your month forecast is blinder than it should be.",
        "recurring_expenses_due": "Still <b>{count}</b> recurring payments due this month for <b>{total}</b>.",
        "recurring_expenses_clear": "No recurring payments left for the rest of this month.",
        "no_recurring_incomes": "No recurring income yet. Expected inflows are understated.",
        "recurring_incomes_due": "Still expecting <b>{count}</b> recurring inflows this month for <b>{total}</b>.",
        "recurring_incomes_clear": "No more recurring inflows expected for the rest of this month.",
        "planned_required": "Required one-time operations ahead: <b>{count}</b> · effect <b>{net}</b>.",
        "planned_flexible": "Flexible one-time operations ahead: <b>{count}</b>. Check if all of them are really needed.",
        "planned_empty": "No planned operations yet. One-time moves are not affecting the forecast.",
        "debt_overdue": "Overdue debts: <b>{count}</b>. Start there.",
        "debt_today": "There is a debt payment due today. Do not miss it in today’s log.",
        "debt_soon": "Debt payments due within 7 days: <b>{count}</b>.",
        "debt_empty": "No active debts. This section is clean for now.",
        "reports_over": "Budget limits are already broken in <b>{count}</b> categories.",
        "reports_warn": "Categories close to the limit: <b>{count}</b>.",
        "reports_minus": "After required future moves, the month is already negative: <b>{amount}</b>.",
        "reports_thin": "Free cash by month end looks thin: around <b>{amount}</b>.",
        "reports_empty_suggest": "No critical signals yet. But for an accurate month-end forecast, add <b>Planning</b> data.",
        "reports_ok": "No critical month signals right now.",
        "main_minus": "After required moves, the month is already negative: <b>{amount}</b>.",
        "main_overdue": "Overdue debts: <b>{count}</b>. Stop pretending they are not there.",
        "main_limits": "Budget limits are already broken in <b>{count}</b> categories.",
        "main_due": "Required moves still hanging until month end: <b>{amount}</b>.",
        "main_empty_suggest": "Everything is fine. But you haven't used <b>Planning</b> yet — add future expenses or debts to get better insights.",
        "main_ok": "No major warning signs right now.",
    },
    "kk": {
        "title": "💡 <b>Нұсқау</b>",
        "no_recurring_expenses": "Әзірге бірде-бір тұрақты шығыс жоқ. Айлық болжам толық емес.",
        "recurring_expenses_due": "Ай соңына дейін тағы <b>{count}</b> тұрақты төлем бар: <b>{total}</b>.",
        "recurring_expenses_clear": "Осы айдың соңына дейін тұрақты төлемдер қалмады.",
        "no_recurring_incomes": "Әзірге тұрақты кіріс жоқ. Күтілетін түсімдер толық есептелмейді.",
        "recurring_incomes_due": "Ай соңына дейін тағы <b>{count}</b> тұрақты түсім күтіледі: <b>{total}</b>.",
        "recurring_incomes_clear": "Осы айдың соңына дейін жаңа тұрақты түсім күтілмейді.",
        "planned_required": "Алда міндетті бір реттік операциялар: <b>{count}</b> · әсері <b>{net}</b>.",
        "planned_flexible": "Алда икемді бір реттік операциялар: <b>{count}</b>. Барлығы шынымен керек пе — тексеріңіз.",
        "planned_empty": "Жоспарланған операциялар бос. Бір реттік қозғалыстар болжамға кірмей тұр.",
        "debt_overdue": "Мерзімі өткен қарыздар бар: <b>{count}</b>.",
        "debt_today": "Бүгін қарыз бойынша төлем бар.",
        "debt_soon": "Келесі 7 күнде қарыз төлемдері: <b>{count}</b>.",
        "debt_empty": "Белсенді қарыздар жоқ. Бұл бөлім әзірге таза.",
        "reports_over": "Лимиттер бұзылған санаттар: <b>{count}</b>.",
        "reports_warn": "Лимитке жақын санаттар: <b>{count}</b>.",
        "reports_minus": "Міндетті болашақ қозғалыстардан кейін ай қазірдің өзінде минуста: <b>{amount}</b>.",
        "reports_thin": "Ай соңындағы бос қалдық жұқа: шамамен <b>{amount}</b>.",
        "reports_empty_suggest": "Әзірге сыни сигналдар жоқ. Бірақ ай соңындағы болжам дәл болуы үшін <b>Жоспарлауды</b> қосыңыз.",
        "reports_ok": "Қазір ай бойынша сыни сигналдар жоқ.",
        "main_minus": "Міндетті қозғалыстардан кейін ай минусқа кетіп тұр: <b>{amount}</b>.",
        "main_overdue": "Мерзімі өткен қарыздар: <b>{count}</b>.",
        "main_limits": "Лимиттер <b>{count}</b> санатта бұзылған.",
        "main_due": "Ай соңына дейін міндетті қозғалыстар әлі бар: <b>{amount}</b>.",
        "main_empty_suggest": "Барлығы дұрыс. Бірақ сен әлі <b>Жоспарлауды</b> қолданбадың — болашақ шығындарды немесе қарыздарды қосыңыз.",
        "main_ok": "Қазір негізгі қауіп сигналдары жоқ.",
    },
}


def _hint_text(lang: str, key: str, **kwargs) -> str:
    pack = _SECTION_HINTS.get(lang) or _SECTION_HINTS["ru"]
    template = pack.get(key) or _SECTION_HINTS["ru"].get(key, "")
    return template.format(**kwargs)


def _wrap_hint(lang: str, body: str | None) -> str:
    if not body:
        return ""
    title = (_SECTION_HINTS.get(lang) or _SECTION_HINTS["ru"])["title"]
    return f"{title}\n{body}"


async def _build_today_feed(db: aiosqlite.Connection, user_id: int, tz_name: str, lang: str) -> str:
    tz = _safe_tz(tz_name)
    now_utc = datetime.now(timezone.utc)
    meta = build_period_meta("day", tz_name, now_utc)
    rows = await _fetch_rows(db, user_id, meta.start, meta.end)
    if not rows: return ""

    filtered_items = []
    today_income = 0
    today_expense = 0
    currency = await _fetch_currency(db, user_id)

    for row in rows:
        amount = int(row[3])
        t_type = row[2]

        # Calculate totals for all today's transactions
        if t_type == "income":
            today_income += amount
        elif t_type == "expense":
            today_expense += abs(amount)

        # Skip the incoming transfer side to avoid duplication in feed
        if t_type == "transfer" and amount > 0:
            continue

        try:
            dt = datetime.fromisoformat(row[1]).astimezone(tz)
        except Exception:
            dt = datetime.now(tz)
        time_str = dt.strftime("%H:%M")

        if t_type == "transfer":
            cat_emoji = "🔁"
            label = {"ru": "Перевод", "en": "Transfer", "kk": "Аударым"}.get(lang, "Перевод")
            display_amount = abs(amount)
        else:
            cat_emoji = row[5] or "🔹"
            label = (row[6] if row[6] else row[4])[:18]
            display_amount = amount

        # Format display amount with sign
        if t_type == "income":
            amount_str = f"+{fmt_money(display_amount, currency)}"
        elif t_type == "expense":
            amount_str = f"-{fmt_money(abs(display_amount), currency)}"
        else:
            # Transfer: neutral representation
            amount_str = fmt_money(display_amount, currency)

        filtered_items.append(
            f"<code>{time_str}</code> · {cat_emoji} {label} · <b>{amount_str}</b>"
        )

    if not filtered_items:
        return ""

    title = {"ru": "🕒 <b>Сегодня:</b>", "en": "🕒 <b>Today:</b>", "kk": "🕒 <b>Бүгін:</b>"}.get(lang, "🕒 <b>Сегодня:</b>")
    feed_body = "\n".join(filtered_items[-5:])

    totals_line = ""
    if today_income > 0 or today_expense > 0:
        parts = []
        if today_income > 0:
            parts.append(f"🟢 +{fmt_money(today_income, currency)}")
        if today_expense > 0:
            parts.append(f"🔴 -{fmt_money(today_expense, currency)}")
        
        lbl = {
            "ru": "Итого за день",
            "en": "Today's total",
            "kk": "Бүгінгі жиынтық"
        }.get(lang, "Итого за день")
        
        totals_line = f"\n───\n<b>{lbl}:</b> " + " · ".join(parts)

    return f"\n{title}\n{feed_body}{totals_line}"


async def build_main_menu_text(db: aiosqlite.Connection, user_id: int, lang: str = "ru") -> str:
    try:
        tz_name = await get_timezone(db, user_id)
        goal_text = await get_financial_goal(db, user_id)
        context = await build_ai_context(db, user_id, tz_name, "month", goal_text)
        total_balance_str = context.get("fmt_total_balance") or fmt_money(int(context.get("total_balance") or 0))
        is_negative = int(context.get("total_balance") or 0) < 0
        indicator = "🔴" if is_negative else "🟢"
        text = f"🏠 <b>{t(lang, 'MENU_LABEL')}</b>\n"
        text += f"{indicator} {t(lang, 'MENU_TOTAL')}: <b>{total_balance_str}</b>"
        feed = await _build_today_feed(db, user_id, tz_name, lang)
        if feed: text += feed
        hint = await build_section_hint(db, user_id, "main_menu", lang)
        critical = ("просрочен", "минус", "пробит", "overdue", "broken", "negative", "архив", "старт")
        if hint and any(k in hint.lower() for k in critical):
            text += f"\n───\n{hint}"
        else:
            from app.db.repositories.users_repo import get_access_profile
            profile = await get_access_profile(db, user_id)
            if profile:
                current_streak = int(profile[1] or 0)
                max_streak = int(profile[2] or 0)
                mode = str(profile[4] or "newbie").lower()
                progress_level = int(profile[5] or 0)
                
                streak_val = max(current_streak, max_streak)
                progression_hint = None
                
                if progress_level < 2:
                    if lang == "en":
                        progression_hint = f"💡 **Path to Mastery:** Log transactions for <b>{streak_val}/3</b> days in a row to unlock <b>\"Reports & Budgets\"</b>! 🚀"
                    elif lang == "kk":
                        progression_hint = f"💡 **Жетістікке жол:** <b>«Есептер мен бюджеттер»</b> бөлімін ашу үшін қатарынан <b>{streak_val}/3</b> күн бюджетті жүргізіңіз! 🚀"
                    else:
                        progression_hint = f"💡 **Путь к мастерству:** Веди бюджет <b>{streak_val}/3</b> дн. подряд, чтобы открыть <b>«Отчёты и Бюджеты»</b>! 🚀"
                elif mode == "newbie":
                    if lang == "en":
                        progression_hint = f"⭐ **Goal Unlocked!** You can now see Reports. Get <b>Full Access</b> in settings ⚙️ to unlock Debts, Smart Planning & AI Financial Coach! 💎"
                    elif lang == "kk":
                        progression_hint = f"⭐ **Мақсат орындалды!** Есептер бөлімі ашылды. Қарыздарды, Жоспарлауды және AI кеңесшісін ашу үшін баптауларда ⚙️ <b>Толық қолжетімділік</b> алыңыз! 💎"
                    else:
                        progression_hint = f"⭐ **Цель достигнута!** Отчёты открыты. Оформи <b>Полный доступ</b> в настройках ⚙️, чтобы открыть Долги, Умное планирование и AI-Консультанта! 💎"
                else:
                    # Full access user with no active moves
                    recurring_snapshot = context.get("recurring_snapshot") or {}
                    planned_snapshot = context.get("planned_snapshot") or {}
                    debt_snapshot = context.get("debt_snapshot") or {}
                    if not (recurring_snapshot.get("count") or planned_snapshot.get("count") or debt_snapshot.get("active_count")):
                        if lang == "en":
                            progression_hint = f"💡 **Pro Tip:** You have Full Access active! Tap <b>Accounts & Transfers</b> 🔄 to set up your subscription, rent, or salary to unlock automatic month forecast! 📈"
                        elif lang == "kk":
                            progression_hint = f"💡 **Кеңес:** Толық қолжетімділік белсенді! Автоматты айлық болжамды ашу үшін <b>Шоттар мен аударымдар</b> 🔄 бөлімінде жазылымдарды, жалдау ақысын немесе жалақыны баптаңыз! 📈"
                        else:
                            progression_hint = f"💡 **Лайфхак:** У тебя активен Полный доступ! Зайди в <b>Счета и переводы</b> 🔄 и добавь аренду, подписки или зарплату, чтобы включить автоматический прогноз баланса на месяц! 📈"
                
                if progression_hint:
                    title = {"ru": "💡 <b>Подсказка</b>", "en": "💡 <b>Hint</b>", "kk": "💡 <b>Нұсқау</b>"}.get(lang, "💡 <b>Подсказка</b>")
                    text += f"\n───\n{title}\n{progression_hint}"
        return text
    except Exception: return t(lang, "MENU_LABEL")


async def build_section_hint(db: aiosqlite.Connection, user_id: int, section: str, lang: str = "ru") -> str:
    tz_name = await get_timezone(db, user_id)
    goal_text = await get_financial_goal(db, user_id)
    context = await build_ai_context(db, user_id, tz_name, "month", goal_text)

    recurring_snapshot = context.get("recurring_snapshot") or {}
    recurring_income_snapshot = context.get("recurring_income_snapshot") or {}
    planned_snapshot = context.get("planned_snapshot") or {}
    debt_snapshot = context.get("debt_snapshot") or {}
    budget_snapshot = context.get("budget_snapshot") or {}
    projected_required_free_cash = int(context.get("projected_required_free_cash") or 0)
    projected_free_cash = int(context.get("projected_free_cash") or 0)

    currency = await _fetch_currency(db, user_id)
    body = ""
    if section == "recurring_expenses":
        if not recurring_snapshot.get("count"):
            body = _hint_text(lang, "no_recurring_expenses")
        elif recurring_snapshot.get("total"):
            body = _hint_text(lang, "recurring_expenses_due", count=int(recurring_snapshot.get("count") or 0), total=fmt_money(int(recurring_snapshot.get("total") or 0), currency))
        else:
            body = _hint_text(lang, "recurring_expenses_clear")
    elif section == "recurring_incomes":
        if not recurring_income_snapshot.get("count"):
            body = _hint_text(lang, "no_recurring_incomes")
        elif recurring_income_snapshot.get("total"):
            body = _hint_text(lang, "recurring_incomes_due", count=int(recurring_income_snapshot.get("count") or 0), total=fmt_money(int(recurring_income_snapshot.get("total") or 0), currency))
        else:
            body = _hint_text(lang, "recurring_incomes_clear")
    elif section == "planned":
        if int(planned_snapshot.get("required_count") or 0) > 0:
            body = _hint_text(lang, "planned_required", count=int(planned_snapshot.get("required_count") or 0), net=fmt_money(int(planned_snapshot.get("required_net") or 0), currency))
        elif int(planned_snapshot.get("count") or 0) > 0:
            body = _hint_text(lang, "planned_flexible", count=int(planned_snapshot.get("count") or 0))
        else:
            body = _hint_text(lang, "planned_empty")
    elif section == "debts":
        if int(debt_snapshot.get("overdue_count") or 0) > 0:
            body = _hint_text(lang, "debt_overdue", count=int(debt_snapshot.get("overdue_count") or 0))
        elif int(debt_snapshot.get("due_today_count") or 0) > 0:
            body = _hint_text(lang, "debt_today")
        elif int(debt_snapshot.get("due_soon_count") or 0) > 0:
            body = _hint_text(lang, "debt_soon", count=int(debt_snapshot.get("due_soon_count") or 0))
        else:
            body = _hint_text(lang, "debt_empty")
    elif section == "reports":
        if int(budget_snapshot.get("over_count") or 0) > 0:
            body = _hint_text(lang, "reports_over", count=int(budget_snapshot.get("over_count") or 0))
        elif projected_required_free_cash < 0:
            body = _hint_text(lang, "reports_minus", amount=fmt_money(projected_required_free_cash, currency))
        elif int(budget_snapshot.get("warn_count") or 0) > 0:
            body = _hint_text(lang, "reports_warn", count=int(budget_snapshot.get("warn_count") or 0))
        elif projected_free_cash < max(15000, int((context.get("projected_month_expense") or 0) * 0.1)) and int((context.get("month") or {}).get("expense") or 0) > 0:
            body = _hint_text(lang, "reports_thin", amount=fmt_money(projected_free_cash, currency))
        elif not (recurring_snapshot.get("count") or planned_snapshot.get("count") or debt_snapshot.get("active_count")):
            body = _hint_text(lang, "reports_empty_suggest")
        else:
            body = _hint_text(lang, "reports_ok")
    elif section == "main_menu":
        due_total = int(recurring_snapshot.get("total") or 0) + max(0, int(planned_snapshot.get("required_expense_total") or 0) - int(planned_snapshot.get("required_income_total") or 0))
        if projected_required_free_cash < 0:
            body = _hint_text(lang, "main_minus", amount=fmt_money(projected_required_free_cash, currency))
        elif int(debt_snapshot.get("overdue_count") or 0) > 0:
            body = _hint_text(lang, "main_overdue", count=int(debt_snapshot.get("overdue_count") or 0))
        elif int(budget_snapshot.get("over_count") or 0) > 0:
            body = _hint_text(lang, "main_limits", count=int(budget_snapshot.get("over_count") or 0))
        elif due_total > 0:
            body = _hint_text(lang, "main_due", amount=fmt_money(due_total, currency))
        elif not (recurring_snapshot.get("count") or planned_snapshot.get("count") or debt_snapshot.get("active_count")):
            body = _hint_text(lang, "main_empty_suggest")
        else:
            body = _hint_text(lang, "main_ok")

    return _wrap_hint(lang, body)


async def discover_recurring_candidates_ai(db: aiosqlite.Connection, user_id: int, days: int = 90) -> list[dict]:
    """Uses AI to find recurring items in history."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    # 1. Fetch History
    cur = await db.execute(
        """
        SELECT t.type, t.amount, COALESCE(t.note, '') as note, c.name as category_name, t.ts
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.user_id = ? AND t.ts >= ? AND t.deleted_at IS NULL
        ORDER BY t.ts DESC LIMIT 150
        """,
        (user_id, start_date.isoformat())
    )
    rows = await cur.fetchall()
    history_json = [
        {"type": r[0], "amount": int(r[1]), "note": r[2], "category": r[3], "date": r[4]}
        for r in rows
    ]

    # 2. Fetch Existing Plans
    existing_expenses = await list_recurring_expenses(db, user_id)
    existing_incomes = await list_recurring_incomes(db, user_id)
    existing_plans_json = [
        {"title": r[2], "amount": int(r[3]), "kind": "expense"} for r in existing_expenses
    ] + [
        {"title": r[2], "amount": int(r[3]), "kind": "income"} for r in existing_incomes
    ]

    # 3. Call AI
    context_str = json.dumps({
        "history": history_json,
        "existing_plans": existing_plans_json
    }, ensure_ascii=False)
    
    try:
        raw_res = await asyncio.to_thread(_generate, SYSTEM_PROMPT_RECURRING_DISCOVERY, context_str)
        # Cleanup code blocks
        raw_res = re.sub(r"```json\s?|\s?```", "", raw_res).strip()
        candidates = json.loads(raw_res)
    except Exception:
        return []

    if not isinstance(candidates, list):
        return []

    # 4. Map back to DB IDs (Categories/Accounts)
    from app.db.repositories.accounts_repo import get_default_account
    from app.db.repositories.categories_repo import find_category_by_name_ci
    
    default_acc = await get_default_account(db, user_id)
    acc_id = default_acc[0] if default_acc else None

    final = []
    for c in candidates:
        kind = c.get("kind", "expense")
        hint = c.get("category_hint")
        
        cat_id = None
        if hint:
            cat_hit = await find_category_by_name_ci(db, user_id, kind, hint)
            if cat_hit:
                cat_id = cat_hit[0]
        
        # Unique ID
        import hashlib
        cid = hashlib.md5(f"{c['title']}{c['amount']}{kind}".encode()).hexdigest()[:12]

        final.append({
            "cid": cid,
            "title": c["title"],
            "type": kind,
            "amount": int(c["amount"]),
            "category_id": cat_id,
            "account_id": acc_id,
            "day_of_month": int(c.get("day") or 15),
            "reason": c.get("reason", "AI detection"),
            "is_unsure": False
        })

    return final


async def discover_recurring_candidates(db: aiosqlite.Connection, user_id: int, days: int = 90) -> list[dict]:
    """Finds potential recurring transactions in history using a strict mathematical algorithm:
    Must be present 3 months in a row, strictly once a month, same amount, same name, same day of month (+/- 5 days tolerance),
    and must not overlap with existing recurring templates or active debts.
    """
    from datetime import datetime, timedelta, timezone
    
    # 1. Fetch existing recurring templates & debts
    existing_expenses = await list_recurring_expenses(db, user_id)
    existing_incomes = await list_recurring_incomes(db, user_id)
    existing_debts = await list_active_debts(db, user_id)

    existing_exp_titles = {str(r[1]).strip().lower() for r in existing_expenses if r[1]}
    existing_inc_titles = {str(r[1]).strip().lower() for r in existing_incomes if r[1]}
    existing_debt_titles = {str(r[1]).strip().lower() for r in existing_debts if r[1]}

    # Fetch transactions from the last 100 days
    start_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    cur = await db.execute(
        """
        SELECT t.type, t.amount, COALESCE(t.note, '') as note, c.name as category_name, t.category_id, t.account_id, t.ts
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.user_id = ? AND t.ts >= ? AND t.deleted_at IS NULL AND t.type IN ('expense', 'income')
        ORDER BY t.ts ASC
        """,
        (user_id, start_date)
    )
    rows = await cur.fetchall()

    # Group by (type, amount, note_cleaned)
    groups = {}
    for r in rows:
        ttype = r[0]
        amount = abs(int(r[1]))
        note = r[2].strip()
        if not note:
            continue
        note_lower = note.lower()

        # Duplicate checking
        is_dup = False
        if ttype == "expense":
            if note_lower in existing_exp_titles:
                is_dup = True
            for t in existing_exp_titles:
                if t in note_lower or note_lower in t:
                    is_dup = True
        elif ttype == "income":
            if note_lower in existing_inc_titles:
                is_dup = True
            for t in existing_inc_titles:
                if t in note_lower or note_lower in t:
                    is_dup = True
        
        for dt in existing_debt_titles:
            if dt in note_lower or note_lower in dt:
                is_dup = True
                
        if is_dup:
            continue

        key = (ttype, amount, note_lower)
        if key not in groups:
            groups[key] = {
                "title": note,
                "category_id": r[4],
                "account_id": r[5],
                "dates": [],
                "rows": []
            }
        
        try:
            dt = datetime.fromisoformat(r[6].replace("Z", "+00:00"))
            groups[key]["dates"].append(dt)
            groups[key]["rows"].append(r)
        except Exception:
            continue

    final_candidates = []
    for (ttype, amount, note_lower), g in groups.items():
        dates = g["dates"]
        if len(dates) < 3:
            continue
        
        # Group dates by calendar month: (year, month) -> list of days
        months = {}
        for dt in dates:
            m_key = (dt.year, dt.month)
            if m_key not in months:
                months[m_key] = []
            months[m_key].append(dt.day)
        
        # Sort keys
        m_keys = sorted(months.keys())
        if len(m_keys) < 3:
            continue
        
        found_consecutive = False
        consecutive_keys = []
        for i in range(len(m_keys) - 2):
            k1, k2, k3 = m_keys[i], m_keys[i+1], m_keys[i+2]
            
            y1, mo1 = k1
            y2, mo2 = k2
            y3, mo3 = k3
            
            # Verify they are consecutive calendar months
            diff1 = (y2 - y1) * 12 + (mo2 - mo1)
            diff2 = (y3 - y2) * 12 + (mo3 - mo2)
            
            if diff1 == 1 and diff2 == 1:
                # Strictly once a month check
                if len(months[k1]) == 1 and len(months[k2]) == 1 and len(months[k3]) == 1:
                    d1 = months[k1][0]
                    d2 = months[k2][0]
                    d3 = months[k3][0]
                    
                    # Preferably in the same day (tolerance <= 5 days)
                    if max(d1, d2, d3) - min(d1, d2, d3) <= 5:
                        found_consecutive = True
                        consecutive_keys = [k1, k2, k3]
                        break
        
        if not found_consecutive:
            continue
            
        d1 = months[consecutive_keys[0]][0]
        d2 = months[consecutive_keys[1]][0]
        d3 = months[consecutive_keys[2]][0]
        day_of_month = int(round((d1 + d2 + d3) / 3))
        
        # Day of month should be between 1 and 28
        day_of_month = max(1, min(day_of_month, 28))
        
        import hashlib
        cid = hashlib.md5(f"{g['title']}{amount}{ttype}".encode()).hexdigest()[:12]
        
        last_row = g["rows"][-1]
        
        final_candidates.append({
            "cid": cid,
            "title": g["title"],
            "type": ttype,
            "amount": amount,
            "category_id": last_row[4],
            "account_id": last_row[5],
            "day_of_month": day_of_month,
            "reason": "3 months in a row"
        })
            
    # Sort alphabetically by title
    final_candidates.sort(key=lambda x: x["title"])
    return final_candidates[:10]
