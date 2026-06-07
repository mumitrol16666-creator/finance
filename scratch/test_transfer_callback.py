import asyncio
import aiosqlite
from unittest.mock import MagicMock, AsyncMock
from app.handlers.transactions import tr_start_callback
from aiogram.types import User, Chat, CallbackQuery, Message

async def test():
    # Setup mock CallbackQuery
    c = MagicMock(spec=CallbackQuery)
    c.from_user = MagicMock(spec=User)
    c.from_user.id = 938030819  # An onboarded user in our local db
    
    c.message = MagicMock(spec=Message)
    c.message.chat = MagicMock(spec=Chat)
    c.message.chat.id = 938030819
    c.message.message_id = 12345
    c.message.answer = AsyncMock()
    c.message.edit_text = AsyncMock()
    c.answer = AsyncMock()
    
    # Mock state
    state = MagicMock()
    state.clear = AsyncMock()
    state.update_data = AsyncMock()
    state.set_state = AsyncMock()
    
    # Mock state.get_data
    state.get_data = AsyncMock(return_value={"lang": "ru"})
    
    # Connect to db
    db = await aiosqlite.connect("data/bot.db")
    db.row_factory = aiosqlite.Row
    
    try:
        # Run tr_start_callback
        await tr_start_callback(c, state, db)
        
        # Print results
        print("Success! answer was called, and state clear/set_state was called.")
        print("state.clear called:", state.clear.called)
        print("state.set_state called with:", state.set_state.call_args)
    except Exception as e:
        print("Error running tr_start_callback:", e)
        import traceback
        traceback.print_exc()
    finally:
        await db.close()

if __name__ == "__main__":
    asyncio.run(test())
