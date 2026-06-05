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
        "export_logs",
        "login_codes",
    ]

    for table in tables:
        try:
            await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        except Exception:
            # Some tables might not exist or fail gracefully
            pass

    # Clean sent_keyboards by chat_id
    try:
        await db.execute("DELETE FROM sent_keyboards WHERE chat_id = ?", (user_id,))
    except Exception:
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
        WHERE id = ?
        """,
        (user_id,),
    )

    # 3. Clear financial goals and triggers in settings, keeping tz, lang, notifications and AI usage counters
    try:
        await db.execute(
            """
            UPDATE settings 
            SET financial_goal_text = NULL, 
                financial_goal_amount = NULL, 
                financial_goal_deadline = NULL,
                daily_report_last_sent_date = NULL,
                daily_report_pre_last_sent_date = NULL,
                nudge_last_sent_at = NULL,
                trial_reminder_sent = 0
            WHERE user_id = ?
            """,
            (user_id,),
        )
    except Exception:
        pass

    await db.commit()


async def delete_user_account(db: aiosqlite.Connection, user_id: int) -> None:
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
        "export_logs",
        "login_codes",
    ]

    for table in tables:
        try:
            await db.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        except Exception:
            pass

    # Clean sent_keyboards by chat_id
    try:
        await db.execute("DELETE FROM sent_keyboards WHERE chat_id = ?", (user_id,))
    except Exception:
        pass

    # 2. Clean settings and user table entries
    try:
        await db.execute("DELETE FROM settings WHERE user_id = ?", (user_id,))
    except Exception:
        pass

    try:
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    except Exception:
        pass

    await db.commit()

