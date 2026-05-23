from __future__ import annotations
import random

import asyncio
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import aiosqlite
from loguru import logger

from app.db.repositories.settings_repo import (
    list_notify_targets,
    list_debt_notify_targets,
    mark_daily_sent,
    mark_daily_pre_sent,
    mark_nudge_sent,
)
from app.db.repositories.users_repo import get_streak
from app.db.repositories.settings_repo import get_financial_goal
from app.domain.services.ai_consultant_service import build_ai_context, build_ai_scheduler_warning
from app.domain.services.reports_service import report_period, report_by_category
from app.db.repositories.debts_repo import list_due_debts_for_reminders, debt_reminder_already_sent, mark_debt_reminder_sent


TOP_CATS = 5
NUDGE_START_HH = 9  # локально: с 09:00
# конец для nudges берём как min(22:00, (время отчёта - 1ч)) — см. ниже



NUDGE_ZERO = [
    "🔔 Сегодня 0 записей. Да, снова нихуя не занесено.",
    "🔔 Ноль операций за день. Красиво игнорируешь учёт.",
    "🔔 Сегодня пусто. День идёт, а ты всё так же ничего не записал.",
    "🔔 0 записей. Потом опять будешь гадать, куда деньги делись.",
    "🔔 Пока ноль. Видимо, память у тебя безлимитная, да?",
    "🔔 Сегодня 0. Отличная стратегия — ничего не фиксировать.",
    "🔔 Пусто. Финансы сами себя не занесут, сюрприз.",
    "🔔 0 записей. День почти идёт в мусор.",
    "🔔 Сегодня нихуя. Просто напоминание.",
    "🔔 Ноль. Как обычно, потом будешь вспоминать наугад."
]

NUDGE_OK = [
    "🔔 Уже {cnt} записей. Ну хоть не полный пиздец.",
    "🔔 Сегодня {cnt}. Ладно, хотя бы что-то делаешь.",
    "🔔 {cnt} записей. Не идеально, но живём.",
    "🔔 Уже {cnt}. Можешь же, когда не тупишь.",
    "🔔 {cnt} за сегодня. Ок, система хотя бы не мертва.",
    "🔔 Уже {cnt}. Не разваливаешься — уже успех.",
    "🔔 {cnt}. Продолжай, не сливайся.",
    "🔔 Уже {cnt}. Хоть какая-то дисциплина появилась.",
    "🔔 {cnt} записей. Ладно, не всё потеряно.",
    "🔔 Уже {cnt}. Сегодня хотя бы не забил полностью."
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


def _date_human(ymd: str) -> str:
    try:
        return datetime.strptime(ymd, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return ymd


def _debt_kind_text(lang: str, direction: str, dtype: str) -> str:
    if lang == "en":
        return "loan payment" if direction == "out" and dtype == "bank" else ("you owe" if direction == "out" else "owed to you")
    if lang == "kk":
        return "несие төлемі" if direction == "out" and dtype == "bank" else ("сіз қарызсыз" if direction == "out" else "сізге қарыз")
    return "платёж по кредиту" if direction == "out" and dtype == "bank" else ("вы должны" if direction == "out" else "вам должны")


def _build_debt_reminder_text(lang: str, debt: dict, days_left: int, currency: str) -> tuple[str, str]:
    title = debt.get("title") or "—"
    amount = int(debt.get("payment_amount") or 0)
    due = str(debt.get("next_payment_date") or "")
    kind = _debt_kind_text(lang, str(debt.get("direction") or "out"), str(debt.get("dtype") or "private"))
    amount_line = f"{_fmt_money(amount)} {currency}" if amount > 0 else ("not fixed" if lang == "en" else ("бекітілмеген" if lang == "kk" else "не фиксирован"))

    if days_left < 0:
        key = "overdue"
        if lang == "en":
            text = f"🔴 <b>Overdue debt reminder</b>\n\n<b>{title}</b> — {kind}.\nDue date: <b>{_date_human(due)}</b>\nPlanned payment: <b>{amount_line}</b>\n\nThe payment date has already passed."
        elif lang == "kk":
            text = f"🔴 <b>Қарыз бойынша кешігу</b>\n\n<b>{title}</b> — {kind}.\nТөлем күні: <b>{_date_human(due)}</b>\nЖоспарланған төлем: <b>{amount_line}</b>\n\nТөлем күні өтіп кетті."
        else:
            text = f"🔴 <b>Просрочка по долгу</b>\n\n<b>{title}</b> — {kind}.\nДата: <b>{_date_human(due)}</b>\nПлановый платёж: <b>{amount_line}</b>\n\nСрок платежа уже прошёл."
    elif days_left == 0:
        key = "today"
        if lang == "en":
            text = f"🟡 <b>Debt reminder for today</b>\n\n<b>{title}</b> — {kind}.\nDue date: <b>today</b>\nPlanned payment: <b>{amount_line}</b>."
        elif lang == "kk":
            text = f"🟡 <b>Бүгінгі қарыз еске салғышы</b>\n\n<b>{title}</b> — {kind}.\nТөлем күні: <b>бүгін</b>\nЖоспарланған төлем: <b>{amount_line}</b>."
        else:
            text = f"🟡 <b>Напоминание по долгу на сегодня</b>\n\n<b>{title}</b> — {kind}.\nДата платежа: <b>сегодня</b>\nПлановый платёж: <b>{amount_line}</b>."
    else:
        key = "soon"
        if lang == "en":
            text = f"🟠 <b>Upcoming debt reminder</b>\n\n<b>{title}</b> — {kind}.\nDue in: <b>{days_left} day(s)</b>\nDate: <b>{_date_human(due)}</b>\nPlanned payment: <b>{amount_line}</b>."
        elif lang == "kk":
            text = f"🟠 <b>Жақында болатын қарыз</b>\n\n<b>{title}</b> — {kind}.\nҚалғаны: <b>{days_left} күн</b>\nКүні: <b>{_date_human(due)}</b>\nЖоспарланған төлем: <b>{amount_line}</b>."
        else:
            text = f"🟠 <b>Скорый платёж по долгу</b>\n\n<b>{title}</b> — {kind}.\nДо даты: <b>{days_left} дн.</b>\nДата: <b>{_date_human(due)}</b>\nПлановый платёж: <b>{amount_line}</b>."
    return key, text


async def _send_debt_reminders(bot, db: aiosqlite.Connection, user_id: int, currency: str, tz_name: str, lang: str, days_before: int, now_utc: datetime):
    tz, tz_norm = _safe_tz(tz_name)
    local_now = now_utc.astimezone(tz)
    local_date = local_now.date().isoformat()
    if local_now.hour < 9:
        return

    rows = await list_due_debts_for_reminders(db, user_id)
    for row in rows:
        debt = {
            "id": row[0], "title": row[1], "payment_amount": row[2], "next_payment_date": row[3],
            "remaining_amount": row[4], "dtype": row[5], "direction": row[6], "is_active": row[7],
        }
        try:
            due = datetime.strptime(str(debt.get("next_payment_date")), "%Y-%m-%d").date()
        except Exception:
            continue
        days_left = (due - local_now.date()).days
        if days_left > int(days_before or 3):
            continue
        reminder_kind, text = _build_debt_reminder_text(lang, debt, days_left, currency)
        if await debt_reminder_already_sent(db, int(user_id), int(debt["id"]), reminder_kind, local_date):
            continue
        await _send_safe(bot, int(user_id), text, parse_mode="HTML")
        await mark_debt_reminder_sent(db, int(user_id), int(debt["id"]), reminder_kind, local_date)


def _day_bounds_utc(now_utc: datetime, tz_name: str) -> tuple[datetime, datetime, str, str]:
    tz, tz_norm = _safe_tz(tz_name)
    local_now = now_utc.astimezone(tz)
    d = local_now.date()
    local_start = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc), d.isoformat(), tz_norm


async def _build_ai_signal_text(db: aiosqlite.Connection, user_id: int, tz_name: str) -> str:
    try:
        goal_text = await get_financial_goal(db, user_id)
        context = await build_ai_context(db, user_id, tz_name, "month", goal_text)
        return build_ai_scheduler_warning(context)
    except Exception as e:
        logger.warning(f"ai signal build failed uid={user_id}: {e}")
        return ""


async def _send_safe(bot, user_id: int, text: str, *, parse_mode: str | None = None):
    try:
        await bot.send_message(user_id, text, parse_mode=parse_mode)
    except Exception as e:
        # Forbidden: bot blocked by user — это нормальная ситуация, не валим цикл
        logger.warning(f"send failed uid={user_id}: {e}")


async def _build_daily_text(db: aiosqlite.Connection, user_id: int, currency: str, tz_name: str, now_utc: datetime) -> str:
    start_utc, end_utc, local_date, tz_norm = _day_bounds_utc(now_utc, tz_name)

    income, expense, cnt = await report_period(db, user_id, start_utc, end_utc)
    cats = await report_by_category(db, user_id, start_utc, end_utc, "expense", TOP_CATS)

    # топ категорий
    top_lines: list[str] = []
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
            "Сегодня 0 записей — добавь одну, чтобы серия продолжилась."
        )
    else:
        badge = "👑" if cur_streak >= 30 else ("🚀" if cur_streak >= 8 else "🔥")
        streak_line = (
            f"{badge} Серия: {cur_streak} дн. (лучшее: {best_streak})\n"
            "Записи есть — серия сохранена."
        )

    net = int(income - expense)
    sign = "+" if net >= 0 else "-"

    lines: list[str] = []
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
        lines.append("👉 Добавь одну операцию сейчас — и серия не оборвётся.")
    else:
        lines.append("👉 Хочешь больше контроля — лимиты: /budget")

    return "\n".join(lines)


async def _check_and_send_trial_reminders(bot, db: aiosqlite.Connection):
    from datetime import date, datetime, timezone
    from zoneinfo import ZoneInfo
    from app.ui.keyboards import upgrade_info_kb

    try:
        cur = await db.execute(
            """
            SELECT u.user_id, u.full_access_until, s.lang, s.timezone 
            FROM users u
            JOIN settings s ON u.user_id = s.user_id
            WHERE u.full_access = 1 
              AND u.full_access_until IS NOT NULL 
              AND COALESCE(s.trial_reminder_sent, 0) = 0
            """
        )
        rows = await cur.fetchall()
        for user_id, full_access_until, lang, tz_name in rows:
            try:
                tz = ZoneInfo(tz_name or "Asia/Aqtobe")
            except Exception:
                tz = ZoneInfo("Asia/Aqtobe")

            local_now = datetime.now(tz)
            # Only send between 10:00 and 21:00 user local time
            if not (10 <= local_now.hour < 21):
                continue

            try:
                until_date = date.fromisoformat(full_access_until)
            except Exception:
                continue

            days_left = (until_date - local_now.date()).days
            if days_left <= 1:
                # 6 days have passed, 1 day or less remains of the 7-day trial. Offer renewal.
                msg = {
                    "ru": (
                        "⚠️ <b>Пробный период заканчивается!</b>\n\n"
                        "Скоро бот перейдет в бесплатный режим с ограничениями. "
                        "Чтобы сохранить все профессиональные функции (ИИ-Консультант, Лимиты, Бюджеты, Регулярные платежи), продли подписку прямо сейчас:\n\n"
                        "⭐ <b>1 месяц</b> — 15 звезд\n"
                        "⭐ <b>3 месяца</b> — 115 звезд\n\n"
                        "Нажми одну из кнопок ниже для оплаты через Telegram Stars 👇"
                    ),
                    "en": (
                        "⚠️ <b>Your trial period is ending soon!</b>\n\n"
                        "The bot will revert to the free version with limits. "
                        "To keep full access to all professional features (AI Consultant, Limits, Budgets, Recurring Payments), renew your subscription now:\n\n"
                        "⭐ <b>1 month</b> — 15 stars\n"
                        "⭐ <b>3 months</b> — 115 stars\n\n"
                        "Click one of the buttons below to pay with Telegram Stars 👇"
                    ),
                    "kk": (
                        "⚠️ <b>Сынақ мерзіміңіз аяқталуға жақын!</b>\n\n"
                        "Жақында бот шектеулері бар тегін нұсқаға өтеді. "
                        "Барлық кәсіби мүмкіндіктерге (AI-Консультант, Лимиттер, Бюджеттер, Тұрақты төлемдер) толық қолжетімділікті сақтау үшін жазылымды қазір ұзартыңыз:\n\n"
                        "⭐ <b>1 ай</b> — 15 жұлдыз\n"
                        "⭐ <b>3 ай</b> — 115 жұлдыз\n\n"
                        "Telegram Stars арқылы төлеу үшін төмендегі батырмалардың бірін басыңыз 👇"
                    )
                }.get(lang, "ru")

                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=msg,
                        parse_mode="HTML",
                        reply_markup=upgrade_info_kb(lang)
                    )
                    await db.execute(
                        "UPDATE settings SET trial_reminder_sent = 1, updated_at = ? WHERE user_id = ?",
                        (datetime.now(timezone.utc).isoformat(), user_id)
                    )
                    await db.commit()
                    logger.info(f"Sent trial expiration reminder to user {user_id}")
                except Exception as e:
                    logger.warning(f"Failed to send trial reminder to user {user_id}: {e}")
    except Exception as e:
        logger.exception(f"Error checking/sending trial reminders: {e}")


async def tick_daily(bot, db: aiosqlite.Connection):
    now_utc = datetime.now(timezone.utc)
    await _check_and_send_trial_reminders(bot, db)
    targets = await list_notify_targets(db)

    for (
        user_id,
        currency,
        tz_name,
        lang,
        daily_enabled,
        hhmm,
        last_sent,
        pre_last_sent,
        nudge_enabled,
        nudge_interval_min,
        nudge_last_sent_at,
        debts_enabled,
        debts_days_before,
    ) in targets:
        try:
            uid = int(user_id)
            tz, tz_norm = _safe_tz(str(tz_name or "UTC"))

            local_now = now_utc.astimezone(tz)
            local_date = local_now.date().isoformat()

            # границы "сегодня" в UTC для подсчёта cnt_today
            start_utc, end_utc, _, _ = _day_bounds_utc(now_utc, tz_norm)

            # ---------------- DEBT REMINDERS ----------------
            if int(debts_enabled or 0) == 1:
                await _send_debt_reminders(bot, db, uid, str(currency or "KZT"), tz_norm, str(lang or "ru"), int(debts_days_before or 3), now_utc)

            # ---------------- NUDGES (в течение дня) ----------------
            if int(nudge_enabled or 0) == 1:
                interval = int(nudge_interval_min or 180)
                # окно: 09:00 .. min(22:00, время_отчёта - 1ч)
                rep_h, rep_m = _parse_hhmm(str(hhmm or "21:00"))
                report_local = local_now.replace(hour=rep_h, minute=rep_m, second=0, microsecond=0)
                nudge_end = report_local - timedelta(hours=1)
                # если отчёт очень рано — просто ограничим 22:00
                end_cap = local_now.replace(hour=22, minute=0, second=0, microsecond=0)
                if nudge_end > end_cap:
                    nudge_end = end_cap
                nudge_start = local_now.replace(hour=NUDGE_START_HH, minute=0, second=0, microsecond=0)

                in_window = (local_now >= nudge_start) and (local_now <= nudge_end)

                should_send = False
                if in_window:
                    if not nudge_last_sent_at:
                        should_send = True
                    else:
                        try:
                            last_dt = datetime.fromisoformat(str(nudge_last_sent_at))
                            if last_dt.tzinfo is None:
                                last_dt = last_dt.replace(tzinfo=timezone.utc)
                        except Exception:
                            last_dt = None
                        if (last_dt is None) or (now_utc - last_dt >= timedelta(minutes=interval)):
                            should_send = True

                if should_send:
                    _, _, cnt_today = await report_period(db, uid, start_utc, end_utc)

                    if cnt_today == 0:
                        nudge_text = random.choice(NUDGE_ZERO)
                    else:
                        nudge_text = random.choice(NUDGE_OK).format(cnt=cnt_today)

                    ai_signal = await _build_ai_signal_text(db, uid, tz_norm)
                    full_nudge = nudge_text if not ai_signal else f"{nudge_text}\n\n{ai_signal}"
                    await _send_safe(bot, uid, full_nudge, parse_mode="HTML" if ai_signal else None)
                    await mark_nudge_sent(db, uid, _iso(now_utc))

            # ---------------- PRE + DAILY REPORT ----------------
            if int(daily_enabled or 0) != 1:
                continue

            rep_h, rep_m = _parse_hhmm(str(hhmm or "21:00"))
            report_local = local_now.replace(hour=rep_h, minute=rep_m, second=0, microsecond=0)
            pre_local = report_local - timedelta(hours=1)

            # PRE (за час)
            if (
                local_now.hour == pre_local.hour
                and local_now.minute == pre_local.minute
                and (pre_last_sent or "") != local_date
            ):
                _, _, cnt_today = await report_period(db, uid, start_utc, end_utc)

                if cnt_today == 0:
                    pre_text = random.choice(PRE_ZERO)
                else:
                    pre_text = random.choice(PRE_OK).format(cnt=cnt_today)

                ai_signal = await _build_ai_signal_text(db, uid, tz_norm)
                full_pre = pre_text if not ai_signal else f"{pre_text}\n\n{ai_signal}"
                await _send_safe(bot, uid, full_pre, parse_mode="HTML" if ai_signal else None)
                await mark_daily_pre_sent(db, uid, local_date, _iso(now_utc))

            # REPORT
            if (
                local_now.hour == report_local.hour
                and local_now.minute == report_local.minute
                and (last_sent or "") != local_date
            ):
                text = await _build_daily_text(db, uid, str(currency or "KZT"), tz_norm, now_utc)
                ai_signal = await _build_ai_signal_text(db, uid, tz_norm)
                full_report = text if not ai_signal else f"{text}\n\n{ai_signal}"
                await _send_safe(bot, uid, full_report, parse_mode="HTML" if ai_signal else None)
                await mark_daily_sent(db, uid, local_date, _iso(now_utc))

        except Exception as e:
            logger.exception(f"daily tick failed uid={user_id}: {e}")
            continue

    await db.commit()


async def run_daily_loop(bot, db: aiosqlite.Connection):
    """
    Проверяет цели раз в час:
    - днём: "напоминания" (если включены) с заданным интервалом
    - за час до отчёта: pre-reminder
    - в назначенное время: отчёт за день
    """
    logger.info("daily loop started (hourly)")
    while True:
        try:
            await tick_daily(bot, db)
        except Exception as e:
            logger.exception(f"daily loop tick failed: {e}")
        await asyncio.sleep(60 * 60)
