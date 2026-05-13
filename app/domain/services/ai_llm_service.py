from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.domain.services.ai_consultant_service import (
    render_ai_insufficient_report,
    render_ai_question_answer,
    render_ai_report,
    render_ai_report_download,
)
from app.integrations.openai_client import get_openai_client, get_openai_model, has_openai_key

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
Ты — AI-консультант по личным финансам.

Работай строго по данным из JSON.
Нельзя:
- выдумывать отсутствующие факты
- смешивать валюты без конвертации
- изображать высокую точность на слабой базе
- придумывать мотивы пользователя
- подменять факты красивым текстом

Обязательно различай:
- факт
- оценку
- гипотезу
- нехватку данных

Если база слабая, не делай вид, что всё понятно. Прямо скажи, что вывод ограничен.

Формат:
<b>Вердикт</b>
<b>Что происходит</b>
<b>Риски</b>
<b>Что делать</b>
<b>Прогноз</b>

Стиль:
коротко, жёстко, прикладно.
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


def _build_payload(context: dict[str, Any]) -> dict[str, Any]:
    meta = context["meta"]
    current = context["current"]
    previous = context["previous"]
    month = context["month"]
    return {
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
            "active_accounts": context.get("active_accounts", [])[:6],
        },
        "budgets": context.get("budget_snapshot"),
        "debts": context.get("debt_snapshot"),
        "recurring_expenses": context.get("recurring_snapshot"),
        "recurring_incomes": context.get("recurring_income_snapshot"),
        "planned_operations": context.get("planned_snapshot"),
        "category_deltas": context.get("category_deltas", [])[:8],
        "month_history": context.get("month_history"),
    }


def _build_report_prompt(context: dict[str, Any]) -> str:
    return "Контекст:\n" + json.dumps(_build_payload(context), ensure_ascii=False, indent=2)


def _build_question_prompt(context: dict[str, Any], question: str) -> str:
    return (
        f"Вопрос пользователя:\n{question}\n\n"
        "Контекст по финансам:\n"
        + json.dumps(_build_payload(context), ensure_ascii=False, indent=2)
    )


def _generate(system_prompt: str, user_prompt: str) -> str:
    client = get_openai_client()
    response = client.responses.create(
        model=get_openai_model(),
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
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

    llm_text = sanitize_telegram_html(llm_text)
    if not llm_text:
        return local_short, local_download
    return llm_text, llm_text + "\n\n" + ("─" * 32) + "\n\n" + local_download


async def render_final_ai_question(context: dict[str, Any], question: str) -> str:
    local_text = render_ai_question_answer(context, question)
    if not has_openai_key():
        return local_text
    try:
        llm_text = await asyncio.to_thread(_generate, SYSTEM_PROMPT_QUESTION, _build_question_prompt(context, question))
    except Exception:
        return local_text
    llm_text = sanitize_telegram_html(llm_text)
    return llm_text or local_text
