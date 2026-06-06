import aiosqlite

async def apply(db: aiosqlite.Connection) -> None:
    # 1. Add deposit and business columns to accounts
    for col, type_def in [
        ("acc_type", "TEXT DEFAULT 'regular'"),
        ("interest_rate", "REAL DEFAULT 0.0"),
        ("accrual_period", "TEXT DEFAULT 'month'"),
        ("last_interest_accrued_at", "TEXT"),
        ("is_business", "INTEGER DEFAULT 0"),
    ]:
        try:
            await db.execute(f"ALTER TABLE accounts ADD COLUMN {col} {type_def}")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                raise e

    # 2. Add business flag to categories
    try:
        await db.execute("ALTER TABLE categories ADD COLUMN is_business INTEGER DEFAULT 0")
    except Exception as e:
        if "duplicate column name" not in str(e).lower():
            raise e

    # 3. Add daily AI limits to settings
    for col, type_def in [
        ("ai_chat_daily_date", "TEXT"),
        ("ai_chat_daily_used", "INTEGER DEFAULT 0"),
    ]:
        try:
            await db.execute(f"ALTER TABLE settings ADD COLUMN {col} {type_def}")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                raise e

    # 4. Create exchange_rates table
    await db.execute("""
        CREATE TABLE IF NOT EXISTS exchange_rates (
            currency TEXT PRIMARY KEY,
            rate_to_usd REAL NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
