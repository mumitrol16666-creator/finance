from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import aiosqlite
import hashlib
import hmac
from datetime import datetime, timezone, date, timedelta
import calendar
from contextlib import asynccontextmanager

from app.config.settings import settings
from app.db.connection import get_db
from app.db.repositories.users_repo import get_onboarded
from app.db.repositories.accounts_repo import list_accounts, apply_balance_delta
from app.db.repositories.categories_repo import list_categories
from app.db.repositories.tx_repo import create_tx, create_transfer
from app.domain.services.access_service import can_use_feature

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Perform database typo migrations
    async with get_db() as db:
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
        elif len(parts) == 2:
            # Backwards compatibility: verify old token format without expiration
            user_id_str, sig = parts
            user_id = int(user_id_str)
            msg = str(user_id).encode()
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

class VerifyRequest(BaseModel):
    code: str

class ProfileUpdateRequest(BaseModel):
    name: str

class SettingsUpdateRequest(BaseModel):
    budget_cycle_start_day: Optional[int] = None
    currency: Optional[str] = None
    timezone: Optional[str] = None
    lang: Optional[str] = None

class CategoryUpdateRequest(BaseModel):
    name: Optional[str] = None
    emoji: Optional[str] = None
    limit_amount: Optional[int] = None

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
    cur = await db.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
    row = await cur.fetchone()
    if row:
        return row[0]
    return None

class TransactionCreateRequest(BaseModel):
    amount: int  # in minor units (e.g. 100 for 1.00 KZT)
    kind: str  # 'expense', 'income', 'transfer'
    account_id: int
    category_id: Optional[int] = None
    note: Optional[str] = None
    to_account_id: Optional[int] = None  # for transfers
    date_override: Optional[str] = None  # YYYY-MM-DD override

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

class AccountUpdateRequest(BaseModel):
    name: Optional[str] = None
    balance: Optional[int] = None
    is_saving: Optional[int] = None
    is_archived: Optional[int] = None

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

class CategoryCreateRequest(BaseModel):
    name: str
    emoji: Optional[str] = "📦"
    kind: Optional[str] = "expense"

    is_required: Optional[int] = 1

class BudgetUpsertRequest(BaseModel):
    category_id: int
    amount: int
    month: Optional[str] = None

@app.post("/api/auth/verify")
async def verify_code(req: VerifyRequest):
    code = req.code.strip()
    now_str = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        cur = await db.execute(
            "SELECT user_id, expires_at FROM login_codes WHERE code=? LIMIT 1",
            (code,)
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="Invalid verification code")
        
        user_id = row[0]
        
        # Check if user settings exists, if not create default settings row
        cur_settings = await db.execute("SELECT 1 FROM settings WHERE user_id=?", (user_id,))
        if not await cur_settings.fetchone():
            await db.execute(
                "INSERT INTO settings (user_id, created_at, updated_at) VALUES (?, ?, ?)",
                (user_id, now_str, now_str)
            )
            await db.commit()
            
        cur_user = await db.execute("SELECT name FROM users WHERE user_id=?", (user_id,))
        user_row = await cur_user.fetchone()
        name = user_row[0] if user_row else None
            
        token = generate_token(user_id)
        return {"token": token, "user_id": user_id, "name": name}

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

        if is_custom_range:
            start_dt, end_dt, cycle_month_str = custom_start_dt, custom_end_dt, custom_cycle_month_str
        else:
            # Get settings cycle start day
            cycle_start_day = await get_budget_cycle_start_day(db, user_id)
            start_dt, end_dt, cycle_month_str = get_budget_cycle_bounds(today, cycle_start_day)
            
        start_str = start_dt.isoformat()
        end_str = end_dt.isoformat()

        # 1. Accounts & balances
        accounts = await list_accounts(db, user_id)
        accounts_data = []
        total_balance = 0
        for acc in accounts:
            accounts_data.append({
                "id": acc["id"],
                "name": acc["name"],
                "balance": acc["balance"],
                "currency": acc["currency"],
                "is_saving": bool(acc["is_saving"])
            })
            if not acc["is_saving"]:
                total_balance += acc["balance"]
            
        # 2. Monthly Expenses inside current cycle
        cur = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions "
            "WHERE user_id=? AND type='expense' AND deleted_at IS NULL AND ts >= ? AND ts < ?",
            (user_id, start_str, end_str)
        )
        (monthly_expenses_row,) = await cur.fetchone()

        # 2b. Monthly Income inside current cycle
        cur_inc = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions "
            "WHERE user_id=? AND type='income' AND deleted_at IS NULL AND ts >= ? AND ts < ?",
            (user_id, start_str, end_str)
        )
        (monthly_income_row,) = await cur_inc.fetchone()
        
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
            "       a.name as account_name, "
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
                "note": row["note"]
            })
            
        # 5. Categories progress (limit vs spent) for both expenses and incomes
        expense_cats = await list_categories(db, user_id, "expense")
        income_cats = await list_categories(db, user_id, "income")
        categories_data = []
        
        for cat in expense_cats:
            cur_spent = await db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions "
                "WHERE user_id=? AND category_id=? AND type='expense' AND deleted_at IS NULL AND ts >= ? AND ts < ?",
                (user_id, cat["id"], start_str, end_str)
            )
            (spent_val,) = await cur_spent.fetchone()
            
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
                "spentAmount": abs(spent_val)
            })
            
        for cat in income_cats:
            cur_earned = await db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions "
                "WHERE user_id=? AND category_id=? AND type='income' AND deleted_at IS NULL AND ts >= ? AND ts < ?",
                (user_id, cat["id"], start_str, end_str)
            )
            (earned_val,) = await cur_earned.fetchone()
            
            categories_data.append({
                "id": cat["id"],
                "name": cat["name"],
                "emoji": cat["emoji"],
                "kind": "income",
                "limitAmount": 0,
                "spentAmount": abs(earned_val)
            })

        # Calculate active days count in current cycle
        cur_active_days = await db.execute(
            "SELECT COUNT(DISTINCT date(ts)) FROM transactions "
            "WHERE user_id=? AND deleted_at IS NULL AND ts >= ? AND ts < ?",
            (user_id, start_str, end_str)
        )
        active_days_count = (await cur_active_days.fetchone())[0]
        total_cycle_days = (end_dt - start_dt).days

        return {
            "totalBalance": total_balance,
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
            "budgetCycleStartDay": cycle_start_day
        }

@app.get("/api/accounts")
async def get_accounts(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        accounts = await list_accounts(db, user_id)
        return [{
            "id": acc["id"],
            "name": acc["name"],
            "balance": acc["balance"],
            "currency": acc["currency"],
            "is_saving": bool(acc["is_saving"])
        } for acc in accounts]

@app.get("/api/categories")
async def get_categories(kind: str = "expense", user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        categories = await list_categories(db, user_id, kind)
        return [{
            "id": cat["id"],
            "name": cat["name"],
            "emoji": cat["emoji"]
        } for cat in categories]

@app.post("/api/categories")
async def add_category(req: CategoryCreateRequest, user_id: int = Depends(get_current_user)):
    now_str = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        from app.db.repositories.categories_repo import create_category, name_exists_any_kind
        if await name_exists_any_kind(db, user_id, req.name):
            raise HTTPException(status_code=400, detail="Категория с таким именем уже существует")
        cat_id = await create_category(db, user_id, req.name, req.emoji, req.kind, now_str)
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
    async with get_db() as db:
        if req.kind == "transfer":
            from app.domain.services.access_service import can_use_feature
            if not await can_use_feature(db, user_id, "transfer"):
                raise HTTPException(status_code=403, detail="Функция перевода доступна только в Premium версии")
            if not req.to_account_id:
                raise HTTPException(status_code=400, detail="to_account_id is required for transfers")
            await create_transfer(
                db, user_id, now_str, req.account_id, req.to_account_id, req.amount, req.note, now_str
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
            "SELECT id, direction, dtype, title, total_amount, remaining_amount, payment_amount, next_payment_date, note, status, is_active "
            "FROM debts WHERE user_id=? AND is_active=1 ORDER BY id DESC",
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
                "status": row["status"]
            })
        return debts

@app.get("/api/recurring")
async def get_recurring(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "recurring"):
            raise HTTPException(status_code=403, detail="Регулярные платежи доступны только в Premium версии")
        # Get recurring expenses
        cur_exp = await db.execute(
            "SELECT r.id, r.title, r.amount, 'expense' as kind, r.day_of_month, r.next_run_date, c.emoji as category_emoji "
            "FROM recurring_expenses r "
            "LEFT JOIN categories c ON c.id = r.category_id "
            "WHERE r.user_id=? AND r.is_archived=0 ORDER BY r.id DESC",
            (user_id,)
        )
        rows_exp = await cur_exp.fetchall()
        
        # Get recurring incomes
        cur_inc = await db.execute(
            "SELECT r.id, r.title, r.amount, 'income' as kind, r.day_of_month, r.next_run_date, c.emoji as category_emoji "
            "FROM recurring_incomes r "
            "LEFT JOIN categories c ON c.id = r.category_id "
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
                "categoryEmoji": row["category_emoji"] or "🔁"
            })
        return recurring

@app.get("/api/planned")
async def get_planned(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "planned"):
            raise HTTPException(status_code=403, detail="Планируемые операции доступны только в Premium версии")
        cur = await db.execute(
            "SELECT p.id, p.title, p.amount, p.planned_date, p.kind, c.emoji as category_emoji "
            "FROM planned_transactions p "
            "LEFT JOIN categories c ON c.id=p.category_id "
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
                "categoryEmoji": row["category_emoji"] or "📅"
            })
        return planned

@app.post("/api/chat")
async def chat_with_ai(req: ChatRequest, user_id: int = Depends(get_current_user)):
    text = req.text
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "ai"):
            raise HTTPException(status_code=403, detail="ИИ-консультант доступен только в Premium версии")
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
        cur = await db.execute(
            "SELECT c.name, c.emoji, COALESCE(SUM(t.amount), 0) as total "
            "FROM transactions t "
            "JOIN categories c ON c.id=t.category_id "
            "WHERE t.user_id=? AND t.type='expense' AND t.deleted_at IS NULL AND strftime('%Y-%m', t.ts)=? "
            "GROUP BY c.id",
            (user_id, current_month_str)
        )
        chart_data = []
        for row in await cur.fetchall():
            chart_data.append({
                "categoryName": row["name"],
                "categoryEmoji": row["emoji"],
                "amount": abs(row["total"])
            })
        return {
            "month": current_month_str,
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
    async with get_db() as db:
        try:
            from app.db.repositories.accounts_repo import create_account
            acc_id, status = await create_account(
                db, user_id, req.name, req.balance, now_str, req.currency or "KZT", req.is_saving or 0
            )
            await db.commit()
            return {"status": status, "id": acc_id}
        except ValueError as e:
            if str(e) == 'active_name_exists':
                raise HTTPException(status_code=400, detail="Счёт с таким именем уже существует")
            raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/debts")
async def add_debt_endpoint(req: DebtCreateRequest, user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "debts"):
            raise HTTPException(status_code=403, detail="Функция долгов доступна только в Premium версии")
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
        
        if req.account_id is not None:
            from app.db.repositories.debts_repo import get_debt
            row = await get_debt(db, user_id, debt_id)
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
                amount = req.payment_amount

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
                    await add_expense(db, user_id, amount, req.account_id, category_id, note)
                else:
                    category_id = await ensure_category(
                        db, user_id, kind="income",
                        name="Мне вернули долг",
                        emoji="📥"
                    )
                    note = f"Мне вернули долг: {title}"
                    from app.domain.services.accounting_service import add_income
                    await add_income(db, user_id, amount, req.account_id, category_id, note)

        from app.db.repositories.debts_repo import apply_debt_payment
        await apply_debt_payment(
            db, user_id, debt_id, req.payment_amount, req.next_payment_date
        )
        return {"status": "success"}

@app.post("/api/recurring")
async def add_recurring_endpoint(req: RecurringCreateRequest, user_id: int = Depends(get_current_user)):
    now_str = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        if not await can_use_feature(db, user_id, "recurring"):
            raise HTTPException(status_code=403, detail="Регулярные платежи доступны только в Premium версии")
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
        from app.db.repositories.planned_repo import create_planned
        item_id = await create_planned(
            db, user_id, req.kind, req.title, req.amount, req.category_id, req.account_id, req.planned_date, req.comment, now_str, req.is_required or 1
        )
        await db.commit()
        return {"status": "success", "id": item_id}

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
        
        # 1. Update name
        if req.name is not None:
            from app.db.repositories.accounts_repo import rename_account, has_active_account_with_name
            name = req.name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="Название не может быть пустым")
            if await has_active_account_with_name(db, user_id, name, exclude_account_id=acc_id):
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
                    note = {
                        "ru": f"Корректировка баланса ({sign}{delta} ₸)",
                        "en": f"Balance adjustment ({sign}{delta} ₸)",
                        "kk": f"Балансты түзету ({sign}{delta} ₸)"
                    }.get(lang, f"Корректировка баланса ({sign}{delta} ₸)")
                    
                    tx_type = 'income' if delta > 0 else 'expense'
                    from app.db.repositories.tx_repo import create_tx
                    await create_tx(
                        db=db,
                        user_id=user_id,
                        ts_iso=now_str,
                        tx_type=tx_type,
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
                await restore_account(db, user_id, acc_id, now_str)
                
        await db.commit()
        return {"status": "success"}

@app.delete("/api/accounts/{acc_id}")
async def delete_account_endpoint(acc_id: int, user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        from app.db.repositories.accounts_repo import archive_account
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
            "UPDATE users SET name=? WHERE user_id=?",
            (name, user_id)
        )
        await db.commit()
    return {"status": "success", "name": name}

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
            await db.execute(
                "UPDATE settings SET currency=?, updated_at=? WHERE user_id=?",
                (req.currency, now_str, user_id)
            )
        if req.timezone is not None:
            await db.execute(
                "UPDATE settings SET timezone=?, updated_at=? WHERE user_id=?",
                (req.timezone, now_str, user_id)
            )
        if req.lang is not None:
            await db.execute(
                "UPDATE settings SET lang=?, updated_at=? WHERE user_id=?",
                (req.lang, now_str, user_id)
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
            
        await db.commit()
        return {"status": "success"}
