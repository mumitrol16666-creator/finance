from __future__ import annotations

import aiosqlite
import random
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def _safe_tz(tz_name: str):
    try:
        return ZoneInfo(tz_name or "UTC"), (tz_name or "UTC")
    except Exception:
        return timezone.utc, "UTC"


def day_bounds_utc(tz_name: str, now_utc: datetime | None = None) -> tuple[datetime, datetime, str, str]:
    now_utc = now_utc or utcnow()
    tz, tz_norm = _safe_tz(tz_name)
    local_now = now_utc.astimezone(tz)
    d = local_now.date()

    local_start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc), d.isoformat(), tz_norm


def week_bounds_utc(tz_name: str, now_utc: datetime | None = None) -> tuple[datetime, datetime, str, str]:
    now_utc = now_utc or utcnow()
    tz, tz_norm = _safe_tz(tz_name)
    local_now = now_utc.astimezone(tz)
    d = local_now.date()

    monday = d - timedelta(days=d.weekday())
    local_start = datetime(monday.year, monday.month, monday.day, 0, 0, 0, tzinfo=tz)
    local_end = local_start + timedelta(days=7)
    label = f"{monday.isoformat()}..{(monday + timedelta(days=6)).isoformat()}"
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc), label, tz_norm


def month_bounds_utc(tz_name: str, now_utc: datetime | None = None) -> tuple[datetime, datetime, str, str]:
    now_utc = now_utc or utcnow()
    tz, tz_norm = _safe_tz(tz_name)
    local_now = now_utc.astimezone(tz)

    y, m = local_now.year, local_now.month
    local_start = datetime(y, m, 1, 0, 0, 0, tzinfo=tz)

    if m == 12:
        ny, nm = y + 1, 1
    else:
        ny, nm = y, m + 1
    local_end = datetime(ny, nm, 1, 0, 0, 0, tzinfo=tz)

    label = f"{y:04d}-{m:02d}"
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc), label, tz_norm


async def report_period(db: aiosqlite.Connection, user_id: int, start: datetime, end: datetime):
    cur = await db.execute(
        "SELECT "
        "SUM(CASE WHEN type='income' THEN amount ELSE 0 END) as income, "
        "SUM(CASE WHEN type='expense' THEN -amount ELSE 0 END) as expense, "
        "SUM(CASE WHEN type='income' THEN 1 ELSE 0 END) as cnt_income, "
        "SUM(CASE WHEN type='expense' THEN 1 ELSE 0 END) as cnt_expense, "
        "SUM(CASE WHEN type='transfer' AND amount < 0 THEN 1 ELSE 0 END) as cnt_transfer "
        "FROM transactions WHERE user_id=? AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, iso(start), iso(end)),
    )
    row = await cur.fetchone()
    income = int(row[0] or 0)
    expense = int(row[1] or 0)
    cnt_income = int(row[2] or 0)
    cnt_expense = int(row[3] or 0)
    cnt_transfer = int(row[4] or 0)
    
    cnt = cnt_income + cnt_expense + cnt_transfer
    return income, expense, cnt


async def report_by_category(
    db: aiosqlite.Connection,
    user_id: int,
    start: datetime,
    end: datetime,
    kind: str = "expense",
    limit: int = 10,
):
    if kind == "expense":
        sign_expr = "-t.amount"
        where_type = "expense"
    else:
        sign_expr = "t.amount"
        where_type = "income"

    cur = await db.execute(
        f"SELECT c.name, c.emoji, SUM({sign_expr}) as total "
        "FROM transactions t LEFT JOIN categories c ON c.id=t.category_id "
        "WHERE t.user_id=? AND t.type=? AND t.ts>=? AND t.ts<? AND t.deleted_at IS NULL "
        "GROUP BY c.name, c.emoji ORDER BY total DESC LIMIT ?",
        (user_id, where_type, iso(start), iso(end), limit),
    )
    return await cur.fetchall()

async def build_smart_suggestion(db: aiosqlite.Connection, user_id: int, lang: str = "ru") -> str:
    """Analyze user data and return one smart suggestion for the dashboard/notifications."""
    # Check if they have recurring incomes
    cur = await db.execute("SELECT COUNT(*) FROM recurring_incomes WHERE user_id=? AND is_archived=0", (user_id,))
    row = await cur.fetchone()
    has_recurring_incomes = int(row[0] or 0) > 0

    # Check if they have any planned ops
    cur = await db.execute("SELECT COUNT(*) FROM planned_transactions WHERE user_id=? AND is_archived=0", (user_id,))
    row = await cur.fetchone()
    has_planned = int(row[0] or 0) > 0

    # Check if they have debts
    cur = await db.execute("SELECT COUNT(*) FROM debts WHERE user_id=? AND is_active=1", (user_id,))
    row = await cur.fetchone()
    has_debts = int(row[0] or 0) > 0

    suggestions_ru = []
    suggestions_en = []
    suggestions_kk = []

    if not has_recurring_incomes:
        suggestions_ru.append("💡 <b>Совет:</b> Занесите зарплату в «Планирование → Постоянные доходы», чтобы бот мог прогнозировать ваш баланс.")
        suggestions_en.append("💡 <b>Tip:</b> Add your salary to 'Planning → Recurring Incomes' so the bot can forecast your balance.")
        suggestions_kk.append("💡 <b>Кеңес:</b> Жалақыңызды «Жоспарлау → Тұрақты кірістерге» енгізіңіз, сонда бот қалдығыңызды болжай алады.")

    if not has_planned:
        suggestions_ru.append("💡 <b>Совет:</b> Используйте «Планирование», чтобы заранее заложить бюджет на крупные разовые покупки.")
        suggestions_en.append("💡 <b>Tip:</b> Use 'Planning' to budget for large one-time purchases in advance.")
        suggestions_kk.append("💡 <b>Кеңес:</b> Ірі бір реттік сатып алуларды алдын ала жоспарлау үшін «Жоспарлау» бөлімін пайдаланыңыз.")

    if not has_debts:
        suggestions_ru.append("💡 <b>Совет:</b> Если вы даете деньги в долг или платите кредиты, занесите их в «Долги». Бот сам напомнит о дате платежа.")
        suggestions_en.append("💡 <b>Tip:</b> If you lend money or pay loans, add them to 'Debts'. The bot will remind you of the due date.")
        suggestions_kk.append("💡 <b>Кеңес:</b> Егер сіз қарызға ақша берсеңіз немесе несие төлесеңіз, оларды «Қарыздарға» енгізіңіз. Бот төлем күнін еске салады.")

    # Generic suggestions if all features are used
    generic_ru = [
        "💡 <b>Совет:</b> Регулярно просматривайте AI-отчет — он может заметить неочевидные финансовые привычки.",
        "💡 <b>Совет:</b> Старайтесь сразу вносить мелкие траты, они часто составляют большую часть незаметных расходов."
    ]
    generic_en = [
        "💡 <b>Tip:</b> Regularly review the AI report — it can spot non-obvious financial habits.",
        "💡 <b>Tip:</b> Try to log small expenses immediately, they often make up a large part of unseen spending."
    ]
    generic_kk = [
        "💡 <b>Кеңес:</b> AI есебін үнемі қарап тұрыңыз — ол байқалмайтын қаржылық әдеттерді таба алады.",
        "💡 <b>Кеңес:</b> Ұсақ шығындарды бірден енгізуге тырысыңыз, көбінесе олар елеусіз шығындардың үлкен бөлігін құрайды."
    ]

    suggs = suggestions_ru
    if lang == "en": suggs = suggestions_en
    elif lang == "kk": suggs = suggestions_kk

    if not suggs:
        gen = generic_ru
        if lang == "en": gen = generic_en
        elif lang == "kk": gen = generic_kk
        return random.choice(gen)

    return suggs[0] # Return the highest priority missing feature

