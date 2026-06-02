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

class ChatRequest(BaseModel):
    text: str

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
            await db.execute("DELETE FROM login_codes WHERE code=?", (code,))
            await db.commit()
            raise HTTPException(status_code=400, detail="Code expired. Please request a new one.")
            
        # Clean up code after successful use
        await db.execute("DELETE FROM login_codes WHERE code=?", (code,))
        await db.commit()
        
        token = generate_token(user_id)
        return {"token": token, "user_id": user_id}

@app.get("/api/dashboard")
async def get_dashboard(user_id: int = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    current_month_str = now.strftime("%Y-%m")
    
    async with get_db() as db:
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
                "categoryName": row["category_name"] or "Перевод" if row["type"] == "transfer" else "Прочее",
                "categoryEmoji": row["category_emoji"] or "🔁" if row["type"] == "transfer" else "📦",
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
            "categories": categories_data
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

@app.post("/api/transactions")
async def add_transaction(req: TransactionCreateRequest, user_id: int = Depends(get_current_user)):
    now_str = datetime.now(timezone.utc).isoformat()
    async with get_db() as db:
        if req.kind == "transfer":
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
        # Get recurring expenses
        cur_exp = await db.execute(
            "SELECT id, title, amount, 'expense' as kind, day_of_month, next_run_date "
            "FROM recurring_expenses WHERE user_id=? AND is_archived=0 ORDER BY id DESC",
            (user_id,)
        )
        rows_exp = await cur_exp.fetchall()
        
        # Get recurring incomes
        cur_inc = await db.execute(
            "SELECT id, title, amount, 'income' as kind, day_of_month, next_run_date "
            "FROM recurring_incomes WHERE user_id=? AND is_archived=0 ORDER BY id DESC",
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
                "nextRunDate": row["next_run_date"]
            })
        return recurring

@app.get("/api/planned")
async def get_planned(user_id: int = Depends(get_current_user)):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT id, title, amount, planned_date, kind, category_id, account_id, is_archived "
            "FROM planned_transactions WHERE user_id=? AND is_archived=0 ORDER BY planned_date ASC",
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
                "status": "pending"
            })
        return planned

@app.post("/api/chat")
async def chat_with_ai(req: ChatRequest, user_id: int = Depends(get_current_user)):
    text = req.text
    async with get_db() as db:
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
