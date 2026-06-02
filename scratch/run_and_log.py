import asyncio
import traceback
import sys
import os

# Ensure working directory is correct
os.chdir(r'c:\FinanceBot')
sys.path.insert(0, os.getcwd())

# Force load of env
from dotenv import load_dotenv
load_dotenv()

with open('bot_startup_debug.log', 'w', encoding='utf-8') as f:
    f.write("Starting debug run...\n")
    try:
        import main
        f.write(f"Loaded main. Token in settings: {repr(main.settings.bot_token)}\n")
        f.write(f"Channel ID in settings: {repr(main.settings.main_channel_id)}\n")
        
        # Run main
        f.write("Calling main.main()...\n")
        asyncio.run(main.main())
    except Exception as e:
        f.write(f"Crashed with exception: {type(e).__name__}: {e}\n")
        traceback.print_exc(file=f)
    f.write("Finished debug run.\n")
print("Run finished. Check bot_startup_debug.log")
