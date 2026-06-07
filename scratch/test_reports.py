import asyncio
from app.db.connection import get_db
from app.handlers.reports import _reports_hub_text, _render_report
from aiogram.types import Message, Chat, User
from datetime import datetime, timezone

async def test():
    user_id = 6856090314  # ADMIN_IDS from .env
    print("Testing report hub text...")
    async with get_db() as db:
        try:
            text = await _reports_hub_text(db, user_id, "ru")
            print("Report Hub Text Success! Length:", len(text))
            print(text)
        except Exception as e:
            import traceback
            print("Error in _reports_hub_text:")
            traceback.print_exc()

        print("\nTesting period report rendering (month)...")
        # Mock message
        chat = Chat(id=user_id, type="private")
        user = User(id=user_id, is_bot=False, first_name="Admin")
        m = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=chat,
            from_user=user,
            text="/month"
        )
        try:
            # We can run the inner rendering code
            from app.db.repositories.settings_repo import get_timezone
            from app.handlers.reports import _period_meta, report_period, report_by_category, _labels, _build_month_plan_lines, _month_plan_snapshot
            tz_name = await get_timezone(db, user_id)
            now_utc = datetime.now(timezone.utc)
            meta = _period_meta("ru", tz_name, "month", now_utc)
            print("Meta:", meta)
            inc, exp, cnt = await report_period(db, user_id, meta["start"], meta["end"])
            print("Period report sums:", inc, exp, cnt)
            month_plan = await _month_plan_snapshot(db, user_id, tz_name, meta["end"])
            print("Month plan snapshot success!")
            lines = _build_month_plan_lines("ru", month_plan)
            print("Month plan lines success! Count:", len(lines))
        except Exception as e:
            import traceback
            print("Error in period report data collection:")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
