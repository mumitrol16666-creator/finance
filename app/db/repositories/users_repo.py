from __future__ import annotations
import aiosqlite

async def upsert_user(db: aiosqlite.Connection, user_id: int, created_at: str):
    await db.execute(
        "INSERT OR IGNORE INTO users(user_id, created_at, onboarded) VALUES(?,?,0)",
        (user_id, created_at),
    )

async def set_onboarded(db: aiosqlite.Connection, user_id: int, onboarded: int):
    await db.execute("UPDATE users SET onboarded=? WHERE user_id=?", (onboarded, user_id))

async def get_onboarded(db: aiosqlite.Connection, user_id: int) -> int | None:
    cur = await db.execute("SELECT onboarded FROM users WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    return None if not row else int(row[0])


async def get_streak(db: aiosqlite.Connection, user_id: int) -> tuple[int, int, str | None]:
    cur = await db.execute(
        "SELECT COALESCE(current_streak,0), COALESCE(max_streak,0), last_activity_date FROM users WHERE user_id=?",
        (user_id,),
    )
    row = await cur.fetchone()
    if not row:
        return 0, 0, None
    return int(row[0] or 0), int(row[1] or 0), (str(row[2]) if row[2] else None)

async def update_streak_on_activity(db: aiosqlite.Connection, user_id: int, local_date: str) -> int:
    """Update streak when user makes a transaction in their local date (YYYY-MM-DD).
    Safe to call multiple times per day.
    """
    cur = await db.execute(
        "SELECT COALESCE(current_streak,0), COALESCE(max_streak,0), last_activity_date FROM users WHERE user_id=?",
        (user_id,),
    )
    row = await cur.fetchone()
    if not row:
        return 0

    current = int(row[0] or 0)
    best = int(row[1] or 0)
    last = str(row[2]) if row[2] else None

    if last == local_date:
        return current  # already counted today

    from datetime import date, timedelta
    try:
        today = date.fromisoformat(local_date)
    except Exception:
        return current

    if last:
        try:
            last_d = date.fromisoformat(last)
        except Exception:
            last_d = None
    else:
        last_d = None

    if last_d and last_d == (today - timedelta(days=1)):
        current = current + 1
    else:
        current = 1

    if current > best:
        best = current

    await db.execute(
        "UPDATE users SET current_streak=?, max_streak=?, last_activity_date=? WHERE user_id=?",
        (current, best, local_date, user_id),
    )
    return current


async def get_access_profile(db: aiosqlite.Connection, user_id: int):
    cur = await db.execute(
        "SELECT onboarded, current_streak, max_streak, last_activity_date, COALESCE(mode, 'newbie') AS mode, COALESCE(progress_level,0) AS progress_level, COALESCE(full_access,0) AS full_access, full_access_until FROM users WHERE user_id=?",
        (user_id,),
    )
    return await cur.fetchone()


async def set_progress_level(db: aiosqlite.Connection, user_id: int, progress_level: int):
    await db.execute("UPDATE users SET progress_level=? WHERE user_id=?", (int(progress_level), user_id))


async def set_mode(db: aiosqlite.Connection, user_id: int, mode: str):
    await db.execute("UPDATE users SET mode=? WHERE user_id=?", (str(mode or 'newbie').lower(), user_id))


async def grant_full_access(db: aiosqlite.Connection, user_id: int, days: int = 90):
    from datetime import datetime, timedelta, timezone, date
    
    # Get current state
    cur = await db.execute("SELECT full_access_until FROM users WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    
    now = datetime.now(timezone.utc)
    base_date = now.date()
    
    if row and row[0]:
        try:
            current_until = date.fromisoformat(row[0])
            if current_until > base_date:
                base_date = current_until
        except Exception:
            pass
            
    until_date = base_date + timedelta(days=days)
    until_str = until_date.strftime("%Y-%m-%d")
    
    await db.execute(
        "UPDATE users SET full_access=1, mode='full', full_access_until=? WHERE user_id=?",
        (until_str, user_id),
    )


async def set_newbie_defaults(db: aiosqlite.Connection, user_id: int):
    cur = await db.execute("SELECT full_access FROM users WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if row and int(row[0] or 0) == 1:
        # Keep full access mode and active subscription, only reset progress level
        await db.execute("UPDATE users SET progress_level=0 WHERE user_id=?", (user_id,))
    else:
        await db.execute("UPDATE users SET mode='newbie', progress_level=0, full_access=0 WHERE user_id=?", (user_id,))


async def get_free_exports_used(db: aiosqlite.Connection, user_id: int) -> int:
    """
    Возвращает количество использованных бесплатных Excel-выгрузок.
    Если поля нет (или юзер новый), возвращает 0.
    """
    cur = await db.execute("SELECT COALESCE(free_exports_used, 0) FROM users WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def increment_free_export(db: aiosqlite.Connection, user_id: int) -> None:
    """
    Увеличивает счетчик бесплатных Excel-выгрузок на 1.
    """
    await db.execute(
        "UPDATE users SET free_exports_used = COALESCE(free_exports_used, 0) + 1 WHERE user_id = ?",
        (user_id,),
    )


async def get_all_active_users(db: aiosqlite.Connection) -> list[int]:
    """
    Возвращает список ID всех активных (прошедших онбординг) пользователей.
    """
    cur = await db.execute("SELECT user_id FROM users WHERE onboarded = 1")
    rows = await cur.fetchall()
    return [row[0] for row in rows]


async def is_promo_used(db: aiosqlite.Connection, user_id: int) -> bool:
    """
    Проверяет, была ли использована разовая скидка на подписку.
    """
    cur = await db.execute("SELECT COALESCE(promo_used, 0) FROM users WHERE user_id = ?", (user_id,))
    row = await cur.fetchone()
    return int(row[0]) == 1 if row else False


async def mark_promo_used(db: aiosqlite.Connection, user_id: int) -> None:
    """
    Помечает разовую скидку как использованную.
    """
    await db.execute("UPDATE users SET promo_used = 1 WHERE user_id = ?", (user_id,))


async def is_eligible_for_trial_3d(db: aiosqlite.Connection, user_id: int) -> bool:
    """
    Проверяет, подходит ли пользователь под условия бесплатного 3-дневного триала:
    1. Еще не активировал этот 3-дневный триал (trial_3d_claimed = 0).
    2. Ни разу не имел премиум-доступа (full_access_until IS NULL).
    3. Достиг серии активности >= 5 дней (current_streak >= 5 или max_streak >= 5).
    """
    cur = await db.execute(
        """
        SELECT 
            COALESCE(trial_3d_claimed, 0) AS trial_claimed,
            full_access_until,
            COALESCE(current_streak, 0) AS cur_streak,
            COALESCE(max_streak, 0) AS m_streak
        FROM users 
        WHERE user_id = ?
        """,
        (user_id,),
    )
    row = await cur.fetchone()
    if not row:
        return False
    
    trial_claimed = int(row["trial_claimed"])
    full_access_until = row["full_access_until"]
    cur_streak = int(row["cur_streak"])
    m_streak = int(row["m_streak"])
    
    if trial_claimed == 1:
        return False
    if full_access_until is not None:
        return False
    if cur_streak < 5 and m_streak < 5:
        return False
        
    return True


async def mark_trial_3d_claimed(db: aiosqlite.Connection, user_id: int) -> None:
    """
    Помечает бесплатный 3-дневный триал как активированный.
    """
    await db.execute("UPDATE users SET trial_3d_claimed = 1 WHERE user_id = ?", (user_id,))


