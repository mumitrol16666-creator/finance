from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import aiosqlite
import hashlib
import hmac
import math
from datetime import datetime, timezone, date, timedelta
import calendar
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo

from app.config.settings import settings
from app.db.connection import get_db
from app.db.migrate import run_migrations
from app.db.repositories.users_repo import get_onboarded
from app.db.repositories.accounts_repo import list_accounts, apply_balance_delta, count_accounts
from app.db.repositories.categories_repo import list_categories
from app.db.repositories.tx_repo import create_tx, create_transfer
from app.domain.services.access_service import can_use_feature, get_user_context
from app.domain.auth import hash_password, verify_password
from app.domain.money import fmt_exchange_rate
from app.domain.validators import clean_name

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with get_db() as db:
        await run_migrations(db)
        # Perform database typo migrations
        await db.execute("UPDATE accounts SET name = 'Копилка' WHERE TRIM(name) = 'Копила'")
        await db.execute("UPDATE transactions SET note = 'Копилка' WHERE TRIM(note) = 'Копила'")
        await db.commit()
    yield

app = FastAPI(title="Finance Tracker API", lifespan=lifespan)

import time

origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = settings.secret_key.encode()
SUPPORTED_CURRENCIES = {"KZT", "USD", "EUR", "RUB"}


def normalize_currency(value: str | None, default: str = "KZT") -> str:
    code = (value or default).strip().upper()
    if code not in SUPPORTED_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported currency: {code}. Supported currencies: KZT, USD, EUR, RUB",
        )
    return code

def generate_token(user_id: int) -> str:
    # 90 days validity
    exp_timestamp = int(time.time()) + 90 * 24 * 3600
    msg = f"{user_id}.{exp_timestamp}".encode()
    sig = hmac.new(SECRET_KEY, msg, hashlib.sha256).hexdigest()
    return f"{user_id}.{exp_timestamp}.{sig}"

def verify_token(token: str) -> int | None:
    try:
        parts = token.split(".")
        if len(parts) == 3:
            user_id_str, exp_str, sig = parts
            user_id = int(user_id_str)
            exp_time = int(exp_str)
            if time.time() > exp_time:
                return None
            msg = f"{user_id}.{exp_time}".encode()
            expected_sig = hmac.new(SECRET_KEY, msg, hashlib.sha256).hexdigest()
            if hmac.compare_digest(sig, expected_sig):
                return user_id
    except Exception:
        pass
    return None

async def get_current_user(authorization: Optional[str] = Header(None)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token"
        )
    token = authorization.split(" ")[1]
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session"
        )
    return user_id

class RegisterRequest(BaseModel):
    display_name: str
    username: str
    password: str
    confirm_password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class ProfileUpdateRequest(BaseModel):
    name: str

class SettingsUpdateRequest(BaseModel):
    budget_cycle_start_day: Optional[int] = None
    currency: Optional[str] = None
    timezone: Optional[str] = None
    lang: Optional[str] = None
    telegram_notifications_enabled: Optional[bool] = None
    push_notifications_enabled: Optional[bool] = None
    daily_report_enabled: Optional[bool] = None
    daily_report_time: Optional[str] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    debts_enabled: Optional[bool] = None
    debts_days_before: Optional[int] = None

class CategoryUpdateRequest(BaseModel):
    name: Optional[str] = None
    emoji: Optional[str] = None
    limit_amount: Optional[int] = None
    default_account_id: Optional[int] = None
    exclude_from_analytics: Optional[int] = None
    warn_threshold: Optional[float] = None

def get_budget_cycle_bounds(ref_date: date, start_day: int) -> tuple[datetime, datetime, str]:
    # Returns (start_datetime_utc, end_datetime_utc, budget_month_str)
    # Clamp start_day to 1..28 (to avoid complications with February)
    start_day = max(1, min(start_day, 28))
    
    if ref_date.day >= start_day:
        start_date = date(ref_date.year, ref_date.month, start_day)
        if ref_date.month == 12:
            end_date = date(ref_date.year + 1, 1, start_day)
        else:
            end_date = date(ref_date.year, ref_date.month + 1, start_day)
    else:
        if ref_date.month == 1:
            start_date = date(ref_date.year - 1, 12, start_day)
        else:
            start_date = date(ref_date.year, ref_date.month - 1, start_day)
        end_date = date(ref_date.year, ref_date.month, start_day)
        
    start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=timezone.utc)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 0, 0, 0, tzinfo=timezone.utc)
    
    budget_month_str = start_date.strftime("%Y-%m")
    return start_dt, end_dt, budget_month_str

async def get_budget_cycle_start_day(db: aiosqlite.Connection, user_id: int) -> int:
    cur = await db.execute("SELECT budget_cycle_start_day FROM settings WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if row:
        return row[0]
    return 1

async def get_user_name(db: aiosqlite.Connection, user_id: int) -> str | None:
    cur = await db.execute("SELECT display_name FROM users WHERE id=?", (user_id,))
    row = await cur.fetchone()
    if row:
        return row[0]
    return None

async def sum_converted_amounts(
    db: aiosqlite.Connection,
    rows,
    base_currency: str,
) -> int:
    """Sum transaction rows converted from account currency into user's base currency."""
    from app.services.currency_service import get_exchange_rate

    total = 0
    for amount, currency in rows:
        rate = await get_exchange_rate(db, currency or base_currency, base_currency)
        total += int(round(int(amount or 0) * rate))
    return total

class TransactionCreateRequest(BaseModel):
    amount: int  # whole currency units
    kind: str  # 'expense', 'income', 'transfer'
    account_id: int
    category_id: Optional[int] = None
    note: Optional[str] = None
    to_account_id: Optional[int] = None  # for transfers
    date_override: Optional[str] = None  # YYYY-MM-DD override
    custom_rate: Optional[float] = None  # custom exchange rate for transfers

class TransactionUpdateRequest(BaseModel):
    amount: Optional[int] = None
    category_id: Optional[int] = None
    note: Optional[str] = None
    account_id: Optional[int] = None
    to_account_id: Optional[int] = None

class ChatRequest(BaseModel):
    text: str

class AccountCreateRequest(BaseModel):
    name: str
    balance: int
    currency: Optional[str] = "KZT"
    is_saving: Optional[int] = 0
    acc_type: Optional[str] = "regular"
    interest_rate: Optional[float] = 0.0
    accrual_period: Optional[str] = "month"
    is_business: Optional[int] = 0

class AccountUpdateRequest(BaseModel):
    name: Optional[str] = None
    balance: Optional[int] = None
    is_saving: Optional[int] = None
    is_archived: Optional[int] = None
    acc_type: Optional[str] = None
    interest_rate: Optional[float] = None
    accrual_period: Optional[str] = None
    is_business: Optional[int] = None
    currency: Optional[str] = None

class DebtCreateRequest(BaseModel):
    direction: str  # 'out' or 'in'
    dtype: str      # 'bank' or 'private'
    title: str
    payment_amount: Optional[int] = None
    next_payment_date: Optional[str] = None  # YYYY-MM-DD
    remaining_amount: int

class DebtPayRequest(BaseModel):
    payment_amount: int
    account_id: Optional[int] = None
    next_payment_date: Optional[str] = None

class DebtReminderRequest(BaseModel):
    enabled: bool = True
    days_before: int = 3

class PushDeviceRequest(BaseModel):
    token: str
    platform: str

class RecurringCreateRequest(BaseModel):
    title: str
    amount: int
    category_id: int
    account_id: int
    day_of_month: int
    kind: str  # 'expense' or 'income'
    comment: Optional[str] = None

class PlannedCreateRequest(BaseModel):
    title: str
    amount: int
    category_id: int
    account_id: int
    planned_date: str
    kind: str
    comment: Optional[str] = None
    is_required: Optional[int] = 1

class CategoryCreateRequest(BaseModel):
    name: str
    emoji: Optional[str] = "📦"
    kind: Optional[str] = "expense"
    is_business: Optional[bool] = False

    is_required: Optional[int] = 1

class BudgetUpsertRequest(BaseModel):
    category_id: int
    amount: int
    month: Optional[str] = None


def validate_hhmm(value: str, field_name: str) -> str:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must use HH:MM format") from exc
    return parsed.strftime("%H:%M")


@app.get("/health")
async def health():
    async with get_db() as db:
        cur = await db.execute("SELECT 1")
        await cur.fetchone()
    return {"status": "ok"}

@app.post("/api/auth/register")
async def register_user(req: RegisterRequest):
    display_name = req.display_name.strip()
    username = req.username.strip().lower()
    password = req.password
    confirm_password = req.confirm_password
    
    if not username:
        raise HTTPException(status_code=400, detail="Логин не может быть пустым")
    if not password:
        raise HTTPException(status_code=400, detail="Пароль не может быть пустым")
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Пароли не совпадают")
        
    import re
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        raise HTTPException(status_code=400, detail="Логин должен содержать только латинские буквы, цифры и подчеркивания")
        
    password_hash = hash_password(password)
    now_str = datetime.now(timezone.utc).isoformat()
    
    async with get_db() as db:
        cur = await db.execute("SELECT 1 FROM users WHERE LOWER(username) = ?", (username,))
        if await cur.fetchone():
            raise HTTPException(status_code=400, detail="Этот логин уже занят, попробуйте другой")
            
        try:
            cur = await db.execute(
                "INSERT INTO users (username, password_hash, display_name, onboarding_state, created_at, onboarded) "
                "VALUES (?, ?, ?, 'completed', ?, 1)",
                (username, password_hash, display_name, now_str)
            )
            user_id = cur.lastrowid
            
            await db.execute(
                "INSERT INTO settings (user_id, lang, currency, created_at, updated_at) VALUES (?, 'ru', 'KZT', ?, ?)",
                (user_id, now_str, now_str)
            )
            
            await db.execute(
                "INSERT INTO accounts (user_id, name, balance, starting_balance, currency, is_saving, is_archived, created_at, updated_at) "
                "VALUES (?, 'Основной', 0, 0, 'KZT', 0, 0, ?, ?)",
                (user_id, now_str, now_str)
            )
            
            from app.db.repositories.categories_repo import ensure_default_categories
            await ensure_default_categories(db, user_id, now_str)
            
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Ошибка при создании аккаунта: {e}")
            
        token = generate_token(user_id)
        return {"token": token, "user_id": user_id, "name": display_name}

@app.post("/api/auth/login")
async def login_user(req: LoginRequest):
    username = req.username.strip().lower()
    password = req.password
    
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, password_hash, display_name FROM users WHERE LOWER(username) = ? LIMIT 1",
            (username,)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Неверный логин или пароль")
            
        user_id, hashed_pass, display_name = row[0], row[1], row[2]
        
        # Hard check for password placeholder legacy security
        if hashed_pass == 'LEGACY_PLACEHOLDER':
            raise HTTPException(
                status_code=400,
                detail="Для входа в приложение установите пароль внутри Telegram-бота"
            )
            
        if not verify_password(password, hashed_pass):
            raise HTTPException(status_code=401, detail="Неверный логин или пароль")
            
        # Ensure settings exist
        cur_settings = await db.execute("SELECT 1 FROM settings WHERE user_id=?", (user_id,))
        if not await cur_settings.fetchone():
            now_str = datetime.now(timezone.utc).isoformat()
            await db.execute(
                "INSERT INTO settings (user_id, created_at, updated_at) VALUES (?, ?, ?)",
                (user_id, now_str, now_str)
            )
            await db.commit()
            
        token = generate_token(user_id)
        return {"token": token, "user_id": user_id, "name": display_name or username}

@app.get("/api/auth/check-username")
async def check_username(username: str):
    async with get_db() as db:
        cur = await db.execute("SELECT 1 FROM users WHERE LOWER(username) = ?", (username.strip().lower(),))
        row = await cur.fetchone()
        return {"available": row is None}

@app.get("/api/dashboard")
async def get_dashboard(
    ref_date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: int = Depends(get_current_user)
):
    now = datetime.now(timezone.utc)
    today = now.date()
    if ref_date:
        try:
            from datetime import date
            today = date.fromisoformat(ref_date)
        except Exception:
            pass
            
    is_custom_range = False
    custom_start_dt = None
    custom_end_dt = None
    custom_cycle_month_str = None
    
    if start_date and end_date:
        try:
            from datetime import date
            s_date = date.fromisoformat(start_date)
            e_date = date.fromisoformat(end_date)
            custom_start_dt = datetime(s_date.year, s_date.month, s_date.day, 0, 0, 0, tzinfo=timezone.utc)
            custom_end_dt = datetime(e_date.year, e_date.month, e_date.day, 0, 0, 0, tzinfo=timezone.utc) + timedelta(days=1)
            custom_cycle_month_str = f"{s_date.strftime('%d.%m.%y')} - {e_date.strftime('%d.%m.%y')}"
            is_custom_range = True
        except Exception:
            pass
    
    async with get_db() as db:
        from app.domain.services.access_service import get_user_context, get_available_features_from_context
        ctx = await get_user_context(db, user_id)
        available_features = list(get_available_features_from_context(ctx))

        cycle_start_day = await get_budget_cycle_start_day(db, user_id)
        if is_custom_range:
            start_dt, end_dt, cycle_month_str = custom_start_dt, custom_end_dt, custom_cycle_month_str
        else:
            # Get settings cycle start day
            start_dt, end_dt, cycle_month_str = get_budget_cycle_bounds(today, cycle_start_day)
            
        start_str = start_dt.isoformat()
        end_str = end_dt.isoformat()

        # 1. Accounts & balances
        from app.services.deposit_service import accrue_deposit_interests
        await accrue_deposit_interests(db, user_id)

        # Fetch user's base currency (used for balance conversions)
        cur_settings = await db.execute("SELECT currency FROM settings WHERE user_id=?", (user_id,))
        settings_row = await cur_settings.fetchone()
        base_currency = normalize_currency(settings_row[0] if settings_row else "KZT")

        accounts = await list_accounts(db, user_id)
        accounts_data = []
        total_balance = 0
        savings_balance = 0
        deposit_balance = 0
        
        from app.services.currency_service import get_exchange_rate
        for acc in accounts:
            rate = await get_exchange_rate(db, acc["currency"], base_currency)
            converted_balance = int(round(acc["balance"] * rate))
            
            accounts_data.append({
                "id": acc["id"],
                "name": acc["name"],
                "balance": acc["balance"],
                "currency": acc["currency"],
                "is_saving": bool(acc["is_saving"]),
                "acc_type": acc["acc_type"],
                "interest_rate": acc["interest_rate"],
                "accrual_period": acc["accrual_period"],
                "is_business": bool(acc["is_business"])
            })
            if acc["acc_type"] == 'deposit':
                deposit_balance += converted_balance
            elif acc["is_saving"]:
                savings_balance += converted_balance
            else:
                total_balance += converted_balance
            
        # 2. Monthly Expenses inside current cycle (with currency conversions)
        cur = await db.execute(
            "SELECT t.amount, a.currency FROM transactions t "
            "JOIN accounts a ON a.id = t.account_id "
            "LEFT JOIN categories c ON c.id = t.category_id "
            "WHERE t.user_id=? AND t.type='expense' AND t.deleted_at IS NULL AND t.ts >= ? AND t.ts < ? "
            "AND (c.exclude_from_analytics IS NULL OR c.exclude_from_analytics = 0)",
            (user_id, start_str, end_str)
        )
        expenses_rows = await cur.fetchall()
        monthly_expenses_row = await sum_converted_amounts(db, expenses_rows, base_currency)

        # 2b. Monthly Income inside current cycle (with currency conversions)
        cur_inc = await db.execute(
            "SELECT t.amount, a.currency FROM transactions t "
            "JOIN accounts a ON a.id = t.account_id "
            "LEFT JOIN categories c ON c.id = t.category_id "
            "WHERE t.user_id=? AND t.type='income' AND t.deleted_at IS NULL AND t.ts >= ? AND t.ts < ? "
            "AND (c.exclude_from_analytics IS NULL OR c.exclude_from_analytics = 0)",
            (user_id, start_str, end_str)
        )
        income_rows = await cur_inc.fetchall()
        monthly_income_row = await sum_converted_amounts(db, income_rows, base_currency)
        
        # 3. Weekly streak (Monday to Sunday)
        start_of_week = today - timedelta(days=today.weekday())
        weekly_streak = []
        for i in range(7):
            day = start_of_week + timedelta(days=i)
            day_str = day.strftime("%Y-%m-%d")
            # check if there was any transaction
            cur_tx = await db.execute(
                "SELECT 1 FROM transactions WHERE user_id=? AND deleted_at IS NULL AND date(ts)=? LIMIT 1",
                (user_id, day_str)
            )
            had_tx = await cur_tx.fetchone() is not None
            weekly_streak.append(had_tx)
            
        # 4. Recent Transactions (last 10)
        cur = await db.execute(
            "SELECT t.id, t.ts, t.type, t.amount, "
            "       a.name as account_name, a.currency as account_currency, "
            "       dest_a.name as dest_account_name, "
            "       c.name as category_name, "
            "       c.emoji as category_emoji, "
            "       t.note "
            "FROM transactions t "
            "JOIN accounts a ON a.id=t.account_id "
            "LEFT JOIN transactions dest_t ON dest_t.id=t.related_tx_id AND t.type='transfer' "
            "LEFT JOIN accounts dest_a ON dest_a.id=dest_t.account_id "
            "LEFT JOIN categories c ON c.id=t.category_id "
            "WHERE t.user_id=? AND t.deleted_at IS NULL AND (t.type != 'transfer' OR t.amount < 0) "
            "ORDER BY t.ts DESC, t.id DESC LIMIT 10",
            (user_id,)
        )
        recent_tx = []
        for row in await cur.fetchall():
            recent_tx.append({
                "id": row["id"],
                "ts": row["ts"],
                "type": row["type"],
                "amount": abs(row["amount"]),
                "accountName": row["account_name"] if row["type"] != "transfer" else f"{row['account_name']} ➡️ {row['dest_account_name']}",
                "categoryName": row["category_name"] or ("Перевод в копилку" if row["type"] == "transfer" and row["dest_account_name"] and "копил" in row["dest_account_name"].lower() else ("Перевод" if row["type"] == "transfer" else "Прочее")),
                "categoryEmoji": row["category_emoji"] or ("🔁" if row["type"] == "transfer" else "📦"),
                "note": row["note"],
                "currency": row["account_currency"]
            })
            
        # 5. Categories progress (limit vs spent) for both expenses and incomes
        expense_cats = await list_categories(db, user_id, "expense")
        income_cats = await list_categories(db, user_id, "income")
        categories_data = []
        
        for cat in expense_cats:
            cur_spent = await db.execute(
                "SELECT t.amount, a.currency FROM transactions t "
                "JOIN accounts a ON a.id = t.account_id "
                "WHERE t.user_id=? AND t.category_id=? AND t.type='expense' AND t.deleted_at IS NULL AND t.ts >= ? AND t.ts < ?",
                (user_id, cat["id"], start_str, end_str)
            )
            spent_val = await sum_converted_amounts(db, await cur_spent.fetchall(), base_currency)
            
            cur_limit = await db.execute(
                "SELECT limit_amount FROM budgets WHERE user_id=? AND category_id=? AND month=?",
                (user_id, cat["id"], cycle_month_str)
            )
            limit_row = await cur_limit.fetchone()
            limit_amount = limit_row[0] if limit_row else 0
            
            categories_data.append({
                "id": cat["id"],
                "name": cat["name"],
                "emoji": cat["emoji"],
                "kind": "expense",
                "limitAmount": limit_amount,
                "spentAmount": abs(spent_val),
                "defaultAccountId": cat["default_account_id"],
                "excludeFromAnalytics": bool(cat["exclude_from_analytics"]),
                "warnThreshold": cat["warn_threshold"] if cat["warn_threshold"] is not None else 0.70,
                "is_business": bool(cat["is_business"])
            })
            
        for cat in income_cats:
            cur_earned = await db.execute(
                "SELECT t.amount, a.currency FROM transactions t "
                "JOIN accounts a ON a.id = t.account_id "
                "WHERE t.user_id=? AND t.category_id=? AND t.type='income' AND t.deleted_at IS NULL AND t.ts >= ? AND t.ts < ?",
                (user_id, cat["id"], start_str, end_str)
            )
            earned_val = await sum_converted_amounts(db, await cur_earned.fetchall(), base_currency)
            
            categories_data.append({
                "id": cat["id"],
                "name": cat["name"],
                "emoji": cat["emoji"],
                "kind": "income",
                "limitAmount": 0,
                "spentAmount": abs(earned_val),
                "defaultAccountId": cat["default_account_id"],
                "excludeFromAnalytics": bool(cat["exclude_from_analytics"]),
                "warnThreshold": cat["warn_threshold"] if cat["warn_threshold"] is not None else 0.70,
                "is_business": bool(cat["is_business"])
            })

        # Calculate active days count in current cycle
        cur_active_days = await db.execute(
            "SELECT COUNT(DISTINCT date(ts)) FROM transactions "
            "WHERE user_id=? AND deleted_at IS NULL AND ts >= ? AND ts < ?",
            (user_id, start_str, end_str)
        )
        active_days_count = (await cur_active_days.fetchone())[0]
        total_cycle_days = (end_dt - start_dt).days

        from app.services.currency_service import get_rates_snapshot
        exchange_rates_data, rates_updated_at = await get_rates_snapshot(db)

        return {
            "totalBalance": total_balance,
            "savingsBalance": savings_balance,
            "depositBalance": deposit_balance,
            "monthlyExpenses": abs(monthly_expenses_row),
            "cycleIncome": abs(monthly_income_row),
            "cycleExpenses": abs(monthly_expenses_row),
            "activeDaysCount": active_days_count,
            "totalCycleDays": total_cycle_days,
            "cycleStart": start_dt.strftime("%Y-%m-%d"),
            "cycleEnd": end_dt.strftime("%Y-%m-%d"),
            "weeklyStreak": weekly_streak,
            "accounts": accounts_data,
            "recentTransactions": recent_tx,
            "categories": categories_data,
            "isPremium": ctx.mode == "full",
            "premiumExpirationDate": ctx.expiration_date,
            "availableFeatures": available_features,
            "progressLevel": ctx.progress_level,
            "currentStreak": ctx.current_streak,
            "maxStreak": ctx.max_streak,
            "userName": await get_user_name(db, user_id),
            "budgetCycleStartDay": cycle_start_day,
            "baseCurrency": base_currency,
            "exchangeRates": {
                "base": "USD",
                "rates": exchange_rates_data,
                "updated_at": rates_updated_at
            }
        }

@app.get("/api/exchange-rates")
async def get_exchange_rates(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        from app.services.currency_service import get_rates_snapshot
        rates, updated_at = await get_rates_snapshot(db)

        return {
            "base": "USD",
            "rates": rates,
            "updated_at": updated_at
        }

@app.get("/api/accounts")
async def get_accounts(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        from app.services.deposit_service import accrue_deposit_interests
        await accrue_deposit_interests(db, user_id)
        accounts = await list_accounts(db, user_id)
        return [{
            "id": acc["id"],
            "name": acc["name"],
            "balance": acc["balance"],
            "currency": acc["currency"],
            "is_saving": bool(acc["is_saving"]),
            "acc_type": acc["acc_type"],
            "interest_rate": acc["interest_rate"],
            "accrual_period": acc["accrual_period"],
            "is_business": bool(acc["is_business"])
        } for acc in accounts]

@app.get("/api/categories")
async def get_categories(kind: str = "expense", user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        categories = await list_categories(db, user_id, kind)
        return [{
            "id": cat["id"],
            "name": cat["name"],
            "emoji": cat["emoji"],
            "is_business": bool(cat["is_business"])
        } for cat in categories]

@app.post("/api/categories")
async def add_category(req: CategoryCreateRequest, user_id: int = Depends(get_current_user)):
    now_str = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        from app.db.repositories.categories_repo import create_category, name_exists_any_kind
        if await name_exists_any_kind(db, user_id, req.name):
            raise HTTPException(status_code=400, detail="Категория с таким именем уже существует")
        cat_id = await create_category(db, user_id, req.name, req.emoji, req.kind, now_str, 1 if req.is_business else 0)
        await db.commit()
        return {"status": "created", "id": cat_id}

@app.delete("/api/categories/{category_id}")
async def delete_category(category_id: int, user_id: int = Depends(get_current_user)):
    now_str = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        from app.db.repositories.categories_repo import archive_category
        await archive_category(db, user_id, category_id, now_str)
        await db.commit()
        return {"status": "deleted"}


@app.post("/api/transactions")
async def add_transaction(req: TransactionCreateRequest, user_id: int = Depends(get_current_user)):
    now_str = datetime.now(timezone.utc).isoformat()
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    if req.kind not in {"expense", "income", "transfer"}:
        raise HTTPException(status_code=400, detail="Unsupported transaction kind")
    if req.custom_rate is not None and (not math.isfinite(req.custom_rate) or req.custom_rate <= 0):
        raise HTTPException(status_code=400, detail="Custom exchange rate must be greater than zero")

    async with get_db() as db:
        from app.db.repositories.accounts_repo import get_account
        from_acc_row = await get_account(db, user_id, req.account_id)
        if not from_acc_row or from_acc_row[3]:
            raise HTTPException(status_code=404, detail="Account not found")

        if req.category_id is not None:
            from app.db.repositories.categories_repo import get_category
            if not await get_category(db, user_id, req.category_id):
                raise HTTPException(status_code=404, detail="Category not found")

        if req.kind == "transfer":
            if not await can_use_feature(db, user_id, "transfer"):
                raise HTTPException(status_code=403, detail="Функция перевода доступна только в Premium версии")
            if not req.to_account_id:
                raise HTTPException(status_code=400, detail="to_account_id is required for transfers")
            if req.account_id == req.to_account_id:
                raise HTTPException(status_code=400, detail="Source and destination accounts must be different")

            # Currency exchange logic
            to_acc_row = await get_account(db, user_id, req.to_account_id)
            if not to_acc_row or to_acc_row[3]:
                raise HTTPException(status_code=404, detail="Счёт не найден")

            from_curr = normalize_currency(from_acc_row[4])  # currency is index 4
            to_curr = normalize_currency(to_acc_row[4])

            ctx = await get_user_context(db, user_id)
            if (from_curr != to_curr or from_curr != "KZT" or to_curr != "KZT") and ctx.mode != "full":
                raise HTTPException(
                    status_code=403,
                    detail="Мультивалютные переводы доступны только в Premium версии"
                )

            if from_curr != to_curr:
                if req.custom_rate is not None and req.custom_rate > 0:
                    rate = req.custom_rate
                else:
                    from app.services.currency_service import get_exchange_rate
                    rate = await get_exchange_rate(db, from_curr, to_curr)
                to_amount = int(round(req.amount * rate))
                conversion_note = f"{req.note or ''} (Курс: {fmt_exchange_rate(from_curr, to_curr, rate)})".strip()
            else:
                to_amount = req.amount
                conversion_note = req.note

            await create_transfer(
                db, user_id, now_str, req.account_id, req.to_account_id, req.amount, conversion_note, now_str, to_amount
            )
        else:
            amount_val = -req.amount if req.kind == "expense" else req.amount
            await create_tx(
                db, user_id, now_str, req.kind, amount_val, req.account_id, req.category_id, req.note, now_str
            )
            await apply_balance_delta(db, user_id, req.account_id, amount_val)
            await db.commit()
            
        return {"status": "success"}

@app.delete("/api/transactions/{tx_id}")
async def delete_transaction_endpoint(tx_id: int, user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        from app.db.repositories.tx_repo import delete_tx
        success, msg = await delete_tx(db, user_id, tx_id)
        if not success:
            raise HTTPException(status_code=400, detail=msg)
        return {"status": "success"}

@app.put("/api/transactions/{tx_id}")
async def update_transaction_endpoint(tx_id: int, req: TransactionUpdateRequest, user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        from app.db.repositories.tx_repo import update_tx
        success = await update_tx(
            db, user_id, tx_id,
            new_amount=req.amount,
            new_category_id=req.category_id,
            new_note=req.note,
            new_account_id=req.account_id,
            new_to_account_id=req.to_account_id
        )
        if not success:
            raise HTTPException(status_code=400, detail="Failed to update transaction")
        return {"status": "success"}


@app.get("/api/debts")
async def get_debts(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "debts"):
            raise HTTPException(status_code=403, detail="Функция долгов доступна только в Premium версии")
        cur = await db.execute(
            "SELECT d.id, d.direction, d.dtype, d.title, d.total_amount, d.remaining_amount, "
            "d.payment_amount, d.next_payment_date, d.note, d.status, d.is_active, "
            "COALESCE(r.enabled, 1) AS reminder_enabled, COALESCE(r.days_before, 3) AS reminder_days_before "
            "FROM debts d LEFT JOIN debt_reminder_preferences r ON r.debt_id=d.id AND r.user_id=d.user_id "
            "WHERE d.user_id=? AND d.is_active=1 ORDER BY d.id DESC",
            (user_id,)
        )
        debts = []
        for row in await cur.fetchall():
            debts.append({
                "id": row["id"],
                "direction": row["direction"],
                "dtype": row["dtype"],
                "title": row["title"],
                "totalAmount": row["total_amount"],
                "remainingAmount": row["remaining_amount"],
                "paymentAmount": row["payment_amount"],
                "nextPaymentDate": row["next_payment_date"],
                "note": row["note"],
                "status": row["status"],
                "reminderEnabled": bool(row["reminder_enabled"]),
                "reminderDaysBefore": row["reminder_days_before"],
            })
        return debts

@app.get("/api/recurring")
async def get_recurring(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "recurring"):
            raise HTTPException(status_code=403, detail="Регулярные платежи доступны только в Premium версии")
        # Get recurring expenses
        cur_exp = await db.execute(
            "SELECT r.id, r.title, r.amount, 'expense' as kind, r.day_of_month, r.next_run_date, c.emoji as category_emoji, "
            "r.account_id, a.currency "
            "FROM recurring_expenses r "
            "LEFT JOIN categories c ON c.id = r.category_id "
            "LEFT JOIN accounts a ON a.id = r.account_id "
            "WHERE r.user_id=? AND r.is_archived=0 ORDER BY r.id DESC",
            (user_id,)
        )
        rows_exp = await cur_exp.fetchall()
        
        # Get recurring incomes
        cur_inc = await db.execute(
            "SELECT r.id, r.title, r.amount, 'income' as kind, r.day_of_month, r.next_run_date, c.emoji as category_emoji, "
            "r.account_id, a.currency "
            "FROM recurring_incomes r "
            "LEFT JOIN categories c ON c.id = r.category_id "
            "LEFT JOIN accounts a ON a.id = r.account_id "
            "WHERE r.user_id=? AND r.is_archived=0 ORDER BY r.id DESC",
            (user_id,)
        )
        rows_inc = await cur_inc.fetchall()
        
        recurring = []
        for row in rows_exp + rows_inc:
            recurring.append({
                "id": row["id"],
                "name": row["title"],
                "amount": row["amount"],
                "kind": row["kind"],
                "intervalType": "monthly",
                "intervalValue": row["day_of_month"],
                "nextRunDate": row["next_run_date"],
                "categoryEmoji": row["category_emoji"] or "🔁",
                "accountId": row["account_id"],
                "currency": normalize_currency(row["currency"])
            })
        return recurring

@app.get("/api/planned")
async def get_planned(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "planned"):
            raise HTTPException(status_code=403, detail="Планируемые операции доступны только в Premium версии")
        cur = await db.execute(
            "SELECT p.id, p.title, p.amount, p.planned_date, p.kind, c.emoji as category_emoji, "
            "p.account_id, a.currency "
            "FROM planned_transactions p "
            "LEFT JOIN categories c ON c.id=p.category_id "
            "LEFT JOIN accounts a ON a.id=p.account_id "
            "WHERE p.user_id=? AND p.is_archived=0 ORDER BY p.planned_date ASC",
            (user_id,)
        )
        planned = []
        for row in await cur.fetchall():
            planned.append({
                "id": row["id"],
                "title": row["title"],
                "amount": row["amount"],
                "date": row["planned_date"],
                "kind": row["kind"],
                "status": "pending",
                "categoryEmoji": row["category_emoji"] or "📅",
                "accountId": row["account_id"],
                "currency": normalize_currency(row["currency"])
            })
        return planned

@app.post("/api/chat")
async def chat_with_ai(req: ChatRequest, user_id: int = Depends(get_current_user)):
    text = req.text
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "ai"):
            raise HTTPException(status_code=403, detail="ИИ-консультант доступен только в Premium версии")
        
        # Check daily limit for non-premium users
        from app.domain.services.access_service import get_user_context
        ctx = await get_user_context(db, user_id)
        if ctx.mode != "full":
            from datetime import date
            today_str = date.today().isoformat()
            
            # Fetch daily AI chat usage
            cur = await db.execute("SELECT ai_chat_daily_date, ai_chat_daily_used FROM settings WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
            if row:
                daily_date, daily_used = row
                daily_used = daily_used or 0
            else:
                daily_date, daily_used = None, 0
                
            if daily_date == today_str:
                if daily_used >= 50:
                    raise HTTPException(
                        status_code=429,
                        detail="Вы превысили дневной лимит в 50 сообщений ИИ. Перейдите на Premium, чтобы снять ограничения."
                    )
                new_used = daily_used + 1
            else:
                new_used = 1
                
            # Update settings
            await db.execute(
                "UPDATE settings SET ai_chat_daily_date=?, ai_chat_daily_used=?, updated_at=? WHERE user_id=?",
                (today_str, new_used, datetime.now(timezone.utc).isoformat(), user_id)
            )
            await db.commit()

        try:
            from app.domain.services.ai_llm_service import chat_with_user_ai
            response = await chat_with_user_ai(db, user_id, text)
            return {"text": response}
        except Exception:
            return {"text": "В данный момент ИИ-консультант временно недоступен. Попробуйте позже."}

@app.get("/api/analytics")
async def get_analytics(user_id: int = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    current_month_str = now.strftime("%Y-%m")
    async with get_db() as db:
        cur_settings = await db.execute("SELECT currency FROM settings WHERE user_id=?", (user_id,))
        settings_row = await cur_settings.fetchone()
        base_currency = normalize_currency(settings_row[0] if settings_row else "KZT")

        cur = await db.execute(
            "SELECT c.id, c.name, c.emoji, t.amount, a.currency "
            "FROM transactions t "
            "JOIN categories c ON c.id=t.category_id "
            "JOIN accounts a ON a.id=t.account_id "
            "WHERE t.user_id=? AND t.type='expense' AND t.deleted_at IS NULL AND strftime('%Y-%m', t.ts)=? ",
            (user_id, current_month_str)
        )
        grouped: dict[int, dict] = {}
        for row in await cur.fetchall():
            item = grouped.setdefault(row["id"], {
                "categoryName": row["name"],
                "categoryEmoji": row["emoji"],
                "amount": 0,
            })
            converted = await sum_converted_amounts(db, [(row["amount"], row["currency"])], base_currency)
            item["amount"] += abs(converted)

        chart_data = []
        for item in grouped.values():
            chart_data.append({
                "categoryName": item["categoryName"],
                "categoryEmoji": item["categoryEmoji"],
                "amount": item["amount"],
            })
        return {
            "month": current_month_str,
            "baseCurrency": base_currency,
            "chartData": chart_data
        }

@app.post("/api/analytics/ai-audit")
async def post_analytics_audit(
    ref_date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: int = Depends(get_current_user)
):
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "ai"):
            raise HTTPException(status_code=403, detail="ИИ-аудит доступен только в Premium версии")
        try:
            from app.db.repositories.settings_repo import get_timezone, get_financial_goal
            from app.domain.services.ai_consultant_service import build_ai_context
            from app.domain.services.ai_llm_service import render_final_ai_question
            import re
            
            tz_name = await get_timezone(db, user_id)
            goal = await get_financial_goal(db, user_id)
            
            ref_dt = None
            if ref_date:
                try:
                    from datetime import date, datetime
                    parsed_date = date.fromisoformat(ref_date)
                    ref_dt = datetime(parsed_date.year, parsed_date.month, parsed_date.day, 12, 0, 0, tzinfo=timezone.utc)
                except Exception:
                    pass
            
            custom_start_dt = None
            custom_end_dt = None
            if start_date and end_date:
                try:
                    from datetime import date, datetime
                    s_date = date.fromisoformat(start_date)
                    e_date = date.fromisoformat(end_date)
                    custom_start_dt = datetime(s_date.year, s_date.month, s_date.day, 0, 0, 0, tzinfo=timezone.utc)
                    custom_end_dt = datetime(e_date.year, e_date.month, e_date.day, 0, 0, 0, tzinfo=timezone.utc) + timedelta(days=1)
                except Exception:
                    pass
                    
            context = await build_ai_context(
                db, user_id, tz_name, "month", goal, 
                ref_dt=ref_dt, 
                start_dt=custom_start_dt, 
                end_dt=custom_end_dt
            )
            
            audit_prompt = (
                "Проанализируй мои финансовые показатели за текущий месяц. "
                "Дай очень краткий (3-4 предложения), конкретный и практичный аудит моих расходов, "
                "сбережений и лимитов. Укажи на аномалии или дай совет по оптимизации."
            )
            
            raw_response = await render_final_ai_question(context, audit_prompt, chat_history=None)
            clean_response = re.sub(r"<[^>]+>", "", raw_response).strip()
            return {"audit": clean_response}
        except Exception as e:
            logger.exception(f"Failed to generate AI analytics audit: {e}")
            return {"audit": "В данный момент ИИ-аудит временно недоступен. Попробуйте обновить позже."}

@app.post("/api/accounts")
async def add_account(req: AccountCreateRequest, user_id: int = Depends(get_current_user)):
    now_str = datetime.now(timezone.utc).isoformat()
    currency = normalize_currency(req.currency)
    name = clean_name(req.name)
    is_saving = req.is_saving if req.is_saving is not None else 0
    acc_type = req.acc_type or "regular"
    interest_rate = req.interest_rate if req.interest_rate is not None else 0.0
    accrual_period = req.accrual_period or "month"
    is_business = req.is_business if req.is_business is not None else 0

    if not name:
        raise HTTPException(status_code=400, detail="Название должно быть от 2 до 24 символов")
    if is_saving not in (0, 1):
        raise HTTPException(status_code=400, detail="is_saving must be 0 or 1")
    if is_business not in (0, 1):
        raise HTTPException(status_code=400, detail="is_business must be 0 or 1")
    if acc_type not in {"regular", "saving", "deposit"}:
        raise HTTPException(status_code=400, detail="Unsupported account type")
    if accrual_period not in {"month", "year"}:
        raise HTTPException(status_code=400, detail="Unsupported accrual period")
    if not math.isfinite(interest_rate) or interest_rate < 0:
        raise HTTPException(status_code=400, detail="interest_rate must be non-negative")

    async with get_db() as db:
        # Check premium logic for non-KZT currency
        ctx = await get_user_context(db, user_id)
        if ctx.mode != "full" and await count_accounts(db, user_id) >= 2:
            raise HTTPException(
                status_code=403,
                detail="В бесплатной версии доступно не более 2 активных счетов"
            )
        if currency != "KZT" and ctx.mode != "full":
            raise HTTPException(
                status_code=403,
                detail="Создание валютных счетов доступно только в Premium версии"
            )

        try:
            from app.db.repositories.accounts_repo import create_account
            acc_id, status = await create_account(
                db, user_id, name, req.balance, now_str,
                currency=currency,
                is_saving=is_saving,
                acc_type=acc_type,
                interest_rate=interest_rate,
                accrual_period=accrual_period,
                is_business=is_business
            )
            await db.commit()
            return {"status": status, "id": acc_id}
        except ValueError as e:
            if str(e) == 'active_name_exists':
                raise HTTPException(status_code=400, detail="Счёт с таким именем уже существует")
            if str(e) == 'archived_name_exists':
                raise HTTPException(status_code=400, detail="Счёт с таким именем уже есть в архиве и содержит историю. Восстановите его из архива или выберите другое название")
            raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/debts")
async def add_debt_endpoint(req: DebtCreateRequest, user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "debts"):
            raise HTTPException(status_code=403, detail="Функция долгов доступна только в Premium версии")
        if req.direction not in {"in", "out"} or req.dtype not in {"bank", "private"}:
            raise HTTPException(status_code=400, detail="Unsupported debt type")
        if not req.title.strip() or req.remaining_amount <= 0:
            raise HTTPException(status_code=400, detail="Debt title and positive amount are required")
        if req.payment_amount is not None and req.payment_amount <= 0:
            raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")
        from app.db.repositories.debts_repo import add_debt
        debt_id = await add_debt(
            db, user_id, req.direction, req.dtype, req.title,
            req.payment_amount, req.next_payment_date, req.remaining_amount
        )
        return {"status": "success", "id": debt_id}

@app.post("/api/debts/{debt_id}/pay")
async def pay_debt_endpoint(debt_id: int, req: DebtPayRequest, user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "debts"):
            raise HTTPException(status_code=403, detail="Функция долгов доступна только в Premium версии")
        if req.payment_amount <= 0:
            raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")

        cur_debt = await db.execute(
            "SELECT * FROM debts WHERE id=? AND user_id=? AND is_active=1",
            (debt_id, user_id),
        )
        row = await cur_debt.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Active debt not found")
        remaining_amount = int(row["remaining_amount"] or 0)
        if remaining_amount <= 0:
            raise HTTPException(status_code=400, detail="Debt has no remaining balance")
        debt_payment_amount = min(req.payment_amount, remaining_amount)

        transaction_amount = debt_payment_amount
        if req.account_id is not None:
            from app.db.repositories.accounts_repo import get_account
            account = await get_account(db, user_id, req.account_id)
            if not account or int(account[3] or 0) == 1:
                raise HTTPException(status_code=404, detail="Active account not found")

            cur_settings = await db.execute("SELECT currency FROM settings WHERE user_id=?", (user_id,))
            settings_row = await cur_settings.fetchone()
            base_currency = normalize_currency(settings_row[0] if settings_row else "KZT")
            account_currency = normalize_currency(account[4])
            from app.services.currency_service import get_exchange_rate
            rate = await get_exchange_rate(db, base_currency, account_currency)
            transaction_amount = max(1, int(round(debt_payment_amount * rate)))
        
        await db.execute("BEGIN IMMEDIATE")
        try:
            payment_tx_id = None
            if req.account_id is not None:
                if row:
                    if hasattr(row, "keys"):
                        debt = {k: row[k] for k in row.keys()}
                    else:
                        debt = {
                            "id": row[0],
                            "title": row[1],
                            "payment_amount": row[2],
                            "next_payment_date": row[3],
                            "remaining_amount": row[4],
                            "dtype": row[5],
                            "direction": row[6],
                            "is_active": row[7],
                            "status": row[8],
                        }
                    
                    direction = debt["direction"]
                    dtype = debt["dtype"]
                    title = debt["title"]
                    amount = transaction_amount

                    async def ensure_category(db_conn, u_id, kind, name, emoji):
                        cur = await db_conn.execute(
                            "SELECT id FROM categories WHERE user_id = ? AND kind = ? AND name = ?",
                            (u_id, kind, name),
                        )
                        r = await cur.fetchone()
                        if r:
                            return int(r["id"] if hasattr(r, "keys") else r[0])

                        cur = await db_conn.execute(
                            """
                            INSERT INTO categories (
                                user_id, name, emoji, kind, is_archived, created_at, updated_at
                            )
                            VALUES (?, ?, ?, ?, 0, datetime('now'), datetime('now'))
                            """,
                            (u_id, name, emoji, kind),
                        )
                        return int(cur.lastrowid)

                    if direction == "out":
                        category_id = await ensure_category(
                            db, user_id, kind="expense",
                            name="Платёж по кредиту" if dtype == "bank" else "Возврат долга",
                            emoji="💳" if dtype == "bank" else "📤"
                        )
                        note = f"Платёж по кредиту: {title}" if dtype == "bank" else f"Возврат долга: {title}"
                        from app.domain.services.accounting_service import add_expense
                        payment_tx_id = await add_expense(db, user_id, amount, req.account_id, category_id, note, commit=False)
                    else:
                        category_id = await ensure_category(
                            db, user_id, kind="income",
                            name="Мне вернули долг",
                            emoji="📥"
                        )
                        note = f"Мне вернули долг: {title}"
                        from app.domain.services.accounting_service import add_income
                        payment_tx_id = await add_income(db, user_id, amount, req.account_id, category_id, note, commit=False)

            from app.db.repositories.debts_repo import apply_debt_payment, add_debt_payment_history
            await apply_debt_payment(
                db, user_id, debt_id, debt_payment_amount, req.next_payment_date, commit=False
            )
            await add_debt_payment_history(
                db,
                user_id,
                debt_id,
                debt_payment_amount,
                tx_id=payment_tx_id,
                account_id=req.account_id,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return {"status": "success"}

@app.get("/api/debts/{debt_id}/payments")
async def get_debt_payments_endpoint(debt_id: int, user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        cur = await db.execute("SELECT 1 FROM debts WHERE id=? AND user_id=?", (debt_id, user_id))
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Debt not found")
        from app.db.repositories.debts_repo import list_debt_payments
        rows = await list_debt_payments(db, user_id, debt_id)
        return [
            {
                "id": row["id"],
                "debtId": row["debt_id"],
                "transactionId": row["tx_id"],
                "accountId": row["account_id"],
                "amount": row["amount"],
                "paymentDate": row["payment_date"],
                "comment": row["comment"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

@app.post("/api/debts/{debt_id}/reminder")
async def update_debt_reminder_endpoint(
    debt_id: int,
    req: DebtReminderRequest,
    user_id: int = Depends(get_current_user),
):
    if req.days_before < 0 or req.days_before > 30:
        raise HTTPException(status_code=400, detail="days_before must be between 0 and 30")
    async with get_db() as db:
        cur = await db.execute(
            "SELECT 1 FROM debts WHERE id=? AND user_id=? AND is_active=1",
            (debt_id, user_id),
        )
        if not await cur.fetchone():
            raise HTTPException(status_code=404, detail="Active debt not found")
        from app.db.repositories.debts_repo import set_debt_reminder_preference
        await set_debt_reminder_preference(db, user_id, debt_id, int(req.enabled), req.days_before)
        await db.commit()
    return {"status": "success", "enabled": req.enabled, "daysBefore": req.days_before}

@app.post("/api/recurring")
async def add_recurring_endpoint(req: RecurringCreateRequest, user_id: int = Depends(get_current_user)):
    now_str = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "recurring"):
            raise HTTPException(status_code=403, detail="Регулярные платежи доступны только в Premium версии")
        if req.amount <= 0 or req.kind not in {"expense", "income"} or not 1 <= req.day_of_month <= 31:
            raise HTTPException(status_code=400, detail="Invalid recurring payment data")
        from app.db.repositories.accounts_repo import get_account
        from app.db.repositories.categories_repo import get_category
        account = await get_account(db, user_id, req.account_id)
        category = await get_category(db, user_id, req.category_id)
        if not account or int(account[3] or 0) == 1:
            raise HTTPException(status_code=404, detail="Active account not found")
        if not category or int(category[4] or 0) == 1 or category[3] != req.kind:
            raise HTTPException(status_code=404, detail="Active category for operation kind not found")
        from app.db.repositories.recurring_repo import create_recurring_expense, create_recurring_income
        if req.kind == "expense":
            item_id = await create_recurring_expense(
                db, user_id, req.title, req.amount, req.category_id, req.account_id, req.day_of_month, req.comment, now_str
            )
        else:
            item_id = await create_recurring_income(
                db, user_id, req.title, req.amount, req.category_id, req.account_id, req.day_of_month, req.comment, now_str
            )
        await db.commit()
        return {"status": "success", "id": item_id}

@app.post("/api/planned")
async def add_planned_endpoint(req: PlannedCreateRequest, user_id: int = Depends(get_current_user)):
    now_str = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "planned"):
            raise HTTPException(status_code=403, detail="Планируемые операции доступны только в Premium версии")
        if req.amount <= 0 or req.kind not in {"expense", "income"}:
            raise HTTPException(status_code=400, detail="Invalid planned operation data")
        try:
            date.fromisoformat(req.planned_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="planned_date must use YYYY-MM-DD format")
        from app.db.repositories.accounts_repo import get_account
        from app.db.repositories.categories_repo import get_category
        account = await get_account(db, user_id, req.account_id)
        category = await get_category(db, user_id, req.category_id)
        if not account or int(account[3] or 0) == 1:
            raise HTTPException(status_code=404, detail="Active account not found")
        if not category or int(category[4] or 0) == 1 or category[3] != req.kind:
            raise HTTPException(status_code=404, detail="Active category for operation kind not found")
        from app.db.repositories.planned_repo import create_planned
        item_id = await create_planned(
            db, user_id, req.kind, req.title, req.amount, req.category_id, req.account_id, req.planned_date, req.comment, now_str, req.is_required or 1
        )
        await db.commit()
        return {"status": "success", "id": item_id}

@app.post("/api/planned/{planned_id}/done")
async def complete_planned_endpoint(planned_id: int, user_id: int = Depends(get_current_user)):
    now_str = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "planned"):
            raise HTTPException(status_code=403, detail="Планируемые операции доступны только в Premium версии")
        from app.db.repositories.planned_repo import mark_planned_done
        row = await mark_planned_done(db, user_id, planned_id, now_str)
        if not row:
            raise HTTPException(status_code=404, detail="Planned transaction not found")
        await db.commit()
        return {"status": "success"}

@app.post("/api/planned/{planned_id}/execute")
async def execute_planned_endpoint(planned_id: int, user_id: int = Depends(get_current_user)):
    now_str = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "planned"):
            raise HTTPException(status_code=403, detail="Planned operations require Premium")
        from app.db.repositories.planned_repo import get_planned, mark_planned_done
        planned = await get_planned(db, user_id, planned_id)
        if not planned or int(planned["is_archived"] or 0) == 1:
            raise HTTPException(status_code=404, detail="Active planned transaction not found")
        await db.execute("BEGIN IMMEDIATE")
        try:
            note = planned["comment"] or planned["title"]
            if planned["kind"] == "expense":
                from app.domain.services.accounting_service import add_expense
                tx_id = await add_expense(
                    db, user_id, int(planned["amount"]), int(planned["account_id"]),
                    int(planned["category_id"]), note, commit=False,
                )
            else:
                from app.domain.services.accounting_service import add_income
                tx_id = await add_income(
                    db, user_id, int(planned["amount"]), int(planned["account_id"]),
                    int(planned["category_id"]), note, commit=False,
                )
            await mark_planned_done(db, user_id, planned_id, now_str)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
    return {"status": "success", "transactionId": tx_id}

@app.post("/api/budgets")
async def upsert_budget_endpoint(req: BudgetUpsertRequest, user_id: int = Depends(get_current_user)):
    month = req.month or datetime.now(timezone.utc).strftime("%Y-%m")
    async with get_db() as db:
        from app.db.repositories.budgets_repo import upsert_budget
        await upsert_budget(db, user_id, month, req.category_id, req.amount)
        await db.commit()
        return {"status": "success"}

@app.post("/api/auth/reset")
async def reset_user_data_endpoint(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        from app.db.repositories.reset_repo import wipe_user_data
        await wipe_user_data(db, user_id)
        return {"status": "success"}

@app.post("/api/auth/delete-account")
async def delete_user_account_endpoint(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        from app.db.repositories.reset_repo import delete_user_account
        await delete_user_account(db, user_id)
        return {"status": "success"}

@app.get("/api/reports/export")
async def export_report_endpoint(
    period: str = "month",
    lang: str = "ru",
    user_id: int = Depends(get_current_user),
):
    async with get_db() as db:
        from app.db.repositories.settings_repo import get_settings
        from app.handlers.export import (
            _resolve_period,
            _fetch_rows,
            _build_xlsx,
            now_in_user_tz,
            calculate_financial_metrics,
            select_top_insights,
        )
        from fastapi import Response

        settings = await get_settings(db, user_id)
        currency = settings[0] if settings else "KZT"
        tz_name = settings[1] if settings else "Asia/Aqtobe"

        try:
            start_iso, end_iso, label = await _resolve_period(db, user_id, period)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid period: {e}")

        rows = await _fetch_rows(db, user_id, start_iso, end_iso)
        if not rows:
            raise HTTPException(status_code=404, detail="No transactions found for the selected period")

        metrics = await calculate_financial_metrics(db, user_id, tz_name)

        cur_prof = await db.execute("SELECT user_stage, behavioral_summary, discipline_score FROM ai_profile WHERE user_id=?", (user_id,))
        row_prof = await cur_prof.fetchone()
        if row_prof:
            profile = {"stage": row_prof[0], "behavioral_summary": row_prof[1], "discipline_score": row_prof[2]}
        else:
            profile = {"stage": "chaotic", "behavioral_summary": "накапливаем статистику", "discipline_score": 100}

        cur_ins = await db.execute("SELECT insight_key, insight_text, confidence FROM ai_insights WHERE user_id=? AND status='active'", (user_id,))
        rows_ins = await cur_ins.fetchall()
        ai_insights = [{"key": r[0], "text": r[1], "confidence": r[2]} for r in rows_ins]
        priority_insights = select_top_insights(ai_insights)

        cur_rec = await db.execute(
            """
            SELECT recommendation_type, message_text, target_metric_name, target_metric_start_value, target_metric_goal_value 
            FROM ai_recommendations_log 
            WHERE user_id=? AND status='sent' 
            ORDER BY id DESC LIMIT 1
            """,
            (user_id,)
        )
        row_rec = await cur_rec.fetchone()
        if row_rec:
            latest_rec = {
                "type": row_rec[0],
                "text": row_rec[1],
                "metric": row_rec[2],
                "start": row_rec[3],
                "goal": row_rec[4]
            }
        else:
            latest_rec = None

        cur_acc = await db.execute(
            "SELECT id, name, balance, starting_balance, currency, is_saving FROM accounts WHERE user_id = ? AND is_archived = 0",
            (user_id,)
        )
        accounts_data = await cur_acc.fetchall()

        now_local = await now_in_user_tz(db, user_id)
        curr_month_str = now_local.strftime("%Y-%m")

        from app.domain.services.reports_service import month_bounds_utc, iso
        start_utc, end_utc, _, _ = month_bounds_utc(tz_name, datetime.now(timezone.utc))
        start_iso_curr = iso(start_utc)
        end_iso_curr = iso(end_utc)

        cur_bud = await db.execute(
            """
            SELECT c.name, c.emoji, b.limit_amount,
                   COALESCE((
                       SELECT SUM(t.amount)
                       FROM transactions t
                       WHERE t.user_id = b.user_id
                         AND t.category_id = b.category_id
                         AND t.type = 'expense'
                         AND t.deleted_at IS NULL
                         AND t.ts >= ? AND t.ts < ?
                   ), 0) AS spent
            FROM budgets b
            JOIN categories c ON c.id = b.category_id
            WHERE b.user_id = ? AND b.month = ?
            """,
            (start_iso_curr, end_iso_curr, user_id, curr_month_str)
        )
        budgets_data = await cur_bud.fetchall()

        liabilities_data = []
        try:
            cur_deb = await db.execute(
                "SELECT direction AS kind, title, remaining_amount, payment_amount, next_payment_date, note FROM debts WHERE user_id = ? AND is_active = 1",
                (user_id,)
            )
            liabilities_data = await cur_deb.fetchall()
        except Exception:
            pass

        recurring_data = []
        try:
            cur_rec = await db.execute(
                """
                SELECT title, amount, 'expense' AS rtype, day_of_month, comment, next_run_date
                FROM recurring_expenses
                WHERE user_id = ? AND is_archived = 0
                UNION ALL
                SELECT title, amount, 'income' AS rtype, day_of_month, comment, next_run_date
                FROM recurring_incomes
                WHERE user_id = ? AND is_archived = 0
                ORDER BY day_of_month ASC
                """,
                (user_id, user_id)
            )
            recurring_data = await cur_rec.fetchall()
        except Exception:
            pass

        planned_data = []
        try:
            cur_plan = await db.execute(
                """
                SELECT p.title, p.kind, p.amount, p.planned_date, a.name AS account_name, c.name AS category_name, c.emoji AS category_emoji, p.is_required, p.comment
                FROM planned_transactions p
                LEFT JOIN accounts a ON a.id = p.account_id
                LEFT JOIN categories c ON c.id = p.category_id
                WHERE p.user_id = ? AND p.is_archived = 0
                ORDER BY date(p.planned_date) ASC
                """,
                (user_id,)
            )
            planned_data = await cur_plan.fetchall()
        except Exception:
            pass

        payload = _build_xlsx(
            rows, lang, currency, user_id, metrics, profile, priority_insights, latest_rec, tz_name,
            accounts_data=accounts_data,
            budgets_data=budgets_data,
            liabilities_data=liabilities_data,
            recurring_data=recurring_data,
            planned_data=planned_data,
            all_insights=ai_insights
        )

        if payload is None:
            raise HTTPException(status_code=500, detail="Failed to generate Excel report")

        filename = f"finance_{label}.xlsx"
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

@app.put("/api/accounts/{acc_id}")
async def update_account_endpoint(acc_id: int, req: AccountUpdateRequest, user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        now_str = datetime.now(timezone.utc).isoformat()
        from app.db.repositories.accounts_repo import get_account

        current_account = await get_account(db, user_id, acc_id)
        if not current_account:
            raise HTTPException(status_code=404, detail="Account not found")

        if req.is_saving is not None and req.is_saving not in (0, 1):
            raise HTTPException(status_code=400, detail="is_saving must be 0 or 1")
        if req.is_archived is not None and req.is_archived not in (0, 1):
            raise HTTPException(status_code=400, detail="is_archived must be 0 or 1")
        if req.is_business is not None and req.is_business not in (0, 1):
            raise HTTPException(status_code=400, detail="is_business must be 0 or 1")
        if req.acc_type is not None and req.acc_type not in {"regular", "saving", "deposit"}:
            raise HTTPException(status_code=400, detail="Unsupported account type")
        if req.accrual_period is not None and req.accrual_period not in {"month", "year"}:
            raise HTTPException(status_code=400, detail="Unsupported accrual period")
        if req.interest_rate is not None and (not math.isfinite(req.interest_rate) or req.interest_rate < 0):
            raise HTTPException(status_code=400, detail="interest_rate must be non-negative")

        normalized_currency = None
        if req.currency is not None:
            normalized_currency = normalize_currency(req.currency)
            from app.db.repositories.accounts_repo import get_account, account_has_transactions
            current_currency = normalize_currency(current_account[4])
            if normalized_currency != current_currency and await account_has_transactions(db, user_id, acc_id):
                raise HTTPException(
                    status_code=400,
                    detail="Currency can only be changed for an account without transactions",
                )
        
        # 1. Update name
        if req.name is not None:
            from app.db.repositories.accounts_repo import rename_account, get_account_by_name
            name = clean_name(req.name)
            if not name:
                raise HTTPException(status_code=400, detail="Название должно быть от 2 до 24 символов")
            existing = await get_account_by_name(db, user_id, name)
            if existing and int(existing[0]) != acc_id:
                raise HTTPException(status_code=400, detail="Счёт с таким названием уже существует")
            await rename_account(db, user_id, acc_id, name, now_str)
            
        # 2. Update balance
        if req.balance is not None:
            from app.db.repositories.accounts_repo import get_account, set_account_balance
            acc = await get_account(db, user_id, acc_id)
            if acc:
                old_balance = acc[2]
                delta = req.balance - old_balance
                if delta != 0:
                    await set_account_balance(db, user_id, acc_id, req.balance, now_str)
                    
                    cur_lang = await db.execute("SELECT lang FROM settings WHERE user_id=? LIMIT 1", (user_id,))
                    lang_row = await cur_lang.fetchone()
                    lang = lang_row[0] if lang_row else 'ru'
                    
                    sign = "+" if delta > 0 else ""
                    currency = normalize_currency(acc[4])
                    note = {
                        "ru": f"Корректировка баланса ({sign}{delta} {currency})",
                        "en": f"Balance adjustment ({sign}{delta} {currency})",
                        "kk": f"Балансты түзету ({sign}{delta} {currency})"
                    }.get(lang, f"Корректировка баланса ({sign}{delta} {currency})")
                    
                    from app.db.repositories.tx_repo import create_tx
                    await create_tx(
                        db=db,
                        user_id=user_id,
                        ts_iso=now_str,
                        tx_type="adjustment",
                        amount=delta,
                        account_id=acc_id,
                        category_id=None,
                        note=note,
                        created_at=now_str
                    )
            
        # 3. Toggle saving type
        if req.is_saving is not None:
            from app.db.repositories.accounts_repo import get_account, toggle_account_saving
            acc = await get_account(db, user_id, acc_id)
            if acc:
                current_is_saving = acc[5]
                # is_saving in database is integer 0/1
                if current_is_saving != req.is_saving:
                    await toggle_account_saving(db, user_id, acc_id, now_str)
                    
        # 4. Toggle archived status
        if req.is_archived is not None:
            from app.db.repositories.accounts_repo import archive_account, restore_account
            if req.is_archived == 1:
                await archive_account(db, user_id, acc_id, now_str)
            else:
                if int(current_account[3] or 0) == 1:
                    ctx = await get_user_context(db, user_id)
                    if ctx.mode != "full" and await count_accounts(db, user_id) >= 2:
                        raise HTTPException(
                            status_code=403,
                            detail="В бесплатной версии доступно не более 2 активных счетов"
                        )
                    try:
                        await restore_account(db, user_id, acc_id, now_str)
                    except ValueError as e:
                        if str(e) == "active_name_exists":
                            raise HTTPException(status_code=400, detail="Счёт с таким названием уже существует")
                        raise

        # 5. Update type, rate, period, business, and currency fields
        if req.acc_type is not None:
            await db.execute(
                "UPDATE accounts SET acc_type=?, updated_at=? WHERE user_id=? AND id=?",
                (req.acc_type, now_str, user_id, acc_id)
            )
        if req.interest_rate is not None:
            await db.execute(
                "UPDATE accounts SET interest_rate=?, updated_at=? WHERE user_id=? AND id=?",
                (req.interest_rate, now_str, user_id, acc_id)
            )
        if req.accrual_period is not None:
            await db.execute(
                "UPDATE accounts SET accrual_period=?, updated_at=? WHERE user_id=? AND id=?",
                (req.accrual_period, now_str, user_id, acc_id)
            )
        if req.is_business is not None:
            await db.execute(
                "UPDATE accounts SET is_business=?, updated_at=? WHERE user_id=? AND id=?",
                (req.is_business, now_str, user_id, acc_id)
            )
        if normalized_currency is not None:
            from app.domain.services.access_service import get_user_context
            ctx = await get_user_context(db, user_id)
            if normalized_currency != current_currency and normalized_currency != "KZT" and ctx.mode != "full":
                raise HTTPException(
                    status_code=403,
                    detail="Использование валютных счетов доступно только в Premium версии"
                )
            await db.execute(
                "UPDATE accounts SET currency=?, updated_at=? WHERE user_id=? AND id=?",
                (normalized_currency, now_str, user_id, acc_id)
            )

        await db.commit()
        return {"status": "success"}

@app.delete("/api/accounts/{acc_id}")
async def delete_account_endpoint(acc_id: int, user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        from app.db.repositories.accounts_repo import archive_account, get_account
        if not await get_account(db, user_id, acc_id):
            raise HTTPException(status_code=404, detail="Account not found")
        now_str = datetime.now(timezone.utc).isoformat()
        await archive_account(db, user_id, acc_id, now_str)
        await db.commit()
        return {"status": "success"}

@app.post("/api/user/profile")
async def update_profile(req: ProfileUpdateRequest, user_id: int = Depends(get_current_user)):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET display_name=? WHERE id=?",
            (name, user_id)
        )
        await db.commit()
    return {"status": "success", "name": name}

@app.post("/api/profile/upgrade")
async def upgrade_profile_to_premium(user_id: int = Depends(get_current_user)):
    raise HTTPException(
        status_code=403,
        detail="Premium activation must be confirmed by the Telegram payment flow",
    )

@app.get("/api/user/settings")
async def get_user_settings(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        cur = await db.execute(
            """
            SELECT currency, timezone, lang, budget_cycle_start_day,
                   telegram_notifications_enabled, push_notifications_enabled,
                   daily_report_enabled, daily_report_time,
                   quiet_hours_enabled, quiet_hours_start, quiet_hours_end,
                   debts_enabled, debts_days_before
            FROM settings WHERE user_id=?
            """,
            (user_id,),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Settings not found")
        return {key: row[key] for key in row.keys()}

@app.post("/api/user/settings")
async def update_settings(req: SettingsUpdateRequest, user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        cur = await db.execute("SELECT 1 FROM settings WHERE user_id=?", (user_id,))
        exists = await cur.fetchone() is not None
        now_str = datetime.now(timezone.utc).isoformat()
        if not exists:
            await db.execute(
                "INSERT INTO settings (user_id, created_at, updated_at) VALUES (?, ?, ?)",
                (user_id, now_str, now_str)
            )
        if req.budget_cycle_start_day is not None:
            day = max(1, min(req.budget_cycle_start_day, 28))
            await db.execute(
                "UPDATE settings SET budget_cycle_start_day=?, updated_at=? WHERE user_id=?",
                (day, now_str, user_id)
            )
        if req.currency is not None:
            currency = normalize_currency(req.currency)
            await db.execute(
                "UPDATE settings SET currency=?, updated_at=? WHERE user_id=?",
                (currency, now_str, user_id)
            )
        if req.timezone is not None:
            try:
                ZoneInfo(req.timezone)
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Invalid timezone") from exc
            await db.execute(
                "UPDATE settings SET timezone=?, updated_at=? WHERE user_id=?",
                (req.timezone, now_str, user_id)
            )
        if req.lang is not None:
            if req.lang not in {"ru", "en", "kk"}:
                raise HTTPException(status_code=400, detail="Unsupported language")
            await db.execute(
                "UPDATE settings SET lang=?, updated_at=? WHERE user_id=?",
                (req.lang, now_str, user_id)
            )
        bool_fields = {
            "telegram_notifications_enabled": req.telegram_notifications_enabled,
            "push_notifications_enabled": req.push_notifications_enabled,
            "daily_report_enabled": req.daily_report_enabled,
            "quiet_hours_enabled": req.quiet_hours_enabled,
            "debts_enabled": req.debts_enabled,
        }
        for field, value in bool_fields.items():
            if value is not None:
                await db.execute(
                    f"UPDATE settings SET {field}=?, updated_at=? WHERE user_id=?",
                    (int(value), now_str, user_id),
                )
        time_fields = {
            "daily_report_time": req.daily_report_time,
            "quiet_hours_start": req.quiet_hours_start,
            "quiet_hours_end": req.quiet_hours_end,
        }
        for field, value in time_fields.items():
            if value is not None:
                normalized = validate_hhmm(value, field)
                await db.execute(
                    f"UPDATE settings SET {field}=?, updated_at=? WHERE user_id=?",
                    (normalized, now_str, user_id),
                )
        if req.debts_days_before is not None:
            if req.debts_days_before < 0 or req.debts_days_before > 30:
                raise HTTPException(status_code=400, detail="debts_days_before must be between 0 and 30")
            await db.execute(
                "UPDATE settings SET debts_days_before=?, updated_at=? WHERE user_id=?",
                (req.debts_days_before, now_str, user_id),
            )
        await db.commit()
        return {"status": "success"}

@app.post("/api/push/devices")
async def register_push_device(req: PushDeviceRequest, user_id: int = Depends(get_current_user)):
    token = req.token.strip()
    platform = req.platform.strip().lower()
    if not token:
        raise HTTPException(status_code=400, detail="Push token cannot be empty")
    if platform not in {"android", "ios", "web"}:
        raise HTTPException(status_code=400, detail="Unsupported push platform")
    now_str = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO push_devices(user_id, token, platform, enabled, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(token) DO UPDATE SET
              user_id=excluded.user_id,
              platform=excluded.platform,
              enabled=1,
              updated_at=excluded.updated_at
            """,
            (user_id, token, platform, now_str, now_str),
        )
        await db.commit()
    return {"status": "success"}

@app.put("/api/categories/{category_id}")
async def update_category_endpoint(category_id: int, req: CategoryUpdateRequest, user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        now_str = datetime.now(timezone.utc).isoformat()
        cur = await db.execute("SELECT kind FROM categories WHERE id=? AND user_id=? LIMIT 1", (category_id, user_id))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Category not found")
        
        if req.name is not None:
            name = req.name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="Name cannot be empty")
            cur_dup = await db.execute(
                "SELECT 1 FROM categories WHERE user_id=? AND name=? AND id != ? AND is_archived=0 LIMIT 1",
                (user_id, name, category_id)
            )
            if await cur_dup.fetchone():
                raise HTTPException(status_code=400, detail="Category with this name already exists")
            await db.execute("UPDATE categories SET name=?, updated_at=? WHERE id=?", (name, now_str, category_id))
            
        if req.emoji is not None:
            await db.execute("UPDATE categories SET emoji=?, updated_at=? WHERE id=?", (req.emoji, now_str, category_id))
            
        if req.limit_amount is not None:
            start_day = await get_budget_cycle_start_day(db, user_id)
            _, _, cycle_month_str = get_budget_cycle_bounds(date.today(), start_day)
            from app.db.repositories.budgets_repo import upsert_budget
            await db.execute(
                "INSERT INTO budgets (user_id, month, category_id, limit_amount, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id, month, category_id) DO UPDATE SET limit_amount=excluded.limit_amount, updated_at=excluded.updated_at",
                (user_id, cycle_month_str, category_id, req.limit_amount, now_str, now_str)
            )
            
        if req.default_account_id is not None:
            val = req.default_account_id if req.default_account_id > 0 else None
            await db.execute("UPDATE categories SET default_account_id=?, updated_at=? WHERE id=?", (val, now_str, category_id))

        if req.exclude_from_analytics is not None:
            await db.execute("UPDATE categories SET exclude_from_analytics=?, updated_at=? WHERE id=?", (req.exclude_from_analytics, now_str, category_id))

        if req.warn_threshold is not None:
            await db.execute("UPDATE categories SET warn_threshold=?, updated_at=? WHERE id=?", (req.warn_threshold, now_str, category_id))

        await db.commit()
        return {"status": "success"}
