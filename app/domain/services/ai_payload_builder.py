"""
AI Payload Builder — separated, sanitized, compressed payload for LLM.

Extracted from ai_llm_service._build_payload() to keep responsibilities clean:
  - _build_core_metrics()        — income/expense/net/balance/runway
  - _build_trend_signals()       — weekly trends, direction, compressed summary
  - _build_behavioral_signals()  — spending patterns, contradictions, seasonality
  - _build_risk_signals()        — unusual spikes, importance signals, confidence
  - _build_financial_scores()    — future-ready aggregate scores
  - _sanitize_payload()          — strip None/NaN/empty/long strings
  - _compress_payload()          — progressive trimming to fit token budget
  - build_llm_payload()          — main entry point
"""
from __future__ import annotations

import copy
import json
import math
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------
MAX_CONTEXT_CHARS = 35_000  # ~8 750 tokens at ~4 chars/token


# ───────────────────────────────────────────────────────────────────────────
# 1. Separate payload builders
# ───────────────────────────────────────────────────────────────────────────

def _build_core_metrics(context: dict[str, Any]) -> dict[str, Any]:
    """Income / expense / net / balance / runway / projection / accounts."""
    current = context.get("current") or {}
    previous = context.get("previous") or {}
    month = context.get("month") or {}
    return {
        "current": {
            "income": current.get("income", 0),
            "expense": current.get("expense", 0),
            "net": current.get("net", 0),
            "tx_count": current.get("tx_count", 0),
            "expense_tx_count": current.get("expense_tx_count", 0),
            "top_categories": current.get("top_categories", [])[:6],
        },
        "previous": {
            "income": previous.get("income", 0),
            "expense": previous.get("expense", 0),
            "net": previous.get("net", 0),
            "top_categories": previous.get("top_categories", [])[:6],
        },
        "month": {
            "income": month.get("income", 0),
            "expense": month.get("expense", 0),
            "net": month.get("net", 0),
        },
        "projection": {
            "projected_month_income": context.get("projected_month_income"),
            "projected_month_expense": context.get("projected_month_expense"),
            "projected_free_cash": context.get("projected_free_cash"),
            "projected_required_free_cash": context.get("projected_required_free_cash"),
        },
        "accounts": {
            "total_balance": context.get("total_balance"),
            "runway_days": context.get("runway_days"),
            "active_accounts": (
                [dict(r) for r in context.get("active_accounts", [])[:6]]
                if context.get("active_accounts")
                else []
            ),
        },
    }


def _build_tiered_metrics(context: dict[str, Any]) -> dict[str, Any]:
    """Extract transaction tiering metrics: CDBR, dual runway, multicurrency."""
    metrics = context.get("financial_metrics") or {}
    cdbr_data = metrics.get("cdbr") or {}
    balances = metrics.get("balances") or {}
    runway_op = metrics.get("runway_operational") or {}
    runway_full = metrics.get("runway_full") or {}

    return {
        "tiered_burn_rate": {
            "clean_daily_burn_rate": cdbr_data.get("cdbr"),
            "routine_total_30d": cdbr_data.get("routine_total"),
            "obligation_total_30d": cdbr_data.get("obligation_total"),
            "anomaly_total_30d": cdbr_data.get("anomaly_total"),
            "legacy_daily_burn": cdbr_data.get("legacy_daily_burn"),
        },
        "runway": {
            "operational_days": runway_op.get("runway_operational_days"),
            "full_days": runway_full.get("runway_full_days"),
            "base_currency": balances.get("base_currency"),
            "has_multi_currency": balances.get("has_multi_currency", False),
        },
        "balances_converted": {
            "liquid_base": balances.get("liquid_balance_base"),
            "saving_base": balances.get("saving_balance_base"),
            "total_base": balances.get("total_balance_base"),
        },
    }


def _build_trend_signals(context: dict[str, Any]) -> dict[str, Any]:
    """Weekly trends, trend direction, compressed summary, month history."""
    return {
        "weekly_trends": context.get("weekly_trends", []),
        "trend_direction": context.get("trend_direction", {}),
        "compressed_summary": context.get("compressed_summary", {}),
        "month_history": context.get("month_history", []),
        "category_deltas": context.get("category_deltas", [])[:8],
    }


def _build_behavioral_signals(context: dict[str, Any]) -> dict[str, Any]:
    """Spending patterns, contradictions, seasonality."""
    return {
        "spending_patterns": context.get("spending_patterns"),
        "potential_contradictions": context.get("potential_contradictions"),
        "seasonality": context.get("seasonality"),
    }


def _build_risk_signals(context: dict[str, Any]) -> dict[str, Any]:
    """Unusual spikes, importance signals, analysis confidence."""
    return {
        "unusual_spikes": context.get("unusual_spikes", []),
        "importance_signals": context.get("importance_signals", []),
        "analysis_confidence": context.get("analysis_confidence"),
    }


# ───────────────────────────────────────────────────────────────────────────
# 2. Future-ready financial scores (point 10)
# ───────────────────────────────────────────────────────────────────────────

def _build_financial_scores(context: dict[str, Any]) -> dict[str, Any]:
    """Aggregate financial scores. Some are placeholders for future dev."""
    current = context.get("current") or {}
    ai_profile = context.get("ai_profile") or {}
    runway_days = context.get("runway_days")
    income = current.get("income", 0)
    expense = current.get("expense", 0)

    overspending = round(expense / income * 100, 1) if income > 0 else None

    if runway_days is None:
        burn_risk = None
    elif runway_days < 14:
        burn_risk = "high"
    elif runway_days < 30:
        burn_risk = "medium"
    else:
        burn_risk = "low"

    return {
        "overspending_ratio": overspending,
        "burn_rate_risk": burn_risk,
        "discipline_score": ai_profile.get("discipline_score"),
        "behavioral_profile": ai_profile.get("behavioral_summary"),
        "financial_stability_score": None,   # TODO: implement
        "goal_alignment_score": None,        # TODO: implement
    }


# ───────────────────────────────────────────────────────────────────────────
# 3. Payload sanitation (point 5)
# ───────────────────────────────────────────────────────────────────────────

_MAX_STR_LEN = 120


def _sanitize_payload(payload: dict) -> dict:
    """Remove None, NaN, empty containers, and overly long strings."""
    result = _sanitize_value(payload)
    return result if isinstance(result, dict) else {}


def _sanitize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, str):
        if not value:
            return None
        return value[:_MAX_STR_LEN - 3] + "..." if len(value) > _MAX_STR_LEN else value
    if isinstance(value, list):
        cleaned = [_sanitize_value(item) for item in value]
        cleaned = [item for item in cleaned if item is not None]
        return cleaned if cleaned else None
    if isinstance(value, dict):
        cleaned = {}
        for k, v in value.items():
            sv = _sanitize_value(v)
            if sv is not None:
                cleaned[k] = sv
        return cleaned if cleaned else None
    # int, bool, etc. — pass through
    return value


# ───────────────────────────────────────────────────────────────────────────
# 4. Token budget guard (point 2)
# ───────────────────────────────────────────────────────────────────────────

def _compress_payload(payload: dict) -> dict:
    """Progressively shrink payload until it fits MAX_CONTEXT_CHARS."""
    payload = copy.deepcopy(payload)

    steps = [
        lambda p: _trim_key(p, "recent_transactions", 30),
        lambda p: _trim_key(p, "recent_transactions", 15),
        lambda p: _trim_list_key(p, "month_history", 3),
        lambda p: _trim_nested(p, "current", "top_categories", 4),
        lambda p: _trim_nested(p, "previous", "top_categories", 3),
        lambda p: _drop_key(p, "ai_recommendations"),
        lambda p: _drop_key(p, "compressed_summary"),
        lambda p: _drop_key(p, "category_deltas"),
        lambda p: _drop_key(p, "planned_operations"),
    ]

    for step in steps:
        if len(json.dumps(payload, ensure_ascii=False)) <= MAX_CONTEXT_CHARS:
            return payload
        step(payload)

    return payload


def _trim_key(p: dict, key: str, max_items: int) -> None:
    if key in p and isinstance(p[key], list):
        p[key] = p[key][-max_items:]


def _trim_list_key(p: dict, key: str, max_items: int) -> None:
    if key in p and isinstance(p[key], list):
        p[key] = p[key][-max_items:]


def _trim_nested(p: dict, outer: str, inner: str, max_items: int) -> None:
    if outer in p and isinstance(p[outer], dict) and inner in p[outer]:
        if isinstance(p[outer][inner], list):
            p[outer][inner] = p[outer][inner][:max_items]


def _drop_key(p: dict, key: str) -> None:
    p.pop(key, None)


# ───────────────────────────────────────────────────────────────────────────
# 5. Main entry point
# ───────────────────────────────────────────────────────────────────────────

def build_llm_payload(context: dict[str, Any]) -> dict[str, Any]:
    """Build, sanitize and compress the full LLM payload."""
    meta = context.get("meta")

    # Transaction list
    tx_list = []
    if context.get("current_rows"):
        for r in context["current_rows"][-60:]:
            tx_type = r["type"]
            raw_amount = int(r["amount"] or 0)
            amount = abs(raw_amount) if tx_type in ("income", "expense") else raw_amount
            tx_list.append({
                "date": r["ts"][:10] if r["ts"] else "",
                "type": tx_type,
                "amount": amount,
                "category": r["category_name"],
                "note": r["note"],
            })

    core = _build_core_metrics(context)

    payload: dict[str, Any] = {
        "goal_text": context.get("goal_text"),
        "goal_amount": context.get("goal_amount"),
        "currency": context.get("currency") or "KZT",
        "period": meta.kind if meta else None,
        "period_title": meta.title if meta else None,
        "recent_transactions": tx_list,
        "data_quality": context.get("data_quality") or {},
        "clarification_note": (context.get("clarification_note") or {}).get("content"),
        **core,
        "budgets": context.get("budget_snapshot"),
        "debts": context.get("debt_snapshot"),
        "recurring_expenses": context.get("recurring_snapshot"),
        "recurring_incomes": context.get("recurring_income_snapshot"),
        "planned_operations": context.get("planned_snapshot"),
        "financial_metrics": context.get("financial_metrics"),
        "ai_profile": context.get("ai_profile"),
        "ai_insights": context.get("ai_insights"),
        "ai_priority_insights": context.get("ai_priority_insights"),
        "ai_recommendations": context.get("ai_recommendations"),
        "financial_scores": _build_financial_scores(context),
        **_build_tiered_metrics(context),
    }

    # Trend / behavioral / risk signals
    payload.update(_build_trend_signals(context))
    payload.update(_build_behavioral_signals(context))
    payload.update(_build_risk_signals(context))

    # Sanitize → Compress
    payload = _sanitize_payload(payload)
    payload = _compress_payload(payload)

    final_len = len(json.dumps(payload, ensure_ascii=False))
    logger.debug("LLM payload: {} chars (~{} tokens)", final_len, final_len // 4)

    return payload
