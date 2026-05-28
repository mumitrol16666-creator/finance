from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any
from loguru import logger

from app.domain.services.ai_consultant_service import (
    render_ai_insufficient_report,
    render_ai_question_answer,
    render_ai_report,
    render_ai_report_download,
)
from app.domain.services.ai_payload_builder import build_llm_payload
from app.integrations.openai_client import get_openai_client, get_openai_model, has_openai_key

USE_ADVANCED_AI_REPORTS = True
MAX_REPORT_CHARS = 4500

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
- РАЗГРАНИЧИВАЙ ПОНЯТИЯ: Четко разделяй "Чистый результат за период" (доходы текущего периода минус расходы этого периода) и "Общий баланс на счетах" (total_balance). Если чистый результат за период отрицательный, но общий баланс положителен (благодаря накоплениям прошлых периодов), обязательно укажи на это пользователю: объясни, что дефицит этого периода покрывается накоплениями прошлых месяцев, общий баланс остается положительным, и паниковать не нужно.

ПРАВИЛА КАЧЕСТВА АНАЛИЗА:
- Опирайся исключительно на предоставленные данные. Если факта нет в контексте — не додумывай.
- Избегай психологических интерпретаций; фокусируйся на числах и фактах.
- Причины трат комментируй только если они явно следуют из примечаний к транзакциям.
- Вероятностные выводы помечай как предположения, указывая уровень уверенности из поля confidence.
- Обрати внимание: каждый блок лучше ограничить 3-5 ёмкими предложениями без мотивационной воды.
- Если в данных есть поле is_probably_recurring у спайка — это скорее регулярный платёж, а не аномалия.

СТРУКТУРА ОТЧЕТА:
🎯 <b>ЦЕЛЬ: [Название цели]</b>
- [Анализ прогресса к финансовой цели, оценка реалистичности достижения на основе прогнозов. ВАЖНО: Если в контексте указано, что месяцев до достижения цели (ETA) равно 0, или баланс/накопления больше или равны сумме цели, обязательно укажи, что цель уже достигнута (накопленных средств достаточно для покупки прямо сейчас), и поздравь пользователя. Иначе оцени ETA (в месяцах) и главные препятствия к ее достижению]

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
Ты — финансовый AI-консультант в Telegram-боте. Пользователь общается с тобой в режиме чата.

ГЛАВНОЕ ПРАВИЛО: Будь КРАТКИМ. Максимум 3-5 предложений на ответ. Никаких эссе.
В контексте тебе передан список последних транзакций пользователя ("recent_transactions").
Используй его, чтобы отвечать на конкретные вопросы о тратах (например, "на что я тратил", "сколько ушло на продукты", "какой средний чек"). 

Формат ответа:
- 1-2 предложения: факт из данных (ссылайся на конкретные транзакции, заметки или категории, если пользователь спросил о них)
- 1 предложение: вывод
- 1 предложение: конкретный совет (если уместно)

Правила:
- отвечай только на базе переданного финансового контекста и транзакций
- если данных недостаточно — скажи прямо в 1 предложении
- не выдумывай цифры, сроки, мотивы
- не повторяй вопрос пользователя
- не используй заголовки и списки для коротких ответов
- используй HTML-теги только <b> и <i>
- если пользователь пишет не про финансы — мягко верни к теме денег
- учитывай историю чата (предыдущие сообщения) для контекста диалога
- РАЗГРАНИЧИВАЙ ПОНЯТИЯ: Четко разделяй "Чистый результат за период" (доходы текущего периода минус расходы этого периода) и "Общий баланс на счетах" (total_balance). Если пользователь беспокоится о минусе или дефиците, когда его общий баланс положителен, объясни ему, что минус относится к текущему периоду (месяцу), а общий баланс остаётся положительным за счёт прошлых накоплений.
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
3. ФОРМАТИРОВАНИЕ ПОЛЯ "note":
   - Сделай первую букву заглавной
   - Исправь опечатки и грамматические ошибки
   - Убери слова-паразиты ("ну", "типа", "э-э", "короче", "как бы")
   - Сделай текст лаконичным и грамотным
   - НЕ включай в note сумму, категорию или название счёта — только описание покупки/действия

ПРИМЕР:
Текст: "Вчера купил кофе 1200 и сегодня пришла зп 500000 на каспи"
Ответ:
[
  {"amount": 1200, "kind": "expense", "category_hint": "Кофе", "account_hint": null, "note": "кофе", "date_offset": -1},
  {"amount": 500000, "kind": "income", "category_hint": "Зарплата", "account_hint": "каспи", "note": "зп", "date_offset": 0}
]

Если сумм в тексте нет, верни пустой массив [].
""".strip()


# _build_payload logic moved to app.domain.services.ai_payload_builder


def _build_report_prompt(context: dict[str, Any]) -> str:
    payload = build_llm_payload(context)
    payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
    logger.info("AI Report Payload: {} chars (~{} tokens)", len(payload_str), len(payload_str) // 4)
    return "Контекст:\n" + payload_str


def _build_question_prompt(context: dict[str, Any], question: str) -> str:
    payload = build_llm_payload(context)
    payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
    logger.info("AI Question Payload: {} chars (~{} tokens)", len(payload_str), len(payload_str) // 4)
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

    prompt_text = _build_report_prompt(context)
    t0 = time.monotonic()
    try:
        llm_text = await asyncio.to_thread(_generate, SYSTEM_PROMPT_REPORT, prompt_text)
        gen_time = time.monotonic() - t0
        logger.info(
            "ai_report_quality | payload_chars={} tokens_est={} response_chars={} gen_time={:.2f}s confidence={}",
            len(prompt_text), len(prompt_text) // 4, len(llm_text), gen_time, context.get("analysis_confidence"),
        )
    except Exception:
        gen_time = time.monotonic() - t0
        logger.warning("ai_report_fallback | gen_time={:.2f}s used_fallback=True", gen_time)
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
                logger.exception(f"Failed to log AI recommendation: {e}")
            
            # Clean recommendation tag from the LLM output
            llm_text = re.sub(
                r'\[REC:\s*type=["\'][^"\']+["\'],\s*target_metric=["\'][^"\']+["\'],\s*start_val=[0-9.-]+,\s*goal_val=[0-9.-]+,\s*text=["\'][^"\']+["\']\]',
                '',
                llm_text
            ).strip()

    # Hard report size limiter
    if len(llm_text) > MAX_REPORT_CHARS:
        truncated = llm_text[:MAX_REPORT_CHARS]
        parts = truncated.rsplit('\n\n', 1)
        llm_text = parts[0] if len(parts) > 1 else truncated
        llm_text += "\n\n<i>...полный отчёт доступен в скачиваемой версии</i>"

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


async def transcribe_audio_ai(file_path: str) -> str:
    """Transcribe an audio file (ogg/opus) to text using OpenAI Whisper.

    Runs the synchronous OpenAI call inside ``asyncio.to_thread`` so the
    event loop is never blocked.

    Returns the transcribed text or an empty string on failure.
    """
    if not has_openai_key():
        return ""
    try:
        def _do_transcribe() -> str:
            client = get_openai_client()
            with open(file_path, "rb") as audio:
                result = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio,
                    language="ru",
                )
            return (result.text or "").strip()

        return await asyncio.to_thread(_do_transcribe)
    except Exception as exc:
        logger.warning("Whisper transcription failed: {}", exc)
        return ""

