from __future__ import annotations
import aiosqlite

async def ensure_settings(db: aiosqlite.Connection, user_id: int, created_at: str, timezone: str):
    await db.execute(
        "INSERT OR IGNORE INTO settings(user_id, currency, timezone, lang, daily_report_enabled, daily_report_time, note_max_len, debts_enabled, debts_days_before, created_at, updated_at) "
        "VALUES(?, 'KZT', ?, 'ru', 0, '21:00', 80, 1, 3, ?, ?)",
        (user_id, timezone, created_at, created_at),
    )

async def update_currency(db: aiosqlite.Connection, user_id: int, currency: str, updated_at: str):
    await db.execute("UPDATE settings SET currency=?, updated_at=? WHERE user_id=?", (currency, updated_at, user_id))

async def update_daily_report(db: aiosqlite.Connection, user_id: int, enabled: int, time_hhmm: str, updated_at: str):
    await db.execute(
        "UPDATE settings SET daily_report_enabled=?, daily_report_time=?, updated_at=? WHERE user_id=?",
        (enabled, time_hhmm, updated_at, user_id),
    )

async def get_settings(db: aiosqlite.Connection, user_id: int):
    cur = await db.execute(
        "SELECT currency, timezone, daily_report_enabled, daily_report_time, note_max_len, "
        "daily_report_last_sent_date, daily_report_pre_last_sent_date "
        "FROM settings WHERE user_id=?",
        (user_id,),
    )
    return await cur.fetchone()


async def get_notification_settings(db: aiosqlite.Connection, user_id: int):
    cur = await db.execute(
        "SELECT daily_report_enabled, daily_report_time, nudge_enabled, nudge_interval_min "
        "FROM settings WHERE user_id=?",
        (user_id,),
    )
    return await cur.fetchone()


async def update_nudges(db: aiosqlite.Connection, user_id: int, enabled: int, interval_min: int, updated_at: str):
    await db.execute(
        "UPDATE settings SET nudge_enabled=?, nudge_interval_min=?, updated_at=? WHERE user_id=?",
        (enabled, interval_min, updated_at, user_id),
    )


async def get_debt_settings(db: aiosqlite.Connection, user_id: int):
    cur = await db.execute(
        "SELECT debts_enabled, debts_days_before FROM settings WHERE user_id=?",
        (user_id,),
    )
    row = await cur.fetchone()
    if not row:
        return 1, 3
    return int(row[0] or 0), int(row[1] or 3)


async def update_debt_settings(db: aiosqlite.Connection, user_id: int, enabled: int, days_before: int, updated_at: str):
    await db.execute(
        "UPDATE settings SET debts_enabled=?, debts_days_before=?, updated_at=? WHERE user_id=?",
        (int(enabled), int(days_before), updated_at, user_id),
    )


async def list_notify_targets(db: aiosqlite.Connection):
    cur = await db.execute(
        "SELECT user_id, currency, timezone, lang, "
        "daily_report_enabled, daily_report_time, "
        "daily_report_last_sent_date, daily_report_pre_last_sent_date, "
        "nudge_enabled, nudge_interval_min, nudge_last_sent_at, debts_enabled, debts_days_before, "
        "recurring_inc_enabled, recurring_inc_days, recurring_exp_enabled, recurring_exp_days "
        "FROM settings WHERE daily_report_enabled=1 OR nudge_enabled=1 OR debts_enabled=1 OR recurring_inc_enabled=1 OR recurring_exp_enabled=1"
    )
    return await cur.fetchall()


async def mark_nudge_sent(db: aiosqlite.Connection, user_id: int, sent_at_utc: str):
    await db.execute(
        "UPDATE settings SET nudge_last_sent_at=?, updated_at=? WHERE user_id=?",
        (sent_at_utc, sent_at_utc, user_id),
    )

async def mark_limits_nudge_sent(db: aiosqlite.Connection, user_id: int, local_date: str, updated_at: str):
    await db.execute(
        "UPDATE settings SET limits_nudge_last_sent_date=?, updated_at=? WHERE user_id=?",
        (local_date, updated_at, user_id),
    )

async def list_daily_targets(db: aiosqlite.Connection):
    cur = await db.execute(
        "SELECT user_id, currency, timezone, daily_report_time, "
        "daily_report_last_sent_date, daily_report_pre_last_sent_date "
        "FROM settings WHERE daily_report_enabled=1"
    )
    return await cur.fetchall()


async def mark_daily_sent(db: aiosqlite.Connection, user_id: int, local_date: str, updated_at: str):
    await db.execute(
        "UPDATE settings SET daily_report_last_sent_date=?, updated_at=? WHERE user_id=?",
        (local_date, updated_at, user_id),
    )


async def mark_daily_pre_sent(db: aiosqlite.Connection, user_id: int, local_date: str, updated_at: str):
    await db.execute(
        "UPDATE settings SET daily_report_pre_last_sent_date=?, updated_at=? WHERE user_id=?",
        (local_date, updated_at, user_id),
    )


async def get_lang(db: aiosqlite.Connection, user_id: int) -> str:
    cur = await db.execute("SELECT lang FROM settings WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if not row or not row[0]:
        return "ru"
    return str(row[0]).lower()

async def set_lang(db: aiosqlite.Connection, user_id: int, lang: str, updated_at: str):
    lang = (lang or "ru").lower()
    if lang not in ("ru", "en", "kk"):
        lang = "ru"
    await db.execute(
        "UPDATE settings SET lang=?, updated_at=? WHERE user_id=?",
        (lang, updated_at, user_id),
    )


async def get_timezone(db: aiosqlite.Connection, user_id: int) -> str:
    cur = await db.execute("SELECT timezone FROM settings WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    return (str(row[0]) if row and row[0] else "Asia/Aqtobe")


async def get_financial_goal(db: aiosqlite.Connection, user_id: int) -> str | None:
    cur = await db.execute("SELECT financial_goal_text FROM settings WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    return str(row[0]) if row and row[0] else None


async def set_financial_goal(db: aiosqlite.Connection, user_id: int, goal_text: str | None, updated_at: str):
    await db.execute("UPDATE settings SET financial_goal_text=?, updated_at=? WHERE user_id=?", (goal_text, updated_at, user_id))


async def get_ai_usage(db: aiosqlite.Connection, user_id: int) -> tuple[int, str | None]:
    cur = await db.execute("SELECT ai_reports_used_month, ai_reports_month FROM settings WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if not row:
        return 0, None
    return int(row[0] or 0), (str(row[1]) if row[1] else None)


async def set_ai_usage(db: aiosqlite.Connection, user_id: int, used: int, month: str | None, updated_at: str):
    await db.execute("UPDATE settings SET ai_reports_used_month=?, ai_reports_month=?, updated_at=? WHERE user_id=?", (int(used), month, updated_at, user_id))


async def list_debt_notify_targets(db: aiosqlite.Connection):
    cur = await db.execute(
        "SELECT user_id, currency, timezone, lang, debts_enabled, debts_days_before FROM settings WHERE debts_enabled=1"
    )
    return await cur.fetchall()

async def get_recurring_settings(db: aiosqlite.Connection, user_id: int):
    cur = await db.execute(
        "SELECT recurring_inc_enabled, recurring_inc_days, recurring_exp_enabled, recurring_exp_days "
        "FROM settings WHERE user_id=?",
        (user_id,),
    )
    row = await cur.fetchone()
    if not row:
        return 1, 0, 1, 1
    return tuple(int(x or 0) for x in row)

async def update_recurring_inc_settings(db: aiosqlite.Connection, user_id: int, enabled: int, days: int, updated_at: str):
    await db.execute(
        "UPDATE settings SET recurring_inc_enabled=?, recurring_inc_days=?, updated_at=? WHERE user_id=?",
        (int(enabled), int(days), updated_at, user_id),
    )

async def update_recurring_exp_settings(db: aiosqlite.Connection, user_id: int, enabled: int, days: int, updated_at: str):
    await db.execute(
        "UPDATE settings SET recurring_exp_enabled=?, recurring_exp_days=?, updated_at=? WHERE user_id=?",
        (int(enabled), int(days), updated_at, user_id),
    )


async def get_ai_chat_usage(db: aiosqlite.Connection, user_id: int) -> tuple[int, str | None, int]:
    """Returns (used, month, extra_purchased)."""
    cur = await db.execute("SELECT ai_chat_used, ai_chat_month, ai_chat_extra FROM settings WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if not row:
        return 0, None, 0
    return int(row[0] or 0), (str(row[1]) if row[1] else None), int(row[2] or 0)


async def set_ai_chat_usage(db: aiosqlite.Connection, user_id: int, used: int, month: str | None, updated_at: str):
    await db.execute(
        "UPDATE settings SET ai_chat_used=?, ai_chat_month=?, updated_at=? WHERE user_id=?",
        (int(used), month, updated_at, user_id),
    )


async def add_ai_chat_extra(db: aiosqlite.Connection, user_id: int, extra: int, updated_at: str):
    """Add purchased extra chat messages."""
    await db.execute(
        "UPDATE settings SET ai_chat_extra = ai_chat_extra + ?, updated_at=? WHERE user_id=?",
        (int(extra), updated_at, user_id),
    )


async def get_ai_reports_usage(db: aiosqlite.Connection, user_id: int) -> tuple[int, str | None, int]:
    """Returns (used, month, extra_purchased)."""
    cur = await db.execute("SELECT ai_reports_used_month, ai_reports_month, ai_reports_extra FROM settings WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if not row:
        return 0, None, 0
    return int(row[0] or 0), (str(row[1]) if row[1] else None), int(row[2] or 0)


async def add_ai_reports_extra(db: aiosqlite.Connection, user_id: int, extra: int, updated_at: str):
    """Add purchased extra deep reports."""
    await db.execute(
        "UPDATE settings SET ai_reports_extra = ai_reports_extra + ?, updated_at=? WHERE user_id=?",
        (int(extra), updated_at, user_id),
    )



async def save_onboarding_interview(
    db: aiosqlite.Connection,
    user_id: int,
    archetype: str,
    main_goal: str,
    daily_limit: int,
    updated_at: str,
):
    await db.execute(
        "UPDATE settings SET "
        "onboarding_archetype=?, "
        "onboarding_main_goal=?, "
        "onboarding_daily_limit=?, "
        "onboarding_interview_done=1, "
        "financial_goal_text=?, "
        "updated_at=? "
        "WHERE user_id=?",
        (archetype, main_goal, daily_limit, main_goal, updated_at, user_id),
    )

