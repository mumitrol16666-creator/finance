import asyncio
import aiosqlite
from unittest.mock import MagicMock, AsyncMock
from app.handlers.common import login_command
from aiogram.types import User, Chat, Message

async def test():
    # Setup mock Message
    m = MagicMock(spec=Message)
    m.from_user = MagicMock(spec=User)
    m.from_user.id = 938030819  # An onboarded user in our local db
    m.chat = MagicMock(spec=Chat)
    m.chat.id = 938030819
    m.answer = AsyncMock()
    
    # Connect to db
    db = await aiosqlite.connect("data/bot.db")
    
    try:
        # Run login_command
        await login_command(m, db)
        
        # Print results
        print("Success! answer was called with:")
        print("Arguments:", m.answer.call_args)
    except Exception as e:
        print("Error running login_command:", e)
        import traceback
        traceback.print_exc()
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(test())
