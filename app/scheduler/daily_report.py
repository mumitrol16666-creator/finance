from __future__ import annotations
import random

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import aiosqlite
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db.repositories.settings_repo import (
    list_daily_targets,
    mark_daily_sent,
    mark_daily_pre_sent,
)

from app.db.repositories.users_repo import get_streak
from app.domain.services.reports_service import report_period, report_by_category

REPORT_ZERO = [
    "📊 Итог дня: пусто. Вообще нихуя.",
    "📊 День закрыт. Записей нет. Логично.",
    "📊 0 операций за день. Стабильно.",
    "📊 Ноль. Финансовый контроль на уровне интуиции.",
    "📊 Пустой день. Как будто ничего и не происходило.",
    "📊 Итог: 0. Просто зафиксируем этот позор.",
    "📊 Ни одной записи. Отличная работа.",
    "📊 День прошёл — данных нет.",
    "📊 Ноль операций. Запомни это ощущение.",
    "📊 Итог дня: ты просто не вёл учёт."
]

REPORT_OK = [
    "📊 Итог дня. Ну хотя бы не пусто.",
    "📊 День закрыт. Уже лучше.",
    "📊 Есть данные за день. Не идеально, но ок.",
    "📊 Итог: что-то да записал.",
    "📊 День прошёл не зря. Есть цифры.",
    "📊 Отчёт готов. Уже рабоче.",
    "📊 Есть записи. Уже контроль.",
    "📊 Итог дня. Не слил полностью.",
    "📊 Данные есть. Уже можно анализировать.",
    "📊 День закрыт. Хоть что-то держишь."
]

PRE_ZERO = [
    "⏰ Через час отчёт. Сейчас 0 записей. Красиво проебал день.",
    "⏰ Через час отчёт. Ноль операций. Потом не ной.",
    "⏰ Через час отчёт. Всё ещё пусто. Отличная работа.",
    "⏰ Через час отчёт. 0 записей. День в никуда.",
    "⏰ Через час отчёт. Ноль. Вспоминать потом будешь долго.",
    "⏰ Через час отчёт. Всё ещё нихуя. Стабильность.",
    "⏰ Через час отчёт. 0. Даже не начинал.",
    "⏰ Через час отчёт. Пусто. Потом сам себя бесить будешь.",
    "⏰ Через час отчёт. Ноль записей. Логика отсутствует.",
    "⏰ Через час отчёт. Сегодня просто проигнорирован."
]

PRE_OK = [
    "⏰ Через час отчёт. Уже {cnt} записей. Ладно, не всё через жопу.",
    "⏰ Через час отчёт. {cnt}. Уже лучше, чем обычно.",
    "⏰ Через час отчёт. {cnt} записей. Хоть что-то держишь.",
    "⏰ Через час отчёт. Уже {cnt}. Не слил день полностью.",
    "⏰ Через час отчёт. {cnt}. Норм, продолжай.",
    "⏰ Через час отчёт. Уже {cnt}. Держишься.",
    "⏰ Через час отчёт. {cnt}. Уже не стыдно показать.",
    "⏰ Через час отчёт. {cnt} записей. Ок.",
    "⏰ Через час отчёт. Уже {cnt}. Рабоче.",
    "⏰ Через час отчёт. {cnt}. Не идеал, но живо."
]

def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _safe_tz(tz_name: str):
    try:
        return ZoneInfo(tz_name or "UTC"), (tz_name or "UTC")
    except Exception:
        return timezone.utc, "UTC"


def _parse_hhmm(hhmm: str) -> tuple[int, int]:
    hhmm = (hhmm or "21:00").strip()
    try:
        hh = int(hhmm[:2])
        mm = int(hhmm[3:5])
    except Exception:
        return 21, 0
    if hh < 0 or hh > 23 or mm < 0 or mm > 59:
        return 21, 0
    return hh, mm


def _fmt_money(n: int) -> str:
    s = str(abs(int(n)))
    parts = []
    while s:
        parts.append(s[-3:])
        s = s[:-3]
    return " ".join(reversed(parts))


def _day_bounds_utc(now_utc: datetime, tz_name: str) -> tuple[datetime, datetime, str, str]:
    tz, tz_norm = _safe_tz(tz_name)
    local_now = now_utc.astimezone(tz)
    d = local_now.date()
    local_start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(timezone.utc),
        local_end.astimezone(timezone.utc),
        d.isoformat(),
        tz_norm,
    )


def _in_window(now_local: datetime, target_local: datetime, window: timedelta) -> bool:
    # true если now_local в диапазоне [target_local, target_local + window)
    return target_local <= now_local < (target_local + window)


async def _send_safe(bot, user_id: int, text: str):
    try:
        await bot.send_message(user_id, text)
    except Exception as e:
        logger.warning(f"send failed uid={user_id}: {e}")



async def _build_daily_text(
    db: aiosqlite.Connection,
    user_id: int,
    currency: str,
    tz_name: str,
    now_utc: datetime
) -> str:
    start_utc, end_utc, local_date, tz_norm = _day_bounds_utc(now_utc, tz_name)

    income, expense, cnt = await report_period(db, user_id, start_utc, end_utc)
    cats = await report_by_category(db, user_id, start_utc, end_utc, "expense", 5)

    # топ категорий
    top_lines = []
    shown = 0
    for n, e, t in cats:
        if not n:
            continue
        v = int(t or 0)
        shown += v
        em = (e + " ") if e else ""
        top_lines.append(f"• {em}{n}: -{_fmt_money(v)} {currency}")
    other = int(expense - shown)
    if other > 0:
        top_lines.append(f"• Другое: -{_fmt_money(other)} {currency}")

    # серия
    cur_streak, best_streak, _ = await get_streak(db, user_id)
    if cnt == 0:
        streak_line = (
            f"⚪ Серия: {cur_streak} дн. (лучшее: {best_streak})\n"
            f"Сегодня 0 записей — добавь хотя бы одну, чтобы серия не оборвалась."
        )
    else:
        badge = "👑" if cur_streak >= 30 else ("🚀" if cur_streak >= 8 else "🔥")
        streak_line = (
            f"{badge} Серия: {cur_streak} дн. (лучшее: {best_streak})\n"
            f"Записи есть — серия сохранена."
        )

    net = int(income - expense)
    sign = "+" if net >= 0 else "-"
    if cnt == 0:
        header = random.choice(REPORT_ZERO)
    else:
        header = random.choice(REPORT_OK)

    lines = []
    lines.append(header)
    lines.append(f"📊 Отчёт за {local_date} ({tz_norm})")
    lines.append("")
    lines.append(streak_line)
    lines.append("")
    lines.append("🟢 Доход")
    lines.append(f"Итого: +{_fmt_money(income)} {currency}")
    lines.append("")
    lines.append("🔴 Расход")
    if top_lines:
        lines.extend(top_lines)
    else:
        lines.append("• нет")
    lines.append(f"Итого: -{_fmt_money(expense)} {currency}")
    lines.append("")
    lines.append("🧾 Итог")
    lines.append(f"• Разница: {sign}{_fmt_money(net)} {currency}")
    lines.append(f"• Операций: {cnt}")
    lines.append("")
    if cnt == 0:
        lines.append("👉 Добавь одну операцию сейчас — и всё будет чисто в отчёте.")
    else:
        lines.append("👉 Если хочешь жёстче контроль — поставь лимит: /budget")

    return "\n".join(lines)


async def tick_daily(bot, db: aiosqlite.Connection):
    """
    Тик раз в час.
    1) За 1 час до установленного времени — шлём pre-reminder (1 раз в день)
    2) В установленное время — шлём отчёт (1 раз в день)
    """
    now_utc = datetime.now(timezone.utc)
    targets = await list_daily_targets(db)

    # окно 1 час, потому что тик раз в час
    window = timedelta(hours=1)

    for (user_id, currency, tz_name, hhmm, last_sent, pre_last_sent) in targets:
        try:
            uid = int(user_id)
            tz, tz_norm = _safe_tz(str(tz_name or "UTC"))

            local_now = now_utc.astimezone(tz)
            local_date = local_now.date().isoformat()

            hh, mm = _parse_hhmm(str(hhmm or "21:00"))
            report_local = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            pre_local = report_local - timedelta(hours=1)

            # PRE-REMINDER (если попали в окно и сегодня ещё не слали)
            if (pre_last_sent or "") != local_date and _in_window(local_now, pre_local, window):
                start_utc, end_utc, _, _ = _day_bounds_utc(now_utc, tz_norm)
                _, _, cnt_today = await report_period(db, uid, start_utc, end_utc)

                if cnt_today == 0:
                    pre_text = random.choice(PRE_ZERO)
                else:
                    pre_text = random.choice(PRE_OK).format(cnt=cnt_today)

                await _send_safe(bot, uid, pre_text)
                await mark_daily_pre_sent(db, uid, local_date, _iso(now_utc))

            # REPORT (если попали в окно и сегодня ещё не слали)
            if (last_sent or "") != local_date and _in_window(local_now, report_local, window):
                text = await _build_daily_text(db, uid, str(currency or "KZT"), tz_norm, now_utc)
                await _send_safe(bot, uid, text)
                await mark_daily_sent(db, uid, local_date, _iso(now_utc))

        except Exception as e:
            logger.exception(f"daily tick failed uid={user_id}: {e}")
            continue

    await db.commit()


def setup_scheduler(bot, db: aiosqlite.Connection) -> AsyncIOScheduler:
    """
    Тикаем строго раз в час, в начале часа (UTC).
    Для каждого юзера внутри проверяем своё локальное время.
    """
    sch = AsyncIOScheduler(timezone="UTC")
    sch.add_job(
        tick_daily,
        CronTrigger(minute=0),   # каждый час на 00 минут
        args=(bot, db),
        id="daily:tick",
        replace_existing=True
    )
    return sch
