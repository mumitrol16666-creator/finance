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

async def update_streak_on_activity(db: aiosqlite.Connection, user_id: int, local_date: str):
    """Update streak when user makes a transaction in their local date (YYYY-MM-DD).
    Safe to call multiple times per day.
    """
    cur = await db.execute(
        "SELECT COALESCE(current_streak,0), COALESCE(max_streak,0), last_activity_date FROM users WHERE user_id=?",
        (user_id,),
    )
    row = await cur.fetchone()
    if not row:
        return

    current = int(row[0] or 0)
    best = int(row[1] or 0)
    last = str(row[2]) if row[2] else None

    if last == local_date:
        return  # already counted today

    from datetime import date, timedelta
    try:
        today = date.fromisoformat(local_date)
    except Exception:
        return

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


async def get_access_profile(db: aiosqlite.Connection, user_id: int):
    cur = await db.execute(
        "SELECT onboarded, current_streak, max_streak, last_activity_date, COALESCE(mode, 'newbie') AS mode, COALESCE(progress_level,0) AS progress_level, COALESCE(full_access,0) AS full_access FROM users WHERE user_id=?",
        (user_id,),
    )
    return await cur.fetchone()


async def set_progress_level(db: aiosqlite.Connection, user_id: int, progress_level: int):
    await db.execute("UPDATE users SET progress_level=? WHERE user_id=?", (int(progress_level), user_id))


async def set_mode(db: aiosqlite.Connection, user_id: int, mode: str):
    await db.execute("UPDATE users SET mode=? WHERE user_id=?", (str(mode or 'newbie').lower(), user_id))


async def grant_full_access(db: aiosqlite.Connection, user_id: int):
    await db.execute("UPDATE users SET full_access=1, mode='full' WHERE user_id=?", (user_id,))


async def set_newbie_defaults(db: aiosqlite.Connection, user_id: int):
    await db.execute("UPDATE users SET mode='newbie', progress_level=0, full_access=0 WHERE user_id=?", (user_id,))
