import asyncio
import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

from app.domain.services.ai_llm_service import render_final_ai_question

async def test():
    context = {
        "user_id": 8092822438,
        "recent_transactions": [],
        "accounts": [],
        "categories": [],
        "weeklyStreak": [False]*7,
        "isPremium": True,
    }
    question = "Какое состояние моих финансов?"
    print("Testing OpenAI API call...")
    try:
        res = await render_final_ai_question(context, question)
        print("Success! Writing AI Response to file...")
        with open("scratch/test_ai_output.txt", "w", encoding="utf-8") as f:
            f.write(res)
        print("Done.")
    except Exception as e:
        print("Error during AI response generation:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
