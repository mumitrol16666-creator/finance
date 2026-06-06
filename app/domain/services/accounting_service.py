from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import aiosqlite
from app.db.repositories.accounts_repo import get_account
from app.db.repositories.tx_repo import create_tx, apply_expense_income, create_transfer
from app.domain.validators import clean_note
from app.db.repositories.settings_repo import get_timezone
from app.db.repositories.limits_repo import get_daily_limit, today_expense_total
from app.db.repositories.users_repo import update_streak_on_activity

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _local_date_for_user(db: aiosqlite.Connection, user_id: int, ts_utc_iso: str) -> str:
    tz_name = await get_timezone(db, user_id)
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    dt_utc = datetime.fromisoformat(ts_utc_iso)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    local = dt_utc.astimezone(tz)
    return local.date().isoformat()


async def get_balance_after(db: aiosqlite.Connection, user_id: int, account_id: int, delta: int) -> tuple[int,int,str] | None:
    acc = await get_account(db, user_id, account_id)
    if not acc:
        return None
    name = acc['name']
    bal = int(acc['balance'])
    return bal, bal + delta, name

async def add_expense(db: aiosqlite.Connection, user_id: int, amount_positive: int, account_id: int, category_id: int, note: str | None, commit: bool = True):
    ts = utcnow_iso()
    note = clean_note(note)
    amount = -amount_positive
    tx_id = await create_tx(db, user_id, ts, "expense", amount, account_id, category_id, note, ts, None)
    await apply_expense_income(db, user_id, tx_id, amount, account_id)
    local_date = await _local_date_for_user(db, user_id, ts)
    await update_streak_on_activity(db, user_id, local_date)
    if commit:
        await db.commit()
    return tx_id

async def add_expense_v2(
    db: aiosqlite.Connection,
    user_id: int,
    amount_positive: int,
    account_id: int,
    category_id: int,
    note: str | None,
    commit: bool = True,
) -> tuple[int, dict]:
    """Expense with meta for daily limit + monthly category budget."""
    ts = utcnow_iso()

    # DAILY totals BEFORE applying
    daily_limit = await get_daily_limit(db, user_id)
    before_day_total = await today_expense_total(db, user_id) if daily_limit else 0

    # MONTHLY category totals BEFORE applying
    from app.db.repositories.budgets_repo import month_key as _month_key, get_category_budget, month_spent_by_category
    month = _month_key(datetime.fromisoformat(ts))
    cat_budget = await get_category_budget(db, user_id, month, category_id)
    before_cat_total = await month_spent_by_category(db, user_id, month, category_id) if cat_budget else 0

    tx_id = await add_expense(db, user_id, amount_positive, account_id, category_id, note, commit=commit)

    meta: dict = {}

    # daily limit meta
    if daily_limit:
        after_day_total = int(before_day_total) + int(amount_positive)
        if after_day_total >= int(daily_limit) * 125 // 100:
            st = "hard_over"
        elif after_day_total >= int(daily_limit):
            st = "over"
        elif after_day_total >= int(daily_limit) * 80 // 100:
            st = "warn"
        else:
            st = "ok"
        meta.update(
            {
                "daily_limit": int(daily_limit),
                "before_total": int(before_day_total),
                "after_total": int(after_day_total),
                "daily_state": st,
            }
        )

    # monthly category budget meta
    if cat_budget:
        after_cat_total = int(before_cat_total) + int(amount_positive)
        left = int(cat_budget) - after_cat_total

        if after_cat_total >= int(cat_budget) * 125 // 100:
            st = "hard_over"
        elif after_cat_total >= int(cat_budget):
            st = "over"
        elif after_cat_total >= int(cat_budget) * 80 // 100:
            st = "warn"
        else:
            st = "ok"

        meta.update(
            {
                "month": month,
                "cat_budget": int(cat_budget),
                "cat_before": int(before_cat_total),
                "cat_after": int(after_cat_total),
                "cat_left": int(left),
                "cat_state": st,
            }
        )

    return tx_id, meta


async def add_income(db: aiosqlite.Connection, user_id: int, amount_positive: int, account_id: int, category_id: int, note: str | None, commit: bool = True):
    ts = utcnow_iso()
    note = clean_note(note)
    amount = amount_positive
    tx_id = await create_tx(db, user_id, ts, "income", amount, account_id, category_id, note, ts, None)
    await apply_expense_income(db, user_id, tx_id, amount, account_id)
    local_date = await _local_date_for_user(db, user_id, ts)
    await update_streak_on_activity(db, user_id, local_date)
    if commit:
        await db.commit()
    return tx_id

async def add_transfer(db: aiosqlite.Connection, user_id: int, amount_positive: int, from_acc: int, to_acc: int, note: str | None, to_amount_positive: int | None = None):
    ts = utcnow_iso()
    tx1, tx2 = await create_transfer(db, user_id, ts, from_acc, to_acc, amount_positive, note, ts, to_amount_positive)
    local_date = await _local_date_for_user(db, user_id, ts)
    await update_streak_on_activity(db, user_id, local_date)
    await db.commit()
    return tx1, tx2
