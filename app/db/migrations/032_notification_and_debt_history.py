import aiosqlite


async def _ensure_column(
    db: aiosqlite.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    cur = await db.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in await cur.fetchall()}
    if column not in columns:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def apply(db: aiosqlite.Connection) -> None:
    for column, definition in (
        ("telegram_notifications_enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("push_notifications_enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("quiet_hours_enabled", "INTEGER NOT NULL DEFAULT 1"),
        ("quiet_hours_start", "TEXT NOT NULL DEFAULT '22:00'"),
        ("quiet_hours_end", "TEXT NOT NULL DEFAULT '08:00'"),
    ):
        await _ensure_column(db, "settings", column, definition)

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS debt_reminder_preferences (
          debt_id INTEGER PRIMARY KEY,
          user_id INTEGER NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          days_before INTEGER NOT NULL DEFAULT 3,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (debt_id) REFERENCES debts(id) ON DELETE CASCADE,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_debt_reminder_preferences_user "
        "ON debt_reminder_preferences(user_id)"
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS push_devices (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          token TEXT NOT NULL UNIQUE,
          platform TEXT NOT NULL,
          enabled INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_push_devices_user ON push_devices(user_id, enabled)"
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS planned_transactions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          kind TEXT NOT NULL,
          title TEXT NOT NULL,
          amount INTEGER NOT NULL,
          category_id INTEGER NOT NULL,
          account_id INTEGER NOT NULL,
          planned_date TEXT NOT NULL,
          comment TEXT,
          is_required INTEGER NOT NULL DEFAULT 1,
          last_reminded_on TEXT,
          is_archived INTEGER NOT NULL DEFAULT 0,
          done_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE RESTRICT,
          FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE RESTRICT
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_planned_user_arch_date "
        "ON planned_transactions(user_id, is_archived, planned_date)"
    )
