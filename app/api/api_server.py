from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import aiosqlite
import hashlib
import hmac
from datetime import datetime, timezone, date, timedelta
import calendar

from app.config.settings import settings
from app.db.connection import get_db
from app.db.repositories.users_repo import get_onboarded
from app.db.repositories.accounts_repo import list_accounts, apply_balance_delta
from app.db.repositories.categories_repo import list_categories
from app.db.repositories.tx_repo import create_tx, create_transfer
from app.domain.services.access_service import can_use_feature

app = FastAPI(title="Finance Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SECRET_KEY = b"finance_bot_secret_key_123!"

def generate_token(user_id: int) -> str:
    msg = str(user_id).encode()
    sig = hmac.new(SECRET_KEY, msg, hashlib.sha256).hexdigest()
    return f"{user_id}.{sig}"

def verify_token(token: str) -> int | None:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
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

class TransactionCreateRequest(BaseModel):
    amount: int  # in minor units (e.g. 100 for 1.00 KZT)
    kind: str  # 'expense', 'income', 'transfer'
    account_id: int
    category_id: Optional[int] = None
    note: Optional[str] = None
    to_account_id: Optional[int] = None  # for transfers
    date_override: Optional[str] = None  # YYYY-MM-DD override

class ChatRequest(BaseModel):
    text: str

class AccountCreateRequest(BaseModel):
    name: str
    balance: int
    currency: Optional[str] = "KZT"
    is_saving: Optional[int] = 0

class DebtCreateRequest(BaseModel):
    direction: str  # 'out' or 'in'
    dtype: str      # 'bank' or 'private'
    title: str
    payment_amount: Optional[int] = None
    next_payment_date: Optional[str] = None  # YYYY-MM-DD
    remaining_amount: int

class DebtPayRequest(BaseModel):
    payment_amount: int
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
        
        user_id, expires_at = row[0], row[1]
        if expires_at < now_str:
            # Code expired
            raise HTTPException(status_code=400, detail="Code expired. Please request a new one.")
            
        token = generate_token(user_id)
        return {"token": token, "user_id": user_id}

@app.get("/api/dashboard")
async def get_dashboard(user_id: int = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    current_month_str = now.strftime("%Y-%m")
    
    async with get_db() as db:
        from app.domain.services.access_service import get_user_context, get_available_features_from_context
        ctx = await get_user_context(db, user_id)
        available_features = list(get_available_features_from_context(ctx))

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
            total_balance += acc["balance"]
            
        # 2. Monthly Expenses
        cur = await db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions "
            "WHERE user_id=? AND type='expense' AND deleted_at IS NULL AND strftime('%Y-%m', ts)=?",
            (user_id, current_month_str)
        )
        (monthly_expenses_row,) = await cur.fetchone()
        
        # 3. Weekly streak (Monday to Sunday)
        # Find start of current week
        today = date.today()
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
            "SELECT t.id, t.ts, t.type, t.amount, a.name as account_name, c.name as category_name, c.emoji as category_emoji, t.note "
            "FROM transactions t "
            "JOIN accounts a ON a.id=t.account_id "
            "LEFT JOIN categories c ON c.id=t.category_id "
            "WHERE t.user_id=? AND t.deleted_at IS NULL "
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
                "accountName": row["account_name"],
                "categoryName": row["category_name"] or ("Перевод" if row["type"] == "transfer" else "Прочее"),
                "categoryEmoji": row["category_emoji"] or ("🔁" if row["type"] == "transfer" else "📦"),
                "note": row["note"]
            })
            
        # 5. Categories progress (limit vs spent)
        categories = await list_categories(db, user_id, "expense")
        categories_data = []
        for cat in categories:
            # Get spent amount for current month
            cur_spent = await db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM transactions "
                "WHERE user_id=? AND category_id=? AND type='expense' AND deleted_at IS NULL AND strftime('%Y-%m', ts)=?",
                (user_id, cat["id"], current_month_str)
            )
            (spent_val,) = await cur_spent.fetchone()
            
            # Get budget limit
            cur_limit = await db.execute(
                "SELECT limit_amount FROM budgets WHERE user_id=? AND category_id=? AND month=?",
                (user_id, cat["id"], current_month_str)
            )
            limit_row = await cur_limit.fetchone()
            limit_amount = limit_row[0] if limit_row else 0
            
            categories_data.append({
                "id": cat["id"],
                "name": cat["name"],
                "emoji": cat["emoji"],
                "limitAmount": limit_amount,
                "spentAmount": abs(spent_val)
            })

        return {
            "totalBalance": total_balance,
            "monthlyExpenses": abs(monthly_expenses_row),
            "weeklyStreak": weekly_streak,
            "accounts": accounts_data,
            "recentTransactions": recent_tx,
            "categories": categories_data,
            "isPremium": ctx.mode == "full",
            "premiumExpirationDate": ctx.expiration_date,
            "availableFeatures": available_features,
            "progressLevel": ctx.progress_level
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
