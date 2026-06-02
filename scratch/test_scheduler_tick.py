import asyncio
import aiosqlite
import sys
from datetime import datetime, timezone, timedelta
from loguru import logger
from unittest.mock import AsyncMock

# Setup logger to stdout
logger.remove()
logger.add(sys.stdout, level="DEBUG")

from app.scheduler.notify_scheduler import tick_notify

async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    mock_bot = AsyncMock()
    
    print("Running tick_notify manually...")
    try:
        await tick_notify(mock_bot)
        print("tick_notify finished successfully!")
    except Exception as e:
        print(f"Exception raised by tick_notify: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
