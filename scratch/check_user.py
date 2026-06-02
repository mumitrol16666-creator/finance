import asyncio
import aiosqlite
import sys
from app.domain.services.access_service import get_user_context, get_available_features, can_use_feature, FEATURE_REPORTS

async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    db = await aiosqlite.connect("data/bot.db")
    db.row_factory = aiosqlite.Row
    
    cur = await db.execute("SELECT * FROM users WHERE user_id = 8092822438")
    row = await cur.fetchone()
    if row:
        print("--- USER ROW ---")
        for k in row.keys():
            print(f"{k}: {row[k]}")
            
        ctx = await get_user_context(db, 8092822438)
        print("\n--- ACCESS CONTEXT ---")
        print(ctx)
        
        features = await get_available_features(db, 8092822438)
        print("\n--- AVAILABLE FEATURES ---")
        print(features)
        
        can_reports = await can_use_feature(db, 8092822438, FEATURE_REPORTS)
        print(f"\nCan use reports: {can_reports}")
    else:
        print("User not found in DB")
        
    await db.close()

if __name__ == "__main__":
    asyncio.run(main())
