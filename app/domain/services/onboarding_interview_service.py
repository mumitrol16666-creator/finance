from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
import aiosqlite
from loguru import logger

from app.integrations.openai_client import get_openai_client, get_openai_model, has_openai_key
from app.db.repositories.settings_repo import save_onboarding_interview

SYSTEM_PROMPT = """
Ты — Onboarding Agent (вводный финансовый консультант) в Telegram-боте FinanceBot.
Твоя задача — провести мягкое, вовлекающее финансовое интервью с новым пользователем.
Многие люди боятся вести бюджет, им стыдно за свои траты. Твоя цель — снять эту тревожность, показать, что учет — это легко, проявить эмпатию.

=== ПРАВИЛА ВЕДЕНИЯ ДИАЛОГА ===
1. ПОЭТАПНОСТЬ: Отвечай строго на текущую реплику и задавай СТРОГО по одному вопросу за раз. Никогда не задавай два вопроса в одном сообщении.
2. ЭМПАТИЯ: Перед тем как задать следующий вопрос, коротко и с пониманием прокомментируй предыдущий ответ пользователя (например: "Ох, понимаю, импульсивные покупки часто приносят минутную радость, но потом расстраивают"). Покажи эмпатию, не осуждай.
3. КРАТКОСТЬ: Твой ответ должен быть не более 2-3 коротких предложений. Будь лаконичен.
4. ЯЗЫК: Отвечай на том же языке, на котором пишет пользователь (обычно это русский).

=== ЭТАПЫ ИНТЕРВЬЮ ===
- Этап 1: Ты спросил "Что тебя больше всего напрягает в деньгах?". Пользователь ответил.
  Твоя задача: Ответить с эмпатией на его боль и спросить про Этап 2: "Вспомни свою последнюю трату, из-за которой стало неприятно (например, спонтанный кофе, заказ еды или покупка одежды). Что это было и сколько примерно стоило?"
- Этап 2: Пользователь рассказал про неприятную трату.
  Твоя задача: Прокомментировать с пониманием и спросить про Этап 3: "А теперь давай о хорошем. Если бы деньги перестали быть проблемой и их хватало на всё самое важное, на что бы ты тратил(а) их в первую очередь?"
- Этап 3: Пользователь рассказал про свои цели/мечты.
  Твоя задача: Поддержать его цели и спросить про Этап 4 (лимит): "Чтобы двигаться к целям, важно определить комфортные границы. Сколько ты хотел(а) бы тратить в день на повседневные расходы (в твоей валюте)? Напиши просто число."
- Этап 4: Пользователь написал число (или текст с числом).
  Твоя задача: Сделать финальное резюме. Подведи итог интервью, определи его архетип:
    * chaotic — импульсивные траты, нет контроля
    * breaker — жестко контролирует, но периодически срывается
    * survivor — денег мало, постоянный стресс или долги
    * controller — всё ок, хочет оптимизировать
  Твой ответ на этом этапе должен состоять из двух частей:
  1. Теплый и ободряющий текст-резюме для пользователя (с эмодзи, описанием его архетипа и планом действий).
  2. Строго в самом конце сообщения добавь блок JSON следующего формата:
     ===JSON===
     {
       "main_goal": "краткое описание цели пользователя",
       "daily_limit": число_лимита,
       "archetype": "chaotic|breaker|survivor|controller"
     }
     ===JSON===

Помни: не выходи за рамки роли и строго придерживайся формата.
"""

def _generate(messages: list[dict[str, str]]) -> str:
    client = get_openai_client()
    response = client.responses.create(
        model=get_openai_model(),
        temperature=0.4,
        input=messages,
    )
    return response.output_text.strip()

async def generate_interview_response(history: list[dict[str, str]]) -> str:
    """Generate interview step response via OpenAI."""
    if not has_openai_key():
        raise RuntimeError("OpenAI API key is missing")
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    return await asyncio.to_thread(_generate, messages)

def parse_digit(text: str) -> int:
    """Extract first integer from text, defaults to 5000."""
    nums = re.findall(r"\d+", text.replace(" ", "").replace(",", "").replace(".", ""))
    if nums:
        return int(nums[0])
    return 5000

def parse_interview_json(ai_response: str) -> tuple[str, dict | None]:
    """
    Parses the JSON block from the AI response.
    Returns (cleaned_text_without_json, parsed_dict).
    """
    match = re.search(r"===JSON===\s*(\{.*?\})\s*===JSON===", ai_response, re.DOTALL)
    if not match:
        # Try a more relaxed search just in case
        match = re.search(r"(\{.*\})", ai_response, re.DOTALL)
        
    if match:
        try:
            json_str = match.group(1).strip()
            parsed = json.loads(json_str)
            # Remove the JSON part and markers from the text
            clean_text = ai_response.replace(match.group(0), "").strip()
            # Also clean up any trailing ===JSON=== markers
            clean_text = re.sub(r"===JSON===", "", clean_text).strip()
            return clean_text, parsed
        except Exception as e:
            logger.error(f"Failed to parse JSON from AI response: {e}")
            
    return ai_response, None


def determine_fallback_archetype(pain: str, regret: str, dream: str) -> str:
    """Simple rule-based archetype classifier for fallback mode."""
    text = f"{pain} {regret} {dream}".lower()
    
    # Check keywords for survivor
    if any(w in text for w in ["долг", "кредит", "не хват", "выжив", "мало", "бедн", "выживать", "кризис", "выживание"]):
        return "survivor"
    # Check keywords for breaker
    if any(w in text for w in ["срыв", "контролиру", "держусь", "срываюсь", "планиру", "срывы", "срываюсь"]):
        return "breaker"
    # Check keywords for chaotic
    if any(w in text for w in ["импульсив", "спонтан", "эмоци", "кофе", "кафе", "одежд", "шмот", "такси", "ресторан"]):
        return "chaotic"
    
    # Default is controller
    return "controller"

def get_archetype_desc(archetype: str) -> str:
    descs = {
        "chaotic": "Хаотик 🌀 (импульсивные траты, сложно удержать фокус)",
        "breaker": "Срыватель ⚡ (строго контролируешь бюджет, но периодически срываешься)",
        "survivor": "Выживающий 🛡 (высокий стресс из-за нехватки денег или долгов)",
        "controller": "Контролёр 📊 (всё под контролем, стремишься к оптимизации)"
    }
    return descs.get(archetype, descs["controller"])

def get_fallback_interview_response(stage: int, user_answer: str, data: dict) -> str:
    """Get static/templated fallback response for interview stage."""
    if stage == 1:
        comment = "Понимаю тебя. Отношения с деньгами бывают непростыми, особенно когда есть ощущение неопределенности или тревоги."
        question = "Вспомни свою последнюю трату, из-за которой стало неприятно (например, спонтанный кофе, заказ еды или покупка одежды). Что это было и сколько примерно стоило?"
        return f"{comment}\n\n{question}"
    
    elif stage == 2:
        comment = "Ох, это неприятное чувство после спонтанных трат знакомо многим. Мы часто совершаем их на эмоциях, а потом корим себя. Но с этим можно работать!"
        question = "А теперь давай о хорошем. Если бы деньги перестали быть проблемой и их хватало на всё самое важное, на что бы ты тратил(а) их в первую очередь?"
        return f"{comment}\n\n{question}"
        
    elif stage == 3:
        comment = "Отличная цель! Деньги — это инструмент для достижения того, что действительно приносит радость и развитие."
        question = "Чтобы двигаться к целям, важно определить комфортные границы. Сколько ты хотел(а) бы тратить в день на повседневные расходы (в твоей валюте)? Напиши просто число."
        return f"{comment}\n\n{question}"
        
    elif stage == 4:
        limit = parse_digit(user_answer)
        pain = data.get("stage_1_pain", "")
        regret = data.get("stage_2_regret", "")
        dream = data.get("stage_3_dream", "Финансовая независимость")
        
        archetype = determine_fallback_archetype(pain, regret, dream)
        archetype_desc = get_archetype_desc(archetype)
        
        summary = (
            "Спасибо за искренность! 😊\n\n"
            "На основе твоих ответов я составил твой финансовый профиль:\n"
            f"🎯 **Твоя цель:** {dream}\n"
            f"💰 **Дневной лимит:** {limit} (в твоей валюте)\n"
            f"🧠 **Твой архетип:** {archetype_desc}\n\n"
            "Я буду помогать тебе держать баланс без чувства вины!"
        )
        
        json_payload = {
            "main_goal": dream,
            "daily_limit": limit,
            "archetype": archetype
        }
        
        return f"{summary}\n\n===JSON===\n{json.dumps(json_payload, ensure_ascii=False)}\n===JSON==="
        
    return "Произошла ошибка. Пожалуйста, попробуй еще раз."

async def save_interview_results_to_db(db: aiosqlite.Connection, user_id: int, parsed_result: dict):
    """Saves the parsed JSON result of the onboarding interview to the database settings table."""
    archetype = parsed_result.get("archetype") or "controller"
    main_goal = parsed_result.get("main_goal") or "Финансовая стабильность"
    daily_limit = int(parsed_result.get("daily_limit") or 5000)
    
    from app.domain.money import get_user_currency, get_scale
    currency = await get_user_currency(db, user_id)
    scale = get_scale(currency)
    daily_limit_minor = daily_limit * scale
    
    now_str = datetime.now(timezone.utc).isoformat()
    await save_onboarding_interview(db, user_id, archetype, main_goal, daily_limit_minor, now_str)
    await db.commit()
