import aiosqlite


async def wipe_user_data(db: aiosqlite.Connection, user_id: int) -> None:
    # 1. Clean up all user data in related tables
    tables = [
        "transactions",
        "accounts",
        "categories",
        "budgets",
        "daily_stats",
        "debts",
        "debt_payments",
        "recurring_expenses",
        "recurring_incomes",
        "ai_context_notes",
        "tx_audit",
        "ai_profile",
        "ai_insights",
        "ai_recommendations_log",
        "liability_events",
        "liabilities",
        "debt_reminder_log",
        "planned_transactions",
        "user_limits",
        "category_limits",
        "debt_notify_log",
    ]

    for table in tables:
        try:
            await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        except Exception:
            # Some tables might not exist or fail gracefully
            pass

    # 2. Reset onboarding & streak fields, but keep subscription (full_access, mode, full_access_until, free_exports_used)
    await db.execute(
        """
        UPDATE users 
        SET onboarded = 0, 
            current_streak = 0, 
            max_streak = 0, 
            progress_level = 0,
            last_activity_date = NULL 
        WHERE user_id = ?
        """,
        (user_id,),
    )

    # 3. Clear financial goals in settings, keeping tz, lang, notifications and AI usage counters
    try:
        await db.execute(
            """
            UPDATE settings 
            SET financial_goal_text = NULL, 
                financial_goal_amount = NULL, 
                financial_goal_deadline = NULL 
            WHERE user_id = ?
            """,
            (user_id,),
        )
    except Exception:
        pass

    await db.commit()
