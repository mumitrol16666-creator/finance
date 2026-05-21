from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from statistics import mean, pstdev
import aiosqlite
from app.domain.services.ai_consultant_service import build_period_meta, _fetch_rows, _safe_tz

async def calculate_burn_rate(db: aiosqlite.Connection, user_id: int, tz_name: str, days: int = 30) -> dict:
    """Calculate daily, weekly, monthly burn rates and trend compared to the previous period."""
    now_utc = datetime.now(timezone.utc)
    tz = _safe_tz(tz_name)
    local_now = now_utc.astimezone(tz)
    
    start_cur = now_utc - timedelta(days=days)
    start_prev = now_utc - timedelta(days=days * 2)
    
    # Fetch expenses for current period
    cur = await db.execute(
        "SELECT SUM(-amount) FROM transactions WHERE user_id=? AND type='expense' AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, start_cur.isoformat(), now_utc.isoformat())
    )
    row = await cur.fetchone()
    cur_total = int(row[0] or 0)
    
    # Fetch expenses for previous period
    cur = await db.execute(
        "SELECT SUM(-amount) FROM transactions WHERE user_id=? AND type='expense' AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, start_prev.isoformat(), start_cur.isoformat())
    )
    row = await cur.fetchone()
    prev_total = int(row[0] or 0)
    
    daily_burn = cur_total / max(1, days)
    weekly_burn = daily_burn * 7
    monthly_burn = daily_burn * 30
    
    trend_pct = 0.0
    if prev_total > 0:
        trend_pct = ((cur_total - prev_total) / prev_total) * 100.0
        
    return {
        "days_analyzed": days,
        "current_period_total": cur_total,
        "previous_period_total": prev_total,
        "daily_burn_rate": int(round(daily_burn)),
        "weekly_burn_rate": int(round(weekly_burn)),
        "monthly_burn_rate": int(round(monthly_burn)),
        "trend_pct": round(trend_pct, 1)
    }

async def calculate_savings_rate(db: aiosqlite.Connection, user_id: int, days: int = 30) -> dict:
    """Calculate savings rate (percentage of income saved)."""
    now_utc = datetime.now(timezone.utc)
    start_dt = now_utc - timedelta(days=days)
    
    cur = await db.execute(
        """
        SELECT 
            SUM(CASE WHEN type='income' THEN amount ELSE 0 END),
            SUM(CASE WHEN type='expense' THEN -amount ELSE 0 END)
        FROM transactions 
        WHERE user_id=? AND ts>=? AND ts<? AND deleted_at IS NULL
        """,
        (user_id, start_dt.isoformat(), now_utc.isoformat())
    )
    row = await cur.fetchone()
    income = int(row[0] or 0)
    expense = int(row[1] or 0)
    
    saved = income - expense
    savings_rate = 0.0
    if income > 0:
        savings_rate = (saved / income) * 100.0
        
    return {
        "days_analyzed": days,
        "income": income,
        "expense": expense,
        "saved_amount": saved,
        "savings_rate_pct": round(savings_rate, 1)
    }

async def calculate_debt_stress_index(db: aiosqlite.Connection, user_id: int) -> dict:
    """Calculate the ratio of debt payments to monthly income."""
    # Average monthly income over the last 90 days
    now_utc = datetime.now(timezone.utc)
    start_dt = now_utc - timedelta(days=90)
    
    cur = await db.execute(
        "SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='income' AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, start_dt.isoformat(), now_utc.isoformat())
    )
    row = await cur.fetchone()
    income_90 = int(row[0] or 0)
    monthly_income = (income_90 / 3) if income_90 > 0 else 0
    
    # Active debts monthly payments
    cur = await db.execute(
        "SELECT SUM(payment_amount), SUM(remaining_amount) FROM debts WHERE user_id=? AND is_active=1",
        (user_id,)
    )
    row = await cur.fetchone()
    monthly_debt_payments = int(row[0] or 0)
    total_remaining_debt = int(row[1] or 0)
    
    stress_index = 0.0
    if monthly_income > 0:
        stress_index = (monthly_debt_payments / monthly_income) * 100.0
        
    # Classify stress level
    stress_level = "low"
    if stress_index > 40:
        stress_level = "critical"
    elif stress_index > 20:
        stress_level = "medium"
        
    return {
        "monthly_debt_payments": monthly_debt_payments,
        "total_remaining_debt": total_remaining_debt,
        "monthly_income_avg": int(round(monthly_income)),
        "debt_stress_index_pct": round(stress_index, 1),
        "debt_stress_level": stress_level
    }

async def calculate_cashflow_stability(db: aiosqlite.Connection, user_id: int) -> dict:
    """Calculate income stability (coefficient of variation of weekly income over 90 days)."""
    now_utc = datetime.now(timezone.utc)
    start_dt = now_utc - timedelta(days=90)
    
    cur = await db.execute(
        "SELECT ts, amount FROM transactions WHERE user_id=? AND type='income' AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, start_dt.isoformat(), now_utc.isoformat())
    )
    rows = await cur.fetchall()
    
    if not rows:
        return {"stability_score": 0.0, "status": "no_income", "coefficient_of_variation": None}
        
    # Group by week index (0 to 12)
    weekly_incomes = [0] * 13
    for row in rows:
        ts = datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        week_idx = min(12, int((now_utc - ts).days // 7))
        weekly_incomes[week_idx] += int(row[1] or 0)
        
    mean_income = mean(weekly_incomes)
    if mean_income <= 0:
        return {"stability_score": 0.0, "status": "no_income", "coefficient_of_variation": None}
        
    std_dev = pstdev(weekly_incomes)
    cov = std_dev / mean_income
    
    # Convert COV to stability score (0 to 100). Higher COV means lower stability.
    # COV <= 0.1: extremely stable (100 score). COV >= 1.0: extremely unstable (0 score).
    stability_score = max(0.0, min(100.0, (1.0 - cov) * 100.0))
    
    status = "stable"
    if cov > 0.6:
        status = "highly_volatile"
    elif cov > 0.3:
        status = "volatile"
        
    return {
        "weekly_incomes": [int(x) for x in weekly_incomes],
        "coefficient_of_variation": round(cov, 3),
        "stability_score": round(stability_score, 1),
        "status": status
    }

async def calculate_impulse_spending_score(db: aiosqlite.Connection, user_id: int, tz_name: str) -> dict:
    """Analyze impulse spending based on timing (night/weekends) and categories."""
    now_utc = datetime.now(timezone.utc)
    start_dt = now_utc - timedelta(days=30)
    tz = _safe_tz(tz_name)
    
    # Fetch all expenses in the last 30 days
    cur = await db.execute(
        """
        SELECT t.ts, t.amount, COALESCE(c.name, '') as cat_name
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE t.user_id=? AND t.type='expense' AND t.ts>=? AND t.ts<? AND t.deleted_at IS NULL
        """,
        (user_id, start_dt.isoformat(), now_utc.isoformat())
    )
    rows = await cur.fetchall()
    
    if not rows:
        return {"impulse_score": 0.0, "weekend_spend_pct": 0.0, "night_spend_pct": 0.0}
        
    total_spend = 0
    weekend_spend = 0
    night_spend = 0
    impulse_category_spend = 0
    
    # Typical impulse categories (food delivery, games, shopping, taxi, cafe, fastfood)
    impulse_keywords = {"доставка", "фастфуд", "кафе", "ресторан", "развлечения", "шопинг", "игры", "такси", "food", "taxi", "shopping", "cafe"}
    
    for row in rows:
        ts_str = row[0]
        amount = int(-row[1])
        cat = str(row[2]).lower()
        
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).astimezone(tz)
        except Exception:
            dt = datetime.now(tz)
            
        total_spend += amount
        
        # Night spending (20:00 - 05:00)
        if dt.hour >= 20 or dt.hour < 5:
            night_spend += amount
            
        # Weekend spending
        if dt.weekday() >= 5:
            weekend_spend += amount
            
        # Category check
        if any(kw in cat for kw in impulse_keywords):
            impulse_category_spend += amount
            
    # Calculate percentages
    weekend_pct = (weekend_spend / total_spend) * 100.0 if total_spend > 0 else 0.0
    night_pct = (night_spend / total_spend) * 100.0 if total_spend > 0 else 0.0
    category_pct = (impulse_category_spend / total_spend) * 100.0 if total_spend > 0 else 0.0
    
    # Combined score (weighted average of indicators)
    # Night: weight 0.4, Weekend: weight 0.2, Category: weight 0.4
    score = (night_pct * 0.4) + (weekend_pct * 0.2) + (category_pct * 0.4)
    score = max(0.0, min(100.0, score))
    
    return {
        "total_spend": total_spend,
        "weekend_spend_pct": round(weekend_pct, 1),
        "night_spend_pct": round(night_pct, 1),
        "impulse_category_spend_pct": round(category_pct, 1),
        "impulse_score": round(score, 1)
    }

async def calculate_subscription_load(db: aiosqlite.Connection, user_id: int) -> dict:
    """Calculate subscription and fixed cost load compared to average monthly income."""
    # Monthly income avg
    now_utc = datetime.now(timezone.utc)
    start_dt = now_utc - timedelta(days=90)
    
    cur = await db.execute(
        "SELECT SUM(amount) FROM transactions WHERE user_id=? AND type='income' AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, start_dt.isoformat(), now_utc.isoformat())
    )
    row = await cur.fetchone()
    income_90 = int(row[0] or 0)
    monthly_income = (income_90 / 3) if income_90 > 0 else 0
    
    # Active recurring expenses (monthly sum)
    cur = await db.execute(
        "SELECT SUM(amount) FROM recurring_expenses WHERE user_id=? AND is_archived=0",
        (user_id,)
    )
    row = await cur.fetchone()
    recurring_expenses_sum = int(row[0] or 0)
    
    load_pct = 0.0
    if monthly_income > 0:
        load_pct = (recurring_expenses_sum / monthly_income) * 100.0
        
    return {
        "monthly_recurring_expenses": recurring_expenses_sum,
        "monthly_income_avg": int(round(monthly_income)),
        "subscription_load_pct": round(load_pct, 1)
    }


# ---------------------------------------------------------------------------
# Transaction Tiering: Clean Daily Burn Rate (CDBR)
# ---------------------------------------------------------------------------

async def calculate_clean_daily_burn_rate(
    db: aiosqlite.Connection, user_id: int, days: int = 30
) -> dict:
    """Calculate Clean Daily Burn Rate using ONLY routine-tier expenses.

    Obligations (rent, subscriptions, loans) and anomalies (one-off large
    purchases) are excluded so the result reflects true daily operational
    spending velocity.
    """
    now_utc = datetime.now(timezone.utc)
    start_dt = now_utc - timedelta(days=days)

    # Routine-only expenses (tier='routine')
    cur = await db.execute(
        "SELECT SUM(-amount) FROM transactions "
        "WHERE user_id=? AND type='expense' AND tier='routine' "
        "AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, start_dt.isoformat(), now_utc.isoformat()),
    )
    row = await cur.fetchone()
    routine_total = int(row[0] or 0)

    # Total expenses (all tiers) for comparison
    cur = await db.execute(
        "SELECT SUM(-amount) FROM transactions "
        "WHERE user_id=? AND type='expense' "
        "AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, start_dt.isoformat(), now_utc.isoformat()),
    )
    row = await cur.fetchone()
    all_total = int(row[0] or 0)

    # Obligation-only expenses
    cur = await db.execute(
        "SELECT SUM(-amount) FROM transactions "
        "WHERE user_id=? AND type='expense' AND tier='obligation' "
        "AND ts>=? AND ts<? AND deleted_at IS NULL",
        (user_id, start_dt.isoformat(), now_utc.isoformat()),
    )
    row = await cur.fetchone()
    obligation_total = int(row[0] or 0)

    cdbr = routine_total / max(1, days)
    legacy_daily = all_total / max(1, days)

    return {
        "days_analyzed": days,
        "routine_total": routine_total,
        "obligation_total": obligation_total,
        "anomaly_total": max(0, all_total - routine_total - obligation_total),
        "all_total": all_total,
        "cdbr": int(round(cdbr)),
        "legacy_daily_burn": int(round(legacy_daily)),
        "obligation_daily_avg": int(round(obligation_total / max(1, days))),
    }


# ---------------------------------------------------------------------------
# Multicurrency Balance Conversion
# ---------------------------------------------------------------------------

async def convert_balances_to_base(
    db: aiosqlite.Connection, user_id: int
) -> dict:
    """Convert all account balances to the user's base currency.

    Returns both the converted total and per-currency breakdown.
    Falls back to raw summation if the exchange rate service is unavailable.
    """
    from app.domain.money import get_user_currency, get_scale, CURRENCY_SCALE

    base_currency = await get_user_currency(db, user_id)
    base_scale = get_scale(base_currency)

    cur = await db.execute(
        "SELECT id, name, balance, currency, is_saving, is_archived "
        "FROM accounts WHERE user_id=? AND is_archived=0",
        (user_id,),
    )
    accounts = await cur.fetchall()

    liquid_base = 0
    saving_base = 0
    raw_liquid = 0
    raw_saving = 0
    per_currency: dict[str, int] = {}
    conversion_errors: list[str] = []

    for acc in accounts:
        _id, _name, balance, acc_currency, is_saving, _archived = acc
        balance = int(balance or 0)
        acc_currency = (acc_currency or base_currency).upper()

        # Track raw (unconverted) totals
        if is_saving:
            raw_saving += balance
        else:
            raw_liquid += balance

        # Track per-currency totals
        per_currency[acc_currency] = per_currency.get(acc_currency, 0) + balance

        # Convert to base currency
        if acc_currency == base_currency:
            converted = balance
        else:
            try:
                from app.services.currency import get_exchange_rate
                rate = await get_exchange_rate(acc_currency, base_currency)
                acc_scale = get_scale(acc_currency)
                # Convert: (balance / acc_scale) * rate * base_scale
                converted = int(round((balance / max(1, acc_scale)) * rate * base_scale))
            except Exception as e:
                conversion_errors.append(f"{acc_currency}: {e}")
                # Fallback: use raw value (imprecise but non-blocking)
                converted = balance

        if is_saving:
            saving_base += converted
        else:
            liquid_base += converted

    return {
        "base_currency": base_currency,
        "liquid_balance_base": liquid_base,
        "saving_balance_base": saving_base,
        "total_balance_base": liquid_base + saving_base,
        "raw_liquid_balance": raw_liquid,
        "raw_saving_balance": raw_saving,
        "per_currency": per_currency,
        "conversion_errors": conversion_errors,
        "has_multi_currency": len(per_currency) > 1,
    }


# ---------------------------------------------------------------------------
# Dual Runway Metrics
# ---------------------------------------------------------------------------

async def calculate_operational_runway(
    db: aiosqlite.Connection, user_id: int, days: int = 30
) -> dict:
    """Operational Runway (R_op): days until liquid funds exhaustion.

    Uses CDBR (routine expenses only) plus daily-amortized obligations
    in the denominator.  Excludes saving accounts from the numerator.
    """
    cdbr_data = await calculate_clean_daily_burn_rate(db, user_id, days)
    balances = await convert_balances_to_base(db, user_id)

    cdbr = cdbr_data["cdbr"]
    obligation_daily = cdbr_data["obligation_daily_avg"]
    daily_total = cdbr + obligation_daily

    liquid = balances["liquid_balance_base"]

    runway_op = None
    if daily_total > 0:
        runway_op = int(liquid / daily_total)

    return {
        "runway_operational_days": runway_op,
        "liquid_balance_base": liquid,
        "cdbr": cdbr,
        "obligation_daily_avg": obligation_daily,
        "daily_total_burn": daily_total,
        "base_currency": balances["base_currency"],
    }


async def calculate_full_runway(
    db: aiosqlite.Connection, user_id: int, days: int = 30
) -> dict:
    """Full Runway (R_full): days until ALL funds exhaustion.

    Includes saving accounts in the numerator to show absolute survival limit.
    """
    cdbr_data = await calculate_clean_daily_burn_rate(db, user_id, days)
    balances = await convert_balances_to_base(db, user_id)

    cdbr = cdbr_data["cdbr"]
    obligation_daily = cdbr_data["obligation_daily_avg"]
    daily_total = cdbr + obligation_daily

    total = balances["total_balance_base"]

    runway_full = None
    if daily_total > 0:
        runway_full = int(total / daily_total)

    return {
        "runway_full_days": runway_full,
        "total_balance_base": total,
        "cdbr": cdbr,
        "obligation_daily_avg": obligation_daily,
        "daily_total_burn": daily_total,
        "base_currency": balances["base_currency"],
    }


# ---------------------------------------------------------------------------
# Aggregated Financial Metrics (updated with tiering)
# ---------------------------------------------------------------------------

async def calculate_financial_metrics(db: aiosqlite.Connection, user_id: int, tz_name: str) -> dict:
    """Compile all financial metrics into a single aggregated object."""
    burn = await calculate_burn_rate(db, user_id, tz_name)
    savings = await calculate_savings_rate(db, user_id)
    debts = await calculate_debt_stress_index(db, user_id)
    stability = await calculate_cashflow_stability(db, user_id)
    impulse = await calculate_impulse_spending_score(db, user_id, tz_name)
    subs = await calculate_subscription_load(db, user_id)

    # --- New tiered metrics ---
    cdbr_data = await calculate_clean_daily_burn_rate(db, user_id)
    balances = await convert_balances_to_base(db, user_id)
    runway_op = await calculate_operational_runway(db, user_id)
    runway_full = await calculate_full_runway(db, user_id)

    # Legacy runway for backward compatibility
    total_liquid_balance = balances["liquid_balance_base"]
    daily_burn = burn["daily_burn_rate"]
    legacy_runway_days = None
    if daily_burn > 0:
        legacy_runway_days = int(total_liquid_balance / daily_burn)

    return {
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        # Legacy fields (backward compatible)
        "liquid_balance": total_liquid_balance,
        "runway_days": legacy_runway_days,
        "burn_rate": burn,
        "savings_rate": savings,
        "debt_stress": debts,
        "cashflow_stability": stability,
        "impulse_spending": impulse,
        "subscription_load": subs,
        # New tiered metrics
        "cdbr": cdbr_data,
        "balances": balances,
        "runway_operational": runway_op,
        "runway_full": runway_full,
    }


async def get_robust_category_anomalies(
    db: aiosqlite.Connection, user_id: int, category_id: int, limit: int = 20
) -> list[dict]:
    """Find anomalies in a specific category using Robust Z-Score (MAD).

    Returns a list of detected anomalies.
    """
    cur = await db.execute(
        "SELECT id, amount, note, ts, tier FROM transactions "
        "WHERE user_id=? AND category_id=? AND type='expense' AND deleted_at IS NULL "
        "ORDER BY ts DESC, id DESC LIMIT ?",
        (user_id, category_id, limit),
    )
    rows = await cur.fetchall()
    if not rows or len(rows) < 3:
        return []

    # Amounts are stored as negative numbers for expenses. Convert to positive.
    vals = [-r[1] for r in rows]

    # Calculate median
    sorted_vals = sorted(vals)
    n = len(sorted_vals)
    if n % 2 == 1:
        median_val = sorted_vals[n // 2]
    else:
        median_val = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0

    # Calculate Median Absolute Deviation (MAD)
    devs = [abs(v - median_val) for v in vals]
    sorted_devs = sorted(devs)
    if n % 2 == 1:
        median_dev = sorted_devs[n // 2]
    else:
        median_dev = (sorted_devs[n // 2 - 1] + sorted_devs[n // 2]) / 2.0

    anomalies = []
    for row in rows:
        tx_id, amount, note, ts, tier = row
        val = -amount
        if val <= 0:
            continue

        # Calculate Robust Z-Score
        if median_dev > 0:
            z_score = 0.6745 * (val - median_val) / median_dev
        else:
            z_score = float("inf") if val > median_val else 0.0

        if z_score > 3.0 and val > 3 * median_val:
            anomalies.append({
                "id": tx_id,
                "amount": val,
                "note": note,
                "ts": ts,
                "tier": tier,
                "z_score": z_score,
                "median": median_val,
            })

    return anomalies


