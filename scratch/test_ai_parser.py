import asyncio
import json
import os
import sys

# Добавляем путь к проекту, чтобы импорты работали
sys.path.append(os.getcwd())

from app.domain.services.ai_llm_service import parse_quick_add_ai

async def test_parser():
    # Используем английский для теста, чтобы точно не было проблем с кодировкой в консоли
    test_text = "Today spent 2500 on taxi, also bought food for 12000, and yesterday paid internet 5500"
    
    print("--- PARSER TEST ---")
    print(f"Input: {test_text}\n")
    
    print("Calling AI (GPT-4)...")
    results = await parse_quick_add_ai(test_text)
    
    if not results:
        print("Error: No results from AI.")
        return

    print(f"Success! Found {len(results)} items:\n")
    for i, res in enumerate(results, 1):
        print(f"Item #{i}:")
        print(f"  - Amount: {res.get('amount')}")
        print(f"  - Kind: {res.get('kind')}")
        print(f"  - Category: {res.get('category_hint')}")
        print(f"  - Note: {res.get('note')}")
        print(f"  - Date offset: {res.get('date_offset')}")
        print("-" * 20)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    asyncio.run(test_parser())
