from __future__ import annotations
from datetime import datetime, timezone
import aiosqlite
from app.db.repositories.users_repo import upsert_user, set_onboarded, set_newbie_defaults
from app.db.repositories.settings_repo import ensure_settings, update_currency, update_daily_report
from app.db.repositories.accounts_repo import create_account, count_accounts
from app.db.repositories.categories_repo import ensure_default_categories

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

async def init_user(db: aiosqlite.Connection, user_id: int, timezone_str: str):
    now = utcnow_iso()
    await upsert_user(db, user_id, now)
    await ensure_settings(db, user_id, now, timezone_str)
    await db.commit()

async def save_currency(db: aiosqlite.Connection, user_id: int, currency: str):
    now = utcnow_iso()
    await update_currency(db, user_id, currency, now)
    await db.commit()

async def add_account(db: aiosqlite.Connection, user_id: int, name: str, balance: int):
    now = utcnow_iso()
    acc_id = await create_account(db, user_id, name, balance, now)
    await db.commit()
    return acc_id

async def has_any_account(db: aiosqlite.Connection, user_id: int) -> bool:
    return (await count_accounts(db, user_id)) > 0

async def save_daily_report(db: aiosqlite.Connection, user_id: int, enabled: int, time_hhmm: str):
    now = utcnow_iso()
    await update_daily_report(db, user_id, enabled, time_hhmm, now)
    await db.commit()

async def finish_onboarding(db: aiosqlite.Connection, user_id: int):
    now = utcnow_iso()
    await ensure_default_categories(db, user_id, now)
    await set_onboarded(db, user_id, 1)
    await set_newbie_defaults(db, user_id)
    await db.commit()
