import os
import sys
from dotenv import load_dotenv

# Load env variables from .env
load_dotenv()

# Add workspace to path
sys.path.append(os.path.abspath("."))

from app.domain.services.ai_llm_service import _generate

def test():
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("ERROR: No OPENAI_API_KEY found in .env")
            return
        
        print("API Key found in ENV:", api_key[:15] + "..." + api_key[-5:])
        print("Model found in ENV:", os.getenv("OPENAI_MODEL"))
        
        print("Sending test request to OpenAI...")
        res = _generate("You are a helpful assistant.", "Say 'Yes, I am working!'")
        print("\nSUCCESS! OpenAI response:")
        print(res)
    except Exception as e:
        print("\nERROR running OpenAI test:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test()
