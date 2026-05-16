import aiosqlite
from datetime import datetime, timedelta, timezone

async def apply(db: aiosqlite.Connection):
    db.row_factory = aiosqlite.Row
    
    # Find permanent full users
    cur = await db.execute("SELECT user_id FROM users WHERE mode='full' AND full_access_until IS NULL")
    rows = await cur.fetchall()
    
    if not rows:
        return

    until = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    
    for row in rows:
        user_id = row['user_id']
        await db.execute(
            "UPDATE users SET full_access=1, full_access_until=? WHERE user_id=?",
            (until, user_id)
        )
    
    print(f"[MIGRATION] Migrated {len(rows)} permanent users to 30-day model.")
