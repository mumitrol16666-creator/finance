from __future__ import annotations
import aiosqlite
import re
from loguru import logger

async def apply(db: aiosqlite.Connection) -> None:
    # 1. Disable foreign keys temporarily
    await db.execute("PRAGMA foreign_keys = OFF;")
    
    # Query all indexes before we touch any tables
    cur_idx = await db.execute("SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")
    indexes = await cur_idx.fetchall()
    
    # 2. Get list of tables and their SQL
    cur = await db.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")
    tables = await cur.fetchall()
    
    users_sql_row = [t for t in tables if t[0] == 'users']
    if not users_sql_row:
        # Fresh database, schema.py will define the tables
        await db.execute("PRAGMA foreign_keys = ON;")
        return
        
    # Check if 'users' already has 'id' column
    cur_info = await db.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in await cur_info.fetchall()}
    
    migrated_tables = set()
    
    if "id" not in cols:
        await db.execute("ALTER TABLE users RENAME TO users_old;")
        
        create_users_sql = """
        CREATE TABLE users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          telegram_id BIGINT UNIQUE,
          username VARCHAR UNIQUE NOT NULL,
          password_hash VARCHAR NOT NULL,
          display_name VARCHAR,
          onboarding_state VARCHAR,
          created_at TEXT NOT NULL,
          onboarded INTEGER NOT NULL DEFAULT 0,
          current_streak INTEGER NOT NULL DEFAULT 0,
          max_streak INTEGER NOT NULL DEFAULT 0,
          last_activity_date TEXT,
          mode TEXT NOT NULL DEFAULT 'newbie',
          progress_level INTEGER NOT NULL DEFAULT 0,
          full_access INTEGER NOT NULL DEFAULT 0,
          full_access_until TEXT,
          free_exports_used INTEGER NOT NULL DEFAULT 0,
          promo_used INTEGER NOT NULL DEFAULT 0,
          trial_3d_claimed INTEGER NOT NULL DEFAULT 0
        );
        """
        await db.execute(create_users_sql)
        
        # Copy data from users_old to users
        cur_old = await db.execute("PRAGMA table_info(users_old)")
        old_cols = {row[1] for row in await cur_old.fetchall()}
        
        name_col = "name" if "name" in old_cols else "NULL"
        
        await db.execute(f"""
            INSERT INTO users (
                id, telegram_id, username, password_hash, display_name, onboarding_state,
                created_at, onboarded, current_streak, max_streak, last_activity_date,
                mode, progress_level, full_access, full_access_until, free_exports_used, promo_used, trial_3d_claimed
            )
            SELECT 
                user_id, user_id, 'user_' || user_id, 'LEGACY_PLACEHOLDER', {name_col}, 'completed',
                created_at, onboarded, current_streak, max_streak, last_activity_date,
                mode, progress_level, full_access, full_access_until, free_exports_used, promo_used, COALESCE(trial_3d_claimed, 0)
            FROM users_old
        """)
        
        # Postpone dropping users_old until child tables are rewritten
        migrated_tables.add("users")
        logger.info("Users table successfully migrated to new unified schema")

    # Drop login_codes table if it exists (deprecated 6-digit codes)
    await db.execute("DROP TABLE IF EXISTS login_codes;")
    
    # 3. Dynamic foreign key rewrite for other tables referencing users(user_id)
    cur = await db.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL")
    tables = await cur.fetchall()
    
    old_tables_to_drop = []
    if "users" in migrated_tables:
        old_tables_to_drop.append("users_old")
    
    for name, sql in tables:
        if name in ('users', 'sqlite_sequence', 'migrations', 'login_codes') or name.endswith('_old'):
            continue
            
        pattern = r'references\s+["\']?(?:users|users_old)["\']?\s*\(\s*(?:user_id|id)\s*\)'
        if re.search(pattern, sql, re.IGNORECASE):
            logger.info(f"Rewriting foreign keys for table: {name}")
            
            # Rewrite references to REFERENCES users(id)
            new_sql = re.sub(
                pattern, 
                'REFERENCES users(id)', 
                sql, 
                flags=re.IGNORECASE
            )
            
            # Rename the old table
            await db.execute(f"ALTER TABLE `{name}` RENAME TO `{name}_old`;")
            
            # Create new table with updated FK constraint
            await db.execute(new_sql)
            
            # Copy all data from old to new
            cur_cols = await db.execute(f"PRAGMA table_info(`{name}_old`)")
            cols_list = [f"`{row[1]}`" for row in await cur_cols.fetchall()]
            cols_str = ", ".join(cols_list)
            
            await db.execute(f"INSERT INTO `{name}` ({cols_str}) SELECT {cols_str} FROM `{name}_old`")
            
            # Postpone drop
            old_tables_to_drop.append(f"{name}_old")
            migrated_tables.add(name)
            logger.info(f"Table {name} successfully updated to reference users(id)")

    # 4. Drop all old tables now that they are no longer referenced
    for old_tbl in old_tables_to_drop:
        try:
            await db.execute(f"DROP TABLE `{old_tbl}`;")
            logger.info(f"Dropped old table: {old_tbl}")
        except Exception as e:
            logger.warning(f"Could not drop old table {old_tbl}: {e}")

    # 4. Recreate any indexes for tables we migrated
    for idx_name, tbl_name, idx_sql in indexes:
        if tbl_name in migrated_tables:
            try:
                await db.execute(idx_sql)
                logger.info(f"Recreated index: {idx_name} on {tbl_name}")
            except Exception as e:
                logger.debug(f"Index {idx_name} on {tbl_name} recreate skipped or already exists: {e}")

    # 5. Re-enable foreign keys
    await db.execute("PRAGMA foreign_keys = ON;")
    await db.commit()
