from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from loguru import logger

from app.domain.services.ai_consultant_service import (
    render_ai_insufficient_report,
    render_ai_question_answer,
    render_ai_report,
    render_ai_report_download,
)
from app.integrations.openai_client import get_openai_client, get_openai_model, has_openai_key

USE_ADVANCED_AI_REPORTS = True

_ALLOWED_TAGS = {"b", "i", "code", "pre", "u", "s", "ins", "del", "strong", "em"}


def sanitize_telegram_html(text: str) -> str:
    if not text:
        return ""
    text = (
        text.replace("<br>", "\n")
        .replace("<br/>", "\n")
        .replace("<br />", "\n")
        .replace("<strong>", "<b>")
        .replace("</strong>", "</b>")
        .replace("<em>", "<i>")
        .replace("</em>", "</i>")
    )

    def repl(match: re.Match[str]) -> str:
        slash, tag = match.group(1), match.group(2).lower()
        if tag in _ALLOWED_TAGS:
            if tag == "strong":
                tag = "b"
            elif tag == "em":
                tag = "i"
            return f"<{slash}{tag}>"
        return ""

    text = re.sub(r"<(/?)([a-zA-Z0-9]+)(?:\s[^>]*)?>", repl, text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


SYSTEM_PROMPT_REPORT = """
Ты — элитный AI-аналитик по личным финансам. Твоя задача — провести глубокий и объективный анализ финансового состояния пользователя, выявить скрытые взаимосвязи, аномалии и риски на основе предоставленных данных.

ПРИОРИТЕТ АНАЛИЗА:
1. Долгосрочные тренды и движение капитала
2. Повторяющиеся паттерны поведения (behavioral patterns)
3. Рост обязательных расходов и просадка свободных денег (lifestyle inflation)
4. Аномалии и разовые крупные траты (spikes)

ИНСТРУКЦИИ ПО АНАЛИЗУ:
- Основной фокус должен быть на main_problem из 'ai_priority_insights', однако ты можешь и должен самостоятельно выявлять скрытые закономерности, аномалии, сезонность, ухудшение финансовой устойчивости, долгосрочные риски и противоречия между целями и поведением на основе всей предоставленной истории, недельных трендов, спайков и сжатого резюме (compressed_summary).
- Анализируй противоречия: если доходы растут, а чистые сбережения падают (lifestyle inflation); или если установлена цель накопления, но растут траты на развлечения.
- Оценивай уровень уверенности своих выводов на основе 'analysis_confidence' (high, medium, low).

ПРАВИЛА БОРЬБЫ С ГАЛЛЮЦИНАЦИЯМИ И ВОДОЙ:
- Никогда не придумывай данные, которых нет в контексте.
- Не делай психологических выводов о личности пользователя и не пытайся угадать его эмоции.
- Не объясняй причины трат, если они не следуют напрямую из примечаний к транзакциям.
- Если вывод вероятностный — четко помечай его как гипотезу или предположение.
- Избегай мотивационной "воды", общих финансовых советов и повторений. Говори исключительно на языке цифр и фактов.
- Каждый блок отчета должен содержать максимум 3-5 информативных предложений.

СТРУКТУРА ОТЧЕТА:
🎯 <b>ЦЕЛЬ: [Название цели]</b>
- [Анализ прогресса к финансовой цели, оценка реалистичности достижения на основе прогнозов, оценка ETA (в месяцах) и главные препятствия к ее достижению]

📊 <b>АНАЛИЗ ТРЕНДОВ И ПАТТЕРНОВ</b>
- [Интерпретация недельной динамики, сезонности и крупных спайков с учетом их важности (importance_signals). Разбор поведенческих паттернов (spending_patterns) и объяснение противоречий (potential_contradictions) между поведением и целями]

💡 <b>РЕКОМЕНДАЦИИ</b>
- [Конкретные, выполнимые действия и реальные способы оптимизации бюджета, основанные на выявленных аномалиях или паттернах]

ПРАВИЛО РЕКОМЕНДАЦИЙ ДЛЯ СИСТЕМЫ:
В самом конце сообщения (после раздела рекомендаций) обязательно добавь скрытый блок рекомендаций для логирования в базу данных. Допускается только один блок [REC: ...]. Формат должен быть строго следующим (подставь реальные значения вместо плейсхолдеров):
[REC: type="descriptive_type_slug", target_metric="descriptive_metric_slug", start_val=15000, goal_val=10000, text="Текст рекомендации"]
Где:
- type: краткий текстовый идентификатор действия (например, cut_delivery, reduce_clothing, increase_savings, reduce_credit)
- target_metric: метрика, на которую направлено действие (например, delivery_spend, clothing_spend, net_savings, monthly_expenses)
- start_val: текущее значение метрики
- goal_val: целевое значение метрики
- text: лаконичное описание действия на русском языке

Стиль: Строгий, аналитический, профессиональный. Используй только HTML-теги <b> и <i>, без Markdown (** или *).
""".strip()

SYSTEM_PROMPT_QUESTION = """
Ты отвечаешь на прямой финансовый вопрос пользователя по его данным.

Правила:
- отвечай только на базе переданного контекста
- если данных недостаточно для точного ответа, скажи это прямо
- не выдумывай цену, сроки, доходы, скрытые расходы и мотивы
- не обещай результат там, где база слабая
- отделяй то, что видно из данных, от предположений
- не используй HTML кроме <b>, <i>, <code>, <pre>

Формат:
<b>Что можно сказать сейчас</b>
<b>На чём это основано</b>
<b>Что мешает точности</b>
<b>Что делать дальше</b>
""".strip()


SYSTEM_PROMPT_QUICK_ADD = """
Ты — парсер финансовых транзакций. Твоя задача — извлечь список операций из текста пользователя.

ПРАВИЛА:
1. Верни ТОЛЬКО валидный JSON-массив объектов. Никакого лишнего текста.
2. Поля для каждого объекта:
   - "amount": число (целое, в минимальных единицах валюты, например 1000 для 1000 тенге)
   - "kind": "expense" или "income"
   - "category_hint": название категории (на языке пользователя)
   - "account_hint": название счета, если упоминается (например "каспи", "наличные")
   - "note": чистый комментарий (без суммы и категории)
   - "date_offset": число дней от сегодня (0 - сегодня, -1 - вчера, -2 - позавчера и т.д.)

ПРИМЕР:
Текст: "Вчера купил кофе 1200 и сегодня пришла зп 500000 на каспи"
Ответ:
[
  {"amount": 1200, "kind": "expense", "category_hint": "Кофе", "account_hint": null, "note": "кофе", "date_offset": -1},
  {"amount": 500000, "kind": "income", "category_hint": "Зарплата", "account_hint": "каспи", "note": "зп", "date_offset": 0}
]

Если сумм в тексте нет, верни пустой массив [].
""".strip()


def _build_payload(context: dict[str, Any]) -> dict[str, Any]:
    meta = context["meta"]
    current = context["current"]
    previous = context["previous"]
    month = context["month"]
    payload = {
        "goal_text": context.get("goal_text"),
        "goal_amount": context.get("goal_amount"),
        "currency": context.get("currency") or "KZT",
        "period": meta.kind,
        "period_title": meta.title,
        "data_quality": context.get("data_quality") or {},
        "clarification_note": (context.get("clarification_note") or {}).get("content"),
        "current": {
            "income": current["income"],
            "expense": current["expense"],
            "net": current["net"],
            "tx_count": current["tx_count"],
            "expense_tx_count": current["expense_tx_count"],
            "top_categories": current["top_categories"][:6],
        },
        "previous": {
            "income": previous["income"],
            "expense": previous["expense"],
            "net": previous["net"],
            "top_categories": previous["top_categories"][:6],
        },
        "month": {
            "income": month["income"],
            "expense": month["expense"],
            "net": month["net"],
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
            "active_accounts": [dict(r) for r in context.get("active_accounts", [])[:6]] if context.get("active_accounts") else [],
        },
        "budgets": context.get("budget_snapshot"),
        "debts": context.get("debt_snapshot"),
        "recurring_expenses": context.get("recurring_snapshot"),
        "recurring_incomes": context.get("recurring_income_snapshot"),
        "planned_operations": context.get("planned_snapshot"),
        "category_deltas": context.get("category_deltas", [])[:8],
        "month_history": context.get("month_history"),
        "financial_metrics": context.get("financial_metrics"),
        "ai_profile": context.get("ai_profile"),
        "ai_insights": context.get("ai_insights"),
        "ai_priority_insights": context.get("ai_priority_insights"),
        "ai_recommendations": context.get("ai_recommendations"),
    }

    if USE_ADVANCED_AI_REPORTS:
        payload.update({
            "weekly_trends": context.get("weekly_trends"),
            "unusual_spikes": context.get("unusual_spikes"),
            "trend_direction": context.get("trend_direction"),
            "compressed_summary": context.get("compressed_summary"),
            "importance_signals": context.get("importance_signals"),
            "spending_patterns": context.get("spending_patterns"),
            "potential_contradictions": context.get("potential_contradictions"),
            "seasonality": context.get("seasonality"),
            "analysis_confidence": context.get("analysis_confidence"),
        })

    return payload


def _build_report_prompt(context: dict[str, Any]) -> str:
    payload = _build_payload(context)
    payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
    logger.info(f"AI Report Payload JSON Size: {len(payload_str)} characters")
    return "Контекст:\n" + payload_str


def _build_question_prompt(context: dict[str, Any], question: str) -> str:
    payload = _build_payload(context)
    payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
    logger.info(f"AI Question Payload JSON Size: {len(payload_str)} characters")
    return (
        f"Вопрос пользователя:\n{question}\n\n"
        "Контекст по финансам:\n"
        + payload_str
    )


def _generate(system_prompt: str, user_prompt: str) -> str:
    client = get_openai_client()
    response = client.responses.create(
        model=get_openai_model(),
        temperature=0.4,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.output_text.strip()


def _generate_with_history(system_prompt: str, messages: list[dict[str, str]]) -> str:
    client = get_openai_client()
    payload = [{"role": "system", "content": system_prompt}] + messages
    response = client.responses.create(
        model=get_openai_model(),
        temperature=0.4,
        input=payload,
    )
    return response.output_text.strip()


async def render_final_ai_report(context: dict[str, Any]) -> tuple[str, str]:
    quality = context.get("data_quality") or {}
    if not quality.get("sufficient_for_deep_report"):
        text = render_ai_insufficient_report(context)
        return text, text.replace("<b>", "").replace("</b>", "")

    local_short = render_ai_report(context)
    local_download = render_ai_report_download(context)
    if not has_openai_key():
        return local_short, local_download

    try:
        llm_text = await asyncio.to_thread(_generate, SYSTEM_PROMPT_REPORT, _build_report_prompt(context))
    except Exception:
        return local_short, local_download

    # Parse and write recommendation to the database log
    user_id = context.get("user_id")
    if user_id and llm_text:
        match = re.search(
            r'\[REC:\s*type=["\']([^"\']+)["\'],\s*target_metric=["\']([^"\']+)["\'],\s*start_val=([0-9.-]+),\s*goal_val=([0-9.-]+),\s*text=["\']([^"\']+)["\']\]',
            llm_text
        )
        if match:
            rec_type, metric_name, start_val, goal_val, rec_text = match.groups()
            try:
                from app.db.connection import get_db
                from datetime import datetime, timezone
                async with get_db() as db:
                    now_str = datetime.now(timezone.utc).isoformat()
                    await db.execute(
                        """
                        INSERT INTO ai_recommendations_log 
                        (user_id, recommendation_type, message_text, target_metric_name, target_metric_start_value, target_metric_goal_value, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'sent', ?)
                        """,
                        (user_id, rec_type, rec_text, metric_name, float(start_val), float(goal_val), now_str)
                    )
                    await db.commit()
            except Exception as e:
                from loguru import logger
                logger.exception(f"Failed to log AI recommendation: {e}")
            
            # Clean recommendation tag from the LLM output
            llm_text = re.sub(
                r'\[REC:\s*type=["\'][^"\']+["\'],\s*target_metric=["\'][^"\']+["\'],\s*start_val=[0-9.-]+,\s*goal_val=[0-9.-]+,\s*text=["\'][^"\']+["\']\]',
                '',
                llm_text
            ).strip()

    llm_text = sanitize_telegram_html(llm_text)
    if not llm_text:
        return local_short, local_download
    return llm_text, llm_text + "\n\n" + ("─" * 32) + "\n\n" + local_download


async def render_final_ai_question(context: dict[str, Any], question: str, chat_history: list[dict[str, str]] | None = None) -> str:
    local_text = render_ai_question_answer(context, question)
    if not has_openai_key():
        return local_text
    try:
        messages = []
        if chat_history:
            for turn in chat_history:
                messages.append({"role": "user", "content": turn["q"]})
                messages.append({"role": "assistant", "content": turn["a"]})
        
        # Последний ход передает актуальный финансовый контекст
        messages.append({"role": "user", "content": _build_question_prompt(context, question)})
        
        llm_text = await asyncio.to_thread(_generate_with_history, SYSTEM_PROMPT_QUESTION, messages)
    except Exception:
        return local_text
    llm_text = sanitize_telegram_html(llm_text)
    return llm_text or local_text


async def parse_quick_add_ai(text: str) -> list[dict[str, Any]]:
    """Parse natural language text into a list of transaction drafts using AI."""
    if not has_openai_key():
        return []
    try:
        raw_json = await asyncio.to_thread(_generate, SYSTEM_PROMPT_QUICK_ADD, text)
        # Cleanup code blocks if AI wrapped it
        raw_json = re.sub(r"```json\s?|\s?```", "", raw_json).strip()
        data = json.loads(raw_json)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []
