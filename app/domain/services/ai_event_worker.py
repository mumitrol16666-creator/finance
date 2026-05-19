from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import aiosqlite
from loguru import logger

from app.db.connection import get_db
from app.db.repositories.settings_repo import get_timezone
from app.domain.services.financial_analysis_engine import calculate_financial_metrics

async def trigger_background_ai_analysis(user_id: int) -> None:
    """Fires a non-blocking background task to analyze the user's financial profile."""
    # Spawn background task
    asyncio.create_task(_run_analysis_safe(user_id))

async def _run_analysis_safe(user_id: int) -> None:
    try:
        await asyncio.sleep(0.1)  # Give time for the calling transaction to commit
        async with get_db() as db:
            await analyze_and_update_profile(db, user_id)
    except Exception as e:
        logger.exception(f"Background AI analysis failed for user {user_id}: {e}")

async def analyze_and_update_profile(db: aiosqlite.Connection, user_id: int) -> None:
    tz_name = await get_timezone(db, user_id) or "Asia/Aqtobe"
    metrics = await calculate_financial_metrics(db, user_id, tz_name)
    
    # 1. Determine user stage based on metrics
    savings_rate = metrics["savings_rate"]["savings_rate_pct"]
    impulse_score = metrics["impulse_spending"]["impulse_score"]
    debt_stress = metrics["debt_stress"]["debt_stress_index_pct"]
    liquid_balance = metrics["liquid_balance"]
    runway = metrics["runway_days"]
    
    # Simple state machine for user stage
    if savings_rate < 0 or impulse_score > 60:
        stage = "chaotic"
    elif runway is not None and runway > 90 and savings_rate > 15:
        stage = "budgeting"
    elif runway is not None and runway > 180 and savings_rate > 25:
        stage = "investing"
    else:
        stage = "stabilizing"
        
    # Generate profile behavioral summary snippet
    summaries = []
    if impulse_score > 40:
        summaries.append("склонен к импульсивным тратам")
    if savings_rate < 5:
        summaries.append("практически не откладывает средства")
    elif savings_rate > 20:
        summaries.append("активно формирует сбережения")
    if debt_stress > 30:
        summaries.append("имеет высокую долговую нагрузку")
    if runway is not None and runway < 30:
        summaries.append("минимальный запас прочности")
        
    summary_text = "Пользователь " + (", ".join(summaries) if summaries else "ведёт стабильный и сбалансированный бюджет")
    
    # Upsert to ai_profile
    now_str = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """
        INSERT INTO ai_profile (user_id, user_stage, behavioral_summary, discipline_score, preferred_budgeting_type, updated_at)
        VALUES (?, ?, ?, 100, 'weekly', ?)
        ON CONFLICT(user_id) DO UPDATE SET
            user_stage=excluded.user_stage,
            behavioral_summary=excluded.behavioral_summary,
            updated_at=excluded.updated_at
        """,
        (user_id, stage, summary_text, now_str)
    )
    
    # 2. Update and insert individual insights
    insights = []
    
    # Insight: negative savings rate
    if savings_rate < 0:
        insights.append((
            "negative_savings",
            "⚠️ Расходы превышают ваши доходы за последние 30 дней. Баланс постепенно уменьшается.",
            0.9
        ))
        
    # Insight: impulse spending
    if impulse_score > 45:
        insights.append((
            "impulse_spending",
            f"🛒 Замечен высокий уровень импульсивных трат (доля вечерних покупок и трат на такси/доставку составляет {metrics['impulse_spending']['impulse_category_spend_pct']}%).",
            0.8
        ))
        
    # Insight: runway alert
    if runway is not None and runway < 14 and metrics["burn_rate"]["daily_burn_rate"] > 0:
        insights.append((
            "low_runway",
            f"🚨 Финансовый запас прочности критически мал: при текущих расходах средств хватит менее чем на {runway} дн.",
            0.95
        ))
        
    # Insight: high debt load
    if debt_stress > 30:
        insights.append((
            "high_debt_stress",
            f"📈 Высокая долговая нагрузка: ежемесячные платежи по долгам забирают {debt_stress}% вашего среднего дохода.",
            0.9
        ))

    # Clean old insights and insert new ones
    # For each rule, update if active, otherwise insert
    for key, text, confidence in insights:
        # Check if already exists and is active
        cur = await db.execute(
            "SELECT id FROM ai_insights WHERE user_id=? AND insight_key=? AND status='active'",
            (user_id, key)
        )
        row = await cur.fetchone()
        if row:
            # Update the text and timestamp
            await db.execute(
                "UPDATE ai_insights SET insight_text=?, confidence=?, detected_at=? WHERE id=?",
                (text, confidence, now_str, row[0])
            )
        else:
            # Insert new
            await db.execute(
                """
                INSERT INTO ai_insights (user_id, insight_key, insight_text, confidence, detected_at, status)
                VALUES (?, ?, ?, ?, ?, 'active')
                """,
                (user_id, key, text, confidence, now_str)
            )
            
    # Mark old insights as archived if they no longer apply
    active_keys = [x[0] for x in insights]
    if active_keys:
        placeholders = ",".join("?" for _ in active_keys)
        await db.execute(
            f"UPDATE ai_insights SET status='archived' WHERE user_id=? AND status='active' AND insight_key NOT IN ({placeholders})",
            (user_id, *active_keys)
        )
    else:
        await db.execute(
            "UPDATE ai_insights SET status='archived' WHERE user_id=? AND status='active'",
            (user_id,)
        )
        
    await db.commit()
    logger.info(f"AI profile and insights updated successfully for user {user_id}")
