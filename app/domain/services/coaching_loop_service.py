from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import aiosqlite
from aiogram import Bot
from loguru import logger

from app.db.connection import get_db
from app.db.repositories.settings_repo import get_timezone
from app.domain.services.financial_analysis_engine import calculate_financial_metrics

def get_metric_value(metrics: dict, name: str) -> float | None:
    """Helper to extract a metric value from the metrics dictionary by name."""
    if name in ("delivery_spend_weekly", "impulse_category_spend_pct"):
        return metrics["impulse_spending"]["impulse_category_spend_pct"]
    if name == "impulse_score":
        return metrics["impulse_spending"]["impulse_score"]
    if name == "savings_rate_pct":
        return metrics["savings_rate"]["savings_rate_pct"]
    if name == "weekly_burn_rate":
        return float(metrics["burn_rate"]["weekly_burn_rate"])
    if name == "daily_burn_rate":
        return float(metrics["burn_rate"]["daily_burn_rate"])
    if name == "debt_stress_index_pct":
        return metrics["debt_stress"]["debt_stress_index_pct"]
    return None

def is_goal_achieved(metric_name: str, current_val: float, goal_val: float) -> bool:
    """Determine achievement based on metric type (lower is better for expenses/debt, higher is better for savings)."""
    # Lower is better metrics
    lower_better = ("delivery_spend_weekly", "impulse_category_spend_pct", "impulse_score", "weekly_burn_rate", "daily_burn_rate", "debt_stress_index_pct")
    if metric_name in lower_better:
        return current_val <= goal_val
    # Higher is better metrics (savings rate)
    return current_val >= goal_val

async def evaluate_active_recommendations(bot: Bot) -> None:
    """Scan and evaluate active AI recommendations for all users."""
    logger.info("Starting evaluation of active AI recommendations...")
    now_utc = datetime.now(timezone.utc)
    
    try:
        async with get_db() as db:
            # Get recommendations that were sent and are ready for evaluation (created > 6 days ago or weekly evaluation)
            cur = await db.execute(
                """
                SELECT id, user_id, recommendation_type, message_text, target_metric_name, 
                       target_metric_start_value, target_metric_goal_value, created_at 
                FROM ai_recommendations_log 
                WHERE status='sent'
                """
            )
            recs = await cur.fetchall()
            
            for rec in recs:
                rec_id, user_id, rec_type, msg_text, metric_name, start_val, goal_val, created_str = rec
                
                # Check if at least 5 days have passed since creation to give user time to act
                created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                if now_utc - created_at < timedelta(days=5):
                    continue
                    
                # Calculate current metrics
                tz_name = await get_timezone(db, user_id) or "Asia/Aqtobe"
                metrics = await calculate_financial_metrics(db, user_id, tz_name)
                
                curr_val = get_metric_value(metrics, metric_name)
                if curr_val is None:
                    # Metric not found or invalid, mark as evaluated/ignored
                    await db.execute(
                        "UPDATE ai_recommendations_log SET status='ignored', evaluated_at=? WHERE id=?",
                        (now_utc.isoformat(), rec_id)
                    )
                    continue
                    
                achieved = is_goal_achieved(metric_name, curr_val, goal_val)
                new_status = "succeeded" if achieved else "failed"
                
                # Update status
                await db.execute(
                    "UPDATE ai_recommendations_log SET status=?, evaluated_at=? WHERE id=?",
                    (new_status, now_utc.isoformat(), rec_id)
                )
                
                # Adjust discipline score in user profile
                score_delta = 10 if achieved else -5
                await db.execute(
                    """
                    INSERT INTO ai_profile (user_id, discipline_score, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        discipline_score = MAX(20, MIN(100, discipline_score + excluded.discipline_score)),
                        updated_at = excluded.updated_at
                    """,
                    (user_id, score_delta, now_utc.isoformat())
                )
                
                # Notify the user
                try:
                    if achieved:
                        notify_text = (
                            f"🎉 <b>Финансовый триумф!</b>\n\n"
                            f"Вы успешно выполнили рекомендацию AI:\n"
                            f"«<i>{msg_text}</i>»\n\n"
                            f"📈 Ваша финансовая дисциплина растёт! Так держать."
                        )
                    else:
                        notify_text = (
                            f"📉 <b>Анализ цели</b>\n\n"
                            f"Не удалось полностью достичь цели по рекомендации:\n"
                            f"«<i>{msg_text}</i>»\n\n"
                            f"Текущее значение: <b>{curr_val:.1f}</b> (цель: <b>{goal_val:.1f}</b>).\n"
                            f"Ничего страшного, мы скорректируем стратегию в следующем отчёте."
                        )
                    
                    await bot.send_message(chat_id=user_id, text=notify_text, parse_mode="HTML")
                except Exception as send_err:
                    logger.warning(f"Could not send coaching feedback to user {user_id}: {send_err}")
                    
            await db.commit()
            
    except Exception as e:
        logger.exception(f"Error in evaluate_active_recommendations job: {e}")
