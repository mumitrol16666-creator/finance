import aiosqlite


async def wipe_user_data(db: aiosqlite.Connection, user_id: int) -> None:
    for sql in (
        "DELETE FROM liability_events WHERE user_id=?",
        "DELETE FROM liabilities WHERE user_id=?",
    ):
        try:
            await db.execute(sql, (user_id,))
        except Exception:
            pass

    try:
        await db.execute("DELETE FROM debt_reminder_log WHERE user_id=?", (user_id,))
    except Exception:
        pass

    await db.execute("DELETE FROM users WHERE user_id=?", (user_id,))
    await db.commit()
